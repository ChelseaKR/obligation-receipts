# ADR 0000: Record architecture decisions

**Status:** Accepted
**Date:** 2026-07-22
**Decider:** repository owner

## Context

Obligation Receipts' human-approval and evidence boundaries are product
behavior. Changes to interpretation, executable inputs, receipt semantics,
signer authority, or confidential-data posture require durable reasoning.

## Decision

Number consequential decisions sequentially and commit them under
`docs/decisions/`. Each record states context, considered options, the decision,
consequences, and any evidence gate that would cause reconsideration.

## Consequences

- Existing decision 0001 remains the authority for a human-approved manifest.
- Model-assisted mapping, production governance, adapters, or signing require a
  new accepted decision.
- Small reversible implementation choices do not require an ADR.
