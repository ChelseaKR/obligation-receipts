"""Fail if the built wheel omits runtime modules or the PEP 561 marker."""

from __future__ import annotations

import sys
from pathlib import Path
from zipfile import BadZipFile, ZipFile

REQUIRED_MEMBERS = {
    "obligation_receipts/__init__.py",
    "obligation_receipts/canonical.py",
    "obligation_receipts/cli.py",
    "obligation_receipts/evaluator.py",
    "obligation_receipts/manifest.py",
    "obligation_receipts/models.py",
    "obligation_receipts/paths.py",
    "obligation_receipts/plan.py",
    "obligation_receipts/py.typed",
    "obligation_receipts/receipt.py",
    "obligation_receipts/research.py",
    "obligation_receipts/single_check.py",
}


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: check_wheel.py DIST_DIRECTORY", file=sys.stderr)
        return 2
    wheels = sorted(Path(argv[0]).glob("obligation_receipts-*.whl"))
    if not wheels:
        print("no obligation-receipts wheel found", file=sys.stderr)
        return 2
    wheel = wheels[-1]
    try:
        with ZipFile(wheel) as archive:
            members = set(archive.namelist())
            missing = sorted(REQUIRED_MEMBERS - members)
            forbidden = sorted(
                member
                for member in members
                if "__pycache__" in member or member.endswith(".pyc") or member.startswith("tests/")
            )
    except BadZipFile as exc:
        print(f"invalid wheel {wheel}: {exc}", file=sys.stderr)
        return 2
    if missing:
        print(f"wheel is missing required members: {', '.join(missing)}", file=sys.stderr)
        return 2
    if forbidden:
        print(f"wheel contains forbidden members: {', '.join(forbidden)}", file=sys.stderr)
        return 2
    print(f"verified wheel contents: {wheel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
