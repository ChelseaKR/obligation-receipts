"""Receipt construction and offline verification."""

from __future__ import annotations

import os
import re
import tempfile
from datetime import UTC, datetime
from enum import StrEnum
from json import JSONDecodeError
from pathlib import Path

from obligation_receipts.canonical import (
    StrictJsonError,
    canonical_json_bytes,
    loads_json_strict,
    sha256_bytes,
    validate_json_value,
)
from obligation_receipts.models import (
    Classification,
    Criticality,
    Evaluation,
    EvidenceKind,
    JsonValue,
    OverallStatus,
    ResultStatus,
)
from obligation_receipts.paths import BoundedPathError, read_regular_file

_MAX_RECEIPT_BYTES = 2 * 1024 * 1024
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_RECEIPT_FIELDS = {"schema_version", "envelope", "payload", "payload_sha256"}
_ENVELOPE_FIELDS = {"claimed_generated_at", "signature_status", "trusted_time"}
_PAYLOAD_FIELDS = {
    "contract",
    "decision_scope",
    "manifest_sha256",
    "obligation_counts",
    "obligations",
    "overall_status",
    "schema_version",
}
_CONTRACT_FIELDS = {
    "authority",
    "effective_date",
    "id",
    "source_path",
    "source_sha256",
    "title",
    "version",
}
_OBLIGATION_FIELDS = {
    "classification",
    "clause_ref",
    "criticality",
    "evidence",
    "id",
    "status",
}
_EVIDENCE_FIELDS = {"artifact_sha256", "detail", "id", "kind", "status"}


class ReceiptError(ValueError):
    """Raised when a receipt is malformed or fails verification."""


def _closed_object(value: JsonValue | None, fields: set[str], context: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict) or set(value) != fields:
        raise ReceiptError(f"{context} fields do not match the closed schema")
    return value


