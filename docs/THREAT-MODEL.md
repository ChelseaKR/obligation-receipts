# Threat model

**Scope:** M0 offline CLI
**Reviewed:** 2026-07-22

## Assets

- authoritative source identity;
- approved obligation mapping;
- evidence integrity and confidentiality;
- reviewer/issuer attribution;
- evaluation result;
- receipt payload integrity.

## Adversaries and failures

| Threat | M0 control | Residual risk |
|---|---|---|
| Supplier changes source after approval | required source SHA-256 is rechecked | dishonest initial source selection |
| Manifest executes code | closed schema; no command/plugin/expression fields | future adapters could reintroduce execution |
| Evidence path escapes root or changes meaning by platform | portable lexical relative-path checks reject traversal, dot/empty segments, URI/colon forms, Windows drives/UNC, and backslashes before root access; containment is rechecked after resolution | operator chooses an overbroad root |
| Huge source or pathological artifact exhausts memory | contract source hashing is capped at 16 MiB; manifests/artifacts at 2 MiB; JSON at 64 levels and 100,000 nodes; recursion failures fail closed | parsing/hashing still consumes resources within those bounds |
| FIFO or device blocks a parser before type checking | descriptors use nonblocking opens before `fstat` and require regular files | network filesystems may implement flags differently |
| Evidence changes between evaluation and hashing | JSON is parsed and hashed from one descriptor-stable byte snapshot | a privileged local actor can still replace parent directories during path resolution |
| Stale or aliased attestation reused | binds contract/version/manifest/obligation/evidence item | M0 has no validity-window policy |
| Reviewer name fabricated | receipt preserves supplied attribution | no authentication or signature in M0 |
| Evidence content leaks in receipt | only digest and bounded result emitted | filenames, clause IDs, and correlatable digests may still be sensitive |
| Ambiguous JSON changes meaning between parsers | duplicate keys and non-finite numbers are rejected in evidence, attestations, and receipts | other JSON interoperability differences may remain |
| Negative or non-canonical array pointer selects unintended evidence | only RFC 6901 canonical nonnegative array indices are accepted | JSON Pointer still proves only the selected value, not semantic adequacy |
| Receipt or attestation extension smuggles unreviewed claims | trust-bearing envelopes use exact closed field sets | payload meaning still depends on the documented schema |
| Recomputed checksum wraps arbitrary claims | verifier closes nested payload fields and rechecks counts, evidence/status compatibility, and overall algebra | an unsigned attacker can still fabricate an entirely self-consistent receipt |
| Predictable temporary receipt path is pre-positioned | collision-resistant same-directory temporary file and atomic replace | directory durability is delegated to the local filesystem |
| Collection checklist leaks operational metadata | portable plan redacts paths, source locators, and free-text reasons; local detail requires explicit opt-in | assertion thresholds and binding identifiers may remain sensitive |
| Plan checksum is mistaken for approval or currentness | fixed false limitations; checksum-only and manifest-regeneration statuses are distinct | M0 has no authenticated manifest approval |
| Stale plan is used after a manifest/source change | optional exact regeneration rechecks the source-bound manifest and privacy profile | operators can skip manifest-backed verification |
| Plan is mistaken for evidence or an outcome | `evidence_observed` is fixed false and outcome fields are absent | downstream tooling may still mislabel artifacts |
| One passing artifact is mistaken for obligation completion | single check fixes completion false and reports declared versus unchecked evidence counts | a downstream UI can hide limitation fields |
| Artifact digest is mistaken for authenticity | result labels digest as content identifier only and document as unsigned | digest can correlate sensitive artifacts across logs or organizations |
| Sibling artifacts are read during a narrow diagnostic | lookup selects one globally unique evidence spec before invoking its evaluator | full evaluation remains a separate command |
| Concurrent hostile filesystem swaps bypass containment | final-component no-follow and one-descriptor snapshots; docs require a trusted evidence root | replaceable parent directories are not a hardened multi-user sandbox |
| Payload altered without checksum update | canonical SHA-256 verification | attacker can rewrite payload and checksum; no M0 authenticity |
| Timestamp presented as trusted | envelope says caller-claimed and untrusted | a downstream UI could misrepresent it |
| Missing evidence treated as breach | distinct missing/review states | users may still overinterpret status labels |
| Contract text treated as legal truth | fixed decision-scope limitation | organizational pressure can override documentation |

## Misuse cases

- Using a receipt as a legal compliance certificate.
- Vendor self-authoring both obligations and evidence without buyer review.
- Selecting only easy clauses and implying complete contract coverage.
- Reclassifying a required clause as `should` to obtain an accepted result.
- Converting subjective obligations into weak proxy metrics.
- Treating automated accessibility output as full accessibility conformance.

These are governance failures. M1 must add role separation, coverage reporting,
amendment history, and signed approvals before production use.
