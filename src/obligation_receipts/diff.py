"""What moved between two receipts of one contract, and why.

A receipt says what was checked. A retest after remediation asks a different
question: *what moved since last time?* Which obligations went from `fail` to
`pass`, which from `missing` to `pass`, which were added or removed by a
manifest change -- and, for each, whether the cause was new evidence, a changed
evidence digest, a changed manifest, or a changed source.

Three constraints keep this a report rather than a verdict.

**It never re-evaluates.** Every status here is copied from a receipt that
already recorded it. Nothing on this path reads an evidence root, so a diff
cannot disagree with the receipts it summarises.

**It uses only the domain's own labels.** `pass`, `fail`, `missing`,
`review_required`, `unverifiable` and the four overall states -- no "improved",
"regressed", "resolved" or "compliant". Those words are conclusions, and a diff
that spoke them would become a legal conclusion by accident.

**Both receipts are verified before anything is compared.** `verify_receipt`
re-derives each payload digest, so a diff is never computed over a document that
does not hash to what it claims. A diff of two unverified receipts is a
confident statement about nothing, which is the failure mode this repository
treats as the important one.

`contract_id` must match. Diffing two contracts is a category error, not a large
change set, and reporting every obligation as `added` and `removed` would dress
that mistake up as a result.
"""

from __future__ import annotations

from obligation_receipts.canonical import canonical_json_bytes, sha256_bytes
from obligation_receipts.models import JsonValue
from obligation_receipts.receipt import ReceiptError, verify_receipt

#: The five change classes. An obligation present on both sides is exactly one
#: of the first three; `added` and `removed` cover presence changes.
UNCHANGED = "unchanged"
STATUS_CHANGED = "status_changed"
EVIDENCE_CHANGED = "evidence_changed"
ADDED = "added"
REMOVED = "removed"

_LIMITATIONS: dict[str, JsonValue] = {
    "cause_is_attributed_not_proven": True,
    "evidence_re_evaluated": False,
    "legal_interpretation_performed": False,
    "official_decision_made": False,
    "remedies_suggested": False,
}


class ReceiptDiffError(ValueError):
    """Raised when two receipts cannot be compared at all."""


def _payload(receipt: dict[str, JsonValue], side: str) -> dict[str, JsonValue]:
    """Verify one receipt and return its payload.

    Verification happens here rather than in the caller so no path into this
    module can skip it.
    """
    try:
        verify_receipt(receipt)
    except ReceiptError as exc:
        raise ReceiptDiffError(f"{side} receipt does not verify: {exc}") from exc
    payload = receipt.get("payload")
    if not isinstance(payload, dict):
        raise ReceiptDiffError(f"{side} receipt has no payload")
    return payload


def _contract(payload: dict[str, JsonValue], side: str) -> dict[str, JsonValue]:
    contract = payload.get("contract")
    if not isinstance(contract, dict):
        raise ReceiptDiffError(f"{side} receipt payload has no contract")
    return contract


def _obligations(payload: dict[str, JsonValue], side: str) -> dict[str, dict[str, JsonValue]]:
    raw = payload.get("obligations")
    if not isinstance(raw, list):
        raise ReceiptDiffError(f"{side} receipt payload has no obligations array")
    result: dict[str, dict[str, JsonValue]] = {}
    for item in raw:
        if not isinstance(item, dict):
            raise ReceiptDiffError(f"{side} receipt has a malformed obligation")
        obligation_id = item.get("id")
        if not isinstance(obligation_id, str):
            raise ReceiptDiffError(f"{side} receipt has an obligation with no id")
        result[obligation_id] = item
    return result


def _evidence_by_id(obligation: dict[str, JsonValue]) -> dict[str, dict[str, JsonValue]]:
    raw = obligation.get("evidence")
    if not isinstance(raw, list):
        return {}
    items: dict[str, dict[str, JsonValue]] = {}
    for entry in raw:
        if isinstance(entry, dict) and isinstance(entry.get("id"), str):
            items[str(entry["id"])] = entry
    return items


