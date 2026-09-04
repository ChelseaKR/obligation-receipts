import re
import shutil
import subprocess
from pathlib import Path

# GitHub honours both spellings, so a gate that reads only one of them is blind
# to any workflow written with the other.
_WORKFLOW_SUFFIXES = ("*.yml", "*.yaml")


def workflow_files(root: Path) -> list[Path]:
    """Every file GitHub would execute as a workflow, in both spellings."""
    directory = root / ".github/workflows"
    return sorted(path for suffix in _WORKFLOW_SUFFIXES for path in directory.glob(suffix))


def test_every_workflow_file_is_discovered_by_the_supply_chain_gate() -> None:
    """The gate's own file discovery must cover what GitHub would run.

    Asserted separately so that a workflow added under an unread suffix fails
    here loudly rather than being silently skipped by the checks below.
    """
    root = Path(__file__).parents[1]
    directory = root / ".github/workflows"
    executed = {path for path in directory.iterdir() if path.is_file()}
    assert executed, "no workflow files found"
    assert executed == set(workflow_files(root)), (
        "these workflow files are not read by the supply-chain gate: "
        f"{sorted(str(path.name) for path in executed - set(workflow_files(root)))}"
    )


def test_ci_actions_are_digest_pinned() -> None:
    root = Path(__file__).parents[1]
    workflows = workflow_files(root)
    assert workflows
    action_pattern = re.compile(r"^\s*(?:-\s+)?uses:\s*[^@\s]+@([0-9a-f]{40})(?:\s+#.*)?$")
    for workflow in workflows:
        text = workflow.read_text(encoding="utf-8")
        uses_lines = [line for line in text.splitlines() if "uses:" in line]
        assert uses_lines
        assert all(action_pattern.fullmatch(line) for line in uses_lines)
        assert "pull_request_target:" not in text
        assert "permissions: write-all" not in text


#: Ways to publish, spelled as commands. A blocklist of spellings is open-ended by
#: construction -- these four were the whole check, and `twine upload`, `hatch publish`,
#: `flit publish` and a plain POST to the PyPI legacy upload API all walked past it -- so
#: this list is the weaker half of the publication ban and is not relied on alone.
_PUBLISH_COMMANDS = (
    "gh release create",
    "pypa/gh-action-pypi-publish",
    "pypi-publish",
    "uv publish",
    "twine upload",
    "hatch publish",
    "flit publish",
    "poetry publish",
    "upload.pypi.org",
    "test.pypi.org",
    "softprops/action-gh-release",
    "ncipollo/release-action",
)

#: Ways to publish, spelled as capability. This is the half that closes: a job cannot
#: create a GitHub release without `contents: write` or push a package to the registry
#: without `packages: write`, whatever binary it invokes to do it. `attestations: write`
#: and `id-token: write` are not on this list -- release.yml needs both to attest and sign
#: the candidate, and neither can publish anything.
_PUBLISH_PERMISSIONS = ("contents: write", "packages: write")


def _publication_capabilities(text: str) -> list[str]:
    """Everything in one workflow that could publish a release or a distribution."""
    return [needle for needle in _PUBLISH_COMMANDS + _PUBLISH_PERMISSIONS if needle in text]


def test_no_workflow_can_publish_a_release() -> None:
    """The publication ban has to cover every workflow, not one filename.

    This read a hardcoded `.github/workflows/release.yml`. A second workflow --
    `publish.yml`, say -- could have declared `contents: write` and run
    `gh release create`, and passed every assertion in this file, because nothing
    read it. The ban now applies to every file GitHub would execute.

    Widened in the other direction too. The old list named four publish commands;
    the set of ways to upload a distribution is not four, and is not closed. So the
    ban is stated as capability as well as spelling: `gh api` is not on the command
    list precisely because ci.yml's pin-identity step uses it under `contents: read`,
    and it is the permission blocklist, not a spelling, that stops the same binary
    from being pointed at the releases endpoint.
    """
    root = Path(__file__).parents[1]
    workflows = workflow_files(root)
    assert workflows

    # The reader must be able to fail. Both halves, on synthetic text, before any
    # clean result from the real files is worth reading.
    assert _publication_capabilities("permissions:\n  contents: write\n") == ["contents: write"]
    assert _publication_capabilities("run: twine upload dist/*\n") == ["twine upload"]
    assert _publication_capabilities("permissions:\n  contents: read\n") == []

    offenders = [
        f"{workflow.name}: {found}"
        for workflow in workflows
        for found in _publication_capabilities(workflow.read_text(encoding="utf-8"))
    ]
    assert not offenders, (
        f"these workflows can publish a release or a distribution: {offenders}. "
        "Publication is a human step performed against a signed, attested candidate; "
        "no workflow in this repository is permitted to do it."
    )

    release = (root / ".github/workflows/release.yml").read_text(encoding="utf-8")
    assert "name: release-candidate" in release, (
        "release.yml must announce itself as a candidate builder, not a publisher"
    )


