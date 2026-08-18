from pathlib import Path

from obligation_receipts.exit_codes import INPUT_ERROR, evaluation_exit_code
from obligation_receipts.models import OverallStatus


def _readme() -> str:
    return (Path(__file__).parents[1] / "README.md").read_text(encoding="utf-8")


def _documented_evaluate_codes() -> dict[str, int]:
    """Read the README's per-command exit-code row for `evaluate`."""
    row = next(line for line in _readme().splitlines() if line.startswith("| `evaluate` |"))
    cells = [cell.strip() for cell in row.strip().strip("|").split("|")][1:]
    columns = (0, 1, 3, 4)
    assert len(cells) == len(columns), "the evaluate row must cover every documented code"
    return {cell: code for cell, code in zip(cells, columns, strict=True)}


def test_readme_documents_the_exit_code_the_cli_actually_returns() -> None:
    documented = _documented_evaluate_codes()
    for status in OverallStatus:
        placed = [code for cell, code in documented.items() if f"`{status.value}`" in cell]
        assert placed == [evaluation_exit_code(status)], (
            f"README places {status.value} at {placed}, "
            f"but evaluate returns {evaluation_exit_code(status)}"
        )


def test_readme_keeps_the_input_error_code_reserved() -> None:
    assert "Code 2 is reserved" in _readme()
    assert INPUT_ERROR not in set(_documented_evaluate_codes().values())
    assert INPUT_ERROR not in {evaluation_exit_code(status) for status in OverallStatus}


def test_security_claims_match_current_bounds_bindings_and_trust_scope() -> None:
    root = Path(__file__).parents[1]
    readme = (root / "README.md").read_text(encoding="utf-8")
    security = (root / "SECURITY.md").read_text(encoding="utf-8")
    threat_model = (root / "docs/THREAT-MODEL.md").read_text(encoding="utf-8")

    assert "Contract-source hashing is capped at 16 MiB" in readme
    assert "manifests, JSON evidence, plans,\n  and receipts are capped at 2 MiB" in readme
    assert "exact evidence ID" in security
    assert "Special files are\nopened nonblocking" in security
    assert "replaceable parent directories are not a hardened multi-user sandbox" in threat_model
