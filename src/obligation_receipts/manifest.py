"""Strict TOML manifest loading."""

from __future__ import annotations

import re
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from obligation_receipts.canonical import (
    StrictJsonError,
    canonical_json_bytes,
    sha256_bytes,
    validate_json_value,
)
from obligation_receipts.models import (
    Classification,
    Contract,
    Criticality,
    EvidenceKind,
    EvidenceSpec,
    JsonValue,
    Manifest,
    Obligation,
)
from obligation_receipts.paths import (
    BoundedPathError,
    hash_bounded_file,
    read_regular_file,
    validate_portable_relative_path,
)
from obligation_receipts.pointer import is_well_formed

_MAX_MANIFEST_BYTES = 2 * 1024 * 1024
_MAX_SOURCE_BYTES = 16 * 1024 * 1024
_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{1,79}$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_OPERATORS = {"eq", "ne", "gt", "gte", "lt", "lte", "exists"}
_ROOT_KEYS = {"contract", "obligations"}
_CONTRACT_KEYS = {
    "id",
    "title",
    "version",
    "authority",
    "effective_date",
    "source_path",
    "source_sha256",
}
_OBLIGATION_KEYS = {
    "id",
    "clause_ref",
    "text",
    "classification",
    "criticality",
    "owner",
    "reason",
    "evidence",
}
_EVIDENCE_KEYS = {"id", "kind", "path", "pointer", "operator", "expected"}


class ManifestError(ValueError):
    """Raised when a manifest is invalid or no longer bound to its source."""


