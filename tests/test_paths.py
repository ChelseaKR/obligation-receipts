import os
from pathlib import Path

import pytest

from obligation_receipts.paths import (
    BoundedPathError,
    read_regular_file,
    resolve_bounded_file,
)


def test_resolve_bounded_file_accepts_local_file(tmp_path: Path) -> None:
    artifact = tmp_path / "evidence.json"
    artifact.write_text("{}", encoding="utf-8")
    assert resolve_bounded_file(tmp_path, "evidence.json") == artifact


def test_resolve_bounded_file_rejects_escape(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    with pytest.raises(BoundedPathError, match="escapes"):
        resolve_bounded_file(tmp_path, "../outside.json")


def test_resolve_bounded_file_rejects_absolute(tmp_path: Path) -> None:
    with pytest.raises(BoundedPathError, match="relative"):
        resolve_bounded_file(tmp_path, str((tmp_path / "x").resolve()))


@pytest.mark.parametrize(
    "requested",
    [
        r"C:\evidence\artifact.json",
        r"C:evidence\artifact.json",
        r"\\server\share\artifact.json",
        r"dir\artifact.json",
        "https:artifact.json",
        "https://example.invalid/artifact.json",
        "dir//artifact.json",
        "./artifact.json",
    ],
)
def test_resolve_bounded_file_rejects_windows_rooted_or_drive_paths(
    tmp_path: Path,
    requested: str,
) -> None:
    with pytest.raises(BoundedPathError, match="portable and relative"):
        resolve_bounded_file(tmp_path, requested)


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO creation is unavailable")
def test_regular_file_reader_rejects_fifo_without_blocking(tmp_path: Path) -> None:
    fifo = tmp_path / "manifest.toml"
    os.mkfifo(fifo)
    with pytest.raises(BoundedPathError, match="regular file"):
        read_regular_file(fifo, max_bytes=1024, no_follow=True)


def test_resolve_bounded_file_rejects_directory(tmp_path: Path) -> None:
    directory = tmp_path / "directory"
    directory.mkdir()
    with pytest.raises(BoundedPathError, match="regular file"):
        resolve_bounded_file(tmp_path, "directory")
