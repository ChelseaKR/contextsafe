"""Canonical JSON and SHA-256 helpers for deterministic artifacts."""

import hashlib
import json
from collections.abc import Mapping, Sequence

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]


def canonical_json(value: JsonValue) -> str:
    """Serialize a JSON value with stable key ordering and no whitespace."""

    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def sha256_json(value: JsonValue) -> str:
    """Hash the UTF-8 bytes of a canonical JSON value."""

    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def as_json_value(value: object) -> JsonValue:
    """Narrow recursively constructed objects to the supported JSON domain."""

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        result: dict[str, JsonValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("JSON object keys must be strings")
            result[key] = as_json_value(item)
        return result
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [as_json_value(item) for item in value]
    raise TypeError("value is outside the supported JSON domain")
