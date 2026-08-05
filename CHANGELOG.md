# Changelog

All notable changes will be documented here.

## [Unreleased]

### Added

- Strict source-bound obligation manifest.
- Automated JSON assertions, manual review attestations, external attestations,
  and explicit unverifiable obligations.
- Deterministic receipt payload with offline verification and replay.
- Synthetic accessibility-acceptance demonstration.
- Pinned CI, security, packaging, and build-only release-candidate workflows.
- Portfolio conformance, data-governance, incident-response, observability,
  release, and internationalization declarations.
- Unrated official public-SOW sample candidates with two byte-frozen source
  digests.

### Changed

- Make the M0 internationalization exemption mechanically auditable with its
  exact scope, re-entry seam, owner, and review date.
- Replace tag-triggered ambient release-candidate builds with explicit
  signed-tag authorization from protected main, exact-commit checkout, and
  candidate build provenance without granting publication authority; verify
  that boundary from permission and publisher semantics rather than a comment.
- Bound contract-source hashing at 16 MiB and reject blocking special files.
- Reject platform-dependent source/evidence path spellings before filesystem
  access.
- Bind attestations to exact evidence IDs to prevent within-obligation reuse.
- Preserve content digests for present malformed JSON while retaining unresolved
  status.
- Validate and bound receipt documents before atomic writes.
- Reject byte-identical discovery rater files as non-independent.
- Reject duplicate JSON object keys and non-finite JSON numbers across evidence,
  attestation, and receipt inputs.
- Reject negative, signed, leading-zero, non-ASCII, and otherwise non-canonical
  JSON Pointer array indices.
- Enforce exact closed fields for receipt and attestation envelopes.
- Parse and hash evidence from one bounded descriptor-stable byte snapshot.
- Bound JSON to 64 levels and 100,000 nodes, translate invalid UTF-8, and reject
  boolean/number equality ambiguity.
- Validate the closed receipt payload schema, counts, evidence compatibility,
  result algebra, and offset-bearing claimed timestamp.
- Write receipts through collision-resistant atomic temporary files.
- Add deterministic two-rater discovery metrics and a typed-wheel content gate.
- Add a closed, deterministic evidence-collection plan with redacted portable
  and explicit local-sensitive profiles.
- Add checksum self-consistency and exact manifest-regeneration verification for
  evidence plans, without reading evidence or claiming an outcome.
- Add a closed single-declared-evidence diagnostic that preserves pass, fail,
  missing, and review-required states with distinct CLI exits.
- Bind single checks to contract/source/manifest/obligation/evidence identities
  while omitting paths, content, assertion details, and aggregate conclusions.

### Fixed

- Restore the `zizmor` CI check to green. Its `impostor-commit` audit cannot
  read the private `portfolio-standards` repo that `release.yml` pins as a
  reusable workflow, and errors out for the whole file rather than skipping
  just that reference; the audit is disabled with a documented scope and
  re-entry condition in `.github/zizmor.yml` rather than left permanently
  red or silenced with an unscoped workaround.
- Grant the `zizmor` job `actions: read`, which its SARIF upload step needs
  to check prior workflow-run state on a private repo; without it, disabling
  `impostor-commit` let the job reach and fail at that later step instead.
