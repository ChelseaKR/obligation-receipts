# Improvement plan, 2026-08-28

The pass itself was working-tree only: nothing was committed while it ran,
because the accountable maintainer holds commit permission. The work was merged
to `main` afterwards, in pull request #38, this file included, so the constraint
recorded below is what held during the pass and not a description of this file's
present state. This file is the durable record of the plan and its running log.

## Constraint recorded at the top of the session

No commit, no push, no pull-request write, no index or HEAD movement, and no
change to any GitHub setting or branch ruleset. `protect-main` and
`protect-tags` are read-only in this pass. The owner keeps
`current_user_can_bypass: always`, confirmed by reading ruleset 20564800.

## Baseline

`make verify` on a clean tree: exit 0, 224 tests, 93.46% branch coverage,
1.3s. The tree was clean at `52360b7`.

## Issue triage

| Issue | Classification | Disposition |
|---|---|---|
| #14 Standards Conformance table invisible to the checker; two rows false | Real defect (documentation + missing guard) | Fix, and add a repo-local guard so it cannot regress |
| #15 Map three public SOWs, run the first non-synthetic evaluation | Real, high-value, **blocked** | Cannot be done without the authoritative PDFs and two independent human raters. Fabricating rater rows would be research fraud. De-risked mechanically instead |
| #16 Five of six CI jobs advisory | **Already fixed** at `52360b7`, residual documentation gap | Verified against the live ruleset. Residual CodeQL element recorded as a waiver |
| #21 `resolve_bounded_file` symlink escape and `hash_bounded_file` special file untested | Real gap in a security guard | Fix with tests that fail before the code they cover exists |
| #23 `cli.py` `__main__` guard and console entry point uncovered | Real gap | Fix with a subprocess test |
| #24 Two evaluator comparison branches untested, one dead | Real gap plus a latent semantic trap | Remove the dead branch, test the reachable one, lock the `exists`-on-`null` semantics |
| #26 Malformed JSON pointer evaluates as an observed fail | **Real defect**, contradicts the repo's own exit-code contract | Fix at manifest load, one validator shared by all three commands |
| #33 `_parse_obligation` adjacent branches and generic `BoundedPathError` untested | Real gap | Fix with one negative test per branch |

## CI diagnosis

| Run | Verdict |
|---|---|
| 32628287945 `verify` on `test-finite-float-canonicalization` | **Real defect, not a flake.** `ruff format --check` would have reformatted `tests/test_canonical.py`. The gate did its job; the author pushed a fix and the rerun passed |
| 33034714935 `zizmor` on `gate-proof/zizmor-blocks-merge` | **Deliberate, not a defect.** A temporary `zz-gate-proof.yml` was added with a real zizmor finding to prove the zizmor gate can turn a pull request red. It did, exit 12. The branch is not on `main` and the workflow does not exist there |

Neither failure is a flake, and neither is outstanding.

## Phases, ranked by value

### Phase 1 — guards that cannot fail

The portfolio's governing rule. A gate present, green, and structurally unable
to report what it exists to report.

1. `scripts/check_wheel.py` hardcodes twelve wheel members. `exit_codes.py` is
   a runtime module and is **not** among them, so the packaging gate cannot
   report the omission it exists to catch, while `docs/ROADMAP.md` claims the
   wheel is checked for "all runtime modules". Derive the required set from the
   source tree so it cannot drift, and cover the script with a test.
2. `tests/test_supply_chain.py` globs `.github/workflows/*.yml` only. A
   workflow named `.yaml` would escape the digest-pin assertion entirely.
3. Nothing in this repo asserts that its own Standards Conformance table is
   machine-readable. Add that guard, in the checker's own terms.
4. Nothing binds `docs/discovery/mapping-rater-template.csv` to
   `research._HEADER`. Silent drift there would waste two raters' work and is
   the mechanical risk under #15.

### Phase 2 — issue #26, the one real behavioral defect

### Phase 3 — issues #21, #23, #24, #33

### Phase 4 — issue #14, documentation truth

### Phase 5 — issue #16 residual

### Phase 6 — changelog, final verification

### Phase 7 — added mid-pass: untested integrity guards

Raising coverage was not the point; the point is that `plan.py`,
`receipt.py`, and `single_check.py` each carried guards no test exercised.
An untested guard is one deletion away from being silently absent, which is
the same failure shape as a gate that cannot fail. The redaction promise in
`plan.py` and the overclaim guards in `single_check.py` are the ones that
matter most, because they are what the README promises in prose.

### Phase 8 — added mid-pass: the SAST gate's stated scope

`ci.yml` runs `semgrep scan --config p/python src tests`. Semgrep's built-in
ignore list drops `tests/` wholesale, so the gate scanned `src` only while
naming both.

### Phase 9 — added mid-pass: the one remaining conformance failure

`release_workflow` fails the portfolio checker. It is a deliberate divergence,
not a defect: the control's remaining elements all presuppose a publish step
this project has decided not to have. The honest record is a waiver, not an
`N/A` row the checker would accept but that would be false, because versioning,
a changelog, and a signed candidate build all exist here.

## Status

