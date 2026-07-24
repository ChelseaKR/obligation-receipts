"""Core immutable domain models."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import cast

type JsonValue = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]


class Classification(StrEnum):
    AUTOMATED = "automated"
    MANUAL_REVIEW = "manual_review"
    EXTERNAL_EVIDENCE = "external_evidence"
    UNVERIFIABLE = "unverifiable"


class Criticality(StrEnum):
    MUST = "must"
    SHOULD = "should"


class EvidenceKind(StrEnum):
    JSON_ASSERTION = "json_assertion"
    REVIEW_ATTESTATION = "review_attestation"
    EXTERNAL_ATTESTATION = "external_attestation"


class ResultStatus(StrEnum):
    PASS = "pass"  # noqa: S105 - evaluation state, not a credential
    FAIL = "fail"
    MISSING = "missing"
    REVIEW_REQUIRED = "review_required"
    UNVERIFIABLE = "unverifiable"


class OverallStatus(StrEnum):
    ACCEPTED = "accepted"
    ACCEPTED_WITH_FINDINGS = "accepted_with_findings"
    INCOMPLETE = "incomplete"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class Contract:
    contract_id: str
    title: str
    version: str
    authority: str
    effective_date: str
    source_path: str
    source_sha256: str

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "authority": self.authority,
            "effective_date": self.effective_date,
            "id": self.contract_id,
            "source_path": self.source_path,
            "source_sha256": self.source_sha256,
            "title": self.title,
            "version": self.version,
        }


@dataclass(frozen=True, slots=True)
class EvidenceSpec:
    evidence_id: str
    kind: EvidenceKind
    path: str
    pointer: str | None = None
    operator: str | None = None
    expected: JsonValue | None = None

    def to_dict(self) -> dict[str, JsonValue]:
        value: dict[str, JsonValue] = {
            "id": self.evidence_id,
            "kind": self.kind.value,
            "path": self.path,
        }
        if self.pointer is not None:
            value["pointer"] = self.pointer
        if self.operator is not None:
            value["operator"] = self.operator
        if self.expected is not None:
            value["expected"] = self.expected
        return value


@dataclass(frozen=True, slots=True)
class Obligation:
    obligation_id: str
    clause_ref: str
    text: str
    classification: Classification
    criticality: Criticality
    owner: str
    reason: str | None
    evidence: tuple[EvidenceSpec, ...]

    def to_dict(self) -> dict[str, JsonValue]:
        value: dict[str, JsonValue] = {
            "classification": self.classification.value,
            "clause_ref": self.clause_ref,
            "criticality": self.criticality.value,
            "evidence": [item.to_dict() for item in self.evidence],
            "id": self.obligation_id,
            "owner": self.owner,
            "text": self.text,
        }
        if self.reason is not None:
            value["reason"] = self.reason
        return value


@dataclass(frozen=True, slots=True)
class Manifest:
    contract: Contract
    obligations: tuple[Obligation, ...]
    manifest_path: str
    manifest_sha256: str

    def normalized_dict(self) -> dict[str, JsonValue]:
        return {
            "contract": self.contract.to_dict(),
            "obligations": [item.to_dict() for item in self.obligations],
            "schema_version": "obligation-receipts/manifest/v0.1",
        }


@dataclass(frozen=True, slots=True)
class EvidenceResult:
    evidence_id: str
    kind: EvidenceKind
    status: ResultStatus
    artifact_sha256: str | None
    detail: str

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "artifact_sha256": self.artifact_sha256,
            "detail": self.detail,
            "id": self.evidence_id,
            "kind": self.kind.value,
            "status": self.status.value,
        }


@dataclass(frozen=True, slots=True)
class ObligationResult:
    obligation_id: str
    clause_ref: str
    classification: Classification
    criticality: Criticality
    status: ResultStatus
    evidence: tuple[EvidenceResult, ...]

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "classification": self.classification.value,
            "clause_ref": self.clause_ref,
            "criticality": self.criticality.value,
            "evidence": [item.to_dict() for item in self.evidence],
            "id": self.obligation_id,
            "status": self.status.value,
        }


@dataclass(frozen=True, slots=True)
class Evaluation:
    contract: Contract
    manifest_sha256: str
    overall_status: OverallStatus
    results: tuple[ObligationResult, ...]

    def payload(self) -> dict[str, JsonValue]:
        counts = {status.value: 0 for status in ResultStatus}
        for item in self.results:
            counts[item.status.value] += 1
        return {
            "contract": self.contract.to_dict(),
            "decision_scope": "technical_evidence_evaluation_only",
            "manifest_sha256": self.manifest_sha256,
            "obligation_counts": cast(JsonValue, counts),
            "obligations": [item.to_dict() for item in self.results],
            "overall_status": self.overall_status.value,
            "schema_version": "obligation-receipts/evaluation/v0.1",
        }
