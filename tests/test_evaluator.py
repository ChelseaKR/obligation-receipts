import json
from dataclasses import replace
from pathlib import Path
from shutil import copytree, rmtree
from typing import cast

import pytest

from obligation_receipts.canonical import canonical_json_bytes, sha256_bytes
from obligation_receipts.evaluator import (
    _compare,
    _evaluate_assertion,
    _load_json_artifact,
    _overall_status,
    evaluate_manifest,
)
from obligation_receipts.manifest import load_manifest
from obligation_receipts.models import (
    Classification,
    Criticality,
    EvidenceKind,
    EvidenceSpec,
    JsonValue,
    ObligationResult,
    OverallStatus,
    ResultStatus,
)
from obligation_receipts.pointer import resolve as _json_pointer


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _result(status: ResultStatus, criticality: Criticality) -> ObligationResult:
    return ObligationResult(
        obligation_id=f"{criticality}-{status}",
        clause_ref="test",
        classification=Classification.AUTOMATED,
        criticality=criticality,
        status=status,
        evidence=(),
    )


def test_example_reports_explicit_unverifiable_finding(example_manifest: Path) -> None:
    evaluation = evaluate_manifest(
        load_manifest(example_manifest), example_manifest.parent / "evidence"
    )
    assert evaluation.overall_status is OverallStatus.ACCEPTED_WITH_FINDINGS
    assert [item.status for item in evaluation.results] == [
        ResultStatus.PASS,
        ResultStatus.PASS,
        ResultStatus.PASS,
        ResultStatus.UNVERIFIABLE,
    ]
    payload = evaluation.payload()
    counts = payload["obligation_counts"]
    assert isinstance(counts, dict)
    assert counts["unverifiable"] == 1


def test_failed_must_obligation_rejects(copied_example: Path) -> None:
    _write_json(
        copied_example / "evidence" / "automated" / "axe-summary.json",
        {"summary": {"critical_violations": 1}},
    )
    evaluation = evaluate_manifest(
        load_manifest(copied_example / "obligations.toml"),
        copied_example / "evidence",
    )
    assert evaluation.overall_status is OverallStatus.REJECTED
    assert evaluation.results[0].status is ResultStatus.FAIL


def test_missing_must_evidence_is_incomplete(copied_example: Path) -> None:
    manifest = load_manifest(copied_example / "obligations.toml")
    (copied_example / "evidence" / "automated" / "axe-summary.json").unlink()
    evaluation = evaluate_manifest(manifest, copied_example / "evidence")
    assert evaluation.overall_status is OverallStatus.INCOMPLETE
    assert evaluation.results[0].status is ResultStatus.MISSING


@pytest.mark.parametrize("status", ["fail", "unknown"])
def test_manual_attestation_fail_closed(copied_example: Path, status: str) -> None:
    path = copied_example / "evidence" / "manual" / "keyboard-review.json"
    attestation = json.loads(path.read_text(encoding="utf-8"))
    attestation["status"] = status
    _write_json(path, attestation)
    evaluation = evaluate_manifest(
        load_manifest(copied_example / "obligations.toml"),
        copied_example / "evidence",
    )
    expected = ResultStatus.FAIL if status == "fail" else ResultStatus.REVIEW_REQUIRED
    assert evaluation.results[1].status is expected
    expected_overall = OverallStatus.REJECTED if status == "fail" else OverallStatus.INCOMPLETE
    assert evaluation.overall_status is expected_overall


def test_attestation_must_be_object_and_content_bound(copied_example: Path) -> None:
    path = copied_example / "evidence" / "manual" / "keyboard-review.json"
    _write_json(path, ["not", "an", "attestation"])
    evaluation = evaluate_manifest(
        load_manifest(copied_example / "obligations.toml"),
        copied_example / "evidence",
    )
    assert evaluation.results[1].status is ResultStatus.REVIEW_REQUIRED


def test_attestation_rejects_extra_and_duplicate_fields(copied_example: Path) -> None:
    path = copied_example / "evidence" / "manual" / "keyboard-review.json"
    attestation = json.loads(path.read_text(encoding="utf-8"))
    attestation["comment"] = "unbounded extension"
    _write_json(path, attestation)
    evaluation = evaluate_manifest(
        load_manifest(copied_example / "obligations.toml"),
        copied_example / "evidence",
    )
    assert evaluation.results[1].status is ResultStatus.REVIEW_REQUIRED

    del attestation["comment"]
    raw = json.dumps(attestation).replace('"status": "pass"', '"status": "pass", "status": "fail"')
    path.write_text(raw, encoding="utf-8")
    evaluation = evaluate_manifest(
        load_manifest(copied_example / "obligations.toml"),
        copied_example / "evidence",
    )
    assert evaluation.results[1].status is ResultStatus.REVIEW_REQUIRED


