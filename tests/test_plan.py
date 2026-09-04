import json
from pathlib import Path

import pytest

from obligation_receipts.canonical import canonical_json_bytes, sha256_bytes
from obligation_receipts.manifest import ManifestError, load_manifest
from obligation_receipts.models import JsonValue
from obligation_receipts.plan import (
    EvidencePlanError,
    build_evidence_plan,
    load_evidence_plan,
    verify_evidence_plan,
    write_evidence_plan,
)
from obligation_receipts.receipt import ReceiptError, load_receipt, verify_receipt


def _payload(plan: dict[str, JsonValue]) -> dict[str, JsonValue]:
    payload = plan["payload"]
    assert isinstance(payload, dict)
    return payload


def _obligations(plan: dict[str, JsonValue]) -> list[JsonValue]:
    obligations = _payload(plan)["obligations"]
    assert isinstance(obligations, list)
    return obligations


def _rehash(plan: dict[str, JsonValue]) -> None:
    plan["payload_sha256"] = sha256_bytes(canonical_json_bytes(plan["payload"]))


def _replace(path: Path, old: str, new: str) -> None:
    content = path.read_text(encoding="utf-8")
    assert old in content
    path.write_text(content.replace(old, new, 1), encoding="utf-8")


def test_portable_plan_is_deterministic_redacted_and_actionable(
    example_manifest: Path,
) -> None:
    manifest = load_manifest(example_manifest)
    first = build_evidence_plan(manifest)
    second = build_evidence_plan(manifest)
    assert first == second
    assert verify_evidence_plan(first) == first["payload_sha256"]
    payload = _payload(first)
    assert payload["manifest_sha256"] == manifest.manifest_sha256
    assert payload["source_sha256"] == manifest.contract.source_sha256
    assert payload["detail_mode"] == "portable_redacted"
    assert payload["evidence_observed"] is False
    assert payload["limitations"] == {
        "approval_authenticated": False,
        "completeness_proven": False,
        "evidence_sufficiency_assessed": False,
        "legal_interpretation_performed": False,
        "official_decision_made": False,
    }
    obligations = _obligations(first)
    assert len(obligations) == 4
    for obligation in obligations[:-1]:
        assert isinstance(obligation, dict)
        assert obligation["combination_rule"] == "all_required"
        assert obligation["source_locator"] is None
        requirements = obligation["evidence_requirements"]
        assert isinstance(requirements, list)
        for requirement in requirements:
            assert isinstance(requirement, dict)
            assert requirement["path"] is None
    automated = obligations[0]
    assert isinstance(automated, dict)
    requirements = automated["evidence_requirements"]
    assert isinstance(requirements, list)
    assertion_requirement = requirements[0]
    assert isinstance(assertion_requirement, dict)
    assert assertion_requirement["assertion"] == {
        "expected": 0,
        "expected_declared": True,
        "operator": "eq",
        "pointer": "/summary/critical_violations",
    }
    unverifiable = obligations[-1]
    assert isinstance(unverifiable, dict)
    assert unverifiable["classification"] == "unverifiable"
    assert unverifiable["combination_rule"] == "not_applicable"
    assert unverifiable["no_evidence_reason"] == "no_evaluable_evidence_declared"
    assert unverifiable["evidence_requirements"] == []
    encoded = canonical_json_bytes(first)
    assert b"The delivered service must have" not in encoded
    assert b"Agency acceptance lead" not in encoded


def test_local_plan_includes_declared_sensitive_collection_details(
    example_manifest: Path,
) -> None:
    plan = build_evidence_plan(load_manifest(example_manifest), include_local_details=True)
    payload = _payload(plan)
    assert payload["detail_mode"] == "local_sensitive"
    obligations = _obligations(plan)
    first = obligations[0]
    assert isinstance(first, dict)
    assert first["source_locator"] == "A-1"
    evidence = first["evidence_requirements"]
    assert isinstance(evidence, list)
    assert isinstance(evidence[0], dict)
    assert evidence[0]["path"] == "automated/axe-summary.json"
    last = obligations[-1]
    assert isinstance(last, dict)
    assert last["no_evidence_reason"] == (
        "No population, task, method, threshold, or accountable reviewer is defined."
    )
    assert verify_evidence_plan(plan, load_manifest(example_manifest)) == plan["payload_sha256"]


