"""Deterministic obligation evaluation."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from obligation_receipts.canonical import (
    MAX_JSON_NODES,
    StrictJsonError,
    loads_json_strict,
    sha256_bytes,
)
from obligation_receipts.models import (
    Classification,
    Criticality,
    Evaluation,
    EvidenceKind,
    EvidenceResult,
    EvidenceSpec,
    JsonValue,
    Manifest,
    Obligation,
    ObligationResult,
    OverallStatus,
    ResultStatus,
)
from obligation_receipts.paths import BoundedPathError, read_bounded_file

_MAX_ARTIFACT_BYTES = 2 * 1024 * 1024


def _read_json_artifact(root: Path, relative_path: str) -> tuple[bytes, str]:
    _, data = read_bounded_file(root, relative_path, max_bytes=_MAX_ARTIFACT_BYTES)
    return data, sha256_bytes(data)


def _load_json_artifact(root: Path, relative_path: str) -> tuple[JsonValue, str]:
    data, digest = _read_json_artifact(root, relative_path)
    return loads_json_strict(data), digest


def _decode_pointer_token(segment: str) -> str | None:
    decoded: list[str] = []
    index = 0
    while index < len(segment):
        character = segment[index]
        if character != "~":
            decoded.append(character)
            index += 1
            continue
        if index + 1 >= len(segment) or segment[index + 1] not in {"0", "1"}:
            return None
        decoded.append("~" if segment[index + 1] == "0" else "/")
        index += 2
    return "".join(decoded)


def _canonical_array_index(segment: str) -> int | None:
    if segment == "0":
        return 0
    if not segment or segment[0] not in "123456789":
        return None
    if any(character not in "0123456789" for character in segment[1:]):
        return None
    if len(segment) > len(str(MAX_JSON_NODES)):
        return None
    return int(segment)


def _json_pointer(document: JsonValue, pointer: str) -> tuple[bool, JsonValue | None]:
    current: JsonValue = document
    if pointer == "":
        return True, current
    if not pointer.startswith("/"):
        return False, None
    for token in pointer.removeprefix("/").split("/"):
        key = _decode_pointer_token(token)
        if key is None:
            return False, None
        if isinstance(current, dict):
            if key not in current:
                return False, None
            current = current[key]
        elif isinstance(current, list):
            index = _canonical_array_index(key)
            if index is None or index >= len(current):
                return False, None
            current = current[index]
        else:
            return False, None
    return True, current


def _compare(actual: JsonValue | None, operator: str, expected: JsonValue | None) -> bool:
    if operator == "exists":
        return actual is not None
    if isinstance(actual, bool) or isinstance(expected, bool):
        equal = isinstance(actual, bool) and isinstance(expected, bool) and actual is expected
        return equal if operator == "eq" else not equal if operator == "ne" else False
    if operator == "eq":
        return actual == expected
    if operator == "ne":
        return actual != expected
    if not isinstance(actual, int | float) or not isinstance(expected, int | float):
        return False
    if operator == "gt":
        return actual > expected
    if operator == "gte":
        return actual >= expected
    if operator == "lt":
        return actual < expected
    if operator == "lte":
        return actual <= expected
    return False


def _evaluate_assertion(spec: EvidenceSpec, evidence_root: Path) -> EvidenceResult:
    try:
        data, artifact_sha256 = _read_json_artifact(evidence_root, spec.path)
    except (
        BoundedPathError,
        FileNotFoundError,
        OSError,
    ) as exc:
        return EvidenceResult(
            evidence_id=spec.evidence_id,
            kind=spec.kind,
            status=ResultStatus.MISSING,
            artifact_sha256=None,
            detail=f"artifact unavailable or invalid: {type(exc).__name__}",
        )
    try:
        document = loads_json_strict(data)
    except (RecursionError, StrictJsonError, ValueError) as exc:
        return EvidenceResult(
            evidence_id=spec.evidence_id,
            kind=spec.kind,
            status=ResultStatus.MISSING,
            artifact_sha256=artifact_sha256,
            detail=f"artifact unavailable or invalid: {type(exc).__name__}",
        )
    if spec.pointer is None or spec.operator is None:
        return EvidenceResult(
            evidence_id=spec.evidence_id,
            kind=spec.kind,
            status=ResultStatus.MISSING,
            artifact_sha256=artifact_sha256,
            detail="validated assertion is missing its pointer or operator",
        )
    found, actual = _json_pointer(document, spec.pointer)
    passed = (
        found
        if spec.operator == "exists"
        else found and _compare(actual, spec.operator, spec.expected)
    )
    return EvidenceResult(
        evidence_id=spec.evidence_id,
        kind=spec.kind,
        status=ResultStatus.PASS if passed else ResultStatus.FAIL,
        artifact_sha256=artifact_sha256,
        detail=(
            f"assertion {spec.pointer} {spec.operator} passed"
            if passed
            else f"assertion {spec.pointer} {spec.operator} did not pass"
        ),
    )


def _attestation_fields(kind: EvidenceKind) -> tuple[str, ...]:
    common = (
        "schema_version",
        "contract_id",
        "contract_version",
        "manifest_sha256",
        "obligation_id",
        "evidence_id",
        "status",
    )
    if kind is EvidenceKind.REVIEW_ATTESTATION:
        return (*common, "reviewer", "reviewed_at", "method")
    return (*common, "issuer", "observed_at", "source_uri")


def _evaluate_attestation(
    spec: EvidenceSpec,
    obligation: Obligation,
    manifest: Manifest,
    evidence_root: Path,
) -> EvidenceResult:
    try:
        data, artifact_sha256 = _read_json_artifact(evidence_root, spec.path)
    except (
        BoundedPathError,
        FileNotFoundError,
        OSError,
    ) as exc:
        return EvidenceResult(
            evidence_id=spec.evidence_id,
            kind=spec.kind,
            status=ResultStatus.REVIEW_REQUIRED,
            artifact_sha256=None,
            detail=f"attestation unavailable or invalid: {type(exc).__name__}",
        )
    try:
        raw = loads_json_strict(data)
    except (RecursionError, StrictJsonError, ValueError) as exc:
        return EvidenceResult(
            evidence_id=spec.evidence_id,
            kind=spec.kind,
            status=ResultStatus.REVIEW_REQUIRED,
            artifact_sha256=artifact_sha256,
            detail=f"attestation unavailable or invalid: {type(exc).__name__}",
        )
    attestation = raw if isinstance(raw, dict) else None
    if attestation is None:
        valid = False
    else:
        required = _attestation_fields(spec.kind)
        valid = set(attestation) == set(required)
        valid = valid and all(
            isinstance(attestation.get(field), str) and bool(cast(str, attestation[field]).strip())
            for field in required
        )
        valid = valid and attestation.get("contract_id") == manifest.contract.contract_id
        valid = valid and attestation.get("contract_version") == manifest.contract.version
        valid = valid and attestation.get("manifest_sha256") == manifest.manifest_sha256
        valid = valid and attestation.get("obligation_id") == obligation.obligation_id
        valid = valid and attestation.get("evidence_id") == spec.evidence_id
        valid = (
            valid and attestation.get("schema_version") == "obligation-receipts/attestation/v0.1"
        )
        valid = valid and attestation.get("status") in {"pass", "fail"}
    if not valid:
        return EvidenceResult(
            evidence_id=spec.evidence_id,
            kind=spec.kind,
            status=ResultStatus.REVIEW_REQUIRED,
            artifact_sha256=artifact_sha256,
            detail="attestation is incomplete or is not bound to this manifest",
        )
    bound_attestation = cast(dict[str, JsonValue], attestation)
    status = ResultStatus.PASS if bound_attestation.get("status") == "pass" else ResultStatus.FAIL
    return EvidenceResult(
        evidence_id=spec.evidence_id,
        kind=spec.kind,
        status=status,
        artifact_sha256=artifact_sha256,
        detail="content-bound attestation accepted",
    )


def evaluate_declared_evidence(
    manifest: Manifest,
    obligation: Obligation,
    spec: EvidenceSpec,
    evidence_root: Path,
) -> EvidenceResult:
    """Evaluate exactly one already-declared evidence item."""
    resolved_root = evidence_root.resolve(strict=True)
    if spec.kind is EvidenceKind.JSON_ASSERTION:
        return _evaluate_assertion(spec, resolved_root)
    return _evaluate_attestation(spec, obligation, manifest, resolved_root)


def _combine_evidence(results: tuple[EvidenceResult, ...]) -> ResultStatus:
    statuses = {item.status for item in results}
    if ResultStatus.FAIL in statuses:
        return ResultStatus.FAIL
    if ResultStatus.MISSING in statuses:
        return ResultStatus.MISSING
    if ResultStatus.REVIEW_REQUIRED in statuses:
        return ResultStatus.REVIEW_REQUIRED
    return ResultStatus.PASS


def _evaluate_obligation(
    obligation: Obligation, manifest: Manifest, evidence_root: Path
) -> ObligationResult:
    if obligation.classification is Classification.UNVERIFIABLE:
        return ObligationResult(
            obligation_id=obligation.obligation_id,
            clause_ref=obligation.clause_ref,
            classification=obligation.classification,
            criticality=obligation.criticality,
            status=ResultStatus.UNVERIFIABLE,
            evidence=(),
        )
    if obligation.classification is Classification.AUTOMATED:
        evidence = tuple(_evaluate_assertion(spec, evidence_root) for spec in obligation.evidence)
    else:
        evidence = tuple(
            _evaluate_attestation(spec, obligation, manifest, evidence_root)
            for spec in obligation.evidence
        )
    return ObligationResult(
        obligation_id=obligation.obligation_id,
        clause_ref=obligation.clause_ref,
        classification=obligation.classification,
        criticality=obligation.criticality,
        status=_combine_evidence(evidence),
        evidence=evidence,
    )


def _overall_status(results: tuple[ObligationResult, ...]) -> OverallStatus:
    must_statuses = {item.status for item in results if item.criticality is Criticality.MUST}
    if ResultStatus.FAIL in must_statuses:
        return OverallStatus.REJECTED
    if must_statuses - {ResultStatus.PASS}:
        return OverallStatus.INCOMPLETE
    if any(item.status is not ResultStatus.PASS for item in results):
        return OverallStatus.ACCEPTED_WITH_FINDINGS
    return OverallStatus.ACCEPTED


def evaluate_manifest(manifest: Manifest, evidence_root: Path) -> Evaluation:
    """Evaluate every obligation without network access or arbitrary execution."""
    resolved_root = evidence_root.resolve(strict=True)
    results = tuple(
        _evaluate_obligation(obligation, manifest, resolved_root)
        for obligation in manifest.obligations
    )
    return Evaluation(
        contract=manifest.contract,
        manifest_sha256=manifest.manifest_sha256,
        overall_status=_overall_status(results),
        results=results,
    )
