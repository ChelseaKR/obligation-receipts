from pathlib import Path

import pytest

from obligation_receipts.canonical import (
    MAX_JSON_NODES,
    StrictJsonError,
    canonical_json_bytes,
    sha256_bytes,
    sha256_file,
    validate_json_value,
)


def test_canonical_json_is_stable() -> None:
    assert canonical_json_bytes({"b": 1, "a": "é"}) == b'{"a":"\xc3\xa9","b":1}'


def test_hash_helpers(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact"
    artifact.write_bytes(b"hello")
    expected = "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    assert sha256_bytes(b"hello") == expected
    assert sha256_file(artifact) == expected


def test_json_shape_rejects_excessive_node_count() -> None:
    with pytest.raises(StrictJsonError, match="node limit"):
        validate_json_value([None] * MAX_JSON_NODES)


def test_finite_floats_survive_validation_and_canonicalization() -> None:
    data = {"score": 0.5, "values": [12.0, -3.14, 0.0]}
    assert validate_json_value(data) == data
    assert canonical_json_bytes(data) == b'{"score":0.5,"values":[12.0,-3.14,0.0]}'

