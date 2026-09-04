# Contributing

Before proposing code, read `AGENTS.md`, the PRD, and the threat model.

```sh
make install
make verify
make package-check
make demo
```

`make verify` is the merge-blocking gate, in this order: `uv lock --check`,
`ruff format --check`, `ruff check`, strict `mypy`, and `pytest` with a 90%
branch-coverage floor.

`uv lock --check` runs first and is not optional. A bare `uv run` syncs
implicitly, and an implicit sync silently rewrites `uv.lock` when it disagrees
with `pyproject.toml` — so any gate invoked before the lockfile assertion can
repair the drift it exists to expose and still report green. The `Makefile`
records the measurement; `tests/test_toolchain_lock.py` holds the `Makefile` and
`ci.yml` to it.

The coverage floor is set once, in `pyproject.toml` (`--cov-fail-under` and
`[tool.coverage.report] fail_under`); every document that states it, this one
included, is checked against that setting by `tests/test_docs.py`. Do not lower
it.

Every parser or trust-boundary change needs a negative test. Do not add contract
interpretation, arbitrary command execution, network fetching, or a model SDK
without an accepted ADR and an explicit product-scope decision.
