"""No gate may run against a lockfile nothing has checked, or quietly rewrite one.

`uv.lock` is a committed artifact that stands in for a computation: the resolution of
`pyproject.toml`. Every guarantee the CI jobs make -- the audited dependency set, the
digest-pinned toolchain, the reproducible wheel -- is a guarantee about *that* resolution.
Nothing in this repository compared the two.

Worse than nothing, in fact. A bare `uv run` implicitly syncs before it runs, and an
implicit sync re-resolves and rewrites `uv.lock` when it disagrees with `pyproject.toml`.
Measured here: bump `project.version`, run `make lint`, and it prints "All checks passed!"
while `uv.lock`'s sha256 changes in the working tree (279d6a55... -> 52052369...). The gate
reported green having silently repaired the drift a lockfile exists to make visible, and left
the repair sitting in the working tree for the next `git add` to sweep up.

And `uv sync --frozen`, which is what CI ran, could never have caught it. `--frozen` means
"install exactly what `uv.lock` records and never re-resolve" -- it does not read
`pyproject.toml` at all, so by construction it cannot notice that the two disagree. On the
drifted pair above it exits 0, having installed `obligation-receipts==0.1.1` from a lock
still recording `0.1.0`. A release is the one change guaranteed to desynchronise the lock,
and it is precisely the change `--frozen` is structurally blind to.

Two rules follow:

1. `uv lock --check` runs first in `verify`, before any target that could rewrite what it
   checks. It re-resolves against `pyproject.toml` and fails when the lock no longer
   satisfies it.
2. Every `uv run`, `uv sync` and `uv export` passes `--locked`, so each invocation makes the
   same assertion and refuses to run rather than relock. Ordering then stops being
   load-bearing: no gate can execute against a drifted lock even when it is invoked alone.

The rules are universal; this file's scope used to be one file. It read the `Makefile` and
`.github/workflows/ci.yml` and nothing else, and the two invocations it could not see were
the two the rules were written for:

* `.github/workflows/release.yml` ran `uv sync --frozen` -- the flag documented above as
  structurally blind to drift, on the one path where a version bump guarantees drift. The
  release job would have built a candidate for the tagged version from a lock recording the
  previous one, and reported green.
* `.pre-commit-config.yaml`'s mypy hook ran a bare `entry: uv run mypy` at the `pre-push`
  stage: an implicit sync, and therefore a silent rewrite of `uv.lock` in the working tree,
  in the instant before a push.

So the scope now is every place a gate is invoked from: the `Makefile`, every file GitHub
would execute as a workflow (both the `.yml` and `.yaml` spellings, discovered by glob and
asserted against the directory listing so a new workflow cannot reintroduce `--frozen`
unseen), and `.pre-commit-config.yaml`.
"""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).parents[1]
_MAKEFILE = _ROOT / "Makefile"
_WORKFLOW_DIR = _ROOT / ".github/workflows"
#: GitHub honours both spellings, so a gate that reads only one of them is blind to any
#: workflow written with the other.
_WORKFLOW_SUFFIXES = ("*.yml", "*.yaml")
_PRE_COMMIT = _ROOT / ".pre-commit-config.yaml"

#: Every uv subcommand that reads or writes the lock and therefore has to assert it.
#: `uv lock --check` is the assertion itself and `uv build` neither reads nor writes the
#: lock, so neither is listed. `uvx` runs a tool from the index rather than this project's
#: environment and never touches `uv.lock`, and `uv\s` does not match it.
_LOCK_SENSITIVE = ("run", "sync", "export")


def _workflow_files() -> list[Path]:
    """Every file GitHub would execute as a workflow, in both spellings."""
    return sorted(path for suffix in _WORKFLOW_SUFFIXES for path in _WORKFLOW_DIR.glob(suffix))


def _recipe_lines() -> list[str]:
    """The Makefile's executable recipe lines: tab-indented, and not a `@#` comment.

    Reading only what make actually runs is the point. A rule satisfied by a line of prose
    describing `--locked` would be a check that cannot fail.
    """
    lines = [
        line.lstrip("\t").lstrip("@").rstrip()
        for line in _MAKEFILE.read_text(encoding="utf-8").splitlines()
        if line.startswith("\t")
    ]
    recipes = [line for line in lines if line and not line.startswith("#")]
    assert recipes, "no recipe lines parsed out of the Makefile; the reader is broken"
    return recipes


#: A `run:` key, at the start of a step (`- run:`) or under a `name:` on its own line, and
#: in either the scalar or the block-scalar form. The leading `- ` is part of the key's
#: indentation: a reader that required `run:` to be the first token on its line would skip
#: every step that omits `name:`, which is a legal and common way to write one.
_RUN_KEY = r"^(?P<prefix>\s*(?:-\s+)?)run:\s*"


