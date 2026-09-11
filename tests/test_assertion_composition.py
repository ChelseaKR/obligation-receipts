"""`all_of` and `any_of`: the composing half of the closed vocabulary (#64).

Three properties run through this file, and each of them is the reason one of
the four surfaces the feature touches had to move at all.

**A branch that could not be measured is `missing`, never `false`.** A
composition folds several answers into one, and folding "not measured" into
"did not pass" is how `any_of` would publish a verdict nobody measured -- an
absence rendered as a value, in a receipt a counterparty relies on. The
combination is Kleene three-valued logic, and `all_of`'s precedence is
`_combine_evidence`'s own order restricted to the statuses a `json_assertion`
can hold, because `all_of` is the within-artifact form of the `all_required`
rule the evidence plan already declares.

**The shape is enforced when the manifest loads, by every command.** Depth,
branch count, an `expected` on an operator that takes none, `branches` on one
that takes none: every one of those is a defect in the *approved manifest*, so
every one is a `ManifestError` raised before anything is read from the evidence
root. That is the line `pointer.is_well_formed` already draws.

**Adding an optional member to a closed document must move no committed byte.**
`branches` is emitted only by a composing operator, in the manifest and in the
plan, so a manifest and a plan that compose nothing hash to exactly what they
hashed to before. `tests/test_receipt.py::test_the_pre_composition_example_still_digests_to_what_it_digested_to`
is the pin on the receipt side; the plan digests pinned here are the pin on the
other.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from obligation_receipts.canonical import canonical_json_bytes, sha256_bytes
from obligation_receipts.evaluator import (
    IMPLEMENTED_OPERATORS,
    UnsupportedOperatorError,
    _assertion_status,
    _combine_branches,
    _compare,
    evaluate_manifest,
)
from obligation_receipts.manifest import ManifestError, load_manifest
from obligation_receipts.models import (
    ASSERTION_OPERATORS,
    COMPOSITION_OPERATORS,
    MAX_ASSERTION_DEPTH,
    MIN_COMPOSITION_BRANCHES,
    OPERATORS_WITHOUT_EXPECTED,
    Assertion,
    JsonValue,
    ResultStatus,
)
from obligation_receipts.plan import (
    EvidencePlanError,
    build_evidence_plan,
    verify_evidence_plan,
)
from obligation_receipts.single_check import check_declared_evidence, evidence_check_exit_code

#: The assertion the example's first obligation carries, which every test that
#: needs a different one swaps out. It includes the `pointer` line, where
#: `tests/test_assertion_vocabulary.py`'s anchor does not, because a composition
#: replaces the pointer as well as the operator. Both anchors are still unique
#: in the file: the branch tables the example now carries write
#: `operator = "eq", expected = 0` on one line, so neither multi-line anchor
#: matches inside them.
_ORIGINAL_ASSERTION = 'pointer = "/summary/critical_violations"\noperator = "eq"\nexpected = 0'

#: The composing evidence item the example ships, and the id of the obligation
#: that declares it.
_EXAMPLE_COMPOSITION_ID = "a5-axe-severity-thresholds"


def _replace(path: Path, old: str, new: str) -> None:
    content = path.read_text(encoding="utf-8")
    assert old in content, old
    path.write_text(content.replace(old, new, 1), encoding="utf-8")


def _with_assertion(copied_example: Path, toml_fragment: str) -> Path:
    """Point the example's *first* obligation at a different assertion.

    The first obligation reads `automated/axe-summary.json`, which really
    contains `{"summary": {"critical_violations": 0, "serious_violations": 0}}`.
    Everything else about the example -- the source binding, the five spans, the
    two attestations, the composing fifth obligation -- is left alone.
    """
    manifest_path = copied_example / "obligations.toml"
    _replace(manifest_path, _ORIGINAL_ASSERTION, toml_fragment)
    return manifest_path


def _first_status(copied_example: Path, toml_fragment: str) -> ResultStatus:
    manifest_path = _with_assertion(copied_example, toml_fragment)
    evaluation = evaluate_manifest(load_manifest(manifest_path), copied_example / "evidence")
    return evaluation.results[0].status


def _first_detail(copied_example: Path, toml_fragment: str) -> str:
    manifest_path = _with_assertion(copied_example, toml_fragment)
    evaluation = evaluate_manifest(load_manifest(manifest_path), copied_example / "evidence")
    return evaluation.results[0].evidence[0].detail


def _composition(operator: str, branches: str, pointer: str = "/summary") -> str:
    return f'pointer = "{pointer}"\noperator = "{operator}"\nbranches = [{branches}]'


def _leaf(pointer: str, operator: str, expected: str | None = None) -> Assertion:
    return Assertion(
        pointer=pointer,
        operator=operator,
        expected=None if expected is None else json.loads(expected),
    )


_SUMMARY: JsonValue = {"critical_violations": 0, "serious_violations": 0}


# ---- the vocabulary itself -----------------------------------------------------------


def test_the_composing_operators_are_accepted_and_implemented() -> None:
    """An accepted operator with no implementation is a `fail` sent to a supplier.

    `tests/test_misuse_boundaries.py` compares the two sets in general. This
    names the two added here, so an edit that drops one from both at once still
    fails, and it pins that they are the only two that compose and the only two
    besides `exists` that carry no `expected`.
    """
    assert sorted(COMPOSITION_OPERATORS) == ["all_of", "any_of"]
    assert COMPOSITION_OPERATORS <= ASSERTION_OPERATORS
    assert COMPOSITION_OPERATORS <= IMPLEMENTED_OPERATORS
    assert sorted(OPERATORS_WITHOUT_EXPECTED) == ["all_of", "any_of", "exists"]
    assert ASSERTION_OPERATORS == IMPLEMENTED_OPERATORS


@pytest.mark.parametrize("operator", sorted(COMPOSITION_OPERATORS))
def test_a_composing_operator_never_reaches_the_value_comparator(operator: str) -> None:
    """`_compare` returns a boolean and a composition needs three answers.

    Without this guard `_compare(0, "all_of", None)` would fall through its
    ordering branch and return `False` -- an observed `fail` against a supplier
    for a composition that was never combined. It is the same refusal `exists`
    already gets, for the same reason.
    """
    with pytest.raises(UnsupportedOperatorError, match="no implementation"):
        _compare(0, operator, None)


# ---- the combination rule ------------------------------------------------------------


_PASS = ResultStatus.PASS
_FAIL = ResultStatus.FAIL
_MISSING = ResultStatus.MISSING


@pytest.mark.parametrize(
    ("operator", "statuses", "combined"),
    [
        ("all_of", (_PASS, _PASS), _PASS),
        ("all_of", (_PASS, _FAIL), _FAIL),
        ("all_of", (_PASS, _MISSING), _MISSING),
        ("all_of", (_FAIL, _MISSING), _FAIL),
        ("all_of", (_MISSING, _MISSING), _MISSING),
        ("any_of", (_FAIL, _FAIL), _FAIL),
        ("any_of", (_PASS, _FAIL), _PASS),
        ("any_of", (_PASS, _MISSING), _PASS),
        ("any_of", (_FAIL, _MISSING), _MISSING),
        ("any_of", (_MISSING, _MISSING), _MISSING),
    ],
)
def test_the_combination_is_kleene_three_valued_logic(
    operator: str, statuses: tuple[ResultStatus, ...], combined: ResultStatus
) -> None:
    """Every cell of both truth tables, `missing` as the unknown.

    The two rows that carry the whole design are `any_of` over
    `(fail, missing)` and over `(missing, missing)`. A boolean fold answers
    `fail` to both: it would tell a supplier their evidence failed a comparison
    that was never made. The two `all_of` rows beside them are the dual, and
    they agree with `_combine_evidence`, which already resolves a `fail` beside
    a `missing` to `fail` across an obligation's evidence items.
    """
    assert _combine_branches(operator, statuses) is combined


def test_the_combination_is_order_independent() -> None:
    """A precedence, not a fold, so the manifest's branch order cannot change a verdict.

    Branch order decides the bytes of the plan and the manifest digest, and it
    must decide nothing about the answer.
    """
    for operator in sorted(COMPOSITION_OPERATORS):
        for statuses in [
            (_PASS, _FAIL, _MISSING),
            (_MISSING, _PASS, _FAIL),
            (_FAIL, _MISSING, _PASS),
        ]:
            assert _combine_branches(operator, statuses) is _combine_branches(
                operator, (_PASS, _FAIL, _MISSING)
            )


# ---- what a branch answers -----------------------------------------------------------


@pytest.mark.parametrize(
    ("node", "status"),
    [
        (Assertion(pointer="/critical_violations", operator="eq", expected=0), _PASS),
        (Assertion(pointer="/critical_violations", operator="eq", expected=1), _FAIL),
        (Assertion(pointer="/absent", operator="eq", expected=1), _MISSING),
        (Assertion(pointer="/critical_violations", operator="exists"), _PASS),
        (Assertion(pointer="/absent", operator="exists"), _FAIL),
    ],
)
def test_a_branch_answers_missing_for_an_unresolvable_pointer_and_exists_answers_it(
    node: Assertion, status: ResultStatus
) -> None:
    """`exists` is the one operator for which "not there" is an answer.

    Every other operator asks a question about a value, and a question about a
    value that is not there has no answer. `exists` asks whether the pointer
    resolves, so `false` really is its answer and it must not be softened into
    `missing` -- an `any_of` guarding an optional member with `exists` would
    otherwise never be able to say the member is absent.
    """
    assert _assertion_status(_SUMMARY, node) is status


def test_a_branch_pointer_is_resolved_inside_its_parents_value() -> None:
    """The base pointer is what makes a composition read one part of a document.

    `/summary` + `/critical_violations` is `/summary/critical_violations`, and a
    base of the empty string -- the whole document, RFC 6901 section 5 -- gives
    branches document-absolute pointers. Both readings come out of one rule.
    """
    document: JsonValue = {"summary": _SUMMARY}
    relative = Assertion(
        pointer="/summary",
        operator="all_of",
        branches=(
            _leaf("/critical_violations", "eq", "0"),
            _leaf("/serious_violations", "lte", "2"),
        ),
    )
    absolute = Assertion(
        pointer="",
        operator="all_of",
        branches=(
            _leaf("/summary/critical_violations", "eq", "0"),
            _leaf("/summary/serious_violations", "lte", "2"),
        ),
    )
    assert _assertion_status(document, relative) is _PASS
    assert _assertion_status(document, absolute) is _PASS
    # And the base really is a base: the same branches read from the root find
    # nothing, which is `missing` and not `fail`.
    misplaced = Assertion(pointer="", operator="all_of", branches=relative.branches)
    assert _assertion_status(document, misplaced) is _MISSING


def test_a_composition_whose_own_pointer_is_absent_reports_every_branch_unmeasured() -> None:
    """Not "the branches failed" and not "no branches were looked at"."""
    node = Assertion(
        pointer="/nowhere",
        operator="all_of",
        branches=(_leaf("/a", "eq", "1"), _leaf("/b", "eq", "2")),
    )
    assert _assertion_status({"summary": _SUMMARY}, node) is _MISSING


def test_a_nested_composition_is_evaluated_within_its_parent() -> None:
    """`all_of` containing `any_of`, which is what the depth cap allows exactly one of."""
    node = Assertion(
        pointer="/summary",
        operator="all_of",
        branches=(
            _leaf("/critical_violations", "eq", "0"),
            Assertion(
                pointer="",
                operator="any_of",
                branches=(
                    _leaf("/serious_violations", "eq", "9"),
                    _leaf("/serious_violations", "lte", "2"),
                ),
            ),
        ),
    )
    assert _assertion_status({"summary": _SUMMARY}, node) is _PASS


# ---- the deliberate difference from the flat form ------------------------------------


@pytest.mark.parametrize(
    ("fragment", "flat_status"),
    [
        ('pointer = "/summary/absent"\noperator = "eq"\nexpected = 0', ResultStatus.FAIL),
        ('pointer = "/summary/absent"\noperator = "exists"', ResultStatus.FAIL),
    ],
)
def test_a_flat_assertion_still_reports_an_unresolvable_pointer_as_fail(
    copied_example: Path, fragment: str, flat_status: ResultStatus
) -> None:
    """The pre-existing contract, unchanged, and the reason it can stay unchanged.

    A flat `eq` over an absent pointer is `fail` (since #24) and a *branch* with
    the same pointer and operator is `missing`. Those two rules could contradict
    each other over one input only if one assertion could be written both ways,
    and `MIN_COMPOSITION_BRANCHES` is what makes that impossible: a one-branch
    composition does not load. See `test_a_composition_of_one_branch_is_refused`.

    Stated as a test rather than as a comment because it is the single most
    likely thing for a later reader to "fix" in one direction or the other, and
    either direction is a change to what a receipt means.
    """
    assert _first_status(copied_example, fragment) is flat_status
    assert (
        _assertion_status(
            {"summary": _SUMMARY},
            Assertion(pointer="/summary/absent", operator="eq", expected=0),
        )
        is ResultStatus.MISSING
    )


# ---- load-time refusals --------------------------------------------------------------


def test_a_composition_of_one_branch_is_refused(copied_example: Path) -> None:
    """The rule that keeps the two unresolvable-pointer rules from ever meeting."""
    assert MIN_COMPOSITION_BRANCHES == 2
    manifest_path = _with_assertion(
        copied_example,
        _composition(
            "all_of", '{ pointer = "/critical_violations", operator = "eq", expected = 0 }'
        ),
    )
    with pytest.raises(ManifestError, match="at least 2 assertions"):
        load_manifest(manifest_path)


@pytest.mark.parametrize("branches", ["", '"not-a-table"', "1, 2"])
def test_branches_must_be_an_array_of_at_least_two_assertion_tables(
    copied_example: Path, branches: str
) -> None:
    manifest_path = _with_assertion(copied_example, _composition("any_of", branches))
    with pytest.raises(ManifestError, match=r"at least 2 assertions|must be a table"):
        load_manifest(manifest_path)


def test_a_composing_operator_may_not_declare_an_expected_value(copied_example: Path) -> None:
    """Its operand is its branches; an `expected` beside them says nothing."""
    manifest_path = _with_assertion(
        copied_example,
        _composition(
            "all_of",
            '{ pointer = "/critical_violations", operator = "eq", expected = 0 }, '
            '{ pointer = "/serious_violations", operator = "lte", expected = 2 }',
        )
        + "\nexpected = 0",
    )
    with pytest.raises(ManifestError, match="expected is not allowed for operator all_of"):
        load_manifest(manifest_path)


def test_branches_are_refused_on_an_operator_that_does_not_compose(
    copied_example: Path,
) -> None:
    """`eq` with branches is an author who thinks the branches will be read."""
    manifest_path = _with_assertion(
        copied_example,
        _ORIGINAL_ASSERTION
        + '\nbranches = [{ pointer = "/serious_violations", operator = "lte", expected = 2 }]',
    )
    with pytest.raises(ManifestError, match="branches is not allowed for operator eq"):
        load_manifest(manifest_path)


def test_a_branch_carrying_an_unknown_field_is_refused(copied_example: Path) -> None:
    manifest_path = _with_assertion(
        copied_example,
        _composition(
            "all_of",
            '{ pointer = "/critical_violations", operator = "eq", expected = 0, note = "x" }, '
            '{ pointer = "/serious_violations", operator = "lte", expected = 2 }',
        ),
    )
    with pytest.raises(ManifestError, match="unknown field"):
        load_manifest(manifest_path)


@pytest.mark.parametrize(
    ("branch", "message"),
    [
        ('{ pointer = "critical", operator = "eq", expected = 0 }', "RFC 6901"),
        ('{ pointer = "/critical", operator = "approximately", expected = 0 }', "must be one of"),
        ('{ pointer = "/critical", operator = "eq" }', "expected is required"),
        ('{ pointer = "/critical", operator = "exists", expected = 0 }', "is not allowed"),
        ('{ pointer = "/critical", operator = "in", expected = [] }', "non-empty array"),
    ],
)
def test_a_branch_is_held_to_every_rule_a_top_level_assertion_is(
    copied_example: Path, branch: str, message: str
) -> None:
    """A branch is an assertion, so it gets the assertion checks, not a subset.

    Without this, a pointer, an operator name or an `expected` shape would reach
    the evaluator unchecked one level down -- and an authoring defect that
    reaches the evaluator becomes an observed `fail` in a receipt, which is the
    line this project draws everywhere else.
    """
    manifest_path = _with_assertion(
        copied_example,
        _composition(
            "all_of",
            f'{branch}, {{ pointer = "/serious_violations", operator = "lte", expected = 2 }}',
        ),
    )
    with pytest.raises(ManifestError, match=message):
        load_manifest(manifest_path)


def test_nesting_is_allowed_to_the_cap_and_refused_past_it(copied_example: Path) -> None:
    """Three assertion levels load; a composition at level 3 does not.

    The cap is what keeps "closed" a property of the format. Without it a
    manifest could nest until the canonical-JSON depth limit stopped it, and a
    64-level assertion is an expression language written in TOML.
    """
    assert MAX_ASSERTION_DEPTH == 3
    leaves = (
        '{ pointer = "/critical_violations", operator = "eq", expected = 0 }, '
        '{ pointer = "/serious_violations", operator = "lte", expected = 2 }'
    )
    at_the_cap = _composition(
        "all_of",
        f'{{ pointer = "", operator = "any_of", branches = [{leaves}] }}, '
        '{ pointer = "/critical_violations", operator = "exists" }',
    )
    manifest = load_manifest(_with_assertion(copied_example, at_the_cap))
    branches = manifest.obligations[0].evidence[0].branches
    assert branches is not None
    assert branches[0].branches is not None

    past_the_cap = _composition(
        "all_of",
        '{ pointer = "", operator = "any_of", branches = ['
        f'{{ pointer = "", operator = "all_of", branches = [{leaves}] }}, '
        '{ pointer = "/critical_violations", operator = "exists" }] }, '
        '{ pointer = "/critical_violations", operator = "exists" }',
    )
    _replace(copied_example / "obligations.toml", at_the_cap, past_the_cap)
    with pytest.raises(ManifestError, match="composes at assertion level"):
        load_manifest(copied_example / "obligations.toml")


def test_attestation_evidence_still_cannot_declare_branches(copied_example: Path) -> None:
    """The `branches` member joins the assertion fields an attestation may not carry."""
    _replace(
        copied_example / "obligations.toml",
        'kind = "review_attestation"',
        'kind = "review_attestation"\nbranches = []',
    )
    with pytest.raises(ManifestError, match="cannot define an assertion"):
        load_manifest(copied_example / "obligations.toml")


# ---- end to end against the example --------------------------------------------------


@pytest.mark.parametrize(
    ("operator", "branches", "status"),
    [
        (
            "all_of",
            '{ pointer = "/critical_violations", operator = "eq", expected = 0 }, '
            '{ pointer = "/serious_violations", operator = "lte", expected = 2 }',
            ResultStatus.PASS,
        ),
        (
            "all_of",
            '{ pointer = "/critical_violations", operator = "eq", expected = 0 }, '
            '{ pointer = "/serious_violations", operator = "eq", expected = 5 }',
            ResultStatus.FAIL,
        ),
        (
            "all_of",
            '{ pointer = "/critical_violations", operator = "eq", expected = 0 }, '
            '{ pointer = "/moderate_violations", operator = "lte", expected = 9 }',
            ResultStatus.MISSING,
        ),
        (
            "any_of",
            '{ pointer = "/critical_violations", operator = "eq", expected = 7 }, '
            '{ pointer = "/serious_violations", operator = "eq", expected = 0 }',
            ResultStatus.PASS,
        ),
        (
            "any_of",
            '{ pointer = "/critical_violations", operator = "eq", expected = 7 }, '
            '{ pointer = "/serious_violations", operator = "eq", expected = 5 }',
            ResultStatus.FAIL,
        ),
        (
            "any_of",
            '{ pointer = "/moderate_violations", operator = "eq", expected = 7 }, '
            '{ pointer = "/minor_violations", operator = "eq", expected = 5 }',
            ResultStatus.MISSING,
        ),
    ],
)
def test_a_composition_evaluates_end_to_end_through_the_cli_path(
    copied_example: Path, operator: str, branches: str, status: ResultStatus
) -> None:
    """Through `load_manifest` and `evaluate_manifest`, not through the helpers.

    The two `missing` rows are the ones worth reading. `/moderate_violations` is
    not in the artifact; the flat form of that assertion would be a `fail`
    against the supplier, and inside a composition it is an admission that the
    question was not answered.
    """
    assert _first_status(copied_example, _composition(operator, branches)) is status


def test_the_detail_line_counts_the_branches_it_could_not_measure(
    copied_example: Path,
) -> None:
    """A denominator, because the three statuses are otherwise indistinguishable.

    It names no branch pointer, no path and no errno, so the payload it lands in
    replays byte-identically on another machine -- the property
    `tests/test_evaluator.py::test_payload_digest_is_independent_of_how_the_artifact_became_unreadable`
    protects for the `missing` branch of the payload.
    """
    detail = _first_detail(
        copied_example,
        _composition(
            "any_of",
            '{ pointer = "/moderate_violations", operator = "eq", expected = 7 }, '
            '{ pointer = "/minor_violations", operator = "eq", expected = 5 }',
        ),
    )
    assert detail == (
        "assertion /summary any_of was not evaluable: 2 of 2 branches could not be measured"
    )


def test_the_detail_line_names_the_operator_and_the_branch_count_when_it_did_answer(
    copied_example: Path,
) -> None:
    passed = _first_detail(
        copied_example,
        _composition(
            "all_of",
            '{ pointer = "/critical_violations", operator = "eq", expected = 0 }, '
            '{ pointer = "/serious_violations", operator = "lte", expected = 2 }',
        ),
    )
    assert passed == "assertion /summary all_of over 2 branches passed"


def test_an_absent_artifact_is_missing_before_any_branch_is_considered(
    copied_example: Path,
) -> None:
    """Composition changes nothing about unavailable evidence.

    An artifact that cannot be read is `missing` with the detail it always had,
    and no branch count, because no branch was reached.
    """
    (copied_example / "evidence" / "automated" / "axe-summary.json").unlink()
    evaluation = evaluate_manifest(
        load_manifest(copied_example / "obligations.toml"), copied_example / "evidence"
    )
    composing = next(
        item for item in evaluation.results if item.obligation_id == "a5-severity-thresholds"
    )
    assert composing.status is ResultStatus.MISSING
    assert composing.evidence[0].detail == "artifact unavailable or invalid"


# ---- the example ---------------------------------------------------------------------


def test_the_shipped_example_composes_and_passes(example_manifest: Path) -> None:
    """#64's first "Done when": the example gains an `all_of` obligation that evaluates."""
    manifest = load_manifest(example_manifest)
    composing = next(
        item for item in manifest.obligations if item.obligation_id == "a5-severity-thresholds"
    )
    spec = composing.evidence[0]
    assert spec.evidence_id == _EXAMPLE_COMPOSITION_ID
    assert spec.operator == "all_of"
    assert spec.pointer == "/summary"
    assert spec.branches is not None
    assert [(item.pointer, item.operator, item.expected) for item in spec.branches] == [
        ("/critical_violations", "eq", 0),
        ("/serious_violations", "lte", 2),
    ]

    evaluation = evaluate_manifest(manifest, example_manifest.parent / "evidence")
    result = next(
        item for item in evaluation.results if item.obligation_id == "a5-severity-thresholds"
    )
    assert result.status is ResultStatus.PASS


def test_the_example_manifest_pins_its_normalized_digest(example_manifest: Path) -> None:
    """The manifest digest is what every attestation in the example binds to.

    Pinned to a literal rather than recomputed, for the reason
    `tests/test_receipt.py` pins the receipt payload: a determinism test that
    normalizes twice in one interpreter agrees with itself no matter what the
    ordering rules are, and a literal computed in another process does not.
    """
    assert load_manifest(example_manifest).manifest_sha256 == (
        "b6a4e14a3a4f46d12ceead157f8766ffceed215cf5d9cc4cd2448e24e68e01c9"
    )


# ---- the evidence plan ---------------------------------------------------------------


def _payload(plan: dict[str, JsonValue]) -> dict[str, JsonValue]:
    payload = plan["payload"]
    assert isinstance(payload, dict)
    return payload


def _assertion_of(plan: dict[str, JsonValue], obligation_id: str) -> dict[str, JsonValue]:
    obligations = _payload(plan)["obligations"]
    assert isinstance(obligations, list)
    entry = next(
        item for item in obligations if isinstance(item, dict) and item["id"] == obligation_id
    )
    requirements = entry["evidence_requirements"]
    assert isinstance(requirements, list)
    requirement = requirements[0]
    assert isinstance(requirement, dict)
    assertion = requirement["assertion"]
    assert isinstance(assertion, dict)
    return assertion


def test_the_plan_carries_the_branches_verbatim(example_manifest: Path) -> None:
    """A collector cannot prepare the right artifact from `all_of` alone.

    `branches` is retained in both privacy profiles for the same reason
    thresholds are: the plan is what somebody reads before the evidence exists.
    """
    manifest = load_manifest(example_manifest)
    for local in (False, True):
        plan = build_evidence_plan(manifest, include_local_details=local)
        assert verify_evidence_plan(plan, manifest) == plan["payload_sha256"]
        assert _assertion_of(plan, "a5-severity-thresholds") == {
            "branches": [
                {
                    "expected": 0,
                    "expected_declared": True,
                    "operator": "eq",
                    "pointer": "/critical_violations",
                },
                {
                    "expected": 2,
                    "expected_declared": True,
                    "operator": "lte",
                    "pointer": "/serious_violations",
                },
            ],
            "expected": None,
            "expected_declared": False,
            "operator": "all_of",
            "pointer": "/summary",
        }


def test_a_non_composing_requirement_carries_no_branches_member_at_all(
    example_manifest: Path,
) -> None:
    """The member is absent, not null.

    This is what makes a plan built from a manifest that composes nothing
    byte-identical to the plans built before composition existed, and it is the
    same rule `source_span` follows.
    """
    plan = build_evidence_plan(load_manifest(example_manifest), include_local_details=True)
    assert "branches" not in _assertion_of(plan, "a1-zero-critical-violations")


@pytest.mark.parametrize(
    ("local", "payload_sha256"),
    [
        (False, "1cfb9a40d208d3bd88176571ee3298d923f3ebfb87528b3f15dcb90d911831e6"),
        (True, "9610765cc0db27ce39b5d3744656b23f13fcc7b4ab4f96790d3d91cf2c8fb1e9"),
    ],
)
def test_the_composing_plan_pins_its_payload_digest(
    example_manifest: Path, local: bool, payload_sha256: str
) -> None:
    """The plan is a wire format too, and nothing pinned its bytes before.

    A plan is handed to a counterparty and verified by them, so a change to key
    naming, member order inside `branches`, or which members a composing
    assertion carries breaks a document somebody already holds. Both profiles
    are pinned because they are two different documents.
    """
    plan = build_evidence_plan(load_manifest(example_manifest), include_local_details=local)
    assert plan["payload_sha256"] == payload_sha256, (
        "the evidence-plan payload wire format changed: a plan a counterparty already "
        "holds no longer verifies. Update this literal only as a deliberate, documented "
        "format change -- never to make the suite green."
    )


def test_the_plan_digest_moves_when_the_branch_order_does(copied_example: Path) -> None:
    """Proof that the pinned digest can see a reordering, by reordering.

    A determinism test that builds the same document twice in one interpreter
    cannot see an ordering that comes out of a `set` or a `dict`, because both
    are stable within a process. Nothing in the composition path iterates either
    -- branches are a tuple in declaration order and `canonical_json_bytes`
    sorts keys -- and this is what says so: swap the two branches and the digest
    the test above pins must not survive it.
    """
    committed = build_evidence_plan(load_manifest(copied_example / "obligations.toml"))
    _replace(
        copied_example / "obligations.toml",
        '{ pointer = "/critical_violations", operator = "eq", expected = 0 },\n'
        '  { pointer = "/serious_violations", operator = "lte", expected = 2 },',
        '{ pointer = "/serious_violations", operator = "lte", expected = 2 },\n'
        '  { pointer = "/critical_violations", operator = "eq", expected = 0 },',
    )
    reordered = build_evidence_plan(load_manifest(copied_example / "obligations.toml"))
    assert committed["payload_sha256"] == (
        "1cfb9a40d208d3bd88176571ee3298d923f3ebfb87528b3f15dcb90d911831e6"
    )
    assert reordered["payload_sha256"] != committed["payload_sha256"]
    # And the reordering really did reach the document under test, rather than
    # only the manifest: a sabotage that lands outside the property proves
    # nothing about it.
    assert _assertion_of(reordered, "a5-severity-thresholds") != _assertion_of(
        committed, "a5-severity-thresholds"
    )


def _rehash(plan: dict[str, JsonValue]) -> None:
    plan["payload_sha256"] = sha256_bytes(canonical_json_bytes(plan["payload"]))


def _branches_of(assertion: dict[str, JsonValue]) -> list[JsonValue]:
    branches = assertion["branches"]
    assert isinstance(branches, list)
    return branches


def _first_branch(assertion: dict[str, JsonValue]) -> dict[str, JsonValue]:
    branch = _branches_of(assertion)[0]
    assert isinstance(branch, dict)
    return branch


def _make_it_a_scalar_operator(assertion: dict[str, JsonValue]) -> None:
    assertion["operator"] = "eq"


def _empty_the_branches(assertion: dict[str, JsonValue]) -> None:
    assertion["branches"] = []


def _leave_one_branch(assertion: dict[str, JsonValue]) -> None:
    assertion["branches"] = _branches_of(assertion)[:1]


def _replace_branches_with_a_string(assertion: dict[str, JsonValue]) -> None:
    assertion["branches"] = "two"


def _break_a_branch_pointer(assertion: dict[str, JsonValue]) -> None:
    _first_branch(assertion)["pointer"] = "critical"


def _break_a_branch_operator(assertion: dict[str, JsonValue]) -> None:
    _first_branch(assertion)["operator"] = "nope"


def _break_a_branch_expected_flag(assertion: dict[str, JsonValue]) -> None:
    _first_branch(assertion)["expected_declared"] = False


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (_make_it_a_scalar_operator, "expected declaration is inconsistent"),
        (_empty_the_branches, "at least 2 branches"),
        (_leave_one_branch, "at least 2 branches"),
        (_replace_branches_with_a_string, "at least 2 branches"),
        (_break_a_branch_pointer, "pointer is invalid"),
        (_break_a_branch_operator, "operator is unsupported"),
        (_break_a_branch_expected_flag, "expected declaration is inconsistent"),
    ],
)
def test_a_hand_edited_composing_plan_is_refused(
    example_manifest: Path,
    mutate: Callable[[dict[str, JsonValue]], None],
    message: str,
) -> None:
    """Checksum-only verification has to reach inside `branches`.

    `verify-evidence-plan` is run without `--manifest` more often than with it,
    so a plan whose branches are unreadable, unsupported or too few must be
    refused by the document's own schema rather than only by regeneration.
    """
    plan = build_evidence_plan(load_manifest(example_manifest))
    mutate(_assertion_of(plan, "a5-severity-thresholds"))
    _rehash(plan)
    with pytest.raises(EvidencePlanError, match=message):
        verify_evidence_plan(plan)


