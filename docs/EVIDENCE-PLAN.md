# Evidence-plan format

An evidence plan is a deterministic projection of a source-bound manifest for
people or systems preparing evidence before evaluation. It does not read,
inspect, hash, validate, or evaluate evidence.

## CLI

Portable-redacted output is the default:

```sh
obligation-receipts evidence-plan obligations.toml --out evidence-plan.json
obligation-receipts verify-evidence-plan evidence-plan.json
obligation-receipts verify-evidence-plan evidence-plan.json \
  --manifest obligations.toml
```

A locally controlled workflow can opt into declared paths, source locators, and
free-text reasons:

```sh
obligation-receipts evidence-plan obligations.toml \
  --include-local-details \
  --out local-sensitive-plan.json
```

The output path is neither embedded in the plan nor repeated in CLI stdout.

## Closed document

The wrapper is `obligation-receipts/evidence-plan-document/v0.1` and contains
only:

- `schema_version`;
- `payload`; and
- `payload_sha256`, the SHA-256 of canonical payload bytes.

The payload `obligation-receipts/evidence-plan/v0.1` binds:

- contract ID and version;
- exact normalized-manifest SHA-256;
- exact source SHA-256;
- detail profile;
- an obligation count; and
- ordered collection requirements.

Each evaluable obligation carries its declared ID, classification, criticality,
`all_required` combination rule, and evidence requirements. Unverifiable
obligations use `not_applicable`, avoiding the false implication that an empty
requirement set was satisfied. Automated
requirements repeat the exact declared JSON pointer, operator, and expected
value — and, for a composing operator, the exact declared branches in order.
Attestation requirements give the allowed statuses, exact required
fields, and fixed contract/version/manifest/obligation/evidence-item binding
values.
Unverifiable obligations have no evidence requirements.

## The assertion vocabulary

`json_assertion` evidence declares one JSON pointer, one operator from a closed
set, and — for every operator except `exists` — one expected value. The
vocabulary is closed and non-executable: there is no expression language, no
regex, no arithmetic, and no comparison between two pointers or two files.

