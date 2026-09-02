import re
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


def test_ci_actions_are_digest_pinned_and_release_does_not_publish() -> None:
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
    release = (root / ".github/workflows/release.yml").read_text(encoding="utf-8")
    assert "name: release-candidate" in release
    assert "contents: write" not in release
    assert "pypa/gh-action-pypi-publish" not in release
    assert "gh release create" not in release
    assert "pypi-publish" not in release
    assert "uv publish" not in release


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


def _semgrep_targets(root: Path) -> list[str]:
    """The paths `.github/workflows/ci.yml` tells Semgrep to scan."""
    ci = (root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    match = _SEMGREP_COMMAND.search(ci)
    assert match is not None, "no `semgrep scan` step found in ci.yml"
    words = match.group("flags").split()
    targets = []
    skip_next = False
    for word in words:
        if skip_next:
            skip_next = False
            continue
        if word.startswith("--"):
            skip_next = word in {"--config"}
            continue
        targets.append(word)
    assert targets, "the semgrep step names no scan targets"
    return targets


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
