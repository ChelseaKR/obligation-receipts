"""Deterministic obligation evaluation."""

from __future__ import annotations

import operator as operator_module
from collections.abc import Callable
from pathlib import Path
from typing import cast

from obligation_receipts.canonical import (
    StrictJsonError,
    loads_json_strict,
    sha256_bytes,
)
from obligation_receipts.manifest import ManifestError
from obligation_receipts.models import (
    Assertion,
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
from obligation_receipts.paths import (
    BoundedPathError,
    read_bounded_file,
    resolve_evidence_root,
)
from obligation_receipts.pointer import resolve

_MAX_ARTIFACT_BYTES = 2 * 1024 * 1024


def _read_json_artifact(root: Path, relative_path: str) -> tuple[bytes, str]:
    _, data = read_bounded_file(root, relative_path, max_bytes=_MAX_ARTIFACT_BYTES)
    return data, sha256_bytes(data)


def _load_json_artifact(root: Path, relative_path: str) -> tuple[JsonValue, str]:
    data, digest = _read_json_artifact(root, relative_path)
    return loads_json_strict(data), digest


#: Ordering comparisons, by name, over two numbers.
#:
#: A dict rather than an if-chain so the set of operators this module can
#: actually answer is a value the test suite can read. As an if-chain the
#: implemented set existed only in control flow, and the trailing `return False`
#: meant an operator nobody had implemented was answered "did not pass".
_ORDERING: dict[str, Callable[[float, float], bool]] = {
    "gt": operator_module.gt,
    "gte": operator_module.ge,
    "lt": operator_module.lt,
    "lte": operator_module.le,
}

_EQUALITY = frozenset({"eq", "ne"})

#: Membership in a literal set declared by the manifest.
_SET_MEMBERSHIP = frozenset({"in", "not_in"})

#: Operators whose answer is computed from the resolved value's *shape* rather
#: than from an ordering over it.
_SHAPE = frozenset({"between", "length", "type"})

#: How the branches of a composition combine, as an ordered precedence: the
#: first status any branch holds is the composition's answer.
#:
#: A dict keyed by operator rather than a conditional, for the reason
#: `_ORDERING` is one: a third composing operator added to the vocabulary and
#: not to this table is a `KeyError` in a test run rather than a silent
#: inheritance of `any_of`'s rule, and `IMPLEMENTED_OPERATORS` is derived from
#: the keys, so it cannot be added to the vocabulary without a rule at all.
#:
#: `all_of`'s order is `_combine_evidence`'s order restricted to the three
#: statuses a `json_assertion` branch can hold, and that is not a coincidence:
#: `all_of` is the within-artifact form of the `all_required` rule the evidence
#: plan already declares over an obligation's evidence items, so the two must
#: agree about a fail beside a missing. `any_of`'s is its dual, which makes the
#: pair Kleene three-valued logic with `missing` as the unknown.
#:
#: The consequence worth stating: `any_of` over branches that were all
#: unmeasurable is `missing`, never `fail`. Folding an unmeasured branch into
#: `false` is how a composition would report an absence as an observed failure
#: against a supplier, or -- with the sense reversed -- absorb one into a pass.
_COMBINATION: dict[str, tuple[ResultStatus, ...]] = {
    "all_of": (ResultStatus.FAIL, ResultStatus.MISSING, ResultStatus.PASS),
    "any_of": (ResultStatus.PASS, ResultStatus.MISSING, ResultStatus.FAIL),
}

#: Every operator this build can answer. `exists` is included because
#: `_evaluate_assertion` answers it from the pointer's found flag, one level up
#: -- it is implemented, just not here. The composing operators are included
#: because `_combine_branches` answers them from their branches' three-valued
#: statuses, where `_compare` returns a boolean.
#:
#: Derived from the sets that dispatch, never typed out again, so an operator
#: can only appear here by having somewhere to go.
#:
#: `tests/test_misuse_boundaries.py` asserts this equals
#: `models.ASSERTION_OPERATORS`, the vocabulary the manifest loader and the
#: evidence plan accept. The two drifting apart is not a crash: it is a
#: `fail` in a receipt, against a supplier, for an assertion that was never
#: evaluated.
IMPLEMENTED_OPERATORS = frozenset(
    _EQUALITY | set(_ORDERING) | _SET_MEMBERSHIP | _SHAPE | set(_COMBINATION) | {"exists"}
)


def _json_type_name(value: JsonValue | None) -> str:
    """The RFC 8259 type of a resolved value, in the same names `type` accepts.

    Booleans are tested before numbers, because `isinstance(True, int)` is True
    and reporting `true` as a `number` would let `type` pass on a value the
    manifest author would not call one.
    """
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int | float):
        return "number"
    if isinstance(value, str):
        return "string"
    return "array" if isinstance(value, list) else "object"


