import os
from pathlib import Path

import pytest

from obligation_receipts.paths import (
    BoundedPathError,
    hash_bounded_file,
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


def test_resolve_bounded_file_rejects_symlink_escape(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside_target.json"
    outside.write_text("{}", encoding="utf-8")
    symlink = tmp_path / "escape_symlink.json"
    symlink.symlink_to(outside)
    with pytest.raises(BoundedPathError, match="escapes"):
        resolve_bounded_file(tmp_path, "escape_symlink.json")


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


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO creation is unavailable")
def test_hash_bounded_file_rejects_fifo_without_blocking(tmp_path: Path) -> None:
    fifo = tmp_path / "stream.fifo"
    os.mkfifo(fifo)
    with pytest.raises(BoundedPathError, match="regular file"):
        hash_bounded_file(tmp_path, "stream.fifo", max_bytes=1024)


def test_hash_bounded_file_rejects_non_regular_descriptor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact = tmp_path / "artifact.json"
    artifact.write_text("{}", encoding="utf-8")

    class FakeStat:
        st_mode = 0  # Not S_ISREG
        st_size = 2

    monkeypatch.setattr(os, "fstat", lambda fd: FakeStat())
    with pytest.raises(BoundedPathError, match="regular file"):
        hash_bounded_file(tmp_path, "artifact.json", max_bytes=1024)


def test_resolve_bounded_file_rejects_directory(tmp_path: Path) -> None:
    directory = tmp_path / "directory"
    directory.mkdir()
    with pytest.raises(BoundedPathError, match="regular file"):
        resolve_bounded_file(tmp_path, "directory")
