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
    assert "Public/package publication" in release
    assert "pypi-publish" not in release
    assert "uv publish" not in release
