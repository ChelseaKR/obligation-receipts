"""Freezing evidence at collection time, and refusing anything that moved.

Issue 58. Each test maps to one of that issue's "Done when" bullets, or to the
one distinction the whole feature rests on: the lock changes what is *refused*,
never what is *judged*. An artifact that was never collected is still `missing`
after this change, because `missing` is a finding about the contract and a
refusal is a statement about the tool.

The other property under test is that a read which could not happen never
becomes an observation. `freeze-evidence` records `present` with a digest or
`absent` with none; anything else -- a path that escapes the root, a file over
the artifact cap, a non-regular file -- refuses to write a lock at all. Writing
those down as `absent` would freeze a failed read as a measured fact, and every
later comparison would be against something nobody measured.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from obligation_receipts.cli import main
from obligation_receipts.exit_codes import INPUT_ERROR, OK
from obligation_receipts.lock import (
    LOCK_SCHEMA_VERSION,
    MAX_ARTIFACT_BYTES,
    EvidenceLockError,
    build_evidence_lock,
    enforce_evidence_lock,
    load_evidence_lock,
    lock_digest,
    write_evidence_lock,
)
from obligation_receipts.manifest import load_manifest
from obligation_receipts.receipt import ReceiptError, build_receipt, load_receipt, verify_receipt

_VENDOR_ATTESTATION = "external/acr-attestation.json"
_AXE_SUMMARY = "automated/axe-summary.json"


def _lock(example: Path) -> dict[str, Any]:
    manifest = load_manifest(example / "obligations.toml")
    return dict(build_evidence_lock(manifest, example / "evidence"))


def _rows(lock: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row["evidence_id"]: row for row in lock["artifacts"]}


def _cli_evaluate(example: Path, out: Path, lock: Path | None) -> int:
    argv = [
        "evaluate",
        str(example / "obligations.toml"),
        "--evidence-root",
        str(example / "evidence"),
        "--out",
        str(out),
        "--generated-at",
        "2026-01-01T00:00:00+00:00",
    ]
    if lock is not None:
        argv += ["--lock", str(lock)]
    return main(argv)


# --- "Done when": lock, then an unchanged run, and the receipt names the lock ---


def test_freezing_then_evaluating_unchanged_evidence_records_the_lock_digest(
    copied_example: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    lock_path = tmp_path / "evidence.lock.json"
    receipt_path = tmp_path / "receipt.json"

    assert (
        main(
            [
                "freeze-evidence",
                str(copied_example / "obligations.toml"),
                "--evidence-root",
                str(copied_example / "evidence"),
                "--out",
                str(lock_path),
            ]
        )
        == OK
    )
    summary = json.loads(capsys.readouterr().out)
    assert summary["artifacts"] == 3
    assert summary["present"] == 3

    assert _cli_evaluate(copied_example, receipt_path, lock_path) == OK
    receipt = load_receipt(receipt_path)
    envelope = receipt["envelope"]
    assert isinstance(envelope, dict)
    assert envelope["evidence_lock_sha256"] == summary["evidence_lock_sha256"]
    assert envelope["evidence_lock_sha256"] == lock_digest(load_evidence_lock(lock_path))


def test_freeze_evidence_judges_nothing(copied_example: Path, tmp_path: Path) -> None:
    """Exit OK over evidence an evaluation would call incomplete.

    The command reads bytes; what they mean is a separate question asked later.
    Mapping this onto an evaluation exit code would report a finding this
    command did not make.
    """

    (copied_example / "evidence" / _VENDOR_ATTESTATION).unlink()
    lock_path = tmp_path / "evidence.lock.json"

    assert (
        main(
            [
                "freeze-evidence",
                str(copied_example / "obligations.toml"),
                "--evidence-root",
                str(copied_example / "evidence"),
                "--out",
                str(lock_path),
            ]
        )
        == OK
    )
    assert _rows(dict(load_evidence_lock(lock_path)))["a3-vendor-attestation"]["status"] == "absent"


# --- "Done when": one changed byte refuses, naming the evidence id ---------


def test_one_changed_byte_refuses_and_writes_no_receipt(
    copied_example: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    lock_path = tmp_path / "evidence.lock.json"
    write_evidence_lock(lock_path, _lock(copied_example))
    artifact = copied_example / "evidence" / _AXE_SUMMARY
    artifact.write_text(artifact.read_text(encoding="utf-8") + " ", encoding="utf-8")
    receipt_path = tmp_path / "receipt.json"

    assert _cli_evaluate(copied_example, receipt_path, lock_path) == INPUT_ERROR
    assert not receipt_path.exists(), "a refused evaluation must leave no receipt"
    assert "a1-axe-summary" in capsys.readouterr().err


def test_the_same_evidence_without_the_lock_still_evaluates(
    copied_example: Path, tmp_path: Path
) -> None:
    """The refusal comes from the lock, not from the evidence.

    Without this, the test above would pass against an `evaluate` that had
    simply broken on the modified artifact, and would say nothing about locks.
    """

    artifact = copied_example / "evidence" / _AXE_SUMMARY
    artifact.write_text(artifact.read_text(encoding="utf-8") + " ", encoding="utf-8")
    receipt_path = tmp_path / "receipt.json"

    assert _cli_evaluate(copied_example, receipt_path, None) == OK
    assert receipt_path.exists()
    envelope = load_receipt(receipt_path)["envelope"]
    assert isinstance(envelope, dict)
    assert "evidence_lock_sha256" not in envelope


# --- "Done when": a lock built against a different manifest is refused -----


def test_a_lock_from_a_different_manifest_is_refused(
    copied_example: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    lock = _lock(copied_example)
    lock["manifest_sha256"] = "b" * 64
    lock_path = tmp_path / "evidence.lock.json"
    write_evidence_lock(lock_path, lock)

    assert _cli_evaluate(copied_example, tmp_path / "receipt.json", lock_path) == INPUT_ERROR
    assert "different manifest" in capsys.readouterr().err


def test_a_lock_from_a_different_approved_source_is_refused(copied_example: Path) -> None:
    """The manifest digest and the source digest are two different bindings.

    A manifest can be re-normalised to the same bytes over a different approved
    source, so checking only `manifest_sha256` would accept a lock taken against
    other evidence of authority.
    """

    manifest = load_manifest(copied_example / "obligations.toml")
    lock = _lock(copied_example)
    lock["source_sha256"] = "c" * 64

    with pytest.raises(EvidenceLockError, match="different approved source"):
        enforce_evidence_lock(manifest, copied_example / "evidence", lock)


# --- "Done when": absent then present is refused, not evaluated ------------


def test_an_artifact_absent_at_lock_time_and_present_later_is_refused(
    copied_example: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The bullet this whole feature exists for.

    Nothing collected this file. Evaluating it would put an artifact into a
    receipt that the collection step never saw, which is exactly the silent
    substitution the lock is meant to make impossible.
    """

    artifact = copied_example / "evidence" / _VENDOR_ATTESTATION
    saved = artifact.read_text(encoding="utf-8")
    artifact.unlink()
    lock_path = tmp_path / "evidence.lock.json"
    write_evidence_lock(lock_path, _lock(copied_example))
    artifact.write_text(saved, encoding="utf-8")

    receipt_path = tmp_path / "receipt.json"
    assert _cli_evaluate(copied_example, receipt_path, lock_path) == INPUT_ERROR
    assert not receipt_path.exists()
    error = capsys.readouterr().err
    assert "a3-vendor-attestation" in error
    assert "never collected" in error


