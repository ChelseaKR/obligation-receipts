import re
from datetime import date
from pathlib import Path

from obligation_receipts.exit_codes import (
    INPUT_ERROR,
    NOT_OBSERVED,
    evaluation_exit_code,
    evidence_exit_code,
)
from obligation_receipts.manifest import load_manifest
from obligation_receipts.models import EvidenceKind, OverallStatus, ResultStatus
from obligation_receipts.single_check import check_declared_evidence, evidence_check_exit_code


def _readme() -> str:
    return (Path(__file__).parents[1] / "README.md").read_text(encoding="utf-8")


def _documented_row_codes(command: str) -> dict[str, int]:
    """Read one per-command exit-code row out of the README's table."""
    opening = f"| `{command}` |"
    rows = [line for line in _readme().splitlines() if line.startswith(opening)]
    assert len(rows) == 1, f"expected exactly one `{command}` exit-code row, found {len(rows)}"
    cells = [cell.strip() for cell in rows[0].strip().strip("|").split("|")][1:]
    columns = (0, 1, 3, 4)
    assert len(cells) == len(columns), f"the {command} row must cover every documented code"
    return {cell: code for cell, code in zip(cells, columns, strict=True)}


def _documented_evaluate_codes() -> dict[str, int]:
    """Read the README's per-command exit-code row for `evaluate`."""
    return _documented_row_codes("evaluate")


def test_readme_documents_the_exit_code_the_cli_actually_returns() -> None:
    documented = _documented_evaluate_codes()
    for status in OverallStatus:
        placed = [code for cell, code in documented.items() if f"`{status.value}`" in cell]
        assert placed == [evaluation_exit_code(status)], (
            f"README places {status.value} at {placed}, "
            f"but evaluate returns {evaluation_exit_code(status)}"
        )


def test_readme_documents_the_exit_code_check_evidence_actually_returns() -> None:
    """`check-evidence` is the only command that reports a per-item state.

    `unverifiable` is deliberately absent from the row as well as from
    `evidence_exit_code`: it belongs to an obligation that declares no evidence,
    so no evidence item can carry it.
    """
    documented = _documented_row_codes("check-evidence")
    for status in ResultStatus:
        placed = [code for cell, code in documented.items() if f"`{status.value}`" in cell]
        if status is ResultStatus.UNVERIFIABLE:
            assert placed == [], f"the check-evidence row places {status.value} at {placed}"
            continue
        assert placed == [evidence_exit_code(status)], (
            f"README places {status.value} at {placed}, "
            f"but check-evidence returns {evidence_exit_code(status)}"
        )


def test_readme_scopes_the_check_evidence_missing_code_to_the_kind_that_reaches_it(
    copied_example: Path,
) -> None:
    """The code-3 cell said "`missing` or malformed", and both halves over-claimed.

    Measured here rather than described: an attestation that is absent or
    malformed is `review_required` and exits 4, so only `json_assertion`
    evidence can reach 3 at all. `docs/SINGLE-EVIDENCE-CHECK.md` already said
    so; the README was the outlier, and a row that names the wrong code is
    exactly the pipeline defect the shared exit-code contract exists to
    prevent.
    """
    manifest = load_manifest(copied_example / "obligations.toml")
    evidence_root = copied_example / "evidence"
    selected = {
        evidence.kind: (evidence.evidence_id, evidence_root / evidence.path)
        for obligation in manifest.obligations
        for evidence in obligation.evidence
    }
    assert set(selected) == set(EvidenceKind), "the example no longer spans every evidence kind"

    reaching_not_observed = set()
    for kind, (evidence_id, artifact) in selected.items():
        for make_unusable in ("absent", "malformed"):
            if make_unusable == "absent":
                artifact.unlink()
            else:
                artifact.write_text("{", encoding="utf-8")
            document = check_declared_evidence(manifest, evidence_id, evidence_root)
            if evidence_check_exit_code(document) == NOT_OBSERVED:
                reaching_not_observed.add(kind)
    assert reaching_not_observed == {EvidenceKind.JSON_ASSERTION}, (
        f"exit {NOT_OBSERVED} is reachable from {sorted(reaching_not_observed)}"
    )

    documented = _documented_row_codes("check-evidence")
    by_code = {code: cell for cell, code in documented.items()}
    assert EvidenceKind.JSON_ASSERTION.value in by_code[NOT_OBSERVED], (
        "the code-3 cell must name the one evidence kind that can reach it"
    )
    assert "attestation" in by_code[evidence_exit_code(ResultStatus.REVIEW_REQUIRED)]


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