| operator | `expected` | passes when |
| --- | --- | --- |
| `eq`, `ne` | any bounded JSON value | the resolved value is / is not that value |
| `gt`, `gte`, `lt`, `lte` | a number | the resolved number orders that way against it |
| `exists` | *not allowed* | the pointer resolves at all |
| `in`, `not_in` | a non-empty array | the resolved value is / is not a member |
| `between` | `[low, high]`, numbers, `low <= high` | the resolved number is within, **inclusive at both ends** |
| `length` | `{operator = <comparison>, value = <non-negative integer>}` | the array, string, or object has that many elements, characters, or members |
| `type` | one of `null`, `boolean`, `number`, `string`, `array`, `object` | the resolved value is of that JSON type |
| `all_of`, `any_of` | *not allowed* — the operand is `branches` | every / at least one branch passes (see [Composition](#composition)) |

`length`'s comparison is one of `eq`, `ne`, `gt`, `gte`, `lt`, `lte`. It is a
fixed two-key table, not an expression: two required keys, no nesting, no third
key. `"the results array is non-empty"` is
`operator = "length"`, `expected = {operator = "gte", value = 1}`.

**Every one of these shapes is enforced when the manifest loads**, by every
command that loads one. An `expected` the operator cannot use — an empty array
for `in`, inverted bounds for `between`, `integer` for `type` — is a
`ManifestError` about the approved manifest, never an observed `fail` in a
receipt. So is a composition with one branch, with an `expected`, or nested past
the depth cap, and so is a `branches` member on an operator that does not
compose. That is the same line a malformed pointer is held to, and for the same
reason: a supplier must never be told their evidence failed a comparison that
was never made.

Three behaviours are worth stating because the alternative reading is tempting:

- **A value with no length is not length zero.** `length lte 0` against the
  number `7` is a `fail`, not a pass. Collapsing "this has no length" into "its
  length is 0" would publish a measurement nobody took.
- **A boolean is never a number.** `type` reports `true` as `boolean`, and `in`
  will not match a resolved `true` against `expected = [1]`, even though Python
  considers `1 == True`.
- **`integer` is not an available type name.** JSON has one number type, so a
  manifest that could say `integer` would make `1.0` a `fail` against `1` for a
  difference no JSON parser preserves.

## Composition

One clause often carries two thresholds. `all_of` and `any_of` express that
without splitting it into two obligations, which would say the contract has two.

```toml
[[obligations.evidence]]
id = "a5-axe-severity-thresholds"
kind = "json_assertion"
path = "automated/axe-summary.json"
pointer = "/summary"
operator = "all_of"
branches = [
  { pointer = "/critical_violations", operator = "eq", expected = 0 },
  { pointer = "/serious_violations", operator = "lte", expected = 2 },
]
```

- **A branch is an assertion**, with the same four members and the same rules: a
  well-formed pointer, an operator from the same closed set, an `expected` whose
  shape that operator can use, and — for `all_of` and `any_of` — its own
  `branches`.
- **A branch's pointer is resolved inside the value its parent resolved.** Above,
  the branches read `/summary/critical_violations` and
  `/summary/serious_violations`. A composition whose own `pointer` is the empty
  string addresses the whole document (RFC 6901 section 5), so its branches carry
  document-absolute pointers. One rule, both readings.
- **A composing operator declares no `expected`.** Its operand is `branches`.
- **At least two branches.** A composition of one is the assertion itself, and it
  is the only input that could be written two ways with two different answers —
  see the `missing` rule below.
- **Three assertion levels, no more.** The evidence item's own assertion is level
  1, its branches are level 2, theirs are level 3. A composition at level 3 is a
  `ManifestError`. The cap is what keeps "closed" a property of the format rather
  than of whoever wrote the manifest.

### `missing` is not `false`

A branch has three outcomes, and they combine as Kleene three-valued logic with
`missing` as the unknown:

| | at least one `fail` | else at least one `missing` | else |
| --- | --- | --- | --- |
| `all_of` | `fail` | `missing` | `pass` |

| | at least one `pass` | else at least one `missing` | else |
| --- | --- | --- | --- |
| `any_of` | `pass` | `missing` | `fail` |

`all_of`'s rule is the one the evidence plan already declares over an
obligation's several evidence items (`all_required`), restricted to the three
statuses an automated assertion can hold; `any_of`'s is its dual.

A branch whose pointer does not resolve is `missing` — **not `false`** — for
every operator except `exists`, which is the one operator whose question
"does this pointer resolve" has `false` as a real answer. Folding an unmeasured
branch into `false` is how `any_of` over two absent members would report an
observed failure against a supplier for a comparison nobody made.

**This differs, deliberately, from a flat assertion**, where a pointer that does
not resolve has been an observed `fail` since the beginning: the document does
not say the thing, and that is the whole answer. Inside a composition the answer
is folded with others, so "not measured" has to survive the fold. The two rules
can never disagree about one input, because the only assertion expressible in
both forms — a composition of one branch — does not load.

A composition whose own `pointer` does not resolve reports every branch as
unmeasured, and the receipt's detail says so with a denominator:
`assertion /summary any_of was not evaluable: 2 of 2 branches could not be
measured`.

### What the plan carries

A composing requirement's `assertion` object gains one member, `branches`, an
ordered array of assertion objects of the same shape. The member is **absent**
for every other operator, so a plan built from a manifest that composes nothing
is byte-identical to the plans built before composition existed, and a reader
built before it refuses a composing plan rather than silently treating `all_of`
as an assertion with no operand.

Branch order is preserved exactly and is part of the payload digest. It does not
affect any verdict.

## Privacy profiles

`portable_redacted` replaces:

- source locators with `null`;
- source spans with `null`, when the manifest declared one;
- evidence filesystem paths with `null`; and
- free-text unverifiable reasons with
  `no_evaluable_evidence_declared`.

A `source_span` is a byte offset, length, and digest into the approved contract
source (ADR 0002). It is a locator into the document, so it is redacted exactly
as `clause_ref` is: the offset says where in the contract a clause sits, and the
digest is a confirmable guess at the bytes there. The member is present only
when the manifest declared one, so a plan built from a manifest with no spans is
byte-identical to the plans built before spans existed.

It deliberately retains assertion thresholds and attestation bindings because a
collector otherwise cannot prepare the right artifact. Those values may still
be sensitive. “Portable” means reduced location leakage, not approved for public
release.

`local_sensitive` includes the exact manifest-declared source locators, source
spans, relative evidence paths, and reasons. Local paths remain lexical relative paths beneath a
future evidence root; absolute, traversal, Windows-drive/UNC, backslash,
colon/URI, dot-segment, and empty-segment paths fail plan generation.

Neither profile contains obligation prose, accountable-owner fields, source
bytes, evidence bytes, evidence hashes, reviewer-entered content, a working
directory, or the output path. A span's digest is not source bytes, but it does
let a holder of a candidate document confirm a guess at one clause of it; that
is why it is redacted from the portable profile rather than kept.

## Fixed limitations

Every payload sets `evidence_observed` to `false`, scopes itself to
`evidence_collection_checklist_only`, and records these fixed false claims:

- approval authenticated;
- completeness proven;
- evidence sufficiency assessed;
- legal interpretation performed; and
- official decision made.

Every non-unverifiable obligation says all declared requirements are required.
The plan cannot report pass, fail, missing, review, or an overall disposition.

## Verification semantics

Checksum-only verification means the closed payload is internally
self-consistent and unchanged. Because M0 has no signature, an attacker can
fabricate a new self-consistent plan.

Manifest-backed verification reloads the source-bound manifest and requires
byte-equivalent regeneration under the plan's own privacy profile. This detects
a stale plan or one derived from another manifest. It still cannot authenticate
who approved the manifest, establish that every contractual clause was mapped,
or decide whether the requested evidence is sufficient.
