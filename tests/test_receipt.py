import json
from copy import deepcopy
from pathlib import Path

import pytest

from obligation_receipts.canonical import canonical_json_bytes, sha256_bytes
from obligation_receipts.evaluator import evaluate_manifest
from obligation_receipts.manifest import load_manifest
from obligation_receipts.models import JsonValue
from obligation_receipts.receipt import (
    ReceiptError,
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
