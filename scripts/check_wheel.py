"""Fail if the built wheel omits runtime modules or the PEP 561 marker."""

from __future__ import annotations

import sys
from pathlib import Path
from zipfile import BadZipFile, ZipFile

PACKAGE = "obligation_receipts"
SOURCE_PACKAGE = Path(__file__).resolve().parents[1] / "src" / PACKAGE

# Files that must exist in the source package for a derived requirement set to
# mean anything. If the source tree is missing or empty, the derived set is
# empty and every wheel would pass vacuously, which is the failure mode this
# gate exists to prevent.
SENTINEL_MEMBERS = frozenset({f"{PACKAGE}/__init__.py", f"{PACKAGE}/py.typed"})


class PackageGateError(Exception):
    """Raised when the gate cannot establish what the wheel is required to hold."""


def required_members(source_package: Path) -> set[str]:
    """Derive the required wheel members from the source package.

    A hardcoded list is a stale baseline: it silently stops covering any module
    added after it was written, which is how `exit_codes.py` shipped unguarded.
    The source tree and the built wheel are two independent artifacts -- one is
    the input to the build, the other is its output -- so comparing them is a
    real check rather than a self-confirming one.
    """
    if not source_package.is_dir():
        raise PackageGateError(f"source package not found at {source_package}")
    members = {
        f"{PACKAGE}/{path.relative_to(source_package).as_posix()}"
        for path in source_package.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and (path.suffix == ".py" or path.name == "py.typed")
    }
    absent_sentinels = sorted(SENTINEL_MEMBERS - members)
    if absent_sentinels:
        raise PackageGateError(
            "source package does not contain "
            f"{', '.join(absent_sentinels)}; the derived requirement set cannot be trusted"
        )
    return members


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: check_wheel.py DIST_DIRECTORY", file=sys.stderr)
        return 2
    wheels = sorted(Path(argv[0]).glob(f"{PACKAGE}-*.whl"))
    if not wheels:
        print("no obligation-receipts wheel found", file=sys.stderr)
        return 2
    wheel = wheels[-1]
    try:
        required = required_members(SOURCE_PACKAGE)
    except PackageGateError as exc:
        print(f"cannot determine required wheel members: {exc}", file=sys.stderr)
        return 2
    try:
        with ZipFile(wheel) as archive:
            members = set(archive.namelist())
            missing = sorted(required - members)
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
    print(f"verified {len(required)} required wheel members: {wheel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
