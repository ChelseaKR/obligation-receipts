import json
import os
from copy import deepcopy
from pathlib import Path

import pytest

from obligation_receipts.canonical import canonical_json_bytes, sha256_bytes
from obligation_receipts.evaluator import _overall_status, evaluate_manifest
from obligation_receipts.manifest import load_manifest
from obligation_receipts.models import (
    Classification,
    Criticality,
    JsonValue,
    ObligationResult,
    OverallStatus,
    ResultStatus,
)
from obligation_receipts.receipt import (
    ReceiptError,
    _expected_overall_status,
    build_receipt,
    load_receipt,
    verify_receipt,
    write_receipt,
)


def test_receipt_is_deterministic_outside_envelope(example_manifest: Path) -> None:
    manifest = load_manifest(example_manifest)
    evaluation = evaluate_manifest(manifest, example_manifest.parent / "evidence")
    first = build_receipt(evaluation, generated_at="2026-01-01T00:00:00+00:00")
    second = build_receipt(evaluation, generated_at="2027-01-01T00:00:00+00:00")
    assert first["payload"] == second["payload"]
    assert first["payload_sha256"] == second["payload_sha256"]
    assert first["envelope"] != second["envelope"]
    assert verify_receipt(first) == first["payload_sha256"]


def test_tampered_receipt_is_rejected(example_manifest: Path) -> None:
    manifest = load_manifest(example_manifest)
    receipt = build_receipt(
        evaluate_manifest(manifest, example_manifest.parent / "evidence"),
        generated_at="2026-01-01T00:00:00+00:00",
    )
    assert isinstance(receipt["payload"], dict)
    assert isinstance(receipt["payload"]["contract"], dict)
    receipt["payload"]["contract"]["title"] = "changed but still structurally valid"
    with pytest.raises(ReceiptError, match="digest mismatch"):
        verify_receipt(receipt)


def test_write_and_load_receipt(tmp_path: Path, example_manifest: Path) -> None:
    manifest = load_manifest(example_manifest)
    receipt = build_receipt(evaluate_manifest(manifest, example_manifest.parent / "evidence"))
    path = tmp_path / "nested" / "receipt.json"
    write_receipt(path, receipt)
    assert load_receipt(path) == receipt


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ({"schema_version": "wrong"}, "unsupported"),
        ({"payload": None}, "payload fields"),
        ({"payload_sha256": None}, "payload_sha256"),
        ({"envelope": None}, "envelope fields"),
        (
            {
                "envelope": {
                    "claimed_generated_at": "2026-01-01T00:00:00+00:00",
                    "signature_status": "signed",
                    "trusted_time": False,
                }
            },
            "overstates",
        ),
        (
            {
                "envelope": {
                    "claimed_generated_at": "2026-01-01T00:00:00+00:00",
                    "signature_status": "not_signed",
                    "trusted_time": True,
                }
            },
            "overstates",
        ),
        ({"unexpected": "field"}, "closed schema"),
    ],
)
def test_malformed_receipt_is_rejected(
    example_manifest: Path, mutation: dict[str, object], message: str
) -> None:
    manifest = load_manifest(example_manifest)
    receipt = build_receipt(
        evaluate_manifest(manifest, example_manifest.parent / "evidence"),
        generated_at="2026-01-01T00:00:00+00:00",
    )
    receipt.update(mutation)  # type: ignore[arg-type]
    with pytest.raises(ReceiptError, match=message):
        verify_receipt(receipt)


def test_receipt_envelope_is_closed_and_timestamp_is_present(example_manifest: Path) -> None:
    manifest = load_manifest(example_manifest)
    receipt = build_receipt(
        evaluate_manifest(manifest, example_manifest.parent / "evidence"),
        generated_at="2026-01-01T00:00:00+00:00",
    )
    assert isinstance(receipt["envelope"], dict)
    receipt["envelope"]["unexpected"] = "field"
    with pytest.raises(ReceiptError, match="envelope fields"):
        verify_receipt(receipt)
    del receipt["envelope"]["unexpected"]
    receipt["envelope"]["claimed_generated_at"] = ""
    with pytest.raises(ReceiptError, match="non-empty"):
        verify_receipt(receipt)


