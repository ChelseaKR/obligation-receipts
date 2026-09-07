# Changelog

All notable changes will be documented here.

## [Unreleased]

### Changed

- **The dogfood job references this repository's composite action as `$/`, not
  `./`, and zizmor's `impostor-commit` audit is enabled again.** The two are
  the same fact arriving twice. `./` resolves an action through the runner's
  workspace, so a step that had cloned something earlier could decide which
  action ran; `$/` is GitHub's self-repository form, resolved by Actions at the
  commit the workflow is running, and zizmor reports the `./` form from v1.30.0
  onward — which is what turned #85, an ordinary `zizmor-action` bump, red.
  Measured before changing anything: zizmor 1.29.0 (what CI runs today) parses
  `$/` and reports nothing, 1.30.0 reports `./` as a finding, and 1.16.3 cannot
  parse `$/` at all, so the two versions overlap and the change can land ahead
  of the bump rather than with it.
  `.github/zizmor.yml` existed only to disable `impostor-commit`, because
  `release.yml` pinned a reusable workflow in the private
  `ChelseaKR/portfolio-standards` that this workflow's GITHUB_TOKEN 404s on, and
  older zizmor abandoned the whole file's audit on that error rather than
  failing closed. #84 repointed the pin at the public `ChelseaKR/.github`, so
  the reason is gone and the file with it. The ci.yml step that asks the same
  identity question stays: it asks the stricter form of it — is the SHA a *tag
  ref* of the repository the pin names — and a required check depends on it.
  Two comments and one test docstring that still described the private pin, its
  `UNREADABLE_PINS` skip and the disabled audit are corrected rather than left
  as a rationale for something that no longer exists.

### Fixed

- **`action.yml` was outside the pin-identity gate and outside the publication
  ban.** It is the file other repositories execute, and two of the three
  supply-chain gates could not see it. Both holes were measured on `origin/main`
  before anything changed, and in both cases the whole 145-test suite stayed
  green.

  The digest gate reads `pinned_files` — workflows plus `action.yml` — and proves
  a pin is forty hex characters. The gate that asks the question that matters,
  whether that SHA is a *tag ref of the repository the pin names*, read
  `.github/workflows` alone, both in ci.yml's `grep -r` and in
  `_pinned_repositories`. Replacing `action.yml`'s `actions/upload-artifact` SHA
  with forty different hex characters changed nothing anywhere: format checked,
  identity never asked, in the one file this repository publishes for others to
  run. That is precisely the substitution
  `test_every_pinned_sha_is_resolved_against_the_repository_it_names` exists to
  stop, and its own docstring says so.

  The publication ban read `workflow_files`, so `action.yml`'s only cover was a
  six-spelling copy of the command list in `tests/test_ci_action.py` against the
  twelve in `_PUBLISH_COMMANDS`. Adding a `softprops/action-gh-release` step to
  `action.yml` passed every assertion in the repository. The capability half of
  the ban — the half that *closes*, because a job cannot create a release without
  `contents: write` — cannot reach a composite action at all: it declares no
  `permissions:` and runs under the caller's. So the open-ended command list is
  the entire cover there, which makes its completeness matter more in that file
  rather than less, which is the opposite of how the two copies were sized.

  Both gates now read `pinned_files`, and
  `test_the_pin_identity_step_reads_every_file_the_digest_gate_reads` holds
  ci.yml's `grep` path arguments to that same set — a relation between two file
  sets rather than an assertion that the string `action.yml` appears somewhere in
  the step, so a path added to one and forgotten in the other fails, in either
  direction.

  Two duplicated literals went with them. `tests/test_ci_action.py` compiled its
  own copy of the `@[0-9a-f]{40}` pattern, so it proved things about a regex
  nothing ran — the same shape as the local-reference exemption that was once
  guarded by a check of a *different* exemption — and it kept its own shorter
  publish list. A second, weaker copy of a gate is worse than none, because it
  reads as coverage. Cross-module import was not the repair available: pytest
  runs `--import-mode=importlib` and `tests/` is not a package, so
  `import test_supply_chain` raises `ModuleNotFoundError` (measured). What
  replaces them is the premise the strong gates rest on — that `action.yml`
  references other actions at all — so if it stops doing so they cannot go
  quietly vacuous over it.