def _evidence_changes(
    prior: dict[str, JsonValue], current: dict[str, JsonValue]
) -> list[JsonValue]:
    """Per-evidence movement, digests on both sides.

    A digest of `None` is preserved as `None`. It means the artifact was never
    read -- absent, oversized, or unparseable -- and rendering that as an empty
    string would make "we could not read it" look like a value that was compared.
    """
    before = _evidence_by_id(prior)
    after = _evidence_by_id(current)
    changes: list[JsonValue] = []
    for evidence_id in sorted(set(before) | set(after)):
        was = before.get(evidence_id)
        now = after.get(evidence_id)
        if was is None:
            changes.append(
                {
                    "id": evidence_id,
                    "change": ADDED,
                    "prior_artifact_sha256": None,
                    "current_artifact_sha256": (now or {}).get("artifact_sha256"),
                    "prior_status": None,
                    "current_status": (now or {}).get("status"),
                }
            )
            continue
        if now is None:
            changes.append(
                {
                    "id": evidence_id,
                    "change": REMOVED,
                    "prior_artifact_sha256": was.get("artifact_sha256"),
                    "current_artifact_sha256": None,
                    "prior_status": was.get("status"),
                    "current_status": None,
                }
            )
            continue
        digest_moved = was.get("artifact_sha256") != now.get("artifact_sha256")
        status_moved = was.get("status") != now.get("status")
        if not digest_moved and not status_moved:
            continue
        changes.append(
            {
                "id": evidence_id,
                "change": STATUS_CHANGED if status_moved else EVIDENCE_CHANGED,
                "prior_artifact_sha256": was.get("artifact_sha256"),
                "current_artifact_sha256": now.get("artifact_sha256"),
                "prior_status": was.get("status"),
                "current_status": now.get("status"),
            }
        )
    return changes


def _causes(
    prior: dict[str, JsonValue],
    current: dict[str, JsonValue],
    evidence_changes: list[JsonValue],
    manifest_changed: bool,
    source_changed: bool,
) -> list[JsonValue]:
    """Which observable differences could account for this obligation moving.

    Attribution, not proof, and the limitations block says so. Several causes
    can hold at once -- a manifest edit that also swaps an artifact -- and all
    of them are listed rather than one being picked as *the* cause, because
    nothing here can rank them.
    """
    causes: list[JsonValue] = []
    if any(
        isinstance(change, dict) and change.get("change") == ADDED for change in evidence_changes
    ):
        causes.append("new_evidence")
    if any(
        isinstance(change, dict) and change.get("change") == REMOVED for change in evidence_changes
    ):
        causes.append("evidence_removed")
    if any(
        isinstance(change, dict)
        and change.get("prior_artifact_sha256") != change.get("current_artifact_sha256")
        and change.get("change") not in {ADDED, REMOVED}
        for change in evidence_changes
    ):
        causes.append("evidence_digest_changed")
    if prior.get("classification") != current.get("classification"):
        causes.append("classification_changed")
    if prior.get("criticality") != current.get("criticality"):
        causes.append("criticality_changed")
    if manifest_changed:
        causes.append("manifest_changed")
    if source_changed:
        causes.append("source_changed")
    return causes


