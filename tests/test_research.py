import csv
from pathlib import Path

import pytest

from obligation_receipts.research import ResearchError, analyze_ratings, load_ratings

HEADER = [
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
]


def _row(
    clause_id: str,
    classification: str,
    *,
    minutes: str = "2",
    interpretation: str = "false",
    handled: str = "false",
) -> list[str]:
    return [
        "sample",
        clause_id,
        "section",
        classification,
        "must",
        "evidence",
        "role",
        minutes,
        interpretation,
        handled,
        "",
    ]


def _write_csv(path: Path, rows: list[list[str]], header: list[str] = HEADER) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def test_perfect_agreement_reports_predeclared_metrics(tmp_path: Path) -> None:
    rows = [
        _row("1", "automated", minutes="1"),
        _row("2", "manual_review", minutes="3", interpretation="true"),
        _row("3", "external_evidence", minutes="5", handled="true"),
        _row("4", "unverifiable", minutes="7"),
    ]
    first = tmp_path / "a.csv"
    second = tmp_path / "b.csv"
    _write_csv(first, rows)
    independent_rows = [row.copy() for row in rows]
    independent_rows[0][-1] = "independently entered"
    _write_csv(second, independent_rows)
    report = analyze_ratings(first, second)
    assert report["total_frozen_clauses"] == 4
    assert report["raw_agreement"] == 1.0
    assert report["cohen_kappa"] == 1.0
    assert report["classifiable_rate"] == {
        "consensus": 0.75,
        "rater_a": 0.75,
        "rater_b": 0.75,
    }
    assert report["gate_status"] == "proceed"
    assert report["mapping_minutes_median"] == 4.0
    assert report["requires_interpretation_count"] == 1
    assert report["current_tool_already_handles_count"] == 1


def test_byte_identical_rater_files_cannot_emit_a_proceed_gate(tmp_path: Path) -> None:
    rows = [
        _row("1", "automated"),
        _row("2", "manual_review"),
        _row("3", "external_evidence"),
    ]
    first = tmp_path / "a.csv"
    second = tmp_path / "b.csv"
    _write_csv(first, rows)
    _write_csv(second, rows)
    with pytest.raises(ResearchError, match="byte-identical"):
        analyze_ratings(first, second)
    with pytest.raises(ResearchError, match="byte-identical"):
        analyze_ratings(first, first)


def test_single_category_kappa_is_reported_as_undefined(tmp_path: Path) -> None:
    first = tmp_path / "a.csv"
    second = tmp_path / "b.csv"
    rows = [_row("1", "automated"), _row("2", "automated")]
    _write_csv(first, rows)
    independent_rows = [row.copy() for row in rows]
    independent_rows[0][-1] = "independently entered"
    _write_csv(second, independent_rows)
    report = analyze_ratings(first, second)
    assert report["cohen_kappa"] is None
    assert report["gate_status"] == "indeterminate"


def test_low_agreement_triggers_warning(tmp_path: Path) -> None:
    first = tmp_path / "a.csv"
    second = tmp_path / "b.csv"
    _write_csv(first, [_row("1", "automated"), _row("2", "manual_review")])
    _write_csv(second, [_row("1", "unverifiable"), _row("2", "out_of_scope")])
    report = analyze_ratings(first, second)
    assert report["raw_agreement"] == 0.0
    assert report["gate_status"] == "serious_warning"


def test_rater_files_must_have_same_unique_frozen_keys(tmp_path: Path) -> None:
    first = tmp_path / "a.csv"
    second = tmp_path / "b.csv"
    _write_csv(first, [_row("1", "automated")])
    _write_csv(second, [_row("2", "automated")])
    with pytest.raises(ResearchError, match="same frozen clause keys"):
        analyze_ratings(first, second)
    _write_csv(first, [_row("1", "automated"), _row("1", "automated")])
    with pytest.raises(ResearchError, match="must be unique"):
        load_ratings(first)


@pytest.mark.parametrize(
    ("column", "value", "message"),
    [
        (3, "unknown", "classification"),
        (4, "maybe", "criticality"),
        (7, "-1", "nonnegative"),
        (7, "NaN", "finite"),
        (7, "1e999", "finite"),
        (8, "yes", "true or false"),
        (0, " spaced ", "whitespace"),
    ],
)
def test_invalid_rating_cells_are_rejected(
    tmp_path: Path,
    column: int,
    value: str,
    message: str,
) -> None:
    path = tmp_path / "ratings.csv"
    row = _row("1", "automated")
    row[column] = value
    _write_csv(path, [row])
    with pytest.raises(ResearchError, match=message):
        load_ratings(path)


def test_header_utf8_and_size_are_bounded(tmp_path: Path) -> None:
    path = tmp_path / "ratings.csv"
    _write_csv(path, [_row("1", "automated")], header=[*HEADER[:-1], "changed"])
    with pytest.raises(ResearchError, match="header"):
        load_ratings(path)
    path.write_bytes(b"\xff")
    with pytest.raises(ResearchError, match="UTF-8"):
        load_ratings(path)
    path.write_bytes(b"x" * (2 * 1024 * 1024 + 1))
    with pytest.raises(ResearchError, match="bounded"):
        load_ratings(path)


def test_empty_and_malformed_csv_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "ratings.csv"
    path.write_text("", encoding="utf-8")
    with pytest.raises(ResearchError, match="header"):
        load_ratings(path)
    path.write_text('sample_id,"unterminated', encoding="utf-8")
    with pytest.raises(ResearchError, match="malformed"):
        load_ratings(path)