def test_a_plan_that_puts_branches_on_a_non_composing_operator_is_refused(
    example_manifest: Path,
) -> None:
    plan = build_evidence_plan(load_manifest(example_manifest))
    assertion = _assertion_of(plan, "a1-zero-critical-violations")
    assertion["branches"] = _assertion_of(plan, "a5-severity-thresholds")["branches"]
    _rehash(plan)
    with pytest.raises(EvidencePlanError, match="branches are not allowed for operator eq"):
        verify_evidence_plan(plan)


def test_a_plan_that_composes_past_the_cap_is_refused(example_manifest: Path) -> None:
    """The manifest loader cannot be the only place the depth is bounded.

    A plan is a document that arrives from outside; its own validator has to
    hold the same cap, or a hand-written plan could ask a reader to walk a
    structure the format does not allow.
    """
    plan = build_evidence_plan(load_manifest(example_manifest))
    assertion = _assertion_of(plan, "a5-severity-thresholds")
    branches = _branches_of(assertion)
    innermost = json.loads(json.dumps(assertion))
    nested = json.loads(json.dumps(assertion))
    nested_branches = nested["branches"]
    nested_branches[0] = innermost
    branches[0] = nested
    _rehash(plan)
    with pytest.raises(EvidencePlanError, match="composes past assertion level 3"):
        verify_evidence_plan(plan)


