.PHONY: install lock-check format lint type test verify package-check benchmark demo

# THE LOCKFILE IS CHECKED BEFORE ANYTHING RUNS, AND EVERY INVOCATION RE-ASSERTS IT.
#
# A bare `uv run` implicitly syncs first, and an implicit sync re-resolves and
# SILENTLY REWRITES uv.lock when it disagrees with pyproject.toml. Measured on
# this repository: bump `project.version` in pyproject.toml, run `make lint`,
# and it prints "All checks passed!" while uv.lock changes underneath it
# (sha256 279d6a55... -> 52052369...). The gate reported green having quietly
# repaired the very drift a lockfile exists to make visible, and the rewrite
# landed in the working tree where the next `git add` would sweep it up.
#
# `uv sync --frozen` -- what CI ran, and what `install` used to approximate --
# CANNOT be the drift gate. `--frozen` means "install exactly what uv.lock
# records and never re-resolve"; it never reads pyproject.toml, so by
# construction it cannot notice the two disagree. On the drifted pair above it
# exits 0, and it installed obligation-receipts==0.1.1 -- the perturbed
# pyproject version -- from a lock that still recorded 0.1.0. The one change
# guaranteed to desynchronise the lock, a release, is the one change --frozen
# is structurally blind to.
#
# `uv lock --check` re-resolves against pyproject.toml and exits non-zero when
# the lock no longer satisfies it. That is the gate, and it runs FIRST in
# `verify`, before any target that could rewrite what it checks.
#
# `--locked` on every `uv run` is the belt to that brace: it makes the same
# assertion at each invocation and refuses to run rather than relock, so no
# gate can execute against a drifted lock even when it is invoked on its own.
# `tests/test_toolchain_lock.py` holds this file and .github/workflows/ci.yml
# to both rules.

install:
	uv lock --check
	uv sync --locked

lock-check:
	uv lock --check

format:
	uv run --locked ruff format .

lint:
	uv run --locked ruff format --check .
	uv run --locked ruff check .

type:
	uv run --locked mypy

test:
	uv run --locked pytest

verify: lock-check lint type test

package-check:
	uv build
	uv run --locked python scripts/check_wheel.py dist

benchmark:
	uv run --locked python scripts/benchmark_m0.py

demo:
	uv run --locked obligation-receipts validate examples/accessibility-acceptance/obligations.toml
	uv run --locked obligation-receipts evaluate examples/accessibility-acceptance/obligations.toml --evidence-root examples/accessibility-acceptance/evidence --out examples/accessibility-acceptance/out/receipt.json
	uv run --locked obligation-receipts verify examples/accessibility-acceptance/out/receipt.json --manifest examples/accessibility-acceptance/obligations.toml --evidence-root examples/accessibility-acceptance/evidence
