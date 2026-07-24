# AGENTS.md — Obligation Receipts

## Product thesis

Obligation Receipts tests whether an already-approved software-acceptance
obligation has the evidence its accountable owner said it requires. It does not
write contracts, interpret law, replace procurement judgment, or certify
compliance.

The contribution under test is the chain:

`source-bound obligation → typed evidence → fail-closed result → deterministic receipt → replay`.

## Load-bearing invariants

1. **Human-approved manifest first.** Runtime code never extracts or interprets a
   clause. A future drafting assistant may propose a manifest, but it may never
   activate or evaluate one without recorded human approval.
2. **No arbitrary execution.** A manifest cannot contain a command, query,
   template expression, Python import, plugin, or URL to execute or fetch.
3. **Missing is not failing.** Missing, invalid, stale, or unbound evidence stays
   distinct from an observed failure.
4. **Unverifiable is valid output.** Ambiguous prose is never silently converted
   into a convenient metric.
5. **Source and evidence binding.** Every result binds to the normalized manifest,
   approved source digest, and evidence artifact digest.
6. **Receipts do not overclaim.** M0 receipts are unsigned, carry no trusted time,
   and state that their scope is technical evidence evaluation only.
7. **No evidence content in receipts.** Receipts contain hashes and bounded
   results, not source contract text, screenshots, reports, or sensitive data.
8. **Replay before trust.** A receipt can be internally verified without its
   evidence and replayed when the exact manifest and evidence are available.
9. **Planning is not evaluation.** An evidence plan reads no evidence, reports
   no outcome, redacts local metadata by default, and distinguishes checksum
   self-consistency from exact manifest regeneration.
10. **One artifact is not an obligation.** A single-evidence check preserves its
    narrow status, never aggregates, and always declares the obligation
    incomplete and sibling evidence unchecked.

## Engineering conventions

- Python 3.12+, standard library runtime, `src/` layout.
- `ruff`, strict `mypy`, and branch coverage ≥90%.
- All file mutations use an atomic replace where a partial artifact would be
  misleading.
- Keep public APIs small. M0 supports the CLI plus `load_manifest`,
  `evaluate_manifest`, and `verify_receipt`.
- Add a negative test for every new parser or trust-boundary behavior.
- Do not add a web interface before real discovery supports one.

## Definition of done for M0

- Synthetic demo exercises every evidence classification.
- A changed source digest invalidates the manifest.
- Path traversal and absolute evidence paths fail closed.
- A failed `must` rejects; an unresolved `must` is incomplete.
- Tampering with the receipt payload is detected.
- Fresh replay matches the committed receipt payload.
- The PRD names a cheapest test and kill threshold for the product hypothesis.
