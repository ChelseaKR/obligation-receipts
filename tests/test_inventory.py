"""The evidence-root inventory: what is in the root, and nothing about passing.

Issue 63. Each test below maps to one of that issue's "Done when" bullets, plus
the two failure modes this repository treats as the important ones: a status
value leaking into an inventory, and an unreadable file being counted as a
present one.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from obligation_receipts.canonical import canonical_json_bytes, sha256_bytes
from obligation_receipts.cli import main
from obligation_receipts.inventory import (
    MAX_ARTIFACT_BYTES,
    EvidenceRootAuditError,
    audit_evidence_root,
    render_markdown,
)
from obligation_receipts.manifest import load_manifest
from obligation_receipts.models import JsonValue

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "accessibility-acceptance"
MANIFEST = EXAMPLE / "obligations.toml"
EVIDENCE = EXAMPLE / "evidence"


def _obj(value: JsonValue) -> dict[str, JsonValue]:
    """Narrow one recursive JsonValue to an object, for `mypy --strict`."""
    assert isinstance(value, dict)
    return value


def _rows(value: JsonValue) -> list[dict[str, JsonValue]]:
    """Narrow one recursive JsonValue to a list of inventory rows."""
    assert isinstance(value, list)
    return [_obj(item) for item in value]


def _counts(payload: dict[str, JsonValue]) -> dict[str, JsonValue]:
    return _obj(payload["counts"])


def _audit(root: Path, *, local: bool = True) -> dict[str, JsonValue]:
    document = audit_evidence_root(load_manifest(MANIFEST), root, include_local_details=local)
    return _obj(document["payload"])


def _copy_example(tmp_path: Path) -> Path:
    """A writable copy of the example evidence root."""
    root = tmp_path / "evidence"
    root.mkdir()
    for source in sorted(EVIDENCE.rglob("*")):
        if source.is_file():
            target = root / source.relative_to(EVIDENCE)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
    return root


def test_the_untouched_example_root_is_fully_declared_and_fully_present() -> None:
    payload = _audit(EVIDENCE)
    counts = _counts(payload)
    assert counts["declared_total"] == 3
    assert counts["declared_present"] == 3
    assert counts["declared_absent"] == 0
    assert counts["undeclared"] == 0
    assert counts["symlinks"] == 0
    assert counts["files_found"] == 3


def test_a_stray_file_is_listed_as_undeclared_with_its_digest(tmp_path: Path) -> None:
    """Issue 63: 'Adding a stray file to the example root lists it as undeclared'."""
    root = _copy_example(tmp_path)
    stray = root / "automated" / "leftover-from-another-contract.json"
    stray.write_bytes(b'{"note": "not declared by this manifest"}\n')

    payload = _audit(root)
    assert _counts(payload)["undeclared"] == 1
    undeclared = _rows(payload["undeclared"])
    assert len(undeclared) == 1
    row = undeclared[0]
    assert row["path"] == "automated/leftover-from-another-contract.json"
    assert row["sha256"] == sha256_bytes(stray.read_bytes())
    assert row["evidence_ids"] == []
    # The declared three are unaffected: an extra file is not a missing one.
    assert _counts(payload)["declared_present"] == 3


def test_a_missing_declared_artifact_is_absent_and_never_counted_present(
    tmp_path: Path,
) -> None:
    root = _copy_example(tmp_path)
    (root / "manual" / "keyboard-review.json").unlink()

    payload = _audit(root)
    assert _counts(payload)["declared_absent"] == 1
    assert _counts(payload)["declared_present"] == 2
    absent = [
        row for row in _rows(payload["declared"]) if row["path"] == "manual/keyboard-review.json"
    ]
    assert len(absent) == 1
    assert absent[0]["sha256"] is None
    assert absent[0]["evidence_ids"] == ["a2-review-attestation"]


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink semantics")
def test_a_symlink_inside_the_root_is_reported_and_never_followed(tmp_path: Path) -> None:
    """Issue 63: 'A symlink inside the root is reported and never followed'.

    The link points at a file OUTSIDE the root holding a distinctive marker. If
    the walk ever followed it, that marker's digest would appear in the output.
    """
    outside = tmp_path / "outside-the-root.json"
    outside.write_bytes(b'{"secret": "must never be hashed by the inventory"}\n')
    outside_digest = sha256_bytes(outside.read_bytes())

    root = _copy_example(tmp_path)
    os.symlink(outside, root / "escape.json")

    payload = _audit(root)
    assert _counts(payload)["symlinks"] == 1
    symlinks = _rows(payload["symlinks"])
    assert symlinks[0]["path"] == "escape.json"
    assert symlinks[0]["is_symlink"] is True
    assert symlinks[0]["sha256"] is None
    assert symlinks[0]["unreadable_reason"] == "symlink reported and never followed"

    # The decisive assertion: nothing outside the root was read.
    assert outside_digest not in canonical_json_bytes(payload).decode()


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink semantics")
def test_a_directory_symlink_is_not_descended_into(tmp_path: Path) -> None:
    outside_dir = tmp_path / "other-contract"
    outside_dir.mkdir()
    (outside_dir / "leak.json").write_bytes(b'{"a": 1}\n')

    root = _copy_example(tmp_path)
    os.symlink(outside_dir, root / "linked-dir")

    payload = _audit(root)
    paths = {row["path"] for row in _rows(payload["undeclared"])} | {
        row["path"] for row in _rows(payload["symlinks"])
    }
    assert "linked-dir" in paths
    assert not any(str(path).startswith("linked-dir/") for path in paths)


def test_two_evidence_ids_on_one_file_are_listed_with_both_ids(tmp_path: Path) -> None:
    """Issue 63: 'Two obligations pointing at one file list the file with both evidence ids'."""
    manifest_text = MANIFEST.read_text(encoding="utf-8")
    manifest_text += """
