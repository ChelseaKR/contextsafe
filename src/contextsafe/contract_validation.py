"""Shared fail-closed primitives for governed envelope contracts."""

import ipaddress
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import cast

from contextsafe.errors import ContextSafeError

DATE_PATTERN = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
TIMESTAMP_PATTERN = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$"
)
HOST_PATTERN = re.compile(
    r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)(?:\.(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?))*$"
)
LEGACY_IP_PATTERN = re.compile(
    r"^(?:0x[0-9a-f]+|0[0-7]*|[0-9]+)"
    r"(?:\.(?:0x[0-9a-f]+|0[0-7]*|[0-9]+)){0,3}$"
)
ID_PATTERN = re.compile(r"^[A-Z][A-Z0-9-]{2,63}$")
RELATIVE_PATH_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*$")
SAFE_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:/_.-]{0,127}$")
SEMVER_PATTERN = re.compile(
    r"^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$"
)
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


@dataclass(frozen=True, slots=True)
class Grammar:
    """A published token grammar: one base shape and its named exclusions.

    Written as a base pattern plus exclusions rather than as one regular
    expression because the same strings are published in
    ``schemas/contextsafe-evidence-v1.schema.json`` as a ``pattern`` and a list
    of ``not`` clauses, and a reader has to be able to line the two up. Every
    string here is ECMA-262 syntax, with no inline flags, so it is valid in a
    JSON Schema ``pattern`` unchanged;
    ``tests/test_evidence_models.py`` asserts the schema carries these exact
    strings, so the code and the published contract cannot drift apart.
    """

    base: str
    exclusions: tuple[tuple[str, str], ...]
    max_length: int

    def compiled_base(self) -> re.Pattern[str]:
        return re.compile(self.base)

    def rejection(self, value: str) -> str | None:
        """Return why ``value`` is not in this grammar, or ``None``."""

        if (
            len(value) > self.max_length
            or self.compiled_base().fullmatch(value) is None
        ):
            return "does not match the published token shape"
        for expression, reason in self.exclusions:
            if re.search(expression, value) is not None:
                return reason
        return None


# A provenance label names a collector or a system. It is not free text: it is
# letter-initial, every separated segment begins with a letter, no run of four
# or more digits may appear, and neither a colon nor a slash is in the alphabet.
# Together those make a bare number, a date, a social security number, a
# telephone number and a URL scheme unwritable, so the boundary detectors in
# `identifiers` cannot fire on a value this grammar admits. See ADR 0006.
PROVENANCE_LABEL_GRAMMAR = Grammar(
    base=r"^[A-Za-z][A-Za-z0-9._-]*$",
    exclusions=(
        (r"[0-9]{4}", "carries a run of four or more digits"),
        (
            r"[._-](?![A-Za-z])",
            "has a separated segment that does not begin with a letter",
        ),
        (r"[Ww][Ww][Ww]\.", "carries a host label"),
    ),
    max_length=128,
)

# The same grammar, restricted to the upper-case alphabet `system_id` already
# published. A host label cannot be written at all without a lower-case letter
# or a dot, so that exclusion is absent rather than redundant.
PROVENANCE_SYSTEM_GRAMMAR = Grammar(
    base=r"^[A-Z][A-Z0-9-]*$",
    exclusions=(
        (r"[0-9]{4}", "carries a run of four or more digits"),
        (r"-(?![A-Z])", "has a separated segment that does not begin with a letter"),
    ),
    max_length=64,
)

# A version is a number, not a word. The base shape is the one
# `contextsafe.safe_value.VERSION_PATTERN` already requires of the version a
# support bundle may carry, for the reason recorded there: a pattern that merely
# forbade spaces accepted `exports-Jordan-Rivera-1987` as a version string.
PROVENANCE_VERSION_GRAMMAR = Grammar(
    base=r"^[0-9]+(?:\.[0-9]+){0,3}(?:[-+][A-Za-z0-9.]{1,16})?$",
    exclusions=(
        (r"[0-9]{7}", "carries a run of seven or more digits"),
        (r"[0-9]{3}[.-][0-9]{3}[.-][0-9]{4}", "carries a telephone number shape"),
        (r"[Ww][Ww][Ww]\.", "carries a host label"),
    ),
    max_length=64,
)


def provenance_string(value: object, path: str, grammar: Grammar) -> str:
    """Require a bounded provenance token in ``grammar``.

    The rejection names the shape rule that was broken and never the value, so
    a rejected identifier cannot reach a log or an error payload by way of the
    message that rejected it.
    """

    if not isinstance(value, str) or not value:
        raise contract_error(
            "invalid_string", path, "expected a bounded non-empty string"
        )
    reason = grammar.rejection(value)
    if reason is not None:
        raise contract_error("invalid_format", path, f"provenance token {reason}")
    return value


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


def timestamp_value(value: object, path: str) -> datetime:
    """Require a canonical UTC timestamp with whole-second precision."""

    raw = bounded_string(value, path, pattern=TIMESTAMP_PATTERN)
    try:
        parsed = datetime.strptime(raw, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError as exc:
        raise contract_error(
            "invalid_timestamp", path, "timestamp is not valid"
        ) from exc
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != raw:
        raise contract_error(
            "invalid_timestamp", path, "timestamp is not canonical UTC"
        )
    return parsed


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

    raw = bounded_string(value, path, max_length=253)
    try:
        ipaddress.ip_address(raw)
    except ValueError:
        canonical_ip = False
    else:
        canonical_ip = True
    if canonical_ip or LEGACY_IP_PATTERN.fullmatch(raw) is not None:
        raise contract_error("invalid_host", path, "IP addresses are not allowed")
    if HOST_PATTERN.fullmatch(raw) is None:
        raise contract_error(
            "invalid_format", path, "string does not match the required format"
        )
    return raw


def unique_strings(values: tuple[str, ...], path: str, *, code: str) -> None:
    """Reject duplicate identifiers while keeping values out of the error."""

    if len(values) != len(set(values)):
        raise contract_error(code, path, "values must be unique")
