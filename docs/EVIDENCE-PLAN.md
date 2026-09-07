# Evidence-plan format

An evidence plan is a deterministic projection of a source-bound manifest for
people or systems preparing evidence before evaluation. It does not read,
inspect, hash, validate, or evaluate evidence.

## CLI

Portable-redacted output is the default:

```sh
obligation-receipts evidence-plan obligations.toml --out evidence-plan.json
obligation-receipts verify-evidence-plan evidence-plan.json
obligation-receipts verify-evidence-plan evidence-plan.json \
  --manifest obligations.toml
```

A locally controlled workflow can opt into declared paths, source locators, and
free-text reasons:

```sh
obligation-receipts evidence-plan obligations.toml \
  --include-local-details \
  --out local-sensitive-plan.json
```

The output path is neither embedded in the plan nor repeated in CLI stdout.

## Closed document

The wrapper is `obligation-receipts/evidence-plan-document/v0.1` and contains
only:

- `schema_version`;
- `payload`; and
- `payload_sha256`, the SHA-256 of canonical payload bytes.

The payload `obligation-receipts/evidence-plan/v0.1` binds:

- contract ID and version;
- exact normalized-manifest SHA-256;
- exact source SHA-256;
- detail profile;
- an obligation count; and
- ordered collection requirements.

Each evaluable obligation carries its declared ID, classification, criticality,
`all_required` combination rule, and evidence requirements. Unverifiable
obligations use `not_applicable`, avoiding the false implication that an empty
requirement set was satisfied. Automated
requirements repeat the exact declared JSON pointer, operator, and expected
value. Attestation requirements give the allowed statuses, exact required
fields, and fixed contract/version/manifest/obligation/evidence-item binding
values.
Unverifiable obligations have no evidence requirements.

## Privacy profiles

`portable_redacted` replaces:

- source locators with `null`;
- source spans with `null`, when the manifest declared one;
- evidence filesystem paths with `null`; and
- free-text unverifiable reasons with
  `no_evaluable_evidence_declared`.

A `source_span` is a byte offset, length, and digest into the approved contract
source (ADR 0002). It is a locator into the document, so it is redacted exactly
as `clause_ref` is: the offset says where in the contract a clause sits, and the
digest is a confirmable guess at the bytes there. The member is present only
when the manifest declared one, so a plan built from a manifest with no spans is
byte-identical to the plans built before spans existed.

It deliberately retains assertion thresholds and attestation bindings because a
collector otherwise cannot prepare the right artifact. Those values may still
be sensitive. “Portable” means reduced location leakage, not approved for public
release.

`local_sensitive` includes the exact manifest-declared source locators, source
spans, relative evidence paths, and reasons. Local paths remain lexical relative paths beneath a
future evidence root; absolute, traversal, Windows-drive/UNC, backslash,
colon/URI, dot-segment, and empty-segment paths fail plan generation.

Neither profile contains obligation prose, accountable-owner fields, source
bytes, evidence bytes, evidence hashes, reviewer-entered content, a working
directory, or the output path. A span's digest is not source bytes, but it does
let a holder of a candidate document confirm a guess at one clause of it; that
is why it is redacted from the portable profile rather than kept.

## Fixed limitations

Every payload sets `evidence_observed` to `false`, scopes itself to
`evidence_collection_checklist_only`, and records these fixed false claims:

- approval authenticated;
- completeness proven;
- evidence sufficiency assessed;
- legal interpretation performed; and
- official decision made.

Every non-unverifiable obligation says all declared requirements are required.
The plan cannot report pass, fail, missing, review, or an overall disposition.

## Verification semantics

Checksum-only verification means the closed payload is internally
self-consistent and unchanged. Because M0 has no signature, an attacker can
fabricate a new self-consistent plan.

Manifest-backed verification reloads the source-bound manifest and requires
byte-equivalent regeneration under the plan's own privacy profile. This detects
a stale plan or one derived from another manifest. It still cannot authenticate
who approved the manifest, establish that every contractual clause was mapped,
or decide whether the requested evidence is sufficient.