def test_an_artifact_absent_at_both_moments_is_still_only_missing(
    copied_example: Path, tmp_path: Path
) -> None:
    """The lock changes what is refused, not what is judged.

    Absence is a finding the result algebra already models. If this returned
    INPUT_ERROR the feature would have converted "the vendor never sent the
    attestation" into "the tool could not run", which are different facts about
    a contract and the exit-code contract keeps them apart on purpose.
    """

    (copied_example / "evidence" / _VENDOR_ATTESTATION).unlink()
    lock_path = tmp_path / "evidence.lock.json"
    write_evidence_lock(lock_path, _lock(copied_example))
    receipt_path = tmp_path / "receipt.json"

    code = _cli_evaluate(copied_example, receipt_path, lock_path)

    assert code != INPUT_ERROR
    assert receipt_path.exists()
    payload = load_receipt(receipt_path)["payload"]
    assert isinstance(payload, dict)
    assert payload["overall_status"] in {"incomplete", "review_required", "accepted_with_findings"}


def test_an_artifact_frozen_and_then_deleted_is_refused(copied_example: Path) -> None:
    manifest = load_manifest(copied_example / "obligations.toml")
    lock = _lock(copied_example)
    (copied_example / "evidence" / _VENDOR_ATTESTATION).unlink()

    with pytest.raises(EvidenceLockError, match="frozen and is gone"):
        enforce_evidence_lock(manifest, copied_example / "evidence", lock)


