"""A hash-chained ledger of one contract's evaluations.

Issue 55. The receipt proves a bounded evaluation; the ledger proves the
*sequence* of them. Each test maps to one of that issue's "Done when" bullets,
or to the distinction the exit-code contract turns on: a broken chain is a
**finding** about the records and exits 1, while a ledger that cannot be read at
all is an **input error** and exits 2. Collapsing those would tell a caller that
a corrupt file and a tampered entry are the same fact.

The tampers the chain cannot see are asserted too, and asserted as passing. A
test suite that only demonstrated what the chain catches would leave the PASS
line reading as a stronger claim than it is.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from obligation_receipts.cli import main
from obligation_receipts.exit_codes import INPUT_ERROR, NOT_OBSERVED, OBSERVED_FAILURE, OK
from obligation_receipts.ledger import (
    GENESIS_PREV_HASH,
    LEDGER_SCHEMA_VERSION,
    PASS_LIMITS,
    LedgerError,
    append_receipt,
    compute_entry_hash,
    read_ledger,
    verify_chain,
)
from obligation_receipts.receipt import load_receipt, verify_receipt


def _evaluate(example: Path, out: Path, when: str, *, expect: int = OK) -> None:
    """Evaluate and write a receipt, asserting the exit code it is expected to give.

    ``expect`` is not a convenience. The second contract below evaluates to
    `incomplete` (exit 3) because its attestations are bound to the *original*
    contract id, which is correct and is the point: the receipt is a real,
    verifiable receipt for a different contract, which is exactly what the
    ledger has to refuse.
    """

    assert (
        main(
            [
                "evaluate",
                str(example / "obligations.toml"),
                "--evidence-root",
                str(example / "evidence"),
                "--out",
                str(out),
                "--generated-at",
                when,
            ]
        )
        == expect
    )


def _three_receipts(example: Path, tmp_path: Path) -> list[Path]:
    """Three evaluations of one contract, at three declared times.

    The times differ so the entries differ; the evidence does not, so every
    `payload_sha256` is identical. That is deliberate — it is what an acceptance
    lead re-running the same evaluation actually produces, and it means the
    chain has to distinguish the entries by index and link rather than by their
    contents happening to differ.
    """

    receipts = []
    for month in (1, 2, 3):
        path = tmp_path / f"receipt-{month}.json"
        _evaluate(example, path, f"2026-0{month}-01T00:00:00+00:00")
        receipts.append(path)
    return receipts


def _append_all(receipts: list[Path], ledger: Path) -> None:
    for receipt in receipts:
        assert main(["ledger-append", str(receipt), "--ledger", str(ledger)]) == OK


def _lines(ledger: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines() if line]


def _rewrite(ledger: Path, records: list[dict[str, Any]]) -> None:
    ledger.write_text(
        "".join(
            json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n" for record in records
        ),
        encoding="utf-8",
    )


# --- "Done when": three receipts append and verify -------------------------


def test_three_receipts_append_and_the_chain_verifies(
    copied_example: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ledger = tmp_path / "contract.ledger.jsonl"
    _append_all(_three_receipts(copied_example, tmp_path), ledger)
    capsys.readouterr()

    assert main(["ledger-verify", str(ledger)]) == OK
    report = json.loads(capsys.readouterr().out)
    assert report["entries"] == 3
    assert report["status"] == "verified"
    assert report["problems"] == []

    entries = read_ledger(ledger)
    assert [entry.index for entry in entries] == [0, 1, 2]
    assert entries[0].prev_hash == GENESIS_PREV_HASH
    assert entries[1].prev_hash == entries[0].entry_hash
    assert entries[2].prev_hash == entries[1].entry_hash


def test_the_pass_output_states_what_a_clean_chain_does_not_prove(
    copied_example: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """PASS must not be readable as more than it is.

    Every limitation the module argues for is printed, and the list is read from
    the module rather than retyped here, so a limitation dropped from one is
    dropped from both and this test cannot silently stop covering it.
    """

    ledger = tmp_path / "contract.ledger.jsonl"
    _append_all(_three_receipts(copied_example, tmp_path), ledger)
    capsys.readouterr()

    main(["ledger-verify", str(ledger)])
    report = json.loads(capsys.readouterr().out)

    assert report["limitations"] == list(PASS_LIMITS)
    assert len(PASS_LIMITS) == 4


# --- "Done when": edit, reorder, or insert fails, naming the index ---------


def test_editing_a_middle_entry_breaks_the_chain_and_names_its_index(
    copied_example: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ledger = tmp_path / "contract.ledger.jsonl"
    _append_all(_three_receipts(copied_example, tmp_path), ledger)
    records = _lines(ledger)
    records[1]["overall_status"] = "accepted"
    _rewrite(ledger, records)
    capsys.readouterr()

    assert main(["ledger-verify", str(ledger)]) == OBSERVED_FAILURE
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "broken"
    assert any("entry 1" in problem for problem in report["problems"])
    assert any("altered" in problem for problem in report["problems"])


def test_reordering_two_entries_breaks_the_chain(
    copied_example: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Swapping two lines leaves every entry's own hash intact.

    So the index check and the link check are what catch this, not the hash
    check — which is why `verify_chain` runs all three rather than the one that
    happens to catch an edit.
    """

    ledger = tmp_path / "contract.ledger.jsonl"
    _append_all(_three_receipts(copied_example, tmp_path), ledger)
    records = _lines(ledger)
    records[1], records[2] = records[2], records[1]
    _rewrite(ledger, records)
    capsys.readouterr()

    assert main(["ledger-verify", str(ledger)]) == OBSERVED_FAILURE
    problems = json.loads(capsys.readouterr().out)["problems"]
    assert any("not contiguous" in problem for problem in problems)


