"""Shared fail-closed primitives for governed envelope contracts."""

import ipaddress
import re
from datetime import date
from typing import cast

from contextsafe.errors import ContextSafeError

DATE_PATTERN = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
HOST_PATTERN = re.compile(
    r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)(?:\.(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?))*$"
)
ID_PATTERN = re.compile(r"^[A-Z][A-Z0-9-]{2,63}$")
RELATIVE_PATH_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*$")
SAFE_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:/_.-]{0,127}$")
SEMVER_PATTERN = re.compile(
    r"^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$"
)
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


def contract_error(code: str, path: str, message: str) -> ContextSafeError:
    """Build a value-minimized contract error."""

    return ContextSafeError(code=code, path=path, message=message)


def object_value(value: object, path: str) -> dict[str, object]:
    """Require a string-keyed JSON object."""

    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise contract_error("invalid_type", path, "expected a JSON object")
    return cast(dict[str, object], value)


def array_value(value: object, path: str) -> list[object]:
    """Require a JSON array."""

    if not isinstance(value, list):
        raise contract_error("invalid_type", path, "expected a JSON array")
    return cast(list[object], value)


def exact_keys(
    data: dict[str, object],
    required: frozenset[str],
    path: str,
    *,
    optional: frozenset[str] = frozenset(),
) -> None:
    """Reject unknown keys and report the first missing required key."""

    unexpected = data.keys() - required - optional
    if unexpected:
        raise contract_error("unknown_field", path, "field is not allowed")
    missing = sorted(required - data.keys())
    if missing:
        raise contract_error(
            "missing_field", f"{path}.{missing[0]}", "required field is missing"
        )


def bounded_string(
    value: object,
    path: str,
    *,
    pattern: re.Pattern[str] | None = None,
    max_length: int = 128,
) -> str:
    """Require a bounded Unicode-scalar string and, optionally, a full pattern."""

    if not isinstance(value, str) or not value or len(value) > max_length:
        raise contract_error(
            "invalid_string", path, "expected a bounded non-empty string"
        )
    if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
        raise contract_error(
            "invalid_unicode", path, "string must contain only Unicode scalar values"
        )
    if pattern is not None and pattern.fullmatch(value) is None:
        raise contract_error(
            "invalid_format", path, "string does not match the required format"
        )
    return value


def boolean_value(value: object, path: str) -> bool:
    """Require a JSON boolean without accepting integers."""

    if not isinstance(value, bool):
        raise contract_error("invalid_type", path, "expected a boolean")
    return value


def date_value(value: object, path: str) -> date:
    """Require a canonical ISO calendar date."""

    raw = bounded_string(value, path, pattern=DATE_PATTERN)
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise contract_error("invalid_date", path, "date is not valid") from exc


def nullable_date_value(value: object, path: str) -> date | None:
    """Require null or a canonical ISO calendar date."""

    if value is None:
        return None
    return date_value(value, path)


def enum_string(value: object, path: str, supported: frozenset[str]) -> str:
    """Require one supported string literal."""

    raw = bounded_string(value, path)
    if raw not in supported:
        raise contract_error("invalid_enum", path, "value is not supported")
    return raw


def relative_path_value(value: object, path: str) -> str:
    """Require a portable, traversal-free relative POSIX path."""

    raw = bounded_string(value, path, pattern=RELATIVE_PATH_PATTERN, max_length=256)
    if any(part in {"", ".", ".."} for part in raw.split("/")):
        raise contract_error(
            "invalid_path", path, "path must remain inside the pack directory"
        )
    return raw


def host_value(value: object, path: str) -> str:
    """Require a canonical lowercase DNS host, never a URL, wildcard, or IP."""

    raw = bounded_string(value, path, pattern=HOST_PATTERN, max_length=253)
    try:
        ipaddress.ip_address(raw)
    except ValueError:
        return raw
    raise contract_error("invalid_host", path, "IP addresses are not allowed")


def unique_strings(values: tuple[str, ...], path: str, *, code: str) -> None:
    """Reject duplicate identifiers while keeping values out of the error."""

    if len(values) != len(set(values)):
        raise contract_error(code, path, "values must be unique")