def diff_receipts(
    prior_receipt: dict[str, JsonValue],
    current_receipt: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    """Compare two verified receipts of one contract. Nothing is re-evaluated."""
    prior = _payload(prior_receipt, "prior")
    current = _payload(current_receipt, "current")
    prior_contract = _contract(prior, "prior")
    current_contract = _contract(current, "current")

    prior_id = prior_contract.get("id")
    current_id = current_contract.get("id")
    if prior_id != current_id:
        raise ReceiptDiffError(
            "receipts are for different contracts "
            f"({prior_id!r} and {current_id!r}); a diff across contracts is not meaningful"
        )

    manifest_changed = prior.get("manifest_sha256") != current.get("manifest_sha256")
    source_changed = prior_contract.get("source_sha256") != current_contract.get("source_sha256")

    before = _obligations(prior, "prior")
    after = _obligations(current, "current")
    changes: list[JsonValue] = []
    tally = {UNCHANGED: 0, STATUS_CHANGED: 0, EVIDENCE_CHANGED: 0, ADDED: 0, REMOVED: 0}

    for obligation_id in sorted(set(before) | set(after)):
        was = before.get(obligation_id)
        now = after.get(obligation_id)
        if was is None or now is None:
            change = ADDED if was is None else REMOVED
            side = now if was is None else was
            tally[change] += 1
            changes.append(
                {
                    "causes": ["manifest_changed"] if manifest_changed else [],
                    "change": change,
                    "current_status": (now or {}).get("status"),
                    "evidence": [],
                    "id": obligation_id,
                    "prior_status": (was or {}).get("status"),
                    "clause_ref": (side or {}).get("clause_ref"),
                }
            )
            continue
        evidence_changes = _evidence_changes(was, now)
        status_moved = was.get("status") != now.get("status")
        if status_moved:
            change = STATUS_CHANGED
        elif evidence_changes:
            change = EVIDENCE_CHANGED
        else:
            change = UNCHANGED
        tally[change] += 1
        changes.append(
            {
                "causes": _causes(was, now, evidence_changes, manifest_changed, source_changed)
                if change != UNCHANGED
                else [],
                "change": change,
                "current_status": now.get("status"),
                "evidence": evidence_changes,
                "id": obligation_id,
                "prior_status": was.get("status"),
                "clause_ref": now.get("clause_ref"),
            }
        )

    payload: dict[str, JsonValue] = {
        "changed": [item for item in changes if _change_of(item) != UNCHANGED],
        "contract_id": prior_id,
        "counts": dict(tally),
        "decision_scope": "receipt_to_receipt_comparison_only",
        "limitations": dict(_LIMITATIONS),
        "manifest_changed": manifest_changed,
        "obligations": changes,
        "overall_status_transition": {
            "changed": prior.get("overall_status") != current.get("overall_status"),
            "current": current.get("overall_status"),
            "prior": prior.get("overall_status"),
        },
        "schema_version": "obligation-receipts/receipt-diff/v0.1",
        "source_changed": source_changed,
        "sides": {
            "current": {
                "manifest_sha256": current.get("manifest_sha256"),
                "source_sha256": current_contract.get("source_sha256"),
            },
            "prior": {
                "manifest_sha256": prior.get("manifest_sha256"),
                "source_sha256": prior_contract.get("source_sha256"),
            },
        },
    }
    return {
        "payload": payload,
        "payload_sha256": sha256_bytes(canonical_json_bytes(payload)),
        "schema_version": "obligation-receipts/receipt-diff-document/v0.1",
    }


def _change_of(item: JsonValue) -> str:
    return str(item["change"]) if isinstance(item, dict) else ""


def render_markdown(document: dict[str, JsonValue]) -> str:
    """Render one diff, in the domain's own labels and no others."""
    payload = document.get("payload")
    if not isinstance(payload, dict):
        raise ReceiptDiffError("diff document has no payload")
    counts = payload.get("counts")
    if not isinstance(counts, dict):
        raise ReceiptDiffError("diff document has no counts")
    transition = payload.get("overall_status_transition")
    transition = transition if isinstance(transition, dict) else {}
    lines = [
        "# Receipt diff",
        "",
        f"Contract `{payload['contract_id']}`.",
        "",
        "Nothing was re-evaluated. Every status below is copied from the receipt",
        "that recorded it, and a listed cause is an attribution, not a proof.",
        "",
        f"Overall status: `{transition.get('prior')}` -> `{transition.get('current')}`"
        f" ({'changed' if transition.get('changed') else 'unchanged'}).",
        "",
        f"Manifest changed: {'yes' if payload.get('manifest_changed') else 'no'}. "
        f"Source changed: {'yes' if payload.get('source_changed') else 'no'}.",
        "",
        "| Change | Count |",
        "|---|---:|",
    ]
    for key in sorted(counts):
        lines.append(f"| {key.replace('_', ' ')} | {counts[key]} |")
    changed = payload.get("changed")
    if isinstance(changed, list) and changed:
        lines.extend(
            ["", "| Obligation | Change | Prior | Current | Causes |", "|---|---|---|---|---|"]
        )
        for raw in changed:
            if not isinstance(raw, dict):
                continue
            causes = raw.get("causes")
            rendered = (
                ", ".join(str(cause) for cause in causes)
                if isinstance(causes, list) and causes
                else "—"
            )
            lines.append(
                f"| `{raw['id']}` | {raw['change']} | {raw.get('prior_status') or '—'} "
                f"| {raw.get('current_status') or '—'} | {rendered} |"
            )
    else:
        lines.extend(["", "No obligation changed between these two receipts."])
    return "\n".join(lines) + "\n"
