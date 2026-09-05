"""Opt-in local event log: closed vocabulary, no free text, no clock.

RG-12 asks for local logs. This is the smallest thing that can be called one
without becoming a second place patient data lives.

Six properties, each of which is a decision rather than an omission.

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
code is checked against the one grammar the writer and the reader share,
because the error codes are raised across the package and are not one
enumerable set here. Either way a sentence cannot be written into a record.

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

**Readable, and only as counts.** ``contextsafe events summarize --directory
DIR`` is the supported way to ask what a log holds: how many records, how many
of each command, how many of each outcome, how many of each error code, and
the SHA-256 of the bytes it read. Nothing else. A summary is derived from the
same closed vocabularies the writer draws from, so there is no field for a
timestamp, a path, or free text to appear in, and the reader refuses a log
whose lines are not the record shape rather than skipping them: a summary over
the lines that happened to parse would understate exactly the runs an operator
is counting. A refusal names the line and the field and carries neither.
"""

from __future__ import annotations

import hashlib
import os
import re
import stat
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from contextsafe.canonical import JsonValue, canonical_json
from contextsafe.contract_validation import (
    array_value,
    bounded_string,
    contract_error,
    enum_string,
    exact_keys,
    object_value,
)
from contextsafe.errors import ContextSafeError
from contextsafe.jsonio import parse_json_bytes

LOG_SCHEMA_VERSION = "contextsafe.event-log/0.2.0"
"""0.2.0 added ``warnings``; 0.1.0 records carried the other five fields."""
SUMMARY_SCHEMA_VERSION = "contextsafe.event-log-summary/0.1.0"
LOG_FILE_NAME = "contextsafe-events.jsonl"
MAX_LOG_BYTES = 1_048_576
"""A log that grows without bound is an operational hazard of its own."""

ERROR_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
"""The shape of every error code this package raises, and the only shape a
record may carry. One constant, held by the writer and by the reader, so the
writer cannot produce a line its own reader refuses."""

RECORD_KEYS = frozenset(
    {"command", "error_code", "outcome", "schema_version", "sequence", "warnings"}
)
"""Every key a record has. Not a minimum: a record with another key is refused."""

_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_NONBLOCK = getattr(os, "O_NONBLOCK", 0)
"""Without it, opening a FIFO read-only blocks until a writer appears, so a
``--directory`` holding one under the log's name would hang instead of being
refused as not a regular file."""
_APPEND_FLAGS = os.O_WRONLY | os.O_APPEND | os.O_CREAT | _NOFOLLOW | _CLOEXEC
_READ_FLAGS = os.O_RDONLY | _NOFOLLOW | _NONBLOCK | _CLOEXEC
_CHUNK_BYTES = 65_536
_MAX_CHUNKS = MAX_LOG_BYTES // _CHUNK_BYTES
"""How many full reads a log at its size limit takes, before the read that sees
end of file. The read loop is bounded by this as well as by end of file, so a
descriptor that never reports end of file cannot hold the command open."""


class Outcome(StrEnum):
    """The closed set of things that can happen to a command."""

    ACCEPTED = "accepted"
    REJECTED = "rejected"


_OUTCOME_VALUES = frozenset(outcome.value for outcome in Outcome)
"""The same closed set, in the form the contract helpers take."""


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
        "fixtures",
        "events",
    }
)
"""Every command that may appear in a record. Not a prefix, not a pattern.

Widening this set has never moved ``LOG_SCHEMA_VERSION`` and does not move it
here. A record is not one of the published contracts in ``schemas/``, whose
rule is that a widened closed set moves the contract version; every log a
narrower vocabulary wrote stays exactly as readable under the wider one, and
bumping the version would instead make an operator's existing log unreadable
by the reader that exists to read it. What does pin this set is the published
summary contract, which names every command as a key, so a command added here
moves *that* contract's version. The residual is stated rather than hidden: a
``0.1.0`` record does not say which vocabulary was in force when it was
written.

``fixtures`` was missing from this set from the day the command was added
until 2026-09-04, so ``fixtures export --log-dir DIR`` printed
``unloggable_command`` on stderr, appended nothing, and exited 0: a run that
happened and left no record in the file whose purpose is to record what ran.
``tests/test_event_log_summary.py`` now derives the check from the argument
parser rather than restating the list.
"""

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
    if error_code is not None and ERROR_CODE_PATTERN.fullmatch(error_code) is None:
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
    without repetition, and a value outside the published set is refused
    rather than written.
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


