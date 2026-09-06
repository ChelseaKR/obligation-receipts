"""Collection progress against an approved plan, with no verdict in it.

`evidence-plan` produces the checklist and `evaluate` produces the verdict. In
between sits a question neither answers: *what is still missing?* A delivery
lead needs that in a status meeting, and today the only way to get it is to run
`evaluate`, which produces a pass/fail that then travels onward as a result.

This project's core distinction is that **missing evidence is not failure**. A
progress view that answers "what has been collected" without answering "did it
pass" is what keeps those two separate, so this module reports:

* `present` -- a regular file exists at the declared path, within the caps;
* `absent` -- nothing is there;
* `unreadable` -- something is there that cannot be used, with the reason
  (over the cap, not a regular file, not strict JSON).

For an attestation it additionally reports whether the document parses and
whether its **binding fields** match the manifest -- contract, manifest digest,
obligation and evidence ids, and schema version. It never reads, reports, or
branches on the `status` value inside the attestation. That value is the
verdict, and reporting it here would smuggle an evaluation into a progress
report, which is the one thing this command exists not to do.

For the same reason nothing here reports an assertion outcome: a `json_assertion`
artifact is checked for readability and nothing else. Whether
`/summary/critical_violations` is 0 is `evaluate`'s question.

The exit code is 0 whenever the report was computed, because a report is not a
verdict. Only an input error -- an unusable plan, manifest, or root -- exits 2.
"""

from __future__ import annotations

from json import JSONDecodeError
from pathlib import Path

from obligation_receipts.canonical import (
    StrictJsonError,
    canonical_json_bytes,
    loads_json_strict,
    sha256_bytes,
)
from obligation_receipts.models import (
    Classification,
    EvidenceKind,
    JsonValue,
    Manifest,
    Obligation,
)
from obligation_receipts.paths import (
    BoundedPathError,
    read_bounded_file,
    resolve_evidence_root,
)
from obligation_receipts.plan import EvidencePlanError, verify_evidence_plan

#: The evaluator's artifact cap, so "present" here means "present and usable
#: by `evaluate`" rather than "a file of some size exists".
MAX_ARTIFACT_BYTES = 2 * 1024 * 1024

PRESENT = "present"
ABSENT = "absent"
UNREADABLE = "unreadable"

_LIMITATIONS: dict[str, JsonValue] = {
    "attestation_status_read": False,
    "completeness_assessed": False,
    "evaluation_performed": False,
    "evidence_sufficiency_assessed": False,
    "legal_interpretation_performed": False,
    "official_decision_made": False,
}


class PlanStatusError(ValueError):
    """Raised when the plan, manifest, or evidence root cannot be used."""


def _attestation_fields(kind: EvidenceKind) -> tuple[str, ...]:
    common = (
        "schema_version",
        "contract_id",
        "contract_version",
        "manifest_sha256",
        "obligation_id",
        "evidence_id",
        "status",
    )
    if kind is EvidenceKind.REVIEW_ATTESTATION:
        return (*common, "reviewer", "reviewed_at", "method")
    return (*common, "issuer", "observed_at", "source_uri")


def _binding_report(
    document: JsonValue,
    manifest: Manifest,
    obligation: Obligation,
    evidence_id: str,
    kind: EvidenceKind,
) -> dict[str, JsonValue]:
    """Which binding fields match the manifest. Never reads `status`.

    `status` is in `required_fields` because an attestation without one is
    incomplete, but only its PRESENCE is reported. Its value is the verdict and
    is deliberately never read: see the module docstring.
    """
    if not isinstance(document, dict):
        unparsed: dict[str, JsonValue] = {
            "parses": True,
            "is_object": False,
            "required_fields_present": False,
            "missing_fields": [],
            "bound_to_manifest": False,
            "mismatched_fields": [],
        }
        return unparsed
    required = _attestation_fields(kind)
    missing = sorted(field for field in required if field not in document)
    expected: dict[str, JsonValue] = {
        "contract_id": manifest.contract.contract_id,
        "contract_version": manifest.contract.version,
        "manifest_sha256": manifest.manifest_sha256,
        "obligation_id": obligation.obligation_id,
        "evidence_id": evidence_id,
        "schema_version": "obligation-receipts/attestation/v0.1",
    }
    mismatched = sorted(key for key, value in expected.items() if document.get(key) != value)
    report: dict[str, JsonValue] = {
        "parses": True,
        "is_object": True,
        "required_fields_present": not missing,
        "missing_fields": list(missing),
        "bound_to_manifest": not mismatched and not missing,
        "mismatched_fields": list(mismatched),
    }
    return report


def _requirement_status(
    manifest: Manifest,
    obligation: Obligation,
    evidence_id: str,
    kind: EvidenceKind,
    path: str,
    evidence_root: Path,
    include_local_details: bool,
) -> dict[str, JsonValue]:
    """One requirement's collection state. No assertion outcome, ever."""
    row: dict[str, JsonValue] = {
        "id": evidence_id,
        "kind": kind.value,
        "path": path if include_local_details else None,
        "attestation_binding": None,
        "reason": None,
        "sha256": None,
        "state": ABSENT,
    }
    try:
        _resolved, data = read_bounded_file(evidence_root, path, max_bytes=MAX_ARTIFACT_BYTES)
    except FileNotFoundError:
        return row
    except BoundedPathError as exc:
        # A path that escapes the root, a special file, or an oversized
        # artifact. Present-but-unusable is its own state: counting it absent
        # would tell a delivery lead to go and collect a file that is already
        # there, and counting it present would claim a usable artifact.
        row["state"] = UNREADABLE
        row["reason"] = str(exc)
        return row
    except OSError:
        row["state"] = UNREADABLE
        row["reason"] = "artifact could not be read"
        return row

    row["sha256"] = sha256_bytes(data)
    try:
        document = loads_json_strict(data)
    except (JSONDecodeError, RecursionError, StrictJsonError, ValueError) as exc:
        row["state"] = UNREADABLE
        row["reason"] = f"artifact is not strict JSON: {exc}"
        return row

    row["state"] = PRESENT
    if kind is not EvidenceKind.JSON_ASSERTION:
        row["attestation_binding"] = _binding_report(
            document, manifest, obligation, evidence_id, kind
        )
    return row