def _same_json_value(left: JsonValue | None, right: JsonValue | None) -> bool:
    """Equality for set membership, with `true` and `1` held apart.

    `1 == True` in Python, so a plain `in` would let `expected = [1]` match a
    resolved `true`. JSON does not consider those the same value and neither
    may a receipt: reporting a boolean as a member of a numeric set is an
    observed `pass` for a comparison nobody wrote.
    """
    if isinstance(left, bool) or isinstance(right, bool):
        return isinstance(left, bool) and isinstance(right, bool) and left is right
    return bool(left == right)


class UnsupportedOperatorError(ManifestError):
    """The manifest declared an operator this build cannot evaluate.

    A disagreement between the accepted vocabulary and the implemented one, not
    a defect in the manifest -- the loader accepted it. It is raised rather than
    answered, so it reaches the CLI's error boundary and exits `INPUT_ERROR`,
    which the contract reserves for "no result document". The alternative, and
    what this code did before, is to return `False`: the assertion is recorded
    as an observed `fail` and the deliverable is `rejected`, on the strength of
    a comparison that never happened.
    """


#: Operators that are implemented, and not by this comparator.
#:
#: `exists` is answered from the pointer's found flag and a composition from its
#: branches' statuses, both one level up, because both answers need something a
#: boolean cannot carry: `exists` needs to tell an absent member from one whose
#: value is JSON `null`, and a composition needs a third value for "not
#: measured". Reaching `_compare` with one of these is a wiring defect, so it
#: raises rather than falling through to a comparison that would answer `False`
#: against an `expected` that was never declared.
_ANSWERED_ELSEWHERE = frozenset({"exists"}) | set(_COMBINATION)


def _compare(actual: JsonValue | None, operator: str, expected: JsonValue | None) -> bool:
    """Compare a resolved value. `exists` and the compositions never reach here.

    `_evaluate_assertion` answers `exists` from the pointer's found flag, one
    level up. This function once carried its own `exists` branch that answered
    `actual is not None`, which was unreachable through that only caller and
    disagreed with it: a member whose value is JSON `null` exists. It was
    removed rather than tested, because keeping two definitions of `exists` and
    exercising the unreachable one would have preserved the disagreement.

    Every `return False` below is a real answer -- an ordering comparison
    against a boolean or a string did not pass -- and every one of them is
    reached only for an operator this module implements. An operator it does
    not implement raises.
    """
    if operator not in IMPLEMENTED_OPERATORS or operator in _ANSWERED_ELSEWHERE:
        raise UnsupportedOperatorError(
            f"operator {operator!r} has no implementation in this comparator; "
            "no evaluation was made"
        )
    if operator in _SET_MEMBERSHIP or operator in _SHAPE:
        return _compare_extended(actual, operator, expected)
    if isinstance(actual, bool) or isinstance(expected, bool):
        equal = isinstance(actual, bool) and isinstance(expected, bool) and actual is expected
        return equal if operator == "eq" else not equal if operator == "ne" else False
    if operator == "eq":
        return actual == expected
    if operator == "ne":
        return actual != expected
    if not isinstance(actual, int | float) or not isinstance(expected, int | float):
        return False
    return _ORDERING[operator](actual, expected)