# --- reading one back -------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Record:
    """One accepted line, reduced to the three things a summary counts."""

    command: str
    outcome: str
    error_code: str | None


@dataclass(frozen=True, slots=True)
class EventLogSummary:
    """What one local event log holds: counts, and the digest of its bytes.

    The digest is of the exact bytes that were read, so an operator can say
    which log a summary describes without naming it and can tell a later
    summary of a grown log from a repeat of this one. It is not a chain: the
    event log is not hash-chained, and a summary of a log cut back to an
    earlier line is a valid summary of a shorter log.
    """

    record_count: int
    log_sha256: str
    by_command: Mapping[str, int]
    by_outcome: Mapping[str, int]
    by_error_code: Mapping[str, int]

    def to_dict(self) -> dict[str, JsonValue]:
        """Return the operator-facing summary: closed keys and counts only."""

        return {
            "counts_by_command": {
                command: self.by_command.get(command, 0) for command in sorted(COMMANDS)
            },
            "counts_by_error_code": dict(sorted(self.by_error_code.items())),
            "counts_by_outcome": {
                outcome.value: self.by_outcome.get(outcome.value, 0)
                for outcome in Outcome
            },
            "log_sha256": self.log_sha256,
            "record_count": self.record_count,
            "schema_version": SUMMARY_SCHEMA_VERSION,
        }


def summarize_log(log_dir: Path) -> EventLogSummary:
    """Summarize the event log in ``log_dir``, reading it and nothing else.

    The log is opened once, no-follow, required to be a regular file within
    the size limit the writer enforces, and never written to. A directory
    holding no log is a rejection rather than an empty summary: absence must
    not read as "nothing failed".
    """

    descriptor = _open_for_read(log_dir / LOG_FILE_NAME)
    try:
        return summarize_bytes(_read_all(descriptor))
    finally:
        os.close(descriptor)


def summarize_bytes(raw: bytes) -> EventLogSummary:
    """Count every record in one log's bytes, or refuse the whole log."""

    commands: dict[str, int] = {}
    outcomes: dict[str, int] = {}
    error_codes: dict[str, int] = {}
    count = 0
    for index, line in enumerate(_lines(raw)):
        record = _parse_record(line, index)
        commands[record.command] = commands.get(record.command, 0) + 1
        outcomes[record.outcome] = outcomes.get(record.outcome, 0) + 1
        if record.error_code is not None:
            error_codes[record.error_code] = error_codes.get(record.error_code, 0) + 1
        count += 1
    return EventLogSummary(
        record_count=count,
        log_sha256=hashlib.sha256(raw).hexdigest(),
        by_command=commands,
        by_outcome=outcomes,
        by_error_code=error_codes,
    )


def _lines(raw: bytes) -> list[bytes]:
    """Split a log into record lines, refusing one that stops mid-record."""

    if not raw:
        return []
    if not raw.endswith(b"\n"):
        raise contract_error(
            "invalid_log_line", "$.log", "the log does not end with a newline"
        )
    return raw[:-1].split(b"\n")


def _parse_record(raw: bytes, index: int) -> _Record:
    """Parse one line, reporting any refusal at that line's own position."""

    try:
        return _read_record(raw, index)
    except ContextSafeError as exc:
        raise ContextSafeError(
            code=exc.code, path=f"$.log[{index}]{exc.path[1:]}", message=exc.message
        ) from exc