def build_plan_status(
    plan: dict[str, JsonValue],
    manifest: Manifest,
    evidence_root: Path,
    *,
    include_local_details: bool = False,
) -> dict[str, JsonValue]:
    """Report collection progress for one approved plan. Evaluates nothing.

    The plan is first regenerated from the manifest and required to match
    exactly (`verify_evidence_plan`'s replay check). A progress report against a
    plan that no longer describes its manifest would count the wrong
    requirements and report confidently about a checklist nobody approved.
    """
    try:
        verify_evidence_plan(plan, manifest)
    except EvidencePlanError as exc:
        raise PlanStatusError(f"plan does not regenerate from the manifest: {exc}") from exc
    root = resolve_evidence_root(evidence_root)

    obligations: list[JsonValue] = []
    totals = {PRESENT: 0, ABSENT: 0, UNREADABLE: 0}
    unbound_attestations = 0
    for obligation in manifest.obligations:
        if obligation.classification is Classification.UNVERIFIABLE:
            obligations.append(
                {
                    "classification": obligation.classification.value,
                    "counts": {PRESENT: 0, ABSENT: 0, UNREADABLE: 0},
                    "id": obligation.obligation_id,
                    "requirements": [],
                }
            )
            continue
        rows: list[JsonValue] = []
        counts = {PRESENT: 0, ABSENT: 0, UNREADABLE: 0}
        for evidence in obligation.evidence:
            row = _requirement_status(
                manifest,
                obligation,
                evidence.evidence_id,
                evidence.kind,
                evidence.path,
                root,
                include_local_details,
            )
            state = row["state"]
            if not isinstance(state, str) or state not in counts:
                # Unreachable through `_requirement_status`, which only ever
                # writes one of the three constants. Raised rather than
                # asserted so the check survives `python -O`, and so a future
                # fourth state cannot be silently dropped from the counts.
                raise PlanStatusError(f"unknown collection state {state!r}")
            counts[state] += 1
            totals[state] += 1
            binding = row["attestation_binding"]
            if isinstance(binding, dict) and binding.get("bound_to_manifest") is not True:
                unbound_attestations += 1
            rows.append(row)
        obligations.append(
            {
                "classification": obligation.classification.value,
                "counts": dict(counts),
                "id": obligation.obligation_id,
                "requirements": rows,
            }
        )

    payload: dict[str, JsonValue] = {
        "contract_id": manifest.contract.contract_id,
        "contract_version": manifest.contract.version,
        "counts": {
            "absent": totals[ABSENT],
            "declared_total": sum(totals.values()),
            "present": totals[PRESENT],
            "unbound_attestations": unbound_attestations,
            "unreadable": totals[UNREADABLE],
        },
        "decision_scope": "evidence_collection_progress_only",
        "detail_mode": "local_sensitive" if include_local_details else "portable_redacted",
        "limitations": dict(_LIMITATIONS),
        "manifest_sha256": manifest.manifest_sha256,
        "obligations": obligations,
        "schema_version": "obligation-receipts/plan-status/v0.1",
        "source_sha256": manifest.contract.source_sha256,
    }
    return {
        "payload": payload,
        "payload_sha256": sha256_bytes(canonical_json_bytes(payload)),
        "schema_version": "obligation-receipts/plan-status-document/v0.1",
    }


def render_markdown(document: dict[str, JsonValue]) -> str:
    """Render progress for a status meeting, saying plainly what it is not."""
    payload = document.get("payload")
    if not isinstance(payload, dict):
        raise PlanStatusError("plan status document has no payload")
    counts = payload.get("counts")
    if not isinstance(counts, dict):
        raise PlanStatusError("plan status document has no counts")
    lines = [
        "# Evidence collection progress",
        "",
        f"Contract `{payload['contract_id']}` version `{payload['contract_version']}`.",
        "",
        "Nothing was evaluated. No requirement below passed or failed; `present`",
        "means a usable artifact is at the declared path, and missing evidence is",
        "not failure. An attestation's own status value was never read.",
        "",
        "| Count | Value |",
        "|---|---:|",
    ]
    for key in sorted(counts):
        lines.append(f"| {key.replace('_', ' ')} | {counts[key]} |")
    obligations = payload.get("obligations")
    if isinstance(obligations, list):
        for entry in obligations:
            if isinstance(entry, dict):
                lines.extend(_obligation_lines(entry))
    return "\n".join(lines) + "\n"


def _obligation_lines(entry: dict[str, JsonValue]) -> list[str]:
    """One obligation's Markdown block."""
    lines = ["", f"## `{entry['id']}` ({entry['classification']})", ""]
    requirements = entry.get("requirements")
    if not isinstance(requirements, list) or not requirements:
        lines.append("No evaluable evidence is declared for this obligation.")
        return lines
    lines.extend(["| Requirement | State | Bound | Note |", "|---|---|---|---|"])
    for raw in requirements:
        if not isinstance(raw, dict):
            continue
        binding = raw.get("attestation_binding")
        bound = "—"
        if isinstance(binding, dict):
            bound = "yes" if binding.get("bound_to_manifest") else "no"
        lines.append(f"| `{raw['id']}` | {raw['state']} | {bound} | {raw.get('reason') or '—'} |")
    return lines
