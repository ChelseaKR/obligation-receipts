# Obligation Receipts

Turn approved software-acceptance promises into testable obligations with
verifiable evidence receipts.

**Status:** technical alpha (`M0`) · offline CLI and synthetic demonstration ·
Apache-2.0

Obligation Receipts does not draft contracts or decide what a contract means.
An accountable human first converts approved source language into an explicit
manifest. The tool then evaluates that manifest against bounded local evidence
and reports each obligation as `pass`, `fail`, `missing`, `review_required`, or
`unverifiable`. Missing evidence never becomes a failure or a pass.

The receipt identifies what evidence was evaluated under which manifest and
source digest. Its self-contained checksum detects accidental corruption, but
M0 is unsigned and cannot prove authorship or prevent a malicious party from
changing both payload and checksum. It also does **not** prove that the manifest
is legally correct, that the evidence is truthful, or that a contracting
authority accepted a deliverable.

## Why this exists

Public software contracts commonly require acceptance testing, objective
evidence, accessibility validation, security attestations, and performance
reports. In practice, the source promise, test, result, reviewer, and acceptance
decision often live in different documents and tools.

The adjacent pieces already exist:

- [FAR 9.302](https://www.acquisition.gov/far/9.302) establishes first-article
  testing and approval as a way to verify conformance with contract requirements.
- [Section508.gov](https://www.section508.gov/buy/integrate-section-508-in-qasps/)
  shows how accessibility requirements become monitored acceptance criteria.
- [Open Contracting Data Standard](https://standard.open-contracting.org/latest/en/guidance/map/milestones/)
  represents implementation milestones and their status.
- [Pact](https://docs.pact.io/implementation_guides/python/docs/consumer)
  verifies machine-to-machine interaction contracts.
- [NASA software-assurance guidance](https://swehb.nasa.gov/spaces/SWEHBVD/pages/102695528/SWE-193%2B-%2BAcceptance%2BTesting%2Bfor%2BAffected%2BSystem%2Band%2BSoftware%2BBehavior)
  calls for traceable objective acceptance evidence.

The proposed contribution is the open, offline chain between them:

```text
approved source
  → human-authored obligation manifest
  → bounded automated evidence + named attestations
  → fail-closed evaluation
  → deterministic receipt payload
  → independent replay
```

This is a hypothesis, not a novelty claim. The discovery gates that could kill
the project are explicit in [the PRD](docs/PRD.md).

## Five-minute synthetic demonstration

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```sh
make install
make verify
make package-check
make benchmark
make demo
```

`make benchmark` reports local median and p95 latency for the synthetic
four-obligation validation-and-evaluation path. It deliberately has no pass/fail
latency threshold until discovery supplies a representative workload and user
expectation.

The example binds four synthetic clauses to:

1. an automated JSON assertion;
2. a named manual-review attestation;
3. an external attestation; and
4. a deliberately untestable phrase, “the service should be intuitive.”

Because the untestable phrase is only a `should`, the example evaluates to
`accepted_with_findings`. Changing its criticality to `must` makes the result
`incomplete`. Changing the automated violation count makes it `rejected`.

The terms are technical evaluation states only. They are not contractual or
legal conclusions.

## CLI

```sh
obligation-receipts validate obligations.toml

obligation-receipts evidence-plan obligations.toml \
  --out evidence-plan.json

obligation-receipts verify-evidence-plan evidence-plan.json \
  --manifest obligations.toml

obligation-receipts check-evidence obligations.toml a1-axe-summary \
  --evidence-root evidence

obligation-receipts evaluate obligations.toml \
  --evidence-root evidence \
  --out receipt.json

obligation-receipts verify receipt.json \
  --manifest obligations.toml \
  --evidence-root evidence

obligation-receipts research-metrics \
  frozen-rater-a.csv frozen-rater-b.csv
```

`evidence-plan` creates a deterministic collection checklist without opening the
evidence root. The default `portable_redacted` profile omits manifest-declared
source locators, filesystem paths, and free-text unverifiable reasons. Exact
assertion pointer/operator/expected values and attestation bindings remain
because they are the collection instructions; therefore even the redacted
profile must be reviewed before public sharing.

Use `--include-local-details` only for a locally controlled handoff that needs
the declared locators, paths, and reasons. The artifact labels that profile
`local_sensitive`.

`verify-evidence-plan` without a manifest reports only
`checksum_self_consistent`. Supplying the exact manifest regenerates the plan
under its recorded detail profile and reports `replay_verified`. Neither status
authenticates approval or proves evidence sufficiency. See the
[evidence-plan format](docs/EVIDENCE-PLAN.md).

Generation stdout reports only manifest/count/digest/status metadata. It does
not repeat the operator-supplied output path.

`check-evidence` evaluates exactly one declared evidence item without reading
its siblings. Its canonical result omits artifact paths, assertion details,
evidence content, evaluator detail text, and all aggregate dispositions. It is
unsigned and fixes `obligation_evaluation_complete` to `false`, even when the
selected evidence passes.

See the [single-evidence check format](docs/SINGLE-EVIDENCE-CHECK.md).

## Exit codes

Every command draws from one band, so an automated acceptance pipeline can tell
an evaluated negative outcome apart from a tool or input error:

| Code | Meaning |
|---:|---|
| 0 | every `must` obligation passed |
| 1 | evidence was read and did not pass; a result document exists |
| 2 | manifest, lookup, path, argument, or document input error; **no result document** |
| 3 | required evidence was absent or unusable, so nothing was observed |
| 4 | an attestation is unbound, malformed, or awaiting review |

Code 2 is reserved: it always means no result document was produced, and no
evaluated state maps onto it. A `rejected` evaluation and an unreadable manifest
are different facts about a contract, and a caller must never have to guess
which one it received.

| Command | 0 | 1 | 3 | 4 |
|---|---|---|---|---|
| `evaluate` | `accepted`, `accepted_with_findings` | `rejected` | `incomplete` | — |
| `verify` | verified | payload digest or replay mismatch | — | — |
| `check-evidence` | `pass` | observed `fail` | `missing` or malformed | `review_required` |
| `validate`, `evidence-plan`, `verify-evidence-plan`, `research-metrics` | success | — | — | — |

`accepted_with_findings` exits 0 because every `must` obligation passed and only
a `should` did not. `incomplete` exits 3 rather than 4 because it aggregates
missing evidence, awaiting review, and unverifiable into one state and cannot
honestly choose between them; `check-evidence` reports the per-item code.

A `verify` failure is code 1, not 2: a receipt that does not reproduce is an
integrity finding about that receipt, not a failure to read it.

`verify receipt.json` checks the receipt's non-circular payload checksum.
Supplying the manifest and evidence root also performs a fresh replay and
requires byte-equivalent payload content.

`research-metrics` is a discovery-only utility for the predeclared two-rater
protocol. It validates bounded frozen CSVs and reports file digests, a confusion
matrix, raw agreement, Cohen's kappa (including an explicit undefined value),
classifiable rates, and the unchanged PRD gates. It does not classify clauses or
interpret contracts. Byte-identical rater files are rejected because they
cannot demonstrate the protocol's required independence.

## What M0 supports

| Classification | Evidence | Result |
|---|---|---|
| `automated` | bounded local JSON assertion | pass, fail, or missing |
| `manual_review` | named attestation bound to contract, manifest, obligation, and evidence ID | pass, fail, or review required |
| `external_evidence` | issuer attestation bound to contract, manifest, obligation, and evidence ID | pass, fail, or review required |
| `unverifiable` | no evidence; a reason is mandatory | unverifiable |

The overall result is:

- `rejected` when any `must` obligation fails;
- `incomplete` when a `must` obligation is missing, awaiting review, or
  unverifiable;
- `accepted_with_findings` when every `must` passes but a `should` does not; or
- `accepted` when every obligation passes.

## Hard boundaries

- No contract drafting, clause extraction, or legal interpretation.
- No LLM or network call in validation, evaluation, or verification.
- No arbitrary command, script, expression language, or plugin execution.
- No fetching evidence from a URL.
- No claim that a technically passing result requires contractual acceptance.
- No signature claim: M0 receipts explicitly say `not_signed`.
- No trusted timestamp claim: envelope time is caller-declared and untrusted.
- No raw evidence content in receipts; only bounded results and artifact hashes.
- Duplicate JSON keys, non-finite numbers, invalid UTF-8, and JSON deeper than 64
  levels or larger than 100,000 nodes fail closed.
- A manifest-authored JSON pointer that is not well formed under RFC 6901 is an
  input error at load time, not an observed failure. All three commands share
  one definition of well formed, so they cannot disagree about a manifest.
- Evidence is parsed and hashed from the same bounded byte snapshot.
- Contract-source hashing is capped at 16 MiB; manifests, JSON evidence, plans,
  and receipts are capped at 2 MiB.
- Declared source and evidence paths must use portable relative syntax; Windows
  drives/UNC, backslashes, colon/URI forms, traversal, dot, and empty segments
  fail closed.
- Evidence plans read no evidence and make no evaluation, approval,
  completeness, sufficiency, legal-interpretation, or official-decision claim.
- A single-evidence check never implies that its obligation or manifest is
  complete, sufficient, accepted, or compliant.

## Architecture

The manifest is strict TOML. Its normalized content and the exact approved source
digest form `manifest_sha256`. Evidence is read only from a declared, minimally
scoped local root, with nonportable or escaping paths rejected. Final-component
no-follow and descriptor-stable snapshots reduce local races but do not make
replaceable parent directories a hostile multi-user sandbox. The evaluator
emits a deterministic payload; time and future signatures live in a separate
envelope and cannot alter that payload.

See [Architecture](docs/ARCHITECTURE.md),
[Threat Model](docs/THREAT-MODEL.md), and
[ADR 0001](docs/decisions/0001-human-approved-manifest.md).

## Standards Conformance

One row per canonical standard, in the labels and states the portfolio
conformance checker reads. The second column is the state, not a summary: an
under-reported row would fail this repo's own argument that a record says
exactly what was checked and nothing more.

| Standard | State |
|---|---|
| Responsible-Tech Framework | Applies — see the [current audit](docs/RESPONSIBLE-TECH-AUDITS.md) |
| Code Quality | Applies — Python 3.12, Ruff, strict mypy, and pytest, all merge-blocking through `make verify` |
| Security & Supply-Chain | Applies — bounded local evidence, zero runtime dependencies, digest-pinned CI actions, and merge-blocking SAST, secret, and dependency scans |
| CI/CD | Applies — hosted CI on `push` and `pull_request`, carried by `ci.yml` since the first commit; the `protect-main` ruleset, active since 2026-08-07, requires a pull request and all six checks (`verify`, `package`, `dependency-scan`, `secret-scan`, `sast`, `zizmor`), having required only `verify` until the change recorded in the CHANGELOG; gap tracked in #16 for the CodeQL `language: actions` element, now unwaived — WVR-008 was retired when this repository became public, because code scanning is available here and the analysis is simply unconfigured |
| Release & Versioning | Applies — build-only release-candidate workflow with SBOM, provenance attestation, and a keyless signature over `dist/SHA256SUMS`; it deliberately holds no publication authority, so the rest of the hardened-release shape presupposes a publish step this project does not have; recorded as WVR-009 in [waivers.yml](waivers.yml) |
| Observability | Applies — Tier C: the CLI is offline, emits no operational telemetry, and says so in [docs/OBSERVABILITY.md](docs/OBSERVABILITY.md) |
| Performance | Applies — narrowly: `make benchmark` reports a bounded synthetic median and p95, with no invented latency threshold until a representative workload is observed |
| Accessibility | N/A — no HTML, graphical, or other user-facing interface exists in M0; the only surface is an offline CLI |
| Internationalization | N/A — expert-authored machine manifest and English-only CLI in M0, with the exemption's scope, re-entry seam, owner, and review date in [docs/I18N.md](docs/I18N.md) |
| AI Evaluation | N/A — the shipped tool contains no model, AI SDK, or LLM call in validation, evaluation, or verification |
| Documentation | Applies — PRD, architecture, threat model, ADRs, and per-format specifications are committed and referenced below |
| Quality & Metrics | Applies — a 90% branch-coverage floor is merge-blocking, and the technical metrics ledger is in [docs/ROADMAP.md](docs/ROADMAP.md) |
| AI Development Measurement | Applies — development is AI-assisted under an accountable human maintainer, as recorded under Provenance; no Track A baseline has been measured, and none is claimed |
| Incident Response | Applies — see [docs/INCIDENT-RESPONSE.md](docs/INCIDENT-RESPONSE.md) and the private-advisory route in `SECURITY.md` |
| Data Governance | Applies — synthetic and public discovery data only; see [docs/DATA-GOVERNANCE.md](docs/DATA-GOVERNANCE.md) |

## Provenance

This project is developed AI-assisted (Claude Code) under an accountable human
maintainer. Every change must pass the merge-blocking `make verify` gate (Ruff,
strict mypy, and pytest with a 90% branch-coverage floor) plus the committed CI
security scans. Development assistance does not change the product boundary:
the shipped tool remains standard-library only and makes no LLM or network call
in validation, evaluation, or verification.

## Project documents

- [PRD](docs/PRD.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Roadmap and metrics](docs/ROADMAP.md)
- [Research and competitive boundary](docs/RESEARCH.md)
- [Adversarial product review](docs/RED-TEAM.md)
- [Discovery and independent-mapping pack](docs/DISCOVERY-PACK.md)
- [Evidence-plan format and privacy profiles](docs/EVIDENCE-PLAN.md)
- [Single-evidence check format](docs/SINGLE-EVIDENCE-CHECK.md)
- [Threat model](docs/THREAT-MODEL.md)
- [Responsible-tech audit](docs/RESPONSIBLE-TECH-AUDITS.md)
- [User-research guide](docs/USER-RESEARCH.md)
- [Public sample candidates](docs/discovery/public-sample-candidates.md)
- [Data governance](docs/DATA-GOVERNANCE.md)
- [Observability declaration](docs/OBSERVABILITY.md)
- [Incident response](docs/INCIDENT-RESPONSE.md)
- [Release posture](docs/RELEASE.md)
- [Internationalization declaration](docs/I18N.md)
