"""Bounded inventory of an evidence root, with no evaluation in it.

`evaluate` answers "did the declared evidence pass". This module answers a
question nothing else here asks: **what is actually in the root**. An evidence
root holding fifty files while the manifest declares six is a silent gap --
extra evidence nobody evaluated, or leftovers from another contract -- and
until now nothing looked at the root except through declared paths.

Three properties are deliberate, and each has a test that fails without it:

* **No status, anywhere.** Not a `ResultStatus`, not a pass/fail, not an
  assertion outcome. A reader who sees "6 declared, 6 found" must not be able
  to read that as "6 passed", so the counts are named `declared_present` and
  `declared_absent` rather than anything from the evaluation vocabulary, and
  `evaluation_performed: false` is stated in the payload.
* **No content.** Files are identified by digest, never excerpted. The digest
  is a content identifier and nothing more.
* **A digest that could not be computed is `null` with a stated reason, never
  a zero, an empty string, or an absence quietly rendered as a value.** An
  unreadable file is counted under `unreadable`, listed with the reason it
  could not be read, and never counted as present. That failure mode -- a
  failed read published as if it were a measurement -- is what
  `_UNREADABLE_REASONS` and the `unreadable` bucket exist to prevent.

Symlinks are reported and never followed, including one pointing outside the
root: the walk uses `os.scandir` with `follow_symlinks=False` throughout, and a
symlink is classified from its own `lstat`, so nothing here can be tricked into
reading outside the root by a link planted inside it.
"""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path

from obligation_receipts.canonical import canonical_json_bytes, sha256_bytes
from obligation_receipts.models import JsonValue, Manifest
from obligation_receipts.paths import (
    BoundedPathError,
    hash_bounded_file,
    resolve_evidence_root,
    validate_portable_relative_path,
)

#: The evaluator's own artifact cap. An evidence file larger than this cannot be
#: evaluated, so the inventory must report it as unreadable rather than as a
#: present artifact the evaluator would later refuse.
MAX_ARTIFACT_BYTES = 2 * 1024 * 1024

#: A hard bound on the walk. A root with more entries than this is refused
#: rather than truncated: a truncated inventory reported as complete is the
#: exact defect this module is written against.
MAX_ENTRIES = 10_000

_LIMITATIONS: dict[str, JsonValue] = {
    "artifact_digest_authenticated": False,
    "artifact_digest_is_content_identifier_only": True,
    "evidence_content_read": False,
    "evidence_sufficiency_assessed": False,
    "evaluation_performed": False,
    "undeclared_files_classified": False,
}


class EvidenceRootAuditError(ValueError):
    """Raised when the evidence root cannot be inventoried at all."""


@dataclass(frozen=True, slots=True)
class _Entry:
    """One file found by the walk, or one declared path that was looked for."""

    relative_path: str
    digest: str | None
    unreadable_reason: str | None
    is_symlink: bool
    size_bytes: int | None


def _reason_for(exc: Exception) -> str:
    """A stable, non-sensitive reason string for a read that did not happen."""
    if isinstance(exc, BoundedPathError):
        return str(exc)
    if isinstance(exc, PermissionError):
        return "artifact is not readable by this process"
    if isinstance(exc, FileNotFoundError):
        return "artifact does not exist"
    if isinstance(exc, OSError):
        return "artifact could not be read"
    return "artifact could not be read"