# ---- the single-evidence check -------------------------------------------------------


def test_the_single_check_serializes_nothing_of_a_composition(example_manifest: Path) -> None:
    """#64's fourth "Done when", on the document that redacts the most.

    `check-evidence` carries the evidence id, kind and status and no part of the
    assertion. A composition is more of an assertion than a scalar comparison
    is, and it is withheld by the same rule and needed no new field: the
    document's closed payload schema is unchanged.
    """
    manifest = load_manifest(example_manifest)
    document = check_declared_evidence(
        manifest, _EXAMPLE_COMPOSITION_ID, example_manifest.parent / "evidence"
    )
    payload = _payload(document)
    evidence = payload["evidence"]
    assert isinstance(evidence, dict)
    assert evidence["status"] == "pass"
    assert set(evidence) == {"artifact_sha256", "id", "kind", "status"}

    encoded = canonical_json_bytes(document)
    for withheld in (b"all_of", b"branches", b"critical_violations", b"/summary", b"lte"):
        assert withheld not in encoded, withheld
    assert evidence_check_exit_code(document) == 0


def test_an_unevaluable_composition_exits_as_missing_not_as_a_failure(
    copied_example: Path,
) -> None:
    """Exit 3, the code reserved for evidence that could not be read.

    Exit 1 would tell a supplier's pipeline their evidence failed. The whole
    point of the three-valued combination is that this is a different sentence,
    and the exit code is where a caller reads it.
    """
    _replace(
        copied_example / "obligations.toml",
        '{ pointer = "/critical_violations", operator = "eq", expected = 0 },',
        '{ pointer = "/moderate_violations", operator = "eq", expected = 0 },',
    )
    _replace(
        copied_example / "obligations.toml",
        '{ pointer = "/serious_violations", operator = "lte", expected = 2 },',
        '{ pointer = "/minor_violations", operator = "lte", expected = 2 },',
    )
    manifest = load_manifest(copied_example / "obligations.toml")
    document = check_declared_evidence(
        manifest, _EXAMPLE_COMPOSITION_ID, copied_example / "evidence"
    )
    payload = _payload(document)
    evidence = payload["evidence"]
    assert isinstance(evidence, dict)
    assert evidence["status"] == "missing"
    assert evidence["artifact_sha256"] is not None
    assert evidence_check_exit_code(document) == 3
