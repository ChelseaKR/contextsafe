"""Bounded, strict JSON loading shared by offline ContextSafe commands."""

import json
from pathlib import Path
from typing import Any

from contextsafe.canonical import JsonValue, as_json_value
from contextsafe.errors import ContextSafeError

MAX_INPUT_BYTES = 1_048_576
MAX_JSON_DEPTH = 64


class _DuplicateKeyError(ValueError):
    """Signal that JSON contained a duplicate object member."""


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError
        result[key] = value
    return result


def _reject_nonstandard_number(_value: str) -> None:
    raise ValueError


def _reject_excessive_depth(value: object) -> None:
    stack: list[tuple[object, int]] = [(value, 0)]
    while stack:
        item, depth = stack.pop()
        if depth > MAX_JSON_DEPTH:
            raise ContextSafeError(
                "input_too_deep", "$", "input exceeds the JSON nesting limit"
            )
        if isinstance(item, dict):
            stack.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            stack.extend((child, depth + 1) for child in item)


def load_json(path: Path) -> JsonValue:
    """Load a bounded UTF-8 JSON value without duplicate keys or NaN values."""

    try:
        with path.open("rb") as handle:
            raw = handle.read(MAX_INPUT_BYTES + 1)
    except OSError as exc:
        raise ContextSafeError(
            "input_io_error", "$", "input could not be read"
        ) from exc
    if len(raw) > MAX_INPUT_BYTES:
        raise ContextSafeError(
            "input_too_large", "$", "input exceeds the one MiB limit"
        )
    try:
        parsed = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_no_duplicate_keys,
            parse_constant=_reject_nonstandard_number,
        )
    except UnicodeDecodeError as exc:
        raise ContextSafeError("invalid_utf8", "$", "input must be UTF-8") from exc
    except _DuplicateKeyError as exc:
        raise ContextSafeError(
            "duplicate_json_key", "$", "duplicate object key is forbidden"
        ) from exc
    except RecursionError as exc:
        raise ContextSafeError(
            "input_too_deep", "$", "input exceeds the JSON nesting limit"
        ) from exc
    except json.JSONDecodeError as exc:
        raise ContextSafeError("invalid_json", "$", "input is not valid JSON") from exc
    except ValueError as exc:
        raise ContextSafeError("invalid_json", "$", "input is not valid JSON") from exc
    _reject_excessive_depth(parsed)
    return as_json_value(parsed)
