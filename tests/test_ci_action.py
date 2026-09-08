"""The shipped CI action and pre-commit hook, checked as shapes.

Issue 61. The action is YAML executed by GitHub, not Python this suite can call,
so what is checkable here is its shape: that every input the documentation
promises exists, that the exit-code contract is mapped rather than collapsed,
and that code 2 is outside `fail-on`. The behaviour itself is exercised by the
`dogfood-action` job in `.github/workflows/ci.yml`, which runs the action in
this repository against this repository's own example on every pull request.

The one behaviour that IS callable is the CLI the action and the hook invoke,
so the exit codes they depend on are asserted against the real CLI.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

from obligation_receipts.cli import main
from obligation_receipts.exit_codes import INPUT_ERROR, OK

ROOT = Path(__file__).resolve().parents[1]
ACTION = ROOT / "action.yml"
HOOKS = ROOT / ".pre-commit-hooks.yaml"
DOCS = ROOT / "docs" / "CI-ACTION.md"
EXAMPLE = ROOT / "examples" / "accessibility-acceptance"


#: The action is read as text, not parsed as YAML. `tests/test_supply_chain.py`
#: reads workflows the same way, and this repository ships zero runtime
#: dependencies and keeps its dev set small -- adding PyYAML so a shape test
#: could use `safe_load` would be a poor trade for what these assertions need.
_ACTION_TEXT = ACTION.read_text(encoding="utf-8")


def _top_level_input_names() -> set[str]:
    """The `inputs:` keys, read from the action's indentation."""
    return _block_keys("inputs:")


def _block_keys(header: str) -> set[str]:
    lines = _ACTION_TEXT.splitlines()
    start = next(index for index, line in enumerate(lines) if line.rstrip() == header)
    keys: set[str] = set()
    for line in lines[start + 1 :]:
        if line.strip() and not line.startswith(" "):
            break
        match = re.fullmatch(r"  ([a-z][a-z0-9-]*):", line.rstrip())
        if match:
            keys.add(match.group(1))
    return keys


def _run_step_script() -> str:
    """The body of the `id: run` step, as shell text."""
    marker = "      id: run"
    assert marker in _ACTION_TEXT, "the run step has no id"
    after = _ACTION_TEXT.split(marker, 1)[1]
    start = after.index("run: |")
    return after[start:]


# --- the action's shape ---------------------------------------------------


def test_the_action_is_a_composite_action_with_the_documented_inputs() -> None:
    assert "using: composite" in _ACTION_TEXT
    assert _top_level_input_names() == {
        "mode",
        "manifest",
        "evidence-root",
        "receipt",
        "fail-on",
        "version",
        "upload-receipt",
    }
    assert _block_keys("outputs:") == {"exit-code", "status"}


def test_every_documented_input_exists_in_the_action() -> None:
    """The docs table and the action must not drift apart."""
    documented = {
        line.split("|")[1].strip().strip("`")
        for line in DOCS.read_text(encoding="utf-8").splitlines()
        if line.startswith("| `") and "`" in line
    }
    for name in _top_level_input_names():
        assert name in documented, f"input {name} is undocumented in docs/CI-ACTION.md"


def test_the_action_maps_every_code_in_the_band() -> None:
    """All five documented codes must be named, not just success and failure."""
    script = _run_step_script()
    for code, status in (
        ("0", "ok"),
        ("1", "rejected"),
        ("2", "input_error"),
        ("3", "not_observed"),
        ("4", "review_required"),
    ):
        assert f'{code}) status="{status}"' in script, f"code {code} is not mapped to {status}"


def test_code_two_fails_regardless_of_fail_on() -> None:
    """The contract's one reserved code must not be filtered by `fail-on`.

    `fail-on: rejected` passing an unreadable manifest would report "nothing was
    rejected" about a run that never evaluated anything.
    """
    script = _run_step_script()
    assert 'if [ "$code" = "2" ]; then' in script
    body = script.split('if [ "$code" = "2" ]; then', 1)[1].split("fi", 1)[0]
    assert "exit 2" in body
    # And the check precedes the fail-on loop, so it cannot be reached first.
    assert script.index('if [ "$code" = "2" ]') < script.index("for blocked in $blocking")


