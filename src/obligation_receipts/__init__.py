"""Deterministic evidence evaluation for approved acceptance obligations."""

from obligation_receipts.evaluator import evaluate_manifest
from obligation_receipts.manifest import load_manifest
from obligation_receipts.receipt import verify_receipt

__all__ = ["evaluate_manifest", "load_manifest", "verify_receipt"]
__version__ = "0.1.0"
