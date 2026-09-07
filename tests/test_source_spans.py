"""An obligation's quotation must be in the document the manifest is bound to.

Before this, `Obligation.text` and `clause_ref` were validated only as
non-empty strings. `_parse_contract` opened the contract source and hashed it,
but never read a byte of it for content, so a receipt could carry a quotation
that appears nowhere in the source whose digest sits beside it -- a typo, a
paraphrase, a clause pasted from a superseded version, or a sentence nobody
agreed to -- and every existing check would pass.

These tests measure the binding rather than describing it, and they also pin
the compatibility half: `tests/fixtures/manifest-without-source-spans.toml` is
the example manifest exactly as it was written before spans existed, and it
must still normalize to the digest it normalized to then.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from obligation_receipts.cli import main
from obligation_receipts.evaluator import evaluate_manifest
from obligation_receipts.manifest import ManifestError, load_manifest
from obligation_receipts.models import JsonValue, Manifest
from obligation_receipts.plan import EvidencePlanError, build_evidence_plan, verify_evidence_plan
from obligation_receipts.receipt import ReceiptError, build_receipt, verify_receipt

_FIXTURES = Path(__file__).parent / "fixtures"

#: What `examples/accessibility-acceptance/obligations.toml` normalized to
#: before any obligation declared a span. A manifest that declares none must
#: still produce exactly this, because `source_span` is emitted into the
#: normalized document only when one is present. If this literal ever has to
#: move, every manifest written against schema v0.1 has been invalidated and
#: every attestation bound to one stops binding.
_PRE_SPANS_MANIFEST_SHA256 = "90f93af731b3e65d4430d96710b6dae199684fc6d9b0cde4854183f8c74a54f9"


def _replace(path: Path, old: str, new: str) -> None:
    content = path.read_text(encoding="utf-8")
    assert old in content, old
    path.write_text(content.replace(old, new, 1), encoding="utf-8")


def _span_free(copied_example: Path) -> Path:
    """The example as it was authored before spans, over the same source file."""
    manifest_path = copied_example / "obligations.toml"
    shutil.copyfile(_FIXTURES / "manifest-without-source-spans.toml", manifest_path)
    return manifest_path


def test_every_example_obligation_quotes_bytes_that_are_really_in_the_source(
    example_manifest: Path,
) -> None:
    manifest = load_manifest(example_manifest)
    source = (example_manifest.parent / manifest.contract.source_path).read_bytes()
    assert manifest.source_spans_declared == 4
    for obligation in manifest.obligations:
        span = obligation.source_span
        assert span is not None, obligation.obligation_id
        quoted = source[span.offset : span.offset + span.length]
        assert quoted == obligation.text.encode("utf-8"), obligation.obligation_id
        assert hashlib.sha256(quoted).hexdigest() == span.sha256, obligation.obligation_id


def test_one_changed_character_in_the_text_is_a_load_time_error_naming_the_obligation(
    copied_example: Path,
) -> None:
    """The whole point: the paraphrase that nothing used to catch."""
    _replace(
        copied_example / "obligations.toml",
        "violations in the approved acceptance run.",
        "violations in the approved acceptance runs.",
    )
    with pytest.raises(ManifestError, match="a1-zero-critical-violations") as error:
        load_manifest(copied_example / "obligations.toml")
    assert "normalization is applied" in str(error.value)


def test_a_plausible_paraphrase_is_refused_even_though_it_reads_correctly(
    copied_example: Path,
) -> None:
    """A clause reworded into better English is exactly the failure mode.

    Nothing about this sentence looks wrong. It says what the source says. It
    is not what the source says, and a counterparty reading the receipt cannot
    tell the difference without the document in front of them.
    """
    _replace(
        copied_example / "obligations.toml",
        "The supplier must provide a current external accessibility conformance\n"
        "report for the delivered release.",
        "The supplier shall provide a current external accessibility conformance\n"
        "report for the delivered release.",
    )
    with pytest.raises(ManifestError, match="a3-external-acr"):
        load_manifest(copied_example / "obligations.toml")


def test_a_span_running_past_the_end_of_the_source_is_refused_before_anything_is_evaluated(
    copied_example: Path,
) -> None:
    _replace(
        copied_example / "obligations.toml",
        "offset = 412, length = 32",
        "offset = 440, length = 32",
    )
    with pytest.raises(ManifestError, match="runs past the end of the contract source"):
        load_manifest(copied_example / "obligations.toml")


def test_a_span_whose_digest_does_not_match_the_bytes_it_points_at_is_refused(
    copied_example: Path,
) -> None:
    _replace(
        copied_example / "obligations.toml",
        "d7f9f8acb55a600dea17b14206cb7bce1f46b38384251fcc0f6a6682bbfa4b9b",
        "0" * 64,
    )
    with pytest.raises(ManifestError, match="digest does not match the bytes it points at"):
        load_manifest(copied_example / "obligations.toml")


#: The A-4 span exactly as the example declares it, and the spellings that
#: replace it. A structural defect must be refused before anything tries to
#: compare bytes, so several of these carry a `sha256` that could not possibly
#: match.
_A4_SPAN = (
    "offset = 412, length = 32, "
    'sha256 = "d7f9f8acb55a600dea17b14206cb7bce1f46b38384251fcc0f6a6682bbfa4b9b"'
)


@pytest.mark.parametrize(
    ("replacement", "message"),
    [
        ('length = 32, sha256 = "0"', "missing field"),
        ('offset = 412, length = 32, sha256 = "0", note = "x"', "unknown field"),
        ('offset = 412, length = 0, sha256 = "0"', "at least one byte"),
        ('offset = 412, length = 32, sha256 = "not-a-digest"', "SHA-256 digest"),
        ('offset = -1, length = 32, sha256 = "0"', "non-negative integer byte count"),
        ('offset = true, length = 32, sha256 = "0"', "non-negative integer byte count"),
        ('offset = "412", length = 32, sha256 = "0"', "non-negative integer byte count"),
        ('offset = 412, length = "32", sha256 = "0"', "non-negative integer byte count"),
    ],
)
def test_a_malformed_span_declaration_is_an_authoring_defect(
    copied_example: Path,
    replacement: str,
    message: str,
) -> None:
    """Every one of these is refused as a `ManifestError`, never as an observed `fail`."""
    manifest_path = copied_example / "obligations.toml"
    _replace(manifest_path, _A4_SPAN, replacement)
    with pytest.raises(ManifestError, match=message):
        load_manifest(manifest_path)


def test_a_span_that_is_not_a_table_is_refused(copied_example: Path) -> None:
    _replace(
        copied_example / "obligations.toml",
        f"source_span = {{ {_A4_SPAN} }}",
        'source_span = "412:32"',
    )
    with pytest.raises(ManifestError, match="must be a table"):
        load_manifest(copied_example / "obligations.toml")


def test_a_manifest_declaring_no_spans_normalizes_to_exactly_what_it_did_before(
    copied_example: Path,
) -> None:
    """The compatibility claim, pinned rather than asserted in prose."""
    manifest = load_manifest(_span_free(copied_example))
    assert manifest.source_spans_declared == 0
    assert manifest.manifest_sha256 == _PRE_SPANS_MANIFEST_SHA256
    assert all(item.source_span is None for item in manifest.obligations)
    assert all("source_span" not in item.to_dict() for item in manifest.obligations)


def test_a_receipt_for_a_span_free_manifest_carries_no_span_member(
    copied_example: Path,
) -> None:
    manifest = load_manifest(_span_free(copied_example))
    receipt = build_receipt(
        evaluate_manifest(manifest, copied_example / "evidence"),
        generated_at="2026-01-01T00:00:00+00:00",
    )
    payload = receipt["payload"]
    assert isinstance(payload, dict)
    obligations = payload["obligations"]
    assert isinstance(obligations, list)
    assert all(isinstance(item, dict) and "source_span" not in item for item in obligations)
    assert verify_receipt(receipt) == receipt["payload_sha256"]


def _example_receipt(example_manifest: Path) -> dict[str, JsonValue]:
    manifest = load_manifest(example_manifest)
    return build_receipt(
        evaluate_manifest(manifest, example_manifest.parent / "evidence"),
        generated_at="2026-01-01T00:00:00+00:00",
    )


def test_a_receipt_carries_the_span_so_replay_can_recheck_it(example_manifest: Path) -> None:
    receipt = _example_receipt(example_manifest)
    payload = receipt["payload"]
    assert isinstance(payload, dict)
    obligations = payload["obligations"]
    assert isinstance(obligations, list)
    spans = [item["source_span"] for item in obligations if isinstance(item, dict)]
    assert spans == [
        {
            "length": 112,
            "offset": 54,
            "sha256": "cde928ac14922fe02bebba48e2434a1c4d48117baf6f1cd209f65711c7bd9bec",
        },
        {
            "length": 121,
            "offset": 173,
            "sha256": "e5039c65405436de326a5f36e865565dd68f430fa1b552e3d110f91a995a441a",
        },
        {
            "length": 104,
            "offset": 301,
            "sha256": "3f9a448c1d41ac588b51eb29a85ec7881c1f71f4c23b782e24c7f59b3cba9efb",
        },
        {
            "length": 32,
            "offset": 412,
            "sha256": "d7f9f8acb55a600dea17b14206cb7bce1f46b38384251fcc0f6a6682bbfa4b9b",
        },
    ]
    assert verify_receipt(receipt) == receipt["payload_sha256"]


@pytest.mark.parametrize(
    ("span", "message"),
    [
        (None, "closed schema"),
        ({"length": 32, "offset": 412}, "closed schema"),
        ({"length": 0, "offset": 412, "sha256": "0" * 64}, "at least one byte"),
        ({"length": 32, "offset": -1, "sha256": "0" * 64}, "non-negative integer byte count"),
        ({"length": True, "offset": 412, "sha256": "0" * 64}, "non-negative integer byte count"),
        ({"length": 32, "offset": 412, "sha256": "nope"}, "SHA-256 digest"),
    ],
)
def test_a_receipt_span_that_cannot_be_rechecked_is_refused(
    example_manifest: Path,
    span: JsonValue,
    message: str,
) -> None:
    """`None` is in this table on purpose.

    A present-and-null member is not the same document as an absent one -- it
    digests differently -- and a receipt that carries the member is asserting a
    binding, so a null is refused rather than quietly read as "no span".
    """
    receipt = _example_receipt(example_manifest)
    payload = receipt["payload"]
    assert isinstance(payload, dict)
    obligations = payload["obligations"]
    assert isinstance(obligations, list)
    first = obligations[0]
    assert isinstance(first, dict)
    first["source_span"] = span
    with pytest.raises(ReceiptError, match=message):
        verify_receipt(receipt)


def test_the_portable_plan_redacts_the_span_and_the_local_plan_carries_it(
    example_manifest: Path,
) -> None:
    """A span offset is a locator into the source, so it is redacted with the rest."""
    manifest = load_manifest(example_manifest)
    portable = build_evidence_plan(manifest)["payload"]
    local = build_evidence_plan(manifest, include_local_details=True)["payload"]
    assert isinstance(portable, dict)
    assert isinstance(local, dict)
    portable_obligations = portable["obligations"]
    local_obligations = local["obligations"]
    assert isinstance(portable_obligations, list)
    assert isinstance(local_obligations, list)
    assert all(
        isinstance(item, dict) and item["source_span"] is None for item in portable_obligations
    )
    assert all(
        isinstance(item, dict) and isinstance(item["source_span"], dict)
        for item in local_obligations
    )


def test_a_portable_plan_that_leaks_a_span_fails_verification(example_manifest: Path) -> None:
    plan = build_evidence_plan(load_manifest(example_manifest))
    payload = plan["payload"]
    assert isinstance(payload, dict)
    obligations = payload["obligations"]
    assert isinstance(obligations, list)
    first = obligations[0]
    assert isinstance(first, dict)
    first["source_span"] = {"length": 112, "offset": 54, "sha256": "0" * 64}
    with pytest.raises(EvidencePlanError, match="source_span must be redacted"):
        verify_evidence_plan(plan)


@pytest.mark.parametrize(
    ("span", "message"),
    [
        (None, "closed schema"),
        ({"length": 0, "offset": 54, "sha256": "0" * 64}, "at least one byte"),
        ({"length": 112, "offset": True, "sha256": "0" * 64}, "non-negative integer byte count"),
        ({"length": 112, "offset": 54, "sha256": "nope"}, "SHA-256 digest"),
    ],
)
def test_a_local_plan_with_an_unusable_span_fails_verification(
    example_manifest: Path,
    span: JsonValue,
    message: str,
) -> None:
    plan = build_evidence_plan(load_manifest(example_manifest), include_local_details=True)
    payload = plan["payload"]
    assert isinstance(payload, dict)
    obligations = payload["obligations"]
    assert isinstance(obligations, list)
    first = obligations[0]
    assert isinstance(first, dict)
    first["source_span"] = span
    with pytest.raises(EvidencePlanError, match=message):
        verify_evidence_plan(plan)


def test_a_plan_from_a_span_free_manifest_has_no_span_member_at_all(
    copied_example: Path,
) -> None:
    manifest: Manifest = load_manifest(_span_free(copied_example))
    for include_local_details in (False, True):
        payload = build_evidence_plan(manifest, include_local_details=include_local_details)[
            "payload"
        ]
        assert isinstance(payload, dict)
        obligations = payload["obligations"]
        assert isinstance(obligations, list)
        assert all(isinstance(item, dict) and "source_span" not in item for item in obligations)


def test_validate_reports_the_declared_span_count_including_zero(
    copied_example: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Zero is reported, not inferred from the absence of an error."""
    assert main(["validate", str(copied_example / "obligations.toml")]) == 0
    assert json.loads(capsys.readouterr().out)["source_spans_declared"] == 4
    assert main(["validate", str(_span_free(copied_example))]) == 0
    assert json.loads(capsys.readouterr().out)["source_spans_declared"] == 0


