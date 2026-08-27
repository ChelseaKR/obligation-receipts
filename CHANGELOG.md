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
- AI-assisted development disclosure in the README, separating development
  provenance from the no-LLM product boundary.
- A `protect-tags` GitHub ruleset requiring signed, non-deletable,
  non-rewritable tags, alongside the existing protected-`main` ruleset.
- SBOM generation and a keyless cosign signature over `dist/SHA256SUMS` in the
  release-candidate workflow, next to the existing build-provenance
  attestation.
- `security` and `incident` repository labels, and a private-advisory
  reporting route documented in `SECURITY.md`.

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
- **Breaking:** extend the single-check exit-code discipline to the whole CLI
  from one shared `obligation_receipts.exit_codes` contract, so exit 2 now means
  only "no result document was produced". `evaluate` previously returned 2 for a
  `rejected` or `incomplete` evaluation — the same code as an unreadable
  manifest, an absent evidence root, or a source-digest mismatch — leaving an
  automated acceptance pipeline unable to tell an evaluated negative outcome
  from a tool failure. `rejected` is now 1 and `incomplete` is 3. `verify`
  likewise returns 1 for a payload-digest or replay mismatch, because a receipt
  that does not reproduce is an integrity finding about that receipt rather than
  a failure to read it.
- Check the `--manifest`/`--evidence-root` pairing for `verify` before reading
  the receipt, so an incomplete invocation is reported as such instead of as
  whatever the receipt path happened to fail on first.

- Require every CI check in the `protect-main` ruleset, not only `verify`.
  `package`, `dependency-scan`, `secret-scan`, `sast` and `zizmor` all ran,
  all reported, and none could stop a merge, so the secret, SAST, SCA and
  workflow-lint gates were advisory in practice. The ruleset now also requires
  a pull request, at zero required approvals, which records the solo-maintainer
  carve-out as a rule rather than as an absence, and closes the direct-push
  path to `main`.
- Assert in `tests/test_supply_chain.py` that the Dependabot ignore list and the
  cross-repository reusable-workflow pins stay in step, in both directions, so
  neither a renamed workflow nor a stale ignore entry can quietly reintroduce a
  failing weekly update job or suppress a live dependency.

### Fixed

- Restore the weekly `Dependabot Updates` job to green. The `github-actions`
  updater failed on 2026-07-24, 07-31, 08-07, 08-14 and 08-21 because
  `release.yml` pins a reusable workflow in the private `portfolio-standards`
  repo that Dependabot's repo-scoped credentials cannot read; one recorded
  `git_dependencies_not_reachable` error fails the whole run even though every
  other action was checked and its pull requests were opened. The pin is now
  ignored explicitly, with the trade-off and the credential-based re-entry
  condition documented in `.github/dependabot.yml`, alongside the same
  repository's already-documented effect on `.github/zizmor.yml`. The sibling
  `pip` updater was unaffected throughout.
- Restore the `zizmor` CI check to green. Its `impostor-commit` audit cannot
  read the private `portfolio-standards` repo that `release.yml` pins as a
  reusable workflow, and errors out for the whole file rather than skipping
  just that reference; the audit is disabled with a documented scope and
  re-entry condition in `.github/zizmor.yml` rather than left permanently
  red or silenced with an unscoped workaround.
- Switch the `zizmor` job off the SARIF/GitHub-Advanced-Security upload path
  (`advanced-security: true`, the action's default), which always failed
  because code scanning is not enabled on this private repo, in favor of
  plain GitHub Actions annotations; zizmor's own exit code still fails the
  job on real findings, and the job no longer needs `security-events` or
  `actions` permissions to run.