def test_inserting_an_entry_breaks_the_chain(
    copied_example: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ledger = tmp_path / "contract.ledger.jsonl"
    _append_all(_three_receipts(copied_example, tmp_path), ledger)
    records = _lines(ledger)
    records.insert(1, dict(records[0]))
    _rewrite(ledger, records)
    capsys.readouterr()

    assert main(["ledger-verify", str(ledger)]) == OBSERVED_FAILURE
    problems = json.loads(capsys.readouterr().out)["problems"]
    assert problems
    assert any("entry 1" in problem or "entry 0" in problem for problem in problems)


def test_an_entry_spliced_from_another_chain_breaks_only_the_link_check(
    copied_example: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The tamper the `prev_hash` check exists for, and the only one it alone catches.

    Written because a negative control found the link check was dead weight
    against every other fixture here: deleting `if entry.prev_hash !=
    expected_prev` left the whole suite green, because an edit is caught by the
    hash check and a reorder, insertion or removal by the index check.

    So this splices a *genuine* entry from a second chain of the same contract
    into the first, at the same index. Its own hash recomputes correctly and the
    indices stay contiguous 0,1,2 — nothing is malformed. What is wrong is that
    it does not follow the entry before it, and that is the whole of what the
    link check is for.
    """

    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"
    _append_all(_three_receipts(copied_example, tmp_path), first)
    later = []
    for month in (4, 5, 6):
        path = tmp_path / f"later-{month}.json"
        _evaluate(copied_example, path, f"2026-0{month}-01T00:00:00+00:00")
        later.append(path)
    _append_all(later, second)

    records = _lines(first)
    donor = _lines(second)[1]
    assert donor["index"] == records[1]["index"] == 1
    assert donor["prev_hash"] != records[1]["prev_hash"]
    records[1] = donor
    _rewrite(first, records)
    capsys.readouterr()

    assert main(["ledger-verify", str(first)]) == OBSERVED_FAILURE
    problems = json.loads(capsys.readouterr().out)["problems"]
    assert problems
    assert all("does not link" in problem for problem in problems), problems
    assert any("entry 1" in problem for problem in problems)


def test_removing_a_middle_entry_breaks_the_chain(
    copied_example: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ledger = tmp_path / "contract.ledger.jsonl"
    _append_all(_three_receipts(copied_example, tmp_path), ledger)
    records = _lines(ledger)
    del records[1]
    _rewrite(ledger, records)
    capsys.readouterr()

    assert main(["ledger-verify", str(ledger)]) == OBSERVED_FAILURE
    assert json.loads(capsys.readouterr().out)["problems"]


# --- the tampers the chain cannot see, asserted as passing -----------------


def test_entries_deleted_from_the_end_still_verify(
    copied_example: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A limitation the PASS line states. Asserted so it stays true or stops being claimed.

    Nothing outside the file records how long the chain should be, so a truncated
    chain is indistinguishable from a shorter history. If this ever starts
    failing, the ledger has gained a property its own output denies having.
    """

    ledger = tmp_path / "contract.ledger.jsonl"
    _append_all(_three_receipts(copied_example, tmp_path), ledger)
    _rewrite(ledger, _lines(ledger)[:2])
    capsys.readouterr()

    assert main(["ledger-verify", str(ledger)]) == OK
    assert json.loads(capsys.readouterr().out)["entries"] == 2


def test_a_wholesale_rewrite_with_recomputed_hashes_still_verifies(
    copied_example: Path, tmp_path: Path
) -> None:
    """The hash has no secret. The chain proves integrity, never authorship."""

    ledger = tmp_path / "contract.ledger.jsonl"
    _append_all(_three_receipts(copied_example, tmp_path), ledger)
    records = _lines(ledger)

    previous = GENESIS_PREV_HASH
    for position, record in enumerate(records):
        record["index"] = position
        record["overall_status"] = "accepted"
        record["prev_hash"] = previous
        record.pop("entry_hash")
        from obligation_receipts.ledger import LedgerEntry

        forged = LedgerEntry(
            entry_hash="", **{k: v for k, v in record.items() if k != "schema_version"}
        )
        record["entry_hash"] = compute_entry_hash(forged)
        record["schema_version"] = LEDGER_SCHEMA_VERSION
        previous = record["entry_hash"]
    _rewrite(ledger, records)

    assert verify_chain(read_ledger(ledger)) == []


# --- "Done when": another contract exits 2 and leaves the file unchanged ---


def test_appending_a_receipt_for_another_contract_refuses_and_changes_nothing(
    copied_example: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A ledger holds one contract's evaluations.

    The second receipt is produced by evaluating a genuinely different manifest,
    not by editing a field in the first. Editing `contract.id` in a receipt
    breaks its `payload_sha256`, so `verify_receipt` refuses it one step
    earlier and this test would pass with the contract check deleted — an
    earlier branch returning before the thing under test is reached. The whole
    example is copied and re-evaluated so the receipt that arrives here is
    valid in every respect except the one being tested.

    The file is compared byte for byte, not by entry count: a refusal that
    appended and then truncated would pass a count check and would still have
    written to the file.
    """

    from shutil import copytree

    ledger = tmp_path / "contract.ledger.jsonl"
    _append_all(_three_receipts(copied_example, tmp_path)[:1], ledger)
    before = ledger.read_bytes()

    other_example = tmp_path / "other-example"
    copytree(copied_example, other_example)
    manifest = other_example / "obligations.toml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            'id = "synthetic-accessibility-acceptance"',
            'id = "some-other-contract"',
            1,
        ),
        encoding="utf-8",
    )
    other_receipt = tmp_path / "other-receipt.json"
    _evaluate(other_example, other_receipt, "2026-04-01T00:00:00+00:00", expect=NOT_OBSERVED)
    # The receipt is valid on its own terms; only its contract differs.
    assert verify_receipt(load_receipt(other_receipt))
    capsys.readouterr()

    assert main(["ledger-append", str(other_receipt), "--ledger", str(ledger)]) == INPUT_ERROR
    assert ledger.read_bytes() == before
    error = capsys.readouterr().err
    assert "some-other-contract" in error
    assert "synthetic-accessibility-acceptance" in error


def test_a_receipt_that_does_not_verify_is_never_appended(
    copied_example: Path, tmp_path: Path
) -> None:
    """A chained sequence of unverified documents is a weaker claim that reads stronger."""

    ledger = tmp_path / "contract.ledger.jsonl"
    receipt_path = tmp_path / "receipt.json"
    _evaluate(copied_example, receipt_path, "2026-01-01T00:00:00+00:00")
    document = load_receipt(receipt_path)
    document["payload_sha256"] = "0" * 64
    receipt_path.write_text(json.dumps(document), encoding="utf-8")

    assert main(["ledger-append", str(receipt_path), "--ledger", str(ledger)]) == INPUT_ERROR
    assert not ledger.exists()


# --- "Done when": the ledger is byte-reproducible --------------------------


def test_the_ledger_is_byte_reproducible_from_the_same_receipts(
    copied_example: Path, tmp_path: Path
) -> None:
    """No clock is read, so rebuilding from the same receipts gives the same bytes.

    That is what lets a third party rebuild the chain and compare it, rather
    than having to trust the copy they were handed.
    """

    receipts = _three_receipts(copied_example, tmp_path)
    first = tmp_path / "a.ledger.jsonl"
    second = tmp_path / "b.ledger.jsonl"
    _append_all(receipts, first)
    _append_all(receipts, second)

    assert first.read_bytes() == second.read_bytes()


def test_appending_in_a_different_order_produces_a_different_chain(
    copied_example: Path, tmp_path: Path
) -> None:
    """Order is the thing the ledger records, so it has to change the bytes.

    Every one of these receipts has the same `payload_sha256` — the evidence did
    not move — so if order were not in the hashed payload the two chains would
    be identical and the ledger would be recording nothing the receipts do not
    already say.
    """

    receipts = _three_receipts(copied_example, tmp_path)
    forward = tmp_path / "forward.jsonl"
    backward = tmp_path / "backward.jsonl"
    _append_all(receipts, forward)
    _append_all(list(reversed(receipts)), backward)

    assert forward.read_bytes() != backward.read_bytes()
    assert verify_chain(read_ledger(forward)) == []
    assert verify_chain(read_ledger(backward)) == []


# --- reading a ledger is an input error, not a finding ---------------------


def test_an_absent_ledger_reads_as_empty_and_the_first_append_is_genesis(
    copied_example: Path, tmp_path: Path
) -> None:
    ledger = tmp_path / "nowhere" / "contract.ledger.jsonl"
    assert read_ledger(ledger) == []

    receipt_path = tmp_path / "receipt.json"
    _evaluate(copied_example, receipt_path, "2026-01-01T00:00:00+00:00")
    entry = append_receipt(ledger, load_receipt(receipt_path))

    assert entry.index == 0
    assert entry.prev_hash == GENESIS_PREV_HASH


@pytest.mark.parametrize(
    ("contents", "match"),
    [
        ("{{{\n", "not strict JSON"),
        ("[1,2]\n", "closed schema"),
        ('{"index": 0}\n', "closed schema"),
    ],
)
def test_a_ledger_that_cannot_be_read_raises_rather_than_reading_as_empty(
    tmp_path: Path, contents: str, match: str
) -> None:
    """The most dangerous failure this module could have.

    Returning `[]` for an unreadable ledger would make the next append behave
    exactly like a genesis append: the chain silently restarts, and every entry
    before the corruption is gone with nothing recording that they existed.
    """

    ledger = tmp_path / "contract.ledger.jsonl"
    ledger.write_text(contents, encoding="utf-8")

    with pytest.raises(LedgerError, match=match):
        read_ledger(ledger)


def test_an_unreadable_ledger_exits_two_and_never_appends(
    copied_example: Path, tmp_path: Path
) -> None:
    ledger = tmp_path / "contract.ledger.jsonl"
    ledger.write_text("not json\n", encoding="utf-8")
    before = ledger.read_bytes()
    receipt_path = tmp_path / "receipt.json"
    _evaluate(copied_example, receipt_path, "2026-01-01T00:00:00+00:00")

    assert main(["ledger-append", str(receipt_path), "--ledger", str(ledger)]) == INPUT_ERROR
    assert main(["ledger-verify", str(ledger)]) == INPUT_ERROR
    assert ledger.read_bytes() == before


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (lambda r: r.update(schema_version="obligation-receipts/receipt/v0.1"), "unsupported"),
        (lambda r: r.update(index=-1), "non-negative integer"),
        (lambda r: r.update(index=True), "non-negative integer"),
        (lambda r: r.update(contract_id=""), "non-empty string"),
        (lambda r: r.update(entry_hash="nope"), "SHA-256 digest"),
        (lambda r: r.update(prev_hash=7), "non-empty string"),
    ],
)
def test_a_malformed_entry_is_refused_rather_than_partially_read(
    copied_example: Path, tmp_path: Path, mutate: Any, match: str
) -> None:
    ledger = tmp_path / "contract.ledger.jsonl"
    _append_all(_three_receipts(copied_example, tmp_path)[:1], ledger)
    records = _lines(ledger)
    mutate(records[0])
    _rewrite(ledger, records)

    with pytest.raises(LedgerError, match=match):
        read_ledger(ledger)


def test_a_ledger_over_the_read_limit_is_refused(tmp_path: Path) -> None:
    ledger = tmp_path / "contract.ledger.jsonl"
    ledger.write_bytes(b"x" * (8 * 1024 * 1024 + 1))

    with pytest.raises(LedgerError, match="cannot be read safely"):
        read_ledger(ledger)


def test_a_blank_line_is_not_an_entry(copied_example: Path, tmp_path: Path) -> None:
    ledger = tmp_path / "contract.ledger.jsonl"
    _append_all(_three_receipts(copied_example, tmp_path)[:1], ledger)
    ledger.write_text(ledger.read_text(encoding="utf-8") + "\n\n", encoding="utf-8")

    assert len(read_ledger(ledger)) == 1
    assert verify_chain(read_ledger(ledger)) == []


def test_a_receipt_missing_the_fields_the_entry_needs_is_refused(tmp_path: Path) -> None:
    ledger = tmp_path / "contract.ledger.jsonl"

    with pytest.raises(LedgerError, match="payload or envelope"):
        append_receipt(ledger, {"schema_version": "x"})
    with pytest.raises(LedgerError, match="contract object"):
        append_receipt(ledger, {"payload": {}, "envelope": {}})
    with pytest.raises(LedgerError, match="payload_sha256"):
        append_receipt(ledger, {"payload": {"contract": {}}, "envelope": {}})
    assert not ledger.exists()
