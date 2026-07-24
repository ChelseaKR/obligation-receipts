import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

import obligation_receipts.evaluator as evaluator_module
from obligation_receipts.canonical import canonical_json_bytes, sha256_bytes
from obligation_receipts.evaluator import evaluate_manifest
from obligation_receipts.manifest import load_manifest
from obligation_receipts.models import JsonValue
from obligation_receipts.plan import EvidencePlanError, load_evidence_plan
from obligation_receipts.receipt import ReceiptError, load_receipt, verify_receipt
from obligation_receipts.single_check import (
    EvidenceCheckError,
    check_declared_evidence,
    evidence_check_exit_code,
    verify_evidence_check,
)


def _payload(document: dict[str, JsonValue]) -> dict[str, JsonValue]:
    payload = document["payload"]
    assert isinstance(payload, dict)
    return payload


def _evidence(document: dict[str, JsonValue]) -> dict[str, JsonValue]:
    evidence = _payload(document)["evidence"]
    assert isinstance(evidence, dict)
    return evidence


def _rehash(document: dict[str, JsonValue]) -> None:
    document["payload_sha256"] = sha256_bytes(canonical_json_bytes(document["payload"]))


def test_single_automated_pass_is_closed_bound_and_content_free(
    example_manifest: Path,
) -> None:
    manifest = load_manifest(example_manifest)
    document = check_declared_evidence(
        manifest,
        "a1-axe-summary",
        example_manifest.parent / "evidence",
    )
    assert verify_evidence_check(document) == document["payload_sha256"]
    assert evidence_check_exit_code(document) == 0
    payload = _payload(document)
    assert payload["decision_scope"] == "single_declared_evidence_check_only"
    assert payload["contract_id"] == manifest.contract.contract_id
    assert payload["contract_version"] == manifest.contract.version
    assert payload["source_sha256"] == manifest.contract.source_sha256
    assert payload["manifest_sha256"] == manifest.manifest_sha256
    assert payload["declared_evidence_count"] == 1
    assert payload["other_evidence_not_checked_count"] == 0
    assert payload["obligation_evaluation_complete"] is False
    assert payload["document_signature_status"] == "not_signed"
    assert payload["obligation"] == {
        "classification": "automated",
        "criticality": "must",
        "id": "a1-zero-critical-violations",
    }
    assert _evidence(document) == {
        "artifact_sha256": sha256_bytes(
            (example_manifest.parent / "evidence/automated/axe-summary.json").read_bytes()
        ),
        "id": "a1-axe-summary",
        "kind": "json_assertion",
        "status": "pass",
    }
    assert payload["limitations"] == {
        "acceptance_decision_made": False,
        "artifact_digest_authenticated": False,
        "artifact_digest_is_content_identifier_only": True,
        "artifact_digest_may_be_sensitive": True,
        "completeness_assessed": False,
        "evidence_sufficiency_assessed": False,
        "legal_interpretation_performed": False,
        "other_evidence_checked": False,
    }
    encoded = canonical_json_bytes(document)
    for forbidden in (
        b"automated/axe-summary.json",
        b"/summary/critical_violations",
        b"critical_violations",
        b"The delivered service must",
        b'"overall_status"',
        b'"detail"',
        b'"path"',
        b'"pointer"',
        b'"expected"',
        b'"overall_status"',
        b'"obligation_status"',
    ):
        assert forbidden not in encoded


def test_unrelated_artifacts_are_never_required_or_read(copied_example: Path) -> None:
    manifest = load_manifest(copied_example / "obligations.toml")
    selected = copied_example / "evidence/automated/axe-summary.json"
    for artifact in (copied_example / "evidence").rglob("*.json"):
        if artifact != selected:
            artifact.write_bytes(b"\xff")
    document = check_declared_evidence(
        manifest,
        "a1-axe-summary",
        copied_example / "evidence",
    )
    assert _evidence(document)["status"] == "pass"
    for artifact in (copied_example / "evidence").rglob("*.json"):
        if artifact != selected:
            artifact.unlink()
    assert (
        _evidence(
            check_declared_evidence(
                manifest,
                "a1-axe-summary",
                copied_example / "evidence",
            )
        )["status"]
        == "pass"
    )