- **The evaluator's artifact cap is copied into two modules and nothing held the
  copies equal.** `evaluator._MAX_ARTIFACT_BYTES`, `inventory.MAX_ARTIFACT_BYTES` and
  `progress.MAX_ARTIFACT_BYTES` are three separate 2 MiB literals; the two newer ones
  are documented as "the evaluator's artifact cap", and the honesty claim of both
  commands rests on that being true. `progress` states that "'present' here means
  'present and usable by `evaluate`' rather than 'a file of some size exists'", and
  `inventory` states that an oversized file "must be reported as unreadable rather than
  as a present artifact the evaluator would later refuse". Measured: tightening
  `evaluator._MAX_ARTIFACT_BYTES` to 256 KiB alone left the whole suite green at exit 0,
  and a 1 MiB artifact then read as present under both `inventory` and `progress` while
  `evaluate` refused it. Each module's tests use its own constant, so they move with
  whichever copy they were written against.
  `tests/test_misuse_boundaries.py` now compares every artifact-cap literal the package
  declares, found by importing each module rather than by naming the three that exist
  today, so a fourth copy is covered without anyone remembering to add it. The test
  fails against a drifted evaluator and passes on this tree; no constant changed.

- Ten wrong page numbers in `docs/discovery/public-sample-candidates.md`. Every
  THECB locator was recorded one page low: §3.4 Deliverables is on p.9, not p.8,
  and §3.5 Acceptance Criteria on p.10, not p.9. The clauses selected were right
  and the pointers to them were not, which is the failure mode this repository
  exists to argue about, here in its own research record. Found by re-fetching
  the document and resolving each locator against the extracted text; the ten
  CalOES locators verified unchanged.

### Added

- **The closed assertion vocabulary gains `in`, `not_in`, `between`, `length` and
  `type`.** `json_assertion` supported seven operators, so "status is one of passed or
  skipped", "version is between 1.2 and 2.0" and "the results array is non-empty" each
  became manual review or several obligations. All five keep the existing flat
  pointer/operator/expected shape, so the evidence plan, the single-evidence check and
  the receipt carry them with no new field. Still closed and non-executable: no regex,
  no arithmetic, no comparison between two pointers.

  The whole extension lives in what `expected` may be, per operator, and every shape is
  enforced **at load time by every command that loads a manifest** -- an empty array for
  `in`, inverted bounds for `between`, a non-integer length, `integer` for `type`. Each
  is a `ManifestError` about the approved manifest rather than an observed `fail` in a
  receipt, which is the same line `pointer.is_well_formed` draws and the same failure
  `models.ASSERTION_OPERATORS` was consolidated to prevent.

  Three behaviours are asserted rather than assumed, because the wrong reading is the
  tempting one. **A value with no length is not length zero**: `length lte 0` against the
  number `7` is a `fail`, since collapsing "has no length" into "length is 0" would
  publish a measurement nobody took. **A boolean is never a number**: `in` will not match
  a resolved `true` against `expected = [1]` even though Python considers `1 == True`,
  and `type` reports it as `boolean`. **`integer` is not an available type name**,
  because JSON has one number type and a manifest that could say `integer` would make
  `1.0` a `fail` against `1` for a difference no JSON parser preserves.

  Composition (`all_of`, `any_of`) is not included: it needs a nested assertion shape the
  plan, the single-evidence check and the receipt do not carry. #64 stays open for it.