def test_attestation_rejects_whitespace_only_required_field(copied_example: Path) -> None:
    path = copied_example / "evidence" / "manual" / "keyboard-review.json"
    attestation = json.loads(path.read_text(encoding="utf-8"))
    attestation["reviewer"] = "   "
    _write_json(path, attestation)
    evaluation = evaluate_manifest(
        load_manifest(copied_example / "obligations.toml"),
        copied_example / "evidence",
    )
    assert evaluation.results[1].status is ResultStatus.REVIEW_REQUIRED


@pytest.mark.parametrize(
    ("field", "wrong_value"),
    [
        ("contract_id", "some-other-contract"),
        ("contract_version", "0.9"),
        ("obligation_id", "a3-external-acr"),
        ("schema_version", "obligation-receipts/attestation/v0.2"),
    ],
)
def test_attestation_requires_every_identity_binding_independently(
    copied_example: Path,
    field: str,
    wrong_value: str,
) -> None:
    """Each identity binding must be load-bearing on its own.

    `manifest_sha256` is deliberately left correct in every case, so an
    attestation that is content-bound to this exact manifest still cannot be
    replayed against a different contract, a different version of it, a
    different obligation, or read as a format it does not claim to be. Without
    a case per field, deleting any one of these four comparisons left the whole
    suite green: the remaining bindings covered for the deleted one.

    `schema_version` is the sharpest of the four. An attestation self-labelled
    `.../attestation/v0.2` announces that it is a different format; accepting
    it means evaluating unknown fields under v0.1 rules and reporting `pass`.
    """
    path = copied_example / "evidence" / "manual" / "keyboard-review.json"
    attestation = json.loads(path.read_text(encoding="utf-8"))
    assert attestation[field] != wrong_value
    attestation[field] = wrong_value
    _write_json(path, attestation)
    manifest = load_manifest(copied_example / "obligations.toml")
    assert attestation["manifest_sha256"] == manifest.manifest_sha256

    evaluation = evaluate_manifest(manifest, copied_example / "evidence")
    assert evaluation.results[1].status is ResultStatus.REVIEW_REQUIRED
    assert evaluation.overall_status is OverallStatus.INCOMPLETE


def test_one_attestation_cannot_satisfy_two_declared_evidence_ids(
    example_manifest: Path,
) -> None:
    manifest = load_manifest(example_manifest)
    manual = manifest.obligations[1]
    first = manual.evidence[0]
    second = replace(first, evidence_id="a2-second-review", path=first.path)
    duplicated = replace(
        manifest,
        obligations=(
            manifest.obligations[0],
            replace(manual, evidence=(first, second)),
            *manifest.obligations[2:],
        ),
    )
    evaluation = evaluate_manifest(duplicated, example_manifest.parent / "evidence")
    results = evaluation.results[1].evidence
    assert [item.status for item in results] == [
        ResultStatus.PASS,
        ResultStatus.REVIEW_REQUIRED,
    ]
    assert evaluation.results[1].status is ResultStatus.REVIEW_REQUIRED


@pytest.mark.parametrize(
    ("operator", "expected", "actual", "passed"),
    [
        ("eq", 3, 3, True),
        ("ne", 3, 4, True),
        ("gt", 3, 4, True),
        ("gte", 4, 4, True),
        ("lt", 5, 4, True),
        ("lte", 4, 4, True),
        ("gt", True, 4, False),
        ("eq", 1, True, False),
        ("eq", False, 0, False),
        ("ne", 1, True, True),
        ("gt", "3", 4, False),
    ],
)
def test_assertion_operators(
    tmp_path: Path,
    operator: str,
    expected: object,
    actual: object,
    passed: bool,
) -> None:
    _write_json(tmp_path / "artifact.json", {"value": actual})
    spec = EvidenceSpec(
        evidence_id="assertion-test",
        kind=EvidenceKind.JSON_ASSERTION,
        path="artifact.json",
        pointer="/value",
        operator=operator,
        expected=expected,  # type: ignore[arg-type]
    )
    result = _evaluate_assertion(spec, tmp_path)
    assert (result.status is ResultStatus.PASS) is passed