def _mapping(value: object, context: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ManifestError(f"{context} must be a table")
    return cast(Mapping[str, object], value)


def _exact_keys(value: Mapping[str, object], allowed: set[str], context: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ManifestError(f"{context} has unknown field(s): {', '.join(unknown)}")


def _required_string(value: Mapping[str, object], key: str, context: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise ManifestError(f"{context}.{key} must be a non-empty string")
    return item.strip()


def _identifier(value: Mapping[str, object], key: str, context: str) -> str:
    item = _required_string(value, key, context)
    if not _ID_PATTERN.fullmatch(item):
        raise ManifestError(f"{context}.{key} must be a stable lowercase identifier")
    return item


def _parse_contract(raw: object, manifest_dir: Path) -> Contract:
    value = _mapping(raw, "contract")
    _exact_keys(value, _CONTRACT_KEYS, "contract")
    if set(value) != _CONTRACT_KEYS:
        missing = sorted(_CONTRACT_KEYS - set(value))
        raise ManifestError(f"contract is missing field(s): {', '.join(missing)}")
    source_sha256 = _required_string(value, "source_sha256", "contract")
    if not _SHA256_PATTERN.fullmatch(source_sha256):
        raise ManifestError("contract.source_sha256 must be a lowercase SHA-256 digest")
    source_path = _required_string(value, "source_path", "contract")
    try:
        validate_portable_relative_path(source_path)
        _, actual_hash = hash_bounded_file(
            manifest_dir,
            source_path,
            max_bytes=_MAX_SOURCE_BYTES,
        )
    except (BoundedPathError, FileNotFoundError) as exc:
        raise ManifestError(f"contract source cannot be opened: {exc}") from exc
    if actual_hash != source_sha256:
        raise ManifestError(
            "contract source digest does not match the approved manifest; "
            f"expected {source_sha256}, got {actual_hash}"
        )
    return Contract(
        contract_id=_identifier(value, "id", "contract"),
        title=_required_string(value, "title", "contract"),
        version=_required_string(value, "version", "contract"),
        authority=_required_string(value, "authority", "contract"),
        effective_date=_required_string(value, "effective_date", "contract"),
        source_path=source_path,
        source_sha256=source_sha256,
    )


def _evidence_path(value: Mapping[str, object], context: str) -> str:
    path = _required_string(value, "path", context)
    try:
        validate_portable_relative_path(path)
    except BoundedPathError as exc:
        raise ManifestError(f"{context}.path is unsafe: {exc}") from exc
    return path


def _parse_evidence(raw: object, context: str) -> EvidenceSpec:
    value = _mapping(raw, context)
    _exact_keys(value, _EVIDENCE_KEYS, context)
    try:
        kind = EvidenceKind(_required_string(value, "kind", context))
    except ValueError as exc:
        raise ManifestError(f"{context}.kind is not supported") from exc
    pointer = value.get("pointer")
    operator = value.get("operator")
    expected = value.get("expected")
    if kind is EvidenceKind.JSON_ASSERTION:
        if not isinstance(pointer, str) or not is_well_formed(pointer):
            # A malformed pointer is an authoring defect in the approved
            # manifest, not evidence content. Catching it here, where all three
            # commands load, keeps it an input error instead of letting the
            # evaluator turn it into a deterministic observed `fail`.
            raise ManifestError(f"{context}.pointer must be an RFC 6901 JSON pointer")
        if not isinstance(operator, str) or operator not in _OPERATORS:
            raise ManifestError(f"{context}.operator must be one of {sorted(_OPERATORS)}")
        if operator != "exists" and "expected" not in value:
            raise ManifestError(f"{context}.expected is required for operator {operator}")
        if operator == "exists" and "expected" in value:
            raise ManifestError(f"{context}.expected is not allowed for operator exists")
        if "expected" in value:
            try:
                expected = validate_json_value(expected)
            except StrictJsonError as exc:
                raise ManifestError(f"{context}.expected is not bounded JSON: {exc}") from exc
    elif any(key in value for key in ("pointer", "operator", "expected")):
        raise ManifestError(f"{context} attestation evidence cannot define an assertion")
    return EvidenceSpec(
        evidence_id=_identifier(value, "id", context),
        kind=kind,
        path=_evidence_path(value, context),
        pointer=cast(str | None, pointer),
        operator=cast(str | None, operator),
        expected=cast(JsonValue | None, expected),
    )


def _parse_obligation(raw: object, index: int) -> Obligation:
    context = f"obligations[{index}]"
    value = _mapping(raw, context)
    _exact_keys(value, _OBLIGATION_KEYS, context)
    try:
        classification = Classification(_required_string(value, "classification", context))
        criticality = Criticality(_required_string(value, "criticality", context))
    except ValueError as exc:
        raise ManifestError(f"{context} has an unsupported classification or criticality") from exc
    evidence_raw = value.get("evidence", [])
    if not isinstance(evidence_raw, list):
        raise ManifestError(f"{context}.evidence must be an array of tables")
    evidence = tuple(
        _parse_evidence(item, f"{context}.evidence[{evidence_index}]")
        for evidence_index, item in enumerate(evidence_raw)
    )
    expected_kind = {
        Classification.AUTOMATED: EvidenceKind.JSON_ASSERTION,
        Classification.MANUAL_REVIEW: EvidenceKind.REVIEW_ATTESTATION,
        Classification.EXTERNAL_EVIDENCE: EvidenceKind.EXTERNAL_ATTESTATION,
    }.get(classification)
    reason: str | None
    if classification is Classification.UNVERIFIABLE:
        if evidence:
            raise ManifestError(f"{context} unverifiable obligations cannot declare evidence")
        reason = _required_string(value, "reason", context)
    else:
        if not evidence:
            raise ManifestError(f"{context} must declare at least one evidence item")
        if any(item.kind is not expected_kind for item in evidence):
            raise ManifestError(f"{context} evidence kind does not match its classification")
        reason_value = value.get("reason")
        if reason_value is not None and (
            not isinstance(reason_value, str) or not reason_value.strip()
        ):
            raise ManifestError(f"{context}.reason must be a non-empty string when present")
        reason = reason_value
    return Obligation(
        obligation_id=_identifier(value, "id", context),
        clause_ref=_required_string(value, "clause_ref", context),
        text=_required_string(value, "text", context),
        classification=classification,
        criticality=criticality,
        owner=_required_string(value, "owner", context),
        reason=reason,
        evidence=evidence,
    )


def load_manifest(path: Path) -> Manifest:
    """Load, validate, source-bind, normalize, and hash a manifest."""
    resolved_path = path.resolve(strict=True)
    try:
        manifest_bytes = read_regular_file(
            resolved_path,
            max_bytes=_MAX_MANIFEST_BYTES,
            no_follow=True,
        )
        raw = tomllib.loads(manifest_bytes.decode("utf-8"))
    except BoundedPathError as exc:
        if "exceeds" in str(exc):
            raise ManifestError("manifest exceeds the 2 MiB limit") from exc
        raise ManifestError(f"manifest cannot be read safely: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise ManifestError("manifest is not valid UTF-8") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ManifestError(f"manifest is not valid TOML: {exc}") from exc
    _exact_keys(raw, _ROOT_KEYS, "manifest")
    contract = _parse_contract(raw.get("contract"), resolved_path.parent)
    obligations_raw = raw.get("obligations")
    if not isinstance(obligations_raw, list) or not obligations_raw:
        raise ManifestError("manifest.obligations must be a non-empty array of tables")
    obligations = tuple(
        _parse_obligation(item, index) for index, item in enumerate(obligations_raw)
    )
    ids = [item.obligation_id for item in obligations]
    if len(ids) != len(set(ids)):
        raise ManifestError("obligation ids must be unique")
    evidence_ids = [item.evidence_id for obligation in obligations for item in obligation.evidence]
    if len(evidence_ids) != len(set(evidence_ids)):
        raise ManifestError("evidence ids must be unique across the manifest")
    normalized = {
        "contract": contract.to_dict(),
        "obligations": [item.to_dict() for item in obligations],
        "schema_version": "obligation-receipts/manifest/v0.1",
    }
    return Manifest(
        contract=contract,
        obligations=obligations,
        manifest_path=str(resolved_path),
        manifest_sha256=sha256_bytes(canonical_json_bytes(normalized)),
    )