# --- a read that could not happen is never frozen as an observation --------


def test_an_artifact_over_the_cap_refuses_the_freeze_rather_than_freezing_absent(
    copied_example: Path, tmp_path: Path
) -> None:
    """The endemic defect, in the shape this feature could take.

    An oversized file is *there*. Recording it as `absent` would freeze a failed
    read as a measured fact, and a later `evaluate --lock` would then compare
    real evidence against a claim that nothing was collected.
    """

    artifact = copied_example / "evidence" / _AXE_SUMMARY
    artifact.write_bytes(b"x" * (MAX_ARTIFACT_BYTES + 1))
    manifest = load_manifest(copied_example / "obligations.toml")

    with pytest.raises(EvidenceLockError, match="a1-axe-summary"):
        build_evidence_lock(manifest, copied_example / "evidence")

    assert (
        main(
            [
                "freeze-evidence",
                str(copied_example / "obligations.toml"),
                "--evidence-root",
                str(copied_example / "evidence"),
                "--out",
                str(tmp_path / "evidence.lock.json"),
            ]
        )
        == INPUT_ERROR
    )
    assert not (tmp_path / "evidence.lock.json").exists()


def test_an_artifact_over_the_cap_at_evaluate_time_refuses_too(copied_example: Path) -> None:
    manifest = load_manifest(copied_example / "obligations.toml")
    lock = _lock(copied_example)
    (copied_example / "evidence" / _AXE_SUMMARY).write_bytes(b"x" * (MAX_ARTIFACT_BYTES + 1))

    with pytest.raises(EvidenceLockError, match="cannot be digested"):
        enforce_evidence_lock(manifest, copied_example / "evidence", lock)


# --- the lock document is closed, versioned, and reproducible --------------


def test_the_lock_is_byte_reproducible_from_the_same_evidence(copied_example: Path) -> None:
    from obligation_receipts.canonical import canonical_json_bytes

    first = canonical_json_bytes(_lock(copied_example))
    second = canonical_json_bytes(_lock(copied_example))

    assert first == second


def test_lock_rows_are_ordered_by_evidence_id_not_by_manifest_order(
    copied_example: Path,
) -> None:
    """Determinism has to survive a reordered manifest, or the digest is noise."""

    identifiers = [row["evidence_id"] for row in _lock(copied_example)["artifacts"]]

    assert identifiers == sorted(identifiers)


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (lambda lock: lock.pop("source_sha256"), "closed schema"),
        (lambda lock: lock.update(extra=1), "closed schema"),
        (
            lambda lock: lock.update(schema_version="obligation-receipts/receipt/v0.1"),
            "unsupported",
        ),
        (lambda lock: lock.update(artifacts={}), "must be a list"),
        (lambda lock: lock["artifacts"][0].pop("sha256"), "closed schema"),
        (lambda lock: lock["artifacts"][0].update(status="maybe"), "unsupported status"),
        (lambda lock: lock["artifacts"][0].update(sha256=None), "present with no digest"),
        (lambda lock: lock["artifacts"][0].update(sha256="not a digest"), "present with no digest"),
        (lambda lock: lock["artifacts"][0].update(evidence_id=""), "non-empty string"),
        (lambda lock: lock["artifacts"][0].update(path=7), "has no path"),
        (
            lambda lock: lock["artifacts"].append(dict(lock["artifacts"][0])),
            "more than once",
        ),
        (
            lambda lock: lock["artifacts"][0].update(status="absent"),
            "absent but carries a digest",
        ),
    ],
)
def test_a_malformed_lock_is_refused_rather_than_partially_read(
    copied_example: Path, tmp_path: Path, mutate: Any, match: str
) -> None:
    """The reader is the path that matters: a lock arrives from someone else.

    Written straight to disk with `json.dumps`, deliberately bypassing
    `write_evidence_lock`, so this exercises `load_evidence_lock`'s own
    validation rather than re-testing the writer's. A lock that only the writer
    checked would be a lock anyone could hand you.
    """

    lock = _lock(copied_example)
    mutate(lock)
    path = tmp_path / "evidence.lock.json"
    path.write_text(json.dumps(lock), encoding="utf-8")

    with pytest.raises(EvidenceLockError, match=match):
        load_evidence_lock(path)

    # ...and the writer refuses the same document, so a malformed lock cannot
    # be produced by this tool either.
    with pytest.raises(EvidenceLockError, match=match):
        write_evidence_lock(tmp_path / "written.lock.json", lock)
    assert not (tmp_path / "written.lock.json").exists()