_THIS_REPO = "chelseakr/obligation-receipts"
_PINNED_USES = re.compile(r"^\s*(?:-\s+)?uses:\s*([^@\s]+)@[0-9a-f]{40}")
_IGNORED_NAME = re.compile(r"^\s*-\s*dependency-name:\s*[\"']?([^\"'\s]+)[\"']?\s*$")


def _cross_repo_reusable_workflows(root: Path) -> set[str]:
    """Dependency names Dependabot derives from reusable workflows in other repos."""
    names: set[str] = set()
    for workflow in workflow_files(root):
        for line in workflow.read_text(encoding="utf-8").splitlines():
            match = _PINNED_USES.match(line)
            if match is None:
                continue
            target = match.group(1).lower()
            # A plain action is `owner/repo`; a reusable workflow carries a path
            # to the workflow file, which is what Dependabot names it by.
            if not target.endswith((".yml", ".yaml")):
                continue
            if target.startswith(f"{_THIS_REPO}/"):
                continue
            names.add(target)
    return names


def _dependabot_ignored_dependencies(root: Path) -> set[str]:
    text = (root / ".github/dependabot.yml").read_text(encoding="utf-8")
    return {
        match.group(1).lower()
        for line in text.splitlines()
        if (match := _IGNORED_NAME.match(line)) is not None
    }


def test_dependabot_ignore_list_matches_the_cross_repo_reusable_workflow_pins() -> None:
    """Keep `.github/dependabot.yml` and the workflow pins from drifting apart.

    Dependabot cannot read a reusable workflow held in a private repository
    under a personal account, and one unreachable dependency fails the whole
    weekly update run even when every other action updated cleanly. Each such
    pin therefore has to be ignored explicitly. Both directions are asserted so
    that neither a renamed workflow nor a stale ignore entry can quietly
    reintroduce the failure or quietly suppress a live dependency.
    """
    root = Path(__file__).parents[1]
    referenced = _cross_repo_reusable_workflows(root)
    ignored = _dependabot_ignored_dependencies(root)

    assert referenced, "expected at least one cross-repository reusable workflow pin"
    assert referenced <= ignored, (
        "these cross-repository reusable workflows are pinned but not ignored by "
        f"Dependabot, so the weekly update job will fail on them: {sorted(referenced - ignored)}"
    )
    assert ignored <= referenced, (
        "these Dependabot ignore entries no longer match any pinned reusable "
        f"workflow and are suppressing nothing: {sorted(ignored - referenced)}"
    )


_SEMGREP_COMMAND = re.compile(r"semgrep scan\s+(?P<flags>[^\n]*)")

#: Semgrep flags that consume the word after them. A flag missing from this set has its
#: value read as a scan target -- `--metrics off` used to contribute a target named `off`
#: -- which is why every target is asserted to be a real path below.
_SEMGREP_VALUE_FLAGS = frozenset(
    {"--config", "--metrics", "--exclude", "--include", "--severity", "--jobs", "--output"}
)


