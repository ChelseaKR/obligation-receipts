"""Collection progress against a plan, with no verdict in it.

Issue 59. Each test maps to one of that issue's "Done when" bullets, plus the
invariant that gives the command its reason to exist: a progress report must
never carry an assertion outcome or an attestation's own status value, because
either one turns "what have we collected" into "did it pass".
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from obligation_receipts.canonical import canonical_json_bytes, sha256_bytes
from obligation_receipts.cli import main
from obligation_receipts.manifest import load_manifest
from obligation_receipts.models import JsonValue
from obligation_receipts.plan import build_evidence_plan, write_evidence_plan
from obligation_receipts.progress import (
    MAX_ARTIFACT_BYTES,
    PlanStatusError,
    build_plan_status,
    render_markdown,
)

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "accessibility-acceptance"
MANIFEST = EXAMPLE / "obligations.toml"
EVIDENCE = EXAMPLE / "evidence"


def _obj(value: JsonValue) -> dict[str, JsonValue]:
    assert isinstance(value, dict)
    return value


def _rows(value: JsonValue) -> list[dict[str, JsonValue]]:
    assert isinstance(value, list)
    return [_obj(item) for item in value]


def _copy_example(tmp_path: Path) -> Path:
    root = tmp_path / "evidence"
    root.mkdir()
    for source in sorted(EVIDENCE.rglob("*")):
        if source.is_file():
            target = root / source.relative_to(EVIDENCE)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
    return root


def _status(root: Path, *, local: bool = True) -> dict[str, JsonValue]:
    manifest = load_manifest(MANIFEST)
    plan = build_evidence_plan(manifest, include_local_details=local)
    document = build_plan_status(plan, manifest, root, include_local_details=local)
    return _obj(document["payload"])


def _requirements(payload: dict[str, JsonValue]) -> dict[str, dict[str, JsonValue]]:
    return {
        _obj(row)["id"]: _obj(row)  # type: ignore[misc]
        for obligation in _rows(payload["obligations"])
        for row in _rows(obligation["requirements"])
    }


def test_the_untouched_example_is_fully_present() -> None:
    payload = _status(EVIDENCE)
    counts = _obj(payload["counts"])
    assert counts["declared_total"] == 3
    assert counts["present"] == 3
    assert counts["absent"] == 0
    assert counts["unreadable"] == 0
    assert counts["unbound_attestations"] == 0


def test_a_removed_attestation_is_absent_and_the_rest_present(tmp_path: Path) -> None:
    """Issue 59: 'one attestation removed reports it absent and everything else present'."""
    root = _copy_example(tmp_path)
    (root / "manual" / "keyboard-review.json").unlink()

    payload = _status(root)
    counts = _obj(payload["counts"])
    assert counts["absent"] == 1
    assert counts["present"] == 2
    assert counts["unreadable"] == 0

    rows = _requirements(payload)
    assert rows["a2-review-attestation"]["state"] == "absent"
    assert rows["a2-review-attestation"]["sha256"] is None
    assert rows["a1-axe-summary"]["state"] == "present"
    assert rows["a3-vendor-attestation"]["state"] == "present"


def test_a_truncated_artifact_is_unreadable_with_the_reason(tmp_path: Path) -> None:
    """Issue 59: 'A truncated JSON artifact reports unreadable with the reason'."""
    root = _copy_example(tmp_path)
    target = root / "automated" / "axe-summary.json"
    target.write_bytes(target.read_bytes()[:20])

    payload = _status(root)
    assert _obj(payload["counts"])["unreadable"] == 1
    assert _obj(payload["counts"])["present"] == 2
    row = _requirements(payload)["a1-axe-summary"]
    assert row["state"] == "unreadable"
    reason = row["reason"]
    assert isinstance(reason, str) and "not strict JSON" in reason
    # A truncated file is present-but-unusable, never absent: telling a delivery
    # lead to go and collect a file that is already there wastes the meeting.
    assert row["state"] != "absent"


def test_an_oversized_artifact_is_unreadable_not_present(tmp_path: Path) -> None:
    root = _copy_example(tmp_path)
    (root / "automated" / "axe-summary.json").write_bytes(b"x" * (MAX_ARTIFACT_BYTES + 1))

    payload = _status(root)
    row = _requirements(payload)["a1-axe-summary"]
    assert row["state"] == "unreadable"
    reason = row["reason"]
    assert isinstance(reason, str) and "limit" in reason


def test_the_output_carries_no_assertion_result_and_no_attestation_status(
    tmp_path: Path,
) -> None:
    """Issue 59 sentinel: 'no assertion result and no attestation status value'.

    Both example attestations carry `"status": "pass"`, and the axe summary
    carries the value the automated obligation asserts on. Neither may appear.
    """
    root = _copy_example(tmp_path)
    payload = _status(root)
    rendered = canonical_json_bytes(payload).decode()

    for forbidden in ('"pass"', '"fail"', "review_required", "unverifiable_result"):
        assert forbidden not in rendered, f"progress report leaked {forbidden}"

    # `status` as a KEY is legitimate here only in the shape `"state"`; the
    # attestation's own field name must not appear at all.
    assert '"status"' not in rendered

    # And no assertion outcome: the pointer, operator and expected value that
    # `evaluate` would compare are absent from the progress report entirely.
    for forbidden in ("/summary/critical_violations", '"operator"', '"expected"'):
        assert forbidden not in rendered, f"progress report leaked {forbidden}"

    assert _obj(payload["limitations"])["evaluation_performed"] is False
    assert _obj(payload["limitations"])["attestation_status_read"] is False
    assert payload["decision_scope"] == "evidence_collection_progress_only"


def test_binding_is_reported_without_reading_the_status_value(tmp_path: Path) -> None:
    """An attestation whose status says `fail` is still reported as bound.

    This is the decisive test for the sentinel above: if the binding check ever
    started consulting `status`, flipping it would change this row.
    """
    root = _copy_example(tmp_path)
    target = root / "manual" / "keyboard-review.json"
    document = json.loads(target.read_text(encoding="utf-8"))
    document["status"] = "fail"
    target.write_text(json.dumps(document), encoding="utf-8")

    payload = _status(root)
    row = _requirements(payload)["a2-review-attestation"]
    assert row["state"] == "present"
    binding = _obj(row["attestation_binding"])
    assert binding["bound_to_manifest"] is True
    assert binding["mismatched_fields"] == []
    assert "fail" not in canonical_json_bytes(payload).decode()


def test_an_attestation_bound_to_another_manifest_is_reported_unbound(
    tmp_path: Path,
) -> None:
    root = _copy_example(tmp_path)
    target = root / "external" / "acr-attestation.json"
    document = json.loads(target.read_text(encoding="utf-8"))
    document["manifest_sha256"] = "0" * 64
    target.write_text(json.dumps(document), encoding="utf-8")

    payload = _status(root)
    row = _requirements(payload)["a3-vendor-attestation"]
    assert row["state"] == "present"
    binding = _obj(row["attestation_binding"])
    assert binding["bound_to_manifest"] is False
    assert binding["mismatched_fields"] == ["manifest_sha256"]
    assert _obj(payload["counts"])["unbound_attestations"] == 1


def test_an_attestation_missing_a_required_field_is_reported_unbound(
    tmp_path: Path,
) -> None:
    root = _copy_example(tmp_path)
    target = root / "manual" / "keyboard-review.json"
    document = json.loads(target.read_text(encoding="utf-8"))
    del document["reviewer"]
    target.write_text(json.dumps(document), encoding="utf-8")

    payload = _status(root)
    binding = _obj(_requirements(payload)["a2-review-attestation"]["attestation_binding"])
    assert binding["required_fields_present"] is False
    assert binding["missing_fields"] == ["reviewer"]
    assert binding["bound_to_manifest"] is False


def test_an_attestation_that_is_not_an_object_is_reported_not_bound(
    tmp_path: Path,
) -> None:
    root = _copy_example(tmp_path)
    (root / "manual" / "keyboard-review.json").write_bytes(b"[1, 2, 3]\n")

    payload = _status(root)
    binding = _obj(_requirements(payload)["a2-review-attestation"]["attestation_binding"])
    assert binding["is_object"] is False
    assert binding["bound_to_manifest"] is False


def test_an_unverifiable_obligation_declares_no_requirements() -> None:
    payload = _status(EVIDENCE)
    unverifiable = [
        entry
        for entry in _rows(payload["obligations"])
        if entry["classification"] == "unverifiable"
    ]
    assert len(unverifiable) == 1
    assert unverifiable[0]["requirements"] == []


def test_portable_mode_redacts_paths_but_keeps_states_and_counts() -> None:
    payload = _status(EVIDENCE, local=False)
    assert payload["detail_mode"] == "portable_redacted"
    rows = _requirements(payload)
    assert all(row["path"] is None for row in rows.values())
    assert _obj(payload["counts"])["present"] == 3


def test_a_plan_that_does_not_regenerate_from_the_manifest_is_refused(
    tmp_path: Path,
) -> None:
    """Issue 59: 'A plan that does not regenerate from the manifest exits 2'."""
    manifest = load_manifest(MANIFEST)
    plan = build_evidence_plan(manifest, include_local_details=True)
    payload = _obj(plan["payload"])
    payload["contract_version"] = "999.0"
    plan["payload_sha256"] = sha256_bytes(canonical_json_bytes(payload))

    with pytest.raises(PlanStatusError, match="does not regenerate"):
        build_plan_status(plan, manifest, EVIDENCE, include_local_details=True)


def test_the_document_digest_covers_the_payload() -> None:
    manifest = load_manifest(MANIFEST)
    plan = build_evidence_plan(manifest)
    document = build_plan_status(plan, manifest, EVIDENCE)
    assert document["payload_sha256"] == sha256_bytes(canonical_json_bytes(document["payload"]))
    assert document["schema_version"] == "obligation-receipts/plan-status-document/v0.1"


def test_the_same_inputs_report_byte_identically_twice() -> None:
    manifest = load_manifest(MANIFEST)
    plan = build_evidence_plan(manifest)
    first = build_plan_status(plan, manifest, EVIDENCE)
    second = build_plan_status(plan, manifest, EVIDENCE)
    assert canonical_json_bytes(first) == canonical_json_bytes(second)


def test_markdown_says_nothing_was_evaluated() -> None:
    manifest = load_manifest(MANIFEST)
    plan = build_evidence_plan(manifest)
    rendered = render_markdown(build_plan_status(plan, manifest, EVIDENCE))
    assert "Nothing was evaluated" in rendered
    assert "missing evidence is" in rendered
    assert "| present | 3 |" in rendered


def test_markdown_refuses_a_document_with_no_payload() -> None:
    with pytest.raises(PlanStatusError, match="no payload"):
        render_markdown({"payload": None})


def test_markdown_refuses_a_document_with_no_counts() -> None:
    with pytest.raises(PlanStatusError, match="no counts"):
        render_markdown({"payload": {"counts": None}})


# --- CLI ------------------------------------------------------------------


def _write_plan(tmp_path: Path, *, local: bool = True) -> Path:
    plan_path = tmp_path / "evidence-plan.json"
    write_evidence_plan(
        plan_path, build_evidence_plan(load_manifest(MANIFEST), include_local_details=local)
    )
    return plan_path


def test_cli_plan_status_emits_one_json_line_and_exits_zero(
    tmp_path: Path, capsysbinary: pytest.CaptureFixture[bytes]
) -> None:
    plan_path = _write_plan(tmp_path)
    code = main(
        [
            "plan-status",
            str(plan_path),
            "--manifest",
            str(MANIFEST),
            "--evidence-root",
            str(EVIDENCE),
            "--include-local-details",
        ]
    )
    assert code == 0
    out = capsysbinary.readouterr().out
    assert out.count(b"\n") == 1
    document = json.loads(out)
    assert document["payload"]["counts"]["present"] == 3


def test_cli_plan_status_markdown(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    plan_path = _write_plan(tmp_path, local=False)
    code = main(
        [
            "plan-status",
            str(plan_path),
            "--manifest",
            str(MANIFEST),
            "--evidence-root",
            str(EVIDENCE),
            "--markdown",
        ]
    )
    assert code == 0
    assert "# Evidence collection progress" in capsys.readouterr().out


def test_cli_exit_zero_even_when_evidence_is_missing(tmp_path: Path) -> None:
    """A report is not a verdict: absent evidence is still exit 0."""
    root = _copy_example(tmp_path)
    (root / "manual" / "keyboard-review.json").unlink()
    plan_path = _write_plan(tmp_path)
    code = main(
        [
            "plan-status",
            str(plan_path),
            "--manifest",
            str(MANIFEST),
            "--evidence-root",
            str(root),
            "--include-local-details",
        ]
    )
    assert code == 0


def test_cli_exits_two_when_the_plan_does_not_match_the_manifest(tmp_path: Path) -> None:
    plan_path = tmp_path / "evidence-plan.json"
    manifest = load_manifest(MANIFEST)
    plan = build_evidence_plan(manifest, include_local_details=True)
    write_evidence_plan(plan_path, plan)
    # A different manifest: same shape, different contract version.
    other = tmp_path / "obligations.toml"
    other.write_text(
        MANIFEST.read_text(encoding="utf-8").replace('version = "1.0"', 'version = "2.0"', 1),
        encoding="utf-8",
    )
    (tmp_path / "source").mkdir()
    (tmp_path / "source" / "section-508-acceptance.txt").write_bytes(
        (EXAMPLE / "source" / "section-508-acceptance.txt").read_bytes()
    )
    code = main(
        [
            "plan-status",
            str(plan_path),
            "--manifest",
            str(other),
            "--evidence-root",
            str(EVIDENCE),
        ]
    )
    assert code == 2


def test_cli_exits_two_on_a_missing_evidence_root(tmp_path: Path) -> None:
    plan_path = _write_plan(tmp_path)
    code = main(
        [
            "plan-status",
            str(plan_path),
            "--manifest",
            str(MANIFEST),
            "--evidence-root",
            str(tmp_path / "nope"),
        ]
    )
    assert code == 2


# --- defensive branches ---------------------------------------------------


def test_an_unreadable_artifact_from_a_plain_oserror_is_unreadable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A read that fails for a reason the bounded seam does not name."""
    root = _copy_example(tmp_path)

    def refuse(*_args: object, **_kwargs: object) -> tuple[Path, bytes]:
        raise PermissionError(13, "denied")

    monkeypatch.setattr("obligation_receipts.progress.read_bounded_file", refuse)
    payload = _status(root)
    assert _obj(payload["counts"])["unreadable"] == 3
    assert _obj(payload["counts"])["present"] == 0
    for row in _requirements(payload).values():
        assert row["state"] == "unreadable"
        assert row["reason"] == "artifact could not be read"