All nine phases complete — six planned, three added mid-pass. One issue, #15,
is blocked and stated as blocked. Nothing was committed while the pass ran; the
work was merged to `main` afterwards, in pull request #38.

The figures below are this pass's before and after, not a running total.

| Metric | Before | After |
|---|---|---|
| Tests | 224 | 345 |
| Branch coverage | 93.46% | 99.89% |
| Modules at 100% | 3 of 12 | 12 of 13 |
| `make verify` | exit 0 | exit 0 |
| Portfolio conformance score | 28/30 | 29/30 |

At the end of this pass the one uncovered line was `cli.py`'s
`raise SystemExit(main())`. It is no longer uncovered, and the reason is worth
recording: `tests/test_cli.py` had always executed it in a child process, but a
child records nothing unless `COVERAGE_PROCESS_START` is set in its
environment, so the report named as unrun two lines the suite ran on every
invocation. With the recorder started in the subprocess environment (#41),
`src/` measures 100% statement and branch coverage, and all thirteen modules
report 100%.

## Running log

- Read `AGENTS.md`, `README.md`, every source module, every test, the CI
  workflow, and both live rulesets. Ran the portfolio conformance checker.
- Read all eight open issues and both CI failures in full. Neither failure is a
  flake and neither is outstanding.
- Phase 1.1: proved the wheel gate accepted a wheel missing `exit_codes.py`,
  then derived the requirement set from the source package. Broke it (swallowed
  the missing-member exit code): 13 failures. Restored: 18 pass.
- Phase 1.2: proved an unpinned `actions/checkout@v4` in a `.yaml` workflow
  passed the digest-pin gate, then widened the glob and added a discovery
  assertion. Both directions observed.
- Phase 2: five malformed-pointer cases failed before the fix and pass after.
  Weakening `is_well_formed` back to the leading-slash check fails 7 tests,
  including one that already existed in `test_plan.py`, which shows the shared
  validator is load-bearing on the plan path too.
- Phase 3: #21, #23, #24, #33. The first FIFO test for `hash_bounded_file`
  passed for the wrong reason -- `resolve_bounded_file` rejected the FIFO first
  and the function under test never ran. Rewritten to simulate the race the
  duplicate check exists to close, and confirmed against line coverage.
- Phase 4: the conformance table now parses; `readme_conformance_table` moved
  FAIL to PASS with all fifteen standards declared. Four deliberate breaks of
  the new guard all fail loudly. The first version failed at collection time,
  which would have masked other failures, so it was restructured to fail as a
  test.
- Phase 5: `waivers.yml` records the CodeQL element of #16 with an owner and a
  2026-11-30 expiry, and lints clean against
  `STANDARDS/automation/check_waivers.py`. The ruleset itself was read only.
- Phase 7: `plan.py`, `receipt.py`, and `single_check.py` reached 100%. Added a
  guard that the receipt verifier's status algebra and the evaluator's cannot
  drift, since both implement the same rule and nothing compared them.
- Phase 8: added `.semgrepignore`, taking the SAST scan from 13 files to 29. A
  planted `shell=True` in a test file is now found (exit 1) where the same file
  was previously invisible (exit 0).

## Blocked, and why

**#15, the first non-synthetic evaluation.** Not attempted. It requires the
three authoritative PDFs, which are not in the repository and would have to be
fetched from the network; visual verification of every clause locator against
those PDFs; and two qualified raters completing the workbooks independently
before any reconciliation. I am not two independent raters, and producing rater
rows myself would be fabricated research data in a repository whose entire
argument is that a record says only what was actually checked. A measured 18%
would be a real result; an invented 41% would be worse than no result.

What was done instead is the part that can be done without a rater: the
mechanical risk in the protocol is now closed. `docs/discovery/mapping-rater-template.csv`
and `research._HEADER` are bound to each other in both directions, and the
template's own example row is parsed under the real protocol. Before this, the
two could drift silently and the drift would only surface after two people had
already filled in unusable workbooks.

**Two things needing repository writes I do not have.** The `release_workflow`
divergence has no tracking issue, because `gh` writes are withheld in this
pass; WVR-009 records it, but an issue should be opened. And the portfolio's
central `STANDARDS/waivers.yml` is a different repository, so the two entries
written in this pass were recorded locally only; `check_waivers.py --portfolio`
will pick them up on its next aggregate run. WVR-008 has since been retired: it
was granted because code scanning was unavailable on a private repository, and
the repository is now public with code-scanning default setup reporting
`not-configured` rather than unavailable. Only WVR-009 remains.

**One judgement left to the owner.** Branch coverage measured 99.89% in this
pass against a merge-blocking floor of 90%, and measures 100% today. The floor
still fails on a real regression, so it is not a broken gate, but it is loose
enough that a large one could slip. It is documented as 90% in `AGENTS.md`, the
README, and `CONTRIBUTING.md`, and the portfolio's own `coverage_floor_value`
control reads that number, so raising it is a standards decision rather than a
cleanup, and it was left alone.

Correction made after this pass: `CONTRIBUTING.md` carried no percentage at all
when the sentence above was written, so the pointer named a document that did
not document the floor. It carries the floor now, and `tests/test_docs.py`
checks all three documents against `pyproject.toml`, so the pointer cannot go
stale again. The floor itself was not changed.
