import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import cast

import coverage
import pytest

import obligation_receipts.cli as cli_module
from obligation_receipts.cli import main

_ROOT = Path(__file__).parents[1]


def _measured_child_env() -> dict[str, str]:
    """Environment for a `python -m` child whose lines still reach the report.

    The `if __name__ == "__main__":` guard can only run in a child process, and
    a child records nothing by default: coverage's site-wide `.pth` hook starts
    a recorder only when `COVERAGE_PROCESS_START` names a config file. Without
    it the guard is genuinely executed by this suite and reported as uncovered
    -- a measurement that understates what ran, which is the one direction this
    project's own argument forbids. (#23)

    `COVERAGE_FILE` is made absolute because one caller below runs with
    `cwd=tmp_path`; a relative data file would be written into that temporary
    directory and combined by nothing. `[tool.coverage.run] parallel` keeps the
    child's file from colliding with the parent's.
    """
    env = dict(os.environ)
    env["COVERAGE_PROCESS_START"] = str(_ROOT / "pyproject.toml")
    env["COVERAGE_FILE"] = str(_ROOT / ".coverage")
    return env


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


def _rewrite(path: Path, old: str, new: str) -> None:
    content = path.read_text(encoding="utf-8")
    assert old in content
    path.write_text(content.replace(old, new), encoding="utf-8")


