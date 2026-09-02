# Contributing

Before proposing code, read `AGENTS.md`, the PRD, and the threat model.

```sh
make install
make verify
make package-check
make demo
```

`make verify` is the merge-blocking gate: `ruff format --check`, `ruff check`,
strict `mypy`, and `pytest` with a 90% branch-coverage floor. That floor is set
once, in `pyproject.toml` (`--cov-fail-under` and `[tool.coverage.report]
fail_under`); every document that states it, this one included, is checked
against that setting by `tests/test_docs.py`. Do not lower it.

Every parser or trust-boundary change needs a negative test. Do not add contract
interpretation, arbitrary command execution, network fetching, or a model SDK
without an accepted ADR and an explicit product-scope decision.
