"""Canonical serialization and content hashing."""

from __future__ import annotations

import hashlib
import json
from io import StringIO
from math import isfinite
from typing import IO, cast

from obligation_receipts.models import JsonValue

MAX_JSON_DEPTH = 64
MAX_JSON_NODES = 100_000


class StrictJsonError(ValueError):
    """Raised when JSON uses an ambiguous or non-interoperable extension."""


def _closed_object(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    value: dict[str, JsonValue] = {}
    for key, item in pairs:
        if key in value:
            raise StrictJsonError(f"duplicate JSON object key: {key}")
        value[key] = item
    return value


def _reject_non_finite(value: str) -> JsonValue:
    raise StrictJsonError(f"non-finite JSON number: {value}")


def validate_json_value(value: object) -> JsonValue:
    """Validate a bounded JSON-shaped value without recursive Python calls."""
    pending = [(value, 0)]
    nodes = 0
    while pending:
        item, depth = pending.pop()
        nodes += 1
        if nodes > MAX_JSON_NODES:
            raise StrictJsonError(f"JSON exceeds the {MAX_JSON_NODES}-node limit")
        if depth > MAX_JSON_DEPTH:
            raise StrictJsonError(f"JSON exceeds the {MAX_JSON_DEPTH}-level nesting limit")
        if item is None or isinstance(item, bool | int | str):
            continue
        if isinstance(item, float):
            if not isfinite(item):
                raise StrictJsonError("JSON contains a non-finite number")
            continue
        if isinstance(item, list):
            pending.extend((child, depth + 1) for child in item)
            continue
        if isinstance(item, dict) and all(isinstance(key, str) for key in item):
            pending.extend((child, depth + 1) for child in item.values())
            continue
        raise StrictJsonError(f"value of type {type(item).__name__} is not JSON")
    return cast(JsonValue, value)


def load_json_strict(handle: IO[str]) -> JsonValue:
    """Decode interoperable JSON, rejecting duplicate keys and non-finite numbers."""
    value = cast(
        object,
        json.load(
            handle,
            object_pairs_hook=_closed_object,
            parse_constant=_reject_non_finite,
        ),
    )
    return validate_json_value(value)


def loads_json_strict(data: bytes) -> JsonValue:
    """Decode bounded strict JSON bytes, translating invalid UTF-8 consistently."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise StrictJsonError("JSON is not valid UTF-8") from exc
    return load_json_strict(StringIO(text))


def canonical_json_bytes(value: object) -> bytes:
    """Serialize a JSON-shaped value deterministically."""
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    """Return a lowercase SHA-256 digest."""
    return hashlib.sha256(value).hexdigest()