def test_attestation_plan_declares_exact_binding(example_manifest: Path) -> None:
    manifest = load_manifest(example_manifest)
    plan = build_evidence_plan(manifest)
    manual = _obligations(plan)[1]
    assert isinstance(manual, dict)
    requirements = manual["evidence_requirements"]
    assert isinstance(requirements, list)
    item = requirements[0]
    assert isinstance(item, dict)
    binding = item["attestation_binding"]
    assert isinstance(binding, dict)
    assert binding["allowed_statuses"] == ["pass", "fail"]
    assert binding["fixed_values"] == {
        "contract_id": manifest.contract.contract_id,
        "contract_version": manifest.contract.version,
        "evidence_id": "a2-review-attestation",
        "manifest_sha256": manifest.manifest_sha256,
        "obligation_id": "a2-human-workflow-review",
        "schema_version": "obligation-receipts/attestation/v0.1",
    }
    assert binding["required_fields"] == [
        "schema_version",
        "contract_id",
        "contract_version",
        "manifest_sha256",
        "obligation_id",
        "evidence_id",
        "status",
        "reviewer",
        "reviewed_at",
        "method",
    ]


def test_plan_does_not_read_or_hash_evidence(copied_example: Path) -> None:
    manifest = load_manifest(copied_example / "obligations.toml")
    before = build_evidence_plan(manifest)
    for artifact in (copied_example / "evidence").rglob("*.json"):
        artifact.write_text("changed or absent", encoding="utf-8")
    assert build_evidence_plan(manifest) == before
    for artifact in (copied_example / "evidence").rglob("*.json"):
        artifact.unlink()
    assert build_evidence_plan(manifest) == before


def test_portable_plan_redacts_manifest_local_metadata(copied_example: Path) -> None:
    manifest_path = copied_example / "obligations.toml"
    locator_marker = "SENSITIVE_LOCATOR_47"
    path_marker = "SENSITIVE_PATH_47.json"
    reason_marker = "SENSITIVE_REASON_47"
    _replace(manifest_path, 'clause_ref = "A-1"', f'clause_ref = "{locator_marker}"')
    _replace(
        manifest_path,
        'path = "automated/axe-summary.json"',
        f'path = "{path_marker}"',
    )
    _replace(
        manifest_path,
        'reason = "No population, task, method, threshold, or accountable reviewer is defined."',
        f'reason = "{reason_marker}"',
    )
    plan = build_evidence_plan(load_manifest(manifest_path))
    encoded = canonical_json_bytes(plan).decode("utf-8")
    assert locator_marker not in encoded
    assert path_marker not in encoded
    assert reason_marker not in encoded


def test_exact_regeneration_detects_stale_or_other_manifest(copied_example: Path) -> None:
    manifest_path = copied_example / "obligations.toml"
    original_manifest = load_manifest(manifest_path)
    plan = build_evidence_plan(original_manifest)
    _replace(manifest_path, 'owner = "Accessibility lead"', 'owner = "Changed owner"')
    changed_manifest = load_manifest(manifest_path)
    assert changed_manifest.manifest_sha256 != original_manifest.manifest_sha256
    with pytest.raises(EvidencePlanError, match="exact manifest regeneration"):
        verify_evidence_plan(plan, changed_manifest)
    assert verify_evidence_plan(plan, original_manifest) == plan["payload_sha256"]


@pytest.mark.parametrize("field", ["source_locator", "path", "reason"])
def test_local_sensitive_rehashed_metadata_requires_exact_regeneration(
    example_manifest: Path,
    field: str,
) -> None:
    manifest = load_manifest(example_manifest)
    plan = build_evidence_plan(manifest, include_local_details=True)
    obligations = _obligations(plan)
    if field == "source_locator":
        first = obligations[0]
        assert isinstance(first, dict)
        first["source_locator"] = "changed-locator"
    elif field == "path":
        first = obligations[0]
        assert isinstance(first, dict)
        requirements = first["evidence_requirements"]
        assert isinstance(requirements, list)
        item = requirements[0]
        assert isinstance(item, dict)
        item["path"] = "changed/artifact.json"
    else:
        last = obligations[-1]
        assert isinstance(last, dict)
        last["no_evidence_reason"] = "changed reason"
    _rehash(plan)
    assert verify_evidence_plan(plan) == plan["payload_sha256"]
    with pytest.raises(EvidencePlanError, match="exact manifest regeneration"):
        verify_evidence_plan(plan, manifest)


