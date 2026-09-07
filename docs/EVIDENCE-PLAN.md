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
value. Attestation requirements give the allowed statuses, exact required
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

`length`'s comparison is one of `eq`, `ne`, `gt`, `gte`, `lt`, `lte`. It is a
fixed two-key table, not an expression: two required keys, no nesting, no third
key. `"the results array is non-empty"` is
`operator = "length"`, `expected = {operator = "gte", value = 1}`.

**Every one of these shapes is enforced when the manifest loads**, by every
command that loads one. An `expected` the operator cannot use — an empty array
for `in`, inverted bounds for `between`, `integer` for `type` — is a
`ManifestError` about the approved manifest, never an observed `fail` in a
receipt. That is the same line a malformed pointer is held to, and for the same
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

Composition — `all_of` and `any_of` over several assertions — is **not** in the
vocabulary. It needs a nested assertion shape that the plan, the single-evidence
check and the receipt do not carry, and it is tracked at
[#64](https://github.com/ChelseaKR/obligation-receipts/issues/64).

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
