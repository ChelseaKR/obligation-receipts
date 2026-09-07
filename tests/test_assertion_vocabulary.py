"""The set, range, length and type operators added to the closed vocabulary (#64).

Two properties run through every test here.

**A shape the operator cannot use is refused at load time, never evaluated.** An
`expected` that is the wrong shape is an authoring defect in the *approved manifest*,
so it is a `ManifestError` raised by every command that loads, exactly as a malformed
pointer is. The alternative is the failure `models.ASSERTION_OPERATORS` was
consolidated to prevent: a comparison nobody could make, reported to a counterparty as
an observed `fail` against their evidence.

**A value with the wrong type is `False`, and a value with no length is not length
zero.** Those are different claims and only the first is an answer. `length lte 0`
passing against the number `7` would be a measurement that was never taken, published
as a real one.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from obligation_receipts.evaluator import (
    IMPLEMENTED_OPERATORS,
    UnsupportedOperatorError,
    _compare,
    evaluate_manifest,
)
from obligation_receipts.manifest import ManifestError, load_manifest
from obligation_receipts.models import (
    ASSERTION_OPERATORS,
    JSON_TYPE_NAMES,
    LENGTH_COMPARISONS,
    JsonValue,
    ResultStatus,
)

_ORIGINAL_ASSERTION = 'operator = "eq"\nexpected = 0'


def _replace(path: Path, old: str, new: str) -> None:
    content = path.read_text(encoding="utf-8")
    assert old in content, old
    path.write_text(content.replace(old, new, 1), encoding="utf-8")


def _with_assertion(copied_example: Path, toml_fragment: str) -> Path:
    """Point the example's first obligation at a different assertion.

    The first obligation asserts `/summary/critical_violations eq 0` against
    `automated/axe-summary.json`, which really contains that member. Swapping only
    the operator and the expected value keeps every other part of the example --
    the source binding, the spans, the two attestations -- exactly as it is.
    """
    manifest_path = copied_example / "obligations.toml"
    _replace(manifest_path, _ORIGINAL_ASSERTION, toml_fragment)
    return manifest_path


def _first_status(copied_example: Path, toml_fragment: str) -> ResultStatus:
    manifest_path = _with_assertion(copied_example, toml_fragment)
    evaluation = evaluate_manifest(load_manifest(manifest_path), copied_example / "evidence")
    return evaluation.results[0].status


# ---- the vocabulary itself -----------------------------------------------------------


def test_the_new_operators_are_accepted_and_implemented() -> None:
    """The guard that matters: an accepted operator with no implementation.

    `test_misuse_boundaries` compares the two sets in general; this names the six
    added here, so a later edit that drops one from both sets at once still fails.
    """
    added = {"in", "not_in", "between", "length", "type"}
    assert added <= ASSERTION_OPERATORS
    assert added <= IMPLEMENTED_OPERATORS
    assert ASSERTION_OPERATORS == IMPLEMENTED_OPERATORS


def test_an_operator_outside_the_vocabulary_still_raises_rather_than_answering() -> None:
    """The refusal `_compare` exists to make, unchanged by the widening."""
    with pytest.raises(UnsupportedOperatorError, match="no evaluation was made"):
        _compare(1, "matches", 1)


def test_exists_still_never_reaches_the_comparator() -> None:
    """`exists` is answered from the pointer's found flag, one level up.

    It is in the vocabulary and in the implemented set, and it must still raise
    here rather than acquire a second definition that could disagree with the
    first.
    """
    with pytest.raises(UnsupportedOperatorError):
        _compare(1, "exists", None)


# ---- set membership ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("actual", "members", "present"),
    [
        ("passed", ["passed", "skipped"], True),
        ("failed", ["passed", "skipped"], False),
        (2, [1, 2, 3], True),
        (None, [None], True),
        ([1, 2], [[1, 2]], True),
        ({"a": 1}, [{"a": 1}], True),
    ],
)
def test_in_and_not_in_are_exact_inverses(
    actual: JsonValue, members: list[JsonValue], present: bool
) -> None:
    assert _compare(actual, "in", members) is present
    assert _compare(actual, "not_in", members) is (not present)


@pytest.mark.parametrize(("actual", "members"), [(True, [1]), (1, [True]), (False, [0])])
def test_a_boolean_is_never_a_member_of_a_numeric_set(
    actual: JsonValue, members: list[JsonValue]
) -> None:
    """`1 == True` in Python and JSON does not agree.

    Without the guard, `expected = [1]` would report a resolved `true` as an
    observed `pass` for a comparison the manifest author did not write.
    """
    assert _compare(actual, "in", members) is False
    assert _compare(actual, "not_in", members) is True


@pytest.mark.parametrize("operator", ["in", "not_in"])
@pytest.mark.parametrize("expected", ["[]", '"passed"', "0"])
def test_a_set_operator_needs_a_non_empty_array(
    copied_example: Path, operator: str, expected: str
) -> None:
    """An empty set makes `in` a constant failure and `not_in` a constant pass."""
    manifest_path = _with_assertion(
        copied_example, f'operator = "{operator}"\nexpected = {expected}'
    )
    with pytest.raises(ManifestError, match="must be a non-empty array"):
        load_manifest(manifest_path)


# ---- between -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("actual", "passes"),
    [(1, True), (10, True), (5, True), (0, False), (11, False), (1.5, True)],
)
def test_between_is_inclusive_on_both_ends(actual: JsonValue, passes: bool) -> None:
    assert _compare(actual, "between", [1, 10]) is passes


@pytest.mark.parametrize("actual", [True, False, "5", None, [5], {"a": 5}])
def test_between_answers_false_for_a_value_that_is_not_a_number(actual: JsonValue) -> None:
    """A real answer about a value of the wrong type, not a refusal.

    `True` is listed because `isinstance(True, int)` would otherwise place it
    inside `[0, 2]`.
    """
    assert _compare(actual, "between", [0, 2]) is False


@pytest.mark.parametrize(
    "expected",
    ["[10, 1]", "[1]", "[1, 2, 3]", '["a", "b"]', "1", '"1"', "[true, false]"],
)
def test_a_malformed_or_inverted_range_is_refused_at_load_time(
    copied_example: Path, expected: str
) -> None:
    """An inverted range matches nothing, so every evaluation would be a `fail`."""
    manifest_path = _with_assertion(copied_example, f'operator = "between"\nexpected = {expected}')
    with pytest.raises(ManifestError, match=r"for operator between|bounds are inverted"):
        load_manifest(manifest_path)


def test_a_degenerate_range_of_one_value_is_allowed(copied_example: Path) -> None:
    """`[3, 3]` is a legitimate way to say exactly three, and is not inverted."""
    manifest_path = _with_assertion(copied_example, 'operator = "between"\nexpected = [0, 0]')
    assert load_manifest(manifest_path).obligations[0].evidence[0].operator == "between"


# ---- length --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("actual", "comparison", "wanted", "passes"),
    [
        ([], "gte", 1, False),
        ([1], "gte", 1, True),
        ([1, 2, 3], "eq", 3, True),
        ("", "gt", 0, False),
        ("abc", "eq", 3, True),
        ({"a": 1, "b": 2}, "eq", 2, True),
        ([1, 2], "ne", 3, True),
        ([1, 2], "lte", 2, True),
        ([1, 2, 3], "lt", 3, False),
    ],
)
def test_length_measures_arrays_strings_and_object_members(
    actual: JsonValue, comparison: str, wanted: int, passes: bool
) -> None:
    assert _compare(actual, "length", {"operator": comparison, "value": wanted}) is passes


@pytest.mark.parametrize("actual", [7, 0, True, False, None, 1.5])
def test_a_value_with_no_length_is_false_rather_than_length_zero(actual: JsonValue) -> None:
    """The whole reason this operator needs a test rather than a comment.

    If "has no length" collapsed to "length 0", then `length lte 0` would pass
    against the number 7 -- a measurement that was never taken, reported as a
    real one, in a receipt a counterparty relies on.
    """
    assert _compare(actual, "length", {"operator": "lte", "value": 0}) is False
    assert _compare(actual, "length", {"operator": "gte", "value": 0}) is False


@pytest.mark.parametrize(
    ("expected", "message"),
    [
        ("1", "must be a table"),
        ('{operator = "gte"}', "must be a table"),
        ('{operator = "gte", value = 1, extra = 2}', "must be a table"),
        ('{operator = "exists", value = 1}', "expected.operator must be one of"),
        ('{operator = "in", value = 1}', "expected.operator must be one of"),
        ('{operator = "gte", value = -1}', "non-negative integer length"),
        ('{operator = "gte", value = 1.5}', "non-negative integer length"),
        ('{operator = "gte", value = true}', "non-negative integer length"),
    ],
)
def test_a_malformed_length_comparison_is_refused_at_load_time(
    copied_example: Path, expected: str, message: str
) -> None:
    manifest_path = _with_assertion(copied_example, f'operator = "length"\nexpected = {expected}')
    with pytest.raises(ManifestError, match=message):
        load_manifest(manifest_path)


def test_length_offers_exactly_the_comparisons_a_length_can_carry() -> None:
    """`exists` and the set operators are excluded on purpose, not by omission."""
    assert set(LENGTH_COMPARISONS) == {"eq", "ne", "gt", "gte", "lt", "lte"}
    assert "exists" not in LENGTH_COMPARISONS
    assert not LENGTH_COMPARISONS & {"in", "not_in", "between", "length", "type"}


# ---- type ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("actual", "name"),
    [
        (None, "null"),
        (True, "boolean"),
        (False, "boolean"),
        (0, "number"),
        (1.5, "number"),
        ("x", "string"),
        ([], "array"),
        ({}, "object"),
    ],
)
def test_type_names_every_json_type(actual: JsonValue, name: str) -> None:
    assert _compare(actual, "type", name) is True
    for other in JSON_TYPE_NAMES - {name}:
        assert _compare(actual, "type", other) is False


def test_a_boolean_is_not_a_number(copied_example: Path) -> None:
    """Tested on its own because `isinstance(True, int)` says otherwise."""
    assert _compare(True, "type", "number") is False
    assert _compare(1, "type", "boolean") is False


def test_integer_is_not_an_available_type_name() -> None:
    """JSON has one number type, and `1.0` must not be a `fail` against `1`."""
    assert "integer" not in JSON_TYPE_NAMES


@pytest.mark.parametrize("expected", ['"integer"', '"Number"', "0", '["number"]', "true"])
def test_an_unknown_type_name_is_refused_at_load_time(copied_example: Path, expected: str) -> None:
    manifest_path = _with_assertion(copied_example, f'operator = "type"\nexpected = {expected}')
    with pytest.raises(ManifestError, match="for operator type"):
        load_manifest(manifest_path)


# ---- end to end ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("fragment", "status"),
    [
        ('operator = "between"\nexpected = [0, 2]', ResultStatus.PASS),
        ('operator = "between"\nexpected = [1, 2]', ResultStatus.FAIL),
        ('operator = "in"\nexpected = [0, 1]', ResultStatus.PASS),
        ('operator = "in"\nexpected = [1, 2]', ResultStatus.FAIL),
        ('operator = "not_in"\nexpected = [1, 2]', ResultStatus.PASS),
        ('operator = "type"\nexpected = "number"', ResultStatus.PASS),
        ('operator = "type"\nexpected = "string"', ResultStatus.FAIL),
        ('operator = "length"\nexpected = {operator = "gte", value = 1}', ResultStatus.FAIL),
    ],
)
def test_each_new_operator_evaluates_end_to_end_against_the_example(
    copied_example: Path, fragment: str, status: ResultStatus
) -> None:
    """Through `load_manifest` and `evaluate_manifest`, not through `_compare`.

    The last row is the one worth reading: `/summary/critical_violations` is the
    number `0`, which has no length, so a length assertion against it is a `fail`
    about a real value rather than a pass against an invented zero.
    """
    assert _first_status(copied_example, fragment) is status


def test_a_receipt_over_a_new_operator_replays_byte_identically(copied_example: Path) -> None:
    """The payload has no new field, so replay must reproduce it exactly.

    The extension deliberately keeps the flat pointer/operator/expected shape, and
    this is what pins that: if a new operator had needed a new member, the
    producer's digest and a counterparty's regeneration would differ.
    """
    manifest_path = _with_assertion(copied_example, 'operator = "between"\nexpected = [0, 2]')
    first = evaluate_manifest(load_manifest(manifest_path), copied_example / "evidence")
    again = evaluate_manifest(load_manifest(manifest_path), copied_example / "evidence")
    assert first.payload() == again.payload()
    assert json.dumps(first.payload(), sort_keys=True) == json.dumps(
        again.payload(), sort_keys=True
    )


def test_the_plan_round_trips_a_new_operator(copied_example: Path) -> None:
    """`plan._validate_assertion` accepts the widened vocabulary unchanged.

    It gates on `ASSERTION_OPERATORS` and on `expected_declared`, and every new
    operator declares an expected value, so no plan-side change was needed. This
    asserts that rather than assuming it.
    """
    from obligation_receipts.plan import build_evidence_plan, verify_evidence_plan

    manifest_path = _with_assertion(copied_example, 'operator = "in"\nexpected = [0, 1]')
    manifest = load_manifest(manifest_path)
    plan: dict[str, Any] = build_evidence_plan(manifest, include_local_details=True)
    verify_evidence_plan(plan, manifest)
    payload = plan["payload"]
    assert isinstance(payload, dict)
    obligations = payload["obligations"]
    assert isinstance(obligations, list)
    first = obligations[0]
    assert isinstance(first, dict)
    requirements = first["evidence_requirements"]
    assert isinstance(requirements, list)
    entry = requirements[0]
    assert isinstance(entry, dict)
    assertion = entry["assertion"]
    assert isinstance(assertion, dict)
    assert assertion["operator"] == "in"
    assert assertion["expected"] == [0, 1]
    assert assertion["expected_declared"] is True