_ROOT = Path(__file__).parents[1]
_CI = _ROOT / ".github/workflows/ci.yml"
_MAKEFILE = _ROOT / "Makefile"
_CONTRIBUTING = _ROOT / "CONTRIBUTING.md"
_ROADMAP = _ROOT / "docs/ROADMAP.md"
_ARCHITECTURE = _ROOT / "docs/ARCHITECTURE.md"
_SOURCE_PACKAGE = _ROOT / "src/obligation_receipts"
_PYPROJECT = _ROOT / "pyproject.toml"
_PLANS = _ROOT / "docs/plans"

# Enough English to name a count in prose. An unlisted count fails the lookup
# rather than passing with the wrong word.
_NUMBER_WORDS = {
    2: "two",
    3: "three",
    4: "four",
    5: "five",
    6: "six",
    7: "seven",
    8: "eight",
    9: "nine",
    10: "ten",
    11: "eleven",
    12: "twelve",
    13: "thirteen",
    14: "fourteen",
    15: "fifteen",
    16: "sixteen",
}


def test_every_shipped_subcommand_appears_in_the_documented_exit_code_table() -> None:
    """A command that ships without a documented exit code is an undocumented gate.

    `check-evidence` and the shared exit-code contract shipped, acquired a
    format document and a Breaking changelog entry, and appeared in neither
    requirement ledger. The exit-code table is the one place that must name
    every command, so it is read against the subparsers `cli.py` registers.
    """
    source = (_SOURCE_PACKAGE / "cli.py").read_text(encoding="utf-8")
    commands = re.findall(r"add_parser\(\s*\"([a-z][a-z-]*)\"", source, re.S)
    assert commands, "no subparsers parsed out of cli.py; the reader is broken, not the file"
    table = re.search(
        r"^\| Command \| 0 \| 1 \| 3 \| 4 \|\n(?:\|.*\n)+",
        _readme(),
        re.M,
    )
    if table is None:
        raise AssertionError("README has no per-command exit-code table")
    missing = [command for command in commands if f"`{command}`" not in table.group(0)]
    assert not missing, f"the exit-code table does not name the shipped commands {missing}"


def _verify_gate_commands() -> list[str]:
    """The commands `make verify` runs, in order, read out of the `Makefile`."""
    text = _MAKEFILE.read_text(encoding="utf-8")
    prerequisites = re.search(r"^verify:(.*)$", text, re.M)
    if prerequisites is None:
        raise AssertionError("the Makefile has no `verify` target")
    commands: list[str] = []
    for target in prerequisites.group(1).split():
        recipe = re.search(rf"^{re.escape(target)}:.*\n((?:\t.*\n)+)", text, re.M)
        if recipe is None:
            raise AssertionError(f"`verify` requires {target}, which has no recipe")
        for line in recipe.group(1).splitlines():
            command = line.strip().removeprefix("uv run --locked ")
            commands.append(command.removesuffix(" .").strip())
    return commands


def test_every_description_of_the_merge_gate_lists_the_steps_it_actually_runs() -> None:
    """`make verify` gained a first step that no description of it mentioned.

    `uv lock --check` became the gate's first prerequisite in #40, and it is
    load-bearing: a bare `uv run` syncs implicitly and rewrites `uv.lock` when
    it disagrees with `pyproject.toml`, so a gate that runs before the lockfile
    assertion can repair the drift it exists to expose and still report green.
    `CONTRIBUTING.md` and the README both went on enumerating the gate as
    "Ruff, strict mypy, pytest". The enumeration is now read out of the
    `Makefile`, in order.
    """
    commands = _verify_gate_commands()
    assert commands[0] == "uv lock --check", (
        f"the lockfile assertion is no longer `verify`'s first step: {commands}"
    )
    contributing = _CONTRIBUTING.read_text(encoding="utf-8")
    positions = []
    for command in commands:
        index = contributing.find(f"`{command}`")
        assert index != -1, f"CONTRIBUTING.md does not name the gate step `{command}`"
        positions.append(index)
    assert positions == sorted(positions), (
        f"CONTRIBUTING.md lists the gate steps out of the order `make verify` runs them: {commands}"
    )
    code_quality = " | ".join(
        next(row for row in _conformance_rows() if row[0] == "Code Quality")[1:]
    )
    assert "`uv lock --check`" in code_quality, "the Code Quality row omits the lockfile gate"
    provenance = re.search(r"^## Provenance[ \t]*\n(.*?)(?=^##[ \t]+|\Z)", _readme(), re.M | re.S)
    if provenance is None:
        raise AssertionError("README has no 'Provenance' section")
    assert "`uv lock --check`" in provenance.group(1), (
        "the README's Provenance paragraph describes a gate that is missing its first step"
    )