[[obligations]]
id = "a5-second-reader-of-one-file"
clause_ref = "A-5"
text = "A second obligation reads the same automated summary."
classification = "automated"
criticality = "should"
owner = "Agency acceptance lead"

[[obligations.evidence]]
id = "a5-axe-summary-again"
kind = "json_assertion"
path = "automated/axe-summary.json"
pointer = "/summary/serious_violations"
operator = "lte"
expected = 2
"""
    contract_dir = tmp_path / "contract"
    contract_dir.mkdir()
    (contract_dir / "obligations.toml").write_text(manifest_text, encoding="utf-8")
    source_dir = contract_dir / "source"
    source_dir.mkdir()
    (source_dir / "section-508-acceptance.txt").write_bytes(
        (EXAMPLE / "source" / "section-508-acceptance.txt").read_bytes()
    )

    document = audit_evidence_root(
        load_manifest(contract_dir / "obligations.toml"),
        EVIDENCE,
        include_local_details=True,
    )
    payload = _obj(document["payload"])
    assert _counts(payload)["multiply_referenced"] == 1
    shared = _rows(payload["multiply_referenced"])
    assert shared[0]["path"] == "automated/axe-summary.json"
    assert shared[0]["evidence_ids"] == ["a1-axe-summary", "a5-axe-summary-again"]
    # Declared totals count paths, not references, so the file is one row.
    assert _counts(payload)["declared_total"] == 3


def test_the_output_carries_no_status_and_no_evidence_content(tmp_path: Path) -> None:
    """Issue 63 sentinel: 'no evidence content and no status value'.

    The example's axe summary holds `"critical_violations": 0` and the manual
    attestation holds `"status": "pass"`. Neither the values nor the evaluation
    vocabulary may appear anywhere in the inventory.
    """
    root = _copy_example(tmp_path)
    payload = _audit(root)
    rendered = canonical_json_bytes(payload).decode()

    for forbidden in ('"status"', '"pass"', '"fail"', "review_required", "unverifiable"):
        assert forbidden not in rendered, f"inventory leaked {forbidden}"

    # Content, not just verdicts. Keys and values that exist only inside the
    # evidence documents -- `contract_id` and `manifest_sha256` are excluded
    # because the inventory carries the MANIFEST's copies of those, which is
    # declared metadata rather than anything read out of an artifact.
    evidence_only = {
        '"reviewer"',
        '"issuer"',
        '"method"',
        '"source_uri"',
        '"reviewed_at"',
        '"observed_at"',
        '"run_id"',
        '"summary"',
        '"critical_violations"',
        '"serious_violations"',
        "Synthetic Reviewer",
        "Synthetic Vendor",
        "synthetic-a11y-2026-07-22",
        "https://example.invalid/synthetic-acr",
        "2026-07-22T12:00:00Z",
    }
    for forbidden in sorted(evidence_only):
        assert forbidden not in rendered, f"inventory leaked evidence content {forbidden}"

    # And the digests really are of the evidence files, so the check above is
    # about content rather than about the inventory having read nothing at all.
    digests = {row["sha256"] for row in _rows(payload["declared"])}
    assert sha256_bytes((root / "manual" / "keyboard-review.json").read_bytes()) in digests

    assert _obj(payload["limitations"])["evaluation_performed"] is False
    assert _obj(payload["limitations"])["evidence_content_read"] is False
    assert payload["decision_scope"] == "evidence_root_inventory_only"


def test_an_oversized_declared_artifact_is_unreadable_not_present(tmp_path: Path) -> None:
    """The absence-rendered-as-a-value guard.

    A file too large to evaluate must not be counted as a present artifact with
    a digest; it is `unreadable`, its digest is `null`, and the reason says why.
    """
    root = _copy_example(tmp_path)
    target = root / "automated" / "axe-summary.json"
    target.write_bytes(b"x" * (MAX_ARTIFACT_BYTES + 1))

    payload = _audit(root)
    assert _counts(payload)["declared_unreadable"] == 1
    assert _counts(payload)["declared_present"] == 2
    row = next(r for r in _rows(payload["declared"]) if r["path"] == "automated/axe-summary.json")
    assert row["sha256"] is None
    assert row["unreadable_reason"] == f"artifact exceeds the {MAX_ARTIFACT_BYTES}-byte limit"
    assert row["size_bytes"] == MAX_ARTIFACT_BYTES + 1


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO creation is unavailable")
def test_a_special_file_is_reported_without_blocking_on_it(tmp_path: Path) -> None:
    root = _copy_example(tmp_path)
    os.mkfifo(root / "pipe.json")

    payload = _audit(root)
    row = next(r for r in _rows(payload["undeclared"]) if r["path"] == "pipe.json")
    assert row["sha256"] is None
    assert row["unreadable_reason"] == "not a regular file"
    assert _counts(payload)["undeclared_unreadable"] == 1


def test_portable_mode_redacts_paths_but_keeps_digests_and_counts(tmp_path: Path) -> None:
    root = _copy_example(tmp_path)
    (root / "external" / "acme-health-renewal.json").write_bytes(b'{"a": 1}\n')

    payload = _audit(root, local=False)
    assert payload["detail_mode"] == "portable_redacted"
    rendered = canonical_json_bytes(payload).decode()
    assert "acme-health-renewal" not in rendered
    assert all(row["path"] is None for row in _rows(payload["undeclared"]))
    assert all(row["path"] is None for row in _rows(payload["declared"]))
    # Redaction removes the name, not the evidence that a file is there.
    assert _counts(payload)["undeclared"] == 1
    assert _rows(payload["undeclared"])[0]["sha256"] == sha256_bytes(b'{"a": 1}\n')


def test_the_document_digest_covers_the_payload(tmp_path: Path) -> None:
    document = audit_evidence_root(load_manifest(MANIFEST), EVIDENCE)
    assert document["payload_sha256"] == sha256_bytes(canonical_json_bytes(document["payload"]))
    assert document["schema_version"] == "obligation-receipts/evidence-root-audit-document/v0.1"


def test_the_same_root_audits_byte_identically_twice() -> None:
    first = audit_evidence_root(load_manifest(MANIFEST), EVIDENCE)
    second = audit_evidence_root(load_manifest(MANIFEST), EVIDENCE)
    assert canonical_json_bytes(first) == canonical_json_bytes(second)


def test_a_root_that_is_not_a_directory_is_an_input_error(tmp_path: Path) -> None:
    from obligation_receipts.paths import BoundedPathError

    not_a_directory = tmp_path / "file.json"
    not_a_directory.write_bytes(b"{}\n")
    with pytest.raises(BoundedPathError):
        audit_evidence_root(load_manifest(MANIFEST), not_a_directory)


def test_markdown_says_the_counts_are_not_a_verdict() -> None:
    document = audit_evidence_root(load_manifest(MANIFEST), EVIDENCE)
    rendered = render_markdown(document)
    assert "not an evaluation" in rendered
    assert "declared present | 3" in rendered
    assert "passed" not in rendered.replace("passed or failed", "")


def test_markdown_refuses_a_document_with_no_payload() -> None:
    with pytest.raises(EvidenceRootAuditError):
        render_markdown({"payload": None})


def test_cli_audit_emits_one_canonical_json_line_and_exits_zero(
    capsysbinary: pytest.CaptureFixture[bytes],
) -> None:
    code = main(
        [
            "audit-evidence-root",
            str(MANIFEST),
            "--evidence-root",
            str(EVIDENCE),
            "--include-local-details",
        ]
    )
    assert code == 0
    out = capsysbinary.readouterr().out
    assert out.endswith(b"\n")
    assert out.count(b"\n") == 1
    document = json.loads(out)
    assert document["payload"]["counts"]["declared_present"] == 3


def test_cli_audit_markdown_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        ["audit-evidence-root", str(MANIFEST), "--evidence-root", str(EVIDENCE), "--markdown"]
    )
    assert code == 0
    assert "# Evidence root inventory" in capsys.readouterr().out


def test_cli_audit_exits_two_on_a_missing_evidence_root(tmp_path: Path) -> None:
    code = main(
        [
            "audit-evidence-root",
            str(MANIFEST),
            "--evidence-root",
            str(tmp_path / "does-not-exist"),
        ]
    )
    assert code == 2


def test_cli_audit_exits_two_on_an_unreadable_manifest(tmp_path: Path) -> None:
    broken = tmp_path / "obligations.toml"
    broken.write_text("this is not a manifest\n", encoding="utf-8")
    code = main(["audit-evidence-root", str(broken), "--evidence-root", str(EVIDENCE)])
    assert code == 2


def test_the_console_entry_point_runs_the_audit() -> None:
    completed = subprocess.run(  # noqa: S603 - fixed argv: sys.executable plus repo constants
        [
            sys.executable,
            "-m",
            "obligation_receipts.cli",
            "audit-evidence-root",
            str(MANIFEST),
            "--evidence-root",
            str(EVIDENCE),
        ],
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0
    assert json.loads(completed.stdout)["payload"]["counts"]["files_found"] == 3


def test_reason_strings_are_stable_and_non_sensitive() -> None:
    from obligation_receipts.inventory import _reason_for
    from obligation_receipts.paths import BoundedPathError

    assert _reason_for(BoundedPathError("escapes its declared root")) == (
        "escapes its declared root"
    )
    assert _reason_for(PermissionError(13, "denied")) == "artifact is not readable by this process"
    assert _reason_for(FileNotFoundError(2, "nope")) == "artifact does not exist"
    assert _reason_for(OSError(5, "io")) == "artifact could not be read"
    assert _reason_for(ValueError("other")) == "artifact could not be read"


def test_a_root_that_cannot_be_enumerated_is_refused_not_reported_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unreadable directory must not be reported as a root holding nothing."""
    root = _copy_example(tmp_path)

    def refuse(_path: object) -> list[object]:
        raise PermissionError(13, "denied")

    monkeypatch.setattr("obligation_receipts.inventory.os.scandir", refuse)
    with pytest.raises(EvidenceRootAuditError, match="cannot be enumerated"):
        _audit(root)


