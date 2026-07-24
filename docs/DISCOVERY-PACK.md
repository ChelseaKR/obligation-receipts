# Discovery pack

This pack tests whether obligation-to-evidence mapping is a repeatable product
job rather than bespoke contract interpretation.

## Sample selection

Select three public software SOWs or acceptance plans from different
jurisdictions and buyers. Record the source URL, retrieval date, document digest,
document type, amendment status, and why it is representative. Do not use
confidential contracts or infer that a public sample is current.

An unrated starting set with two byte-frozen official PDFs and one federal
candidate awaiting a stable attachment URL is recorded in
[`public-sample-candidates.md`](discovery/public-sample-candidates.md). A
qualified selection owner must confirm or replace these candidates before
freezing the sample.

From each document, predeclare ten consequential clauses covering at least
three of:

- accessibility;
- data export or portability;
- security evidence;
- availability or performance;
- interoperability;
- testing and remediation;
- documentation or training; and
- human review or approval.

The selection owner freezes the clause IDs before either rater begins.

## Independent mapping exercise

Two qualified raters independently complete one row per clause using
[`mapping-rater-template.csv`](discovery/mapping-rater-template.csv).

Allowed classifications are:

- `automated`;
- `manual_review`;
- `external_evidence`;
- `unverifiable`; or
- `out_of_scope`.

Raters record proposed evidence and criticality, but agreement is measured first
on classification. They may not reconcile until both files are frozen and
digested.

## Metrics

Report:

- total frozen clauses;
- fraction objectively classifiable as automated, manual, or external;
- classification confusion matrix;
- raw agreement;
- Cohen's kappa where defined;
- disagreement reasons after reconciliation;
- median mapping minutes per clause;
- number requiring legal or procurement interpretation; and
- number already handled adequately in the buyer's current software.

Apply the PRD gates without moving thresholds after seeing the result:

- proceed evidence: ≥40% classifiable and κ ≥0.70;
- serious warning: <25% classifiable or κ <0.50.

Undefined kappa due to a single-category sample must be reported, not replaced
post hoc with a friendlier metric.

After both CSVs are frozen, run:

```sh
obligation-receipts research-metrics rater-a.csv rater-b.csv
```

The utility requires identical unique `(sample_id, clause_id)` sets and exact
frozen columns. Its conservative `consensus` classifiable rate counts a clause
only when both raters assign the same automated, manual-review, or
external-evidence classification. `gate_status` is `proceed`,
`serious_warning`, or `indeterminate`; undefined kappa can never produce
`proceed`. The output digests both input files so reconciliation cannot silently
replace the independent ratings.

## Buyer workflow interview

Ask participants to reconstruct the last acceptance event before demonstrating
the tool. Capture:

1. authoritative source;
2. who decided what evidence counted;
3. where evidence lived;
4. how missing evidence differed from failure;
5. amendment behavior;
6. approval authority;
7. current software and manual glue;
8. cost of delay, rework, dispute, or audit;
9. budget-adjacent owner; and
10. whether a replayable receipt would change a real decision.

Do not collect confidential contract language in the research repository.

## Decision record

After 8–12 conversations and three mapping exercises, publish aggregate results
and one of:

- proceed with exactly one vertical evidence pack;
- integrate with an existing system;
- reframe as a methodology/service; or
- stop.

Technical elegance is not a reason to override a kill threshold.
