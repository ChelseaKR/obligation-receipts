import re
from pathlib import Path


def test_ci_actions_are_digest_pinned_and_release_does_not_publish() -> None:
    root = Path(__file__).parents[1]
    workflows = sorted((root / ".github/workflows").glob("*.yml"))
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
    for workflow in sorted((root / ".github/workflows").glob("*.yml")):
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