def test_unknown_reads_zero_and_missing_selected_reads_once(
    copied_example: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = load_manifest(copied_example / "obligations.toml")
    calls: list[str] = []
    original = evaluator_module._read_json_artifact

    def tracked(root: Path, relative_path: str) -> tuple[bytes, str]:
        calls.append(relative_path)
        return original(root, relative_path)

    monkeypatch.setattr(evaluator_module, "_read_json_artifact", tracked)
    with pytest.raises(EvidenceCheckError, match="exactly one"):
        check_declared_evidence(manifest, "unknown", copied_example / "evidence")
    assert calls == []

    (copied_example / "evidence/automated/axe-summary.json").unlink()
    result = check_declared_evidence(
        manifest,
        "a1-axe-summary",
        copied_example / "evidence",
    )
    assert _evidence(result)["status"] == "missing"
    assert calls == ["automated/axe-summary.json"]


def test_selected_automated_fail_missing_and_malformed_remain_distinct(
    copied_example: Path,
) -> None:
    manifest = load_manifest(copied_example / "obligations.toml")
    selected = copied_example / "evidence/automated/axe-summary.json"
    selected.write_text('{"summary":{"critical_violations":1}}', encoding="utf-8")
    failed = check_declared_evidence(manifest, "a1-axe-summary", copied_example / "evidence")
    assert _evidence(failed)["status"] == "fail"
    assert _evidence(failed)["artifact_sha256"] is not None
    assert evidence_check_exit_code(failed) == 1

    selected.write_text("{", encoding="utf-8")
    malformed = check_declared_evidence(
        manifest,
        "a1-axe-summary",
        copied_example / "evidence",
    )
    assert _evidence(malformed) == {
        "artifact_sha256": sha256_bytes(b"{"),
        "id": "a1-axe-summary",
        "kind": "json_assertion",
        "status": "missing",
    }
    assert evidence_check_exit_code(malformed) == 3

    selected.unlink()
    missing = check_declared_evidence(manifest, "a1-axe-summary", copied_example / "evidence")
    assert _evidence(missing)["status"] == "missing"
    assert evidence_check_exit_code(missing) == 3


def test_attestation_check_preserves_exact_manifest_binding(copied_example: Path) -> None:
    manifest = load_manifest(copied_example / "obligations.toml")
    evidence_root = copied_example / "evidence"
    passed = check_declared_evidence(manifest, "a2-review-attestation", evidence_root)
    assert _evidence(passed)["status"] == "pass"
    assert evidence_check_exit_code(passed) == 0

    path = evidence_root / "manual/keyboard-review.json"
    raw = path.read_text(encoding="utf-8").replace(
        manifest.manifest_sha256,
        "0" * 64,
    )
    path.write_text(raw, encoding="utf-8")
    unbound = check_declared_evidence(manifest, "a2-review-attestation", evidence_root)
    assert _evidence(unbound)["status"] == "review_required"
    assert _evidence(unbound)["artifact_sha256"] == sha256_bytes(path.read_bytes())
    assert evidence_check_exit_code(unbound) == 4

    path.unlink()
    absent = check_declared_evidence(manifest, "a2-review-attestation", evidence_root)
    assert _evidence(absent)["status"] == "review_required"
    assert _evidence(absent)["artifact_sha256"] is None
    assert evidence_check_exit_code(absent) == 4


def test_malformed_observed_attestation_retains_its_content_digest(
    copied_example: Path,
) -> None:
    manifest = load_manifest(copied_example / "obligations.toml")
    evidence_root = copied_example / "evidence"
    path = evidence_root / "manual/keyboard-review.json"
    malformed = b'{"status":'
    path.write_bytes(malformed)
    document = check_declared_evidence(
        manifest,
        "a2-review-attestation",
        evidence_root,
    )
    assert _evidence(document)["status"] == "review_required"
    assert _evidence(document)["artifact_sha256"] == sha256_bytes(malformed)
    assert evidence_check_exit_code(document) == 4


def test_single_check_matches_full_evaluator_for_all_declared_kinds(
    copied_example: Path,
) -> None:
    manifest = load_manifest(copied_example / "obligations.toml")
    evidence_root = copied_example / "evidence"

    def full_statuses() -> dict[str, str]:
        evaluation = evaluate_manifest(manifest, evidence_root)
        return {
            evidence.evidence_id: evidence.status.value
            for obligation in evaluation.results
            for evidence in obligation.evidence
        }

    for evidence_id in (
        "a1-axe-summary",
        "a2-review-attestation",
        "a3-vendor-attestation",
    ):
        assert (
            _evidence(check_declared_evidence(manifest, evidence_id, evidence_root))["status"]
            == full_statuses()[evidence_id]
        )

    for path in (
        evidence_root / "manual/keyboard-review.json",
        evidence_root / "external/acr-attestation.json",
    ):
        value = path.read_text(encoding="utf-8").replace('"status": "pass"', '"status": "fail"')
        path.write_text(value, encoding="utf-8")
    for evidence_id in ("a2-review-attestation", "a3-vendor-attestation"):
        assert (
            _evidence(check_declared_evidence(manifest, evidence_id, evidence_root))["status"]
            == full_statuses()[evidence_id]
            == "fail"
        )

    for path in (
        evidence_root / "manual/keyboard-review.json",
        evidence_root / "external/acr-attestation.json",
    ):
        value = (
            path.read_text(encoding="utf-8")
            .replace('"status": "fail"', '"status": "pass"')
            .replace(manifest.manifest_sha256, "0" * 64)
        )
        path.write_text(value, encoding="utf-8")
    for evidence_id in ("a2-review-attestation", "a3-vendor-attestation"):
        assert (
            _evidence(check_declared_evidence(manifest, evidence_id, evidence_root))["status"]
            == full_statuses()[evidence_id]
            == "review_required"
        )

    (evidence_root / "automated/axe-summary.json").write_text("{", encoding="utf-8")
    for path in (
        evidence_root / "manual/keyboard-review.json",
        evidence_root / "external/acr-attestation.json",
    ):
        path.unlink()
    expected = {
        "a1-axe-summary": "missing",
        "a2-review-attestation": "review_required",
        "a3-vendor-attestation": "review_required",
    }
    statuses = full_statuses()
    for evidence_id, expected_status in expected.items():
        assert (
            _evidence(check_declared_evidence(manifest, evidence_id, evidence_root))["status"]
            == statuses[evidence_id]
            == expected_status
        )


@pytest.mark.parametrize("unknown_id", ["does-not-exist", "a4-intuitive"])
def test_unknown_and_unverifiable_ids_fail_closed(
    example_manifest: Path,
    unknown_id: str,
) -> None:
    with pytest.raises(EvidenceCheckError, match="exactly one"):
        check_declared_evidence(
            load_manifest(example_manifest),
            unknown_id,
            example_manifest.parent / "evidence",
        )


def test_defensive_duplicate_evidence_lookup_fails_closed(example_manifest: Path) -> None:
    manifest = load_manifest(example_manifest)
    first, second, *remaining = manifest.obligations
    duplicate = first.evidence[0]
    duplicate_manifest = replace(
        manifest,
        obligations=(
            first,
            replace(second, evidence=(*second.evidence, duplicate)),
            *remaining,
        ),
    )
    with pytest.raises(EvidenceCheckError, match="exactly one"):
        check_declared_evidence(
            duplicate_manifest,
            duplicate.evidence_id,
            example_manifest.parent / "evidence",
        )


def test_multi_evidence_obligation_remains_explicitly_incomplete(
    example_manifest: Path,
) -> None:
    manifest = load_manifest(example_manifest)
    first, *remaining = manifest.obligations
    second_spec = replace(first.evidence[0], evidence_id="second-declared-evidence")
    multi_manifest = replace(
        manifest,
        obligations=(replace(first, evidence=(*first.evidence, second_spec)), *remaining),
    )
    document = check_declared_evidence(
        multi_manifest,
        first.evidence[0].evidence_id,
        example_manifest.parent / "evidence",
    )
    payload = _payload(document)
    assert payload["declared_evidence_count"] == 2
    assert payload["other_evidence_not_checked_count"] == 1
    assert payload["obligation_evaluation_complete"] is False
    assert _evidence(document)["status"] == "pass"


def test_rehashed_result_cannot_add_acceptance_or_change_scope(
    example_manifest: Path,
) -> None:
    document = check_declared_evidence(
        load_manifest(example_manifest),
        "a1-axe-summary",
        example_manifest.parent / "evidence",
    )
    limitations = _payload(document)["limitations"]
    assert isinstance(limitations, dict)
    limitations["acceptance_decision_made"] = True
    _rehash(document)
    with pytest.raises(EvidenceCheckError, match="limitations"):
        verify_evidence_check(document)

    document = check_declared_evidence(
        load_manifest(example_manifest),
        "a1-axe-summary",
        example_manifest.parent / "evidence",
    )
    _payload(document)["overall_status"] = "accepted"
    _rehash(document)
    with pytest.raises(EvidenceCheckError, match="closed schema"):
        verify_evidence_check(document)


def test_rehashed_result_rejects_status_kind_digest_and_count_inconsistency(
    example_manifest: Path,
) -> None:
    document = check_declared_evidence(
        load_manifest(example_manifest),
        "a1-axe-summary",
        example_manifest.parent / "evidence",
    )
    _evidence(document)["status"] = "review_required"
    _rehash(document)
    with pytest.raises(EvidenceCheckError, match="incompatible"):
        verify_evidence_check(document)

    document = check_declared_evidence(
        load_manifest(example_manifest),
        "a1-axe-summary",
        example_manifest.parent / "evidence",
    )
    _evidence(document)["artifact_sha256"] = None
    _rehash(document)
    with pytest.raises(EvidenceCheckError, match="requires an artifact digest"):
        verify_evidence_check(document)

    document = check_declared_evidence(
        load_manifest(example_manifest),
        "a1-axe-summary",
        example_manifest.parent / "evidence",
    )
    _payload(document)["other_evidence_not_checked_count"] = 1
    _rehash(document)
    with pytest.raises(EvidenceCheckError, match="counts are inconsistent"):
        verify_evidence_check(document)


def test_result_is_neither_receipt_nor_evidence_plan(
    tmp_path: Path,
    example_manifest: Path,
) -> None:
    document = check_declared_evidence(
        load_manifest(example_manifest),
        "a1-axe-summary",
        example_manifest.parent / "evidence",
    )
    path = tmp_path / "single-check.json"
    path.write_bytes(canonical_json_bytes(document) + b"\n")
    with pytest.raises(ReceiptError, match="closed schema"):
        verify_receipt(load_receipt(path))
    with pytest.raises(EvidencePlanError, match="unsupported"):
        load_evidence_plan(path)


def test_check_evidence_subprocess_exit_contract_and_path_nonleak(
    copied_example: Path,
) -> None:
    manifest = copied_example / "obligations.toml"
    evidence_root = copied_example / "evidence"

    def run(evidence_id: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(  # noqa: S603 - fixed interpreter and module in a test
            [
                sys.executable,
                "-m",
                "obligation_receipts.cli",
                "check-evidence",
                str(manifest),
                evidence_id,
                "--evidence-root",
                str(evidence_root),
            ],
            check=False,
            capture_output=True,
            text=True,
        )

    passed = run("a1-axe-summary")
    assert passed.returncode == 0
    assert json.loads(passed.stdout)["payload"]["evidence"]["status"] == "pass"
    assert str(manifest) not in passed.stdout
    assert str(evidence_root) not in passed.stdout

    selected = evidence_root / "automated/axe-summary.json"
    selected.write_text('{"summary":{"critical_violations":1}}', encoding="utf-8")
    failed = run("a1-axe-summary")
    assert failed.returncode == 1
    assert json.loads(failed.stdout)["payload"]["evidence"]["status"] == "fail"

    selected.unlink()
    missing = run("a1-axe-summary")
    assert missing.returncode == 3
    assert json.loads(missing.stdout)["payload"]["evidence"]["status"] == "missing"

    (evidence_root / "manual/keyboard-review.json").unlink()
    review = run("a2-review-attestation")
    assert review.returncode == 4
    assert json.loads(review.stdout)["payload"]["evidence"]["status"] == "review_required"

    unknown = run("not-declared")
    assert unknown.returncode == 2
    assert unknown.stdout == ""
    assert "exactly one declared evidence item" in unknown.stderr