def _run_lines(text: str) -> list[str]:
    """Every shell line a workflow step executes, from `run:` scalars and `run: |` blocks."""
    lines: list[str] = []
    source = text.splitlines()
    for index, line in enumerate(source):
        inline = re.match(rf"{_RUN_KEY}(?![|>])(?P<command>\S.*)$", line)
        if inline is not None:
            lines.append(inline.group("command").strip())
            continue
        block = re.match(rf"{_RUN_KEY}[|>][-+]?\s*$", line)
        if block is None:
            continue
        indent = len(block.group("prefix"))
        for following in source[index + 1 :]:
            if following.strip() and len(following) - len(following.lstrip()) <= indent:
                break
            if following.strip():
                lines.append(following.strip())
    return lines


def _workflow_run_lines() -> list[tuple[str, str]]:
    """Every workflow shell line in the repository, labelled with the file that runs it."""
    labelled = [
        (workflow.name, line)
        for workflow in _workflow_files()
        for line in _run_lines(workflow.read_text(encoding="utf-8"))
    ]
    assert labelled, "no run lines parsed out of any workflow; the reader is broken"
    return labelled


def _hook_args(lines: list[str], index: int, indent: int) -> list[str]:
    """The `args:` pre-commit appends to the `entry:` found at `lines[index]`."""
    words: list[str] = []
    for offset, line in enumerate(lines[index + 1 :], start=index + 1):
        if line.strip() and len(line) - len(line.lstrip()) < indent:
            break  # dedented out of this hook
        inline = re.match(rf"^ {{{indent}}}args:\s*\[(?P<items>.*)\]\s*$", line)
        if inline is not None:
            words += [item.strip().strip("\"'") for item in inline.group("items").split(",")]
            continue
        if re.match(rf"^ {{{indent}}}args:\s*$", line) is None:
            continue
        for following in lines[offset + 1 :]:
            item = re.match(r"^\s+-\s*(\S.*?)\s*$", following)
            if item is None:
                break
            words.append(item.group(1).strip("\"'"))
    return [word for word in words if word]


def _pre_commit_commands(text: str) -> list[str]:
    """Every command line `.pre-commit-config.yaml` hands to a shell.

    A local hook runs its `entry` with its `args` appended, so both are read and joined:
    a lock-sensitive uv invocation is one whichever of the two spells it.
    """
    lines = text.splitlines()
    commands: list[str] = []
    for index, line in enumerate(lines):
        entry = re.match(r"^(\s*)entry:\s*(\S.*?)\s*$", line)
        if entry is None:
            continue
        indent = len(entry.group(1))
        commands.append(" ".join([entry.group(2), *_hook_args(lines, index, indent)]))
    return commands


def _unlocked(lines: list[str]) -> list[str]:
    """Lock-sensitive uv invocations that do not assert the lock."""
    pattern = re.compile(rf"(?<!\S)uv\s+({'|'.join(_LOCK_SENSITIVE)})\b(.*)$")
    offenders = []
    for line in lines:
        match = pattern.search(line)
        if match is not None and "--locked" not in match.group(2):
            offenders.append(line)
    return offenders


def _every_invocation() -> list[tuple[str, str]]:
    """Every shell line any gate in this repository runs, labelled with its source."""
    invocations = [*_workflow_run_lines()]
    invocations += [
        (_PRE_COMMIT.name, command)
        for command in _pre_commit_commands(_PRE_COMMIT.read_text(encoding="utf-8"))
    ]
    return invocations


def test_the_reader_finds_the_uv_invocations_it_is_meant_to_police() -> None:
    """The guard against a green run that parsed nothing.

    Every assertion below is "no offenders found". That is worth exactly as much as the
    parser's ability to find a `uv run` at all, so prove it can before trusting a clean
    result -- and prove it on synthetic drifted input, not only on the real files.
    """
    assert _unlocked(["uv run pytest"]) == ["uv run pytest"]
    assert _unlocked(["uv sync --frozen"]) == ["uv sync --frozen"]
    assert _unlocked(["uv run --locked pytest"]) == []
    assert _unlocked(["uvx --from semgrep==1.168.0 semgrep scan src"]) == []

    # Both `run:` spellings, because a workflow may use either and a reader that saw only
    # the scalar form would skip every multi-line install step in this repository.
    synthetic = "jobs:\n  j:\n    steps:\n      - run: uv sync --frozen\n      - run: |\n"
    synthetic += "          uv export --locked --no-hashes\n          make verify\n"
    assert _run_lines(synthetic) == [
        "uv sync --frozen",
        "uv export --locked --no-hashes",
        "make verify",
    ]

    # `entry:` plus `args:` in both YAML spellings, joined the way pre-commit runs them.
    hooks = "    hooks:\n      - id: a\n        entry: uv run mypy\n      - id: b\n"
    hooks += "        entry: uv run pytest\n        args: [--locked, -q]\n      - id: c\n"
    hooks += "        entry: uv run\n        args:\n          - --locked\n          - ruff\n"
    assert _pre_commit_commands(hooks) == [
        "uv run mypy",
        "uv run pytest --locked -q",
        "uv run --locked ruff",
    ]
    assert _unlocked(_pre_commit_commands(hooks)) == ["uv run mypy"]

    recipes = _recipe_lines()
    assert sum(1 for line in recipes if re.search(r"(?<!\S)uv\s+run\b", line)) >= 8, (
        f"only found {recipes} -- the Makefile reader is not seeing the recipes it polices"
    )
    installs = [line for _, line in _every_invocation() if re.search(r"(?<!\S)uv\s+sync\b", line)]
    assert len(installs) >= 2, (
        f"found {installs} -- the reader is not seeing every workflow's install step"
    )
    assert any(
        re.search(r"(?<!\S)uv\s", command)
        for command in _pre_commit_commands(_PRE_COMMIT.read_text(encoding="utf-8"))
    ), "the .pre-commit-config.yaml reader found no uv invocation; it is not reading the hooks"


