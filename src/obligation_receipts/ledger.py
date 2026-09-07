"""A hash-chained ledger of the evaluations made against one contract.

Each `evaluate` writes an independent receipt. Nothing binds evaluation N to
N-1, so a later receipt can be dropped, reordered, or replaced without trace,
and an acceptance lead reconstructing "what did we know on each date" has only
file timestamps — which the receipt envelope already declares untrusted.

The receipt proves a bounded evaluation. The ledger proves the *sequence* of
them. Each entry carries the `entry_hash` of the entry before it, so recomputing
each hash and walking the links detects an entry edited in place, and an entry
inserted, removed, or reordered anywhere except at the end.

What a clean chain does not establish
-------------------------------------
Three tampers leave no trace, and `ledger-verify` prints them beside its PASS
line rather than letting PASS be read as more than it is:

1. **Entries deleted from the end.** Nothing outside the file records how long
   the chain should be, so a shorter chain verifies.
2. **A wholesale rewrite.** The hash has no secret in it. The chain proves the
   integrity of what is recorded, never who recorded it.
3. **An evaluation never appended.** A clean chain is not evidence of
   completeness.

Closing any of those needs an out-of-band copy of the expected head or entry
count, or a signature — M0 has neither, and this module does not pretend
otherwise. Signatures and roles are #53.

No clock
--------
The entry records the receipt's own `claimed_generated_at`, carried forward as
what it is: caller-declared, untrusted, exactly as the envelope declares it.
Nothing here reads a clock. That is also what makes the ledger byte-reproducible
— appending the same receipts to a fresh ledger produces the same bytes, so a
third party can rebuild it and compare.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, replace
from json import JSONDecodeError
from pathlib import Path

from obligation_receipts.canonical import (
    StrictJsonError,
    canonical_json_bytes,
    loads_json_strict,
    sha256_bytes,
)
from obligation_receipts.models import JsonValue
from obligation_receipts.paths import BoundedPathError, read_regular_file

LEDGER_SCHEMA_VERSION = "obligation-receipts/receipt-ledger/v0.1"

#: The `prev_hash` of the first entry. There is no prior entry to link to, so
#: the chain is anchored to a fixed all-zero digest rather than to `null` — a
#: reader comparing digests never has to branch on a type.
GENESIS_PREV_HASH = "0" * 64

_MAX_LEDGER_BYTES = 8 * 1024 * 1024
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")

#: The fields the entry hash is taken over: every field except the hash itself.
#: Held as one tuple so the hashed payload and the written line cannot disagree
#: about the schema — a field added to one and forgotten in the other would be
#: a field the chain does not actually protect.
_HASHED_FIELDS = (
    "schema_version",
    "index",
    "contract_id",
    "contract_version",
    "manifest_sha256",
    "source_sha256",
    "payload_sha256",
    "overall_status",
    "claimed_generated_at",
    "prev_hash",
)

_ENTRY_FIELDS = frozenset({*_HASHED_FIELDS, "entry_hash"})


class LedgerError(ValueError):
    """Raised when a ledger cannot be read, or a receipt cannot be appended.

    Distinct from a broken chain, which is a *finding* about the records and
    exits 1. This is an input error and exits 2: no result document.
    """


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    """One append-only record of an evaluation.

    ``claimed_generated_at`` is copied from the receipt envelope and is
    caller-declared. It is in the hashed payload so it cannot be edited without
    breaking the chain, which is a different claim from it being *true*: the
    chain fixes the order the entries were written in, not when they happened.
    """

    index: int
    contract_id: str
    contract_version: str
    manifest_sha256: str
    source_sha256: str
    payload_sha256: str
    overall_status: str
    claimed_generated_at: str
    prev_hash: str
    entry_hash: str

    def to_dict(self) -> dict[str, JsonValue]:
        record: dict[str, JsonValue] = {
            "schema_version": LEDGER_SCHEMA_VERSION,
            "index": self.index,
            "contract_id": self.contract_id,
            "contract_version": self.contract_version,
            "manifest_sha256": self.manifest_sha256,
            "source_sha256": self.source_sha256,
            "payload_sha256": self.payload_sha256,
            "overall_status": self.overall_status,
            "claimed_generated_at": self.claimed_generated_at,
            "prev_hash": self.prev_hash,
            "entry_hash": self.entry_hash,
        }
        return record


def hashed_payload(entry: LedgerEntry) -> dict[str, JsonValue]:
    """Everything the entry hash covers, which is every field but the hash."""

    record = entry.to_dict()
    return {name: record[name] for name in _HASHED_FIELDS}


def compute_entry_hash(entry: LedgerEntry) -> str:
    """SHA-256 over the canonical bytes of the hashed payload.

    The same seam every other digest in this project goes through, so a reader
    who can recompute a receipt digest can recompute this one the same way.
    """

    return sha256_bytes(canonical_json_bytes(hashed_payload(entry)))


def _string(record: dict[str, JsonValue], key: str, index: int) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        raise LedgerError(f"ledger entry {index}: {key} must be a non-empty string")
    return value


def _digest(record: dict[str, JsonValue], key: str, index: int) -> str:
    value = _string(record, key, index)
    if not _SHA256_PATTERN.fullmatch(value):
        raise LedgerError(f"ledger entry {index}: {key} must be a lowercase SHA-256 digest")
    return value


def _entry_from(record: JsonValue, position: int) -> LedgerEntry:
    """One line, validated before any field in it is believed."""

    if not isinstance(record, dict) or set(record) != _ENTRY_FIELDS:
        raise LedgerError(f"ledger entry {position}: fields do not match the closed schema")
    if record.get("schema_version") != LEDGER_SCHEMA_VERSION:
        raise LedgerError(
            f"ledger entry {position}: schema_version is unsupported; "
            f"expected {LEDGER_SCHEMA_VERSION}"
        )
    index = record.get("index")
    if isinstance(index, bool) or not isinstance(index, int) or index < 0:
        raise LedgerError(f"ledger entry {position}: index must be a non-negative integer")
    return LedgerEntry(
        index=index,
        contract_id=_string(record, "contract_id", position),
        contract_version=_string(record, "contract_version", position),
        manifest_sha256=_digest(record, "manifest_sha256", position),
        source_sha256=_digest(record, "source_sha256", position),
        payload_sha256=_digest(record, "payload_sha256", position),
        overall_status=_string(record, "overall_status", position),
        claimed_generated_at=_string(record, "claimed_generated_at", position),
        prev_hash=_digest(record, "prev_hash", position),
        entry_hash=_digest(record, "entry_hash", position),
    )


def read_ledger(path: Path) -> list[LedgerEntry]:
    """Read a bounded JSONL ledger, or return an empty list if it does not exist.

    A file that exists and cannot be parsed raises rather than reading as empty.
    An unreadable ledger returning ``[]`` would make the first append behave
    exactly like a genesis append — the chain would silently restart, and every
    entry before the corruption would be gone with no record that they existed.
    """

    if not path.exists():
        return []
    try:
        data = read_regular_file(path, max_bytes=_MAX_LEDGER_BYTES)
    except BoundedPathError as exc:
        raise LedgerError(f"ledger cannot be read safely: {exc}") from exc
    entries: list[LedgerEntry] = []
    for position, line in enumerate(data.decode("utf-8").splitlines()):
        if not line.strip():
            continue
        try:
            record = loads_json_strict(line.encode("utf-8"))
        except (JSONDecodeError, RecursionError, StrictJsonError) as exc:
            raise LedgerError(f"ledger entry {position} is not strict JSON: {exc}") from exc
        entries.append(_entry_from(record, position))
    return entries


def entry_for_receipt(receipt: dict[str, JsonValue], *, index: int, prev_hash: str) -> LedgerEntry:
    """Build the entry one verified receipt contributes to the chain.

    The receipt must already have passed ``verify_receipt``; this reads its
    fields rather than re-deciding whether they are trustworthy, so there is one
    definition of a valid receipt and it is not this module's.
    """

    payload = receipt.get("payload")
    envelope = receipt.get("envelope")
    if not isinstance(payload, dict) or not isinstance(envelope, dict):
        raise LedgerError("receipt has no payload or envelope object")
    contract = payload.get("contract")
    if not isinstance(contract, dict):
        raise LedgerError("receipt payload has no contract object")
    payload_sha256 = receipt.get("payload_sha256")
    if not isinstance(payload_sha256, str):
        raise LedgerError("receipt has no payload_sha256")

    draft = LedgerEntry(
        index=index,
        contract_id=_string(contract, "id", index),
        contract_version=_string(contract, "version", index),
        manifest_sha256=_digest(payload, "manifest_sha256", index),
        source_sha256=_digest(contract, "source_sha256", index),
        payload_sha256=payload_sha256,
        overall_status=_string(payload, "overall_status", index),
        # Carried forward as declared. See the module docstring: recording it
        # here binds it to the chain, which is not the same as trusting it.
        claimed_generated_at=_string(envelope, "claimed_generated_at", index),
        prev_hash=prev_hash,
        entry_hash="",
    )
    return replace(draft, entry_hash=compute_entry_hash(draft))


def append_receipt(path: Path, receipt: dict[str, JsonValue]) -> LedgerEntry:
    """Append one verified receipt to the chain, or refuse and change nothing.

    A receipt for a different contract is refused by name. A ledger is the
    record of one contract's evaluations; mixing two would make the chain's
    order meaningless for both, and neither party could read their own sequence
    out of it.

    Every check happens before the file is opened for writing, so a refusal
    leaves the ledger byte-identical.
    """

    entries = read_ledger(path)
    prev_hash = entries[-1].entry_hash if entries else GENESIS_PREV_HASH
    entry = entry_for_receipt(receipt, index=len(entries), prev_hash=prev_hash)
    if entries and entry.contract_id != entries[0].contract_id:
        raise LedgerError(
            f"receipt is for contract {entry.contract_id!r} and this ledger records "
            f"{entries[0].contract_id!r}; a ledger holds one contract's evaluations"
        )
    line = canonical_json_bytes(entry.to_dict()) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as handle:
        handle.write(line)
        handle.flush()
        os.fsync(handle.fileno())
    return entry


#: What a clean chain does not establish, stated next to every PASS. Single
#: sourced so the CLI cannot print a shorter list than the one the module
#: docstring argues for.
PASS_LIMITS = (
    "entries deleted from the end leave a shorter chain that still verifies; "
    "nothing outside the file records how long the chain should be",
    "a rewrite of the whole file with recomputed hashes verifies; the chain has no "
    "secret and proves integrity of what is recorded, not authorship",
    "an evaluation that was never appended leaves no trace; a clean chain is not "
    "evidence of completeness",
    "the recorded times are the receipts' own caller-declared timestamps; the chain "
    "fixes the order entries were written in, not when the evaluations happened",
)


def verify_chain(entries: list[LedgerEntry]) -> list[str]:
    """Every break in the chain, naming the index. Empty means no record was altered.

    Three independent checks per entry, because they catch different tampers and
    a single one would miss two of them: the index must be contiguous from zero
    (nothing inserted, dropped, or reordered in the middle), the `prev_hash`
    must link to the entry before it, and the recomputed `entry_hash` must match
    the stored one (no field was edited).

    An empty list is not a claim that the ledger is complete or authentic. See
    ``PASS_LIMITS``.
    """

    problems: list[str] = []
    for position, entry in enumerate(entries):
        if entry.index != position:
            problems.append(
                f"entry {position}: index {entry.index} is not contiguous (expected {position})"
            )
        expected_prev = GENESIS_PREV_HASH if position == 0 else entries[position - 1].entry_hash
        if entry.prev_hash != expected_prev:
            problems.append(f"entry {entry.index}: prev_hash does not link to the entry before it")
        if compute_entry_hash(entry) != entry.entry_hash:
            problems.append(f"entry {entry.index}: entry_hash mismatch, the record was altered")
    return problems