def test_verify_reports_null_when_no_manifest_was_supplied_to_check_spans_against(
    copied_example: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Not-checked and none-declared are different facts and are rendered differently."""
    receipt_path = tmp_path / "receipt.json"
    assert (
        main(
            [
                "evaluate",
                str(copied_example / "obligations.toml"),
                "--evidence-root",
                str(copied_example / "evidence"),
                "--out",
                str(receipt_path),
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert main(["verify", str(receipt_path)]) == 0
    assert json.loads(capsys.readouterr().out)["source_spans_verified"] is None

    assert (
        main(
            [
                "verify",
                str(receipt_path),
                "--manifest",
                str(copied_example / "obligations.toml"),
                "--evidence-root",
                str(copied_example / "evidence"),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["source_spans_verified"] == 4


def test_editing_the_source_after_a_receipt_was_issued_is_caught_at_replay(
    copied_example: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The contract digest catches this first, which is the point.

    A span cannot be the thing that notices an edited source, because the
    manifest is already bound to the source by digest and refuses to load at
    all. This test exists so that ordering is recorded rather than assumed:
    the span check is about the *quotation*, not about the document's identity.
    """
    receipt_path = tmp_path / "receipt.json"
    assert (
        main(
            [
                "evaluate",
                str(copied_example / "obligations.toml"),
                "--evidence-root",
                str(copied_example / "evidence"),
                "--out",
                str(receipt_path),
            ]
        )
        == 0
    )
    capsys.readouterr()
    source = copied_example / "source" / "section-508-acceptance.txt"
    source.write_text(source.read_text(encoding="utf-8") + "\nA-5. Nothing.\n", encoding="utf-8")
    assert (
        main(
            [
                "verify",
                str(receipt_path),
                "--manifest",
                str(copied_example / "obligations.toml"),
                "--evidence-root",
                str(copied_example / "evidence"),
            ]
        )
        == 2
    )
    assert "source digest does not match" in capsys.readouterr().err
