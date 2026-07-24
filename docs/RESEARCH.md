# Research and competitive boundary

**Scan date:** 2026-07-22
**Claim posture:** adjacent-capability map, not an exhaustive market or patent search

## Evidence that the problem exists

- FAR recognizes acceptance testing as a way to determine whether a product
  conforms to contract requirements.
- Section 508 procurement guidance recommends enforceable accessibility
  criteria, representative workflows, testing checkpoints, and corrective
  action.
- Public software contracts routinely require approved acceptance plans, test
  data, expected results, remediation, and retest.
- NASA software-assurance guidance asks for objective, traceable acceptance
  evidence.

## Adjacent software and standards

| Adjacent category | What it does | Boundary |
|---|---|---|
| Contract lifecycle management | drafting, negotiation, signature, obligation tracking | does not ordinarily execute technical acceptance evidence |
| Test management | plans, cases, runs, defects | test is not source-bound contractual obligation |
| Pact/PactFlow | API consumer-provider contracts | machine interactions, not procurement language or human review |
| OCDS | contracting lifecycle and implementation milestones | data representation, not evidence evaluation |
| GRC/OSCAL | control catalogs and compliance evidence | broader control programs; different acceptance unit and buyer workflow |
| Spec-driven development gates | verify implementation against development specs | team/internal spec, not authoritative procurement source and mixed evidence |
| IV&V services | expert independent verification | service model; potential partner or competitor |

## Defensible contribution hypothesis

Not a new hashing primitive, test runner, contract parser, or evidence store.
The contribution under test is:

1. the approved clause is a first-class, source-bound object;
2. verification method is explicit before evaluation;
3. human, external, automated, and unverifiable evidence remain distinct;
4. missing evidence cannot become breach or success;
5. the result is portable and replayable outside the originating tool.

## Primary sources

- [FAR 9.302](https://www.acquisition.gov/far/9.302)
- [FAR Part 46](https://www.acquisition.gov/far/part-46)
- [Section 508 QASP guidance](https://www.section508.gov/buy/integrate-section-508-in-qasps/)
- [Section 508 procurement testing](https://www.section508.gov/buy/define-accessibility-criteria/)
- [OCDS milestones](https://standard.open-contracting.org/latest/en/guidance/map/milestones/)
- [Pact documentation](https://docs.pact.io/implementation_guides/python/docs/consumer)
- [NASA SWE-193](https://swehb.nasa.gov/spaces/SWEHBVD/pages/102695528/SWE-193%2B-%2BAcceptance%2BTesting%2Bfor%2BAffected%2BSystem%2Band%2BSoftware%2BBehavior)
- [OpenProcurement acceptance test stand](https://openprocurement.org/en/test-stand.html)

## Research still required

- Current commercial test-management and government-acceptance platforms.
- Patent search for executable contractual acceptance and evidence receipts.
- Practitioner workflows in state/local government and federal primes.
- Whether OSCAL or an existing assurance-case format should be extended instead.
- Public contract samples suitable for an independent mapping benchmark.