def _read_record(raw: bytes, index: int) -> _Record:
    """Require the closed record shape, byte for byte, or refuse the log.

    The last check is the strict one: the record is rebuilt from the values
    that were accepted and compared with the line as it was read. A line with
    the keys in another order, with whitespace, or with a number spelled
    another way is refused there even though every field passed, because a log
    a summary is derived from has one canonical form and an edited line is not
    it.
    """

    data = object_value(parse_json_bytes(raw), "$")
    exact_keys(data, RECORD_KEYS, "$")
    if data["schema_version"] != LOG_SCHEMA_VERSION:
        raise contract_error(
            "unsupported_schema_version",
            "$.schema_version",
            "record version is not published",
        )
    command = enum_string(data["command"], "$.command", COMMANDS)
    outcome = Outcome(enum_string(data["outcome"], "$.outcome", _OUTCOME_VALUES))
    error_code = _error_code_value(data["error_code"], "$.error_code")
    warnings = _warning_list(data["warnings"], "$.warnings")
    if data["sequence"] != index:
        raise contract_error(
            "log_sequence_mismatch", "$.sequence", "record is out of sequence"
        )
    rebuilt = _record(
        command=command,
        outcome=outcome,
        error_code=error_code,
        sequence=index,
        warnings=warnings,
    )
    if canonical_json(rebuilt).encode("utf-8") != raw:
        raise contract_error("invalid_log_line", "$", "record is not canonical JSON")
    return _Record(command=command, outcome=outcome.value, error_code=error_code)


def _warning_list(value: object, path: str) -> list[str]:
    """Require an array of published warning codes, and nothing else.

    The values are handed back as they were read rather than sorted here: the
    canonical rebuild in ``_read_record`` is what refuses a log whose warnings
    are out of order or repeated, so this reports the one thing the rebuild
    could not name -- a value that is not a warning code -- at its own field.
    """

    codes: list[str] = []
    for item in array_value(value, path):
        codes.append(enum_string(item, path, WARNING_CODES))
    return codes


def _error_code_value(value: object, path: str) -> str | None:
    """Require null, or one closed identifier of the writer's own shape."""

    if value is None:
        return None
    return bounded_string(value, path, pattern=ERROR_CODE_PATTERN, max_length=64)


def _open_for_read(path: Path) -> int:
    """Open the log for reading: no symbolic link, no device, nothing oversize."""

    if _NOFOLLOW == 0:
        raise ContextSafeError(
            "input_path_unsupported",
            "$",
            "platform cannot enforce no-follow event-log access",
        )
    try:
        descriptor = os.open(path, _READ_FLAGS)
    except OSError as exc:
        raise ContextSafeError(
            "log_io_error", "$", "the local event log could not be opened"
        ) from exc
    try:
        details = os.fstat(descriptor)
        if not stat.S_ISREG(details.st_mode):
            raise ContextSafeError(
                "input_path_unsafe", "$", "the local event log must be a regular file"
            )
        if details.st_size > MAX_LOG_BYTES:
            raise ContextSafeError(
                "input_too_large",
                "$",
                "the local event log exceeds its published size limit",
            )
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


def _read_all(descriptor: int) -> bytes:
    """Read the whole log within its published bound, or refuse it."""

    chunks: list[bytes] = []
    count = 0
    try:
        while len(chunks) <= _MAX_CHUNKS:
            chunk = os.read(descriptor, _CHUNK_BYTES)
            if not chunk:
                return b"".join(chunks)
            count += len(chunk)
            if count > MAX_LOG_BYTES:
                raise ContextSafeError(
                    "input_too_large",
                    "$",
                    "the local event log exceeds its published size limit",
                )
            chunks.append(chunk)
    except OSError as exc:
        raise ContextSafeError(
            "log_io_error", "$", "the local event log could not be read"
        ) from exc
    raise ContextSafeError(
        "log_io_error", "$", "the local event log did not end within its read bound"
    )