def _walk(root: Path) -> list[_Entry]:
    """Every entry beneath root, without following a single symlink.

    `Path.rglob` follows directory symlinks, which would let a link inside the
    root enumerate a tree outside it. `os.scandir` with `follow_symlinks=False`
    on every test is the bounded seam, and a symlink is recorded from its own
    `lstat` without ever being opened.
    """
    entries: list[_Entry] = []
    stack: list[Path] = [root]
    seen = 0
    while stack:
        directory = stack.pop()
        try:
            scanned = list(os.scandir(directory))
        except OSError as exc:
            raise EvidenceRootAuditError(
                f"evidence root cannot be enumerated: {_reason_for(exc)}"
            ) from exc
        for item in sorted(scanned, key=lambda entry: entry.name):
            seen += 1
            if seen > MAX_ENTRIES:
                raise EvidenceRootAuditError(
                    f"evidence root holds more than {MAX_ENTRIES} entries; "
                    "refusing to report a truncated inventory as a complete one"
                )
            path = Path(item.path)
            relative = path.relative_to(root).as_posix()
            if item.is_symlink():
                entries.append(
                    _Entry(
                        relative_path=relative,
                        digest=None,
                        unreadable_reason="symlink reported and never followed",
                        is_symlink=True,
                        size_bytes=None,
                    )
                )
                continue
            if item.is_dir(follow_symlinks=False):
                stack.append(path)
                continue
            entries.append(_measure(root, relative, item))
    return sorted(entries, key=lambda entry: entry.relative_path)


def _measure(root: Path, relative: str, item: os.DirEntry[str]) -> _Entry:
    """Digest one non-symlink entry, or record why it has no digest."""
    try:
        info = item.stat(follow_symlinks=False)
    except OSError as exc:
        return _Entry(relative, None, _reason_for(exc), False, None)
    if not stat.S_ISREG(info.st_mode):
        return _Entry(relative, None, "not a regular file", False, None)
    try:
        validate_portable_relative_path(relative)
    except BoundedPathError as exc:
        # A file whose own name is not a portable relative path can never be
        # declared by a manifest, so it is undeclared by construction; it is
        # reported with the rule it breaks rather than silently skipped.
        return _Entry(relative, None, str(exc), False, info.st_size)
    # The size cap is NOT re-tested here. `hash_bounded_file` fstats the
    # descriptor and refuses anything over `max_bytes` before reading a byte,
    # so a second comparison against the same constant would be a duplicate
    # definition of "too large" that could drift from the seam that enforces
    # it -- and a negative control proved it was doing no work: deleting it
    # changed no observable behaviour, because the seam below already produced
    # the identical reason string.
    try:
        _, digest = hash_bounded_file(root, relative, max_bytes=MAX_ARTIFACT_BYTES)
    except (BoundedPathError, OSError) as exc:
        return _Entry(relative, None, _reason_for(exc), False, info.st_size)
    return _Entry(relative, digest, None, False, info.st_size)


def _declared_paths(manifest: Manifest) -> dict[str, list[str]]:
    """Declared relative path -> the evidence ids that reference it, sorted.

    A path referenced by more than one evidence id is the duplication the
    issue asks about, and it is visible here rather than inferred later.
    """
    references: dict[str, list[str]] = {}
    for obligation in manifest.obligations:
        for evidence in obligation.evidence:
            references.setdefault(evidence.path, []).append(evidence.evidence_id)
    return {path: sorted(ids) for path, ids in sorted(references.items())}


def _row(
    entry: _Entry | None,
    relative_path: str,
    evidence_ids: list[str] | None,
    include_local_details: bool,
) -> dict[str, JsonValue]:
    """One inventory row. `path` is local detail; the digest never is."""
    row: dict[str, JsonValue] = {
        "evidence_ids": list(evidence_ids) if evidence_ids is not None else [],
        "is_symlink": entry.is_symlink if entry is not None else False,
        "path": relative_path if include_local_details else None,
        "sha256": entry.digest if entry is not None else None,
        "size_bytes": entry.size_bytes if entry is not None else None,
        "unreadable_reason": entry.unreadable_reason if entry is not None else None,
    }
    return row


