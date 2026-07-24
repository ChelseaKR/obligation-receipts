# ADR 0001: Require a human-approved manifest before evaluation

**Status:** Accepted
**Date:** 2026-07-22
**Decider:** Chelsea Kelly-Reif

## Context

The product eventually might help map prose requirements to evidence. Allowing
runtime extraction or model interpretation into the acceptance path would make
the most consequential and least measurable step implicit.

## Decision

M0 accepts only a strict, source-bound manifest authored or approved by an
accountable human. The evaluator cannot read a PDF, infer clause meaning, draft
criteria, or activate proposed mappings.

## Options considered

| Option | Complexity | Main risk |
|---|---|---|
| Human-approved manifest | Low | Manual setup and possible human error |
| Rules-based clause extraction | Medium | Brittle false certainty |
| LLM extraction and direct evaluation | High | Unreviewed interpretation controls acceptance |
| LLM draft with human activation | Medium | Appropriate future research seam |

## Consequences

- The core evaluation can be deterministic and independently tested.
- “Unverifiable” remains visible instead of being optimized away.
- M0 does not demonstrate document ingestion or mapping productivity.
- User research must determine whether manual mapping is tolerable.
- Any future model-assisted mapper is a drafting tool with its own eval and no
  activation authority.