def test_the_architecture_component_list_names_every_runtime_module() -> None:
    """A component list that reads as exhaustive has to be exhaustive.

    `canonical.py` and `exit_codes.py` were both absent from it -- the seam
    every digest passes through and the contract every command's exit code
    comes from -- while the surrounding prose described the list as the
    system's components. The list now states its own count, and both the count
    and the membership are read off the source tree.
    """
    modules = sorted(path.name for path in _SOURCE_PACKAGE.glob("*.py"))
    section = re.search(
        r"^##[ \t]+Components[ \t]*\n(.*?)(?=^##[ \t]+|\Z)",
        _ARCHITECTURE.read_text(encoding="utf-8"),
        re.M | re.S,
    )
    if section is None:
        raise AssertionError("ARCHITECTURE.md has no 'Components' section")
    named = sorted(set(re.findall(r"^- `([a-z_]+\.py)`", section.group(1), re.M)))
    assert named == modules, (
        f"the component list omits {sorted(set(modules) - set(named))} "
        f"and invents {sorted(set(named) - set(modules))}"
    )
    assert f"All {_NUMBER_WORDS[len(modules)]} modules" in section.group(1), (
        f"the section does not say it covers all {len(modules)} modules"
    )


def _job_name_pattern(job: str) -> str:
    return rf"^  {re.escape(job)}:\n(?:    .*\n)*?    name:"


def _ci_job_ids() -> list[str]:
    """Top-level job ids in `ci.yml`, read structurally.

    The dev group has no YAML parser and the runtime has no dependencies at
    all, so the workflow is read the way `waivers.yml` is. Job ids sit at two
    spaces under `jobs:`; everything inside a job sits at four or more. No job
    sets `name:`, so the id is also the required-status-check context.
    """
    section = re.search(r"^jobs:\n(.*)\Z", _CI.read_text(encoding="utf-8"), re.M | re.S)
    if section is None:
        raise AssertionError("ci.yml has no top-level `jobs:` block")
    ids = re.findall(r"^  ([a-z][a-z0-9-]*):[ \t]*$", section.group(1), re.M)
    if not ids:
        raise AssertionError("no job ids parsed out of ci.yml; the reader is broken, not the file")
    if any(re.search(_job_name_pattern(job), _CI.read_text(encoding="utf-8"), re.M) for job in ids):
        raise AssertionError("a job sets `name:`, so its check context is no longer its id")
    return ids


def _cicd_state() -> str:
    row = next(row for row in _conformance_rows() if row[0] == "CI/CD")
    return " | ".join(row[1:])


def _roadmap_bullet(opening: str) -> str:
    """One roadmap checklist item, rejoined across the lines it wraps onto."""
    lines = _ROADMAP.read_text(encoding="utf-8").splitlines()
    starts = [index for index, line in enumerate(lines) if line.startswith(f"- [x] {opening}")]
    if len(starts) != 1:
        raise AssertionError(
            f"expected exactly one roadmap item opening {opening!r}, found {len(starts)}"
        )
    collected = [lines[starts[0]]]
    for line in lines[starts[0] + 1 :]:
        if not line.startswith("      "):
            break
        collected.append(line.strip())
    return " ".join(collected)


