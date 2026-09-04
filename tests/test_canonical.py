import copy
from pathlib import Path

import pytest

from obligation_receipts.canonical import (
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


def test_json_node_budget_is_exactly_one_hundred_thousand_nodes() -> None:
    """Pin the node cap with literals, because the constant cannot pin itself.

    This test used to build its input from `MAX_JSON_NODES` -- the very
    constant it was checking -- so it passed for any value of it. Raising the
    cap a thousandfold left the suite green and merely slower, which is exactly
    the change a node cap exists to prevent.

    A list contributes one node for itself plus one per member, so `99_999`
    members is exactly the 100,000-node budget and `100_000` members is one
    over. Stating both halves as literals means moving the constant in either
    direction fails one of them.
    """
    inside = [None] * 99_999
    assert validate_json_value(inside) is inside

    with pytest.raises(StrictJsonError, match="node limit"):
        validate_json_value([None] * 100_000)


def test_validate_json_value_accepts_finite_floats() -> None:
    # validate_json_value returns the exact same object it was given, not a
    # rebuilt copy, so comparing the result to `data` itself is tautological
    # (data == data is always true) and can't detect the traversal silently
    # corrupting a nested value. Comparing against an independent snapshot
    # taken *before* the call actually exercises that nothing changed.
    data = {"score": 0.5, "values": [12.0, -3.14, 0.0]}
    snapshot = copy.deepcopy(data)
    assert validate_json_value(data) == snapshot


def test_canonical_json_bytes_formats_finite_floats() -> None:
    data = {"score": 0.5, "values": [12.0, -3.14, 0.0]}
    assert canonical_json_bytes(data) == b'{"score":0.5,"values":[12.0,-3.14,0.0]}'
