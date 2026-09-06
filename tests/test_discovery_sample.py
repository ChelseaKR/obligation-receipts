"""Bindings between the discovery sample record, the rater instrument, and the tool.

Three artifacts have to agree before two raters can produce a comparable pair of
workbooks, and nothing structural made them agree (#15):

- `docs/discovery/public-sample-candidates.md` declares the samples and locators;
- `docs/discovery/rater-workbook-prepared.csv` is the instrument each rater copies;
- `obligation_receipts.research` defines the columns `research-metrics` accepts.

Drift between any two of them is invisible until both raters have finished and
`research-metrics` refuses the result, which is the most expensive moment to
discover it.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

import pytest

import obligation_receipts.research as research
from obligation_receipts.research import ResearchError, load_ratings

_DISCOVERY = Path(__file__).parents[1] / "docs" / "discovery"
_INSTRUMENT = _DISCOVERY / "rater-workbook-prepared.csv"
_RECORD = _DISCOVERY / "public-sample-candidates.md"

# `sample_id`, `clause_id` and `source_locator` identify a clause. Everything
# else is the rater's judgment and must be blank in the shipped instrument.
_IDENTIFICATION_COLUMNS = 3


def _instrument_rows() -> list[list[str]]:
    with _INSTRUMENT.open(encoding="utf-8", newline="") as handle:
        return list(csv.reader(handle, strict=True))


def _declared_sample_ids() -> list[str]:
    """Sample IDs the record assigns, read from its own `**Sample ID:**` lines."""
    text = _RECORD.read_text(encoding="utf-8")
    return re.findall(r"^- \*\*Sample ID:\*\* `([^`]+)`$", text, flags=re.MULTILINE)


def test_instrument_header_matches_the_frozen_protocol() -> None:
    """The instrument must be readable by the tool that will consume its copies."""
    assert tuple(_instrument_rows()[0]) == research._HEADER


def test_instrument_carries_no_ratings() -> None:
    """A blank instrument is the whole point: ratings must come from raters.

    If a filled-in copy were ever committed here, both raters would start from
    somebody else's answers and the independence the protocol exists to measure
    would be gone before either of them opened the file. Cheaper to assert than
    to detect afterwards, because a plausible filled workbook looks exactly like
    a real one.
    """
    for number, row in enumerate(_instrument_rows()[1:], start=2):
        judgment = row[_IDENTIFICATION_COLUMNS:]
        assert judgment == [""] * len(judgment), f"row {number} carries a rating"


def test_instrument_identifies_every_clause() -> None:
    for number, row in enumerate(_instrument_rows()[1:], start=2):
        for index, field in enumerate(research._HEADER[:_IDENTIFICATION_COLUMNS]):
            value = row[index]
            assert value and value == value.strip(), f"row {number} has an empty {field}"


def test_instrument_clause_keys_are_unique() -> None:
    keys = [(row[0], row[1]) for row in _instrument_rows()[1:]]
    assert len(keys) == len(set(keys))


def test_instrument_and_record_declare_the_same_samples() -> None:
    """Neither file may gain or lose a sample without the other."""
    declared = _declared_sample_ids()
    assert declared, "the record must assign at least one sample ID"
    assert sorted({row[0] for row in _instrument_rows()[1:]}) == sorted(declared)


def test_every_instrument_locator_appears_in_the_record() -> None:
    """A clause key in the instrument must point at a locator the record vouches for.

    This is the binding that catches a corrected page number applied to one file
    and not the other -- the exact defect the 2026-09-06 verification found in
    the record itself, where all ten THECB locators were one page low.
    """
    text = _RECORD.read_text(encoding="utf-8")
    for number, row in enumerate(_instrument_rows()[1:], start=2):
        assert row[2] in text, f"row {number} locator {row[2]!r} is not in the record"


def test_the_blank_instrument_is_not_mistakable_for_a_completed_workbook(
    tmp_path: Path,
) -> None:
    """`research-metrics` must refuse the instrument until a rater has filled it.

    Otherwise the failure mode is a run that succeeds on blank judgment cells and
    reports a rate over nothing -- absence rendered as a measurement.
    """
    copied = tmp_path / "instrument.csv"
    copied.write_bytes(_INSTRUMENT.read_bytes())
    with pytest.raises(ResearchError):
        load_ratings(copied)
