"""Bounded checks of one evidence item declared by a source-bound manifest."""

from __future__ import annotations

import re
from enum import StrEnum
from pathlib import Path

from obligation_receipts.canonical import (
    StrictJsonError,
    canonical_json_bytes,
    sha256_bytes,
    validate_json_value,
)
from obligation_receipts.evaluator import evaluate_declared_evidence
from obligation_receipts.exit_codes import evidence_exit_code
from obligation_receipts.models import (
    Classification,
    Criticality,
    EvidenceKind,
    EvidenceSpec,
    JsonValue,
    Manifest,
    Obligation,
    ResultStatus,
)

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_DOCUMENT_FIELDS = {"payload", "payload_sha256", "schema_version"}
_PAYLOAD_FIELDS = {
    "contract_id",
    "contract_version",
    "declared_evidence_count",
    "decision_scope",
    "document_signature_status",
    "evidence",
    "limitations",
    "manifest_sha256",
    "obligation",
    "obligation_evaluation_complete",
    "other_evidence_not_checked_count",
    "schema_version",
    "source_sha256",
}
_EVIDENCE_FIELDS = {"artifact_sha256", "id", "kind", "status"}
_OBLIGATION_FIELDS = {"classification", "criticality", "id"}
_LIMITATION_FIELDS = {
    "acceptance_decision_made",
    "artifact_digest_authenticated",
    "artifact_digest_is_content_identifier_only",
    "artifact_digest_may_be_sensitive",
    "completeness_assessed",
    "evidence_sufficiency_assessed",
    "legal_interpretation_performed",
    "other_evidence_checked",
}
_LIMITATIONS: dict[str, JsonValue] = {
    "acceptance_decision_made": False,
    "artifact_digest_authenticated": False,
    "artifact_digest_is_content_identifier_only": True,
    "artifact_digest_may_be_sensitive": True,
    "completeness_assessed": False,
    "evidence_sufficiency_assessed": False,
    "legal_interpretation_performed": False,
    "other_evidence_checked": False,
}


class EvidenceCheckError(ValueError):
    """Raised when a single-evidence check is unknown or internally inconsistent."""


def _closed_object(
    value: JsonValue | None,
    fields: set[str],
    context: str,
) -> dict[str, JsonValue]:
    if not isinstance(value, dict) or set(value) != fields:
        raise EvidenceCheckError(f"{context} fields do not match the closed schema")
    return value


