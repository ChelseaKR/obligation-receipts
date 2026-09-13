"""The required ``secret-scan`` check must read every commit, not the one it was handed.

``secret-scan`` is one of the six jobs the ``protect-main`` ruleset names, so it is a
merge-blocking check. Until this change it was ``gitleaks/gitleaks-action``, which chooses
its scan range from the triggering event:

* ``push`` carrying several commits ->
  ``gitleaks detect --log-opts=--no-merges --first-parent BASE^..HEAD``
* ``push`` carrying exactly one commit -> ``gitleaks detect --log-opts=-1``, i.e. ONE commit
* ``pull_request`` -> that pull request's own commits
* ``schedule`` / ``workflow_dispatch`` -> no range argument at all, i.e. the whole history

Every merge into ``main`` in this repository is a squash merge, so every push to ``main``
carries one commit. And ``ci.yml`` triggers on ``push`` and ``pull_request`` only -- the two
events the action narrows -- so the only two lanes that would have read the whole history
do not exist here. The check therefore read 1 of ``main``'s 57 commits, and a credential
added in one commit and deleted in the next was invisible to it while the job reported
success.

``fetch-depth: 0`` did not prevent that and could not. It decides how much history
``actions/checkout`` puts on DISK; what the scanner reads is decided by how it is INVOKED.
A checkout deep enough to scan and an invocation that declines to scan it is precisely the
state this job was in. So the assertions below are about the invocation, and the
``fetch-depth: 0`` assertion is kept as the necessary precondition it actually is and
nothing more.

Measured on a throwaway clone of this repository, its remote removed, with the fix in hand:
a random real-shaped AWS key planted in one commit and removed in the next left
``gitleaks git . --log-opts=-1`` exiting 0 and ``gitleaks git .`` exiting 1, over the same
57-commit history, with the restored tree byte-identical to the baseline.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CI = ROOT / ".github" / "workflows" / "ci.yml"

#: Four conformance checks elsewhere in this portfolio passed because they matched a tool
#: name that appeared only inside a COMMENT. The comment above the scan step names both the
#: action that was removed and the flag that must not return -- it has to, because that is
#: what the comment is explaining -- so every assertion here reads the file with its
#: comments stripped and cannot be satisfied by prose.
_COMMENT = re.compile(r"(?m)^\s*#.*$|\s+#.*$")

#: The invocation that makes this a history scan: no ``--log-opts``, no range, so gitleaks
#: walks every commit reachable from HEAD regardless of which event started the run.
_HISTORY_WALK = "gitleaks git . --no-banner --redact --exit-code 1"


def _ci_code() -> str:
    """``ci.yml`` with every comment removed, which is the only form asserted against."""
    return _COMMENT.sub("", CI.read_text(encoding="utf-8"))


def test_the_reader_cannot_see_what_the_comments_say() -> None:
    """Prove the comment stripper strips before trusting anything it reports.

    Without this, every assertion below would be worth exactly as much as a regex nobody
    exercised -- and a stripper that silently stopped stripping would turn each of them
    into a check that passes on the explanation of the thing it forbids.
    """
    assert _COMMENT.sub("", "# gitleaks/gitleaks-action\n").strip() == ""
    assert _COMMENT.sub("", "    # --log-opts=-1\n").strip() == ""
    assert _COMMENT.sub("", "    fetch-depth: 0 # --log-opts\n").strip() == "fetch-depth: 0"
    assert "--log-opts" in CI.read_text(encoding="utf-8"), (
        "the comment explaining what was removed is gone, so this file is asserting "
        "against text that never mentioned the defect; restore the explanation"
    )


def test_the_scanner_is_not_handed_a_range() -> None:
    code = _ci_code()
    assert _HISTORY_WALK in code, (
        f"the secret scan no longer runs `{_HISTORY_WALK}`. Whatever replaces it must still "
        "walk every commit reachable from HEAD on every event, not a range chosen from the "
        "event that started the run."
    )
    assert "--log-opts" not in code, (
        "`--log-opts` scopes gitleaks to a commit range. A range chosen from the triggering "
        "event is how a required check came to read 1 of this repository's 57 commits."
    )


def test_the_event_driven_action_does_not_come_back() -> None:
    assert "gitleaks/gitleaks-action" not in _ci_code(), (
        "gitleaks/gitleaks-action picks its scan range from the event and degrades to "
        "`--log-opts=-1` on a single-commit push, which is every squash merge into `main`. "
        "`ci.yml` has no `schedule` and no `workflow_dispatch`, the only two events for "
        "which it would scan the whole history, so nothing else would make up the shortfall."
    )


def test_the_scan_is_not_scoped_by_the_event_that_started_the_run() -> None:
    """The scan step must not read `github.event_name` or a base/head SHA off the event.

    Stated as a property rather than as "the action is gone", because the defect is the
    range coming from the event, not the name of the thing that read it: a hand-written
    step that branched on `github.event_name` would reintroduce it exactly.
    """
    code = _ci_code()
    block = re.search(r"^  secret-scan:\n(?:(?:    .*)?\n)*?(?=^  \S|\Z)", code, re.M)
    assert block is not None, "the `secret-scan` job is gone from ci.yml, or was renamed"
    scoped = [
        needle
        for needle in ("github.event_name", "event.before", "event.after", "base.sha", "head.sha")
        if needle in block.group(0)
    ]
    assert not scoped, (
        f"the secret-scan job reads {scoped} from the triggering event. What is scanned must "
        "not depend on how the run was started; that dependency is the whole defect."
    )


def test_checkout_still_fetches_the_history_the_scan_walks() -> None:
    """Necessary, not sufficient: without it there is nothing on disk to walk.

    This assertion is deliberately not evidence that the scan reads history. It was true
    for the whole life of the defect. It is kept because removing it would leave
    `gitleaks git .` walking the single commit `actions/checkout` fetched by default --
    which is the same failure arriving from the other direction.
    """
    code = _ci_code()
    block = re.search(r"^  secret-scan:\n(?:(?:    .*)?\n)*?(?=^  \S|\Z)", code, re.M)
    assert block is not None, "the `secret-scan` job is gone from ci.yml, or was renamed"
    assert re.search(r"^\s*fetch-depth:\s*0\s*$", block.group(0), re.M), (
        "`fetch-depth: 0` is gone from the secret-scan checkout, so `gitleaks git .` would "
        "walk only the commit actions/checkout fetched. This is the precondition for a "
        "history scan; the invocation is what makes it one."
    )


def test_the_pinned_binary_is_checksum_verified() -> None:
    """A downloaded scanner is a supply-chain input like any other.

    The action this replaced was digest-pinned, and `tests/test_supply_chain.py` proved it.
    A tarball fetched with `curl` is outside that gate entirely, so the published checksum
    has to be checked here or by nothing.
    """
    code = _ci_code()
    assert "gitleaks_checksums.txt" in code and "sha256sum --check --strict" in code, (
        "the gitleaks binary is downloaded without verifying its published checksum"
    )
    assert "set -euo pipefail" in code, (
        "without `pipefail` the checksum lives in a pipeline whose failure the shell "
        "discards, and the step would carry on to run an unverified binary"
    )


def test_the_workflow_and_the_pre_commit_hook_run_the_same_gitleaks() -> None:
    """One version, so the local hook and the required check cannot disagree on a finding.

    `.pre-commit-config.yaml` pins the hook by tag; the workflow pins the binary by version
    in its download URL. They are two files, so nothing but this holds them together.
    """
    workflow = re.search(r"^\s*GL=(?P<version>\d+\.\d+\.\d+)\s*$", _ci_code(), re.M)
    assert workflow is not None, "the secret-scan step no longer pins a gitleaks version"
    hook = re.search(
        r"gitleaks\n\s*rev:\s*v(?P<version>\d+\.\d+\.\d+)",
        (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8"),
    )
    assert hook is not None, "the gitleaks pre-commit hook no longer pins a version"
    assert workflow.group("version") == hook.group("version"), (
        f"ci.yml runs gitleaks {workflow.group('version')} and the pre-commit hook runs "
        f"{hook.group('version')}; a local pass would not mean the required check passes"
    )