def _required_string(value: dict[str, JsonValue], key: str, context: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise ReceiptError(f"{context}.{key} must be a non-empty string")
    return item


def _required_digest(value: dict[str, JsonValue], key: str, context: str) -> str:
    item = _required_string(value, key, context)
    if not _SHA256_PATTERN.fullmatch(item):
        raise ReceiptError(f"{context}.{key} must be a lowercase SHA-256 digest")
    return item


def _enum_value[EnumValue: StrEnum](
    value: dict[str, JsonValue],
    key: str,
    context: str,
    enum_type: type[EnumValue],
) -> EnumValue:
    item = _required_string(value, key, context)
    try:
        return enum_type(item)
    except ValueError as exc:
        raise ReceiptError(f"{context}.{key} is unsupported") from exc


def _validate_claimed_time(value: str) -> None:
    normalized = f"{value[:-1]}+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ReceiptError("claimed_generated_at must be an ISO 8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ReceiptError("claimed_generated_at must include a UTC offset")


def _validate_contract(value: JsonValue | None) -> None:
    contract = _closed_object(value, _CONTRACT_FIELDS, "receipt payload contract")
    for field in _CONTRACT_FIELDS - {"source_sha256"}:
        _required_string(contract, field, "receipt payload contract")
    _required_digest(contract, "source_sha256", "receipt payload contract")


def _validate_evidence(value: JsonValue, context: str) -> tuple[str, EvidenceKind, ResultStatus]:
    evidence = _closed_object(value, _EVIDENCE_FIELDS, context)
    evidence_id = _required_string(evidence, "id", context)
    _required_string(evidence, "detail", context)
    kind = _enum_value(evidence, "kind", context, EvidenceKind)
    status = _enum_value(evidence, "status", context, ResultStatus)
    allowed_statuses = (
        {ResultStatus.PASS, ResultStatus.FAIL, ResultStatus.MISSING}
        if kind is EvidenceKind.JSON_ASSERTION
        else {ResultStatus.PASS, ResultStatus.FAIL, ResultStatus.REVIEW_REQUIRED}
    )
    if status not in allowed_statuses:
        raise ReceiptError(f"{context}.status is incompatible with its evidence kind")
    digest = evidence.get("artifact_sha256")
    if digest is not None:
        _required_digest(evidence, "artifact_sha256", context)
    elif status in {ResultStatus.PASS, ResultStatus.FAIL}:
        raise ReceiptError(f"{context}.artifact_sha256 is required for an observed result")
    return evidence_id, kind, status


def _combined_status(statuses: list[ResultStatus]) -> ResultStatus:
    for status in (
        ResultStatus.FAIL,
        ResultStatus.MISSING,
        ResultStatus.REVIEW_REQUIRED,
    ):
        if status in statuses:
            return status
    return ResultStatus.PASS


def _validate_obligation(
    value: JsonValue,
    index: int,
) -> tuple[str, Criticality, ResultStatus, list[str]]:
    context = f"receipt payload obligations[{index}]"
    obligation = _closed_object(value, _OBLIGATION_FIELDS, context)
    obligation_id = _required_string(obligation, "id", context)
    _required_string(obligation, "clause_ref", context)
    classification = _enum_value(obligation, "classification", context, Classification)
    criticality = _enum_value(obligation, "criticality", context, Criticality)
    status = _enum_value(obligation, "status", context, ResultStatus)
    evidence_raw = obligation.get("evidence")
    if not isinstance(evidence_raw, list):
        raise ReceiptError(f"{context}.evidence must be an array")
    if classification is Classification.UNVERIFIABLE:
        if evidence_raw or status is not ResultStatus.UNVERIFIABLE:
            raise ReceiptError(f"{context} has inconsistent unverifiable evidence or status")
        return obligation_id, criticality, status, []
    if not evidence_raw:
        raise ReceiptError(f"{context}.evidence must not be empty")
    expected_kind = {
        Classification.AUTOMATED: EvidenceKind.JSON_ASSERTION,
        Classification.MANUAL_REVIEW: EvidenceKind.REVIEW_ATTESTATION,
        Classification.EXTERNAL_EVIDENCE: EvidenceKind.EXTERNAL_ATTESTATION,
    }[classification]
    validated = [
        _validate_evidence(item, f"{context}.evidence[{evidence_index}]")
        for evidence_index, item in enumerate(evidence_raw)
    ]
    if any(kind is not expected_kind for _, kind, _ in validated):
        raise ReceiptError(f"{context} evidence kind does not match its classification")
    if status is not _combined_status([item_status for _, _, item_status in validated]):
        raise ReceiptError(f"{context}.status does not match its evidence results")
    return obligation_id, criticality, status, [item_id for item_id, _, _ in validated]


def _expected_overall_status(
    results: list[tuple[Criticality, ResultStatus]],
) -> OverallStatus:
    must_statuses = {status for criticality, status in results if criticality is Criticality.MUST}
    if ResultStatus.FAIL in must_statuses:
        return OverallStatus.REJECTED
    if must_statuses - {ResultStatus.PASS}:
        return OverallStatus.INCOMPLETE
    if any(status is not ResultStatus.PASS for _, status in results):
        return OverallStatus.ACCEPTED_WITH_FINDINGS
    return OverallStatus.ACCEPTED


def _validate_payload(value: JsonValue | None) -> dict[str, JsonValue]:
    payload = _closed_object(value, _PAYLOAD_FIELDS, "receipt payload")
    if payload.get("schema_version") != "obligation-receipts/evaluation/v0.1":
        raise ReceiptError("unsupported receipt payload schema")
    if payload.get("decision_scope") != "technical_evidence_evaluation_only":
        raise ReceiptError("receipt payload overstates its decision scope")
    _required_digest(payload, "manifest_sha256", "receipt payload")
    _validate_contract(payload.get("contract"))
    obligations_raw = payload.get("obligations")
    if not isinstance(obligations_raw, list) or not obligations_raw:
        raise ReceiptError("receipt payload obligations must be a non-empty array")
    obligations = [_validate_obligation(item, index) for index, item in enumerate(obligations_raw)]
    obligation_ids = [item[0] for item in obligations]
    evidence_ids = [evidence_id for item in obligations for evidence_id in item[3]]
    if len(obligation_ids) != len(set(obligation_ids)):
        raise ReceiptError("receipt payload obligation ids must be unique")
    if len(evidence_ids) != len(set(evidence_ids)):
        raise ReceiptError("receipt payload evidence ids must be unique")
    counts = _closed_object(
        payload.get("obligation_counts"),
        {status.value for status in ResultStatus},
        "receipt payload obligation_counts",
    )
    expected_counts = {
        status.value: sum(item[2] is status for item in obligations) for status in ResultStatus
    }
    if any(isinstance(value, bool) or not isinstance(value, int) for value in counts.values()):
        raise ReceiptError("receipt payload obligation counts must be integers")
    if counts != expected_counts:
        raise ReceiptError("receipt payload obligation counts do not match its obligations")
    overall_status = _enum_value(payload, "overall_status", "receipt payload", OverallStatus)
    if overall_status is not _expected_overall_status([(item[1], item[2]) for item in obligations]):
        raise ReceiptError("receipt payload overall status does not match its obligations")
    return payload


def build_receipt(
    evaluation: Evaluation, *, generated_at: str | None = None
) -> dict[str, JsonValue]:
    """Build a deterministic payload with an explicitly untrusted envelope."""
    payload = evaluation.payload()
    payload_sha256 = sha256_bytes(canonical_json_bytes(payload))
    timestamp = generated_at or datetime.now(tz=UTC).replace(microsecond=0).isoformat()
    _validate_claimed_time(timestamp)
    return {
        "envelope": {
            "claimed_generated_at": timestamp,
            "signature_status": "not_signed",
            "trusted_time": False,
        },
        "payload": payload,
        "payload_sha256": payload_sha256,
        "schema_version": "obligation-receipts/receipt/v0.1",
    }


def write_receipt(path: Path, receipt: dict[str, JsonValue]) -> None:
    """Validate and atomically write one bounded canonical receipt."""
    verify_receipt(receipt)
    encoded = canonical_json_bytes(receipt) + b"\n"
    if len(encoded) > _MAX_RECEIPT_BYTES:
        raise ReceiptError("receipt exceeds the 2 MiB limit")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def load_receipt(path: Path) -> dict[str, JsonValue]:
    """Load a bounded receipt document."""
    try:
        data = read_regular_file(path, max_bytes=_MAX_RECEIPT_BYTES)
        raw = loads_json_strict(data)
    except BoundedPathError as exc:
        if "exceeds" in str(exc):
            raise ReceiptError("receipt exceeds the 2 MiB limit") from exc
        raise ReceiptError(f"receipt cannot be read safely: {exc}") from exc
    except (JSONDecodeError, RecursionError, StrictJsonError) as exc:
        raise ReceiptError(f"receipt is not strict JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise ReceiptError("receipt must be a JSON object")
    return raw


def verify_receipt(receipt: dict[str, JsonValue]) -> str:
    """Verify the non-circular payload digest and fixed trust labels."""
    try:
        validate_json_value(receipt)
    except StrictJsonError as exc:
        raise ReceiptError(f"receipt is not bounded JSON: {exc}") from exc
    _closed_object(receipt, _RECEIPT_FIELDS, "receipt")
    if receipt.get("schema_version") != "obligation-receipts/receipt/v0.1":
        raise ReceiptError("unsupported receipt schema")
    payload = _validate_payload(receipt.get("payload"))
    claimed_hash = _required_digest(receipt, "payload_sha256", "receipt")
    envelope = _closed_object(receipt.get("envelope"), _ENVELOPE_FIELDS, "receipt envelope")
    timestamp = _required_string(envelope, "claimed_generated_at", "receipt envelope")
    _validate_claimed_time(timestamp)
    if (
        envelope.get("signature_status") != "not_signed"
        or envelope.get("trusted_time") is not False
    ):
        raise ReceiptError("receipt envelope overstates its trust status")
    actual_hash = sha256_bytes(canonical_json_bytes(payload))
    if actual_hash != claimed_hash:
        raise ReceiptError("receipt payload digest mismatch")
    return actual_hash
