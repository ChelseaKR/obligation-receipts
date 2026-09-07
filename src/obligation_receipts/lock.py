"""Freeze the declared evidence at collection time.

Evidence is collected days before it is evaluated. In between, a build can be
re-run and a result file regenerated. `evaluate` will honestly hash whatever
bytes it finds and record that digest in the receipt -- but nobody learns that
the bytes evaluated are not the bytes collected, because nothing recorded what
was collected.

The threat model's local-race mitigations cover the moment of reading: one
descriptor, `O_NOFOLLOW`, `fstat` on the open descriptor. This closes the other
window, the days on either side of it. `freeze-evidence` digests every declared
artifact without evaluating anything; `evaluate --lock` refuses to produce a
receipt at all when what it finds is not what was frozen.

What the lock does not do
-------------------------
It changes what is *refused*, not what is *judged*. An artifact absent when the
lock was taken and still absent at evaluation is still `missing`, exactly as
before -- absence is a state the result algebra already models, and turning it
into a refusal would collapse "the evidence was never delivered" into "the tool
could not run". Every refusal below is about a *change* between the two moments.

It is unsigned, like the receipt, and it makes no claim about who took it or
when. A party who can rewrite the evidence can rewrite the lock beside it. What
the lock establishes is that the evidence and the lock were consistent at one
moment, which is what a third party replaying the evaluation needs and is
strictly more than the nothing that was recorded before.

Three states, kept distinct
---------------------------
A declared artifact is frozen as ``present`` with a digest, or as ``absent``
with no digest -- and nothing else. A path that cannot be read for any *other*
reason (it escapes the evidence root, it is not a regular file, it exceeds the
artifact cap) makes `freeze-evidence` refuse to write a lock at all, naming the
evidence id.

That refusal is deliberate. Recording an unreadable artifact as ``absent`` would
render a failed read as a real observation of absence, and every later
comparison against it would be comparing against something nobody measured. The
lock would then say "this was not there" about a file that was there and could
not be read, which is the failure this project exists to make impossible.
"""

from __future__ import annotations

import os
import re
import tempfile
from json import JSONDecodeError
from pathlib import Path

from obligation_receipts.canonical import (
    StrictJsonError,
    canonical_json_bytes,
    loads_json_strict,
    sha256_bytes,
)
from obligation_receipts.models import JsonValue, Manifest
from obligation_receipts.paths import (
    BoundedPathError,
    hash_bounded_file,
    read_regular_file,
    resolve_evidence_root,
)

LOCK_SCHEMA_VERSION = "obligation-receipts/evidence-lock/v0.1"

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")

#: The artifact cap this module reads under. It must equal the evaluator's:
#: a lock that could digest a file `evaluate` will later refuse to read would
#: freeze an artifact into a state no evaluation can ever match.
#: `tests/test_misuse_boundaries.py` compares every `MAX_ARTIFACT_BYTES` in the
#: package and fails when they disagree, so this copy is held to the others
#: rather than trusted to stay in step.
MAX_ARTIFACT_BYTES = 2 * 1024 * 1024

_MAX_LOCK_BYTES = 2 * 1024 * 1024

_LOCK_FIELDS = {
    "schema_version",
    "contract_id",
    "contract_version",
    "manifest_sha256",
    "source_sha256",
    "artifacts",
}
_ARTIFACT_FIELDS = {"evidence_id", "path", "status", "sha256"}

PRESENT = "present"
ABSENT = "absent"


class EvidenceLockError(ValueError):
    """Raised when a lock cannot be built, read, or satisfied.

    One class for all three, because every one of them means the same thing to
    a caller: no receipt is produced. The CLI maps it to `INPUT_ERROR`, which
    the exit-code contract reserves for "no result document" -- a locked
    evaluation that refuses has not observed a failure, it has declined to
    observe at all.
    """


def _declared_artifacts(manifest: Manifest) -> list[tuple[str, str]]:
    """Every declared ``(evidence_id, path)``, in manifest order.

    Duplicate evidence ids would make the lock ambiguous about which artifact a
    row describes, so they are refused here rather than silently collapsed by
    the dict that indexes them later.
    """

    seen: set[str] = set()
    declared: list[tuple[str, str]] = []
    for obligation in manifest.obligations:
        for spec in obligation.evidence:
            if spec.evidence_id in seen:
                raise EvidenceLockError(
                    f"evidence id {spec.evidence_id!r} is declared more than once; "
                    "a lock cannot describe two artifacts under one id"
                )
            seen.add(spec.evidence_id)
            declared.append((spec.evidence_id, spec.path))
    return declared


