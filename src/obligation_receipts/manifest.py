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
    ASSERTION_OPERATORS,
    Classification,
    Contract,
    Criticality,
    EvidenceKind,
    EvidenceSpec,
    JsonValue,
    Manifest,
    Obligation,
    SourceSpan,
)
from obligation_receipts.paths import (
    BoundedPathError,
    hash_bounded_file,
    read_bounded_file,
    read_regular_file,
    validate_portable_relative_path,
)
from obligation_receipts.pointer import is_well_formed

_MAX_MANIFEST_BYTES = 2 * 1024 * 1024
_MAX_SOURCE_BYTES = 16 * 1024 * 1024
_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{1,79}$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
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
    "source_span",
}
_EVIDENCE_KEYS = {"id", "kind", "path", "pointer", "operator", "expected"}
_SPAN_KEYS = {"offset", "length", "sha256"}


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


def _parse_contract(
    raw: object, manifest_dir: Path, *, read_source: bool
) -> tuple[Contract, bytes]:
    """Validate the contract block and bind it to its source.

    ``read_source`` is set only when at least one obligation declares a
    ``source_span``, because that is the only case where the source's *content*
    is needed rather than its digest. Without a span the source is still hashed
    a 64 KiB chunk at a time by ``hash_bounded_file``, so a 16 MiB contract PDF
    never enters memory for a manifest that quotes nothing from it. The two
    paths compute the same digest over the same bytes; only the buffering
    differs. Both raise through the one ``except`` below, so a source that
    cannot be read safely is a ``ManifestError`` either way.
    """
    value = _mapping(raw, "contract")
    _exact_keys(value, _CONTRACT_KEYS, "contract")
    if set(value) != _CONTRACT_KEYS:
        missing = sorted(_CONTRACT_KEYS - set(value))
        raise ManifestError(f"contract is missing field(s): {', '.join(missing)}")
    source_sha256 = _required_string(value, "source_sha256", "contract")
    if not _SHA256_PATTERN.fullmatch(source_sha256):
        raise ManifestError("contract.source_sha256 must be a lowercase SHA-256 digest")
    source_path = _required_string(value, "source_path", "contract")
    source_bytes = b""
    try:
        validate_portable_relative_path(source_path)
        if read_source:
            _, source_bytes = read_bounded_file(
                manifest_dir,
                source_path,
                max_bytes=_MAX_SOURCE_BYTES,
            )
            actual_hash = sha256_bytes(source_bytes)
        else:
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
    contract = Contract(
        contract_id=_identifier(value, "id", "contract"),
        title=_required_string(value, "title", "contract"),
        version=_required_string(value, "version", "contract"),
        authority=_required_string(value, "authority", "contract"),
        effective_date=_required_string(value, "effective_date", "contract"),
        source_path=source_path,
        source_sha256=source_sha256,
    )
    return contract, source_bytes


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
        if not isinstance(operator, str) or operator not in ASSERTION_OPERATORS:
            raise ManifestError(f"{context}.operator must be one of {sorted(ASSERTION_OPERATORS)}")
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


def _byte_count(value: Mapping[str, object], key: str, context: str) -> int:
    item = value.get(key)
    # `isinstance(True, int)` is True, and TOML has a boolean type, so
    # `offset = true` would otherwise be accepted as offset 1.
    if isinstance(item, bool) or not isinstance(item, int) or item < 0:
        raise ManifestError(f"{context}.{key} must be a non-negative integer byte count")
    return item


def _parse_source_span(value: Mapping[str, object], context: str) -> SourceSpan | None:
    raw = value.get("source_span")
    if raw is None:
        return None
    span_context = f"{context}.source_span"
    span = _mapping(raw, span_context)
    _exact_keys(span, _SPAN_KEYS, span_context)
    missing = sorted(_SPAN_KEYS - set(span))
    if missing:
        raise ManifestError(f"{span_context} is missing field(s): {', '.join(missing)}")
    offset = _byte_count(span, "offset", span_context)
    length = _byte_count(span, "length", span_context)
    if length == 0:
        raise ManifestError(f"{span_context}.length must quote at least one byte")
    digest = _required_string(span, "sha256", span_context)
    if not _SHA256_PATTERN.fullmatch(digest):
        raise ManifestError(f"{span_context}.sha256 must be a lowercase SHA-256 digest")
    return SourceSpan(offset=offset, length=length, sha256=digest)


def _bind_source_spans(obligations: tuple[Obligation, ...], source_bytes: bytes) -> None:
    """Check every declared span against the source the manifest is bound to.

    Every failure here is a defect in the *approved manifest* -- a quotation
    that is not in the document it claims to come from -- so every one is a
    `ManifestError` raised before anything is evaluated, never an observed
    `fail` in a receipt. That is the same line `pointer.is_well_formed` draws.
    """
    for index, obligation in enumerate(obligations):
        span = obligation.source_span
        if span is None:
            continue
        context = f"obligations[{index}] ({obligation.obligation_id})"
        end = span.offset + span.length
        if end > len(source_bytes):
            raise ManifestError(
                f"{context} source_span runs past the end of the contract source: "
                f"bytes {span.offset}..{end} of {len(source_bytes)}"
            )
        quoted = source_bytes[span.offset : end]
        actual_digest = sha256_bytes(quoted)
        if actual_digest != span.sha256:
            raise ManifestError(
                f"{context} source_span digest does not match the bytes it points at; "
                f"expected {span.sha256}, got {actual_digest}"
            )
        if quoted != obligation.text.encode("utf-8"):
            raise ManifestError(
                f"{context} text is not the bytes at its declared source_span; "
                "the quotation is compared to the source verbatim and no "
                "normalization is applied"
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
        source_span=_parse_source_span(value, context),
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
    obligations_raw = raw.get("obligations")
    # Read ahead for span declarations before the contract is bound, so that
    # `_parse_contract` knows whether the source's bytes are needed or only its
    # digest. This is a structural peek at unvalidated input and asserts
    # nothing: a `source_span` that is not a table, or is missing a field, is
    # still refused by `_parse_source_span` with its own message.
    spans_declared = isinstance(obligations_raw, list) and any(
        isinstance(item, Mapping) and item.get("source_span") is not None
        for item in obligations_raw
    )
    contract, source_bytes = _parse_contract(
        raw.get("contract"),
        resolved_path.parent,
        read_source=spans_declared,
    )
    if not isinstance(obligations_raw, list) or not obligations_raw:
        raise ManifestError("manifest.obligations must be a non-empty array of tables")
    obligations = tuple(
        _parse_obligation(item, index) for index, item in enumerate(obligations_raw)
    )
    _bind_source_spans(obligations, source_bytes)
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
