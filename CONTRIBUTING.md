# Contributing

Before proposing code, read `AGENTS.md`, the PRD, and the threat model.

```sh
make install
make verify
make package-check
make demo
```

Every parser or trust-boundary change needs a negative test. Do not add contract
interpretation, arbitrary command execution, network fetching, or a model SDK
without an accepted ADR and an explicit product-scope decision.