def build_evidence_lock(manifest: Manifest, evidence_root: Path) -> dict[str, JsonValue]:
    """Digest every declared artifact, evaluating nothing.

    No pointer is resolved, no assertion is compared and no attestation is
    checked. The lock records bytes and paths; what those bytes mean is the
    evaluator's question, asked later and separately.

    Rows are ordered by evidence id rather than by manifest order, so the same
    manifest and the same evidence produce byte-identical lock bytes however
    the obligations happen to be arranged.
    """

    resolved_root = resolve_evidence_root(evidence_root)
    rows: list[JsonValue] = []
    for evidence_id, relative_path in sorted(_declared_artifacts(manifest)):
        try:
            _path, digest = hash_bounded_file(
                resolved_root, relative_path, max_bytes=MAX_ARTIFACT_BYTES
            )
        except FileNotFoundError:
            rows.append(
                {
                    "evidence_id": evidence_id,
                    "path": relative_path,
                    "status": ABSENT,
                    "sha256": None,
                }
            )
        except (BoundedPathError, OSError) as exc:
            # Not `absent`. See the module docstring: a read that could not
            # happen is not an observation that the file was not there.
            raise EvidenceLockError(
                f"evidence {evidence_id!r} at {relative_path!r} cannot be digested: {exc}"
            ) from exc
        else:
            rows.append(
                {
                    "evidence_id": evidence_id,
                    "path": relative_path,
                    "status": PRESENT,
                    "sha256": digest,
                }
            )
    return {
        "artifacts": rows,
        "contract_id": manifest.contract.contract_id,
        "contract_version": manifest.contract.version,
        "manifest_sha256": manifest.manifest_sha256,
        "schema_version": LOCK_SCHEMA_VERSION,
        "source_sha256": manifest.contract.source_sha256,
    }


def lock_digest(lock: dict[str, JsonValue]) -> str:
    """The digest a receipt records to say which lock bound it."""

    return sha256_bytes(canonical_json_bytes(lock))


def _closed(value: JsonValue | None, fields: set[str], context: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict) or set(value) != fields:
        raise EvidenceLockError(f"{context} fields do not match the closed schema")
    return value


def _validate_lock(lock: dict[str, JsonValue]) -> dict[str, JsonValue]:
    """Check the whole document's shape before any field is believed."""

    document = _closed(lock, _LOCK_FIELDS, "evidence lock")
    if document.get("schema_version") != LOCK_SCHEMA_VERSION:
        raise EvidenceLockError(
            f"evidence lock schema_version is unsupported; expected {LOCK_SCHEMA_VERSION}"
        )
    rows = document.get("artifacts")
    if not isinstance(rows, list):
        raise EvidenceLockError("evidence lock artifacts must be a list")
    seen: set[str] = set()
    for row in rows:
        evidence_id = _validate_row(row)
        if evidence_id in seen:
            raise EvidenceLockError(f"evidence lock names {evidence_id!r} more than once")
        seen.add(evidence_id)
    return document


def _validate_row(row: JsonValue) -> str:
    """One artifact row, checked before any field in it is believed."""

    artifact = _closed(row, _ARTIFACT_FIELDS, "evidence lock artifact")
    evidence_id = artifact.get("evidence_id")
    status = artifact.get("status")
    digest = artifact.get("sha256")
    if not isinstance(evidence_id, str) or not evidence_id.strip():
        raise EvidenceLockError("evidence lock artifact id must be a non-empty string")
    if not isinstance(artifact.get("path"), str):
        raise EvidenceLockError(f"evidence lock artifact {evidence_id!r} has no path")
    if status == PRESENT:
        if not isinstance(digest, str) or not _SHA256_PATTERN.fullmatch(digest):
            raise EvidenceLockError(
                f"evidence lock artifact {evidence_id!r} is present with no digest"
            )
    elif status == ABSENT:
        # An absent row carrying a digest would be two claims at once, and a
        # reader branching on either one would be right half the time.
        if digest is not None:
            raise EvidenceLockError(
                f"evidence lock artifact {evidence_id!r} is absent but carries a digest"
            )
    else:
        raise EvidenceLockError(f"evidence lock artifact {evidence_id!r} has an unsupported status")
    return evidence_id