def test_a_root_larger_than_the_entry_cap_is_refused_not_truncated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A truncated inventory reported as a complete one is the defect this guards."""
    root = _copy_example(tmp_path)
    monkeypatch.setattr("obligation_receipts.inventory.MAX_ENTRIES", 2)
    with pytest.raises(EvidenceRootAuditError, match="truncated inventory"):
        _audit(root)


def test_a_file_whose_stat_fails_is_unreadable_with_a_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _copy_example(tmp_path)
    real_stat = os.DirEntry.stat

    def flaky(self: os.DirEntry[str], *, follow_symlinks: bool = True) -> os.stat_result:
        if self.name == "axe-summary.json":
            raise PermissionError(13, "denied")
        return real_stat(self, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(os.DirEntry, "stat", flaky, raising=False)
    payload = _audit(root)
    row = next(r for r in _rows(payload["declared"]) if r["path"] == "automated/axe-summary.json")
    assert row["sha256"] is None
    assert row["unreadable_reason"] == "artifact is not readable by this process"
    assert _counts(payload)["declared_unreadable"] == 1


def test_a_file_that_vanishes_before_hashing_is_unreadable_not_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The stat/hash race: the digest is null, never an empty string."""
    root = _copy_example(tmp_path)

    def vanish(*_args: object, **_kwargs: object) -> tuple[Path, str]:
        raise FileNotFoundError(2, "gone")

    monkeypatch.setattr("obligation_receipts.inventory.hash_bounded_file", vanish)
    payload = _audit(root)
    assert _counts(payload)["declared_present"] == 0
    assert _counts(payload)["declared_unreadable"] == 3
    assert all(row["sha256"] is None for row in _rows(payload["declared"]))
    assert all(
        row["unreadable_reason"] == "artifact does not exist" for row in _rows(payload["declared"])
    )


def test_a_file_named_unportably_is_reported_with_the_rule_it_breaks(tmp_path: Path) -> None:
    root = _copy_example(tmp_path)
    (root / "back\\slash.json").write_bytes(b"{}\n")

    payload = _audit(root)
    row = next(r for r in _rows(payload["undeclared"]) if r["path"] == "back\\slash.json")
    assert row["sha256"] is None
    assert row["unreadable_reason"] == "artifact path must be portable and relative"


def test_markdown_refuses_a_document_with_no_counts() -> None:
    with pytest.raises(EvidenceRootAuditError, match="no counts"):
        render_markdown({"payload": {"counts": None}})


def test_markdown_in_portable_mode_says_paths_are_redacted() -> None:
    document = audit_evidence_root(load_manifest(MANIFEST), EVIDENCE)
    rendered = render_markdown(document)
    assert "redacted in this profile" in rendered
    assert "--include-local-details" in rendered


def test_markdown_in_local_mode_does_not_claim_redaction() -> None:
    document = audit_evidence_root(load_manifest(MANIFEST), EVIDENCE, include_local_details=True)
    rendered = render_markdown(document)
    assert "local_sensitive" in rendered
    assert "redacted in this profile" not in rendered