def test_every_workflow_file_is_discovered_by_the_lock_gate() -> None:
    """The gate's own file discovery must cover what GitHub would run.

    Asserted separately from the rules below, so that a workflow added under an unread
    suffix fails here loudly instead of being silently exempt from them. This gate was
    scoped to a hardcoded `ci.yml`; the `uv sync --frozen` it could not see was sitting in
    `release.yml` the whole time.
    """
    executed = {path for path in _WORKFLOW_DIR.iterdir() if path.is_file()}
    assert executed, "no workflow files found"
    assert executed == set(_workflow_files()), (
        "these workflow files are not read by the lockfile gate: "
        f"{sorted(path.name for path in executed - set(_workflow_files()))}"
    )
    assert _PRE_COMMIT.is_file(), f"{_PRE_COMMIT.name} is missing; the gate reads nothing"


def test_no_makefile_gate_can_run_against_an_unasserted_lock() -> None:
    """Every lock-sensitive uv invocation in the Makefile passes `--locked`."""
    offenders = _unlocked(_recipe_lines())
    assert not offenders, (
        "these Makefile recipe lines let uv re-resolve and silently rewrite uv.lock: "
        f"{offenders}. Pass --locked so the invocation refuses to run rather than relock."
    )


def test_no_gate_anywhere_installs_from_a_lock_it_has_not_asserted() -> None:
    """The same rule everywhere a gate is invoked from, not just in `ci.yml`.

    `--frozen` is not a weaker version of this check; it is a different operation that
    cannot perform this check at all.
    """
    invocations = _every_invocation()
    offenders = [f"{source}: {line}" for source, line in invocations if _unlocked([line])]
    assert not offenders, f"these steps do not assert uv.lock against pyproject.toml: {offenders}"
    frozen = [f"{source}: {line}" for source, line in invocations if "--frozen" in line]
    assert not frozen, (
        f"these steps still use --frozen: {frozen}. It installs from uv.lock without "
        "reading pyproject.toml and therefore exits 0 on exactly the drift it appears to "
        "guard. (Checked on the run lines and hook entries, not the file text, so a "
        "comment explaining why --frozen is wrong cannot satisfy or break this.)"
    )


def test_verify_checks_the_lock_before_any_gate_that_could_rewrite_it() -> None:
    """`lock-check` is the first prerequisite of `verify`, and it is a real target."""
    text = _MAKEFILE.read_text(encoding="utf-8")
    prerequisites = re.search(r"^verify:[ \t]*(.*)$", text, re.M)
    assert prerequisites is not None, "the Makefile has no `verify` target"
    names = prerequisites.group(1).split()
    assert names and names[0] == "lock-check", (
        f"`verify` runs {names} -- lock-check must come first, before a target that "
        f"could rewrite the lock it checks"
    )
    assert re.search(r"^lock-check:[ \t]*$", text, re.M), "lock-check is not a real target"
    recipe = re.search(r"^lock-check:[ \t]*\n((?:\t.*\n)+)", text, re.M)
    assert recipe is not None and "uv lock --check" in recipe.group(1), (
        "lock-check must run `uv lock --check`: it is the only uv command that re-resolves "
        "pyproject.toml and compares the result against the committed lock"
    )


def test_verify_and_lock_check_are_declared_phony() -> None:
    """A `lock-check` file in the tree must not be able to switch the gate off."""
    phony = re.search(r"^\.PHONY:[ \t]*(.*)$", _MAKEFILE.read_text(encoding="utf-8"), re.M)
    assert phony is not None, "the Makefile declares no .PHONY targets"
    declared = set(phony.group(1).split())
    assert {"verify", "lock-check", "install"} <= declared, (
        f".PHONY omits {sorted({'verify', 'lock-check', 'install'} - declared)}"
    )
