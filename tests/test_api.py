import obligation_receipts


def test_public_library_api_remains_intentionally_small() -> None:
    assert obligation_receipts.__all__ == [
        "evaluate_manifest",
        "load_manifest",
        "verify_receipt",
    ]
