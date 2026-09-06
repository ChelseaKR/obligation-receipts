"""Command-line interface."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable
from pathlib import Path

from obligation_receipts.canonical import StrictJsonError, canonical_json_bytes
from obligation_receipts.diff import ReceiptDiffError, diff_receipts
from obligation_receipts.diff import render_markdown as render_diff_markdown
from obligation_receipts.evaluator import evaluate_manifest
from obligation_receipts.exit_codes import INPUT_ERROR, OBSERVED_FAILURE, OK, evaluation_exit_code
from obligation_receipts.inventory import (
    EvidenceRootAuditError,
    audit_evidence_root,
    render_markdown,
)
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
from obligation_receipts.progress import (
    PlanStatusError,
    build_plan_status,
)
from obligation_receipts.progress import render_markdown as render_status_markdown
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

    diff_parser = subparsers.add_parser(
        "diff-receipts",
        help="compare two receipts of one contract; nothing is re-evaluated",
    )
    diff_parser.add_argument("prior", type=Path)
    diff_parser.add_argument("current", type=Path)
    diff_parser.add_argument(
        "--markdown",
        action="store_true",
        help="write a Markdown rendering to stdout instead of one canonical JSON line",
    )

    plan_status = subparsers.add_parser(
        "plan-status",
        help="report evidence-collection progress against a plan, evaluating nothing",
    )
    plan_status.add_argument("plan", type=Path)
    plan_status.add_argument("--manifest", type=Path, required=True)
    plan_status.add_argument("--evidence-root", type=Path, required=True)
    plan_status.add_argument(
        "--include-local-details",
        action="store_true",
        help="include declared artifact paths, which can name a client or contract",
    )
    plan_status.add_argument(
        "--markdown",
        action="store_true",
        help="write a Markdown rendering to stdout instead of one canonical JSON line",
    )

    audit_root = subparsers.add_parser(
        "audit-evidence-root",
        help="inventory an evidence root against a manifest, evaluating nothing",
    )
    audit_root.add_argument("manifest", type=Path)
    audit_root.add_argument("--evidence-root", type=Path, required=True)
    audit_root.add_argument(
        "--include-local-details",
        action="store_true",
        help="include relative artifact paths, which can name a client or contract",
    )
    audit_root.add_argument(
        "--markdown",
        action="store_true",
        help="write a Markdown rendering to stdout instead of one canonical JSON line",
    )

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


def _diff_receipts(prior_path: Path, current_path: Path, markdown: bool) -> int:
    document = diff_receipts(load_receipt(prior_path), load_receipt(current_path))
    if markdown:
        sys.stdout.write(render_diff_markdown(document))
        return OK
    _print_json(document)
    return OK


def _plan_status(
    plan_path: Path,
    manifest_path: Path,
    evidence_root: Path,
    include_local_details: bool,
    markdown: bool,
) -> int:
    manifest = load_manifest(manifest_path)
    plan = load_evidence_plan(plan_path)
    document = build_plan_status(
        plan,
        manifest,
        evidence_root,
        include_local_details=include_local_details,
    )
    if markdown:
        sys.stdout.write(render_status_markdown(document))
        return OK
    _print_json(document)
    return OK


def _audit_evidence_root(
    manifest_path: Path,
    evidence_root: Path,
    include_local_details: bool,
    markdown: bool,
) -> int:
    document = audit_evidence_root(
        load_manifest(manifest_path),
        evidence_root,
        include_local_details=include_local_details,
    )
    if markdown:
        sys.stdout.write(render_markdown(document))
        return OK
    _print_json(document)
    return OK


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


def _research_metrics(rater_a: Path, rater_b: Path) -> int:
    _print_json(analyze_ratings(rater_a, rater_b))
    return OK


#: Subcommand -> the handler and the argument names it takes, in order.
#:
#: A table rather than an `if` chain. The chain grew one branch per subcommand
#: and twice pushed its enclosing function past the complexity ceiling
#: `make lint` enforces -- first `main`, then `_dispatch` -- so each new verb
#: cost a refactor. A table's complexity does not grow with the number of
#: commands, and a verb registered here with no parser, or a parser with no
#: entry here, is caught by a test rather than by a missing branch that
#: silently returns INPUT_ERROR.
_COMMANDS: dict[str, tuple[Callable[..., int], tuple[str, ...]]] = {
    "validate": (_validate, ("manifest",)),
    "evaluate": (_evaluate, ("manifest", "evidence_root", "out", "generated_at")),
    "evidence-plan": (_evidence_plan, ("manifest", "out", "include_local_details")),
    "verify-evidence-plan": (_verify_evidence_plan, ("plan", "manifest")),
    "check-evidence": (_check_evidence, ("manifest", "evidence_id", "evidence_root")),
    "diff-receipts": (_diff_receipts, ("prior", "current", "markdown")),
    "plan-status": (
        _plan_status,
        ("plan", "manifest", "evidence_root", "include_local_details", "markdown"),
    ),
    "audit-evidence-root": (
        _audit_evidence_root,
        ("manifest", "evidence_root", "include_local_details", "markdown"),
    ),
    "verify": (_verify, ("receipt", "manifest", "evidence_root")),
    "research-metrics": (_research_metrics, ("rater_a", "rater_b")),
}


def _dispatch(args: argparse.Namespace) -> int:
    """Route one parsed command to its handler.

    Split out of `main` so `main` stays the error boundary and nothing else.
    """
    entry = _COMMANDS.get(args.command)
    if entry is None:
        return INPUT_ERROR
    handler, parameters = entry
    return handler(*(getattr(args, name) for name in parameters))


def main(argv: list[str] | None = None) -> int:
    """Run the CLI with bounded, user-readable failures."""
    args = _parser().parse_args(argv)
    try:
        return _dispatch(args)
    except (
        ManifestError,
        EvidencePlanError,
        EvidenceCheckError,
        EvidenceRootAuditError,
        PlanStatusError,
        ReceiptDiffError,
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
