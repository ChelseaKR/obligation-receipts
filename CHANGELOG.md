# Changelog

All notable changes will be documented here.

## [Unreleased]

### Added

- `pointer.py`, one RFC 6901 definition shared by manifest loading,
  evidence-plan validation, and evaluation.
- `waivers.yml`, recording the one CICD-13 element this repository cannot
  implement, with an owner and a mandatory expiry, and a merge-blocking test
  that fails once that expiry passes.
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

- Bind the shipped rater workbook template to the frozen two-rater protocol it
  is filled in against, in both directions, so the discovery experiment cannot
  reach its raters with columns `research-metrics` will reject.
- Record hosted CI and the `protect-main` ruleset as shipped in
  `docs/ROADMAP.md` rather than as M1 items gated on discovery thresholds.
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

- Measure the CLI entry point the suite already runs. `tests/test_cli.py` has
  executed `cli.py`'s `if __name__ == "__main__":` guard in a child process
  since #23, but a child records no coverage unless `COVERAGE_PROCESS_START` is
  set in its environment, so the report kept naming the guard as an unrun line.
  Two lines this suite runs on every invocation were published as two lines it
  does not. The subprocess environment now starts a recorder, `[tool.coverage.run]
  parallel` keeps the child's data file from overwriting the parent's, and
  `src/` reports 100% statement and branch coverage rather than 99.89%. A new
  test asserts the mechanism directly against a data file of its own: without
  it, breaking the plumbing would silently return the report to understating
  what ran, and nothing — least of all the 90% floor — would fail.

- Stop dating hosted CI to a day this repository has no commit for. The README
  and `docs/ROADMAP.md` both said `since 2026-08-05`; `.github/workflows/ci.yml`
  has carried `push` and `pull_request` since the repository's first commit, and
  `git log --all` finds no commit dated 2026-08-05 at all. The date is gone
  rather than corrected, because the triggers are readable out of the workflow
  and a typed date is readable out of nothing. `tests/test_docs.py` now checks
  the documented triggers against the workflow and fails on a date typed back
  into that line.
- Stop backdating the `protect-main` requirements to the ruleset's creation.
  The ruleset has been active since 2026-08-07, but until the change recorded
  above under Changed it required only `verify`; the other five checks ran,
  reported, and could not block. Dating "a pull request and all six checks" to
  2026-08-07 claimed about three weeks of merge-blocking that did not happen.
  Both documents now say which requirement arrived when, and a test fails if
  the qualification is dropped. The `all six checks` phrasing is also checked
  against the jobs `ci.yml` actually defines, so a seventh job cannot quietly
  become a check nothing requires.
- Document the branch-coverage floor where `docs/plans/improvement-plan.md` said
  it was documented. That file named `AGENTS.md`, the README and
  `CONTRIBUTING.md`; `CONTRIBUTING.md` contained no percentage at all.
  `CONTRIBUTING.md` now states the floor, and a test reads `--cov-fail-under`
  out of `pyproject.toml` and fails if any of the three documents states a
  different number or stops stating one. The floor itself is unchanged at 90%.
- Stop a committed record from denying that it is committed.
  `docs/plans/improvement-plan.md` opened with "Nothing in this pass is
  committed" while being, itself, a file on `main`. The constraint is now
  described as what held during the pass, the outcome says the work was merged
  in pull request #38, and a test fails on a tracked plan that claims
  otherwise.
- Report a malformed manifest JSON pointer as the input error it is. A pointer
  with a dangling or invalid `~` escape used to load cleanly, then become a
  deterministic `fail` and an overall `rejected`: exit code 1 and a complete,
  checksum-verified, replayable receipt claiming an observed failure, on
  evidence that in fact satisfied the intended assertion. The same manifest was
  simultaneously refused by `evidence-plan` as invalid input, so one manifest
  produced two incompatible verdicts. Well-formedness is now checked once, at
  manifest load, where all three commands share it. Canonical array-index form
  is deliberately not part of that check: RFC 6901 makes a non-canonical index
  an error only when evaluated against an array, and the same token can legally
  name an object member, so rejecting it at load would refuse manifests that
  real evidence can satisfy (#26).
- Make the wheel content gate able to report the omission it exists to catch.
  Its required-member list was written by hand and had stopped covering
  `exit_codes.py`, so a wheel missing that runtime module passed and printed
  "verified wheel contents", while `docs/ROADMAP.md` claimed every runtime
  module was checked. The requirement set is now derived from the source
  package, and refuses to derive a vacuously satisfiable set from a missing or
  partial source tree.
- Widen the supply-chain workflow gate to `.github/workflows/*.yaml` as well as
  `*.yml`. An unpinned action in a `.yaml` workflow passed the digest-pin
  assertion because the file was never read. The gate now also asserts that its
  own file discovery covers every file in the directory.
- Make the README's Standards Conformance table readable by the portfolio
  conformance checker. Its `| Standard | M0 status |` header did not match the
  checker's rule, so the table was skipped entirely and DOC-11, DOC-12, and
  DOC-13 were unevaluated: every row could have been blank with no change in
  the reported result. The header is now `| Standard | State |`, all fifteen
  canonical standards are declared, and a test in this repository enforces the
  same rules the checker applies (#14).
- Remove `_compare`'s own `exists` branch. It was unreachable through its only
  caller and disagreed with the reachable path, which correctly treats a member
  whose value is JSON `null` as existing (#24).
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
