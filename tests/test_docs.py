from pathlib import Path


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
