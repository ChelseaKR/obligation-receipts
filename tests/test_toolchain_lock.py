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

Two rules follow, and this file holds the `Makefile` and `.github/workflows/ci.yml` to both:

1. `uv lock --check` runs first in `verify`, before any target that could rewrite what it
   checks. It re-resolves against `pyproject.toml` and fails when the lock no longer
   satisfies it.
2. Every `uv run`, `uv sync` and `uv export` passes `--locked`, so each invocation makes the
   same assertion and refuses to run rather than relock. Ordering then stops being
   load-bearing: no gate can execute against a drifted lock even when it is invoked alone.
"""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).parents[1]
_MAKEFILE = _ROOT / "Makefile"
_CI = _ROOT / ".github/workflows/ci.yml"

#: Every uv subcommand that reads or writes the lock and therefore has to assert it.
#: `uv lock --check` is the assertion itself and `uv build` neither reads nor writes the
#: lock, so neither is listed.
_LOCK_SENSITIVE = ("run", "sync", "export")


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


def _ci_run_lines() -> list[str]:
    """Every shell line a CI step executes, from `run:` scalars and `run: |` blocks."""
    lines: list[str] = []
    text = _CI.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(text):
        inline = re.match(r"^\s*run:\s*(?!\|)(\S.*)$", line)
        if inline is not None:
            lines.append(inline.group(1).strip())
            continue
        block = re.match(r"^(\s*)run:\s*\|\s*$", line)
        if block is None:
            continue
        indent = len(block.group(1))
        for following in text[index + 1 :]:
            if following.strip() and len(following) - len(following.lstrip()) <= indent:
                break
            if following.strip():
                lines.append(following.strip())
    assert lines, "no run lines parsed out of ci.yml; the reader is broken, not the file"
    return lines


def _unlocked(lines: list[str]) -> list[str]:
    """Lock-sensitive uv invocations that do not assert the lock."""
    pattern = re.compile(rf"(?<!\S)uv\s+({'|'.join(_LOCK_SENSITIVE)})\b(.*)$")
    offenders = []
    for line in lines:
        match = pattern.search(line)
        if match is not None and "--locked" not in match.group(2):
            offenders.append(line)
    return offenders


def test_the_reader_finds_the_uv_invocations_it_is_meant_to_police() -> None:
    """The guard against a green run that parsed nothing.

    Every assertion below is "no offenders found". That is worth exactly as much as the
    parser's ability to find a `uv run` at all, so prove it can before trusting a clean
    result -- and prove it on a synthetic drifted line, not only on the real files.
    """
    assert _unlocked(["uv run pytest"]) == ["uv run pytest"]
    assert _unlocked(["uv sync --frozen"]) == ["uv sync --frozen"]
    assert _unlocked(["uv run --locked pytest"]) == []

    recipes = _recipe_lines()
    assert sum(1 for line in recipes if re.search(r"(?<!\S)uv\s+run\b", line)) >= 8, (
        f"only found {recipes} -- the Makefile reader is not seeing the recipes it polices"
    )
    assert any("uv sync" in line for line in _ci_run_lines()), (
        "the ci.yml reader found no `uv sync`; it is not reading the install step"
    )


def test_no_makefile_gate_can_run_against_an_unasserted_lock() -> None:
    """Every lock-sensitive uv invocation in the Makefile passes `--locked`."""
    offenders = _unlocked(_recipe_lines())
    assert not offenders, (
        "these Makefile recipe lines let uv re-resolve and silently rewrite uv.lock: "
        f"{offenders}. Pass --locked so the invocation refuses to run rather than relock."
    )


def test_no_ci_step_installs_from_a_lock_it_has_not_asserted() -> None:
    """The same rule in the workflow, where `uv sync --frozen` used to sit.

    `--frozen` is not a weaker version of this check; it is a different operation that
    cannot perform this check at all.
    """
    offenders = _unlocked(_ci_run_lines())
    assert not offenders, (
        f"these ci.yml steps do not assert uv.lock against pyproject.toml: {offenders}"
    )
    frozen = [line for line in _ci_run_lines() if "--frozen" in line]
    assert not frozen, (
        f"these ci.yml steps still use --frozen: {frozen}. It installs from uv.lock "
        "without reading pyproject.toml and therefore exits 0 on exactly the drift it "
        "appears to guard. (Checked on the run lines, not the file text, so the comment "
        "explaining why --frozen is wrong cannot satisfy or break this.)"
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
