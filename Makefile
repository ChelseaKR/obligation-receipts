.PHONY: install format lint type test verify package-check benchmark demo

install:
	uv sync

format:
	uv run ruff format .

lint:
	uv run ruff format --check .
	uv run ruff check .

type:
	uv run mypy

test:
	uv run pytest

verify: lint type test

package-check:
	uv build
	uv run python scripts/check_wheel.py dist

benchmark:
	uv run python scripts/benchmark_m0.py

demo:
	uv run obligation-receipts validate examples/accessibility-acceptance/obligations.toml
	uv run obligation-receipts evaluate examples/accessibility-acceptance/obligations.toml --evidence-root examples/accessibility-acceptance/evidence --out examples/accessibility-acceptance/out/receipt.json
	uv run obligation-receipts verify examples/accessibility-acceptance/out/receipt.json --manifest examples/accessibility-acceptance/obligations.toml --evidence-root examples/accessibility-acceptance/evidence
