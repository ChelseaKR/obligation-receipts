"""The single documented CLI exit-code contract.

Every command draws from one band so that an automated acceptance pipeline can
tell an evaluated negative outcome apart from a tool or input error. That
distinction is the point: a `rejected` evaluation and an unreadable manifest are
different facts about a contract, and collapsing both into one code makes a
pipeline unable to report which one happened.

The bands are:

- `OK` — the tool read the declared evidence and every `must` obligation passed.
- `OBSERVED_FAILURE` — evidence was read and did not pass. A result document
  exists.
- `INPUT_ERROR` — the manifest, evidence root, arguments, or a supplied document
  could not be used. No result document is produced.
- `NOT_OBSERVED` — required evidence was absent or unusable, so no observation
  was made. Never an observed failure.
- `REVIEW_REQUIRED` — an attestation is unbound, malformed, or awaiting review.

`INPUT_ERROR` is reserved: it always means "no result document", and no
evaluated state ever maps onto it.
"""

from __future__ import annotations

from obligation_receipts.models import OverallStatus, ResultStatus

OK = 0
OBSERVED_FAILURE = 1
INPUT_ERROR = 2
NOT_OBSERVED = 3
REVIEW_REQUIRED = 4

_EVALUATION_EXIT_CODES: dict[OverallStatus, int] = {
    OverallStatus.ACCEPTED: OK,
    OverallStatus.ACCEPTED_WITH_FINDINGS: OK,
    OverallStatus.REJECTED: OBSERVED_FAILURE,
    OverallStatus.INCOMPLETE: NOT_OBSERVED,
}

_EVIDENCE_EXIT_CODES: dict[ResultStatus, int] = {
    ResultStatus.PASS: OK,
    ResultStatus.FAIL: OBSERVED_FAILURE,
    ResultStatus.MISSING: NOT_OBSERVED,
    ResultStatus.REVIEW_REQUIRED: REVIEW_REQUIRED,
}


def evaluation_exit_code(status: OverallStatus) -> int:
    """Map a whole-manifest evaluation state to its documented exit code.

    `accepted_with_findings` is an accepted state: every `must` obligation
    passed and only a `should` did not, so it exits `OK`.

    `incomplete` collapses missing evidence, awaiting review, and unverifiable
    into one aggregate, so it cannot honestly choose between `NOT_OBSERVED` and
    `REVIEW_REQUIRED`. It reports the weaker `NOT_OBSERVED`: nothing was
    observed to fail. Per-item codes remain available from `check-evidence`.
    """
    return _EVALUATION_EXIT_CODES[status]


def evidence_exit_code(status: ResultStatus) -> int:
    """Map one preserved evidence state to its documented exit code.

    `ResultStatus.UNVERIFIABLE` is deliberately absent. It is a property of an
    obligation that declares no evidence, so no evidence item can carry it; a
    lookup failure here is a broken manifest invariant, not a reportable state.
    """
    return _EVIDENCE_EXIT_CODES[status]
