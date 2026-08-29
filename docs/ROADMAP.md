# Roadmap and metrics

## Now: M0 technical hypothesis

- [x] Source-bound strict manifest
- [x] Four obligation classifications
- [x] Bounded local JSON evaluation
- [x] Content-bound manual and external attestations
- [x] Explicit overall-status algebra
- [x] Deterministic receipt payload and untrusted envelope
- [x] Offline integrity verification and evidence replay
- [x] Synthetic example spanning every classification
- [x] Adversarial usefulness, duplication, adoption, and safety review
- [x] Complete ≥90% branch coverage gate
- [x] First clean `make verify`
- [x] Descriptor-stable evidence parsing and hashing
- [x] Closed semantic receipt verification
- [x] Bounded two-rater discovery metrics utility
- [x] Typed-wheel content gate
- [x] Redacted-by-default, manifest-bound evidence collection plan
- [x] Hosted CI on push and pull request, since 2026-08-05
- [x] `protect-main` requiring a pull request and all six checks, since
      2026-08-07; zizmor's ability to block was proved on 2026-08-27
- [x] One RFC 6901 pointer definition shared by load, plan, and evaluation,
      so an authoring defect is an input error rather than an observed fail

## Next: discovery, not features

- [ ] Map three public SOWs from different jurisdictions.
- [ ] Measure classifiable-clause rate and independent agreement.
- [ ] Interview 8–12 acceptance, procurement, QA, accessibility, security, prime,
      and IV&V practitioners.
- [ ] Observe one real acceptance-evidence assembly workflow.
- [ ] Obtain one serious, nonbinding design-partner next step.
- [ ] Select exactly one vertical pack.

## M1 only if proceed thresholds pass

- Signed manifest-approval and review roles.
- Evidence validity windows and explicit staleness.
- Coverage denominator: every in-scope clause must be classified.
- One adapter family selected from observed workflow.
- Static accessible trace report.
- Amendment diff and invalidation rules.
- Signed release pipeline with actual publication authority. Hosted CI is no
  longer listed here: it shipped on 2026-08-05, ahead of the thresholds.

## Later

- OCDS milestone export.
- Cross-organization evidence exchange.
- Proposed-mapping review queue.
- Model-assisted mapping research with a committed gold set.

## Kill rules

Stop or reframe if:

- fewer than 25% of sampled consequential clauses are objectively classifiable;
- independent experts cannot reach κ 0.50 on classification;
- the primary buyer wants document storage rather than evidence replay;
- no budget-adjacent participant considers the bounded outcome purchasable;
- the first design partner requires legal conclusions or compliance
  certification;
- maintaining adapters dominates the obligation/evidence model; or
- existing acceptance-management software already solves the observed workflow.

## Technical metrics ledger

| Attribute | M0 target | Evidence |
|---|---:|---|
| Correctness | 0 false passes from missing/unbound evidence | tests |
| Reproducibility | identical input payload digest | tests/demo |
| Security | 0 accepted absolute/traversal paths | tests |
| Maintainability | strict typing; complexity ≤10 | `make verify` |
| Coverage | ≥90% branch | `make verify` |
| Dependency risk | 0 runtime dependencies | `pyproject.toml` |
| Artifact bound | ≤2 MiB per evidence/receipt JSON | code/tests |
| Structure bound | ≤64 JSON levels and ≤100,000 nodes | code/tests |
| Snapshot binding | parsed evidence bytes equal hashed bytes | code/tests |
| Package typing | wheel contains `py.typed` and every runtime module, derived from the source tree rather than a hand-listed baseline | `make package-check` |
| Performance | reproducible local median/p95 report; no invented threshold | `make benchmark` |
| Planning privacy | local paths/locators/reasons require explicit opt-in | code/tests |
| Planning currentness | checksum self-check separated from exact manifest regeneration | code/tests |
