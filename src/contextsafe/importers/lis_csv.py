"""A strict reader for the RFC 4180 subset an LIS CSV export may use.

The subset, stated once. UTF-8 text with no byte-order mark. Records end
in CRLF or LF; a bare CR is not a terminator and rejects the text. A field
is unquoted, in which case it may not contain a comma, a double quote, or a
line break; or it is quoted, in which case it may contain a comma and a
doubled double quote (``""``) and still may not contain a line break. A
quoted field ends at its closing quote, which must be followed by a comma
or the end of the record. Every record has the same number of fields as the
first, and the first is the header. Record, field, and field-length counts
are bounded by the caller.

Why a reader of its own rather than :mod:`csv`. The standard module is
lenient by design: it carries a line break inside a quoted field, it
accepts a quote in the middle of an unquoted field in its default dialect,
and its ``strict`` flag reaches only some of that. Every leniency is a way
for a record to mean two things, and a boundary reader must mean one. This
reader is a small state machine whose every rejection names a record and a
field position and never the text at it.

The line-break rule also bounds the work before any field is read: because
a line break can never be inside a field, records are split on line breaks
first and the record bound is applied to that count, so a text that is
nothing but line breaks is refused for its record count and not parsed
field by field.
"""

from dataclasses import dataclass

from contextsafe.errors import ContextSafeError
from contextsafe.importers.base import ImportErrorCode, import_error

QUOTE = '"'
SEPARATOR = ","


@dataclass(frozen=True, slots=True)
class CsvBounds:
    """What a caller allows: records including the header, fields, and length."""

    max_records: int
    max_fields: int
    max_field_length: int


def _position(record: int, field: int) -> str:
    return f"$.records[{record}][{field}]"


def _malformed(path: str, message: str) -> ContextSafeError:
    return import_error(ImportErrorCode.SOURCE_MALFORMED, path, message)


def split_records(text: str, *, max_records: int) -> tuple[str, ...]:
    """Split ``text`` on CRLF or LF, refusing a bare CR and a record overrun.

    A terminator after the last record is permitted and produces no empty
    record; a second one does, and that empty record is later refused for
    its field count. Empty text has no header and is refused here.
    """

    if not text:
        raise _malformed("$", "a header record is required")
    if "\r" in text.replace("\r\n", ""):
        raise _malformed("$", "a bare carriage return is not a record terminator")
    records = text.replace("\r\n", "\n").split("\n")
    if records[-1] == "":
        records.pop()
    if len(records) > max_records:
        raise import_error(
            ImportErrorCode.BOUND_EXCEEDED,
            "$.records",
            "record count exceeds the bound",
        )
    return tuple(records)


def _unquoted_field(line: str, start: int, path: str) -> tuple[str, int]:
    index = start
    while index < len(line) and line[index] != SEPARATOR:
        if line[index] == QUOTE:
            raise _malformed(path, "a quote inside an unquoted field")
        index += 1
    return line[start:index], index


def _quoted_field(line: str, start: int, path: str) -> tuple[str, int]:
    """Read from just after an opening quote to just after the closing one."""

    characters: list[str] = []
    index = start
    while True:
        if index >= len(line):
            raise _malformed(
                path,
                "a quoted field is not closed on its record; line breaks "
                "inside a field are not accepted",
            )
        character = line[index]
        if character != QUOTE:
            characters.append(character)
            index += 1
            continue
        if index + 1 < len(line) and line[index + 1] == QUOTE:
            characters.append(QUOTE)
            index += 2
            continue
        index += 1
        break
    if index < len(line) and line[index] != SEPARATOR:
        raise _malformed(path, "text follows a closing quote")
    return "".join(characters), index


def _parse_record(line: str, record: int, bounds: CsvBounds) -> tuple[str, ...]:
    fields: list[str] = []
    index = 0
    while True:
        path = _position(record, len(fields))
        if len(fields) >= bounds.max_fields:
            raise import_error(
                ImportErrorCode.BOUND_EXCEEDED, path, "field count exceeds the bound"
            )
        if index < len(line) and line[index] == QUOTE:
            field, index = _quoted_field(line, index + 1, path)
        else:
            field, index = _unquoted_field(line, index, path)
        if len(field) > bounds.max_field_length:
            raise import_error(
                ImportErrorCode.BOUND_EXCEEDED, path, "field length exceeds the bound"
            )
        fields.append(field)
        if index >= len(line):
            return tuple(fields)
        index += 1


def parse_csv(text: str, *, bounds: CsvBounds) -> tuple[tuple[str, ...], ...]:
    """Parse ``text`` into records of fields, the first record being the header.

    Every record has the header's field count; a shorter or longer one is a
    grammar failure, not a record with defaults. Nothing is trimmed,
    decoded, or interpreted: a field is the characters the grammar found
    between its delimiters, and what they mean is the caller's profile.
    """

    lines = split_records(text, max_records=bounds.max_records)
    records = [_parse_record(line, index, bounds) for index, line in enumerate(lines)]
    width = len(records[0])
    for index, record in enumerate(records[1:], start=1):
        if len(record) != width:
            raise _malformed(
                f"$.records[{index}]",
                "record field count differs from the header",
            )
    return tuple(records)