def test_the_three_fail_on_levels_are_nested_correctly() -> None:
    script = _run_step_script()
    assert 'rejected) blocking="1"' in script
    assert 'incomplete) blocking="1 3"' in script
    assert 'any) blocking="1 3 4"' in script


def test_an_unknown_fail_on_or_mode_is_refused_as_an_input_error() -> None:
    script = _run_step_script()
    assert "fail-on must be one of" in script
    assert "mode must be one of" in script


def test_the_run_step_does_not_use_set_e() -> None:
    """`set -e` would abort on the CLI's nonzero exit before it could be mapped.

    That is the whole failure this action exists to avoid: aborting on exit 1
    discards the distinction between an evaluated outcome and a tool failure.
    """
    script = _run_step_script()
    assert "set -uo pipefail" in script
    assert "set -euo pipefail" not in script
    assert "set -e\n" not in script


def test_the_install_step_does_use_set_e() -> None:
    """Installation failing silently would run the next step against no CLI."""
    install = _ACTION_TEXT.split("name: Install obligation-receipts", 1)[1]
    install = install.split("- name:", 1)[0]
    assert "set -euo pipefail" in install


def test_the_action_uses_other_actions_at_all() -> None:
    """The floor under the two gates that now live in `tests/test_supply_chain.py`.

    Both of this module's own supply-chain assertions were deleted, and this is what
    stops that from having quietly reduced coverage to nothing.

    They were **weaker duplicates of gates that already read `action.yml`**, each with its
    own copy of a literal the real gate also holds:

    * the digest-pin check compiled a second copy of the `@[0-9a-f]{40}` pattern, so it
      proved things about a regex nothing ran -- the same shape as the local-reference
      exemption that used to be guarded by a check of a different exemption, and the
      reason `_PINNED_USE_LINE` is now one module-level constant;
    * `test_the_action_publishes_nothing` held **six** forbidden spellings where
      `_PUBLISH_COMMANDS` holds twelve, and it was `action.yml`'s only cover, because the
      publication ban read `workflow_files`. `hatch publish`, `flit publish`,
      `poetry publish`, `softprops/action-gh-release` and `ncipollo/release-action` all
      walked past it. Measured on `origin/main`: a `softprops/action-gh-release` step
      added to `action.yml` left all 145 tests green.

    A second, weaker copy of a gate is worse than none, because it reads as coverage. The
    strong ones read `pinned_files`, which contains this file --
    `test_the_composite_action_is_read_by_the_supply_chain_gate` asserts that, and
    `test_the_pin_identity_step_reads_every_file_the_digest_gate_reads` asserts ci.yml
    resolves the SHAs it finds there. What is left here is the premise those gates rest
    on: that this file references other actions at all. If it stops doing so, they become
    vacuous over it and this fails rather than going quietly green.

    (Cross-module import would have been the other repair. It is not available: pytest
    runs with `--import-mode=importlib` and `tests/` is not a package, so
    `import test_supply_chain` raises `ModuleNotFoundError` -- measured, not assumed.)
    """
    uses = [
        line for line in _ACTION_TEXT.splitlines() if line.strip().startswith(("- uses:", "uses:"))
    ]
    assert uses, (
        "the action references no other actions, so the digest-pin and publication gates "
        "in tests/test_supply_chain.py now prove nothing about it"
    )


def test_the_dogfood_job_runs_the_local_action_on_the_example() -> None:
    """Issue 61: 'The example manifest passes in CI through the action'."""
    text = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "  dogfood-action:" in text
    job = text.split("  dogfood-action:", 1)[1].split("\n  package:", 1)[0]
    assert "timeout-minutes: 15" in job
    # `$/`, not `./`: the self-repository form is resolved by Actions rather
    # than through whatever the runner's workspace happens to hold, so a step
    # that cloned something before this one cannot decide which action runs.
    # Asserted as the exact YAML line, because `$/` also appears in the comment
    # above it and a bare substring would pass on the comment alone.
    assert "\n        uses: $/\n" in job
    assert "\n        uses: ./\n" not in job
    assert "\n          mode: evaluate\n" in job
    assert "examples/accessibility-acceptance/obligations.toml" in job
    assert "examples/accessibility-acceptance/evidence" in job
    # The indented KEY, not the bare string: the job block also contains a
    # comment explaining the choice, and asserting on the bare string passed
    # happily when the setting itself was changed to `rejected`. A negative
    # control caught that, which is why this is anchored to the YAML line.
    assert "\n          fail-on: any\n" in job