def test_malformed_pointer_is_an_input_error_and_produces_no_receipt(
    tmp_path: Path,
    copied_example: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Regression test for #26.

    A dangling `~` in a manifest-authored pointer used to load cleanly, then
    become a deterministic `fail` and an overall `rejected`: exit 1 with a
    complete, checksum-verified receipt claiming a real observed failure, on
    evidence that in fact satisfies the intended assertion. The exit-code
    contract reserves code 2 for "no result document", which is what an
    authoring defect in the approved manifest is.
    """
    manifest = copied_example / "obligations.toml"
    _rewrite(
        manifest,
        'pointer = "/summary/critical_violations"',
        'pointer = "/summary/critical_violations~"',
    )
    receipt = tmp_path / "receipt.json"
    assert (
        main(
            [
                "evaluate",
                str(manifest),
                "--evidence-root",
                str(copied_example / "evidence"),
                "--out",
                str(receipt),
            ]
        )
        == 2
    )
    assert not receipt.exists()
    assert "RFC 6901" in capsys.readouterr().err


def test_every_command_agrees_that_a_malformed_pointer_is_an_input_error(
    tmp_path: Path,
    copied_example: Path,
) -> None:
    """One manifest, one verdict.

    `evaluate` reported `rejected`, `check-evidence` reported `fail`, and
    `evidence-plan` reported an input error, for the same manifest.
    """
    manifest = copied_example / "obligations.toml"
    _rewrite(
        manifest,
        'pointer = "/summary/critical_violations"',
        'pointer = "/summary/critical_violations~"',
    )
    evidence_root = str(copied_example / "evidence")
    assert main(["validate", str(manifest)]) == 2
    assert main(["evidence-plan", str(manifest), "--out", str(tmp_path / "plan.json")]) == 2
    assert (
        main(["check-evidence", str(manifest), "a1-axe-summary", "--evidence-root", evidence_root])
        == 2
    )
    assert (
        main(
            [
                "evaluate",
                str(manifest),
                "--evidence-root",
                evidence_root,
                "--out",
                str(tmp_path / "receipt.json"),
            ]
        )
        == 2
    )


def test_module_entry_point_runs_as_main(tmp_path: Path) -> None:
    """Regression test for #23.

    `python -m obligation_receipts.cli` is the only in-repo path that executes
    the `if __name__ == "__main__":` guard, and it is the closest available
    stand-in for the packaged `obligation-receipts` console script, which
    resolves to the same `cli:main`.
    """
    completed = subprocess.run(
        [sys.executable, "-m", "obligation_receipts.cli", "--help"],
        capture_output=True,
        text=True,
        check=False,
        env=_measured_child_env(),
    )
    assert completed.returncode == 0
    assert "obligation-receipts" in completed.stdout


def test_module_entry_point_propagates_the_input_error_exit_code(tmp_path: Path) -> None:
    """The guard must hand `main()`'s code to the shell, not swallow it.

    Run from an empty directory with a bare relative argument, so every element
    of the command line is a literal.
    """
    completed = subprocess.run(
        [sys.executable, "-m", "obligation_receipts.cli", "validate", "absent.toml"],
        capture_output=True,
        text=True,
        check=False,
        cwd=tmp_path,
        env=_measured_child_env(),
    )
    assert completed.returncode == 2
    assert completed.stdout == ""


def test_the_module_entry_point_child_is_measured_and_not_merely_run(tmp_path: Path) -> None:
    """The measurement of the guard must itself be able to fail.

    The two tests above execute the `if __name__ == "__main__":` guard in a
    child process. Whether the coverage report *sees* that is a separate fact,
    carried entirely by `COVERAGE_PROCESS_START` and coverage's site-wide `.pth`
    hook. If either stops working the guard would still be executed, the suite
    would still be green, and the 90% floor would still be cleared -- the number
    would just quietly fall back to reporting a line as unrun that this suite
    runs on every invocation. Nothing else in the repository would notice.

    So assert the mechanism directly, on a data file of this test's own, rather
    than trusting the aggregate percentage: the child must record `cli.py`, and
    the guard's own two lines must be among the lines it recorded.
    """
    guard = 'if __name__ == "__main__":\n    raise SystemExit(main())\n'
    cli_path = _ROOT / "src" / "obligation_receipts" / "cli.py"
    source = cli_path.read_text(encoding="utf-8")
    assert source.endswith(guard), "the guard is not the tail of cli.py; the offsets below lie"
    guard_first_line = len(source.splitlines()) - 1

    env = _measured_child_env()
    env["COVERAGE_FILE"] = str(tmp_path / "child.coverage")
    completed = subprocess.run(
        [sys.executable, "-m", "obligation_receipts.cli", "--help"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert completed.returncode == 0

    written = sorted(tmp_path.glob("child.coverage*"))
    assert written, (
        "the child process wrote no coverage data. COVERAGE_PROCESS_START no longer starts a "
        "recorder in a subprocess, so the module entry point is executed but unmeasured."
    )

    recorded: set[int] = set()
    measured: set[str] = set()
    for data_file in written:
        data = coverage.CoverageData(basename=str(data_file))
        data.read()
        for name in data.measured_files():
            measured.add(name)
            if Path(name).resolve() == cli_path.resolve():
                recorded.update(data.lines(name) or [])
    assert recorded, (
        f"the child measured {sorted(measured)} but recorded no lines of {cli_path}; the "
        "entry point ran outside coverage's view"
    )
    assert {guard_first_line, guard_first_line + 1} <= recorded, (
        f"the child recorded {cli_path.name} but not its `__main__` guard at lines "
        f"{guard_first_line}-{guard_first_line + 1}; recorded tail was {sorted(recorded)[-5:]}"
    )


def test_packaged_console_script_is_declared_for_the_same_entry_point() -> None:
    """The console script and the module guard must not drift apart."""
    pyproject = (Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    assert 'obligation-receipts = "obligation_receipts.cli:main"' in pyproject
    cli_source = (Path(__file__).parents[1] / "src" / "obligation_receipts" / "cli.py").read_text(
        encoding="utf-8"
    )
    assert 'if __name__ == "__main__":\n    raise SystemExit(main())\n' in cli_source


def test_unhandled_subcommand_fails_closed_as_an_input_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A subcommand added to the parser but not wired into dispatch must not exit 0.

    `main`'s trailing return is the fail-closed default for exactly that
    mistake. Untested, it would be one edit away from becoming a silent success
    that produces no result document and says nothing.
    """

    class _UnwiredParser:
        def parse_args(self, argv: list[str] | None = None) -> argparse.Namespace:
            return argparse.Namespace(command="not-wired-up")

    monkeypatch.setattr(cli_module, "_parser", _UnwiredParser)
    assert cli_module.main([]) == 2


def test_evidence_plan_refuses_a_plan_without_a_payload(
    tmp_path: Path, example_manifest: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The CLI must not print a summary for a plan it cannot read."""
    monkeypatch.setattr(
        cli_module,
        "build_evidence_plan",
        lambda manifest, *, include_local_details: {"payload": None},
    )
    monkeypatch.setattr(cli_module, "write_evidence_plan", lambda path, plan: None)
    assert main(["evidence-plan", str(example_manifest), "--out", str(tmp_path / "plan.json")]) == 2
