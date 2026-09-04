"""Command-line interface."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from obligation_receipts.canonical import StrictJsonError, canonical_json_bytes
from obligation_receipts.evaluator import evaluate_manifest
from obligation_receipts.exit_codes import INPUT_ERROR, OBSERVED_FAILURE, OK, evaluation_exit_code
from obligation_receipts.manifest import ManifestError, load_manifest
from obligation_receipts.models import JsonValue
from obligation_receipts.paths import BoundedPathError
from obligation_receipts.plan import (
    EvidencePlanError,
    build_evidence_plan,
    load_evidence_plan,
    verify_evidence_plan,
    write_evidence_plan,
)
from obligation_receipts.receipt import (
    ReceiptError,
    build_receipt,
    load_receipt,
    verify_receipt,
    write_receipt,
)
from obligation_receipts.research import ResearchError, analyze_ratings
from obligation_receipts.single_check import (
    EvidenceCheckError,
    check_declared_evidence,
    evidence_check_exit_code,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="obligation-receipts",
        description="Evaluate approved acceptance obligations and issue evidence receipts.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="validate and source-bind a manifest")
    validate.add_argument("manifest", type=Path)

    evaluate = subparsers.add_parser("evaluate", help="evaluate a manifest against local evidence")
    evaluate.add_argument("manifest", type=Path)
    evaluate.add_argument("--evidence-root", type=Path, required=True)
    evaluate.add_argument("--out", type=Path, required=True)
    evaluate.add_argument("--generated-at")

    evidence_plan = subparsers.add_parser(
        "evidence-plan",
        help="create a deterministic evidence-collection checklist",
    )
    evidence_plan.add_argument("manifest", type=Path)
    evidence_plan.add_argument("--out", type=Path, required=True)
    evidence_plan.add_argument(
        "--include-local-details",
        action="store_true",
        help="include sensitive manifest-declared locators, paths, and reasons",
    )

    verify_plan = subparsers.add_parser(
        "verify-evidence-plan",
        help="check plan self-consistency or exact manifest regeneration",
    )
    verify_plan.add_argument("plan", type=Path)
    verify_plan.add_argument("--manifest", type=Path)

    check_evidence = subparsers.add_parser(
        "check-evidence",
        help="evaluate exactly one evidence item declared by a manifest",
    )
    check_evidence.add_argument("manifest", type=Path)
    check_evidence.add_argument("evidence_id")
    check_evidence.add_argument("--evidence-root", type=Path, required=True)

    verify = subparsers.add_parser("verify", help="verify a receipt, optionally by replay")
    verify.add_argument("receipt", type=Path)
    verify.add_argument("--manifest", type=Path)
    verify.add_argument("--evidence-root", type=Path)

    research = subparsers.add_parser(
        "research-metrics",
        help="analyze two frozen independent-mapping CSV files",
    )
    research.add_argument("rater_a", type=Path)
    research.add_argument("rater_b", type=Path)
    return parser


def _print_json(value: dict[str, JsonValue]) -> None:
    """Write one canonical JSON line, surviving a reader that has stopped reading.

    `obligation-receipts ... | head -1` closes the pipe early. Without this the
    write, or the interpreter's shutdown flush, raises BrokenPipeError and the
    process exits 120 -- outside the documented {0,1,2,3,4} band that callers
    are told they never have to guess about. Redirecting the descriptor to
    devnull silences the shutdown flush so the computed verdict is what the
    caller receives.
    """
    try:
        sys.stdout.buffer.write(canonical_json_bytes(value) + b"\n")
        sys.stdout.buffer.flush()
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())


def _validate(path: Path) -> int:
    manifest = load_manifest(path)
    _print_json(
        {
            "contract_id": manifest.contract.contract_id,
            "manifest_sha256": manifest.manifest_sha256,
            "obligation_count": len(manifest.obligations),
            "status": "valid",
        }
    )
    return OK


def _evaluate(
    manifest_path: Path,
    evidence_root: Path,
    out: Path,
    generated_at: str | None,
) -> int:
    manifest = load_manifest(manifest_path)
    evaluation = evaluate_manifest(manifest, evidence_root)
    receipt = build_receipt(evaluation, generated_at=generated_at)
    write_receipt(out, receipt)
    _print_json(
        {
            "manifest_sha256": manifest.manifest_sha256,
            "overall_status": evaluation.overall_status.value,
            "payload_sha256": receipt["payload_sha256"],
            "receipt": str(out),
        }
    )
    return evaluation_exit_code(evaluation.overall_status)


def _evidence_plan(
    manifest_path: Path,
    out: Path,
    include_local_details: bool,
) -> int:
    plan = build_evidence_plan(
        load_manifest(manifest_path),
        include_local_details=include_local_details,
    )
    write_evidence_plan(out, plan)
    payload = plan["payload"]
    if not isinstance(payload, dict):
        raise EvidencePlanError("generated evidence plan payload is missing")
    _print_json(
        {
            "manifest_sha256": payload["manifest_sha256"],
            "obligation_count": payload["obligation_count"],
            "payload_sha256": plan["payload_sha256"],
            "status": "plan_generated",
        }
    )
    return OK


def _verify_evidence_plan(plan_path: Path, manifest_path: Path | None) -> int:
    plan = load_evidence_plan(plan_path)
    manifest = load_manifest(manifest_path) if manifest_path is not None else None
    payload_sha256 = verify_evidence_plan(plan, manifest)
    _print_json(
        {
            "manifest_regenerated": manifest is not None,
            "payload_sha256": payload_sha256,
            "status": ("replay_verified" if manifest is not None else "checksum_self_consistent"),
        }
    )
    return OK


def _check_evidence(
    manifest_path: Path,
    evidence_id: str,
    evidence_root: Path,
) -> int:
    document = check_declared_evidence(
        load_manifest(manifest_path),
        evidence_id,
        evidence_root,
    )
    _print_json(document)
    return evidence_check_exit_code(document)


def _verify(
    receipt_path: Path,
    manifest_path: Path | None,
    evidence_root: Path | None,
) -> int:
    if (manifest_path is None) != (evidence_root is None):
        raise ReceiptError("--manifest and --evidence-root must be supplied together")
    receipt = load_receipt(receipt_path)
    replay: dict[str, JsonValue] | None = None
    if manifest_path is not None and evidence_root is not None:
        replay = evaluate_manifest(load_manifest(manifest_path), evidence_root).payload()
    # Reading the receipt, manifest, and evidence root above can only fail as an
    # input error. From here on every failure is a finding about the receipt
    # itself, so it must not be reported as one.
    try:
        payload_sha256 = verify_receipt(receipt)
        if replay is not None and receipt["payload"] != replay:
            raise ReceiptError("receipt payload does not match a fresh evidence replay")
    except ReceiptError as exc:
        print(f"obligation-receipts: {exc}", file=sys.stderr)
        return OBSERVED_FAILURE
    _print_json(
        {
            "payload_sha256": payload_sha256,
            "replayed": replay is not None,
            "status": "verified",
        }
    )
    return OK


def main(argv: list[str] | None = None) -> int:
    """Run the CLI with bounded, user-readable failures."""
    args = _parser().parse_args(argv)
    try:
        if args.command == "validate":
            return _validate(args.manifest)
        if args.command == "evaluate":
            return _evaluate(
                args.manifest,
                args.evidence_root,
                args.out,
                args.generated_at,
            )
        if args.command == "evidence-plan":
            return _evidence_plan(args.manifest, args.out, args.include_local_details)
        if args.command == "verify-evidence-plan":
            return _verify_evidence_plan(args.plan, args.manifest)
        if args.command == "check-evidence":
            return _check_evidence(args.manifest, args.evidence_id, args.evidence_root)
        if args.command == "verify":
            return _verify(args.receipt, args.manifest, args.evidence_root)
        if args.command == "research-metrics":
            _print_json(analyze_ratings(args.rater_a, args.rater_b))
            return OK
    except (
        ManifestError,
        EvidencePlanError,
        EvidenceCheckError,
        ReceiptError,
        ResearchError,
        BoundedPathError,
        StrictJsonError,
        FileNotFoundError,
        NotADirectoryError,
        OSError,
        json.JSONDecodeError,
    ) as exc:
        print(f"obligation-receipts: {exc}", file=sys.stderr)
        return INPUT_ERROR
    return INPUT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
