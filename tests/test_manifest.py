from pathlib import Path

import pytest

import obligation_receipts.manifest as manifest_module
from obligation_receipts.manifest import ManifestError, load_manifest
from obligation_receipts.models import Classification
from obligation_receipts.paths import BoundedPathError


def _replace(path: Path, old: str, new: str) -> None:
    content = path.read_text(encoding="utf-8")
    assert old in content
    path.write_text(content.replace(old, new), encoding="utf-8")


def test_loads_and_normalizes_source_bound_manifest(example_manifest: Path) -> None:
    manifest = load_manifest(example_manifest)
    assert manifest.contract.contract_id == "synthetic-accessibility-acceptance"
    assert len(manifest.obligations) == 4
    assert manifest.obligations[-1].classification is Classification.UNVERIFIABLE
    assert manifest.normalized_dict()["schema_version"] == "obligation-receipts/manifest/v0.1"


def test_rejects_source_digest_mismatch(copied_example: Path) -> None:
    source = copied_example / "source" / "section-508-acceptance.txt"
    source.write_text(source.read_text(encoding="utf-8") + "\nchanged", encoding="utf-8")
    with pytest.raises(ManifestError, match="source digest does not match"):
        load_manifest(copied_example / "obligations.toml")


def test_rejects_nonportable_source_path_before_source_access(
    copied_example: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path = copied_example / "obligations.toml"
    _replace(
        manifest_path,
        'source_path = "source/section-508-acceptance.txt"',
        'source_path = "https:source.txt"',
    )

    def unexpected_hash(*args: object, **kwargs: object) -> tuple[Path, str]:
        pytest.fail("source hash must not be attempted for an unsafe lexical path")

    monkeypatch.setattr(manifest_module, "hash_bounded_file", unexpected_hash)
    with pytest.raises(ManifestError, match="portable and relative"):
        load_manifest(manifest_path)


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        (
            'authority = "Synthetic public-sector software acceptance exercise"',
            'authority = "Synthetic public-sector software acceptance exercise"\nextra = "no"',
            "unknown field",
        ),
        ('id = "synthetic-accessibility-acceptance"', 'id = "INVALID ID"', "identifier"),
        (
            'source_sha256 = "b94a87890d23aaedc93c143a00d5fc4f96f7ed09a9f839bb4aa8d9c841562bed"',
            'source_sha256 = "bad"',
            "SHA-256",
        ),
        ('classification = "automated"', 'classification = "magic"', "unsupported"),
        ('kind = "json_assertion"', 'kind = "shell_command"', "not supported"),
        (
            'pointer = "/summary/critical_violations"',
            'pointer = "summary/critical_violations"',
            "RFC 6901",
        ),
        ('operator = "eq"', 'operator = "approximately"', "operator"),
        (
            'kind = "review_attestation"',
            'kind = "review_attestation"\npointer = "/status"',
            "cannot define an assertion",
        ),
        (
            'kind = "review_attestation"',
            'kind = "external_attestation"',
            "does not match",
        ),
        (
            'reason = "No population, task, method, threshold, or accountable reviewer is defined."',
            'reason = ""',
            "non-empty",
        ),
    ],
)
def test_rejects_invalid_manifest_variants(
    copied_example: Path, old: str, new: str, message: str
) -> None:
    manifest_path = copied_example / "obligations.toml"
    _replace(manifest_path, old, new)
    with pytest.raises(ManifestError, match=message):
        load_manifest(manifest_path)


def test_rejects_missing_assertion_expected(copied_example: Path) -> None:
    manifest_path = copied_example / "obligations.toml"
    _replace(manifest_path, "expected = 0\n", "")
    with pytest.raises(ManifestError, match="expected is required"):
        load_manifest(manifest_path)


def test_rejects_expected_for_exists_operator(copied_example: Path) -> None:
    manifest_path = copied_example / "obligations.toml"
    _replace(manifest_path, 'operator = "eq"', 'operator = "exists"')
    with pytest.raises(ManifestError, match="not allowed"):
        load_manifest(manifest_path)


