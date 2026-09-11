# Single-evidence check

`check-evidence` is a narrow diagnostic for one evidence item already declared
in a source-bound manifest:

```sh
obligation-receipts check-evidence obligations.toml EVIDENCE_ID \
  --evidence-root evidence
```

It locates exactly one globally unique evidence ID and opens only that declared
artifact. Unknown IDs—including the ID of an unverifiable obligation rather
than an evidence ID—fail before evidence access.

## Output

The wrapper schema is
`obligation-receipts/single-evidence-check-document/v0.1`. Its canonical payload
schema is `obligation-receipts/single-evidence-check/v0.1`.

The payload binds:

- contract ID and version;
- source and normalized-manifest SHA-256;
- selected obligation ID, classification, and criticality;
- selected evidence ID and kind;
- preserved evidence status and artifact SHA-256 when available;
- declared evidence count and number deliberately not checked; and
- fixed scope `single_declared_evidence_check_only`.

It serializes no evidence path, source locator, obligation prose, assertion
pointer/operator/expected value, assertion branches, evaluator detail, evidence
content, sibling result, obligation result, or overall disposition.

That holds for every operator in the closed vocabulary, including the set,
range, length and type operators. They keep the same flat
pointer/operator/expected shape as `eq` and `gt`, so this document needed no new
field to carry them and redacts them by the same rule — an `expected` that is a
list of permitted statuses is exactly as much of a source locator as a scalar
one, and is withheld here for the same reason.

It holds for the composing operators too, and for the stronger reason. `all_of`
and `any_of` do add a member to the *manifest* and to the *evidence plan* — an
ordered `branches` array of further assertions — and this document carries none
of it. Its payload schema is unchanged: a check of a composing evidence item
reports the same evidence id, kind, status and artifact digest as a check of an
`eq`. A composition is more of an author's reasoning than a scalar comparison
is, so publishing it here would disclose more, not less. The vocabulary is
tabulated in
[EVIDENCE-PLAN.md](./EVIDENCE-PLAN.md#the-assertion-vocabulary), and composition
is described under [Composition](./EVIDENCE-PLAN.md#composition).

`obligation_evaluation_complete` is always `false`. For a two-evidence
obligation, checking one evidence reports `declared_evidence_count: 2` and
`other_evidence_not_checked_count: 1`, even if the selected result is `pass`.

## Limitations

The document is unsigned. Its fixed limitation fields say:

- no acceptance decision was made;
- obligation or manifest completeness was not assessed;
- evidence sufficiency was not assessed;
- no legal interpretation was performed;
- other declared evidence was not checked;
- the artifact digest is a content identifier/checksum, not authentication; and
- the digest may be sensitive or correlatable.

The payload checksum detects incomplete or accidental changes. An attacker can
fabricate a new internally consistent unsigned document.

## Status and exit codes

Automated assertions preserve `pass`, `fail`, and `missing`. Malformed automated
JSON is unavailable evidence and therefore remains `missing`, never an observed
failure.

An `all_of` or `any_of` is `missing` for a second reason: the artifact was read
and at least one branch could not be measured while no branch settled the
question — `any_of` where nothing passed and something was absent, or `all_of`
where nothing failed and something was absent. That is exit 3, not exit 1, and
the distinction is the point: exit 1 tells a supplier's pipeline their evidence
failed a comparison, and here no comparison was made. A flat assertion over an
absent pointer remains `fail`; see
[Composition](./EVIDENCE-PLAN.md#composition) for why the two differ and why
they cannot disagree about one input.

Manual and external attestations preserve `pass`, `fail`, and
`review_required`. Missing, malformed, incomplete, or manifest-unbound
attestations require review and never become a pass or observed failure. A
valid attestation is bound to its exact evidence ID as well as its contract,
manifest, and obligation, so one file cannot silently satisfy two declared
evidence items.

| Exit | Meaning |
|---:|---|
| 0 | selected evidence passed |
| 1 | selected evidence produced an observed failure |
| 2 | no check document: invalid manifest, unknown/ambiguous ID, unsafe root, or other input error |
| 3 | selected automated evidence is missing/unavailable |
| 4 | selected attestation requires review |

These are the shared CLI codes, not a table local to this command. Every command
draws from the same band; see the README's exit-code section for the whole
contract and `obligation_receipts.exit_codes` for the single mapping both this
command and `evaluate` are derived from.

## Operational security

The caller must provide a minimally scoped evidence root that is not writable
by an untrusted concurrent actor. Final-component no-follow and descriptor
snapshot controls do not provide a hostile multi-user filesystem sandbox for
replaceable parent directories.

Artifact digests can correlate the same confidential artifact across systems.
Treat stdout, shell history, CI logs, and retained check documents according to
the evidence program's retention and access policy. Do not publish check results
merely because raw content and paths were omitted.