def test_the_documented_ci_triggers_are_the_triggers_the_workflow_has() -> None:
    """The claim the documents make about hosted CI, checked against `ci.yml`.

    This is the checkable half of what `since 2026-08-05` used to assert. The
    triggers are in the workflow; the date was in nobody's file.
    """
    events = re.search(r"^on:\n((?:  \S.*\n|    .*\n)+)", _CI.read_text(encoding="utf-8"), re.M)
    if events is None:
        raise AssertionError("ci.yml has no top-level `on:` block")
    triggers = set(re.findall(r"^  ([a-z_]+):", events.group(1), re.M))
    assert triggers == {"push", "pull_request"}, f"ci.yml triggers on {sorted(triggers)}"
    assert re.search(r"^  push:\n    branches: \[main\]$", _CI.read_text(encoding="utf-8"), re.M)
    state = _cicd_state()
    assert "`push`" in state and "`pull_request`" in state
    assert "push and pull request" in _roadmap_bullet("Hosted CI")


def test_the_hosted_ci_claim_carries_no_hand_typed_date() -> None:
    """A date typed into prose is a claim nothing checks, and this one was wrong.

    Both documents dated hosted CI to 2026-08-05. `.github/workflows/ci.yml`
    has carried `push` and `pull_request` since the repository's first commit,
    and no commit in this repository is dated 2026-08-05 at all. The triggers
    are derivable from the workflow, so the date was removed rather than
    corrected.
    """
    assert not re.search(r"\d{4}-\d{2}-\d{2}", _roadmap_bullet("Hosted CI"))
    for path in (_ROOT / "README.md", _ROADMAP):
        assert "2026-08-05" not in path.read_text(encoding="utf-8"), (
            f"{path.name} restates a date the repository has no commit for"
        )


def test_the_readme_names_every_ci_job_as_a_required_check() -> None:
    """`all six checks` has to keep meaning every job the workflow defines.

    A seventh job that nobody adds to the ruleset, or to this row, is exactly
    the failure #16 recorded: a check that runs, reports, and cannot block.
    """
    jobs = _ci_job_ids()
    state = _cicd_state()
    assert f"all {_NUMBER_WORDS[len(jobs)]} checks" in state, (
        f"ci.yml defines {len(jobs)} jobs {jobs}, which the CI/CD row does not say"
    )
    missing = [job for job in jobs if f"`{job}`" not in state]
    assert not missing, f"the CI/CD row does not name the required checks {missing}"