def test_load_receipt_rejects_non_object_and_oversized(tmp_path: Path) -> None:
    path = tmp_path / "receipt.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ReceiptError, match="JSON object"):
        load_receipt(path)
    path.write_bytes(b" " * (2 * 1024 * 1024 + 1))
    with pytest.raises(ReceiptError, match="2 MiB"):
        load_receipt(path)


@pytest.mark.parametrize(
    "mutation",
    [
        '"payload_sha256": "first", "payload_sha256": "second"',
        '"payload_sha256": NaN',
        '"payload_sha256": Infinity',
        '"payload_sha256": -Infinity',
    ],
)
def test_load_receipt_rejects_ambiguous_json(tmp_path: Path, mutation: str) -> None:
    path = tmp_path / "receipt.json"
    path.write_text(f'{{"schema_version":"x",{mutation}}}', encoding="utf-8")
    with pytest.raises(ReceiptError, match="strict JSON"):
        load_receipt(path)


def test_load_receipt_rejects_nested_duplicate_key(tmp_path: Path) -> None:
    path = tmp_path / "receipt.json"
    path.write_text(
        json.dumps({"envelope": {"trusted_time": False}}).replace(
            '"trusted_time": false',
            '"trusted_time": false, "trusted_time": true',
        ),
        encoding="utf-8",
    )
    with pytest.raises(ReceiptError, match="duplicate JSON object key"):
        load_receipt(path)


def test_receipt_rejects_invalid_utf8_and_excessive_nesting(tmp_path: Path) -> None:
    path = tmp_path / "receipt.json"
    path.write_bytes(b"\xff")
    with pytest.raises(ReceiptError, match="valid UTF-8"):
        load_receipt(path)
    path.write_text("[" * 66 + "0" + "]" * 66, encoding="utf-8")
    with pytest.raises(ReceiptError, match="nesting limit"):
        load_receipt(path)


def _rehash(receipt: dict[str, JsonValue]) -> None:
    receipt["payload_sha256"] = sha256_bytes(canonical_json_bytes(receipt["payload"]))


def _fresh_receipt(example_manifest: Path) -> dict[str, JsonValue]:
    return deepcopy(
        build_receipt(
            evaluate_manifest(
                load_manifest(example_manifest), example_manifest.parent / "evidence"
            ),
            generated_at="2026-01-01T00:00:00+00:00",
        )
    )


def test_recomputed_arbitrary_payload_is_not_a_valid_receipt(example_manifest: Path) -> None:
    receipt = build_receipt(
        evaluate_manifest(load_manifest(example_manifest), example_manifest.parent / "evidence"),
        generated_at="2026-01-01T00:00:00+00:00",
    )
    receipt["payload"] = {"overall_status": "accepted"}
    _rehash(receipt)
    with pytest.raises(ReceiptError, match="closed schema"):
        verify_receipt(receipt)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("decision_scope", "contractually_accepted", "decision scope"),
        ("overall_status", "accepted", "overall status"),
        (
            "obligation_counts",
            {
                "pass": 4,
                "fail": 0,
                "missing": 0,
                "review_required": 0,
                "unverifiable": 0,
            },
            "counts do not match",
        ),
    ],
)
def test_recomputed_semantically_inconsistent_payload_is_rejected(
    example_manifest: Path,
    field: str,
    value: JsonValue,
    message: str,
) -> None:
    receipt = _fresh_receipt(example_manifest)
    assert isinstance(receipt["payload"], dict)
    receipt["payload"][field] = value
    _rehash(receipt)
    with pytest.raises(ReceiptError, match=message):
        verify_receipt(receipt)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("schema_version", "wrong", "payload schema"),
        ("manifest_sha256", "bad", "SHA-256"),
        ("overall_status", "unknown", "unsupported"),
    ],
)
def test_recomputed_payload_rejects_invalid_core_fields(
    example_manifest: Path,
    field: str,
    value: str,
    message: str,
) -> None:
    receipt = _fresh_receipt(example_manifest)
    payload = receipt["payload"]
    assert isinstance(payload, dict)
    payload[field] = value
    _rehash(receipt)
    with pytest.raises(ReceiptError, match=message):
        verify_receipt(receipt)


