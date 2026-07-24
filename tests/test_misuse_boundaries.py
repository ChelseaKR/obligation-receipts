import ast
from pathlib import Path


def test_runtime_has_no_network_process_or_dynamic_execution_surface() -> None:
    source_root = Path(__file__).parents[1] / "src/obligation_receipts"
    forbidden_imports = {
        "http",
        "requests",
        "socket",
        "subprocess",
        "urllib",
    }
    forbidden_calls = {"__import__", "compile", "eval", "exec"}
    for path in source_root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all(
                    alias.name.split(".")[0] not in forbidden_imports for alias in node.names
                )
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                assert node.module.split(".")[0] not in forbidden_imports
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in forbidden_calls


def test_discovery_boundary_excludes_signing_adapters_and_legal_interpretation() -> None:
    root = Path(__file__).parents[1]
    agents = (root / "AGENTS.md").read_text(encoding="utf-8")
    readme = (root / "README.md").read_text(encoding="utf-8")
    normalized_agents = " ".join(agents.split())
    assert "does not write contracts, interpret law" in normalized_agents
    assert "No contract drafting, clause extraction, or legal interpretation." in readme
    assert "Future cryptographic signing" in (root / "docs/ARCHITECTURE.md").read_text(
        encoding="utf-8"
    )
    assert not any(
        path.name in {"adapters.py", "signing.py", "legal.py"}
        for path in (root / "src/obligation_receipts").glob("*.py")
    )
