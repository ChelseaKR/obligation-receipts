import errno
import hashlib
import os
from collections.abc import Callable
from pathlib import Path

import pytest

import obligation_receipts.paths as paths
from obligation_receipts.paths import (
    BoundedPathError,
    hash_bounded_file,
    read_bounded_file,
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


@pytest.mark.parametrize(
    "reader",
    [read_bounded_file, hash_bounded_file],
    ids=["read_bounded_file", "hash_bounded_file"],
)
def test_bounded_readers_refuse_a_symlink_swapped_in_after_resolution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    reader: Callable[..., object],
) -> None:
    """`O_NOFOLLOW` closes the window between resolving a name and opening it.

    `resolve_bounded_file` decides on a name: it resolves links, confirms the
    result is a regular file inside the root, and hands the path back. Both
    readers then `os.open` that path -- a second name lookup, on a filesystem
    anyone with write access to the directory can change in between. Planting a
    symlink there after the check is what `O_NOFOLLOW` refuses.

    Nothing simulated that window, so removing `O_NOFOLLOW` from either reader
    left the suite green: every other symlink test hands the link to
    `resolve_bounded_file`, which resolves it and never reaches the open flags.
    Monkeypatching the resolver is the only way to reach them, the same
    technique the FIFO test above uses for the second `S_ISREG` check.

    The errno assertion is the point of the test: `OSError` alone would also be
    satisfied by an unrelated failure, so it would not prove `O_NOFOLLOW` is
    what refused. Linux raises `ELOOP`; the BSDs, including macOS, may raise
    `EMLINK`.
    """
    target = tmp_path / "target.json"
    target.write_bytes(b'{"planted":true}')
    link = tmp_path / "artifact.json"
    os.symlink(target, link)
    monkeypatch.setattr(paths, "resolve_bounded_file", lambda root, relative: link)
    with pytest.raises(OSError) as raised:
        reader(tmp_path, "artifact.json", max_bytes=1024)
    assert raised.value.errno in {errno.ELOOP, errno.EMLINK}


def test_read_regular_file_accepts_a_file_of_exactly_the_cap(tmp_path: Path) -> None:
    """A file of exactly the cap is inside the cap, and must be read.

    Every other cap test uses `limit + 1`, so the boundary itself was never
    exercised and both of this reader's `> max_bytes` comparisons -- the
    `st_size` pre-check and the `len(data)` post-check -- could become `>=`
    unnoticed. That off-by-one is not a tightened limit, it is a wrong answer:
    a valid 2 MiB evidence artifact would be refused, the evaluator would
    record `missing`, and a tool whose whole contract is fail-closed reporting
    would say it did not observe evidence that is sitting there and is within
    its own documented bound.
    """
    payload = b"x" * 4096
    artifact = tmp_path / "artifact.json"
    artifact.write_bytes(payload)
    assert read_regular_file(artifact, max_bytes=4096, no_follow=True) == payload


def test_hash_bounded_file_accepts_a_file_of_exactly_the_cap(tmp_path: Path) -> None:
    """The hashing reader carries the same boundary, and its own streaming counter.

    See `test_read_regular_file_accepts_a_file_of_exactly_the_cap`: this reader
    repeats the `st_size` comparison and adds `total > max_bytes` over the
    stream, so it can drift to `>=` in two more places.
    """
    payload = b"x" * 4096
    (tmp_path / "artifact.json").write_bytes(payload)
    _, digest = hash_bounded_file(tmp_path, "artifact.json", max_bytes=4096)
    assert digest == hashlib.sha256(payload).hexdigest()


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