def test_source_mutation_blocks_manifest_regeneration(copied_example: Path) -> None:
    source = copied_example / "source" / "section-508-acceptance.txt"
    source.write_text("changed source", encoding="utf-8")
    with pytest.raises(ManifestError, match="source digest does not match"):
        load_manifest(copied_example / "obligations.toml")


def test_write_load_and_symlink_replacement_are_safe(
    tmp_path: Path,
    example_manifest: Path,
) -> None:
    plan = build_evidence_plan(load_manifest(example_manifest))
    target = tmp_path / "outside.json"
    target.write_text("do not overwrite", encoding="utf-8")
    output = tmp_path / "nested" / "plan.json"
    output.parent.mkdir()
    output.symlink_to(target)
    predictable = output.with_suffix(".json.tmp")
    predictable.write_text("sentinel", encoding="utf-8")
    write_evidence_plan(output, plan)
    assert not output.is_symlink()
    assert target.read_text(encoding="utf-8") == "do not overwrite"
    assert predictable.read_text(encoding="utf-8") == "sentinel"
    assert load_evidence_plan(output, load_manifest(example_manifest)) == plan


def test_plan_replace_failure_preserves_destination_and_cleans_temp(
    tmp_path: Path,
    example_manifest: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "plan.json"
    destination.write_text("existing", encoding="utf-8")

    def fail_replace(source: Path, target: Path) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr("obligation_receipts.plan.os.replace", fail_replace)
    plan = build_evidence_plan(load_manifest(example_manifest))
    with pytest.raises(OSError, match="simulated"):
        write_evidence_plan(destination, plan)
    assert destination.read_text(encoding="utf-8") == "existing"
    assert sorted(tmp_path.iterdir()) == [destination]


def test_tamper_without_rehash_is_rejected(example_manifest: Path) -> None:
    plan = build_evidence_plan(load_manifest(example_manifest))
    first = _obligations(plan)[0]
    assert isinstance(first, dict)
    requirements = first["evidence_requirements"]
    assert isinstance(requirements, list)
    item = requirements[0]
    assert isinstance(item, dict)
    assertion = item["assertion"]
    assert isinstance(assertion, dict)
    assertion["expected"] = 1
    with pytest.raises(EvidencePlanError, match="digest mismatch"):
        verify_evidence_plan(plan)


def test_rehashed_plan_cannot_add_claims_or_unredact_portable_fields(
    example_manifest: Path,
) -> None:
    plan = build_evidence_plan(load_manifest(example_manifest))
    payload = _payload(plan)
    limitations = payload["limitations"]
    assert isinstance(limitations, dict)
    limitations["official_decision_made"] = True
    _rehash(plan)
    with pytest.raises(EvidencePlanError, match="limitations"):
        verify_evidence_plan(plan)

    plan = build_evidence_plan(load_manifest(example_manifest))
    first = _obligations(plan)[0]
    assert isinstance(first, dict)
    first["source_locator"] = "secret"
    _rehash(plan)
    with pytest.raises(EvidencePlanError, match="redacted"):
        verify_evidence_plan(plan)


def test_rehashed_plan_rejects_inconsistent_requirements(example_manifest: Path) -> None:
    plan = build_evidence_plan(load_manifest(example_manifest))
    obligations = _obligations(plan)
    first = obligations[0]
    assert isinstance(first, dict)
    first["combination_rule"] = "any"
    _rehash(plan)
    with pytest.raises(EvidencePlanError, match="all_required"):
        verify_evidence_plan(plan)

    plan = build_evidence_plan(load_manifest(example_manifest))
    manual = _obligations(plan)[1]
    assert isinstance(manual, dict)
    requirements = manual["evidence_requirements"]
    assert isinstance(requirements, list)
    item = requirements[0]
    assert isinstance(item, dict)
    binding = item["attestation_binding"]
    assert isinstance(binding, dict)
    fixed = binding["fixed_values"]
    assert isinstance(fixed, dict)
    fixed["manifest_sha256"] = "0" * 64
    _rehash(plan)
    with pytest.raises(EvidencePlanError, match="fixed values"):
        verify_evidence_plan(plan)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("schema_version", "wrong", "payload schema"),
        ("decision_scope", "evidence_evaluated", "decision scope"),
        ("detail_mode", "public", "detail_mode"),
        ("evidence_observed", True, "evidence observation"),
        ("manifest_sha256", "bad", "SHA-256"),
        ("obligation_count", True, "obligation_count"),
    ],
)
def test_rehashed_plan_rejects_invalid_payload_header(
    example_manifest: Path,
    field: str,
    value: JsonValue,
    message: str,
) -> None:
    plan = build_evidence_plan(load_manifest(example_manifest))
    _payload(plan)[field] = value
    _rehash(plan)
    with pytest.raises(EvidencePlanError, match=message):
        verify_evidence_plan(plan)