def test_exists_accepts_present_json_null(tmp_path: Path) -> None:
    _write_json(tmp_path / "artifact.json", {"present": None})
    spec = EvidenceSpec(
        evidence_id="exists-test",
        kind=EvidenceKind.JSON_ASSERTION,
        path="artifact.json",
        pointer="/present",
        operator="exists",
    )
    assert _evaluate_assertion(spec, tmp_path).status is ResultStatus.PASS


def test_json_pointer_supports_arrays_and_escaping() -> None:
    found, value = _json_pointer({"a/b": [{"~key": 7}]}, "/a~1b/0/~0key")
    assert found is True
    assert value == 7
    assert _json_pointer({"items": []}, "/items/2") == (False, None)
    assert _json_pointer({"items": []}, "/items/nope") == (False, None)
    assert _json_pointer(1, "/anything") == (False, None)
    assert _json_pointer({"root": 1}, "") == (True, {"root": 1})


@pytest.mark.parametrize("index", ["-1", "+1", "01", "00", chr(0x661), "1.0", ""])
def test_json_pointer_rejects_noncanonical_array_indices(index: str) -> None:
    assert _json_pointer({"items": ["zero", "one"]}, f"/items/{index}") == (False, None)


def test_json_pointer_accepts_canonical_nonnegative_array_indices() -> None:
    assert _json_pointer(["zero", "one"], "/0") == (True, "zero")
    assert _json_pointer(["zero", "one"], "/1") == (True, "one")


def test_json_pointer_rejects_resource_exhausting_array_index() -> None:
    found, actual = _json_pointer(["zero"], f"/{'9' * 10_000}")
    assert found is False
    assert actual is None


@pytest.mark.parametrize("pointer", ["not-a-pointer", "/~", "/~2"])
def test_json_pointer_rejects_malformed_pointer_syntax(pointer: str) -> None:
    assert _json_pointer({"~2": 1}, pointer) == (False, None)


