"""Deterministic evidence-collection plans derived from approved manifests."""

from __future__ import annotations

import os
import re
import tempfile
from enum import StrEnum
from json import JSONDecodeError
from pathlib import Path
from typing import cast

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
    EvidenceKind,
    EvidenceSpec,
    JsonValue,
    Manifest,
    Obligation,
)
from obligation_receipts.paths import (
    BoundedPathError,
    read_regular_file,
    validate_portable_relative_path,
)
from obligation_receipts.pointer import is_well_formed

_MAX_PLAN_BYTES = 2 * 1024 * 1024
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_OPERATORS = {"eq", "ne", "gt", "gte", "lt", "lte", "exists"}
_DOCUMENT_FIELDS = {"payload", "payload_sha256", "schema_version"}
_PAYLOAD_FIELDS = {
    "contract_id",
    "contract_version",
    "decision_scope",
    "detail_mode",
    "evidence_observed",
    "limitations",
    "manifest_sha256",
    "obligation_count",
    "obligations",
    "schema_version",
    "source_sha256",
}
_OBLIGATION_FIELDS = {
    "classification",
    "combination_rule",
    "criticality",
    "evidence_requirements",
    "id",
    "no_evidence_reason",
    "source_locator",
}
_EVIDENCE_FIELDS = {"assertion", "attestation_binding", "id", "kind", "path"}
_ASSERTION_FIELDS = {"expected", "expected_declared", "operator", "pointer"}
_BINDING_FIELDS = {"allowed_statuses", "fixed_values", "required_fields"}
_FIXED_VALUE_FIELDS = {
    "contract_id",
    "contract_version",
    "evidence_id",
    "manifest_sha256",
    "obligation_id",
    "schema_version",
}
_LIMITATION_FIELDS = {
    "approval_authenticated",
    "completeness_proven",
    "evidence_sufficiency_assessed",
    "legal_interpretation_performed",
    "official_decision_made",
}
_LIMITATIONS: dict[str, JsonValue] = {
    "approval_authenticated": False,
    "completeness_proven": False,
    "evidence_sufficiency_assessed": False,
    "legal_interpretation_performed": False,
    "official_decision_made": False,
}


class EvidencePlanError(ValueError):
    """Raised when an evidence plan is malformed, unsafe, or internally inconsistent."""


def _safe_relative_path(value: str) -> bool:
    try:
        validate_portable_relative_path(value)
    except BoundedPathError:
        return False
    return True


def _attestation_fields(kind: EvidenceKind) -> list[str]:
    common = [
        "schema_version",
        "contract_id",
        "contract_version",
        "manifest_sha256",
        "obligation_id",
        "evidence_id",
        "status",
    ]
    if kind is EvidenceKind.REVIEW_ATTESTATION:
        return [*common, "reviewer", "reviewed_at", "method"]
    return [*common, "issuer", "observed_at", "source_uri"]


def _evidence_requirement(
    manifest: Manifest,
    obligation: Obligation,
    evidence: EvidenceSpec,
    include_local_details: bool,
) -> dict[str, JsonValue]:
    if not _safe_relative_path(evidence.path):
        raise EvidencePlanError("manifest evidence path must remain inside the evidence root")
    assertion: JsonValue = None
    binding: JsonValue = None
    if evidence.kind is EvidenceKind.JSON_ASSERTION:
        assertion = {
            "expected": evidence.expected,
            "expected_declared": evidence.operator != "exists",
            "operator": evidence.operator,
            "pointer": evidence.pointer,
        }
    else:
        binding = cast(
            JsonValue,
            {
                "allowed_statuses": ["pass", "fail"],
                "fixed_values": {
                    "contract_id": manifest.contract.contract_id,
                    "contract_version": manifest.contract.version,
                    "evidence_id": evidence.evidence_id,
                    "manifest_sha256": manifest.manifest_sha256,
                    "obligation_id": obligation.obligation_id,
                    "schema_version": "obligation-receipts/attestation/v0.1",
                },
                "required_fields": _attestation_fields(evidence.kind),
            },
        )
    return {
        "assertion": assertion,
        "attestation_binding": binding,
        "id": evidence.evidence_id,
        "kind": evidence.kind.value,
        "path": evidence.path if include_local_details else None,
    }


