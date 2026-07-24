# Product requirements: M0 obligation-to-receipt vertical slice

**Status:** implemented technical hypothesis
**Date:** 2026-07-22
**Owner:** Chelsea Kelly-Reif

## Problem statement

Public and regulated software buyers routinely place accessibility, security,
performance, interoperability, and delivery promises in solicitations and
contracts. The promise, acceptance method, produced evidence, human review, and
final disposition often live in separate artifacts, making it difficult to
answer a basic question: “What evidence showed that this exact promise was met?”

The first product risk is not technical. It is whether enough consequential
clauses can become objective, maintainable evidence contracts without turning
the tool into legal interpretation or bespoke consulting.

## Target users

1. Government product, QA, accessibility, security, and contracting-officer
   representatives responsible for acceptance evidence.
2. Delivery primes and software vendors who must assemble repeatable acceptance
   data packages.
3. Independent verification and validation teams that need traceability without
   becoming the system of record for contract administration.

## Goals

1. An expert can represent ten approved obligations in under 60 minutes after
   learning the manifest.
2. Every evaluated obligation binds to an exact source digest, manifest digest,
   and evidence digest.
3. The evaluator never reports `pass` when evidence is absent, invalid, outside
   the evidence root, or not bound to the active manifest.
4. A third party can verify a receipt offline and replay it with the original
   inputs.
5. Discovery finds at least three independent organizations with a repeated,
   funded acceptance-evidence problem before M1 product expansion.

## Non-goals

- **Contract drafting or legal interpretation.** The authoritative organization
  owns what a clause means.
- **Automated clause extraction.** Extraction would test model performance
  before testing product demand.
- **Contract lifecycle management.** Signatures, amendments, invoices, and
  payments already have mature systems.
- **General test automation.** Existing tools create test results; this project
  binds approved obligations to those results.
- **Compliance certification.** A receipt proves a bounded evaluation, not legal
  compliance or official acceptance.
- **Hosted evidence warehouse.** M0 keeps confidential evidence under operator
  control.

## User stories

### Acceptance lead

- As an acceptance lead, I want each obligation classified by verification
  method so that ambiguous promises are visible before delivery.
- As an acceptance lead, I want missing evidence distinguished from observed
  failure so that I do not make an unsupported contractual conclusion.
- As an acceptance lead, I want `must` and `should` obligations to aggregate
  predictably so that the release disposition follows approved policy.

### Technical evaluator

- As a technical evaluator, I want to consume existing JSON test summaries so
  that I do not replace the team's current tools.
- As a technical evaluator, I want path traversal and command execution to be
  impossible so that a supplier-authored manifest cannot become code execution.

### Reviewer or auditor

- As a reviewer, I want attestations bound to the exact contract and manifest so
  that a review from another version cannot be silently reused.
- As an auditor, I want to verify the receipt without the evidence and replay it
  when evidence is available so that integrity and reproducibility remain
  separate claims.

## Requirements

### P0 — M0

1. **Strict source-bound manifest.**
   - Given an approved source file and declared SHA-256,
   - when the file changes,
   - then validation fails before any evidence is evaluated.
2. **Four evidence classifications.**
   - Automated, manual review, external evidence, and unverifiable are distinct.
   - Evidence kinds cannot be substituted across classifications.
3. **Bounded local evaluation.**
   - Absolute paths, traversal, missing files, non-files, malformed JSON, and
     artifacts over 2 MiB fail closed.
   - Duplicate keys, non-finite numbers, invalid UTF-8, excessive nesting, and
     excessive JSON node counts fail closed.
   - The exact evidence bytes parsed are the bytes hashed into the result.
   - No command, plugin, expression, or network primitive exists.
4. **Explicit result algebra.**
   - A failed `must` yields `rejected`.
   - An unresolved `must` yields `incomplete`.
   - Nonpassing `should` obligations yield `accepted_with_findings` only after
     every `must` passes.
5. **Receipt and replay.**
   - Payload bytes are deterministic for the same normalized inputs.
   - Timestamp and signature status are outside the payload.
   - Accidental or incomplete payload modification is detectable; malicious
     rewrite is explicitly outside an unsigned receipt's claims.
   - Replay requires an exact payload match.
   - Offline verification rejects internally inconsistent payload fields,
     counts, evidence/status combinations, and overall-status algebra even when
     a checksum was recomputed.
6. **Pre-evaluation evidence plan.**
   - A source-bound manifest can produce a deterministic collection checklist
     without opening evidence.
   - Portable output redacts local locators, paths, and free-text reasons;
     local-sensitive detail requires explicit opt-in.
   - Exact assertion requirements and attestation bindings remain actionable.
   - Fixed limitations prevent the plan from claiming approval, completeness,
     evidence sufficiency, interpretation, evaluation, or an official decision.
   - Manifest-backed verification requires exact regeneration; checksum-only
     verification is labeled as self-consistency.

### P1 — only after discovery

- A versioned JSON Schema for interchange.
- Staleness and validity windows for external evidence.
- Multiple accepted evidence formats through reviewed, non-executable adapters.
- Human-readable static trace report with WCAG 2.2 AA gates.
- Amendment comparison: added, removed, tightened, loosened, and reclassified
  obligations.
- A mapping-review queue for proposed clauses, still requiring human activation.

### P2 — future hypotheses

- OCDS extension or export for implementation milestones.
- Pact, SARIF, OSCAL, ACR, SBOM, and SLSA adapters.
- Cryptographic signer roles for manifest approval and evidence review.
- Hosted multi-party evidence exchange.
- A model-assisted draft mapper, separately evaluated and prohibited from
  activation authority.

## Success metrics

### Product evidence

| Metric | Proceed threshold | Kill/reframe threshold |
|---|---:|---:|
| Clean-source discovery conversations | 8–12 | fewer than 8 |
| Similar pain described independently | ≥3 organizations | fewer than 3 |
| Clauses objectively classifiable in public samples | ≥40% | <25% |
| Independent expert classification agreement | Cohen's κ ≥0.70 | κ <0.50 |
| Buyer near budget confirms purchasability | ≥1 | 0 |
| Serious pilot next step | ≥1 | 0 after 12 interviews |

### Technical evidence

| Metric | M0 target |
|---|---:|
| Branch coverage | ≥90% |
| Runtime dependencies | 0 |
| Unbound evidence producing pass | 0 |
| Replay mismatch accepted | 0 |
| Source digest mismatch accepted | 0 |
| Artifact path escapes accepted | 0 |

## Open questions

- **Procurement:** Can a receipt be referenced in a QASP or acceptance plan
  without becoming part of the official contract file?
- **Legal:** Which labels avoid implying a contractual determination while
  remaining useful to acceptance staff?
- **Buyer:** Is the first paid outcome obligation mapping, repeatable evidence
  collection, independent replay, or all three?
- **Engineering:** Which existing result formats provide the highest-value first
  adapters?
- **Governance:** Who may approve a manifest, review evidence, and accept a
  residual finding in a real engagement?

None blocks the M0 technical hypothesis. All block a production claim.

## Phasing

- **M0:** offline typed vertical slice and synthetic example.
- **Discovery:** 8–12 interviews and three public-document mapping exercises.
- **M1:** one narrow design-partner pack only if proceed thresholds pass.
- **M2:** interoperable adapters and static reviewer experience only after a
  real acceptance workflow has been observed.