def audit_evidence_root(
    manifest: Manifest,
    evidence_root: Path,
    *,
    include_local_details: bool = False,
) -> dict[str, JsonValue]:
    """Inventory an evidence root against one manifest. No evaluation occurs.

    Relative paths are treated as local detail and redacted unless
    `include_local_details` is set, exactly as `evidence-plan` treats declared
    paths: a path such as `external/acme-health-2026/acr.json` names a client.
    Digests and counts are always present, so a redacted row is still
    matchable against a local file by whoever holds the root.
    """
    root = resolve_evidence_root(evidence_root)
    found = {entry.relative_path: entry for entry in _walk(root)}
    declared = _declared_paths(manifest)

    declared_rows: list[JsonValue] = []
    present = absent = unreadable = 0
    for path, evidence_ids in declared.items():
        entry = found.get(path)
        if entry is None:
            absent += 1
        elif entry.digest is None:
            unreadable += 1
        else:
            present += 1
        declared_rows.append(_row(entry, path, evidence_ids, include_local_details))

    undeclared_rows: list[JsonValue] = []
    undeclared_unreadable = 0
    for path, entry in sorted(found.items()):
        if path in declared:
            continue
        if entry.digest is None:
            undeclared_unreadable += 1
        undeclared_rows.append(_row(entry, path, [], include_local_details))

    multiply_referenced: list[JsonValue] = [
        _row(found.get(path), path, evidence_ids, include_local_details)
        for path, evidence_ids in declared.items()
        if len(evidence_ids) > 1
    ]
    symlinks: list[JsonValue] = [
        _row(entry, path, declared.get(path, []), include_local_details)
        for path, entry in sorted(found.items())
        if entry.is_symlink
    ]

    payload: dict[str, JsonValue] = {
        "contract_id": manifest.contract.contract_id,
        "contract_version": manifest.contract.version,
        "counts": {
            "declared_absent": absent,
            "declared_present": present,
            "declared_total": len(declared),
            "declared_unreadable": unreadable,
            "files_found": len(found),
            "multiply_referenced": len(multiply_referenced),
            "symlinks": len(symlinks),
            "undeclared": len(undeclared_rows),
            "undeclared_unreadable": undeclared_unreadable,
        },
        "declared": declared_rows,
        "decision_scope": "evidence_root_inventory_only",
        "detail_mode": "local_sensitive" if include_local_details else "portable_redacted",
        "limitations": dict(_LIMITATIONS),
        "manifest_sha256": manifest.manifest_sha256,
        "multiply_referenced": multiply_referenced,
        "schema_version": "obligation-receipts/evidence-root-audit/v0.1",
        "source_sha256": manifest.contract.source_sha256,
        "symlinks": symlinks,
        "undeclared": undeclared_rows,
    }
    return {
        "payload": payload,
        "payload_sha256": sha256_bytes(canonical_json_bytes(payload)),
        "schema_version": "obligation-receipts/evidence-root-audit-document/v0.1",
    }


def render_markdown(document: dict[str, JsonValue]) -> str:
    """Render one audit document for a status meeting.

    The heading says what the numbers are not, because the counts alone read
    like a verdict to anyone who has seen a test summary.
    """
    payload = document.get("payload")
    if not isinstance(payload, dict):
        raise EvidenceRootAuditError("audit document has no payload")
    counts = payload.get("counts")
    if not isinstance(counts, dict):
        raise EvidenceRootAuditError("audit document has no counts")
    lines = [
        "# Evidence root inventory",
        "",
        f"Contract `{payload['contract_id']}` version `{payload['contract_version']}`.",
        "",
        "This is an inventory, not an evaluation. No evidence was read for its",
        "content and nothing here passed or failed; a declared artifact being",
        "present says only that a file exists at the declared path.",
        "",
        "| Count | Value |",
        "|---|---:|",
    ]
    for key in sorted(counts):
        lines.append(f"| {key.replace('_', ' ')} | {counts[key]} |")
    lines.extend(["", f"Detail mode: `{payload['detail_mode']}`.", ""])
    if payload["detail_mode"] == "portable_redacted":
        lines.extend(
            [
                "Relative paths are redacted in this profile. Re-run with",
                "`--include-local-details` on a machine that already holds the",
                "evidence root to see them.",
                "",
            ]
        )
    return "\n".join(lines)
