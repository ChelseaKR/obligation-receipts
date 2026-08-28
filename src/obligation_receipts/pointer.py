"""RFC 6901 JSON pointer syntax and resolution.

One definition, used by manifest loading, evidence-plan validation, and
evaluation, so those three commands can never disagree about whether a pointer
is well formed. Before this module existed, `manifest.py` checked only the
leading `/`, `plan.py` carried a partial copy that checked escape correctness
alone, and `evaluator.py` held the only complete implementation -- reached far
too late, after a manifest defect had already become an observed `fail`.
"""

from __future__ import annotations

from obligation_receipts.canonical import MAX_JSON_NODES
from obligation_receipts.models import JsonValue

_ESCAPES = {"0": "~", "1": "/"}


def decode_reference_token(segment: str) -> str | None:
    """Decode one RFC 6901 reference token, or return None when it is malformed.

    `~` must be followed by `0` or `1`; every other use of `~`, including a
    trailing one, has no meaning and can never match a JSON member name.
    """
    decoded: list[str] = []
    index = 0
    while index < len(segment):
        character = segment[index]
        if character != "~":
            decoded.append(character)
            index += 1
            continue
        escape = segment[index + 1] if index + 1 < len(segment) else ""
        if escape not in _ESCAPES:
            return None
        decoded.append(_ESCAPES[escape])
        index += 2
    return "".join(decoded)


def is_well_formed(pointer: str) -> bool:
    """Report whether a string is syntactically a JSON pointer (RFC 6901 section 3).

    A pointer is either the empty string or a sequence of `/`-prefixed
    reference tokens.

    Canonical array-index form (`0` or `[1-9][0-9]*`) is deliberately not part
    of this check. RFC 6901 section 4 makes a non-canonical index an error only
    when the pointer is evaluated against an array; a segment such as `00` is a
    legal reference token that addresses an object member literally named
    `00`. Treating it as a syntax error would reject a manifest that real
    evidence can satisfy, so it stays a runtime non-match instead. See
    `canonical_array_index`.
    """
    if pointer == "":
        return True
    if not pointer.startswith("/"):
        return False
    return all(
        decode_reference_token(segment) is not None
        for segment in pointer.removeprefix("/").split("/")
    )


def canonical_array_index(segment: str) -> int | None:
    """Return the array index a decoded segment addresses, or None when it addresses none.

    Bounded by the strict-JSON node ceiling so that an arbitrarily long digit
    run cannot be converted at all.
    """
    if segment == "0":
        return 0
    if not segment or segment[0] not in "123456789":
        return None
    if any(character not in "0123456789" for character in segment[1:]):
        return None
    if len(segment) > len(str(MAX_JSON_NODES)):
        return None
    return int(segment)


def resolve(document: JsonValue, pointer: str) -> tuple[bool, JsonValue | None]:
    """Resolve a pointer against a document, reporting whether it was found.

    A found value may itself be JSON `null`, which is why the found flag is
    returned separately rather than inferred from the value.
    """
    current: JsonValue = document
    if pointer == "":
        return True, current
    if not pointer.startswith("/"):
        return False, None
    for segment in pointer.removeprefix("/").split("/"):
        key = decode_reference_token(segment)
        if key is None:
            return False, None
        if isinstance(current, dict):
            if key not in current:
                return False, None
            current = current[key]
        elif isinstance(current, list):
            index = canonical_array_index(key)
            if index is None or index >= len(current):
                return False, None
            current = current[index]
        else:
            return False, None
    return True, current