def test_invalid_or_oversized_artifact_is_missing(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{", encoding="utf-8")
    spec = EvidenceSpec(
        evidence_id="bad-json",
        kind=EvidenceKind.JSON_ASSERTION,
        path="bad.json",
        pointer="/value",
        operator="eq",
        expected=1,
    )
    assert _evaluate_assertion(spec, tmp_path).status is ResultStatus.MISSING
    path.write_bytes(b" " * (2 * 1024 * 1024 + 1))
    assert _evaluate_assertion(spec, tmp_path).status is ResultStatus.MISSING


@pytest.mark.parametrize(
    "document",
    [
        '{"value": 1, "value": 2}',
        '{"value": NaN}',
        '{"value": Infinity}',
        '{"value": -Infinity}',
    ],
)
def test_ambiguous_json_artifact_is_missing(tmp_path: Path, document: str) -> None:
    (tmp_path / "artifact.json").write_text(document, encoding="utf-8")
    spec = EvidenceSpec(
        evidence_id="strict-json",
        kind=EvidenceKind.JSON_ASSERTION,
        path="artifact.json",
        pointer="/value",
        operator="eq",
        expected=1,
    )
    assert _evaluate_assertion(spec, tmp_path).status is ResultStatus.MISSING


def test_artifact_rejects_invalid_utf8_and_excessive_nesting(tmp_path: Path) -> None:
    path = tmp_path / "artifact.json"
    spec = EvidenceSpec(
        evidence_id="bounded-json",
        kind=EvidenceKind.JSON_ASSERTION,
        path="artifact.json",
        pointer="",
        operator="exists",
    )
    path.write_bytes(b"\xff")
    assert _evaluate_assertion(spec, tmp_path).status is ResultStatus.MISSING
    path.write_text("[" * 66 + "0" + "]" * 66, encoding="utf-8")
    assert _evaluate_assertion(spec, tmp_path).status is ResultStatus.MISSING


def test_invalid_observed_artifact_retains_its_content_digest(tmp_path: Path) -> None:
    malformed = b'{"value":'
    (tmp_path / "artifact.json").write_bytes(malformed)
    assertion = EvidenceSpec(
        evidence_id="bounded-json",
        kind=EvidenceKind.JSON_ASSERTION,
        path="artifact.json",
        pointer="/value",
        operator="eq",
        expected=1,
    )
    result = _evaluate_assertion(assertion, tmp_path)
    assert result.status is ResultStatus.MISSING
    assert result.artifact_sha256 == sha256_bytes(malformed)


def test_artifact_digest_is_bound_to_parsed_byte_snapshot(tmp_path: Path) -> None:
    path = tmp_path / "artifact.json"
    original = b'{"value":1}'
    path.write_bytes(original)
    document, digest = _load_json_artifact(tmp_path, "artifact.json")
    path.write_bytes(b'{"value":2}')
    assert document == {"value": 1}
    assert digest == sha256_bytes(original)


def test_defensive_assertion_shape_fails_closed(tmp_path: Path) -> None:
    _write_json(tmp_path / "artifact.json", {"value": 1})
    spec = EvidenceSpec(
        evidence_id="invalid-in-memory-spec",
        kind=EvidenceKind.JSON_ASSERTION,
        path="artifact.json",
    )
    assert _evaluate_assertion(spec, tmp_path).status is ResultStatus.MISSING


def test_overall_status_algebra() -> None:
    assert (
        _overall_status((_result(ResultStatus.PASS, Criticality.MUST),)) is OverallStatus.ACCEPTED
    )
    assert (
        _overall_status(
            (
                _result(ResultStatus.PASS, Criticality.MUST),
                _result(ResultStatus.FAIL, Criticality.SHOULD),
            )
        )
        is OverallStatus.ACCEPTED_WITH_FINDINGS
    )
    assert (
        _overall_status((_result(ResultStatus.UNVERIFIABLE, Criticality.MUST),))
        is OverallStatus.INCOMPLETE
    )
    assert (
        _overall_status((_result(ResultStatus.FAIL, Criticality.MUST),)) is OverallStatus.REJECTED
    )


def test_pointer_descending_through_a_scalar_fails_without_raising(tmp_path: Path) -> None:
    """Regression test for #24.

    A manifest pointer that walks into a scalar (`/a/b` where `a` is a string)
    is well formed and reaches the evaluator. It must resolve to "not found"
    and become a bounded result, never an exception out of the evaluator.
    """
    _write_json(tmp_path / "artifact.json", {"a": "scalar"})
    spec = EvidenceSpec(
        evidence_id="scalar-descent",
        kind=EvidenceKind.JSON_ASSERTION,
        path="artifact.json",
        pointer="/a/b",
        operator="eq",
        expected="anything",
    )
    result = _evaluate_assertion(spec, tmp_path)
    assert result.status is ResultStatus.FAIL
    assert result.artifact_sha256 is not None


def test_pointer_reports_an_absent_object_member_as_not_found() -> None:
    assert _json_pointer({"present": 1}, "/absent") == (False, None)
    assert _json_pointer({"outer": {"present": 1}}, "/outer/absent") == (False, None)


@pytest.mark.parametrize("operator", ["exists", "matches", ""])
@pytest.mark.parametrize("value", [1, 1.5, "value", None])
def test_compare_refuses_operators_it_does_not_answer(operator: str, value: object) -> None:
    """`_compare` answers only the six comparison operators, fail-closed.

    `exists` is answered one level up, from the pointer's found flag, because a
    member whose value is JSON `null` exists. `_compare` deliberately no longer
    carries a second, contradicting definition of it (#24); asked anyway, it
    returns the fail-closed default rather than inventing an answer.
    """
    assert _compare(cast(JsonValue, value), operator, cast(JsonValue, value)) is False


def test_payload_digest_is_independent_of_how_the_artifact_became_unreadable(
    tmp_path: Path, example_root: Path
) -> None:
    """One `missing` verdict must digest one way, whatever the operating system raised.

    The payload is the replay contract. If the cause reaches the payload, a
    receipt written where an artifact is absent fails replay where the same
    artifact is merely unreachable, and `verify` reports that environment
    difference as an integrity finding about the receipt.
    """
    digests = set()
    for cause in ("absent", "unreadable_parent"):
        root = tmp_path / cause
        copytree(example_root, root)
        artifact = root / "evidence" / "automated" / "axe-summary.json"
        if cause == "absent":
            artifact.unlink()
        else:
            rmtree(artifact.parent)
            artifact.parent.write_text("not a directory", encoding="utf-8")

        evaluation = evaluate_manifest(load_manifest(root / "obligations.toml"), root / "evidence")
        assert evaluation.results[0].evidence[0].status is ResultStatus.MISSING
        digests.add(sha256_bytes(canonical_json_bytes(evaluation.payload())))

    assert len(digests) == 1, (
        "the payload digest depends on which OSError the filesystem raised; "
        "receipts are no longer replayable across environments"
    )