def test_a_lock_naming_an_artifact_the_manifest_does_not_declare_is_refused(
    copied_example: Path,
) -> None:
    manifest = load_manifest(copied_example / "obligations.toml")
    lock = _lock(copied_example)
    lock["artifacts"].append(
        {"evidence_id": "z-unknown", "path": "nowhere.json", "status": "absent", "sha256": None}
    )

    with pytest.raises(EvidenceLockError, match="z-unknown"):
        enforce_evidence_lock(manifest, copied_example / "evidence", lock)


def test_a_declared_artifact_missing_from_the_lock_is_refused(copied_example: Path) -> None:
    manifest = load_manifest(copied_example / "obligations.toml")
    lock = _lock(copied_example)
    lock["artifacts"] = [row for row in lock["artifacts"] if row["evidence_id"] != "a1-axe-summary"]

    with pytest.raises(EvidenceLockError, match="absent from the lock"):
        enforce_evidence_lock(manifest, copied_example / "evidence", lock)


def test_a_lock_whose_row_points_at_a_different_path_is_refused(copied_example: Path) -> None:
    manifest = load_manifest(copied_example / "obligations.toml")
    lock = _lock(copied_example)
    _rows(lock)["a1-axe-summary"]["path"] = "automated/somewhere-else.json"

    with pytest.raises(EvidenceLockError, match="was frozen at"):
        enforce_evidence_lock(manifest, copied_example / "evidence", lock)


@pytest.mark.parametrize(
    ("contents", "match"),
    [
        ("[]", "must be a JSON object"),
        ("{{{", "not strict JSON"),
    ],
)
def test_a_lock_file_that_is_not_a_lock_is_refused(
    tmp_path: Path, contents: str, match: str
) -> None:
    path = tmp_path / "evidence.lock.json"
    path.write_text(contents, encoding="utf-8")

    with pytest.raises(EvidenceLockError, match=match):
        load_evidence_lock(path)


def test_a_missing_lock_file_is_refused(tmp_path: Path) -> None:
    with pytest.raises((EvidenceLockError, FileNotFoundError)):
        load_evidence_lock(tmp_path / "nope.json")


def test_a_lock_over_the_size_limit_is_refused(copied_example: Path, tmp_path: Path) -> None:
    lock = _lock(copied_example)
    lock["artifacts"] = [
        {
            "evidence_id": f"pad-{index}",
            "path": "x" * 4096,
            "status": "absent",
            "sha256": None,
        }
        for index in range(600)
    ]

    with pytest.raises(EvidenceLockError, match="exceeds the 2 MiB limit"):
        write_evidence_lock(tmp_path / "evidence.lock.json", lock)


# --- the receipt envelope stays closed, and stays backward compatible ------


def test_a_receipt_without_a_lock_carries_no_lock_field(copied_example: Path) -> None:
    """Every receipt written before locks existed still verifies unchanged.

    The optional member is what makes that true; a required one would have
    invalidated every committed fixture and every receipt already in the world.
    """

    from obligation_receipts.evaluator import evaluate_manifest

    manifest = load_manifest(copied_example / "obligations.toml")
    evaluation = evaluate_manifest(manifest, copied_example / "evidence")
    receipt = build_receipt(evaluation, generated_at="2026-01-01T00:00:00+00:00")

    envelope = receipt["envelope"]
    assert isinstance(envelope, dict)
    assert set(envelope) == {"claimed_generated_at", "signature_status", "trusted_time"}
    assert verify_receipt(receipt) == receipt["payload_sha256"]