def load_evidence_lock(path: Path) -> dict[str, JsonValue]:
    """Load and validate a bounded evidence lock."""

    try:
        data = read_regular_file(path, max_bytes=_MAX_LOCK_BYTES)
        raw = loads_json_strict(data)
    except BoundedPathError as exc:
        raise EvidenceLockError(f"evidence lock cannot be read safely: {exc}") from exc
    except (JSONDecodeError, RecursionError, StrictJsonError) as exc:
        raise EvidenceLockError(f"evidence lock is not strict JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise EvidenceLockError("evidence lock must be a JSON object")
    return _validate_lock(raw)


def write_evidence_lock(path: Path, lock: dict[str, JsonValue]) -> None:
    """Validate and atomically write one bounded canonical lock."""

    _validate_lock(lock)
    encoded = canonical_json_bytes(lock) + b"\n"
    if len(encoded) > _MAX_LOCK_BYTES:
        raise EvidenceLockError("evidence lock exceeds the 2 MiB limit")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _current_state(root: Path, relative_path: str, evidence_id: str) -> tuple[str, str | None]:
    """What the evidence root says about one artifact right now."""

    try:
        _path, digest = hash_bounded_file(root, relative_path, max_bytes=MAX_ARTIFACT_BYTES)
    except FileNotFoundError:
        return ABSENT, None
    except (BoundedPathError, OSError) as exc:
        raise EvidenceLockError(
            f"evidence {evidence_id!r} at {relative_path!r} cannot be digested: {exc}"
        ) from exc
    return PRESENT, digest


def _enforce_one(
    root: Path, evidence_id: str, relative_path: str, row: dict[str, JsonValue]
) -> None:
    """Compare one artifact against its frozen row, refusing on any difference.

    Four outcomes, and each is decided rather than defaulted:

    ``absent`` then ``absent``   the evidence was never collected. Not a
                                 refusal: the evaluator already models this as
                                 `missing`, which is a finding, not a failure of
                                 the tool.
    ``absent`` then ``present``  refused. Something arrived after collection,
                                 and whatever it is, nobody collected it.
    ``present`` then ``absent``  refused. What was collected is gone.
    ``present`` then ``present`` refused unless the digests are equal.
    """

    if row.get("path") != relative_path:
        raise EvidenceLockError(
            f"evidence {evidence_id!r} was frozen at {row.get('path')!r} "
            f"and the manifest now declares {relative_path!r}"
        )
    status, digest = _current_state(root, relative_path, evidence_id)
    was = row.get("status")
    if was == ABSENT:
        if status == PRESENT:
            raise EvidenceLockError(
                f"evidence {evidence_id!r} was absent when the lock was taken and is "
                "present now; it was never collected, so it is not evaluated"
            )
        return
    if status == ABSENT:
        raise EvidenceLockError(
            f"evidence {evidence_id!r} was frozen and is gone; the evidence "
            "collected is not the evidence present"
        )
    if digest != row.get("sha256"):
        raise EvidenceLockError(
            f"evidence {evidence_id!r} changed after the lock was taken "
            f"({row.get('sha256')} -> {digest})"
        )


def enforce_evidence_lock(
    manifest: Manifest, evidence_root: Path, lock: dict[str, JsonValue]
) -> str:
    """Refuse unless the evidence is exactly what the lock froze.

    Returns the lock's digest, which the receipt records, so a caller cannot
    obtain the digest without having passed the check that earns it.

    Every branch below refuses. There is no "warn and continue": a lock that
    reported a mismatch and let the evaluation proceed would put the mismatch
    in a log nobody reads and the resulting receipt would look exactly like an
    unlocked one.
    """

    document = _validate_lock(lock)
    if document.get("manifest_sha256") != manifest.manifest_sha256:
        raise EvidenceLockError(
            "evidence lock was built against a different manifest "
            f"({document.get('manifest_sha256')} != {manifest.manifest_sha256})"
        )
    if document.get("source_sha256") != manifest.contract.source_sha256:
        raise EvidenceLockError("evidence lock was built against a different approved source")

    rows = document["artifacts"]
    if not isinstance(rows, list):  # pragma: no cover - _validate_lock guarantees this
        raise EvidenceLockError("evidence lock artifacts must be a list")
    frozen = {
        str(row["evidence_id"]): row
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("evidence_id"), str)
    }

    resolved_root = resolve_evidence_root(evidence_root)
    declared = _declared_artifacts(manifest)
    for evidence_id, relative_path in sorted(declared):
        row = frozen.get(evidence_id)
        if row is None:
            raise EvidenceLockError(
                f"evidence {evidence_id!r} is declared by the manifest and absent from the lock"
            )
        _enforce_one(resolved_root, evidence_id, relative_path, row)

    extra = sorted(set(frozen) - {evidence_id for evidence_id, _path in declared})
    if extra:
        raise EvidenceLockError(
            "evidence lock names artifacts the manifest does not declare: " + ", ".join(extra)
        )
    return lock_digest(document)