def build_evidence_plan(
    manifest: Manifest,
    *,
    include_local_details: bool = False,
) -> dict[str, JsonValue]:
    """Project a source-bound manifest into a deterministic collection checklist."""
    obligations: list[JsonValue] = []
    for obligation in manifest.obligations:
        requirements: list[JsonValue] = [
            _evidence_requirement(
                manifest,
                obligation,
                evidence,
                include_local_details,
            )
            for evidence in obligation.evidence
        ]
        obligations.append(
            {
                "classification": obligation.classification.value,
                "combination_rule": (
                    "not_applicable"
                    if obligation.classification is Classification.UNVERIFIABLE
                    else "all_required"
                ),
                "criticality": obligation.criticality.value,
                "evidence_requirements": requirements,
                "id": obligation.obligation_id,
                "no_evidence_reason": (
                    (
                        obligation.reason
                        if include_local_details
                        else "no_evaluable_evidence_declared"
                    )
                    if obligation.classification is Classification.UNVERIFIABLE
                    else None
                ),
                "source_locator": obligation.clause_ref if include_local_details else None,
            }
        )
    payload: dict[str, JsonValue] = {
        "contract_id": manifest.contract.contract_id,
        "contract_version": manifest.contract.version,
        "decision_scope": "evidence_collection_checklist_only",
        "detail_mode": "local_sensitive" if include_local_details else "portable_redacted",
        "evidence_observed": False,
        "limitations": dict(_LIMITATIONS),
        "manifest_sha256": manifest.manifest_sha256,
        "obligation_count": len(obligations),
        "obligations": obligations,
        "schema_version": "obligation-receipts/evidence-plan/v0.1",
        "source_sha256": manifest.contract.source_sha256,
    }
    plan: dict[str, JsonValue] = {
        "payload": payload,
        "payload_sha256": sha256_bytes(canonical_json_bytes(payload)),
        "schema_version": "obligation-receipts/evidence-plan-document/v0.1",
    }
    verify_evidence_plan(plan)
    return plan


def _closed_object(
    value: JsonValue | None,
    fields: set[str],
    context: str,
) -> dict[str, JsonValue]:
    if not isinstance(value, dict) or set(value) != fields:
        raise EvidencePlanError(f"{context} fields do not match the closed schema")
    return value


