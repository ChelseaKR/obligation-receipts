# CI action and pre-commit hook

`obligation-receipts` ships a reusable [composite GitHub Action](../action.yml)
and a [pre-commit hook](../.pre-commit-hooks.yaml) so a vendor's acceptance
evidence is regenerated on every change rather than by hand on a maintainer's
laptop. A receipt only a maintainer can produce is not replayable in practice.

## The exit-code contract is the whole point

`src/obligation_receipts/exit_codes.py` reserves one band, and the action maps
each code to a different CI outcome rather than collapsing them into "failed":

| Code | Meaning | In CI |
|---:|---|---|
| 0 | every `must` obligation passed | job passes, `::notice::` |
| 1 | evidence was read and did not pass (`rejected`) | fails under every `fail-on` |
| 2 | manifest, path, argument, or document input error; **no result document** | **always** fails, as `::error::` |
| 3 | required evidence was absent or unusable (`incomplete`) | fails under `incomplete` and `any` |
| 4 | an attestation is unbound or awaiting review | fails under `any` |

Code 2 is deliberately outside `fail-on`. It means no result document was
produced, so it is a tool or input error and never an evaluated outcome. Letting
`fail-on: rejected` pass an unreadable manifest would report "nothing was
rejected" about a run that never evaluated anything — the same defect class as a
scanner whose flags are malformed reporting a clean scan.

## Usage

```yaml
# .github/workflows/acceptance.yml
name: acceptance

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read

jobs:
  evaluate:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - uses: ChelseaKR/obligation-receipts@v0.1.0
        with:
          mode: evaluate
          manifest: acceptance/obligations.toml
          evidence-root: acceptance/evidence
          receipt: ${{ runner.temp }}/receipt.json
          fail-on: incomplete
```

To re-verify a receipt that is already committed:

```yaml
      - uses: ChelseaKR/obligation-receipts@v0.1.0
        with:
          mode: verify
          receipt: acceptance/receipt.json
```

### Inputs

| Input | Default | Notes |
|---|---|---|
| `mode` | `evaluate` | `evaluate` a manifest, or `verify` an existing receipt. |
| `manifest` | — | Required when `mode` is `evaluate`. |
| `evidence-root` | — | Required when `mode` is `evaluate`. |
| `receipt` | `receipt.json` | Written when evaluating; read when verifying. |
| `fail-on` | `rejected` | `rejected`, `incomplete`, or `any`. |
| `version` | `v0.1.0` | Git ref of this repository to install. |
| `upload-receipt` | `true` | Upload the receipt as an artifact (evaluate only). |

### Outputs

`exit-code` and `status` (`ok`, `rejected`, `input_error`, `not_observed`,
`review_required`), so a later step can branch on the outcome without re-running
anything.

## Pinning

`version` takes a git ref. Pin to a tag or a full commit SHA; a branch name
means a later push changes what your CI runs. The action pins every third-party
action it uses to a commit SHA, and `tests/test_supply_chain.py` reads
`action.yml` as well as `.github/workflows/`, so an unpinned reference added
here fails this repository's own build.

## Pre-commit hook

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/ChelseaKR/obligation-receipts
    rev: v0.1.0
    hooks:
      - id: obligation-receipts-validate
```

It runs `obligation-receipts validate` on every changed `obligations.toml`.
`validate` loads the manifest, re-hashes its declared source, and refuses an
authoring defect — a malformed RFC 6901 pointer, an unknown operator, a
classification that does not match its evidence kind — at load time, before it
can reach an evaluation and be reported as an observed failure. It is fast,
offline, needs no evidence root, and evaluates nothing.

`validate` accepts several manifests in one invocation, because that is how
pre-commit passes a batch of changed files.

## What neither of these does

Neither publishes anything. This repository has no publication authority
(WVR-009), the action installs from a git ref rather than a package index, and
no step here creates a release or a tag.