def _compare_extended(actual: JsonValue | None, operator: str, expected: JsonValue | None) -> bool:
    """The set and shape operators added under #64.

    Split from `_compare` rather than inlined so that the equality/ordering path
    -- which every manifest written before this vocabulary existed uses -- keeps
    exactly the shape it had, and so neither half grows past the complexity the
    linter allows. Reached only for an operator in `_SET_MEMBERSHIP | _SHAPE`.

    Every `return False` here is a real answer about a value of the wrong type,
    never a stand-in for "could not compare": the manifest loader has already
    refused an `expected` this function could not use, so a shape it cannot
    handle is a fact about the *evidence*, which is what a receipt reports.
    """
    if operator in _SET_MEMBERSHIP:
        # `expected` is a non-empty array: the manifest loader refuses anything
        # else, so this cannot silently answer `False` against a scalar.
        members = expected if isinstance(expected, list) else []
        present = any(_same_json_value(actual, member) for member in members)
        return present if operator == "in" else not present
    if operator == "between":
        # Inclusive on both ends, and numbers only. A string between two numbers
        # is `False` -- a real answer about a value of the wrong type -- and the
        # bounds themselves are guaranteed numeric and ordered by the loader.
        if isinstance(actual, bool) or not isinstance(actual, int | float):
            return False
        low, high = cast("list[float]", expected)
        return low <= actual <= high
    if operator == "length":
        return _compare_length(actual, expected)
    return _json_type_name(actual) == expected


def _compare_length(actual: JsonValue | None, expected: JsonValue | None) -> bool:
    """Length of an array, a string, or an object's member count.

    A value with no length -- a number, a boolean, `null` -- is `False` rather
    than length zero. Treating "this has no length" as "its length is 0" would
    let `length lte 0` pass against a number, which is the absence-rendered-as-a
    -value error in miniature: a missing measurement published as a real one.
    """
    if isinstance(actual, bool) or not isinstance(actual, str | list | dict):
        return False
    comparison = cast("dict[str, JsonValue]", expected)
    wanted = cast(int, comparison["value"])
    name = cast(str, comparison["operator"])
    measured = len(actual)
    if name == "eq":
        return measured == wanted
    if name == "ne":
        return measured != wanted
    return _ORDERING[name](measured, wanted)


def _combine_branches(operator: str, statuses: tuple[ResultStatus, ...]) -> ResultStatus:
    """The composition's answer, as the first precedence entry any branch holds.

    `statuses` is never empty: the manifest loader refuses a composition with
    fewer than `MIN_COMPOSITION_BRANCHES` branches, so the generator always
    finds a member and this cannot fall through to a default that would have to
    invent one.
    """
    held = set(statuses)
    return next(status for status in _COMBINATION[operator] if status in held)


def _branch_statuses(
    container: JsonValue | None,
    container_found: bool,
    branches: tuple[Assertion, ...],
) -> tuple[ResultStatus, ...]:
    """Every branch's status, in declaration order.

    A composition whose own pointer does not resolve reports **every** branch as
    `missing` rather than returning early. The combined answer is the same
    either way, and the difference is the count in the detail line: "2 of 2
    branches could not be measured" is true, and "0 of 2" -- what an early
    return would leave -- would say the branches were fine.
    """
    if not container_found:
        return tuple(ResultStatus.MISSING for _ in branches)
    return tuple(_assertion_status(container, branch) for branch in branches)


def _assertion_status(container: JsonValue | None, node: Assertion) -> ResultStatus:
    """One branch's three-valued status, resolved within its parent's value.

    Bounded by `models.MAX_ASSERTION_DEPTH`, which the manifest loader enforces,
    so this recursion is three frames deep at most.

    **A pointer that does not resolve is `missing` here and `fail` in the flat
    top-level assertion**, and that difference is deliberate rather than an
    oversight. A flat assertion is the whole answer, and the pre-existing
    contract -- pinned by
    `tests/test_evaluator.py::test_pointer_descending_through_a_scalar_fails_without_raising`
    since #24 -- is that the document not saying the thing is an observed
    failure. A branch is folded together with others, and folding "not
    measured" into "false" is what would let `any_of` publish a verdict nobody
    measured. `MIN_COMPOSITION_BRANCHES` keeps the two rules from ever
    disagreeing about the same input: a one-branch composition, the only way to
    write one assertion in both forms, does not load.
    """
    found, actual = resolve(container, node.pointer)
    if node.branches is not None:
        return _combine_branches(node.operator, _branch_statuses(actual, found, node.branches))
    if node.operator == "exists":
        return ResultStatus.PASS if found else ResultStatus.FAIL
    if not found:
        return ResultStatus.MISSING
    return (
        ResultStatus.PASS if _compare(actual, node.operator, node.expected) else ResultStatus.FAIL
    )


