"""Deterministic evidence evaluation for approved acceptance obligations."""

import importlib.metadata

from obligation_receipts.evaluator import evaluate_manifest
from obligation_receipts.manifest import load_manifest
from obligation_receipts.receipt import verify_receipt

__all__ = ["evaluate_manifest", "load_manifest", "verify_receipt"]

#: Read from the installed distribution rather than retyped here.
#:
#: A literal was a second source of truth with no gate behind it: nothing in the
#: repository compared it to `project.version`, so the two could disagree and
#: every check would still pass. Only the release workflow tied a tag to
#: pyproject.toml, and it never looked at this file. Derived, they cannot drift
#: -- this is the same string the wheel's METADATA carries, read back out of it.
#:
#: `PackageNotFoundError` is deliberately not caught. A fallback literal would
#: reintroduce exactly the second source of truth this removes; an uninstalled
#: package failing loudly is the honest outcome, and the console script cannot
#: run uninstalled anyway.
__version__ = importlib.metadata.version("obligation-receipts")