def _string(value: dict[str, JsonValue], key: str, context: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise EvidenceCheckError(f"{context}.{key} must be a non-empty string")
    return item


def _digest(value: dict[str, JsonValue], key: str, context: str) -> str:
    item = _string(value, key, context)
    if not _SHA256_PATTERN.fullmatch(item):
        raise EvidenceCheckError(f"{context}.{key} must be a lowercase SHA-256 digest")
    return item


def _enum[EnumValue: StrEnum](
    value: dict[str, JsonValue],
    key: str,
    context: str,
    enum_type: type[EnumValue],
) -> EnumValue:
    item = _string(value, key, context)
    try:
        return enum_type(item)
    except ValueError as exc:
        raise EvidenceCheckError(f"{context}.{key} is unsupported") from exc


def _locate_evidence(
    manifest: Manifest,
    evidence_id: str,
) -> tuple[Obligation, EvidenceSpec]:
    matches = [
        (obligation, evidence)
        for obligation in manifest.obligations
        for evidence in obligation.evidence
        if evidence.evidence_id == evidence_id
    ]
    if len(matches) != 1:
        raise EvidenceCheckError(
            f"evidence id {evidence_id!r} must identify exactly one declared evidence item"
        )
    return matches[0]


def check_declared_evidence(
    manifest: Manifest,
    evidence_id: str,
    evidence_root: Path,
) -> dict[str, JsonValue]:
    """Evaluate one selected evidence artifact and bind its bounded result."""
    obligation_value, spec_value = _locate_evidence(manifest, evidence_id)
    result = evaluate_declared_evidence(
        manifest,
        obligation_value,
        spec_value,
        evidence_root,
    )
    payload: dict[str, JsonValue] = {
        "contract_id": manifest.contract.contract_id,
        "contract_version": manifest.contract.version,
        "declared_evidence_count": len(obligation_value.evidence),
        "decision_scope": "single_declared_evidence_check_only",
        "document_signature_status": "not_signed",
        "evidence": {
            "artifact_sha256": result.artifact_sha256,
            "id": result.evidence_id,
            "kind": result.kind.value,
            "status": result.status.value,
        },
        "limitations": dict(_LIMITATIONS),
        "manifest_sha256": manifest.manifest_sha256,
        "obligation": {
            "classification": obligation_value.classification.value,
            "criticality": obligation_value.criticality.value,
            "id": obligation_value.obligation_id,
        },
        "obligation_evaluation_complete": False,
        "other_evidence_not_checked_count": len(obligation_value.evidence) - 1,
        "schema_version": "obligation-receipts/single-evidence-check/v0.1",
        "source_sha256": manifest.contract.source_sha256,
    }
    document: dict[str, JsonValue] = {
        "payload": payload,
        "payload_sha256": sha256_bytes(canonical_json_bytes(payload)),
        "schema_version": "obligation-receipts/single-evidence-check-document/v0.1",
    }
    verify_evidence_check(document)
    return document


def _validate_evidence(
    value: JsonValue | None,
) -> ResultStatus:
    evidence = _closed_object(value, _EVIDENCE_FIELDS, "single evidence check evidence")
    _string(evidence, "id", "single evidence check evidence")
    kind = _enum(evidence, "kind", "single evidence check evidence", EvidenceKind)
    status = _enum(evidence, "status", "single evidence check evidence", ResultStatus)
    allowed = (
        {ResultStatus.PASS, ResultStatus.FAIL, ResultStatus.MISSING}
        if kind is EvidenceKind.JSON_ASSERTION
        else {ResultStatus.PASS, ResultStatus.FAIL, ResultStatus.REVIEW_REQUIRED}
    )
    if status not in allowed:
        raise EvidenceCheckError("single evidence status is incompatible with its evidence kind")
    artifact_sha256 = evidence.get("artifact_sha256")
    if artifact_sha256 is not None:
        _digest(evidence, "artifact_sha256", "single evidence check evidence")
    elif status in {ResultStatus.PASS, ResultStatus.FAIL}:
        raise EvidenceCheckError("observed single evidence result requires an artifact digest")
    return status


def _validate_payload(value: JsonValue | None) -> dict[str, JsonValue]:
    payload = _closed_object(value, _PAYLOAD_FIELDS, "single evidence check payload")
    if payload.get("schema_version") != "obligation-receipts/single-evidence-check/v0.1":
        raise EvidenceCheckError("unsupported single evidence check payload schema")
    if payload.get("decision_scope") != "single_declared_evidence_check_only":
        raise EvidenceCheckError("single evidence check overstates its decision scope")
    if payload.get("document_signature_status") != "not_signed":
        raise EvidenceCheckError("single evidence check cannot claim a signature")
    if payload.get("obligation_evaluation_complete") is not False:
        raise EvidenceCheckError("single evidence check cannot claim obligation completion")
    declared_count = payload.get("declared_evidence_count")
    unchecked_count = payload.get("other_evidence_not_checked_count")
    if (
        isinstance(declared_count, bool)
        or not isinstance(declared_count, int)
        or declared_count < 1
        or isinstance(unchecked_count, bool)
        or not isinstance(unchecked_count, int)
        or unchecked_count != declared_count - 1
    ):
        raise EvidenceCheckError("single evidence check counts are inconsistent")
    for key in ("contract_id", "contract_version"):
        _string(payload, key, "single evidence check payload")
    for key in ("manifest_sha256", "source_sha256"):
        _digest(payload, key, "single evidence check payload")
    obligation = _closed_object(
        payload.get("obligation"),
        _OBLIGATION_FIELDS,
        "single evidence check obligation",
    )
    _string(obligation, "id", "single evidence check obligation")
    classification = _enum(
        obligation,
        "classification",
        "single evidence check obligation",
        Classification,
    )
    if classification is Classification.UNVERIFIABLE:
        raise EvidenceCheckError("unverifiable obligations cannot have declared evidence")
    _enum(obligation, "criticality", "single evidence check obligation", Criticality)
    _validate_evidence(payload.get("evidence"))
    limitations = _closed_object(
        payload.get("limitations"),
        _LIMITATION_FIELDS,
        "single evidence check limitations",
    )
    if limitations != _LIMITATIONS:
        raise EvidenceCheckError("single evidence check limitations are inconsistent")
    return payload


def verify_evidence_check(document: dict[str, JsonValue]) -> str:
    """Verify the closed result shape and non-circular canonical payload digest."""
    try:
        validate_json_value(document)
    except StrictJsonError as exc:
        raise EvidenceCheckError(f"single evidence check is not bounded JSON: {exc}") from exc
    closed = _closed_object(document, _DOCUMENT_FIELDS, "single evidence check")
    if closed.get("schema_version") != "obligation-receipts/single-evidence-check-document/v0.1":
        raise EvidenceCheckError("unsupported single evidence check document schema")
    payload = _validate_payload(closed.get("payload"))
    claimed = _digest(closed, "payload_sha256", "single evidence check")
    actual = sha256_bytes(canonical_json_bytes(payload))
    if claimed != actual:
        raise EvidenceCheckError("single evidence check payload digest mismatch")
    return actual


def evidence_check_exit_code(document: dict[str, JsonValue]) -> int:
    """Map preserved evidence states to documented CLI exit codes."""
    verify_evidence_check(document)
    payload = _validate_payload(document.get("payload"))
    evidence = _closed_object(
        payload.get("evidence"),
        _EVIDENCE_FIELDS,
        "single evidence check evidence",
    )
    status = _enum(evidence, "status", "single evidence check evidence", ResultStatus)
    return evidence_exit_code(status)