def _composition_result(
    spec: EvidenceSpec,
    pointer: str,
    operator: str,
    branches: tuple[Assertion, ...],
    document: JsonValue,
    artifact_sha256: str,
) -> EvidenceResult:
    """Evaluate a composing evidence item and describe what it measured.

    The pointer and operator arrive as the non-optional strings the caller has
    already established them to be, rather than being re-read from `spec` and
    re-widened to `str | None`.

    The detail carries a denominator because the three statuses are otherwise
    indistinguishable in a receipt: `missing` on a composition means at least
    one branch could not be measured and no branch settled the question, and
    "how many" is the difference between an artifact that has drifted a little
    and one that does not carry the shape at all. It names no branch pointer and
    no filesystem fact, so it stays replayable across machines like every other
    detail string here.
    """
    found, actual = resolve(document, pointer)
    statuses = _branch_statuses(actual, found, branches)
    status = _combine_branches(operator, statuses)
    if status is ResultStatus.MISSING:
        unmeasured = sum(1 for item in statuses if item is ResultStatus.MISSING)
        detail = (
            f"assertion {pointer} {operator} was not evaluable: "
            f"{unmeasured} of {len(statuses)} branches could not be measured"
        )
    else:
        outcome = "passed" if status is ResultStatus.PASS else "did not pass"
        detail = f"assertion {pointer} {operator} over {len(statuses)} branches {outcome}"
    return EvidenceResult(
        evidence_id=spec.evidence_id,
        kind=spec.kind,
        status=status,
        artifact_sha256=artifact_sha256,
        detail=detail,
    )


def _evaluate_assertion(spec: EvidenceSpec, evidence_root: Path) -> EvidenceResult:
    try:
        data, artifact_sha256 = _read_json_artifact(evidence_root, spec.path)
    except (
        BoundedPathError,
        FileNotFoundError,
        OSError,
    ):
        return EvidenceResult(
            evidence_id=spec.evidence_id,
            kind=spec.kind,
            status=ResultStatus.MISSING,
            artifact_sha256=None,
            detail="artifact unavailable or invalid",
        )
    try:
        document = loads_json_strict(data)
    except (RecursionError, StrictJsonError, ValueError):
        return EvidenceResult(
            evidence_id=spec.evidence_id,
            kind=spec.kind,
            status=ResultStatus.MISSING,
            artifact_sha256=artifact_sha256,
            detail="artifact unavailable or invalid",
        )
    if spec.pointer is None or spec.operator is None:
        return EvidenceResult(
            evidence_id=spec.evidence_id,
            kind=spec.kind,
            status=ResultStatus.MISSING,
            artifact_sha256=artifact_sha256,
            detail="validated assertion is missing its pointer or operator",
        )
    if spec.branches is not None:
        return _composition_result(
            spec,
            spec.pointer,
            spec.operator,
            spec.branches,
            document,
            artifact_sha256,
        )
    found, actual = resolve(document, spec.pointer)
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
    ):
        return EvidenceResult(
            evidence_id=spec.evidence_id,
            kind=spec.kind,
            status=ResultStatus.REVIEW_REQUIRED,
            artifact_sha256=None,
            detail="attestation unavailable or invalid",
        )
    try:
        raw = loads_json_strict(data)
    except (RecursionError, StrictJsonError, ValueError):
        return EvidenceResult(
            evidence_id=spec.evidence_id,
            kind=spec.kind,
            status=ResultStatus.REVIEW_REQUIRED,
            artifact_sha256=artifact_sha256,
            detail="attestation unavailable or invalid",
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
    resolved_root = resolve_evidence_root(evidence_root)
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
            source_span=obligation.source_span,
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
        source_span=obligation.source_span,
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
    resolved_root = resolve_evidence_root(evidence_root)
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
