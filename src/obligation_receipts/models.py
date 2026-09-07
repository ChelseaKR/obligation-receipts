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


#: The closed assertion vocabulary, in one place.
#:
#: It was two places -- a `_OPERATORS` literal in `manifest.py` and an identical
#: one in `plan.py` -- with a third, implicit copy in `evaluator._compare`'s
#: if-chain, and nothing compared any of them. The failure that allows is not a
#: crash. Measured on this tree: adding one operator to `manifest._OPERATORS`
#: and to the example manifest produced `overall_status: rejected` and an
#: evidence result of `fail`, detail "assertion /summary/critical_violations
#: matches did not pass" -- because `_compare` returned `False` for an operator
#: it did not recognise. The supplier is told their evidence failed, in a
#: receipt, when nothing was evaluated at all.
#:
#: `evaluator.IMPLEMENTED_OPERATORS` is derived from the dispatch that actually
#: answers each one, and `tests/test_misuse_boundaries.py` asserts the two sets
#: are equal, so a vocabulary entry with no implementation is a failing test
#: rather than a rejection sent to a counterparty.
#: The set operators, the range operator, the length operator and the type
#: operator were added under #64. They keep the flat
#: pointer/operator/expected shape the plan, the single-evidence check and the
#: receipt already carry, so none of those documents needed a new field: the
#: whole extension lives in what `expected` is allowed to be, per operator, and
#: `_EXPECTED_SHAPES` in `manifest.py` is where that is enforced.
ASSERTION_OPERATORS = frozenset(
    {
        "eq",
        "ne",
        "gt",
        "gte",
        "lt",
        "lte",
        "exists",
        "in",
        "not_in",
        "between",
        "length",
        "type",
    }
)

#: The JSON type names `type` may assert, which are the seven RFC 8259 types
#: with `integer` deliberately absent. JSON has one number type; a manifest
#: that could say `integer` would be asserting something the format does not
#: distinguish, and `1.0` would then be a `fail` against a supplier for a
#: difference no JSON parser preserves.
JSON_TYPE_NAMES = frozenset({"null", "boolean", "number", "string", "array", "object"})

#: The comparisons `length` may carry. `exists` is excluded: a length that
#: exists is a tautology, and the set operators are excluded because a length
#: is a single number and `in` over lengths is expressible as `eq`.
LENGTH_COMPARISONS = frozenset({"eq", "ne", "gt", "gte", "lt", "lte"})


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
class SourceSpan:
    """Where in the approved source an obligation's quotation is, byte-exact.

    `offset` and `length` are byte positions into the contract source the
    manifest is already bound to by digest, and `sha256` is taken over exactly
    those bytes. The loader checks all three, and checks that the obligation's
    `text` is those bytes with **no normalization at all** -- see
    `docs/decisions/0002-obligation-text-is-verbatim-source-bytes.md`.

    A span is a locator into the source, so `plan.py`'s `portable_redacted`
    profile omits it exactly as it omits `clause_ref`.
    """

    offset: int
    length: int
    sha256: str

    def to_dict(self) -> dict[str, JsonValue]:
        return {"length": self.length, "offset": self.offset, "sha256": self.sha256}


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
    #: Optional at manifest schema v0.1 so that every manifest written before
    #: spans existed normalizes, hashes, and evaluates to exactly what it did
    #: before. The key is emitted only when one is declared, so an absent span
    #: is absent from the normalized document rather than present as a null --
    #: which is what keeps `manifest_sha256` stable for those manifests.
    source_span: SourceSpan | None = None

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
        if self.source_span is not None:
            value["source_span"] = self.source_span.to_dict()
        return value


@dataclass(frozen=True, slots=True)
class Manifest:
    contract: Contract
    obligations: tuple[Obligation, ...]
    manifest_path: str
    manifest_sha256: str

    @property
    def source_spans_declared(self) -> int:
        """How many obligations bind their text to a span of the approved source.

        Reported rather than inferred. Zero declared spans and a manifest whose
        spans were never checked are different states, and a caller that only
        ever saw "no span errors" cannot tell them apart.
        """
        return sum(1 for item in self.obligations if item.source_span is not None)

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
    source_span: SourceSpan | None = None

    def to_dict(self) -> dict[str, JsonValue]:
        value: dict[str, JsonValue] = {
            "classification": self.classification.value,
            "clause_ref": self.clause_ref,
            "criticality": self.criticality.value,
            "evidence": [item.to_dict() for item in self.evidence],
            "id": self.obligation_id,
            "status": self.status.value,
        }
        if self.source_span is not None:
            value["source_span"] = self.source_span.to_dict()
        return value


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
