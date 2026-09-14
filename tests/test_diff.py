"""What moved between two receipts, and what a diff must never claim.

Issue 57. Each test maps to one of that issue's "Done when" bullets, plus the
two properties that keep a diff a report: it verifies both receipts before
comparing anything, and it speaks only the domain's own status labels.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from obligation_receipts.canonical import canonical_json_bytes, sha256_bytes
from obligation_receipts.cli import _COMMANDS, main
from obligation_receipts.diff import (
    ADDED,
    EVIDENCE_CHANGED,
    REMOVED,
    STATUS_CHANGED,
    UNCHANGED,
    ReceiptDiffError,
    diff_receipts,
    render_markdown,
)
from obligation_receipts.evaluator import evaluate_manifest
from obligation_receipts.manifest import load_manifest
from obligation_receipts.models import JsonValue
from obligation_receipts.receipt import build_receipt, write_receipt

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "accessibility-acceptance"
MANIFEST = EXAMPLE / "obligations.toml"
EVIDENCE = EXAMPLE / "evidence"


def _obj(value: JsonValue) -> dict[str, JsonValue]:
    assert isinstance(value, dict)
    return value


def _rows(value: JsonValue) -> list[dict[str, JsonValue]]:
    assert isinstance(value, list)
    return [_obj(item) for item in value]


def _receipt() -> dict[str, JsonValue]:
    manifest = load_manifest(MANIFEST)
    evaluation = evaluate_manifest(manifest, EVIDENCE)
    return build_receipt(evaluation, generated_at="2026-09-06T12:00:00+00:00")


def _reseal(receipt: dict[str, JsonValue]) -> dict[str, JsonValue]:
    """Re-derive every field a receipt derives, then its payload digest.

    `verify_receipt` checks a receipt's internal consistency, not just its
    digest: `obligation_counts` must tally the obligations and `overall_status`
    must follow from their criticalities. Editing a status in a fixture and
    resealing only the digest produces a receipt the validator rightly refuses,
    so a fixture edited here is brought back into consistency the same way the
    evaluator would -- otherwise these tests would be exercising the validator
    rather than the diff.
    """
    payload = _obj(receipt["payload"])
    obligations = _rows(payload["obligations"])
    if not isinstance(payload.get("obligations"), str):
        counts = {
            status: 0 for status in ("pass", "fail", "missing", "review_required", "unverifiable")
        }
        pairs = []
        for row in obligations:
            status = str(row.get("status"))
            if status in counts:
                counts[status] += 1
            pairs.append((str(row.get("criticality")), status))
        payload["obligation_counts"] = dict(counts)

        must = {status for criticality, status in pairs if criticality == "must"}
        if "fail" in must:
            overall = "rejected"
        elif must - {"pass"}:
            overall = "incomplete"
        elif any(status != "pass" for _criticality, status in pairs):
            overall = "accepted_with_findings"
        else:
            overall = "accepted"
        payload["overall_status"] = overall
    receipt["payload_sha256"] = sha256_bytes(canonical_json_bytes(receipt["payload"]))
    return receipt


def _set_status(obligation: dict[str, JsonValue], status: str) -> None:
    """Move an obligation's status, and its evidence with it.

    `verify_receipt` requires an obligation's status to be the combination of
    its evidence results, so a fixture that moves only the obligation is a
    receipt the validator refuses -- and the test would then be exercising the
    validator instead of the diff.
    """
    obligation["status"] = status
    for evidence in _rows(obligation["evidence"]):
        evidence["status"] = status


def _payload_of(document: dict[str, JsonValue]) -> dict[str, JsonValue]:
    return _obj(document["payload"])


def _by_id(payload: dict[str, JsonValue]) -> dict[str, dict[str, JsonValue]]:
    return {str(row["id"]): row for row in _rows(payload["obligations"])}


# --- the four "Done when" bullets ----------------------------------------


def test_identical_receipts_yield_an_empty_change_list() -> None:
    """Issue 57: 'Identical receipts yield an empty change list'."""
    receipt = _receipt()
    payload = _payload_of(diff_receipts(deepcopy(receipt), deepcopy(receipt)))

    assert payload["changed"] == []
    counts = _obj(payload["counts"])
    assert counts[STATUS_CHANGED] == 0
    assert counts[EVIDENCE_CHANGED] == 0
    assert counts[ADDED] == 0
    assert counts[REMOVED] == 0
    assert counts[UNCHANGED] == 5
    assert _obj(payload["overall_status_transition"])["changed"] is False
    assert payload["manifest_changed"] is False
    assert payload["source_changed"] is False


def test_one_changed_evidence_digest_yields_exactly_one_entry_with_both_digests() -> None:
    """Issue 57: 'differing in one evidence digest yield exactly one entry with both'."""
    prior = _receipt()
    current = deepcopy(prior)
    obligations = _rows(_obj(current["payload"])["obligations"])
    target = next(row for row in obligations if row["id"] == "a1-zero-critical-violations")
    evidence = _rows(target["evidence"])[0]
    original_digest = evidence["artifact_sha256"]
    evidence["artifact_sha256"] = "a" * 64
    _reseal(current)

    payload = _payload_of(diff_receipts(prior, current))
    changed = _rows(payload["changed"])
    assert len(changed) == 1
    entry = changed[0]
    assert entry["id"] == "a1-zero-critical-violations"
    assert entry["change"] == EVIDENCE_CHANGED

    evidence_changes = _rows(entry["evidence"])
    assert len(evidence_changes) == 1
    moved = evidence_changes[0]
    assert moved["prior_artifact_sha256"] == original_digest
    assert moved["current_artifact_sha256"] == "a" * 64
    assert "evidence_digest_changed" in _rows_of_str(entry["causes"])


def _rows_of_str(value: JsonValue) -> list[str]:
    assert isinstance(value, list)
    return [str(item) for item in value]


def test_receipts_for_different_contracts_are_refused() -> None:
    """Issue 57: 'Receipts with different contract ids exit 2'."""
    prior = _receipt()
    current = deepcopy(prior)
    _obj(_obj(current["payload"])["contract"])["id"] = "some-other-contract"
    _reseal(current)

    with pytest.raises(ReceiptDiffError, match="different contracts"):
        diff_receipts(prior, current)


def test_a_receipt_that_does_not_verify_is_refused_before_diffing() -> None:
    """Issue 57: 'A receipt that fails verify_receipt is refused before diffing'.

    The payload is edited and the digest deliberately NOT re-derived, so the
    receipt no longer hashes to what it claims.
    """
    prior = _receipt()
    current = deepcopy(prior)
    _obj(_obj(current["payload"])["contract"])["title"] = "tampered"
    # No _reseal: payload_sha256 now disagrees with the payload.

    with pytest.raises(ReceiptDiffError, match="current receipt does not verify"):
        diff_receipts(prior, current)

    with pytest.raises(ReceiptDiffError, match="prior receipt does not verify"):
        diff_receipts(current, prior)


# --- status movement ------------------------------------------------------


def test_a_status_change_is_classified_and_both_statuses_reported() -> None:
    prior = _receipt()
    current = deepcopy(prior)
    _set_status(_by_id(_obj(current["payload"]))["a1-zero-critical-violations"], "fail")
    _reseal(current)

    payload = _payload_of(diff_receipts(prior, current))
    entry = _by_id(payload)["a1-zero-critical-violations"]
    assert entry["change"] == STATUS_CHANGED
    assert entry["prior_status"] == "pass"
    assert entry["current_status"] == "fail"
    assert _obj(payload["counts"])[STATUS_CHANGED] == 1


def test_an_added_and_a_removed_obligation_are_both_reported() -> None:
    prior = _receipt()
    current = deepcopy(prior)
    obligations = _rows(_obj(current["payload"])["obligations"])
    dropped = obligations.pop(0)
    added = deepcopy(dropped)
    added["id"] = "a9-brand-new-obligation"
    obligations.append(added)
    _obj(current["payload"])["obligations"] = list(obligations)
    _reseal(current)

    payload = _payload_of(diff_receipts(prior, current))
    by_id = _by_id(payload)
    assert by_id[str(dropped["id"])]["change"] == REMOVED
    assert by_id["a9-brand-new-obligation"]["change"] == ADDED
    assert _obj(payload["counts"])[REMOVED] == 1
    assert _obj(payload["counts"])[ADDED] == 1


def test_a_manifest_change_is_reported_and_attributed() -> None:
    prior = _receipt()
    current = deepcopy(prior)
    _obj(current["payload"])["manifest_sha256"] = "b" * 64
    _set_status(_by_id(_obj(current["payload"]))["a1-zero-critical-violations"], "fail")
    _reseal(current)

    payload = _payload_of(diff_receipts(prior, current))
    assert payload["manifest_changed"] is True
    assert _obj(payload["sides"])["prior"] != _obj(payload["sides"])["current"]
    entry = _by_id(payload)["a1-zero-critical-violations"]
    assert "manifest_changed" in _rows_of_str(entry["causes"])


def test_a_source_change_is_reported_and_attributed() -> None:
    prior = _receipt()
    current = deepcopy(prior)
    _obj(_obj(current["payload"])["contract"])["source_sha256"] = "c" * 64
    _set_status(_by_id(_obj(current["payload"]))["a1-zero-critical-violations"], "fail")
    _reseal(current)

    payload = _payload_of(diff_receipts(prior, current))
    assert payload["source_changed"] is True
    assert "source_changed" in _rows_of_str(
        _by_id(payload)["a1-zero-critical-violations"]["causes"]
    )


def test_new_and_removed_evidence_are_attributed_separately() -> None:
    prior = _receipt()
    current = deepcopy(prior)
    target = _by_id(_obj(current["payload"]))["a1-zero-critical-violations"]
    evidence = _rows(target["evidence"])
    extra = deepcopy(evidence[0])
    extra["id"] = "a1-second-artifact"
    target["evidence"] = [*evidence, extra]
    _reseal(current)

    payload = _payload_of(diff_receipts(prior, current))
    entry = _by_id(payload)["a1-zero-critical-violations"]
    assert entry["change"] == EVIDENCE_CHANGED
    assert "new_evidence" in _rows_of_str(entry["causes"])

    # And the reverse direction reports removal.
    reversed_payload = _payload_of(diff_receipts(current, prior))
    reversed_entry = _by_id(reversed_payload)["a1-zero-critical-violations"]
    assert "evidence_removed" in _rows_of_str(reversed_entry["causes"])


def test_an_unreadable_artifact_keeps_a_null_digest_on_both_sides() -> None:
    """A digest that was never computed stays null, never an empty string."""
    prior = _receipt()
    current = deepcopy(prior)
    target = _by_id(_obj(current["payload"]))["a1-zero-critical-violations"]
    evidence = _rows(target["evidence"])[0]
    evidence["artifact_sha256"] = None
    evidence["status"] = "missing"
    target["status"] = "missing"
    _reseal(current)

    payload = _payload_of(diff_receipts(prior, current))
    moved = _rows(_by_id(payload)["a1-zero-critical-violations"]["evidence"])[0]
    assert moved["current_artifact_sha256"] is None
    assert moved["current_artifact_sha256"] != ""


# --- what a diff must never say ------------------------------------------


def test_the_diff_speaks_only_the_domains_own_labels() -> None:
    """No judgement words: a diff states movement, never whether it is good."""
    prior = _receipt()
    current = deepcopy(prior)
    _set_status(_by_id(_obj(current["payload"]))["a1-zero-critical-violations"], "fail")
    _reseal(current)

    document = diff_receipts(prior, current)
    rendered = canonical_json_bytes(document).decode().lower()
    for forbidden in (
        "improved",
        "regressed",
        "resolved",
        "compliant",
        "non-compliant",
        "better",
        "worse",
        "accepted_by_this_tool",
        "remediated",
    ):
        assert forbidden not in rendered, f"diff used the judgement word {forbidden!r}"

    payload = _payload_of(document)
    assert payload["decision_scope"] == "receipt_to_receipt_comparison_only"
    limitations = _obj(payload["limitations"])
    assert limitations["evidence_re_evaluated"] is False
    assert limitations["official_decision_made"] is False
    assert limitations["cause_is_attributed_not_proven"] is True


def test_the_diff_never_reads_the_evidence_root(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nothing on this path may open an artifact: statuses come from receipts."""
    import obligation_receipts.paths as paths_module

    def refuse(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("diff_receipts must not read any evidence file")

    monkeypatch.setattr(paths_module, "read_bounded_file", refuse)
    monkeypatch.setattr(paths_module, "hash_bounded_file", refuse)

    prior = _receipt()
    current = deepcopy(prior)
    _reseal(current)
    assert _payload_of(diff_receipts(prior, current))["changed"] == []


# --- shape ----------------------------------------------------------------


def test_the_document_digest_covers_the_payload() -> None:
    receipt = _receipt()
    document = diff_receipts(deepcopy(receipt), deepcopy(receipt))
    assert document["payload_sha256"] == sha256_bytes(canonical_json_bytes(document["payload"]))
    assert document["schema_version"] == "obligation-receipts/receipt-diff-document/v0.1"


def test_the_same_pair_diffs_byte_identically_twice() -> None:
    receipt = _receipt()
    first = diff_receipts(deepcopy(receipt), deepcopy(receipt))
    second = diff_receipts(deepcopy(receipt), deepcopy(receipt))
    assert canonical_json_bytes(first) == canonical_json_bytes(second)


def test_the_shape_guards_are_defence_in_depth_not_dead_code() -> None:
    """The payload-shape guards, exercised directly.

    They are unreachable through `diff_receipts` itself: `verify_receipt` runs
    first and refuses a receipt whose payload does not match the closed schema,
    so a malformed payload never reaches them. They are kept because they are
    what narrows `JsonValue` for `mypy --strict` at each access, and a narrowing
    that raised nothing would return `None` into arithmetic instead. Tested here
    against the helpers so their messages are real rather than assumed.
    """
    from obligation_receipts.diff import _contract, _obligations, _payload

    with pytest.raises(ReceiptDiffError, match="no obligations array"):
        _obligations({"obligations": "not a list"}, "current")
    with pytest.raises(ReceiptDiffError, match="malformed obligation"):
        _obligations({"obligations": ["not an object"]}, "current")
    with pytest.raises(ReceiptDiffError, match="obligation with no id"):
        _obligations({"obligations": [{"status": "pass"}]}, "current")
    with pytest.raises(ReceiptDiffError, match="no contract"):
        _contract({"contract": "not an object"}, "prior")

    receipt = _receipt()
    receipt["payload"] = "not an object"
    with pytest.raises(ReceiptDiffError):
        _payload(receipt, "prior")


# --- markdown -------------------------------------------------------------


def test_markdown_says_nothing_was_re_evaluated() -> None:
    receipt = _receipt()
    rendered = render_markdown(diff_receipts(deepcopy(receipt), deepcopy(receipt)))
    assert "Nothing was re-evaluated" in rendered
    assert "No obligation changed between these two receipts." in rendered


def test_markdown_lists_a_change_with_its_causes() -> None:
    prior = _receipt()
    current = deepcopy(prior)
    _set_status(_by_id(_obj(current["payload"]))["a1-zero-critical-violations"], "fail")
    _reseal(current)
    rendered = render_markdown(diff_receipts(prior, current))
    assert "`a1-zero-critical-violations`" in rendered
    assert "status_changed" in rendered


def test_markdown_refuses_a_document_with_no_payload() -> None:
    with pytest.raises(ReceiptDiffError, match="no payload"):
        render_markdown({"payload": None})


def test_markdown_refuses_a_document_with_no_counts() -> None:
    with pytest.raises(ReceiptDiffError, match="no counts"):
        render_markdown({"payload": {"counts": None}})


# --- CLI ------------------------------------------------------------------


def _write_pair(tmp_path: Path) -> tuple[Path, Path]:
    prior = _receipt()
    current = deepcopy(prior)
    _set_status(_by_id(_obj(current["payload"]))["a1-zero-critical-violations"], "fail")
    _reseal(current)
    prior_path = tmp_path / "prior.json"
    current_path = tmp_path / "current.json"
    write_receipt(prior_path, prior)
    write_receipt(current_path, current)
    return prior_path, current_path


def test_cli_diff_emits_one_json_line_and_exits_zero(
    tmp_path: Path, capsysbinary: pytest.CaptureFixture[bytes]
) -> None:
    prior_path, current_path = _write_pair(tmp_path)
    assert main(["diff-receipts", str(prior_path), str(current_path)]) == 0
    out = capsysbinary.readouterr().out
    assert out.count(b"\n") == 1
    document = json.loads(out)
    assert document["payload"]["counts"]["status_changed"] == 1


def test_cli_diff_markdown(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    prior_path, current_path = _write_pair(tmp_path)
    assert main(["diff-receipts", str(prior_path), str(current_path), "--markdown"]) == 0
    assert "# Receipt diff" in capsys.readouterr().out


def test_cli_diff_exits_two_for_different_contracts(tmp_path: Path) -> None:
    prior = _receipt()
    current = deepcopy(prior)
    _obj(_obj(current["payload"])["contract"])["id"] = "another-contract"
    _reseal(current)
    prior_path = tmp_path / "prior.json"
    current_path = tmp_path / "current.json"
    write_receipt(prior_path, prior)
    write_receipt(current_path, current)
    assert main(["diff-receipts", str(prior_path), str(current_path)]) == 2


def test_cli_diff_exits_two_on_a_missing_file(tmp_path: Path) -> None:
    prior_path, _current = _write_pair(tmp_path)
    assert main(["diff-receipts", str(prior_path), str(tmp_path / "nope.json")]) == 2


# --- the dispatch table ---------------------------------------------------


def test_every_parser_subcommand_has_a_dispatch_entry() -> None:
    """A verb with a parser but no table entry would silently exit 2.

    The `if` chain this table replaced had exactly that failure mode -- a new
    subcommand whose branch was forgotten parsed fine and returned INPUT_ERROR
    with no message -- which is why the table is checked rather than trusted.
    """
    import argparse as argparse_module

    from obligation_receipts.cli import _parser

    subparsers = [
        action
        for action in _parser()._actions
        if isinstance(action, argparse_module._SubParsersAction)
    ]
    assert subparsers, "no subparser action found"
    declared = set(subparsers[0].choices)
    assert declared == set(_COMMANDS), (
        f"parser and dispatch table disagree: "
        f"parser-only {sorted(declared - set(_COMMANDS))}, "
        f"table-only {sorted(set(_COMMANDS) - declared)}"
    )


def test_the_payload_guard_holds_if_verification_ever_stops_covering_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The `no payload` guard, with its precondition removed.

    It is unreachable while `verify_receipt` runs first, because verification
    already refuses a receipt whose payload is not the closed object. It is kept
    because it is what narrows `JsonValue` to a dict for `mypy --strict` at that
    access, and because it is the guard that would matter if verification ever
    stopped covering that case. Neutralising verification here is the only way
    to reach it, and doing so is the point of the test.
    """
    from obligation_receipts import diff as diff_module

    monkeypatch.setattr(diff_module, "verify_receipt", lambda _receipt: "")
    with pytest.raises(ReceiptDiffError, match="no payload"):
        diff_module._payload({"payload": "not an object"}, "prior")


def test_an_obligation_with_no_usable_evidence_list_contributes_no_rows() -> None:
    """An unverifiable obligation legitimately has no evidence; that is not an error."""
    from obligation_receipts.diff import _evidence_by_id

    assert _evidence_by_id({"evidence": "not a list"}) == {}
    assert _evidence_by_id({"evidence": [{"no": "id"}]}) == {}


def test_a_classification_or_criticality_change_is_attributed() -> None:
    prior = _receipt()
    current = deepcopy(prior)
    target = _by_id(_obj(current["payload"]))["a3-external-acr"]
    target["classification"] = "manual_review"
    # The receipt validator requires the evidence kind to match the
    # classification, so a fixture that moves one must move the other.
    for evidence in _rows(target["evidence"]):
        evidence["kind"] = "review_attestation"
    _set_status(target, "review_required")
    _reseal(current)

    entry = _by_id(_payload_of(diff_receipts(prior, current)))["a3-external-acr"]
    assert "classification_changed" in _rows_of_str(entry["causes"])

    other = deepcopy(prior)
    changed = _by_id(_obj(other["payload"]))["a3-external-acr"]
    changed["criticality"] = "must"
    _set_status(changed, "fail")
    _reseal(other)
    entry2 = _by_id(_payload_of(diff_receipts(prior, other)))["a3-external-acr"]
    assert "criticality_changed" in _rows_of_str(entry2["causes"])


def test_markdown_skips_a_malformed_change_row() -> None:
    document: dict[str, JsonValue] = {
        "payload": {
            "contract_id": "c",
            "counts": {"unchanged": 0},
            "changed": ["not an object", {"id": "o1", "change": "status_changed"}],
            "overall_status_transition": {},
        }
    }
    rendered = render_markdown(document)
    assert "`o1`" in rendered
    assert "not an object" not in rendered
