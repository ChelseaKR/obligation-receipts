# ADR 0002: An obligation's text is verbatim source bytes, compared with no normalization

**Status:** Accepted
**Date:** 2026-09-07
**Decider:** Chelsea Kelly-Reif

## Context

`Obligation.text` and `clause_ref` were validated only as non-empty strings.
`_parse_contract` opened the contract source and hashed it, so the manifest was
bound to the document by digest — but the document's bytes were never read for
content. Nothing checked that the sentence the manifest quotes is in the
document the manifest is bound to.

A verifier could therefore prove that the receipt matches the manifest, and that
the manifest matches the document's digest, and still not prove the quotation is
in the document. A typo, a paraphrase, a clause pasted from a superseded
version, or a sentence nobody agreed to all survived every existing check and
reached a counterparty as an authoritative-looking quotation with a matching
digest sitting beside it. The obligation text is the field a human reads first
and was the only one nothing checked.

That is the same shape as two failures this repository already writes against.
`models.ASSERTION_OPERATORS` exists because an unimplemented operator sent a
supplier a `fail` for something nothing evaluated. `pointer.is_well_formed`
exists so an authoring defect is an input error rather than an observed result.

## Decision

Each obligation may declare a `source_span` — a byte `offset`, a byte `length`,
and a `sha256` over exactly those bytes of the approved source. At load time the
span is resolved against the source the manifest is already bound to, its digest
is re-derived, and **the obligation's `text` must equal those bytes exactly.**

**No normalization is applied.** Not whitespace folding, not line-ending
translation, not Unicode normalization, not case. `text.encode("utf-8")` is
compared to the source slice with `==`.

## Options considered

| Option | Authoring cost | What the receipt can claim |
|---|---|---|
| **No normalization (chosen)** | High — the author reproduces the source's own line breaks | "This is the document's bytes" |
| Fold runs of whitespace | Low | "This is the document's words, in order" |
| Unicode NFC, then fold whitespace | Low | "This is something that renders like the document" |
| Compare nothing; span is advisory | None | Nothing — the current state |

Whitespace folding is the tempting option and it is the one that quietly gives
up the claim. Once a comparison is allowed to ignore *any* difference, the
receipt no longer says "these are the bytes of the clause"; it says "these are
bytes that some normalizer maps onto the clause", and the reader now has to know
which normalizer. Two documents can fold to the same string. A hard-wrapped
clause and a re-flowed one are not the same evidence about what was agreed, and
the person who has to defend the receipt is the one who would have to explain
the difference.

## Consequences

- **A real, deliberate cost to authors.** A clause that is hard-wrapped in the
  source must be quoted with its line breaks, which in TOML means a multi-line
  string. `examples/accessibility-acceptance/obligations.toml` shows this: three
  of its four obligations now use `"""…"""` and read less tidily than the
  paraphrases they replace. Two of those paraphrases were also *wrong* —
  A-1 dropped "in the approved acceptance run" and A-2 dropped "accessibility"
  and "before acceptance" — which is the finding, not an accident of the
  exercise.
- Spans are **optional at manifest schema v0.1**. A manifest declaring none
  loads, normalizes, hashes, plans and evaluates exactly as before;
  `tests/test_source_spans.py` pins the pre-spans manifest digest to prove it.
- `validate` reports `source_spans_declared`, including `0`. A manifest that
  binds no quotation and a manifest whose spans were never looked at are
  different facts, and the absence of an error is not a measurement of either.
- `verify` reports `source_spans_verified: null` when no manifest was supplied,
  rather than `0`.
- Every span failure is a `ManifestError` raised before anything is evaluated —
  an authoring defect in the approved manifest, never an observed `fail` in a
  receipt.
- A span is a locator into the source, so `plan.py`'s `portable_redacted`
  profile omits it alongside `clause_ref`.

## Deliberately left open

- **Whether spans become required at a future schema version.** Required is the
  only version that makes the guarantee unconditional, and it is a breaking
  change for every manifest already written. Optional is what shipped; the
  decision to require them is not made here.
- **Whether a span coverage denominator is meaningful** — "what fraction of the
  document is under obligation" is issue #53, gated on discovery, and nothing
  here takes a position on it. This decision only makes such a measure possible.
