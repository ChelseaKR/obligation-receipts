"""Deterministic metrics for the frozen two-rater discovery protocol."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from io import StringIO
from math import isfinite
from pathlib import Path
from statistics import median
from typing import cast

from obligation_receipts.canonical import sha256_bytes
from obligation_receipts.models import JsonValue
from obligation_receipts.paths import BoundedPathError, read_regular_file

_MAX_CSV_BYTES = 2 * 1024 * 1024
_MAX_ROWS = 10_000
_HEADER = (
    "sample_id",
    "clause_id",
    "source_locator",
    "classification",
    "criticality",
    "proposed_evidence",
    "accountable_owner",
    "mapping_minutes",
    "requires_interpretation",
    "current_tool_already_handles",
    "notes",
)
_CLASSIFICATIONS = (
    "automated",
    "manual_review",
    "external_evidence",
    "unverifiable",
    "out_of_scope",
)
_OBJECTIVE_CLASSIFICATIONS = {
    "automated",
    "manual_review",
    "external_evidence",
}
_CRITICALITIES = {"must", "should"}


class ResearchError(ValueError):
    """Raised when frozen discovery ratings are invalid or incomparable."""


@dataclass(frozen=True, slots=True)
class Rating:
    sample_id: str
    clause_id: str
    classification: str
    mapping_minutes: float
    requires_interpretation: bool
    current_tool_already_handles: bool

    @property
    def key(self) -> tuple[str, str]:
        return self.sample_id, self.clause_id


def _required_cell(row: list[str], index: int, field: str) -> str:
    value = row[index]
    if not value or value != value.strip():
        raise ResearchError(f"{field} must be non-empty without surrounding whitespace")
    return value


def _boolean_cell(row: list[str], index: int, field: str) -> bool:
    value = row[index]
    if value not in {"true", "false"}:
        raise ResearchError(f"{field} must be true or false")
    return value == "true"


def _minutes_cell(row: list[str], index: int) -> float:
    value = _required_cell(row, index, "mapping_minutes")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ResearchError("mapping_minutes must be a finite nonnegative number") from exc
    if not parsed.is_finite() or parsed < 0:
        raise ResearchError("mapping_minutes must be a finite nonnegative number")
    result = float(parsed)
    if not isfinite(result):
        raise ResearchError("mapping_minutes must be a finite nonnegative number")
    return result


def _parse_rating(row: list[str], row_number: int) -> Rating:
    if len(row) != len(_HEADER):
        raise ResearchError(f"row {row_number} does not match the frozen CSV columns")
    classification = _required_cell(row, 3, "classification")
    if classification not in _CLASSIFICATIONS:
        raise ResearchError(f"row {row_number} has an unsupported classification")
    criticality = _required_cell(row, 4, "criticality")
    if criticality not in _CRITICALITIES:
        raise ResearchError(f"row {row_number} has an unsupported criticality")
    for index, field in ((2, "source_locator"), (5, "proposed_evidence"), (6, "accountable_owner")):
        _required_cell(row, index, field)
    return Rating(
        sample_id=_required_cell(row, 0, "sample_id"),
        clause_id=_required_cell(row, 1, "clause_id"),
        classification=classification,
        mapping_minutes=_minutes_cell(row, 7),
        requires_interpretation=_boolean_cell(row, 8, "requires_interpretation"),
        current_tool_already_handles=_boolean_cell(row, 9, "current_tool_already_handles"),
    )


def load_ratings(path: Path) -> tuple[tuple[Rating, ...], str]:
    """Load and digest one bounded, frozen rater CSV."""
    try:
        data = read_regular_file(path, max_bytes=_MAX_CSV_BYTES)
        text = data.decode("utf-8")
        rows = list(csv.reader(StringIO(text, newline=""), strict=True))
    except UnicodeDecodeError as exc:
        raise ResearchError("rater CSV is not valid UTF-8") from exc
    except BoundedPathError as exc:
        raise ResearchError(f"rater CSV is not safely bounded: {exc}") from exc
    except csv.Error as exc:
        raise ResearchError(f"rater CSV is malformed: {exc}") from exc
    if not rows or tuple(rows[0]) != _HEADER:
        raise ResearchError("rater CSV header does not match the frozen template")
    if not 1 <= len(rows) - 1 <= _MAX_ROWS:
        raise ResearchError(f"rater CSV must contain 1-{_MAX_ROWS} data rows")
    ratings = tuple(_parse_rating(row, index) for index, row in enumerate(rows[1:], start=2))
    keys = [rating.key for rating in ratings]
    if len(keys) != len(set(keys)):
        raise ResearchError("rater CSV clause keys must be unique")
    return ratings, sha256_bytes(data)


def _rounded(value: float) -> float:
    return round(value, 6)


def analyze_ratings(rater_a_path: Path, rater_b_path: Path) -> dict[str, JsonValue]:
    """Validate two frozen files and compute predeclared agreement metrics."""
    rater_a, digest_a = load_ratings(rater_a_path)
    rater_b, digest_b = load_ratings(rater_b_path)
    if digest_a == digest_b:
        raise ResearchError(
            "rater CSVs are byte-identical and cannot demonstrate independent ratings"
        )
    a_by_key = {rating.key: rating for rating in rater_a}
    b_by_key = {rating.key: rating for rating in rater_b}
    if set(a_by_key) != set(b_by_key):
        raise ResearchError("rater CSVs do not contain the same frozen clause keys")
    keys = sorted(a_by_key)
    total = len(keys)
    confusion = {first: {second: 0 for second in _CLASSIFICATIONS} for first in _CLASSIFICATIONS}
    for key in keys:
        confusion[a_by_key[key].classification][b_by_key[key].classification] += 1
    agreements = sum(a_by_key[key].classification == b_by_key[key].classification for key in keys)
    raw_agreement = agreements / total
    expected_agreement = sum(
        (
            sum(rating.classification == label for rating in rater_a)
            / total
            * sum(rating.classification == label for rating in rater_b)
            / total
        )
        for label in _CLASSIFICATIONS
    )
    kappa = (
        None
        if expected_agreement == 1
        else _rounded((raw_agreement - expected_agreement) / (1 - expected_agreement))
    )
    consensus_classifiable = sum(
        a_by_key[key].classification == b_by_key[key].classification
        and a_by_key[key].classification in _OBJECTIVE_CLASSIFICATIONS
        for key in keys
    )
    consensus_rate = consensus_classifiable / total
    warning = consensus_rate < 0.25 or (kappa is not None and kappa < 0.50)
    proceed = consensus_rate >= 0.40 and kappa is not None and kappa >= 0.70
    gate_status = "serious_warning" if warning else "proceed" if proceed else "indeterminate"
    all_minutes = [rating.mapping_minutes for rating in (*rater_a, *rater_b)]
    return {
        "classifiable_rate": {
            "consensus": _rounded(consensus_rate),
            "rater_a": _rounded(
                sum(rating.classification in _OBJECTIVE_CLASSIFICATIONS for rating in rater_a)
                / total
            ),
            "rater_b": _rounded(
                sum(rating.classification in _OBJECTIVE_CLASSIFICATIONS for rating in rater_b)
                / total
            ),
        },
        "cohen_kappa": kappa,
        "confusion_matrix": cast(JsonValue, confusion),
        "current_tool_already_handles_count": sum(
            a_by_key[key].current_tool_already_handles or b_by_key[key].current_tool_already_handles
            for key in keys
        ),
        "gate_status": gate_status,
        "mapping_minutes_median": _rounded(float(median(all_minutes))),
        "protocol": "obligation-receipts/two-rater-discovery/v0.1",
        "rater_a_sha256": digest_a,
        "rater_b_sha256": digest_b,
        "raw_agreement": _rounded(raw_agreement),
        "requires_interpretation_count": sum(
            a_by_key[key].requires_interpretation or b_by_key[key].requires_interpretation
            for key in keys
        ),
        "thresholds": {
            "proceed_classifiable_rate": 0.40,
            "proceed_kappa": 0.70,
            "warning_classifiable_rate_below": 0.25,
            "warning_kappa_below": 0.50,
        },
        "total_frozen_clauses": total,
    }
