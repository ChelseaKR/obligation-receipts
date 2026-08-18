import pytest

from obligation_receipts.exit_codes import (
    INPUT_ERROR,
    NOT_OBSERVED,
    OBSERVED_FAILURE,
    OK,
    REVIEW_REQUIRED,
    evaluation_exit_code,
    evidence_exit_code,
)
from obligation_receipts.models import OverallStatus, ResultStatus


def test_every_overall_status_has_a_declared_exit_code() -> None:
    assert {status: evaluation_exit_code(status) for status in OverallStatus} == {
        OverallStatus.ACCEPTED: OK,
        OverallStatus.ACCEPTED_WITH_FINDINGS: OK,
        OverallStatus.REJECTED: OBSERVED_FAILURE,
        OverallStatus.INCOMPLETE: NOT_OBSERVED,
    }


def test_every_observable_evidence_state_has_a_declared_exit_code() -> None:
    assert {
        status: evidence_exit_code(status)
        for status in ResultStatus
        if status is not ResultStatus.UNVERIFIABLE
    } == {
        ResultStatus.PASS: OK,
        ResultStatus.FAIL: OBSERVED_FAILURE,
        ResultStatus.MISSING: NOT_OBSERVED,
        ResultStatus.REVIEW_REQUIRED: REVIEW_REQUIRED,
    }


def test_unverifiable_is_not_an_evidence_state() -> None:
    with pytest.raises(KeyError):
        evidence_exit_code(ResultStatus.UNVERIFIABLE)


def test_input_error_is_reserved_for_producing_no_result_document() -> None:
    evaluated = {evaluation_exit_code(status) for status in OverallStatus}
    observed = {
        evidence_exit_code(status)
        for status in ResultStatus
        if status is not ResultStatus.UNVERIFIABLE
    }
    assert INPUT_ERROR not in evaluated | observed


def test_codes_are_distinct() -> None:
    codes = [OK, OBSERVED_FAILURE, INPUT_ERROR, NOT_OBSERVED, REVIEW_REQUIRED]
    assert len(set(codes)) == len(codes)