def test_an_unknown_collection_state_is_refused_not_counted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fourth state must not be silently dropped from the counts."""
    root = _copy_example(tmp_path)

    def odd_state(*_args: object, **_kwargs: object) -> dict[str, JsonValue]:
        return {"id": "x", "state": "probably-fine", "attestation_binding": None}

    monkeypatch.setattr("obligation_receipts.progress._requirement_status", odd_state)
    with pytest.raises(PlanStatusError, match="unknown collection state"):
        _status(root)


def test_markdown_skips_a_malformed_obligation_entry() -> None:
    document: dict[str, JsonValue] = {
        "payload": {
            "contract_id": "c",
            "contract_version": "1.0",
            "counts": {"present": 0},
            "obligations": ["not an object"],
        }
    }
    rendered = render_markdown(document)
    assert "not an object" not in rendered


def test_markdown_skips_a_malformed_requirement_row() -> None:
    document: dict[str, JsonValue] = {
        "payload": {
            "contract_id": "c",
            "contract_version": "1.0",
            "counts": {"present": 0},
            "obligations": [
                {
                    "id": "o1",
                    "classification": "automated",
                    "requirements": ["not an object", {"id": "r1", "state": "present"}],
                }
            ],
        }
    }
    rendered = render_markdown(document)
    assert "`r1`" in rendered
    assert "not an object" not in rendered


def test_markdown_handles_a_non_list_obligations_field() -> None:
    document: dict[str, JsonValue] = {
        "payload": {
            "contract_id": "c",
            "contract_version": "1.0",
            "counts": {"present": 0},
            "obligations": "not a list",
        }
    }
    assert "# Evidence collection progress" in render_markdown(document)