def test_recomputed_payload_rejects_incompatible_evidence(
    example_manifest: Path,
) -> None:
    receipt = _fresh_receipt(example_manifest)
    payload = receipt["payload"]
    assert isinstance(payload, dict)
    obligations = payload["obligations"]
    assert isinstance(obligations, list)
    first = obligations[0]
    assert isinstance(first, dict)
    evidence = first["evidence"]
    assert isinstance(evidence, list)
    item = evidence[0]
    assert isinstance(item, dict)
    item["kind"] = "external_attestation"
    _rehash(receipt)
    with pytest.raises(ReceiptError, match="classification"):
        verify_receipt(receipt)

    item["kind"] = "json_assertion"
    item["artifact_sha256"] = None
    _rehash(receipt)
    with pytest.raises(ReceiptError, match="required for an observed result"):
        verify_receipt(receipt)


def test_recomputed_payload_rejects_duplicate_ids_and_boolean_counts(
    example_manifest: Path,
) -> None:
    receipt = _fresh_receipt(example_manifest)
    payload = receipt["payload"]
    assert isinstance(payload, dict)
    obligations = payload["obligations"]
    assert isinstance(obligations, list)
    assert isinstance(obligations[0], dict)
    assert isinstance(obligations[1], dict)
    obligations[1]["id"] = obligations[0]["id"]
    _rehash(receipt)
    with pytest.raises(ReceiptError, match="ids must be unique"):
        verify_receipt(receipt)

    receipt = _fresh_receipt(example_manifest)
    payload = receipt["payload"]
    assert isinstance(payload, dict)
    counts = payload["obligation_counts"]
    assert isinstance(counts, dict)
    counts["pass"] = True
    _rehash(receipt)
    with pytest.raises(ReceiptError, match="counts must be integers"):
        verify_receipt(receipt)


def test_programmatic_receipt_is_structurally_bounded(example_manifest: Path) -> None:
    receipt = _fresh_receipt(example_manifest)
    payload = receipt["payload"]
    assert isinstance(payload, dict)
    contract = payload["contract"]
    assert isinstance(contract, dict)
    contract["title"] = float("nan")
    with pytest.raises(ReceiptError, match="bounded JSON"):
        verify_receipt(receipt)


@pytest.mark.parametrize("timestamp", ["not-a-time", "2026-01-01T00:00:00"])
def test_receipt_requires_offset_iso_timestamp(example_manifest: Path, timestamp: str) -> None:
    evaluation = evaluate_manifest(
        load_manifest(example_manifest), example_manifest.parent / "evidence"
    )
    with pytest.raises(ReceiptError, match=r"timestamp|UTC offset"):
        build_receipt(evaluation, generated_at=timestamp)


def test_atomic_write_does_not_use_predictable_temp_path(
    tmp_path: Path, example_manifest: Path
) -> None:
    receipt = build_receipt(
        evaluate_manifest(load_manifest(example_manifest), example_manifest.parent / "evidence")
    )
    path = tmp_path / "receipt.json"
    predictable = tmp_path / "receipt.json.tmp"
    predictable.write_text("sentinel", encoding="utf-8")
    write_receipt(path, receipt)
    assert predictable.read_text(encoding="utf-8") == "sentinel"
    assert load_receipt(path) == receipt


def test_writer_rejects_invalid_or_oversized_receipt_before_filesystem_mutation(
    tmp_path: Path,
    example_manifest: Path,
) -> None:
    receipt = _fresh_receipt(example_manifest)
    payload = receipt["payload"]
    assert isinstance(payload, dict)
    contract = payload["contract"]
    assert isinstance(contract, dict)
    contract["title"] = "x" * (2 * 1024 * 1024)
    _rehash(receipt)
    destination = tmp_path / "not-created" / "receipt.json"
    with pytest.raises(ReceiptError, match="2 MiB"):
        write_receipt(destination, receipt)
    assert not destination.parent.exists()

    invalid = _fresh_receipt(example_manifest)
    invalid["payload_sha256"] = "0" * 64
    with pytest.raises(ReceiptError, match="digest mismatch"):
        write_receipt(destination, invalid)
    assert not destination.parent.exists()