def test_plan_document_and_obligation_shapes_are_closed(example_manifest: Path) -> None:
    plan = build_evidence_plan(load_manifest(example_manifest))
    plan["unexpected"] = False
    with pytest.raises(EvidencePlanError, match="closed schema"):
        verify_evidence_plan(plan)

    plan = build_evidence_plan(load_manifest(example_manifest))
    first = _obligations(plan)[0]
    assert isinstance(first, dict)
    first["text"] = "raw prose must not be added"
    _rehash(plan)
    with pytest.raises(EvidencePlanError, match="closed schema"):
        verify_evidence_plan(plan)


def test_rehashed_plan_rejects_duplicate_ids_and_invalid_unverifiable_state(
    example_manifest: Path,
) -> None:
    plan = build_evidence_plan(load_manifest(example_manifest))
    obligations = _obligations(plan)
    assert isinstance(obligations[0], dict)
    assert isinstance(obligations[-1], dict)
    obligations[-1]["id"] = obligations[0]["id"]
    _rehash(plan)
    with pytest.raises(EvidencePlanError, match="obligation ids must be unique"):
        verify_evidence_plan(plan)

    plan = build_evidence_plan(load_manifest(example_manifest))
    last = _obligations(plan)[-1]
    assert isinstance(last, dict)
    last["no_evidence_reason"] = None
    _rehash(plan)
    with pytest.raises(EvidencePlanError, match="unverifiable state"):
        verify_evidence_plan(plan)


def test_rehashed_plan_rejects_malformed_assertion_and_attestation(
    example_manifest: Path,
) -> None:
    plan = build_evidence_plan(load_manifest(example_manifest))
    first = _obligations(plan)[0]
    assert isinstance(first, dict)
    requirements = first["evidence_requirements"]
    assert isinstance(requirements, list)
    automated = requirements[0]
    assert isinstance(automated, dict)
    assertion = automated["assertion"]
    assert isinstance(assertion, dict)
    assertion["pointer"] = "/bad~2escape"
    _rehash(plan)
    with pytest.raises(EvidencePlanError, match="pointer is invalid"):
        verify_evidence_plan(plan)

    plan = build_evidence_plan(load_manifest(example_manifest))
    manual = _obligations(plan)[1]
    assert isinstance(manual, dict)
    requirements = manual["evidence_requirements"]
    assert isinstance(requirements, list)
    attestation = requirements[0]
    assert isinstance(attestation, dict)
    binding = attestation["attestation_binding"]
    assert isinstance(binding, dict)
    binding["allowed_statuses"] = ["pass", "unknown"]
    _rehash(plan)
    with pytest.raises(EvidencePlanError, match="statuses are not closed"):
        verify_evidence_plan(plan)


def test_programmatic_plan_is_bounded_json(example_manifest: Path) -> None:
    plan = build_evidence_plan(load_manifest(example_manifest))
    _payload(plan)["contract_version"] = float("nan")
    with pytest.raises(EvidencePlanError, match="bounded JSON"):
        verify_evidence_plan(plan)


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "../outside.json",
        r"..\outside.json",
        "/outside.json",
        r"C:\outside.json",
        "C:outside.json",
        "https://x",
        "./artifact.json",
        "dir//artifact.json",
        "dir/",
    ],
)
def test_manifest_rejects_unsafe_declared_evidence_path(
    copied_example: Path,
    unsafe_path: str,
) -> None:
    manifest_path = copied_example / "obligations.toml"
    toml_path = unsafe_path.replace("\\", "\\\\")
    _replace(
        manifest_path,
        'path = "automated/axe-summary.json"',
        f'path = "{toml_path}"',
    )
    with pytest.raises(ManifestError, match="path is unsafe"):
        load_manifest(manifest_path)