# --- the pre-commit hook --------------------------------------------------


def test_the_hook_manifest_declares_the_validate_hook() -> None:
    text = HOOKS.read_text(encoding="utf-8")
    assert text.count("\n- id:") == 1, "exactly one hook is published"
    assert "- id: obligation-receipts-validate" in text
    assert "entry: obligation-receipts validate" in text
    assert "language: python" in text
    assert "pass_filenames: true" in text


def test_the_hook_matches_an_obligations_manifest_and_little_else() -> None:
    text = HOOKS.read_text(encoding="utf-8")
    files_line = next(line for line in text.splitlines() if line.strip().startswith("files:"))
    pattern = re.compile(files_line.split("files:", 1)[1].strip())
    for matching in ("obligations.toml", "acceptance/obligations.toml"):
        assert pattern.search(matching), f"hook should match {matching}"
    for other in ("pyproject.toml", "uv.lock", "docs/obligations.md", "my-obligations.toml"):
        assert not pattern.search(other), f"hook should not match {other}"


def test_the_console_script_the_hook_invokes_exists() -> None:
    """A hook whose entry point does not exist fails at install time, obscurely."""
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    scripts = project["project"]["scripts"]
    assert "obligation-receipts" in scripts


def test_validate_accepts_a_batch_because_that_is_how_pre_commit_calls_it(
    capsysbinary: pytest.CaptureFixture[bytes],
) -> None:
    """Issue 61: pre-commit passes every changed matching file in one call."""
    manifest = str(EXAMPLE / "obligations.toml")
    assert main(["validate", manifest, manifest]) == OK
    assert capsysbinary.readouterr().out.count(b"\n") == 2


def test_one_manifest_still_produces_exactly_one_line(
    capsysbinary: pytest.CaptureFixture[bytes],
) -> None:
    """The batch change must not alter single-manifest behaviour."""
    assert main(["validate", str(EXAMPLE / "obligations.toml")]) == OK
    out = capsysbinary.readouterr().out
    assert out.count(b"\n") == 1
    assert b'"status":"valid"' in out


def test_the_hook_refuses_a_manifest_with_a_malformed_pointer(tmp_path: Path) -> None:
    """Issue 61: 'The pre-commit hook refuses a manifest with a malformed JSON pointer'."""
    broken = tmp_path / "obligations.toml"
    text = (EXAMPLE / "obligations.toml").read_text(encoding="utf-8")
    broken.write_text(
        text.replace('pointer = "/summary/critical_violations"', 'pointer = "summary/oops"'),
        encoding="utf-8",
    )
    (tmp_path / "source").mkdir()
    (tmp_path / "source" / "section-508-acceptance.txt").write_bytes(
        (EXAMPLE / "source" / "section-508-acceptance.txt").read_bytes()
    )
    assert main(["validate", str(broken)]) == INPUT_ERROR


def test_a_malformed_manifest_is_an_input_error_not_a_rejection(tmp_path: Path) -> None:
    """Issue 61: 'A malformed manifest fails as an error (code 2), not as a rejection'."""
    broken = tmp_path / "obligations.toml"
    broken.write_text("this is not a manifest\n", encoding="utf-8")
    code = main(["validate", str(broken)])
    assert code == INPUT_ERROR
    assert code != 1, "an unreadable manifest must never read as an evaluated failure"


def test_the_action_does_not_write_to_github_path() -> None:
    """`GITHUB_PATH` persists into every later step of the CONSUMER's job.

    zizmor's `github-env` audit flags a write there as a code-execution risk,
    and the pattern deserves it: an action that appends to `GITHUB_PATH` is
    silently changing how the calling job resolves commands after it returns.
    The CLI is invoked at its absolute path instead, so there is nothing to
    waive and nothing leaks out of the action.
    """
    assert "GITHUB_PATH" not in _run_step_script()
    install = _ACTION_TEXT.split("name: Install obligation-receipts", 1)[1].split("- name:", 1)[0]
    assert "GITHUB_PATH" not in install
    # And the CLI really is reached by absolute path, not by bare name.
    script = _run_step_script()
    assert 'cli="${RUNNER_TEMP}/obligation-receipts-venv/bin/obligation-receipts"' in script
    assert '"$cli" evaluate' in script
    assert '"$cli" verify' in script
