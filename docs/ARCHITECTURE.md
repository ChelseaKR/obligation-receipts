# Architecture

## System boundary

Obligation Receipts begins after authoritative language has been interpreted and
approved by accountable humans. It ends before a contracting authority makes an
official acceptance, payment, remedy, or legal decision.

```text
                   outside this product
 approved source ───────────────────────────────────────────┐
        │                                                   │
        ▼                                                   │
human-approved manifest                                   │
        │                                                   │
        ├── source SHA-256 gate                             │
        ├── classification/type gate                        │
        └── normalized manifest SHA-256                     │
        │                                                   │
        ├── deterministic evidence plan                     │
        │     └── no evidence opened or evaluated           │
        ├── single declared evidence check                  │
        │     └── no sibling or aggregate evaluation        │
        │                                                   │
        ▼                                                   │
 bounded evidence root                                     │
        ├── JSON assertions                                 │
        ├── manual review attestations                      │
        ├── external attestations                           │
        └── explicit unverifiable state                     │
        │                                                   │
        ▼                                                   │
 deterministic evaluator                                   │
        │                                                   │
        ▼                                                   │
 receipt payload ── SHA-256 ── untrusted envelope           │
        │                                                   │
        ▼                                                   ▼
 offline verification / replay              official acceptance decision
```

## Components

- `manifest.py` parses a closed TOML shape, validates type/classification
  compatibility, re-hashes the approved source, normalizes the manifest, and
  issues its digest.
- `pointer.py` is the single RFC 6901 seam. Manifest loading, plan
  validation, and evaluation share one definition of a well-formed pointer,
  so a malformed one is refused as an authoring defect at load time instead
  of reaching the evaluator and becoming an observed `fail`. Canonical
  array-index form is checked at resolution, not at load: RFC 6901 makes a
  non-canonical index an error only against an array, and the same token can
  legally name an object member.
- `paths.py` is the single bounded-path seam. Source/evidence paths must be
  portable lexical relative paths beneath a caller-declared root; regular-file
  descriptors are opened nonblocking and final components are not followed.
- `evaluator.py` parses and hashes one descriptor-stable bounded byte snapshot,
  evaluates a small closed operator set, and validates content-bound
  attestations bound through contract, manifest, obligation, and evidence ID.
- `models.py` defines the result algebra and overall-status policy.
- `receipt.py` creates the deterministic payload, keeps time in a separate
  envelope, writes through a collision-resistant atomic replacement, and
  verifies the closed payload schema, result algebra, counts, and integrity.
- `cli.py` exposes validate, evaluate, and verify/replay.
- `plan.py` projects declared collection instructions into a closed,
  manifest-bound checklist. Its default profile redacts local paths, locators,
  and free-text reasons; it never opens evidence.
- `single_check.py` locates one globally unique declared evidence ID, delegates
  to the same assertion/attestation semantics as full evaluation, and emits an
  unsigned, non-aggregate diagnostic with explicit unchecked-evidence counts.
- `research.py` validates two frozen discovery CSVs and computes predeclared
  agreement metrics; it never creates or activates obligation mappings.

## Deliberate technology decisions

| Decision | Choice | Reason |
|---|---|---|
| Runtime | Python 3.12 standard library | Auditable, portable, zero runtime dependencies |
| Manifest | Strict TOML | Human-reviewable and available in stdlib |
| Evidence | Bounded local JSON | Integrates without arbitrary execution |
| Hash | SHA-256 | Interoperable content identity, not a signature |
| Receipt | Canonical JSON payload + separate envelope | Determinism without false time/signature claims |
| Storage | Caller-owned filesystem | Avoid confidential evidence centralization |
| Parser bounds | 2 MiB manifest/artifact/document, 16 MiB source, 64 levels, 100,000 JSON nodes | Bound offline resource use and reject ambiguous JSON |

## Trust claims

The receipt records:

- a canonical payload and its self-contained checksum;
- the exact normalized manifest digest;
- the source digest declared and rechecked during evaluation;
- the digest and bounded result of each evidence artifact; and
- replay equivalence when replay succeeds.

It does not prove:

- authorship, authenticity, or immutability of an unsigned receipt;
- source authority or legal interpretation;
- evidence truth, completeness, or independence;
- reviewer identity beyond the supplied attestation;
- trusted creation time;
- contractual acceptance; or
- compliance with a law, regulation, or standard.

An attacker who can rewrite an M0 receipt can also recompute its checksum.
Authenticity therefore requires an independently trusted payload digest or a
future signature; replay provides reproducibility, not identity.

## Result algebra

Evidence combines fail closed:

`fail > missing > review_required > pass`.

An unverifiable obligation bypasses evidence and remains `unverifiable`.
Overall results distinguish observed failure from unresolved evidence:

1. failed `must` → `rejected`;
2. unresolved `must` → `incomplete`;
3. all `must` pass, nonpassing `should` → `accepted_with_findings`;
4. every obligation passes → `accepted`.

These names are domain labels, not official actions.

## Future seams

Adapters may convert existing tools' outputs into the closed internal evidence
shape. They may not add general command execution. Future cryptographic signing
must sign the existing payload hash and must not relabel old unsigned receipts.