def test_exists_assertion_preserves_explicit_no_expected_state(copied_example: Path) -> None:
    manifest_path = copied_example / "obligations.toml"
    _replace(manifest_path, 'operator = "eq"', 'operator = "exists"')
    _replace(manifest_path, "expected = 0\n", "")
    plan = build_evidence_plan(load_manifest(manifest_path))
    first = _obligations(plan)[0]
    assert isinstance(first, dict)
    requirements = first["evidence_requirements"]
    assert isinstance(requirements, list)
    item = requirements[0]
    assert isinstance(item, dict)
    assert item["assertion"] == {
        "expected": None,
        "expected_declared": False,
        "operator": "exists",
        "pointer": "/summary/critical_violations",
    }


@pytest.mark.parametrize(
    "document",
    [
        b"\xff",
        b'{"x":NaN}',
        b'{"x":1,"x":2}',
        ("[" * 66 + "0" + "]" * 66).encode(),
    ],
)
def test_plan_loader_rejects_hostile_json(tmp_path: Path, document: bytes) -> None:
    path = tmp_path / "plan.json"
    path.write_bytes(document)
    with pytest.raises(EvidencePlanError, match="strict JSON"):
        load_evidence_plan(path)


def test_plan_loader_rejects_non_object_and_oversized(tmp_path: Path) -> None:
    path = tmp_path / "plan.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(EvidencePlanError, match="JSON object"):
        load_evidence_plan(path)
    path.write_bytes(b" " * (2 * 1024 * 1024 + 1))
    with pytest.raises(EvidencePlanError, match="safely"):
        load_evidence_plan(path)


def test_writer_rejects_oversized_but_self_consistent_plan(
    tmp_path: Path,
    example_manifest: Path,
) -> None:
    plan = build_evidence_plan(load_manifest(example_manifest), include_local_details=True)
    first = _obligations(plan)[0]
    assert isinstance(first, dict)
    first["source_locator"] = "x" * (2 * 1024 * 1024)
    _rehash(plan)
    with pytest.raises(EvidencePlanError, match="2 MiB"):
        write_evidence_plan(tmp_path / "plan.json", plan)


def test_evidence_plan_is_not_a_receipt(tmp_path: Path, example_manifest: Path) -> None:
    path = tmp_path / "plan.json"
    write_evidence_plan(path, build_evidence_plan(load_manifest(example_manifest)))
    loaded = load_receipt(path)
    with pytest.raises(ReceiptError, match="closed schema"):
        verify_receipt(loaded)


def test_serialized_plan_avoids_outcome_claims(example_manifest: Path) -> None:
    encoded = json.dumps(build_evidence_plan(load_manifest(example_manifest)))
    for forbidden in (
        '"overall_status"',
        '"status": "pass"',
        '"status": "fail"',
        '"accepted"',
        '"compliant"',
    ):
        assert forbidden not in encoded


def _requirement(plan: dict[str, JsonValue], index: int = 0) -> dict[str, JsonValue]:
    obligation = _obligations(plan)[index]
    assert isinstance(obligation, dict)
    requirements = obligation["evidence_requirements"]
    assert isinstance(requirements, list)
    requirement = requirements[0]
    assert isinstance(requirement, dict)
    return requirement


def test_portable_plan_cannot_smuggle_an_evidence_path_back_in(
    example_manifest: Path,
) -> None:
    """The redaction promise, enforced on verification and not only on generation.

    `portable_redacted` is the default and the profile the README calls safe to
    hand to someone else. Verification has to refuse a portable plan that
    carries a filesystem path, or the promise holds only for plans this tool
    happened to write itself.
    """
    plan = build_evidence_plan(load_manifest(example_manifest))
    _requirement(plan)["path"] = "automated/axe-summary.json"
    _rehash(plan)
    with pytest.raises(EvidencePlanError, match="must be redacted in portable mode"):
        verify_evidence_plan(plan)