- **An obligation can now be bound to the span of the approved source it quotes,
  and nothing could check that before.** `Obligation.text` and `clause_ref` were
  validated only as non-empty strings; `_parse_contract` opened the contract
  source and hashed it, but never read a byte of it for content. A verifier could
  prove the receipt matched the manifest, and the manifest matched the document's
  digest, and still not prove the quotation was in the document — so a typo, a
  paraphrase, a clause pasted from a superseded version, or a sentence nobody
  agreed to reached a counterparty as an authoritative-looking quotation with a
  matching digest beside it.
  Each obligation may now declare `source_span = { offset, length, sha256 }`.
  The loader resolves it against the source the manifest is already bound to,
  re-derives the digest, and requires `text` to be **exactly** those bytes with
  no normalization of any kind ([ADR 0002](docs/decisions/0002-obligation-text-is-verbatim-source-bytes.md)).
  Every failure is a `ManifestError` raised before anything is evaluated, never
  an observed `fail`. The receipt payload and the `local_sensitive` evidence plan
  carry the span so replay re-checks it; `portable_redacted` omits it, as it does
  every other source locator.
  Measured on the committed example: **two of its four obligation texts were
  already wrong.** A-1 dropped "in the approved acceptance run" and A-2 dropped
  "accessibility" and "before acceptance". Both now quote the source verbatim,
  which moved the example's `manifest_sha256`, its two attestation bindings, and
  the two pinned receipt payload digests.
  Spans are optional at manifest schema v0.1:
  `tests/fixtures/manifest-without-source-spans.toml` is the example exactly as
  it was written before spans existed and still normalizes to
  `90f93af7…`, pinned as a test. `validate` reports `source_spans_declared`
  including `0`; `verify` reports `source_spans_verified: null` when no manifest
  was supplied, because "not checked" and "none declared" are different facts.

- A verification record in `docs/discovery/public-sample-candidates.md`: both
  frozen sources re-fetched from their official URLs on 2026-09-06, byte counts
  and SHA-256 digests reproduced exactly 46 days after retrieval, and each of the
  twenty locators resolved against the extracted text. Recorded as a documented
  procedure rather than a CI check, because a gate that fetches a live
  third-party URL and asserts a hash fails as if the repository were wrong the
  day the publisher re-exports the file.
- Immutable sample and clause IDs for the two documents with a frozen byte
  artifact, namespaced per sample so a third document never renumbers them. The
  USDA/FNS candidate is deliberately unassigned: an ID would let a clause key
  point at a document nobody can reproduce.
- `docs/discovery/rater-workbook-prepared.csv`, the shared instrument each rater
  copies, carrying the twenty clause keys with identification filled and every
  judgment column blank. `research-metrics` compares two workbooks by their
  `(sample_id, clause_id)` key set, so two raters who each invented their own
  clause IDs would produce two individually valid files the tool cannot compare
  -- discoverable only after both had finished.
- `tests/test_discovery_sample.py`, binding the record, the instrument and
  `research._HEADER` to each other, and asserting the instrument carries no
  ratings and is refused by `load_ratings` until a rater fills it.

- **`--allow-absent-source`: verify a receipt or a plan without possession of the
  approved contract document.** `manifest._parse_contract` opened and re-hashed
  `contract.source_path` unconditionally, so every manifest-bound command required
  the SOW itself — and independent replay, the chain the README ends on, was
  therefore impossible for anyone not entitled to it. The manifest can now be loaded
  against `contract.source_sha256` alone, under an explicit opt-in, and reports
  `contract_source_binding` as `verified` or `declared_only`. Only ABSENCE is
  downgradable: a present source whose digest does not match, a path that escapes
  its root, and a source that is not a regular file are all refused under both
  modes, with the same messages. Without the flag, behaviour is byte-identical
  including the error text, and the flag is refused where no manifest is loaded at
  all. `manifest_sha256` is deliberately identical under both bindings — if the
  binding entered the hashed payload, the replay this mode exists to enable would
  fail on the digest rather than on the evidence.
  Accepted by `validate`, `evidence-plan`, `verify-evidence-plan` and `verify`.
  `evaluate` and `freeze-evidence` refuse it and say why: whether a *receipt* may be
  produced against an unchecked contract binding is the open half of #78.

## [0.1.0] - 2026-09-04

First tagged technical-alpha candidate. M0 scope: an offline CLI that evaluates
a human-authored obligation manifest against bounded local evidence and issues
an unsigned deterministic receipt. Not published to any package index; the
release workflow builds and attests a candidate and holds no publication
authority (WVR-009).

### Added

- `pointer.py`, one RFC 6901 definition shared by manifest loading,
  evidence-plan validation, and evaluation.
- `waivers.yml`, recording each control this repository cannot implement, with
  an owner and a mandatory expiry, and a merge-blocking test that fails once
  that expiry passes.
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

- Pinned receipt payload digests: two literals that fail on any change to the
  bytes a receipt carries. Nothing pinned them before, so every determinism
  test compared two values that moved together and a wire-format change passed
  a full green suite.
