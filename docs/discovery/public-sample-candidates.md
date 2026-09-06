# Public SOW sample candidates

**Retrieved:** 2026-07-22
**Locators verified against the authoritative PDFs:** 2026-09-06 (see
[Verification record](#verification-record))
**Status:** candidate selection only; clauses have not been independently rated,
classified, interpreted, or frozen for the discovery experiment

These sources were selected from official public-sector systems. They contain no
confidential contract material. A qualified selection owner must confirm the
final sample and freeze clause IDs before two independent raters begin.

Clause IDs are **assigned** below and are stable, but the sample is **not
confirmed**: the federal candidate still has no byte artifact, and confirming or
substituting it is the selection owner's call. IDs are namespaced by sample so
that adding, replacing, or dropping a document never renumbers another one.

## Texas Higher Education Coordinating Board

- **Sample ID:** `thecb-sow-781-5-03717`
- **Document:** SOW 781-5-03717 IT Ticketing Software Replacement and
  Implementation
- **Buyer/jurisdiction:** Texas Higher Education Coordinating Board, State of
  Texas
- **Type:** software implementation statement of work
- **Source:** [official THECB PDF](https://reportcenter.highered.texas.gov/agency-publication/sow-781-5-03717-it-ticketing-software-replacement-and-implementation/thecb-sow-781-5-03717-it-ticketing-software-replacement/)
- **Retrieved file:** 325,330 bytes; 25 pages; PDF 1.6
- **SHA-256:** `fe89fab860902533a12cd3ce58ecb70c797ed0f2a89c191fb75962011cd356ff`
- **Digest status:** frozen; re-fetched and reproduced byte-for-byte 2026-09-06.
- **Why representative:** modern SaaS/ITSM replacement covering migration,
  configuration, UAT, training, production sign-off, invoicing, and
  post-acceptance defects.

Candidate locators, not classifications. Page numbers are PDF page indexes,
which for this document equal the printed footer on every numbered page (page 1
is an unnumbered cover):

| Clause ID | Locator |
|---|---|
| `c01` | PDF p.9 §3.4 Project Plan |
| `c02` | PDF p.9 §3.4 Data Migration Plan |
| `c03` | PDF p.9 §3.4 User Acceptance Testing Plan |
| `c04` | PDF p.9 §3.4 Data Migration to UAT |
| `c05` | PDF p.9 §3.4 Data Migration to Production |
| `c06` | PDF p.9 §3.4 System Configuration |
| `c07` | PDF p.9 §3.4 Knowledge Transfer |
| `c08` | PDF p.10 §3.4 Hypercare |
| `c09` | PDF p.10 §3.5 Acceptance Criteria and written sign-off |
| `c10` | PDF p.10 §3.5 latent-defect correction |

**These page numbers were corrected on 2026-09-06.** Every one of the ten was
recorded one page low: §3.4 Deliverables begins on p.9, not p.8, and §3.5
Acceptance Criteria begins on p.10, not p.9. The clause text named by each
locator was found where the corrected number says it is; nothing in the
selection changed, only the pointer. See the verification record below.

The embedded PDF title is "Agile SOW Template"; the official catalog title is
project-specific. Tables may require visual review because extracted text wraps.

## California Governor's Office of Emergency Services

- **Sample ID:** `caloes-ifb-8500-2016-sow-appendix-a`
- **Document:** 9-1-1 CPE Systems Statement of Work, Appendix A to IFB
  8500-2016, Addendum 3
- **Buyer/jurisdiction:** California Governor's Office of Emergency Services,
  State of California
- **Type:** public-safety technology system SOW and acceptance plan
- **Source:** [official CalOES PDF](https://www.caloes.ca.gov/wp-content/uploads/PSC/Documents/Addem-3-IFB-911-CPE-8500-2016-SOW-Appendix-A_111416.pdf)
- **Retrieved file:** 3,314,941 bytes; 104 pages; PDF 1.5
- **SHA-256:** `d85eca940232e3f94aa46c8e798e630b55ba064a55c14c8fa3ab7f6360b8a2a2`
- **Digest status:** frozen; re-fetched and reproduced byte-for-byte 2026-09-06.
- **Why representative:** mission-critical hardware/software acquisition with a
  timed operational test, quantified effectiveness measure, written records,
  acceptance checklist, payment linkage, re-testing, and buyer remedies.

Candidate locators use the printed footer page numbers, which for this document
equal the PDF page index on every page checked:

| Clause ID | Locator |
|---|---|
| `c01` | printed p.27 Acceptance Testing Criteria ¶1 |
| `c02` | printed p.27 Acceptance Testing Criteria ¶2 |
| `c03` | printed p.27 Acceptance Testing Criteria ¶3 |
| `c04` | printed p.27 Acceptance Testing Criteria ¶4 |
| `c05` | printed p.28 Acceptance Testing Criteria ¶7 |
| `c06` | printed p.28 Acceptance Testing Criteria ¶10 |
| `c07` | printed pp.28-29 Acceptance Testing Criteria ¶12 |
| `c08` | printed p.29 §1.11.2 System Acceptance Testing |
| `c09` | printed p.30 §1.11.3 Acceptance Testing for Software |
| `c10` | printed p.30 §1.11.3 application-program testing paragraph |

All ten verified unchanged on 2026-09-06. The earlier caution that "browser page
indexes may be one lower than the printed footer" did not hold for this
document — footer p.27 is PDF page 27 — and it is the *other* sample, which
carried no such caution, that was off by one. The caution is kept as a warning
about the class of error rather than as a claim about this file.

Section numbers `1.11.2` and `1.11.3` are not printed at those headings; they
are the SOW's own cross-reference to them, which appears on printed p.48
("as defined in SOW Sections 1.11.2, System Acceptance Testing and 1.11.3,
Acceptance Testing for Software"). The headings themselves read "System
Acceptance Testing" and "Acceptance Testing For Software (Other Than Operating
System Software)", and the table of contents places them on 29 and 30.

## U.S. Department of Agriculture, Food and Nutrition Service

- **Sample ID:** not assigned. IDs are assigned only to documents with a frozen
  byte artifact, so that a clause key can never point at a document nobody can
  reproduce.
- **Document:** Performance Work Statement — Services for Maintenance, Support
  and Enhancements of the Food Programs Reporting System and National Databank,
  Solicitation 12319819R0006
- **Buyer/jurisdiction:** USDA Food and Nutrition Service, United States
- **Type:** federal software operations, maintenance, and enhancement PWS
- **Source:** [official SAM.gov opportunity](https://sam.gov/opp/c3c15ce04caa4ec5b3d56690e00aada6/view)
- **Digest status:** not frozen. The public viewer exposed indexed solicitation
  content but not a stable direct attachment URL during retrieval.
- **Why representative:** controlled change delivery, UAT release packages,
  traceability, test-history deliverables, service metrics, monitoring, and
  government acceptance.

Candidate locators:

1. §1.4.1, Change Request Process for O&M.
2. §1.4.1, production-ready release-package requirement.
3. §1.4.1, updated release-package documentation.
4. §2.2.1, Deliverable 004, certification/accreditation documentation.
5. §2.2.1, Deliverable 011, Requirements Traceability Matrix.
6. §2.2.1, Deliverable 012, installation guide.
7. §2.2.1, Deliverable 014, test history, cases, and final outcomes.
8. §2.2.2, modification-analysis traceability.
9. §2.2.2, Business Analysis and Business Rules Maintenance matrix row.
10. §2.2.2, Operations and Maintenance Support matrix row.

These locators were **not** verified on 2026-09-06, because there is no byte
artifact to verify them against. That is the point of the digest status: an
unverifiable locator list is kept visibly separate from the two that were
checked, rather than being carried alongside them as if it had the same standing.

This third candidate must not enter the frozen sample until a stable byte
artifact and SHA-256 are recorded, or the selection owner substitutes another
official document.

## Verification record

**Date:** 2026-09-06. **Performed by:** repository maintenance, not by a rater.
**What this is not:** it is not a rating, a classification, or a legal reading of
any clause. It checks only that each recorded pointer resolves to the text it
names, in the document the digest identifies.

**Method.** Each frozen source was re-fetched from the official URL above over
HTTPS, its byte count and SHA-256 recomputed, and its text extracted per page
with `pdftotext -layout` (Poppler). Each locator was then resolved by finding the
named section, heading, or numbered paragraph and reading the page it falls on,
including the printed footer of that page. Extraction is a proxy for visual
review: it establishes which page carries the text, and it is why the THECB
note about wrapped tables is retained rather than retired.

**Results.**

| Source | Bytes reproduced | SHA-256 reproduced | Locators checked | Locators correct as recorded |
|---|---|---|---:|---|
| `thecb-sow-781-5-03717` | yes, 325,330 | yes | 10 | 0 — all ten one page low; corrected above |
| `caloes-ifb-8500-2016-sow-appendix-a` | yes, 3,314,941 | yes | 10 | 10 |
| USDA/FNS candidate | n/a, no artifact | n/a | 0 | not assessable |

Both frozen digests reproduced exactly, 46 days after retrieval, so the recorded
hashes are live facts rather than a stale record of one download.

To reproduce, from any directory:

```
curl -sSL -o thecb.pdf 'https://reportcenter.highered.texas.gov/agency-publication/sow-781-5-03717-it-ticketing-software-replacement-and-implementation/thecb-sow-781-5-03717-it-ticketing-software-replacement/'
curl -sSL -o caloes.pdf 'https://www.caloes.ca.gov/wp-content/uploads/PSC/Documents/Addem-3-IFB-911-CPE-8500-2016-SOW-Appendix-A_111416.pdf'
shasum -a 256 thecb.pdf caloes.pdf
```

This is deliberately a documented procedure and not a CI check. A gate that
fetches a live third-party URL and asserts a hash fails the day the publisher
re-exports the file, and it fails as if the repository were wrong. The digests
are the record; re-running the procedure is how a reader confirms it.

## Rater instrument

`rater-workbook-prepared.csv` carries the twenty assigned clause keys with their
identification columns filled and **every judgment column empty**. Each rater
copies it and fills their own copy independently.

It exists because `research-metrics` compares two workbooks by their
`(sample_id, clause_id)` key set and refuses files whose key sets differ. Two
raters who each invented their own clause IDs would produce two valid files that
the tool cannot compare — a failure that would only surface after both had
finished. The shared instrument removes that failure mode.

`tests/test_discovery_sample.py` asserts the instrument's header matches the
protocol the tool enforces, that its keys match the tables above, and that its
judgment cells are empty — so a filled-in copy can never be committed in place of
the blank instrument.

## Next controlled step

1. ~~Confirm the three-document sample~~ or replace the unfrozen federal
   candidate. **Open, and an owner decision.** The two documents above are
   re-verified and reproducible; the third has no byte artifact. Confirming a
   two-document sample, obtaining the USDA artifact, or substituting another
   federal document are all defensible, and choosing between them is a judgment
   about what counts as representative.
2. ~~Visually verify each locator against the authoritative PDF.~~ Done for the
   two frozen documents on 2026-09-06, by text extraction rather than by eye;
   ten corrections made. Not done for the third, which has no artifact.
3. ~~Assign immutable sample and clause IDs.~~ Done for the two frozen
   documents, namespaced so a third does not renumber them.
4. ~~Record exact source digests in both rater workbooks.~~ Done indirectly and
   deliberately: the digests are recorded here and bound to the workbook by
   `sample_id`, because the workbook's eleven columns are frozen by
   `research._HEADER` and adding a twelfth would break every rater CSV the tool
   accepts.
5. Have two qualified raters work independently before reconciliation. **Open,
   and the reason no number exists yet.** Both figures this experiment produces —
   the classifiable-clause rate and Cohen's κ — measure human judgment. Two
   workbooks written by one author, or by one model, would yield a κ that
   measured nothing, which is the failure this repository argues against.

## Open questions for the selection owner

- **The denominator.** `docs/PRD.md` sets the proceed threshold at ">=40% of
  clauses objectively classifiable". The ten locators per document are a
  hand-picked subset chosen because they looked acceptance-shaped, not a census:
  THECB §3.4 has twelve deliverable rows and four of them (RACI, Training Plan,
  Custom Report Templates and Dashboards, End-User Training) are not in the
  sample. A rate measured over clauses selected for looking classifiable is
  biased upward, and the threshold cannot be read against it without saying so.
  Either the denominator becomes every consequential clause in the sampled
  sections, or the reported figure is named as a rate over a purposive sample.
- **Two documents or three.** Whether the experiment runs on the two reproducible
  documents or waits for a third, per step 1.