def _semgrep_targets(root: Path) -> list[str]:
    """The paths the workflows tell Semgrep to scan.

    Read from every workflow rather than a hardcoded `ci.yml`, and required to be a
    single invocation: a second, narrower `semgrep scan` elsewhere would otherwise be
    a scope this gate never sees.
    """
    commands = [
        match
        for workflow in workflow_files(root)
        for match in _SEMGREP_COMMAND.findall(workflow.read_text(encoding="utf-8"))
    ]
    assert len(commands) == 1, f"expected exactly one `semgrep scan` step, found {commands}"
    words = commands[0].split()
    targets = []
    skip_next = False
    for word in words:
        if skip_next:
            skip_next = False
            continue
        if word.startswith("--"):
            skip_next = word in _SEMGREP_VALUE_FLAGS
            continue
        targets.append(word)
    assert targets, "the semgrep step names no scan targets"
    missing = [target for target in targets if not (root / target).exists()]
    assert not missing, (
        f"the semgrep step names {missing}, which are not paths in this repository. "
        "Either a target was deleted, or a flag's value is being read as a target "
        f"because the flag is missing from {sorted(_SEMGREP_VALUE_FLAGS)}."
    )
    return targets


def _directories_holding_tracked_python(root: Path) -> set[str]:
    """Top-level directories holding tracked `.py` files, as git sees them.

    `git ls-files`, not a filesystem walk: the SAST gate's subject is the code this
    repository commits, and a walk would have to re-implement `.gitignore` to say the
    same thing -- it would report `.venv/` as a directory the scan must cover. A
    tracked `.py` at the repository root is reported as `.`, the target that would
    have to be named to scan it.
    """
    git = shutil.which("git")
    assert git is not None, "git is not on PATH, so this gate cannot enumerate tracked files"
    completed = subprocess.run(  # noqa: S603 - resolved git path, fixed argv, no shell
        [git, "-C", str(root), "ls-files", "-z", "--", "*.py"],
        capture_output=True,
        text=True,
        check=True,
    )
    tracked = [name for name in completed.stdout.split("\0") if name]
    assert tracked, "git lists no tracked .py files; the reader is broken, not the repository"
    return {name.split("/")[0] if "/" in name else "." for name in tracked}


def test_sast_scans_every_directory_that_holds_tracked_python() -> None:
    """The SAST gate's targets must cover the whole tree it is supposed to cover.

    `semgrep scan ... src tests` stopped one directory short. `scripts/` is under
    `[tool.mypy] strict = true` and holds `check_wheel.py`, which is a gate
    implementation `ci.yml` runs -- and it was outside the scan. Measured: an
    `os.system(sys.argv[1])` added to `scripts/check_wheel.py` was zero findings
    under `src tests` and one blocking finding under `scripts src tests`.

    Naming the directories one by one is fine; leaving one out is what was not
    noticed, so the list is derived from git rather than from memory. The next
    top-level directory of Python added to this repository fails here until it is
    named, instead of being scanned by nobody.
    """
    root = Path(__file__).parents[1]
    holding_python = _directories_holding_tracked_python(root)
    assert holding_python, "no directories of tracked Python found"
    targets = {target.rstrip("/") for target in _semgrep_targets(root)}
    # `.` as a target scans the whole tree, so it covers every subdirectory at once.
    unscanned = set() if "." in targets else holding_python - targets
    assert not unscanned, (
        f"these directories hold tracked Python that Semgrep never reads: {sorted(unscanned)}. "
        f"The scan targets are {sorted(targets)}."
    )


def test_sast_actually_scans_every_directory_it_claims_to_scan() -> None:
    """The SAST gate's stated scope must equal its real scope.

    Semgrep's built-in ignore list drops `tests/` wholesale, so
    `semgrep scan --config p/python src tests` scanned `src` only while the
    workflow named both. A repository `.semgrepignore` replaces that built-in
    list; if it is deleted or starts excluding a named target, the gate
    silently narrows again and nothing else notices.
    """
    root = Path(__file__).parents[1]
    ignore_file = root / ".semgrepignore"
    assert ignore_file.exists(), (
        "no .semgrepignore: Semgrep's built-in list will silently drop tests/ "
        f"from the scan of {_semgrep_targets(root)}"
    )
    patterns = [
        line.strip().rstrip("/")
        for line in ignore_file.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith(("#", ":"))
    ]
    excluded = [target for target in _semgrep_targets(root) if target.rstrip("/") in patterns]
    assert not excluded, f"ci.yml scans {excluded}, but .semgrepignore excludes them"