- Tests for defenses the threat model claimed and nothing held: each of the
  four attestation identity bindings independently, `O_NOFOLLOW` on both
  bounded readers, acceptance at exactly each size cap, and the lowercase-digest
  requirement across all four verifiers.
- `[project.urls]`, so a built distribution carries Homepage, Repository,
  Issues, Changelog and Documentation links; it carried none.
- `Typing :: Typed`, advertising the `py.typed` marker the wheel already
  shipped, plus audience, environment and testing classifiers.
- `twine check --strict` in `make package-check`, and `tests/test_packaging_metadata.py`
  holding `CITATION.cff` to the version `pyproject.toml` declares -- the one
  version string no other gate could reach.
- A CI step asserting every pinned action SHA is a tag in the repository the
  pin names. Resolving the SHA through the commits endpoint cannot do this:
  GitHub forks share the upstream object store, so a commit that exists only
  in a fork returns 200 against the upstream repository.
- `timeout-minutes` on every runner job, replacing the six-hour default on
  workflows that execute fork-authored code.

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

- Count requirements rather than bytes in `dependency-scan`, and drop
  `--no-dev`. The export always carries a comment header, so `test -s` was
  true when nothing would be audited: pip-audit ran against an empty set and
  the "no runtime dependencies" branch was unreachable. The development
  toolchain, which is what actually executes in CI, is now in scope.
- Widen the lockfile-drift guard from `ci.yml` alone to every workflow and
  `.pre-commit-config.yaml`, and fix the two violations outside its old scope:
  `release.yml` installed with `uv sync --frozen`, and a `pre-push` hook ran a
  bare `uv run` that rewrites `uv.lock` in the working tree.
- Widen the publication boundary assertions from `release.yml` alone to every
  workflow, and assert declared permissions rather than only command spellings.
- Add `scripts` to the Semgrep targets; it holds a gate implementation that
  runs in CI and was never scanned.
- Derive `__version__` from installed distribution metadata, pin the hatchling
  build backend, and align the package keywords with the repository topics.
- Retire WVR-008 rather than renew it. It was granted because code scanning
  was unavailable on a private repository and named its own revisit trigger:
  the repository is public and code scanning is available but unconfigured, so
  every clause of its rationale is false. The gap is real, open, and now
  unwaived; the expiry test would not have caught this for twelve more weeks,
  because it detects decay by time and this waiver decayed by a change of fact.
- Ignore `.claude/worktrees/`, so a checkout of another branch inside the
  repository cannot fail this one's `ruff check .`.

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
  because code scanning was not enabled on this then-private repository, in
  favor of
  plain GitHub Actions annotations; zizmor's own exit code still fails the
  job on real findings, and the job no longer needs `security-events` or
  `actions` permissions to run.
- Keep the operating-system failure cause out of the digested receipt payload.
  `detail` interpolated the exception class name, so one `missing` verdict
  digested three ways depending on whether an artifact was absent, unreachable
  or unreadable, and a receipt written in one environment failed replay in
  another as a payload mismatch.
- Refuse an evidence root that is not a directory. `Path.resolve(strict=True)`
  succeeds on a regular file, so a mistyped `--evidence-root` produced a
  checksummed receipt reporting the obligations unmet, indistinguishable from
  a supplier that delivered nothing.
- Return the documented exit code when stdout is a closed pipe; a broken pipe
  exited 120, outside the band callers are told they never have to guess about.
- Catch `BoundedPathError` and `StrictJsonError` in the CLI: both are
  `ValueError` subclasses that were absent from the band, so either would have
  printed a traceback and exited 1 rather than 2.
- Correct the `check-evidence` exit-code rows. An absent or unusable
  attestation exits 4, not 3; only `json_assertion` evidence reaches `missing`.
  The split is by evidence kind, not by failure mode.
- Correct the README tagline, which claimed the clause-to-obligation
  conversion the tool refuses to perform and a human performs.

### Removed

- `sha256_file`, an unbounded reader with no `O_NOFOLLOW`, no regular-file
  check and no size cap, in a module whose stated discipline is bounded
  fail-closed reads. It had no callers and its own test held it at full
  coverage.
