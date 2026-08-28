import os
from collections.abc import Callable
from pathlib import Path

import pytest

import obligation_receipts.paths as paths
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


def test_resolve_bounded_file_rejects_symlink_escaping_the_root(tmp_path: Path) -> None:
    """Regression test for #21.

    The lexical checks pass for `escape`: it is one portable relative segment
    with no `..`. Only the `is_relative_to` test after `Path.resolve` catches
    it, and nothing exercised that test before.
    """
    root = tmp_path / "evidence"
    root.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    os.symlink(outside, root / "escape")
    with pytest.raises(BoundedPathError, match="escapes"):
        resolve_bounded_file(root, "escape")


def test_resolve_bounded_file_accepts_symlink_that_stays_inside_the_root(
    tmp_path: Path,
) -> None:
    """The escape check must reject escaping links, not every link."""
    root = tmp_path / "evidence"
    root.mkdir()
    target = root / "real.json"
    target.write_text("{}", encoding="utf-8")
    os.symlink(target, root / "alias")
    assert resolve_bounded_file(root, "alias") == target


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO creation is unavailable")
def test_hash_bounded_file_rejects_a_special_file_without_blocking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression test for #21: the hashing path needs its own S_ISREG check.

    Reached only by defeating `resolve_bounded_file`, which is the point. That
    function decides with `is_file()` on the resolved name; `hash_bounded_file`
    decides again with `fstat` on the descriptor it is about to read. The
    second check exists to close the window between those two, so the window is
    what this test simulates. Handing the FIFO to `resolve_bounded_file`
    instead only re-tests the first check, passes, and proves nothing about the
    second.
    """
    fifo = tmp_path / "source.txt"
    os.mkfifo(fifo)
    monkeypatch.setattr(paths, "resolve_bounded_file", lambda root, relative: fifo)
    with pytest.raises(BoundedPathError, match="regular file"):
        hash_bounded_file(tmp_path, "source.txt", max_bytes=1024)


def _stale_size_fstat(size: int) -> Callable[[int], os.stat_result]:
    """Report a stale `st_size`, as a file that grew after `fstat` would."""
    real_fstat = os.fstat

    def fake_fstat(descriptor: int) -> os.stat_result:
        actual = real_fstat(descriptor)
        fields = list(actual)
        fields[6] = size
        return os.stat_result(fields)

    return fake_fstat


def test_hash_bounded_file_stops_a_file_that_grew_after_its_size_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The streaming byte counter, not `st_size`, is what actually bounds the read."""
    artifact = tmp_path / "artifact.json"
    artifact.write_bytes(b"x" * 4096)
    monkeypatch.setattr(os, "fstat", _stale_size_fstat(1))
    with pytest.raises(BoundedPathError, match="exceeds"):
        hash_bounded_file(tmp_path, "artifact.json", max_bytes=16)


def test_read_regular_file_stops_a_file_that_grew_after_its_size_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact = tmp_path / "artifact.json"
    artifact.write_bytes(b"x" * 4096)
    monkeypatch.setattr(os, "fstat", _stale_size_fstat(1))
    with pytest.raises(BoundedPathError, match="exceeds"):
        read_regular_file(artifact, max_bytes=16)
