"""Opt-in local event log: closed vocabulary, no free text, no clock.

RG-12 asks for local logs. This is the smallest thing that can be called one
without becoming a second place patient data lives.

Five properties, each of which is a decision rather than an omission.

**Off unless asked, and asked on the command line.** A log is written only when
``--log-dir`` is passed. It is never enabled by an environment variable,
because output that changes with the environment is exactly what
``tests/test_determinism.py`` exists to prevent, and because a log nobody asked
for is a disclosure nobody consented to.

**No free text.** A record is a fixed set of fields drawn from closed
vocabularies: the command, the outcome, the error code if there was one, and
the closed warning codes the command carried. There is no message field, so
there is nowhere for an exception string, a path, or a token to end up. The
command and every warning code are checked against the lists this module
publishes and a value outside them is refused, never truncated; an error
code is checked to be a closed identifier, because the error codes are
raised across the package and are not one enumerable set here. Either way a
sentence cannot be written into a record.

**Warnings, because otherwise nobody reads them.** ``contextsafe import``
attaches closed warning codes to a conversion, and until 0.2.0 the only
reader was a test: the CLI writes the observation set and nothing else, so
``mapping_profile_row_unmatched`` -- a ``--mapping`` profile whose rows bind
nothing -- reached no operator at the moment they could still fix the
profile. A warning code is a published value carrying no more content than
an error code does, so the record carries them here rather
than a second output document being invented for them (whether an import
report is ever published is a maintainer's decision, not this file's). The
list is sorted and may not repeat a code, so it is a set of codes rather
than a sequence carrying information of its own. It describes a command the
runner accepted: a rejected record carries the error code and no warnings,
so the field does not change meaning with how far the command got.

**No clock.** The runner never reads a clock — the receipt envelope is explicit
that it has no trusted time — and a log is not a good reason to start. Records
carry a per-file sequence number instead. That is a real limitation: correlating
these records with anything else needs an external timestamp, and an operator
who needs one should capture it outside the tool. Recording an untrusted local
clock reading in a file that looks like an audit trail would be worse.

**Append-only, owner-only, one line at a time.** Each record is one canonical
JSON line, opened with ``O_APPEND`` and ``O_NOFOLLOW``, written in a single
call. Nothing here imports ``logging``: the privacy canary in
``tests/test_privacy_canaries.py`` asserts no module does, and that canary is
worth more than the convenience.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from enum import StrEnum
from pathlib import Path

from contextsafe.canonical import JsonValue, canonical_json
from contextsafe.errors import ContextSafeError

LOG_SCHEMA_VERSION = "contextsafe.event-log/0.2.0"
"""0.2.0 added ``warnings``; 0.1.0 records carried the other five fields."""
LOG_FILE_NAME = "contextsafe-events.jsonl"
MAX_LOG_BYTES = 1_048_576
"""A log that grows without bound is an operational hazard of its own."""

_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_APPEND_FLAGS = os.O_WRONLY | os.O_APPEND | os.O_CREAT | _NOFOLLOW | _CLOEXEC


class Outcome(StrEnum):
    """The closed set of things that can happen to a command."""

    ACCEPTED = "accepted"
    REJECTED = "rejected"


COMMANDS = frozenset(
    {
        "validate",
        "evaluate",
        "render",
        "receipt",
        "pack",
        "plan",
        "evidence",
        "import",
        "mapping",
        "finding",
        "diagnostics",
        "cleanup",
        "support-bundle",
    }
)
"""Every command that may appear in a record. Not a prefix, not a pattern."""

WARNING_CODES = frozenset(
    {
        "checkpoint_asserted_by_caller",
        "checkpoint_not_in_source",
        "mapping_profile_not_bound",
        "mapping_profile_row_unmatched",
        "plan_binding_not_checked",
        "result_columns_not_observed",
        "result_observations_not_written",
    }
)
"""Every warning code that may appear in a record: a list, not a shape.

Written out here the way ``COMMANDS`` is, rather than imported from the
importer package, so the log does not depend on the readers to know what it
may write. ``tests/test_diagnostics.py`` pins this set against
``ImportWarningCode`` so the two cannot drift apart in silence. A shape check
alone would have admitted any lowercase word, which is the distinction the
rest of this iteration is about.
"""


def _closed_identifier(value: str) -> bool:
    """A code is letters, digits and underscores; anything else is a message."""

    return bool(value) and value.replace("_", "").isalnum()


def _warning_codes(warnings: Sequence[str]) -> list[JsonValue]:
    """Sort the warning codes, refusing anything that is not one."""

    for code in warnings:
        if code not in WARNING_CODES:
            raise ContextSafeError(
                "unloggable_warning_code",
                "$.warnings",
                "a warning code is a published value, not a message",
            )
    if len(set(warnings)) != len(warnings):
        raise ContextSafeError(
            "unloggable_warning_code",
            "$.warnings",
            "a warning code is recorded once; a repeat says nothing more",
        )
    return [*sorted(warnings)]


def _record(
    *,
    command: str,
    outcome: Outcome,
    error_code: str | None,
    sequence: int,
    warnings: Sequence[str],
) -> dict[str, JsonValue]:
    if command not in COMMANDS:
        raise ContextSafeError(
            "unloggable_command", "$.command", "command is not a published value"
        )
    if error_code is not None and not _closed_identifier(error_code):
        raise ContextSafeError(
            "unloggable_error_code",
            "$.error_code",
            "an error code is a closed identifier, not a message",
        )
    return {
        "command": command,
        "error_code": error_code,
        "outcome": outcome.value,
        "schema_version": LOG_SCHEMA_VERSION,
        "sequence": sequence,
        "warnings": _warning_codes(warnings),
    }


def _next_sequence(path: Path) -> int:
    try:
        with path.open("rb") as handle:
            return sum(1 for line in handle if line.strip())
    except FileNotFoundError:
        return 0
    except OSError as exc:
        raise ContextSafeError(
            "log_io_error", "$", "the local event log could not be read"
        ) from exc


def append_event(
    log_dir: Path,
    *,
    command: str,
    outcome: Outcome,
    error_code: str | None = None,
    warnings: Sequence[str] = (),
) -> Path:
    """Append one record to the local event log and return the log path.

    ``warnings`` are the closed warning codes the command carried, if any:
    for ``import``, the conversion's own. They are recorded sorted and
    without repetition, and a value outside the closed-identifier shape is
    refused rather than written.
    """

    try:
        log_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    except OSError as exc:
        raise ContextSafeError(
            "log_io_error", "$", "the log directory could not be created"
        ) from exc
    path = log_dir / LOG_FILE_NAME
    if path.is_symlink():
        raise ContextSafeError(
            "log_io_error", "$", "the local event log may not be a symbolic link"
        )
    sequence = _next_sequence(path)
    line = (
        canonical_json(
            _record(
                command=command,
                outcome=outcome,
                error_code=error_code,
                sequence=sequence,
                warnings=warnings,
            )
        )
        + "\n"
    ).encode("utf-8")
    _append_bytes(path, line)
    return path


def _append_bytes(path: Path, line: bytes) -> None:
    try:
        descriptor = os.open(path, _APPEND_FLAGS, 0o600)
    except OSError as exc:
        raise ContextSafeError(
            "log_io_error", "$", "the local event log could not be opened"
        ) from exc
    try:
        if os.fstat(descriptor).st_size + len(line) > MAX_LOG_BYTES:
            raise ContextSafeError(
                "log_full",
                "$",
                "the local event log has reached its published size limit",
            )
        os.write(descriptor, line)
    finally:
        os.close(descriptor)
