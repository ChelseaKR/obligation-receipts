"""Fail-closed bounded file access."""

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path, PureWindowsPath


class BoundedPathError(ValueError):
    """Raised when a requested artifact escapes its declared root."""


def validate_portable_relative_path(relative_path: str) -> None:
    """Reject relative-path spellings with platform-dependent semantics."""
    requested = Path(relative_path)
    windows_requested = PureWindowsPath(relative_path)
    segments = relative_path.split("/")
    if (
        not relative_path
        or "\\" in relative_path
        or ":" in relative_path
        or requested.is_absolute()
        or windows_requested.is_absolute()
        or bool(windows_requested.drive)
        or any(segment in {"", "."} for segment in segments)
    ):
        raise BoundedPathError("artifact path must be portable and relative")
    if ".." in segments:
        raise BoundedPathError("artifact path escapes its declared root")


def resolve_bounded_file(root: Path, relative_path: str) -> Path:
    """Resolve an existing regular file beneath root."""
    validate_portable_relative_path(relative_path)
    requested = Path(relative_path)
    resolved_root = root.resolve(strict=True)
    candidate = (resolved_root / requested).resolve(strict=True)
    if not candidate.is_relative_to(resolved_root):
        raise BoundedPathError("artifact path escapes its declared root")
    if not candidate.is_file():
        raise BoundedPathError("artifact path is not a regular file")
    return candidate


def read_bounded_file(
    root: Path,
    relative_path: str,
    *,
    max_bytes: int,
) -> tuple[Path, bytes]:
    """Read bounded bytes once from a regular file beneath root."""
    path = resolve_bounded_file(root, relative_path)
    return path, read_regular_file(path, max_bytes=max_bytes, no_follow=True)


def read_regular_file(path: Path, *, max_bytes: int, no_follow: bool = False) -> bytes:
    """Read at most max_bytes from one regular-file descriptor."""
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NONBLOCK", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    if not no_follow:
        flags &= ~getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        file_stat = os.fstat(descriptor)
        if not stat.S_ISREG(file_stat.st_mode):
            raise BoundedPathError("artifact path is not a regular file")
        if file_stat.st_size > max_bytes:
            raise BoundedPathError(f"artifact exceeds the {max_bytes}-byte limit")
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            data = handle.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise BoundedPathError(f"artifact exceeds the {max_bytes}-byte limit")
        return data
    finally:
        os.close(descriptor)


def hash_bounded_file(
    root: Path,
    relative_path: str,
    *,
    max_bytes: int,
) -> tuple[Path, str]:
    """Hash one descriptor-stable regular file beneath root."""
    path = resolve_bounded_file(root, relative_path)
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NONBLOCK", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = os.open(path, flags)
    try:
        file_stat = os.fstat(descriptor)
        if not stat.S_ISREG(file_stat.st_mode):
            raise BoundedPathError("artifact path is not a regular file")
        if file_stat.st_size > max_bytes:
            raise BoundedPathError(f"artifact exceeds the {max_bytes}-byte limit")
        digest = hashlib.sha256()
        total = 0
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            for chunk in iter(lambda: handle.read(64 * 1024), b""):
                total += len(chunk)
                if total > max_bytes:
                    raise BoundedPathError(f"artifact exceeds the {max_bytes}-byte limit")
                digest.update(chunk)
        return path, digest.hexdigest()
    finally:
        os.close(descriptor)