def test_the_ruleset_claim_does_not_backdate_the_requirement_to_the_rulesets_creation() -> None:
    """The ruleset predates what it requires, and the row has to say so.

    `protect-main` has been active since 2026-08-07, but it required only
    `verify` until the change the CHANGELOG records under "Require every CI
    check"; the other five jobs reported without being able to block. Dating
    the six-check requirement to the ruleset's creation claimed roughly three
    weeks of blocking that did not happen.
    """
    changelog = (_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "Require every CI check in the `protect-main` ruleset" in changelog
    for text in (_cicd_state(), _roadmap_bullet("`protect-main`")):
        assert "only `verify`" in text, "the row backdates the six-check requirement"


def _coverage_floor() -> int:
    """The one place the branch-coverage floor is configured."""
    text = _PYPROJECT.read_text(encoding="utf-8")
    addopts = re.search(r"^--cov-fail-under=(\d+)", text, re.M)
    report = re.search(r"^fail_under = (\d+)$", text, re.M)
    assert addopts is not None, "pyproject.toml sets no --cov-fail-under"
    assert report is not None, "pyproject.toml sets no [tool.coverage.report] fail_under"
    assert addopts.group(1) == report.group(1), "the two coverage floors in pyproject.toml disagree"
    return int(addopts.group(1))


_FLOOR_IN_PROSE = re.compile(
    r"(\d+)\s*%\s*branch[- ]coverage|branch[- ]coverage\s*(?:≥|>=|of)?\s*(\d+)\s*%",
    re.I,
)
_FLOOR_DOCUMENTS = ("AGENTS.md", "README.md", "CONTRIBUTING.md")


def test_every_document_stating_the_coverage_floor_states_the_configured_one() -> None:
    """The floor is counted from `pyproject.toml`, not typed into prose.

    `CONTRIBUTING.md` was cited as documenting the 90% floor while containing
    no percentage at all. It carries the floor now, and all three documents are
    read against the setting, so raising the floor without updating them is a
    failing test rather than a stale sentence.
    """
    floor = _coverage_floor()
    for name in _FLOOR_DOCUMENTS:
        text = (_ROOT / name).read_text(encoding="utf-8")
        stated = {int(a or b) for a, b in _FLOOR_IN_PROSE.findall(text)}
        assert stated, f"{name} states no branch-coverage floor; pyproject.toml sets {floor}%"
        assert stated == {floor}, (
            f"{name} states {sorted(stated)}% but pyproject.toml sets {floor}%"
        )


# A tracked plan may record what held while its pass ran; it may not claim, in
# the present tense, that it is not committed. The discriminator is tense, not
# vocabulary: "nothing was committed while it ran" is true and stays allowed,
# "Nothing is committed" is the false claim. Holding two literal strings caught
# only the two spellings that happened to exist, and "Nothing is committed;
# every change is in the working tree" walked past them.
_UNCOMMITTED_DENIALS = (
    # "Nothing is committed", "Nothing in this pass is committed",
    # "no change is committed".
    re.compile(r"\b(?:nothing|none|no\s+\w+)\b[^.;\n]{0,60}?\bis\s+(?:not\s+)?committed\b", re.I),
    # "is not committed", "are not committed".
    re.compile(r"\b(?:is|are)\s+not\s+committed\b", re.I),
    # "is uncommitted", "remains uncommitted", "stays uncommitted".
    re.compile(r"\b(?:is|are|remains?|stays?)\s+(?:still\s+)?uncommitted\b", re.I),
    # "every change is in the working tree".
    re.compile(
        r"\b(?:every|all|each)\b[^.;\n]{0,40}?\b(?:is|are)\s+in\s+the\s+working[ -]tree\b", re.I
    ),
    # "Working-tree only." as an assertion, but not "the pass was working-tree
    # only", which describes a past constraint rather than a present state.
    re.compile(r"(?<!was\s)(?<!were\s)\bworking[ -]tree\s+only\b", re.I),
)

_DENIALS_THIS_GUARD_MUST_CATCH = (
    "Working-tree only. Nothing in this pass is committed; the accountable maintainer",
    "Nothing is committed; every change is in the working tree.",
    "No change is committed yet.",
    "The plan remains uncommitted.",
    "This document is not committed.",
)

_TRUE_STATEMENTS_THIS_GUARD_MUST_ALLOW = (
    "The pass itself was working-tree only: nothing was committed while it ran,",
    "Nothing was committed while the pass ran; the work was merged to `main` afterwards.",
    "No commit, no push, no pull-request write, no index or HEAD movement.",
    "The work was merged to `main` in pull request #38, this file included.",
)


def test_the_uncommitted_denial_guard_rejects_the_family_and_not_the_record() -> None:
    """The guard has to separate a false present claim from a true past one.

    Both sentences contain the same words. Only one of them is a committed file
    saying it is not committed, and a guard that cannot tell them apart either
    misses the defect or forbids the correction.
    """
    for denial in _DENIALS_THIS_GUARD_MUST_CATCH:
        assert any(pattern.search(denial) for pattern in _UNCOMMITTED_DENIALS), (
            f"the guard does not catch {denial!r}"
        )
    for statement in _TRUE_STATEMENTS_THIS_GUARD_MUST_ALLOW:
        matched = [pattern.pattern for pattern in _UNCOMMITTED_DENIALS if pattern.search(statement)]
        assert not matched, f"the guard rejects the true statement {statement!r} via {matched}"


def test_a_committed_plan_does_not_present_itself_as_uncommitted() -> None:
    """`Nothing in this pass is committed` was written in a committed file.

    The plan under `docs/plans/` is tracked, and the pass it describes reached
    `main`. A record that denies its own existence is the one claim a reader
    can falsify just by reading it.
    """
    tracked = sorted(path for path in _PLANS.glob("*.md"))
    assert tracked, "docs/plans holds no plan; drop this guard or restore the file"
    for path in tracked:
        text = path.read_text(encoding="utf-8")
        for pattern in _UNCOMMITTED_DENIALS:
            found = pattern.search(text)
            if found is not None:
                raise AssertionError(f"{path.name} is committed and says {found.group(0)!r}")
