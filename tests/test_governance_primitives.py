"""Negative tests for shared governed-contract parsing primitives."""

import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager

import pytest

from contextsafe.contract_validation import (
    array_value,
    boolean_value,
    bounded_string,
    date_value,
    enum_string,
    exact_keys,
    host_value,
    nullable_date_value,
    object_value,
    relative_path_value,
    unique_strings,
)
from contextsafe.errors import ContextSafeError


@contextmanager
def _passthrough_context() -> Iterator[None]:
    yield


@pytest.mark.parametrize(
    ("operation", "expected_code"),
    [
        (lambda: object_value([], "$"), "invalid_type"),
        (lambda: object_value({1: "value"}, "$"), "invalid_type"),
        (lambda: array_value({}, "$"), "invalid_type"),
        (
            lambda: exact_keys({"unexpected": True}, frozenset(), "$"),
            "unknown_field",
        ),
        (
            lambda: exact_keys({}, frozenset({"required"}), "$"),
            "missing_field",
        ),
        (lambda: bounded_string(None, "$"), "invalid_string"),
        (lambda: bounded_string("\ud800", "$"), "invalid_unicode"),
        (
            lambda: bounded_string("lower", "$", pattern=re.compile(r"^[A-Z]+$")),
            "invalid_format",
        ),
        (lambda: boolean_value(1, "$"), "invalid_type"),
        (lambda: date_value("2026-02-30", "$"), "invalid_date"),
        (
            lambda: enum_string("unsupported", "$", frozenset({"supported"})),
            "invalid_enum",
        ),
        (lambda: relative_path_value(".", "$"), "invalid_path"),
        (lambda: host_value("127.0.0.1", "$"), "invalid_host"),
        (lambda: host_value("2130706433", "$"), "invalid_host"),
        (lambda: host_value("127.1", "$"), "invalid_host"),
        (lambda: host_value("0177.0.0.1", "$"), "invalid_host"),
        (lambda: host_value("0x7f.0.0.1", "$"), "invalid_host"),
        (lambda: host_value("::1", "$"), "invalid_host"),
        (lambda: host_value("0:0:0:0:0:0:0:1", "$"), "invalid_host"),
        (lambda: host_value("::ffff:127.0.0.1", "$"), "invalid_host"),
        (
            lambda: unique_strings(("same", "same"), "$", code="duplicate"),
            "duplicate",
        ),
    ],
)
def test_contract_primitive_rejections(
    operation: Callable[[], object], expected_code: str
) -> None:
    with pytest.raises(ContextSafeError) as raised:
        operation()

    assert raised.value.code == expected_code


def test_optional_keys_nullable_dates_and_dns_hosts_are_accepted() -> None:
    exact_keys(
        {"required": True, "optional": True},
        frozenset({"required"}),
        "$",
        optional=frozenset({"optional"}),
    )
    assert nullable_date_value(None, "$") is None
    assert nullable_date_value("2026-07-13", "$").isoformat() == "2026-07-13"
    assert host_value("staging.contextsafe.invalid", "$") == (
        "staging.contextsafe.invalid"
    )


def test_structured_error_preserves_itself_across_context_manager() -> None:
    error = ContextSafeError("test_code", "$", "safe message")

    with pytest.raises(ContextSafeError) as raised, _passthrough_context():
        raise error

    assert raised.value is error