def test_the_lock_field_does_not_change_the_payload_digest(copied_example: Path) -> None:
    """The envelope is not the determinism contract, and must not become one.

    Every committed fixture pins `payload_sha256`. Recording the lock in the
    payload would have moved all of them and made a locked evaluation
    non-comparable with an unlocked one over the same evidence.
    """

    from obligation_receipts.evaluator import evaluate_manifest

    manifest = load_manifest(copied_example / "obligations.toml")
    evaluation = evaluate_manifest(manifest, copied_example / "evidence")
    plain = build_receipt(evaluation, generated_at="2026-01-01T00:00:00+00:00")
    locked = build_receipt(
        evaluation, generated_at="2026-01-01T00:00:00+00:00", evidence_lock_sha256="d" * 64
    )

    assert locked["payload_sha256"] == plain["payload_sha256"]
    assert locked["payload"] == plain["payload"]


def test_the_envelope_is_still_closed_against_an_unknown_key(copied_example: Path) -> None:
    """Optional does not mean open."""

    from obligation_receipts.evaluator import evaluate_manifest

    manifest = load_manifest(copied_example / "obligations.toml")
    evaluation = evaluate_manifest(manifest, copied_example / "evidence")
    receipt = build_receipt(evaluation, generated_at="2026-01-01T00:00:00+00:00")
    envelope = receipt["envelope"]
    assert isinstance(envelope, dict)
    envelope["something_else"] = "x"

    with pytest.raises(ReceiptError, match="closed schema"):
        verify_receipt(receipt)


def test_a_lock_digest_that_is_not_a_digest_is_refused(copied_example: Path) -> None:
    from obligation_receipts.evaluator import evaluate_manifest

    manifest = load_manifest(copied_example / "obligations.toml")
    evaluation = evaluate_manifest(manifest, copied_example / "evidence")
    receipt = build_receipt(
        evaluation, generated_at="2026-01-01T00:00:00+00:00", evidence_lock_sha256="not-a-digest"
    )

    with pytest.raises(ReceiptError, match="lowercase SHA-256 digest"):
        verify_receipt(receipt)


def test_the_lock_schema_version_is_its_own(copied_example: Path) -> None:
    assert LOCK_SCHEMA_VERSION == "obligation-receipts/evidence-lock/v0.1"
    assert _lock(copied_example)["schema_version"] == LOCK_SCHEMA_VERSION


# --- the two refusals reachable only through the Python API ----------------


def test_a_manifest_declaring_one_evidence_id_twice_is_refused(copied_example: Path) -> None:
    """`manifest.py` already refuses this in a *file*; the API takes a `Manifest`.

    `build_evidence_lock` is given the in-memory type, not a path, so a caller
    constructing one directly can hand it a duplicate. A lock indexed by
    evidence id would silently keep whichever row came last, and the row it
    dropped would then be enforced against nothing.
    """

    from obligation_receipts.models import (
        Classification,
        Contract,
        Criticality,
        EvidenceKind,
        EvidenceSpec,
        Manifest,
        Obligation,
    )

    def obligation(obligation_id: str) -> Obligation:
        return Obligation(
            obligation_id=obligation_id,
            clause_ref="1.1",
            text="the same evidence id twice",
            classification=Classification.AUTOMATED,
            criticality=Criticality.MUST,
            owner="acceptance",
            reason=None,
            evidence=(
                EvidenceSpec(
                    evidence_id="shared-id",
                    kind=EvidenceKind.JSON_ASSERTION,
                    path=_AXE_SUMMARY,
                    pointer="/critical",
                    operator="eq",
                    expected=0,
                ),
            ),
        )

    manifest = Manifest(
        contract=Contract(
            contract_id="c",
            title="t",
            version="1.0",
            authority="a",
            effective_date="2026-01-01",
            source_path="source/contract.md",
            source_sha256="e" * 64,
        ),
        obligations=(obligation("o1"), obligation("o2")),
        manifest_path="obligations.toml",
        manifest_sha256="f" * 64,
    )

    with pytest.raises(EvidenceLockError, match="declared more than once"):
        build_evidence_lock(manifest, copied_example / "evidence")


def test_a_lock_file_over_the_read_limit_is_refused_rather_than_truncated(
    tmp_path: Path,
) -> None:
    """A truncated read of a lock would compare against a fragment of one."""

    path = tmp_path / "evidence.lock.json"
    path.write_bytes(b"x" * (2 * 1024 * 1024 + 1))

    with pytest.raises(EvidenceLockError, match="cannot be read safely"):
        load_evidence_lock(path)
