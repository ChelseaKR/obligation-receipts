# Adversarial product review

**Decision:** proceed to discovery; do not present M0 as a novel category,
production control, or compliance product.

## Scorecard

| Quality | Score | Adversarial conclusion |
|---|---:|---|
| Usefulness if the problem is real | 4/5 | Strong audit and handoff value, but only when acceptance evidence is repeatedly assembled |
| Evidence of a real niche | 3/5 | Primary guidance supports the workflow; buyer pain and budget remain unproven |
| Technical distinctiveness | 4/5 | Source binding, typed mixed evidence, explicit unverifiability, and replay form a coherent new seam |
| Proven market novelty | 2/5 | Adjacent categories are crowded and the scan is not exhaustive |
| Defensibility | 2/5 | Data model and workflow learning, not the hash or evaluator, must become the moat |
| Feasibility | 5/5 | M0 works offline with zero runtime dependencies |
| Safety for production use | 2/5 | Unsigned identity, role separation, staleness, and coverage-denominator controls are missing |

Scores are hypotheses, not evidence of product-market fit.

## Strongest attacks

### “This is just test management with contract IDs”

Test-management tools already connect requirements, cases, runs, and defects.
If practitioners can bind authoritative source versions, human reviews, external
attestations, and deliberately unverifiable obligations in their existing tool
and independently replay the result, this project adds little.

**Falsifier:** two observed teams demonstrate the full workflow in existing
software without spreadsheets, custom glue, or manual evidence-package work.

### “This is a CLM obligation tracker with a checksum”

Contract-lifecycle tools already extract and assign obligations. The evaluator
is only distinct if the operative unit is technical acceptance evidence rather
than reminders, dates, and business workflow.

**Falsifier:** a mainstream CLM product natively executes bounded technical
acceptance criteria and exports independently replayable mixed-evidence results.

### “This is GRC evidence collection in a narrower costume”

GRC and OSCAL ecosystems already model controls, evidence, assessment, and
findings. Extending one may be more interoperable than creating another format.

**Falsifier:** a small OSCAL profile can express the source-bound,
obligation-level workflow with less translation and equal usability for
acceptance staff.

### “The expensive part is interpretation, which M0 refuses to do”

Human mapping may consume all value and turn the product into consulting. The
runtime is deliberately simple; maintaining mappings after amendments may be
the actual hard problem.

**Test:** time two experts mapping the same public ten-clause excerpt, measure
agreement, then repeat after a realistic amendment. Reframe as a methodology or
service if authoring and reconciliation dominate repeated evaluation.

### “The receipt creates false certainty”

A weak proxy can make an ambiguous obligation look objective. A vendor could
author the manifest, evidence, reviewer name, and unsigned receipt. A
self-contained checksum cannot authenticate any of them.

**M0 response:** unverifiable is first-class; classifications are closed;
missing evidence never passes; trust limitations are explicit.

**Production blocker:** signed roles, segregation of duties, evidence validity
windows, complete in-scope clause coverage, amendment invalidation, and
independent security and legal review.

### “No one owns the budget”

QA may feel the pain while procurement, the contracting officer’s
representative, legal, the prime, and IV&V each own only part of the decision.
Cross-organizational value can mean no buyer.

**Test:** every discovery conversation must identify the last actual cost,
authority boundary, current tool, and budget-adjacent owner. Interest without a
funded workflow is not validation.

## Non-duplication test

Before M1, evaluate at least one current product from each category:

1. contract lifecycle/obligation management;
2. test management and requirements traceability;
3. GRC/OSCAL evidence systems;
4. public-sector procurement/contract administration;
5. specification-driven development gates; and
6. IV&V evidence-package services.

Use the same scenario and score whether each can:

- bind an exact authoritative source;
- distinguish automated, human, external, and unverifiable evidence;
- fail closed on missing or unbound evidence;
- preserve the denominator of all in-scope obligations;
- export a portable result without raw confidential evidence; and
- replay the result independently.

If an existing product passes five of six without bespoke work, integrate with
it or stop.

## Business-model attacks

| Model | Attractive because | Likely failure |
|---|---|---|
| Open-source CLI + paid vertical packs | trust, adoption, public-interest fit | packs become bespoke consulting |
| Governed on-prem team product | sensitive evidence stays controlled | long enterprise and government sales cycle |
| Hosted multi-party exchange | recurring network value | security, records, authority, and procurement burden |
| IV&V-enabled service | immediate domain expertise and revenue | software never becomes repeatable |

The least-regret first bet is open core plus one evidence pack chosen from an
observed design-partner workflow. Do not build a hosted exchange before role,
records-retention, and buyer questions are answered.

## Verdict

The technical seam is original enough to investigate but not original enough to
claim. The cheapest next work is not another feature. It is three public-source
mapping exercises, 8–12 clean discovery interviews, and a hands-on comparison
against existing tools. The PRD’s kill thresholds should be enforced even if
the implementation remains technically elegant.