def test_local_sensitive_plan_rejects_an_escaping_evidence_path(
    example_manifest: Path,
) -> None:
    plan = build_evidence_plan(load_manifest(example_manifest), include_local_details=True)
    _requirement(plan)["path"] = "../../etc/passwd"
    _rehash(plan)
    with pytest.raises(EvidencePlanError, match="remain inside the evidence root"):
        verify_evidence_plan(plan)


def test_plan_rejects_evidence_kind_that_contradicts_its_classification(
    example_manifest: Path,
) -> None:
    plan = build_evidence_plan(load_manifest(example_manifest))
    _requirement(plan)["kind"] = "review_attestation"
    _rehash(plan)
    with pytest.raises(EvidencePlanError, match="does not match its classification"):
        verify_evidence_plan(plan)


def test_plan_rejects_an_assertion_carrying_an_attestation_binding(
    example_manifest: Path,
) -> None:
    plan = build_evidence_plan(load_manifest(example_manifest))
    attestation = _requirement(plan, 1)
    _requirement(plan)["attestation_binding"] = attestation["attestation_binding"]
    _rehash(plan)
    with pytest.raises(EvidencePlanError, match="automated evidence cannot have a binding"):
        verify_evidence_plan(plan)


def test_plan_rejects_an_attestation_carrying_an_assertion(example_manifest: Path) -> None:
    plan = build_evidence_plan(load_manifest(example_manifest))
    _requirement(plan, 1)["assertion"] = _requirement(plan)["assertion"]
    _rehash(plan)
    with pytest.raises(EvidencePlanError, match="attestation evidence cannot have an assertion"):
        verify_evidence_plan(plan)


def test_plan_rejects_altered_attestation_required_fields(example_manifest: Path) -> None:
    """The required-field list is the collection instruction; it cannot be shortened."""
    plan = build_evidence_plan(load_manifest(example_manifest))
    binding = _requirement(plan, 1)["attestation_binding"]
    assert isinstance(binding, dict)
    fields = binding["required_fields"]
    assert isinstance(fields, list)
    binding["required_fields"] = fields[:-1]
    _rehash(plan)
    with pytest.raises(EvidencePlanError, match="required fields are inconsistent"):
        verify_evidence_plan(plan)


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("operator", "matches", "operator is unsupported"),
        ("expected_declared", False, "expected declaration is inconsistent"),
    ],
)
def test_plan_rejects_an_inconsistent_assertion(
    example_manifest: Path, key: str, value: JsonValue, message: str
) -> None:
    plan = build_evidence_plan(load_manifest(example_manifest))
    assertion = _requirement(plan)["assertion"]
    assert isinstance(assertion, dict)
    assertion[key] = value
    _rehash(plan)
    with pytest.raises(EvidencePlanError, match=message):
        verify_evidence_plan(plan)


def test_plan_rejects_an_expected_value_declared_absent(example_manifest: Path) -> None:
    plan = build_evidence_plan(load_manifest(example_manifest))
    assertion = _requirement(plan)["assertion"]
    assert isinstance(assertion, dict)
    assertion["operator"] = "exists"
    assertion["expected_declared"] = False
    _rehash(plan)
    with pytest.raises(EvidencePlanError, match="expected value is not allowed"):
        verify_evidence_plan(plan)


def test_plan_rejects_a_blank_required_string(example_manifest: Path) -> None:
    plan = build_evidence_plan(load_manifest(example_manifest))
    _requirement(plan)["id"] = "   "
    _rehash(plan)
    with pytest.raises(EvidencePlanError, match="must be a non-empty string"):
        verify_evidence_plan(plan)


def test_plan_rejects_an_unsupported_enum_value(example_manifest: Path) -> None:
    plan = build_evidence_plan(load_manifest(example_manifest))
    obligation = _obligations(plan)[0]
    assert isinstance(obligation, dict)
    obligation["criticality"] = "nice_to_have"
    _rehash(plan)
    with pytest.raises(EvidencePlanError, match="is unsupported"):
        verify_evidence_plan(plan)