#: The identity question, as the workflow asks it. Matching a pinned SHA against the named
#: repository's own tag refs is the part that cannot be satisfied by a fork, because forks
#: share a repository's git objects but not its refs.
_PIN_RESOLUTION = "git/matching-refs/tags/"
_UNREADABLE_PINS = re.compile(r"^\s*UNREADABLE_PINS:\s*(?P<repositories>\S.*?)\s*$", re.M)

#: The only pinned repository the pin-identity step may skip. Private, owned by another
#: account, and unreadable by this workflow's repo-scoped GITHUB_TOKEN, so the API 404s on
#: a genuine pin; it is verified by hand at every bump instead. Each exemption is a pin
#: nothing automated checks, so the set is pinned down here rather than left to whatever
#: the workflow happens to say: adding one means editing this line, in a diff a reviewer
#: reads, instead of appending a word to an env var in ci.yml.
_EXEMPT_FROM_PIN_IDENTITY = frozenset({"ChelseaKR/portfolio-standards"})


def _pinned_repositories(root: Path) -> set[str]:
    """Every `owner/repo` whose commits this repository pins.

    A reusable-workflow reference carries a path after the repository name, so only the
    first two segments identify the repository the pin has to resolve against.
    """
    repositories = set()
    for workflow in workflow_files(root):
        for line in workflow.read_text(encoding="utf-8").splitlines():
            match = _PINNED_USES.match(line)
            if match is not None:
                repositories.add("/".join(match.group(1).split("/")[:2]))
    return repositories


def test_every_pinned_sha_is_resolved_against_the_repository_it_names() -> None:
    """A 40-hex pin is a format, not an identity.

    `test_ci_actions_are_digest_pinned` matches `@([0-9a-f]{40})` -- any 40 hex
    characters -- and zizmor's `impostor-commit`, the rule that would ask whether
    those characters name a commit in the repository the pin names, is disabled
    repo-wide in `.github/zizmor.yml`. So replacing `actions/checkout@<real sha>`
    with a SHA from an attacker's fork of checkout kept every gate green.

    Something has to ask. This asserts that ci.yml still does, and holds its
    exemption list to the one repository the token genuinely cannot read. Without
    that, the step's `UNREADABLE_PINS` env var would be a way to switch the gate
    off one action at a time, in a workflow edit, while the job kept reporting
    success -- appending `actions/checkout` to it is a one-word diff.
    """
    root = Path(__file__).parents[1]
    resolving = [
        workflow.name
        for workflow in workflow_files(root)
        if _PIN_RESOLUTION in workflow.read_text(encoding="utf-8")
    ]
    assert len(resolving) == 1, (
        "expected exactly one workflow to resolve pinned SHAs against the repository "
        f"they name, found {resolving}. Nothing else checks pin identity: the digest "
        "gate checks format and zizmor's impostor-commit rule is disabled repo-wide."
    )

    declarations = [
        match
        for workflow in workflow_files(root)
        for match in _UNREADABLE_PINS.findall(workflow.read_text(encoding="utf-8"))
    ]
    assert len(declarations) == 1, f"expected one UNREADABLE_PINS declaration, got {declarations}"
    skipped = set(declarations[0].split())
    pinned = _pinned_repositories(root)
    assert pinned, "no pinned repositories found; the reader is broken, not the workflows"
    assert skipped == set(_EXEMPT_FROM_PIN_IDENTITY), (
        f"the pin-identity step skips {sorted(skipped)}, but only "
        f"{sorted(_EXEMPT_FROM_PIN_IDENTITY)} is exempt. An exemption is a pin nothing "
        "automated verifies; adding one is a decision to record here, not a word to append "
        "to an env var."
    )
    assert skipped <= pinned, (
        f"{sorted(skipped - pinned)} is exempt from pin identity but nothing pins it. "
        "A stale exemption exempts nothing and only obscures the list."
    )
    assert pinned - skipped, (
        "every pinned repository is exempt, so the pin-identity step resolves nothing "
        "while still reporting success."
    )