def test_receipt_replace_failure_preserves_destination_and_cleans_temp(
    tmp_path: Path,
    example_manifest: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "receipt.json"
    destination.write_text("existing", encoding="utf-8")

    def fail_replace(source: Path, target: Path) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr("obligation_receipts.receipt.os.replace", fail_replace)
    with pytest.raises(OSError, match="simulated"):
        write_receipt(destination, _fresh_receipt(example_manifest))
    assert destination.read_text(encoding="utf-8") == "existing"
    assert sorted(tmp_path.iterdir()) == [destination]


def _built(example_manifest: Path) -> dict[str, JsonValue]:
    return build_receipt(
        evaluate_manifest(load_manifest(example_manifest), example_manifest.parent / "evidence"),
        generated_at="2026-01-01T00:00:00+00:00",
    )


def _obligations(receipt: dict[str, JsonValue]) -> list[JsonValue]:
    payload = receipt["payload"]
    assert isinstance(payload, dict)
    obligations = payload["obligations"]
    assert isinstance(obligations, list)
    return obligations


def _rehashed(receipt: dict[str, JsonValue]) -> dict[str, JsonValue]:
    receipt["payload_sha256"] = sha256_bytes(canonical_json_bytes(receipt["payload"]))
    return receipt


def test_recomputed_payload_rejects_a_non_array_evidence_field(example_manifest: Path) -> None:
    receipt = _built(example_manifest)
    first = _obligations(receipt)[0]
    assert isinstance(first, dict)
    first["evidence"] = "one artifact"
    with pytest.raises(ReceiptError, match="evidence must be an array"):
        verify_receipt(_rehashed(receipt))


def test_recomputed_payload_rejects_an_evidenced_obligation_with_no_evidence(
    example_manifest: Path,
) -> None:
    receipt = _built(example_manifest)
    first = _obligations(receipt)[0]
    assert isinstance(first, dict)
    first["evidence"] = []
    first["status"] = "pass"
    with pytest.raises(ReceiptError, match="evidence must not be empty"):
        verify_receipt(_rehashed(receipt))


def test_recomputed_payload_rejects_an_unverifiable_obligation_carrying_evidence(
    example_manifest: Path,
) -> None:
    """The unverifiable obligation is the last one in the synthetic example."""
    receipt = _built(example_manifest)
    last = _obligations(receipt)[-1]
    assert isinstance(last, dict)
    first = _obligations(receipt)[0]
    assert isinstance(first, dict)
    evidence = first["evidence"]
    assert isinstance(evidence, list)
    last["evidence"] = deepcopy(evidence)
    with pytest.raises(ReceiptError, match="inconsistent unverifiable"):
        verify_receipt(_rehashed(receipt))


def test_recomputed_payload_rejects_an_obligation_status_its_evidence_does_not_support(
    example_manifest: Path,
) -> None:
    receipt = _built(example_manifest)
    first = _obligations(receipt)[0]
    assert isinstance(first, dict)
    evidence = first["evidence"]
    assert isinstance(evidence, list)
    item = evidence[0]
    assert isinstance(item, dict)
    item["status"] = "fail"
    with pytest.raises(ReceiptError, match="status does not match its evidence"):
        verify_receipt(_rehashed(receipt))


def test_recomputed_payload_rejects_an_empty_obligation_array(example_manifest: Path) -> None:
    receipt = _built(example_manifest)
    payload = receipt["payload"]
    assert isinstance(payload, dict)
    payload["obligations"] = []
    with pytest.raises(ReceiptError, match="obligations must be a non-empty array"):
        verify_receipt(_rehashed(receipt))


def test_recomputed_payload_rejects_evidence_ids_reused_across_obligations(
    example_manifest: Path,
) -> None:
    """Evidence ids are unique manifest-wide, which is what binds an attestation."""
    receipt = _built(example_manifest)
    obligations = _obligations(receipt)
    first, second = obligations[0], obligations[1]
    assert isinstance(first, dict) and isinstance(second, dict)
    first_evidence = first["evidence"]
    second_evidence = second["evidence"]
    assert isinstance(first_evidence, list) and isinstance(second_evidence, list)
    borrowed = first_evidence[0]
    reused = second_evidence[0]
    assert isinstance(borrowed, dict) and isinstance(reused, dict)
    reused["id"] = borrowed["id"]
    with pytest.raises(ReceiptError, match="evidence ids must be unique"):
        verify_receipt(_rehashed(receipt))


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO creation is unavailable")
def test_load_receipt_rejects_a_receipt_that_is_not_a_regular_file(tmp_path: Path) -> None:
    fifo = tmp_path / "receipt.json"
    os.mkfifo(fifo)
    with pytest.raises(ReceiptError, match="cannot be read safely"):
        load_receipt(fifo)


def test_receipt_evidence_status_must_suit_its_kind(example_manifest: Path) -> None:
    """`review_required` is an attestation state; an automated assertion cannot hold it."""
    receipt = _built(example_manifest)
    first = _obligations(receipt)[0]
    assert isinstance(first, dict)
    evidence = first["evidence"]
    assert isinstance(evidence, list)
    item = evidence[0]
    assert isinstance(item, dict)
    item["status"] = "review_required"
    first["status"] = "review_required"
    with pytest.raises(ReceiptError, match="incompatible with its evidence kind"):
        verify_receipt(_rehashed(receipt))


@pytest.mark.parametrize(
    ("results", "expected"),
    [
        (
            [(Criticality.MUST, ResultStatus.PASS), (Criticality.SHOULD, ResultStatus.PASS)],
            OverallStatus.ACCEPTED,
        ),
        (
            [(Criticality.MUST, ResultStatus.PASS), (Criticality.SHOULD, ResultStatus.FAIL)],
            OverallStatus.ACCEPTED_WITH_FINDINGS,
        ),
        ([(Criticality.MUST, ResultStatus.FAIL)], OverallStatus.REJECTED),
        ([(Criticality.MUST, ResultStatus.MISSING)], OverallStatus.INCOMPLETE),
        ([(Criticality.MUST, ResultStatus.REVIEW_REQUIRED)], OverallStatus.INCOMPLETE),
        ([(Criticality.MUST, ResultStatus.UNVERIFIABLE)], OverallStatus.INCOMPLETE),
    ],
)
def test_receipt_status_algebra_matches_the_documented_table(
    results: list[tuple[Criticality, ResultStatus]], expected: OverallStatus
) -> None:
    """The receipt verifier re-derives overall status; it must agree with the evaluator.

    Exercised directly because the synthetic example deliberately contains an
    unverifiable obligation and so can only ever produce one of these arms.
    """
    assert _expected_overall_status(results) is expected


def test_receipt_and_evaluator_status_algebras_cannot_drift_apart() -> None:
    """Two implementations of the same rule must agree on every input.

    `evaluator._overall_status` decides the status a receipt is issued with;
    `receipt._expected_overall_status` re-derives it during verification, and
    rejects the receipt when the two disagree. If they ever drift, verification
    starts rejecting honest receipts, or accepting dishonest ones, with nothing
    else in the suite comparing them. Every criticality/status pair, and every
    ordered pair of them, is checked.
    """
    pairs = [(criticality, status) for criticality in Criticality for status in ResultStatus]
    cases = [[pair] for pair in pairs] + [[first, second] for first in pairs for second in pairs]
    for case in cases:
        evaluated = _overall_status(
            tuple(
                ObligationResult(
                    obligation_id=f"o{index}",
                    clause_ref="c",
                    classification=Classification.AUTOMATED,
                    criticality=criticality,
                    status=status,
                    evidence=(),
                )
                for index, (criticality, status) in enumerate(case)
            )
        )
        assert _expected_overall_status(case) is evaluated, (
            f"status algebras disagree for {case}: "
            f"receipt says {_expected_overall_status(case)}, evaluator says {evaluated}"
        )