@pytest.mark.parametrize("value", ["nan", "2026-07-22", "12:30:00"])
def test_rejects_non_json_expected_values(copied_example: Path, value: str) -> None:
    manifest_path = copied_example / "obligations.toml"
    _replace(manifest_path, "expected = 0", f"expected = {value}")
    with pytest.raises(ManifestError, match="not bounded JSON"):
        load_manifest(manifest_path)


def test_rejects_duplicate_obligation_ids(copied_example: Path) -> None:
    manifest_path = copied_example / "obligations.toml"
    _replace(manifest_path, 'id = "a2-human-workflow-review"', 'id = "a1-zero-critical-violations"')
    with pytest.raises(ManifestError, match="obligation ids must be unique"):
        load_manifest(manifest_path)


def test_rejects_duplicate_evidence_ids(copied_example: Path) -> None:
    manifest_path = copied_example / "obligations.toml"
    _replace(manifest_path, 'id = "a2-review-attestation"', 'id = "a1-axe-summary"')
    with pytest.raises(ManifestError, match="evidence ids must be unique"):
        load_manifest(manifest_path)


def test_rejects_empty_obligations(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    manifest_path = tmp_path / "empty.toml"
    manifest_path.write_text(
        """
obligations = []

[contract]
id = "empty-contract"
title = "Empty"
version = "1"
authority = "Test"
effective_date = "2026-07-22"
source_path = "source.txt"
source_sha256 = "41cf6794ba4200b839c53531555f0f3998df4cbb01a4d5cb0b94e3ca5e23947d"
""".strip(),
        encoding="utf-8",
    )
    with pytest.raises(ManifestError, match="non-empty"):
        load_manifest(manifest_path)


def test_rejects_malformed_toml(tmp_path: Path) -> None:
    manifest_path = tmp_path / "broken.toml"
    manifest_path.write_text("[contract", encoding="utf-8")
    with pytest.raises(ManifestError, match="not valid TOML"):
        load_manifest(manifest_path)


def test_rejects_non_utf8_and_oversized_manifest(tmp_path: Path) -> None:
    manifest_path = tmp_path / "bad.toml"
    manifest_path.write_bytes(b"\xff")
    with pytest.raises(ManifestError, match="valid UTF-8"):
        load_manifest(manifest_path)
    manifest_path.write_bytes(b" " * (2 * 1024 * 1024 + 1))
    with pytest.raises(ManifestError, match="2 MiB"):
        load_manifest(manifest_path)


def test_rejects_oversized_contract_source_before_hashing(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_bytes(b"x" * (16 * 1024 * 1024 + 1))
    manifest = tmp_path / "obligations.toml"
    manifest.write_text(
        f"""
[contract]
id = "contract-1"
title = "Bounded source"
version = "1"
authority = "approved"
effective_date = "2026-01-01"
source_path = "source.txt"
source_sha256 = "{"0" * 64}"

[[obligations]]
id = "obligation-1"
clause_ref = "1"
text = "A bounded source."
classification = "unverifiable"
criticality = "should"
owner = "owner"
reason = "not machine evaluable"
""",
        encoding="utf-8",
    )
    with pytest.raises(ManifestError, match="16777216-byte limit"):
        load_manifest(manifest)


def test_rejects_non_table_contract_section(tmp_path: Path) -> None:
    # A structural change (table -> scalar) doesn't fit the copied_example +
    # _replace() pattern the rest of this file uses for single-line
    # mutations, so this one stays hand-written -- but bounded to just the
    # one section under test, not a full manifest with an unreachable
    # source file and obligation the assertion never gets to.
    manifest = tmp_path / "obligations.toml"
    manifest.write_text('contract = "not-a-table"\n\n[[obligations]]\n', encoding="utf-8")
    with pytest.raises(ManifestError, match="contract must be a table"):
        load_manifest(manifest)


def test_rejects_missing_required_contract_fields(copied_example: Path) -> None:
    manifest_path = copied_example / "obligations.toml"
    _replace(manifest_path, 'version = "1.0"\n', "")
    with pytest.raises(ManifestError, match="contract is missing field\\(s\\): version"):
        load_manifest(manifest_path)


def test_rejects_multiple_missing_required_contract_fields(copied_example: Path) -> None:
    # The single-field case above can't tell sorted(_CONTRACT_KEYS -
    # set(value)) + ", ".join(...) apart from a hardcoded one-field message;
    # this pins the join/order behavior for more than one.
    manifest_path = copied_example / "obligations.toml"
    _replace(manifest_path, 'version = "1.0"\n', "")
    _replace(
        manifest_path, 'authority = "Synthetic public-sector software acceptance exercise"\n', ""
    )
    with pytest.raises(ManifestError, match=r"contract is missing field\(s\): authority, version"):
        load_manifest(manifest_path)


def test_rejects_non_list_evidence(copied_example: Path) -> None:
    manifest_path = copied_example / "obligations.toml"
    _replace(
        manifest_path,
        '[[obligations.evidence]]\nid = "a1-axe-summary"\nkind = "json_assertion"\npath = "automated/axe-summary.json"\npointer = "/summary/critical_violations"\noperator = "eq"\nexpected = 0\n',
        'evidence = "not-a-list"\n',
    )
    with pytest.raises(
        ManifestError, match=r"obligations\[0\]\.evidence must be an array of tables"
    ):
        load_manifest(manifest_path)


def test_rejects_unverifiable_obligation_declaring_evidence(copied_example: Path) -> None:
    manifest_path = copied_example / "obligations.toml"
    _replace(
        manifest_path,
        'reason = "No population, task, method, threshold, or accountable reviewer is defined."',
        'reason = "No population, task, method, threshold, or accountable reviewer is defined."\n\n[[obligations.evidence]]\nid = "a4-evidence"\nkind = "json_assertion"\npath = "automated/axe-summary.json"\npointer = "/summary/critical_violations"\noperator = "eq"\nexpected = 0',
    )
    with pytest.raises(
        ManifestError, match=r"obligations\[3\] unverifiable obligations cannot declare evidence"
    ):
        load_manifest(manifest_path)


def test_rejects_verifiable_obligation_without_evidence(copied_example: Path) -> None:
    manifest_path = copied_example / "obligations.toml"
    _replace(
        manifest_path,
        '[[obligations.evidence]]\nid = "a1-axe-summary"\nkind = "json_assertion"\npath = "automated/axe-summary.json"\npointer = "/summary/critical_violations"\noperator = "eq"\nexpected = 0\n\n',
        "",
    )
    with pytest.raises(
        ManifestError, match=r"obligations\[0\] must declare at least one evidence item"
    ):
        load_manifest(manifest_path)


def test_rejects_blank_reason_when_present_on_verifiable_obligation(copied_example: Path) -> None:
    manifest_path = copied_example / "obligations.toml"
    _replace(
        manifest_path,
        'id = "a1-zero-critical-violations"',
        'id = "a1-zero-critical-violations"\nreason = "   "',
    )
    with pytest.raises(
        ManifestError, match=r"obligations\[0\]\.reason must be a non-empty string when present"
    ):
        load_manifest(manifest_path)


def test_rejects_manifest_when_read_fails_bounded_path(
    copied_example: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path = copied_example / "obligations.toml"

    def raise_bounded_error(*args: object, **kwargs: object) -> bytes:
        raise BoundedPathError("artifact path is not a regular file")

    monkeypatch.setattr(manifest_module, "read_regular_file", raise_bounded_error)
    with pytest.raises(
        ManifestError,
        match="manifest cannot be read safely: artifact path is not a regular file",
    ):
        load_manifest(manifest_path)