def test_plan_rejects_non_array_requirements(example_manifest: Path) -> None:
    plan = build_evidence_plan(load_manifest(example_manifest))
    obligation = _obligations(plan)[0]
    assert isinstance(obligation, dict)
    obligation["evidence_requirements"] = "one item"
    _rehash(plan)
    with pytest.raises(EvidencePlanError, match="evidence_requirements must be an array"):
        verify_evidence_plan(plan)


def test_plan_rejects_an_evidenced_obligation_carrying_a_no_evidence_reason(
    example_manifest: Path,
) -> None:
    plan = build_evidence_plan(load_manifest(example_manifest))
    obligation = _obligations(plan)[0]
    assert isinstance(obligation, dict)
    obligation["no_evidence_reason"] = "no_evaluable_evidence_declared"
    _rehash(plan)
    with pytest.raises(EvidencePlanError, match="evidence requirements are inconsistent"):
        verify_evidence_plan(plan)


def test_plan_rejects_an_empty_obligation_array(example_manifest: Path) -> None:
    plan = build_evidence_plan(load_manifest(example_manifest))
    _payload(plan)["obligations"] = []
    _payload(plan)["obligation_count"] = 0
    _rehash(plan)
    with pytest.raises(EvidencePlanError, match="obligations must be a non-empty array"):
        verify_evidence_plan(plan)


def test_plan_rejects_evidence_ids_reused_across_obligations(example_manifest: Path) -> None:
    plan = build_evidence_plan(load_manifest(example_manifest))
    borrowed = _requirement(plan)["id"]
    reused = _requirement(plan, 1)
    reused["id"] = borrowed
    binding = reused["attestation_binding"]
    assert isinstance(binding, dict)
    fixed = binding["fixed_values"]
    assert isinstance(fixed, dict)
    fixed["evidence_id"] = borrowed
    _rehash(plan)
    with pytest.raises(EvidencePlanError, match="evidence ids must be unique"):
        verify_evidence_plan(plan)


def test_plan_generation_refuses_an_evidence_path_outside_the_root(
    copied_example: Path,
) -> None:
    """Generation refuses too, before a plan exists to verify.

    The manifest loader already rejects a traversal path, so this guard is only
    reachable if a future loader change lets one through; asserting it keeps
    the plan builder's own boundary from becoming untested dead weight.
    """
    manifest = load_manifest(copied_example / "obligations.toml")
    spec = manifest.obligations[0].evidence[0]
    object.__setattr__(spec, "path", "../outside.json")
    with pytest.raises(EvidencePlanError, match="remain inside the evidence root"):
        build_evidence_plan(manifest)


@pytest.mark.parametrize(
    ("location", "key"),
    [
        ("plan", "payload_sha256"),
        ("payload", "manifest_sha256"),
        ("payload", "source_sha256"),
    ],
)
def test_every_plan_digest_field_must_be_lowercase(
    example_manifest: Path,
    location: str,
    key: str,
) -> None:
    """The plan verifier only format-checks its digests, so the pattern is the rule.

    Relaxing `_SHA256_PATTERN` to case-insensitive survived the whole suite.
    Nothing here recomputes `manifest_sha256` or `source_sha256` from anything;
    they are copied out of the manifest and checked for shape alone. If the
    shape check accepted either case, the same manifest could be projected into
    several distinct plans, each with its own canonical `payload_sha256`, and
    every one of them verifying -- so a plan digest would stop identifying a
    plan.
    """
    plan = build_evidence_plan(load_manifest(example_manifest))
    holder = plan if location == "plan" else _payload(plan)
    original = holder[key]
    assert isinstance(original, str)
    assert original != original.upper()
    holder[key] = original.upper()
    if location != "plan":
        _rehash(plan)
    with pytest.raises(EvidencePlanError, match="must be a lowercase SHA-256 digest"):
        verify_evidence_plan(plan)


def test_plan_rejects_an_unsupported_document_schema(example_manifest: Path) -> None:
    plan = build_evidence_plan(load_manifest(example_manifest))
    plan["schema_version"] = "obligation-receipts/receipt/v0.1"
    with pytest.raises(EvidencePlanError, match="unsupported evidence plan document schema"):
        verify_evidence_plan(plan)
