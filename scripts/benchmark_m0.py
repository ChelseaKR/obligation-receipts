"""Report local M0 validation-and-evaluation latency without asserting a target."""

from __future__ import annotations

import argparse
import platform
from pathlib import Path
from statistics import median
from time import perf_counter_ns

from obligation_receipts.canonical import canonical_json_bytes
from obligation_receipts.evaluator import evaluate_manifest
from obligation_receipts.manifest import load_manifest
from obligation_receipts.models import JsonValue


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=200)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("examples/accessibility-acceptance/obligations.toml"),
    )
    return parser


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(len(ordered) * fraction + 0.999999) - 1))
    return ordered[index]


def main() -> int:
    args = _parser().parse_args()
    if not 1 <= args.iterations <= 10_000:
        raise SystemExit("--iterations must be between 1 and 10000")
    manifest_path: Path = args.manifest.resolve(strict=True)
    evidence_root = manifest_path.parent / "evidence"
    durations: list[float] = []
    payload_sha256 = ""
    for _ in range(args.iterations):
        started = perf_counter_ns()
        evaluation = evaluate_manifest(load_manifest(manifest_path), evidence_root)
        durations.append((perf_counter_ns() - started) / 1_000_000)
        payload_sha256 = evaluation.manifest_sha256
    report: dict[str, JsonValue] = {
        "iterations": args.iterations,
        "manifest_sha256": payload_sha256,
        "median_ms": round(median(durations), 3),
        "p95_ms": round(_percentile(durations, 0.95), 3),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "scope": "manifest_validation_plus_four_obligation_evaluation",
        "threshold_status": "not_set_pending_real_workload",
    }
    print(canonical_json_bytes(report).decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
