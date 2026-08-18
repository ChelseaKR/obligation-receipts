import json
from pathlib import Path
from typing import cast

import pytest

from obligation_receipts.cli import main


def _last_stdout_json(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    raw = json.loads(capsys.readouterr().out)
    assert isinstance(raw, dict)
    return cast(dict[str, object], raw)


def test_validate_cli(example_manifest: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["validate", str(example_manifest)]) == 0
    assert _last_stdout_json(capsys)["status"] == "valid"


def test_evaluate_and_replay_cli(
    tmp_path: Path,
    example_manifest: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    receipt = tmp_path / "receipt.json"
    assert (
        main(
            [
                "evaluate",
                str(example_manifest),
                "--evidence-root",
                str(example_manifest.parent / "evidence"),
                "--out",
                str(receipt),
                "--generated-at",
                "2026-01-01T00:00:00+00:00",
            ]
        )
        == 0
    )
    assert _last_stdout_json(capsys)["overall_status"] == "accepted_with_findings"
    assert (
        main(
            [
                "verify",
                str(receipt),
                "--manifest",
                str(example_manifest),
                "--evidence-root",
                str(example_manifest.parent / "evidence"),
            ]
        )
        == 0
    )
    replay = _last_stdout_json(capsys)
    assert replay["status"] == "verified"
    assert replay["replayed"] is True


def test_verify_without_replay(
    tmp_path: Path,
    example_manifest: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    receipt = tmp_path / "receipt.json"
    assert (
        main(
            [
                "evaluate",
                str(example_manifest),
                "--evidence-root",
                str(example_manifest.parent / "evidence"),
                "--out",
                str(receipt),
            ]
        )
        == 0
    )
    _last_stdout_json(capsys)
    assert main(["verify", str(receipt)]) == 0
    assert _last_stdout_json(capsys)["replayed"] is False


def test_replay_rejects_changed_evidence(
    copied_example: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    receipt = tmp_path / "receipt.json"
    manifest = copied_example / "obligations.toml"
    evidence_root = copied_example / "evidence"
    assert (
        main(
            [
                "evaluate",
                str(manifest),
                "--evidence-root",
                str(evidence_root),
                "--out",
                str(receipt),
            ]
        )
        == 0
    )
    _last_stdout_json(capsys)
    (evidence_root / "automated" / "axe-summary.json").write_text(
        '{"summary":{"critical_violations":1}}',
        encoding="utf-8",
    )
    assert (
        main(
            [
                "verify",
                str(receipt),
                "--manifest",
                str(manifest),
                "--evidence-root",
                str(evidence_root),
            ]
        )
        == 1
    )
    assert "does not match a fresh evidence replay" in capsys.readouterr().err


def test_cli_reports_bounded_errors(
    tmp_path: Path,
    example_manifest: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    receipt = tmp_path / "missing.json"
    assert main(["verify", str(receipt)]) == 2
    captured = capsys.readouterr()
    assert "No such file" in captured.err

    valid_receipt = tmp_path / "receipt.json"
    assert (
        main(
            [
                "evaluate",
                str(example_manifest),
                "--evidence-root",
                str(example_manifest.parent / "evidence"),
                "--out",
                str(valid_receipt),
            ]
        )
        == 0
    )
    _last_stdout_json(capsys)
    assert main(["verify", str(valid_receipt), "--manifest", str(example_manifest)]) == 2
    captured = capsys.readouterr()
    assert "must be supplied together" in captured.err


def test_cli_returns_nonzero_for_rejected_evaluation(
    copied_example: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    evidence = copied_example / "evidence" / "automated" / "axe-summary.json"
    evidence.write_text('{"summary":{"critical_violations":1}}', encoding="utf-8")
    assert (
        main(
            [
                "evaluate",
                str(copied_example / "obligations.toml"),
                "--evidence-root",
                str(copied_example / "evidence"),
                "--out",
                str(tmp_path / "receipt.json"),
            ]
        )
        == 1
    )
    assert _last_stdout_json(capsys)["overall_status"] == "rejected"


def test_research_metrics_cli(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    template = Path(__file__).parents[1] / "docs" / "discovery" / "mapping-rater-template.csv"
    first = tmp_path / "rater-a.csv"
    second = tmp_path / "rater-b.csv"
    content = template.read_text(encoding="utf-8")
    first.write_text(content, encoding="utf-8")
    second.write_text(
        content.replace("replace this example row", "independent example row"), encoding="utf-8"
    )
    assert main(["research-metrics", str(first), str(second)]) == 0
    report = _last_stdout_json(capsys)
    assert report["total_frozen_clauses"] == 1
    assert report["cohen_kappa"] is None
    assert report["gate_status"] == "serious_warning"


def test_evidence_plan_generation_and_verification_cli(
    tmp_path: Path,
    example_manifest: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    plan = tmp_path / "SENSITIVE_OUTPUT_PATH_plan.json"
    assert (
        main(
            [
                "evidence-plan",
                str(example_manifest),
                "--out",
                str(plan),
            ]
        )
        == 0
    )
    generated = _last_stdout_json(capsys)
    assert generated["status"] == "plan_generated"
    assert generated["obligation_count"] == 4
    assert "SENSITIVE_OUTPUT_PATH" not in json.dumps(generated)

    assert main(["verify-evidence-plan", str(plan)]) == 0
    self_check = _last_stdout_json(capsys)
    assert self_check["status"] == "checksum_self_consistent"
    assert self_check["manifest_regenerated"] is False

    assert (
        main(
            [
                "verify-evidence-plan",
                str(plan),
                "--manifest",
                str(example_manifest),
            ]
        )
        == 0
    )
    replay = _last_stdout_json(capsys)
    assert replay["status"] == "replay_verified"
    assert replay["manifest_regenerated"] is True


def test_evidence_plan_local_details_are_explicit_opt_in(
    tmp_path: Path,
    example_manifest: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    plan = tmp_path / "local-plan.json"
    assert (
        main(
            [
                "evidence-plan",
                str(example_manifest),
                "--out",
                str(plan),
                "--include-local-details",
            ]
        )
        == 0
    )
    _last_stdout_json(capsys)
    document = json.loads(plan.read_text(encoding="utf-8"))
    assert document["payload"]["detail_mode"] == "local_sensitive"
    assert document["payload"]["obligations"][0]["source_locator"] == "A-1"


def test_check_evidence_cli_exit_codes_preserve_states(
    copied_example: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    manifest = copied_example / "obligations.toml"
    evidence_root = copied_example / "evidence"
    command = [
        "check-evidence",
        str(manifest),
        "a1-axe-summary",
        "--evidence-root",
        str(evidence_root),
    ]
    assert main(command) == 0
    assert _last_stdout_json(capsys)["payload"]["evidence"]["status"] == "pass"  # type: ignore[index]

    selected = evidence_root / "automated/axe-summary.json"
    selected.write_text('{"summary":{"critical_violations":1}}', encoding="utf-8")
    assert main(command) == 1
    assert _last_stdout_json(capsys)["payload"]["evidence"]["status"] == "fail"  # type: ignore[index]

    selected.unlink()
    assert main(command) == 3
    assert _last_stdout_json(capsys)["payload"]["evidence"]["status"] == "missing"  # type: ignore[index]

    review_command = [
        "check-evidence",
        str(manifest),
        "a2-review-attestation",
        "--evidence-root",
        str(evidence_root),
    ]
    (evidence_root / "manual/keyboard-review.json").unlink()
    assert main(review_command) == 4
    assert (
        _last_stdout_json(capsys)["payload"]["evidence"]["status"]  # type: ignore[index]
        == "review_required"
    )


def test_check_evidence_cli_unknown_id_is_usage_failure(
    example_manifest: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert (
        main(
            [
                "check-evidence",
                str(example_manifest),
                "a4-intuitive",
                "--evidence-root",
                str(example_manifest.parent / "evidence"),
            ]
        )
        == 2
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "exactly one declared evidence item" in captured.err


def _evaluate_args(manifest: Path, evidence_root: Path, out: Path) -> list[str]:
    return [
        "evaluate",
        str(manifest),
        "--evidence-root",
        str(evidence_root),
        "--out",
        str(out),
        "--generated-at",
        "2026-01-01T00:00:00+00:00",
    ]


def test_evaluate_separates_an_incomplete_result_from_an_input_error(
    copied_example: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An awaited `must` review is code 3 and still writes a receipt."""
    (copied_example / "evidence" / "manual" / "keyboard-review.json").unlink()
    receipt = tmp_path / "receipt.json"
    assert (
        main(
            _evaluate_args(
                copied_example / "obligations.toml", copied_example / "evidence", receipt
            )
        )
        == 3
    )
    assert _last_stdout_json(capsys)["overall_status"] == "incomplete"
    assert receipt.is_file()


def test_evaluate_reports_a_rejected_result_as_an_observed_failure_with_a_receipt(
    copied_example: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (copied_example / "evidence" / "automated" / "axe-summary.json").write_text(
        '{"summary":{"critical_violations":1}}',
        encoding="utf-8",
    )
    receipt = tmp_path / "receipt.json"
    assert (
        main(
            _evaluate_args(
                copied_example / "obligations.toml", copied_example / "evidence", receipt
            )
        )
        == 1
    )
    assert _last_stdout_json(capsys)["overall_status"] == "rejected"
    assert receipt.is_file()


@pytest.mark.parametrize("broken", ["manifest", "evidence_root", "source"])
def test_evaluate_input_errors_are_code_two_and_write_no_receipt(
    broken: str,
    copied_example: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Code 2 must mean "no result document", never an evaluated outcome."""
    manifest = copied_example / "obligations.toml"
    evidence_root = copied_example / "evidence"
    if broken == "manifest":
        manifest.write_text("not toml [[[", encoding="utf-8")
    elif broken == "evidence_root":
        evidence_root = copied_example / "absent"
    else:
        source = copied_example / "source" / "section-508-acceptance.txt"
        source.write_text(source.read_text(encoding="utf-8") + "amended", encoding="utf-8")

    receipt = tmp_path / "receipt.json"
    assert main(_evaluate_args(manifest, evidence_root, receipt)) == 2
    assert capsys.readouterr().out == ""
    assert not receipt.exists()


def test_verify_separates_an_integrity_finding_from_an_unreadable_receipt(
    tmp_path: Path,
    example_manifest: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    receipt = tmp_path / "receipt.json"
    assert (
        main(_evaluate_args(example_manifest, example_manifest.parent / "evidence", receipt)) == 0
    )
    _last_stdout_json(capsys)

    document = json.loads(receipt.read_text(encoding="utf-8"))
    payload = document["payload"]
    assert isinstance(payload, dict)
    payload["overall_status"] = "accepted"
    receipt.write_text(json.dumps(document), encoding="utf-8")

    assert main(["verify", str(receipt)]) == 1
    assert "obligation-receipts:" in capsys.readouterr().err
    assert main(["verify", str(tmp_path / "absent.json")]) == 2
    assert "No such file" in capsys.readouterr().err
