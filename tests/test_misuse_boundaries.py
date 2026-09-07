import ast
import re
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


def test_every_module_that_names_the_artifact_cap_names_the_same_number() -> None:
    """The evaluator's artifact cap is copied into two modules and held by nothing.

    `evaluator._MAX_ARTIFACT_BYTES` decides what `evaluate` can read.
    `inventory.MAX_ARTIFACT_BYTES` and `progress.MAX_ARTIFACT_BYTES` are separate
    literals whose comments both say they are "the evaluator's artifact cap", and the
    honesty claim of both modules rests on that being true: progress states that
    "'present' here means 'present and usable by `evaluate`' rather than 'a file of
    some size exists'", and inventory says an oversized file "must be reported as
    unreadable rather than as a present artifact the evaluator would later refuse".

    Nothing compared them. Measured on this tree: tightening
    `evaluator._MAX_ARTIFACT_BYTES` to 256 KiB alone left the whole suite green at
    exit 0, and a 1 MiB artifact then read as present in both inventory and progress
    while `evaluate` refused it -- the two commands written to say what `evaluate`
    would do, disagreeing with `evaluate`. Each module's own tests use its own
    constant, so they move together with whichever copy they were written against.

    So the copies are compared here, by reading every literal in the package rather
    than the three that exist today: a fourth copy added later is covered without
    anyone remembering to add it.
    """
    import importlib

    source_root = Path(__file__).parents[1] / "src/obligation_receipts"
    found: dict[str, int] = {}
    for path in sorted(source_root.glob("*.py")):
        if path.stem == "__init__":
            continue
        module = importlib.import_module(f"obligation_receipts.{path.stem}")
        for name, value in vars(module).items():
            if not name.lstrip("_").startswith("MAX_ARTIFACT_BYTES"):
                continue
            assert isinstance(value, int), f"{path.name}:{name} is not an integer byte count"
            found[f"{path.name}:{name}"] = value

    assert len(found) >= 3, (
        "the artifact cap is declared in evaluator, inventory and progress; "
        f"this scan found {sorted(found)}. If a declaration moved, point this test at "
        "wherever it went rather than deleting it."
    )
    assert len(set(found.values())) == 1, (
        "the modules disagree about the artifact cap: "
        + ", ".join(f"{where} = {value}" for where, value in sorted(found.items()))
        + ". `inventory` and `progress` report what `evaluate` would be able to read, "
        "so a file between the smallest and largest of these reads as present in one "
        "command and is refused by another."
    )


def test_the_accepted_assertion_vocabulary_is_the_implemented_one() -> None:
    """Two copies of the operator set, and a third in an if-chain, held by nothing.

    `manifest._OPERATORS` decided what a manifest may declare. `plan._OPERATORS`
    was an identical literal deciding what an evidence plan may carry.
    `evaluator._compare` was an if-chain, so the *implemented* set existed only
    in control flow -- and its trailing `return False` answered an operator
    nobody had implemented.

    Nothing compared them, and the consequence is not a crash. Measured on this
    tree before the change: adding one operator to `manifest._OPERATORS` and to
    the example manifest produced `overall_status: rejected`, with the evidence
    result `fail` and the detail "assertion /summary/critical_violations matches
    did not pass". A supplier is told in a receipt that their evidence failed
    when nothing was compared to anything -- a check that could not run,
    published as an observed failure.

    So the vocabulary is now one frozenset in `models.py` that both loaders
    import, and the implemented set is derived from the dispatch that answers
    each operator. Adding an operator to the vocabulary without implementing it
    fails here rather than in a counterparty's receipt.
    """
    from obligation_receipts.evaluator import IMPLEMENTED_OPERATORS
    from obligation_receipts.models import ASSERTION_OPERATORS

    assert ASSERTION_OPERATORS == IMPLEMENTED_OPERATORS, (
        "the accepted and implemented operator sets differ: accepted-only "
        f"{sorted(ASSERTION_OPERATORS - IMPLEMENTED_OPERATORS)}, implemented-only "
        f"{sorted(IMPLEMENTED_OPERATORS - ASSERTION_OPERATORS)}. An accepted operator with "
        "no implementation is recorded as an observed `fail` against a supplier."
    )


def test_no_module_keeps_its_own_copy_of_the_operator_vocabulary() -> None:
    """The set literal must not come back.

    The test above compares two names; it cannot see a third module that
    re-declares the same strings and drifts. This reads the source for the
    literal itself, the way the artifact-cap test reads every module's constant.
    """
    root = Path(__file__).parents[1] / "src/obligation_receipts"
    # A *set* literal naming the operators, not a dict keyed by them: excluding
    # any brace group containing a colon is what tells the re-declared
    # vocabulary apart from `evaluator._ORDERING`, which is the implementation
    # the first test already holds equal to it. Without that exclusion this
    # fires on the fix itself, which is a gate that cannot be satisfied.
    literal = re.compile(r"=\s*(?:frozenset\()?\{[^}:]*\"gte\"[^}:]*\}")
    offenders = [
        path.name
        for path in sorted(root.glob("*.py"))
        if path.name != "models.py" and literal.search(path.read_text(encoding="utf-8"))
    ]
    assert not offenders, (
        f"{offenders} declare their own operator set; import "
        "`models.ASSERTION_OPERATORS` instead so there is one vocabulary"
    )