def _string(value: dict[str, JsonValue], key: str, context: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise EvidencePlanError(f"{context}.{key} must be a non-empty string")
    return item


def _digest(value: dict[str, JsonValue], key: str, context: str) -> str:
    item = _string(value, key, context)
    if not _SHA256_PATTERN.fullmatch(item):
        raise EvidencePlanError(f"{context}.{key} must be a lowercase SHA-256 digest")
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
        raise EvidencePlanError(f"{context}.{key} is unsupported") from exc


def _validate_assertion(value: JsonValue | None, context: str) -> None:
    assertion = _closed_object(value, _ASSERTION_FIELDS, f"{context}.assertion")
    pointer = assertion.get("pointer")
    operator = assertion.get("operator")
    expected_declared = assertion.get("expected_declared")
    # The same well-formedness test the manifest loader applies, so a plan and
    # the manifest it was generated from can never disagree about a pointer.
    if not isinstance(pointer, str) or not is_well_formed(pointer):
        raise EvidencePlanError(f"{context}.assertion.pointer is invalid")
    if not isinstance(operator, str) or operator not in _OPERATORS:
        raise EvidencePlanError(f"{context}.assertion.operator is unsupported")
    if not isinstance(expected_declared, bool) or expected_declared is (operator == "exists"):
        raise EvidencePlanError(f"{context}.assertion expected declaration is inconsistent")
    if not expected_declared and assertion.get("expected") is not None:
        raise EvidencePlanError(f"{context}.assertion expected value is not allowed")


def _validate_binding(
    value: JsonValue | None,
    context: str,
    kind: EvidenceKind,
    payload: dict[str, JsonValue],
    obligation_id: str,
    evidence_id: str,
) -> None:
    binding = _closed_object(value, _BINDING_FIELDS, f"{context}.attestation_binding")
    if binding.get("allowed_statuses") != ["pass", "fail"]:
        raise EvidencePlanError(f"{context} attestation statuses are not closed")
    if binding.get("required_fields") != _attestation_fields(kind):
        raise EvidencePlanError(f"{context} attestation required fields are inconsistent")
    fixed = _closed_object(
        binding.get("fixed_values"),
        _FIXED_VALUE_FIELDS,
        f"{context}.attestation_binding.fixed_values",
    )
    expected = {
        "contract_id": payload["contract_id"],
        "contract_version": payload["contract_version"],
        "evidence_id": evidence_id,
        "manifest_sha256": payload["manifest_sha256"],
        "obligation_id": obligation_id,
        "schema_version": "obligation-receipts/attestation/v0.1",
    }
    if fixed != expected:
        raise EvidencePlanError(f"{context} attestation fixed values are inconsistent")


def _validate_evidence(
    value: JsonValue,
    context: str,
    classification: Classification,
    payload: dict[str, JsonValue],
    obligation_id: str,
    detail_mode: str,
) -> str:
    evidence = _closed_object(value, _EVIDENCE_FIELDS, context)
    evidence_id = _string(evidence, "id", context)
    evidence_path = evidence.get("path")
    if detail_mode == "portable_redacted":
        if evidence_path is not None:
            raise EvidencePlanError(f"{context}.path must be redacted in portable mode")
    else:
        requested_path = _string(evidence, "path", context)
        if not _safe_relative_path(requested_path):
            raise EvidencePlanError(f"{context}.path must remain inside the evidence root")
    kind = _enum(evidence, "kind", context, EvidenceKind)
    expected_kind = {
        Classification.AUTOMATED: EvidenceKind.JSON_ASSERTION,
        Classification.MANUAL_REVIEW: EvidenceKind.REVIEW_ATTESTATION,
        Classification.EXTERNAL_EVIDENCE: EvidenceKind.EXTERNAL_ATTESTATION,
    }[classification]
    if kind is not expected_kind:
        raise EvidencePlanError(f"{context}.kind does not match its classification")
    if kind is EvidenceKind.JSON_ASSERTION:
        _validate_assertion(evidence.get("assertion"), context)
        if evidence.get("attestation_binding") is not None:
            raise EvidencePlanError(f"{context} automated evidence cannot have a binding")
    else:
        if evidence.get("assertion") is not None:
            raise EvidencePlanError(f"{context} attestation evidence cannot have an assertion")
        _validate_binding(
            evidence.get("attestation_binding"),
            context,
            kind,
            payload,
            obligation_id,
            evidence_id,
        )
    return evidence_id


def _validate_obligation(
    raw: JsonValue,
    index: int,
    payload: dict[str, JsonValue],
    detail_mode: str,
) -> tuple[str, list[str]]:
    context = f"evidence plan obligations[{index}]"
    obligation = _closed_object(raw, _OBLIGATION_FIELDS, context)
    obligation_id = _string(obligation, "id", context)
    source_locator = obligation.get("source_locator")
    if detail_mode == "portable_redacted":
        if source_locator is not None:
            raise EvidencePlanError(f"{context}.source_locator must be redacted")
    else:
        _string(obligation, "source_locator", context)
    classification = _enum(obligation, "classification", context, Classification)
    expected_rule = (
        "not_applicable" if classification is Classification.UNVERIFIABLE else "all_required"
    )
    if obligation.get("combination_rule") != expected_rule:
        raise EvidencePlanError(f"{context}.combination_rule must be {expected_rule}")
    _enum(obligation, "criticality", context, Criticality)
    requirements = obligation.get("evidence_requirements")
    reason = obligation.get("no_evidence_reason")
    if not isinstance(requirements, list):
        raise EvidencePlanError(f"{context}.evidence_requirements must be an array")
    if classification is Classification.UNVERIFIABLE:
        expected_reason = (
            "no_evaluable_evidence_declared" if detail_mode == "portable_redacted" else None
        )
        invalid_reason = (
            reason != expected_reason
            if expected_reason is not None
            else not isinstance(reason, str) or not reason.strip()
        )
        if requirements or invalid_reason:
            raise EvidencePlanError(f"{context} unverifiable state is inconsistent")
        return obligation_id, []
    if not requirements or reason is not None:
        raise EvidencePlanError(f"{context} evidence requirements are inconsistent")
    evidence_ids = [
        _validate_evidence(
            item,
            f"{context}.evidence_requirements[{evidence_index}]",
            classification,
            payload,
            obligation_id,
            detail_mode,
        )
        for evidence_index, item in enumerate(requirements)
    ]
    return obligation_id, evidence_ids


def _validate_payload_header(payload: dict[str, JsonValue]) -> str:
    if payload.get("schema_version") != "obligation-receipts/evidence-plan/v0.1":
        raise EvidencePlanError("unsupported evidence plan payload schema")
    if payload.get("decision_scope") != "evidence_collection_checklist_only":
        raise EvidencePlanError("evidence plan overstates its decision scope")
    detail_mode = payload.get("detail_mode")
    if detail_mode not in {"portable_redacted", "local_sensitive"}:
        raise EvidencePlanError("evidence plan detail_mode is unsupported")
    if payload.get("evidence_observed") is not False:
        raise EvidencePlanError("evidence plan cannot claim evidence observation")
    limitations = _closed_object(
        payload.get("limitations"),
        _LIMITATION_FIELDS,
        "evidence plan limitations",
    )
    if limitations != _LIMITATIONS:
        raise EvidencePlanError("evidence plan limitations are inconsistent")
    for key in ("contract_id", "contract_version"):
        _string(payload, key, "evidence plan payload")
    for key in ("manifest_sha256", "source_sha256"):
        _digest(payload, key, "evidence plan payload")
    return detail_mode


def _validate_payload(value: JsonValue | None) -> dict[str, JsonValue]:
    payload = _closed_object(value, _PAYLOAD_FIELDS, "evidence plan payload")
    detail_mode = _validate_payload_header(payload)
    obligations = payload.get("obligations")
    count = payload.get("obligation_count")
    if not isinstance(obligations, list) or not obligations:
        raise EvidencePlanError("evidence plan obligations must be a non-empty array")
    if isinstance(count, bool) or not isinstance(count, int) or count != len(obligations):
        raise EvidencePlanError("evidence plan obligation_count is inconsistent")
    validated = [
        _validate_obligation(raw, index, payload, detail_mode)
        for index, raw in enumerate(obligations)
    ]
    obligation_ids = [item[0] for item in validated]
    evidence_ids = [evidence_id for item in validated for evidence_id in item[1]]
    if len(obligation_ids) != len(set(obligation_ids)):
        raise EvidencePlanError("evidence plan obligation ids must be unique")
    if len(evidence_ids) != len(set(evidence_ids)):
        raise EvidencePlanError("evidence plan evidence ids must be unique")
    return payload


def verify_evidence_plan(
    plan: dict[str, JsonValue],
    manifest: Manifest | None = None,
) -> str:
    """Verify self-consistency and, when supplied, exact manifest regeneration."""
    try:
        validate_json_value(plan)
    except StrictJsonError as exc:
        raise EvidencePlanError(f"evidence plan is not bounded JSON: {exc}") from exc
    document = _closed_object(plan, _DOCUMENT_FIELDS, "evidence plan")
    if document.get("schema_version") != "obligation-receipts/evidence-plan-document/v0.1":
        raise EvidencePlanError("unsupported evidence plan document schema")
    payload = _validate_payload(document.get("payload"))
    claimed = _digest(document, "payload_sha256", "evidence plan")
    actual = sha256_bytes(canonical_json_bytes(payload))
    if claimed != actual:
        raise EvidencePlanError("evidence plan payload digest mismatch")
    if manifest is not None:
        expected = build_evidence_plan(
            manifest,
            include_local_details=payload.get("detail_mode") == "local_sensitive",
        )
        if plan != expected:
            raise EvidencePlanError("evidence plan does not match exact manifest regeneration")
    return actual


def write_evidence_plan(path: Path, plan: dict[str, JsonValue]) -> None:
    """Validate and atomically write one bounded canonical evidence plan."""
    verify_evidence_plan(plan)
    encoded = canonical_json_bytes(plan) + b"\n"
    if len(encoded) > _MAX_PLAN_BYTES:
        raise EvidencePlanError("evidence plan exceeds the 2 MiB limit")
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


def load_evidence_plan(
    path: Path,
    manifest: Manifest | None = None,
) -> dict[str, JsonValue]:
    """Load one bounded strict-JSON evidence plan."""
    try:
        raw = loads_json_strict(read_regular_file(path, max_bytes=_MAX_PLAN_BYTES))
    except BoundedPathError as exc:
        raise EvidencePlanError(f"evidence plan cannot be read safely: {exc}") from exc
    except (JSONDecodeError, RecursionError, StrictJsonError) as exc:
        raise EvidencePlanError(f"evidence plan is not strict JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise EvidencePlanError("evidence plan must be a JSON object")
    verify_evidence_plan(raw, manifest)
    return raw
