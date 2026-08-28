import re
from datetime import date
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


# The canonical fifteen, from DOCUMENTATION-STANDARD section 5. Held here rather
# than derived from the README, because a list derived from the document under
# test would agree with any README at all.
_CANONICAL_STANDARDS = (
    "Responsible-Tech Framework",
    "Code Quality",
    "Security & Supply-Chain",
    "CI/CD",
    "Release & Versioning",
    "Observability",
    "Performance",
    "Accessibility",
    "Internationalization",
    "AI Evaluation",
    "Documentation",
    "Quality & Metrics",
    "AI Development Measurement",
    "Incident Response",
    "Data Governance",
)


def _table_cells(line: str) -> list[str] | None:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return None
    return [cell.replace(r"\|", "|").strip() for cell in re.split(r"(?<!\\)\|", stripped[1:-1])]


def _is_conformance_header(header: list[str] | None, delimiter: list[str] | None) -> bool:
    """Match the checker's own header rule: `Standard`, then a column naming a state."""
    if header is None or delimiter is None or len(header) < 2:
        return False
    if len(header) != len(delimiter) or header[0].casefold() != "standard":
        return False
    if not any("state" in cell.casefold() for cell in header[1:]):
        return False
    return all(re.fullmatch(r":?-{3,}:?", cell) for cell in delimiter)


def _conformance_rows() -> list[list[str]]:
    """Find the Standards Conformance table the way the portfolio checker does.

    The checker only recognizes a table whose first column header is `Standard`
    and whose second contains `state`. A header of `| Standard | M0 status |`
    was skipped entirely, so DOC-11, DOC-12, and DOC-13 went unevaluated and
    every row could have been blank without anything noticing (#14).

    Raises rather than returning an empty list: a table this function cannot
    find must fail a test loudly, never yield zero rows for a caller to iterate
    over and pass.
    """
    section = re.search(
        r"^##[ \t]+Standards Conformance[ \t]*\n(.*?)(?=^##[ \t]+|\Z)",
        _readme(),
        re.I | re.M | re.S,
    )
    if section is None:
        raise AssertionError("README has no 'Standards Conformance' section")
    lines = section.group(1).splitlines()
    starts = [
        index + 2
        for index in range(len(lines) - 1)
        if _is_conformance_header(_table_cells(lines[index]), _table_cells(lines[index + 1]))
    ]
    if len(starts) != 1:
        raise AssertionError(
            f"expected exactly one conformance table the checker can read, found {len(starts)}; "
            "the header must be `| Standard | State |`"
        )
    rows = []
    for line in lines[starts[0] :]:
        cells = _table_cells(line)
        if cells is None:
            break
        rows.append(cells)
    if not rows:
        raise AssertionError("the conformance table has a header but no rows")
    return rows


def test_conformance_table_is_readable_by_the_portfolio_checker() -> None:
    assert len(_conformance_rows()) == len(_CANONICAL_STANDARDS)


def test_conformance_table_declares_every_canonical_standard_exactly_once() -> None:
    labels = [row[0] for row in _conformance_rows()]
    assert sorted(labels) == sorted(_CANONICAL_STANDARDS), (
        "conformance rows do not match the canonical fifteen: "
        f"missing {sorted(set(_CANONICAL_STANDARDS) - set(labels))}, "
        f"unexpected {sorted(set(labels) - set(_CANONICAL_STANDARDS))}"
    )
    assert len(labels) == len(set(labels)), "a standard is declared more than once"


def test_every_conformance_state_is_a_real_declaration() -> None:
    """A state must commit to `Applies` or a reasoned `N/A`, and track its gaps."""
    problems: list[str] = []
    for row in _conformance_rows():
        standard = row[0]
        state = " | ".join(row[1:]).strip()
        if not state:
            problems.append(f"{standard}: blank state")
            continue
        if not re.match(r"^(?:Applies|N/A)(?:\s|$|[:(—-])", state):
            problems.append(f"{standard}: state does not begin with Applies or N/A: {state!r}")
            continue
        if re.search(r"\bN/A\b", state) and not re.search(
            r"N/A\s*(?:(?:[—-]|:)\s*\S|\([^\s)][^)]*\))", state
        ):
            problems.append(f"{standard}: declares N/A without a reason")
        if re.search(r"\bgap tracked\b", state, re.I) and not re.search(
            r"\bgap tracked in\s+(?:#\d+\b|\[#\d+\]\([^)]+\))", state, re.I
        ):
            problems.append(f"{standard}: claims a tracked gap without naming an issue")
    assert not problems, "\n".join(problems)


_WAIVERS = Path(__file__).parents[1] / "waivers.yml"
_REQUIRED_WAIVER_FIELDS = ("id", "control", "repo", "kind", "reason", "owner", "granted", "expires")
_ALLOWED_WAIVER_KINDS = {"semgrep", "vex", "pa11y", "na-in-flight", "other"}


def _waiver_entries() -> list[dict[str, str]]:
    """Parse `waivers.yml` without a YAML dependency.

    The runtime has no third-party dependencies and the dev group has no YAML
    parser, so the registry is read structurally. The file is a fixed, flat
    shape defined by STANDARDS/WAIVERS-SCHEMA.md version 1.
    """
    entries: list[dict[str, str]] = []
    for line in _WAIVERS.read_text(encoding="utf-8").splitlines():
        if re.match(r"^\s*-\s+id:\s*\S", line):
            entries.append({})
        match = re.match(r"^\s*(?:-\s+)?([a-z_]+):\s*(.*)$", line)
        if match is None or not entries:
            continue
        key, value = match.group(1), match.group(2).strip()
        if key in _REQUIRED_WAIVER_FIELDS or key == "link":
            entries[-1][key] = value
    return entries


def test_waiver_registry_is_complete_and_unexpired() -> None:
    """Every escape hatch is owned, reasoned, and dated, and no expiry has passed.

    Deliberately time-sensitive. A mandatory expiry that never fires is how a
    binding gate decays back into an aspiration; when this test goes red the
    waiver is due for a decision, which is the mechanism working.
    """
    entries = _waiver_entries()
    assert entries, "waivers.yml declares no waivers; delete the file or record one"
    problems: list[str] = []
    identifiers = [entry.get("id", "") for entry in entries]
    if len(identifiers) != len(set(identifiers)):
        problems.append(f"duplicate waiver ids: {identifiers}")
    for entry in entries:
        name = entry.get("id", "<unidentified>")
        for field in _REQUIRED_WAIVER_FIELDS:
            if not entry.get(field):
                problems.append(f"{name}: missing {field}")
        if entry.get("kind") not in _ALLOWED_WAIVER_KINDS:
            problems.append(f"{name}: kind {entry.get('kind')!r} is outside the allowed set")
        expires = entry.get("expires", "")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", expires):
            problems.append(f"{name}: expires {expires!r} is not YYYY-MM-DD")
        elif date.fromisoformat(expires) < date.today():
            problems.append(f"{name}: expired on {expires} and must be renewed or retired")
    assert not problems, "\n".join(problems)


def test_every_waiver_names_a_standards_control_and_this_repo() -> None:
    for entry in _waiver_entries():
        assert re.fullmatch(r"[A-Z]+-\d+", entry.get("control", "")), (
            f"{entry.get('id')}: control {entry.get('control')!r} is not a PREFIX-NN control id"
        )
        assert entry.get("repo") == "obligation-receipts", (
            f"{entry.get('id')}: waiver in this repo names repo {entry.get('repo')!r}"
        )
