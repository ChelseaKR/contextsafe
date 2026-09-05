"""Reading the local event log back: ``contextsafe events summarize``.

The log has been written since B-046 and nothing read it, so an operator with
a week of runs had a JSON-lines file and no supported way to ask how many
evaluations failed closed and with which codes. This file holds the reader to
the standard the writer was held to: closed vocabulary and counts only, a
refusal rather than a skip for anything that is not one canonical record, a
location and no content in every rejection, and nothing written to the log by
the command that reads it.

The refusal-rather-than-skip tests are the ones that matter. A summary derived
from the lines that happened to parse would understate exactly the runs an
operator is counting, and would do it silently.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import threading
from pathlib import Path
from typing import Any

import pytest

from contextsafe import eventlog
from contextsafe.canonical import canonical_json
from contextsafe.cli import (
    EXIT_CONTRACT_ERROR,
    EXIT_SUCCESS,
    _operator_command,
    _parser,
    main,
)
from contextsafe.errors import ContextSafeError
from contextsafe.eventlog import (
    COMMANDS,
    LOG_FILE_NAME,
    LOG_SCHEMA_VERSION,
    MAX_LOG_BYTES,
    SUMMARY_SCHEMA_VERSION,
    Outcome,
    append_event,
    summarize_bytes,
    summarize_log,
)

EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
"""The SHA-256 of no bytes, which is what a log holding no record digests to."""


def _record(**overrides: Any) -> dict[str, Any]:
    record: dict[str, Any] = {
        "command": "evaluate",
        "error_code": None,
        "outcome": "accepted",
        "schema_version": LOG_SCHEMA_VERSION,
        "sequence": 0,
        "warnings": [],
    }
    record.update(overrides)
    return record


def _log(*records: dict[str, Any]) -> bytes:
    return b"".join(f"{canonical_json(record)}\n".encode() for record in records)


def _write_log(directory: Path, raw: bytes) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / LOG_FILE_NAME
    path.write_bytes(raw)
    return path


@pytest.fixture
def populated_log(tmp_path: Path) -> Path:
    """Three runs an operator would recognise: two accepted, one refused."""

    log_dir = tmp_path / "logs"
    append_event(log_dir, command="evaluate", outcome=Outcome.ACCEPTED)
    append_event(log_dir, command="evaluate", outcome=Outcome.ACCEPTED)
    append_event(
        log_dir,
        command="import",
        outcome=Outcome.REJECTED,
        error_code="invalid_rsg_value",
    )
    return log_dir


def test_a_log_summarises_to_counts_and_one_digest(populated_log: Path) -> None:
    """The question the issue asks: how many failed closed, with which codes."""

    summary = summarize_log(populated_log).to_dict()

    assert summary["record_count"] == 3
    assert summary["counts_by_outcome"] == {"accepted": 2, "rejected": 1}
    assert summary["counts_by_error_code"] == {"invalid_rsg_value": 1}
    assert summary["schema_version"] == SUMMARY_SCHEMA_VERSION
    counts = summary["counts_by_command"]
    assert isinstance(counts, dict)
    assert counts["evaluate"] == 2
    assert counts["import"] == 1


def test_every_published_command_is_a_key_whether_or_not_it_was_run(
    populated_log: Path,
) -> None:
    """A fixed shape: a command with no record reads as zero, not as absent."""

    counts = summarize_log(populated_log).to_dict()["counts_by_command"]
    assert isinstance(counts, dict)
    assert set(counts) == set(COMMANDS)
    assert counts["cleanup"] == 0


def test_the_digest_is_of_the_bytes_that_were_read(populated_log: Path) -> None:
    """An operator can say which log a summary describes without naming it."""

    raw = (populated_log / LOG_FILE_NAME).read_bytes()
    summary = summarize_log(populated_log).to_dict()
    assert summary["log_sha256"] == hashlib.sha256(raw).hexdigest()


def test_a_log_holding_no_record_summarises_to_zero(tmp_path: Path) -> None:
    """The boundary below one: an empty file is a log of no runs, not an error."""

    _write_log(tmp_path / "logs", b"")
    summary = summarize_log(tmp_path / "logs").to_dict()
    assert summary["record_count"] == 0
    assert summary["counts_by_error_code"] == {}
    assert summary["counts_by_outcome"] == {"accepted": 0, "rejected": 0}
    assert summary["log_sha256"] == EMPTY_SHA256


def test_a_summary_carries_no_path_and_no_free_text(populated_log: Path) -> None:
    """Value minimization: hashes, statuses, counts, and closed keys only."""

    rendered = canonical_json(summarize_log(populated_log).to_dict())
    assert str(populated_log) not in rendered
    assert LOG_FILE_NAME not in rendered
    for key in json.loads(rendered):
        assert key in {
            "counts_by_command",
            "counts_by_error_code",
            "counts_by_outcome",
            "log_sha256",
            "record_count",
            "schema_version",
        }


def test_summarising_writes_nothing_to_the_log(populated_log: Path) -> None:
    """A reader that appends is a writer, and this one does not."""

    before = (populated_log / LOG_FILE_NAME).read_bytes()
    summarize_log(populated_log)
    assert (populated_log / LOG_FILE_NAME).read_bytes() == before


@pytest.mark.parametrize("command", sorted(COMMANDS))
@pytest.mark.parametrize("outcome", list(Outcome))
def test_the_reader_accepts_everything_the_writer_writes(
    tmp_path: Path, command: str, outcome: Outcome
) -> None:
    """The writer cannot produce a record its own reader refuses."""

    log_dir = tmp_path / command / outcome.value
    append_event(
        log_dir,
        command=command,
        outcome=outcome,
        error_code=None if outcome is Outcome.ACCEPTED else "invalid_json",
    )
    summary = summarize_log(log_dir).to_dict()
    counts = summary["counts_by_command"]
    assert isinstance(counts, dict)
    assert counts[command] == 1
    assert summary["record_count"] == 1


def test_a_log_four_commands_appended_to_at_once_still_summarises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The writer takes no lock, so the reader may not assume it does.

    ``append_event`` counts the file's lines and only then appends: nothing
    holds the file between the two, so commands run at once against one shared
    ``--log-dir`` all see the same count and all write it. Every record in this
    log was written by this tool. A reader that required a sequence to equal
    its position refused all four of them, as a whole log, permanently and with
    no way to relax it -- which is precisely the operator issue #97 describes,
    holding a week of runs and asking how many failed closed. The barrier makes
    the race certain rather than likely, so this is a test and not a coin toss.
    """

    log_dir = tmp_path / "logs"
    writers = 4
    barrier = threading.Barrier(writers)
    counted = eventlog._next_sequence

    def count_then_wait(path: Path) -> int:
        sequence = counted(path)
        barrier.wait(timeout=30)
        return sequence

    monkeypatch.setattr(eventlog, "_next_sequence", count_then_wait)
    failures: list[Exception] = []

    def append() -> None:
        try:
            append_event(log_dir, command="evaluate", outcome=Outcome.ACCEPTED)
        except Exception as exc:
            failures.append(exc)

    threads = [threading.Thread(target=append) for _ in range(writers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert failures == []
    raw = (log_dir / LOG_FILE_NAME).read_bytes()
    assert raw.count(b'"sequence":0') == writers
    summary = summarize_log(log_dir).to_dict()
    assert summary["record_count"] == writers
    counts = summary["counts_by_command"]
    assert isinstance(counts, dict)
    assert counts["evaluate"] == writers


def test_a_repeated_sequence_is_read_as_the_concurrency_it_is() -> None:
    """The bytes those writers leave, pinned as a literal log rather than a race."""

    raw = _log(_record(sequence=0), _record(sequence=0), _record(sequence=1))
    assert summarize_bytes(raw).record_count == 3


def test_a_sequence_behind_its_position_is_read_too() -> None:
    """A writer delayed between counting and appending writes one of these."""

    raw = _log(_record(sequence=0), _record(sequence=1), _record(sequence=0))
    assert summarize_bytes(raw).record_count == 3


# --- refusals ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("line", "code", "path"),
    [
        (b"not json", "invalid_json", "$.log[1]"),
        (b"[]", "invalid_type", "$.log[1]"),
        (b"", "invalid_json", "$.log[1]"),
    ],
)
def test_a_line_that_is_not_a_record_refuses_the_whole_log(
    line: bytes, code: str, path: str
) -> None:
    """Refused, not skipped: an unreadable line is an uncounted run."""

    raw = _log(_record()) + line + b"\n"
    with pytest.raises(ContextSafeError) as raised:
        summarize_bytes(raw)
    assert raised.value.code == code
    assert raised.value.path == path


@pytest.mark.parametrize(
    ("overrides", "code", "path"),
    [
        ({"command": "rm -rf /"}, "invalid_enum", "$.log[0].command"),
        ({"command": "evaluate --case"}, "invalid_enum", "$.log[0].command"),
        ({"outcome": "maybe"}, "invalid_enum", "$.log[0].outcome"),
        (
            {"error_code": "failed reading the case file for CSYN-CTP-I01"},
            "invalid_format",
            "$.log[0].error_code",
        ),
        ({"error_code": 7}, "invalid_string", "$.log[0].error_code"),
        (
            {"schema_version": "contextsafe.event-log/9.9.9"},
            "unsupported_schema_version",
            "$.log[0].schema_version",
        ),
        ({"sequence": 4}, "log_sequence_mismatch", "$.log[0].sequence"),
        ({"sequence": -1}, "log_sequence_mismatch", "$.log[0].sequence"),
        ({"sequence": True}, "invalid_integer", "$.log[0].sequence"),
        ({"sequence": "0"}, "invalid_integer", "$.log[0].sequence"),
        ({"note": "by hand"}, "unknown_field", "$.log[0]"),
    ],
)
def test_a_field_outside_the_record_shape_is_refused_where_it_sits(
    overrides: dict[str, Any], code: str, path: str
) -> None:
    """Every rejection names a line and a field, and carries no value."""

    with pytest.raises(ContextSafeError) as raised:
        summarize_bytes(_log(_record(**overrides)))
    assert raised.value.code == code
    assert raised.value.path == path
    for value in overrides.values():
        assert str(value) not in raised.value.message


def test_a_missing_field_is_refused_at_the_field(tmp_path: Path) -> None:
    """Absence is not a default; a record has every key or it is not one."""

    record = _record()
    del record["error_code"]
    with pytest.raises(ContextSafeError) as raised:
        summarize_bytes(_log(record))
    assert raised.value.code == "missing_field"
    assert raised.value.path == "$.log[0].error_code"


@pytest.mark.parametrize(
    "line",
    [
        b'{"error_code":null,"command":"evaluate","outcome":"accepted","schema_version":"contextsafe.event-log/0.2.0","sequence":0,"warnings":[]}',
        b'{"command": "evaluate", "error_code": null, "outcome": "accepted", "schema_version": "contextsafe.event-log/0.2.0", "sequence": 0, "warnings": []}',
    ],
)
def test_a_record_that_is_not_canonical_is_refused(line: bytes) -> None:
    """A hand-edited line has the same fields and is not the record written."""

    with pytest.raises(ContextSafeError) as raised:
        summarize_bytes(line + b"\n")
    assert raised.value.code == "invalid_log_line"
    assert raised.value.path == "$.log[0]"


def test_a_log_that_stops_mid_record_is_refused() -> None:
    """A partial final line is a log that was cut, not a log with one fewer run."""

    raw = _log(_record())[:-1]
    with pytest.raises(ContextSafeError) as raised:
        summarize_bytes(raw)
    assert raised.value.code == "invalid_log_line"
    assert raised.value.path == "$.log"


def test_a_removed_line_is_caught_by_the_sequence(tmp_path: Path) -> None:
    """The one edit a per-line shape check alone would miss."""

    lines = _log(
        _record(sequence=0), _record(sequence=1), _record(sequence=2)
    ).splitlines(keepends=True)
    with pytest.raises(ContextSafeError) as raised:
        summarize_bytes(lines[0] + lines[2])
    assert raised.value.code == "log_sequence_mismatch"
    assert raised.value.path == "$.log[1].sequence"


def test_a_log_over_the_published_size_limit_is_refused(tmp_path: Path) -> None:
    """The boundary above: one byte more than the writer would ever write."""

    _write_log(tmp_path / "logs", b"\n" * (MAX_LOG_BYTES + 1))
    with pytest.raises(ContextSafeError) as raised:
        summarize_log(tmp_path / "logs")
    assert raised.value.code == "input_too_large"


def test_a_directory_with_no_log_is_refused(tmp_path: Path) -> None:
    """Absence must not read as "nothing failed"."""

    with pytest.raises(ContextSafeError) as raised:
        summarize_log(tmp_path / "logs")
    assert raised.value.code == "log_io_error"


@pytest.mark.skipif(os.name == "nt", reason="POSIX symbolic links")
def test_a_log_that_is_a_symbolic_link_is_refused(tmp_path: Path) -> None:
    """Reading through a link is how a reader is pointed at somebody else's file."""

    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (tmp_path / "elsewhere").write_bytes(b"")
    (log_dir / LOG_FILE_NAME).symlink_to(tmp_path / "elsewhere")
    with pytest.raises(ContextSafeError) as raised:
        summarize_log(log_dir)
    assert raised.value.code == "log_io_error"


@pytest.mark.skipif(os.name == "nt", reason="POSIX FIFOs")
def test_a_log_that_is_not_a_regular_file_is_refused(tmp_path: Path) -> None:
    """A FIFO under the log's name is refused rather than waited on."""

    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    os.mkfifo(log_dir / LOG_FILE_NAME)
    with pytest.raises(ContextSafeError) as raised:
        summarize_log(log_dir)
    assert raised.value.code == "input_path_unsafe"


def test_a_read_that_never_ends_is_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A descriptor that never reports end of file cannot hold the command open."""

    _write_log(tmp_path / "logs", b"")
    monkeypatch.setattr(os, "read", lambda _descriptor, size: b"x" * size)
    with pytest.raises(ContextSafeError) as raised:
        summarize_log(tmp_path / "logs")
    assert raised.value.code == "input_too_large"


def test_a_read_that_never_ends_in_small_pieces_is_bounded_too(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The byte bound alone would never fire against one-byte reads."""

    _write_log(tmp_path / "logs", b"")
    monkeypatch.setattr(os, "read", lambda _descriptor, _size: b"x")
    with pytest.raises(ContextSafeError) as raised:
        summarize_log(tmp_path / "logs")
    assert raised.value.code == "log_io_error"


def test_a_platform_without_no_follow_open_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No-follow is a POSIX guarantee, and this reader refuses to do without it."""

    _write_log(tmp_path / "logs", b"")
    monkeypatch.setattr(eventlog, "_NOFOLLOW", 0)
    with pytest.raises(ContextSafeError) as raised:
        summarize_log(tmp_path / "logs")
    assert raised.value.code == "input_path_unsupported"


def test_a_read_error_is_reported_rather_than_summarised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A log that could not be read is not a log with nothing in it."""

    _write_log(tmp_path / "logs", _log(_record()))

    def refuse(_descriptor: int, _size: int) -> bytes:
        raise OSError("refused")

    monkeypatch.setattr(os, "read", refuse)
    with pytest.raises(ContextSafeError) as raised:
        summarize_log(tmp_path / "logs")
    assert raised.value.code == "log_io_error"


def test_the_writer_refuses_an_error_code_the_reader_would_refuse(
    tmp_path: Path,
) -> None:
    """One grammar, held by both ends, so the writer cannot poison its reader."""

    with pytest.raises(ContextSafeError) as raised:
        append_event(
            tmp_path,
            command="evaluate",
            outcome=Outcome.REJECTED,
            error_code="Cleanup_Not_Confirmed",
        )
    assert raised.value.code == "unloggable_error_code"


# --- the command ------------------------------------------------------------


def test_the_command_prints_one_canonical_line(
    populated_log: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Exit 0, one JSON line on stdout, nothing on stderr."""

    assert main(["events", "summarize", "--directory", str(populated_log)]) == (
        EXIT_SUCCESS
    )
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out.count("\n") == 1
    assert json.loads(captured.out)["record_count"] == 3


def test_the_command_honours_quiet_and_output(
    populated_log: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The same bytes to a file as to stdout, and nothing printed with --quiet."""

    artifact = tmp_path / "summary.json"
    assert (
        main(
            [
                "events",
                "summarize",
                "--directory",
                str(populated_log),
                "--no-color",
                "--output",
                str(artifact),
            ]
        )
        == EXIT_SUCCESS
    )
    assert capsys.readouterr().out == ""
    assert main(["events", "summarize", "--directory", str(populated_log)]) == (
        EXIT_SUCCESS
    )
    assert capsys.readouterr().out == artifact.read_text(encoding="utf-8")
    assert (
        main(["events", "summarize", "--quiet", "--directory", str(populated_log)])
        == EXIT_SUCCESS
    )
    assert capsys.readouterr().out == ""


def test_the_command_refuses_an_output_that_names_the_log(
    populated_log: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """--output truncates, and the log is append-only."""

    before = (populated_log / LOG_FILE_NAME).read_bytes()
    assert (
        main(
            [
                "events",
                "summarize",
                "--directory",
                str(populated_log),
                "--output",
                str(populated_log / LOG_FILE_NAME),
            ]
        )
        == EXIT_CONTRACT_ERROR
    )
    error = json.loads(capsys.readouterr().err)["error"]
    assert error["code"] == "output_path_unsafe"
    assert str(populated_log) not in error["message"]
    assert (populated_log / LOG_FILE_NAME).read_bytes() == before


def test_the_command_refuses_an_output_that_names_the_log_it_writes_to(
    tmp_path: Path, populated_log: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The other half of the same guard: ``--log-dir``'s log, not ``--directory``'s.

    ``--output`` is a truncating write and it happens before the record is
    appended, so an ``--output`` naming the log ``--log-dir`` writes to
    replaced every record in it with a summary of a different log and then
    appended one record to what was left. It exited 0, and the log it emptied
    could never be summarised again, because the reader refuses a whole log
    over one line it cannot parse.
    """

    written = tmp_path / "written"
    append_event(written, command="evaluate", outcome=Outcome.ACCEPTED)
    before = (written / LOG_FILE_NAME).read_bytes()
    assert (
        main(
            [
                "events",
                "summarize",
                "--directory",
                str(populated_log),
                "--log-dir",
                str(written),
                "--output",
                str(written / LOG_FILE_NAME),
            ]
        )
        == EXIT_CONTRACT_ERROR
    )
    error = json.loads(capsys.readouterr().err)["error"]
    assert error["code"] == "output_path_unsafe"
    assert str(written) not in error["message"]
    raw = (written / LOG_FILE_NAME).read_bytes()
    assert raw.startswith(before)
    summary = summarize_log(written).to_dict()
    assert summary["record_count"] == 2
    assert summary["counts_by_error_code"] == {"output_path_unsafe": 1}


def test_every_command_refuses_an_output_that_names_the_event_log(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The guard is on ``--log-dir``, so it covers the commands that only write."""

    log_dir = tmp_path / "logs"
    append_event(log_dir, command="evaluate", outcome=Outcome.ACCEPTED)
    before = (log_dir / LOG_FILE_NAME).read_bytes()
    assert (
        main(
            [
                "diagnostics",
                "--log-dir",
                str(log_dir),
                "--output",
                str(log_dir / LOG_FILE_NAME),
            ]
        )
        == EXIT_CONTRACT_ERROR
    )
    assert json.loads(capsys.readouterr().err)["error"]["code"] == "output_path_unsafe"
    assert (log_dir / LOG_FILE_NAME).read_bytes().startswith(before)
    summary = summarize_log(log_dir).to_dict()
    assert summary["record_count"] == 2
    assert summary["counts_by_error_code"] == {"output_path_unsafe": 1}


def test_a_refused_log_exits_two_with_one_error_object(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The exit-code contract, and a rejection that names a line, not a value."""

    _write_log(tmp_path / "logs", _log(_record(command="rm -rf /")))
    assert (
        main(["events", "summarize", "--directory", str(tmp_path / "logs")])
        == EXIT_CONTRACT_ERROR
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    error = json.loads(captured.err)["error"]
    assert error["code"] == "invalid_enum"
    assert error["path"] == "$.log[0].command"
    assert "rm -rf" not in captured.err


def test_the_command_can_summarise_the_log_it_also_writes_to(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Its own record is appended after the summary, so the next one shows it."""

    log_dir = tmp_path / "logs"
    append_event(log_dir, command="evaluate", outcome=Outcome.ACCEPTED)
    argv = [
        "events",
        "summarize",
        "--directory",
        str(log_dir),
        "--log-dir",
        str(log_dir),
    ]
    assert main(argv) == EXIT_SUCCESS
    first = json.loads(capsys.readouterr().out)
    assert first["counts_by_command"]["events"] == 0
    assert main(argv) == EXIT_SUCCESS
    second = json.loads(capsys.readouterr().out)
    assert second["counts_by_command"]["events"] == 1
    assert second["record_count"] == 2


def test_every_command_the_cli_publishes_can_be_logged() -> None:
    """A command outside the vocabulary logs nothing and says so on stderr.

    ``fixtures`` was outside it from the day the command was added: a run of
    ``fixtures export --log-dir DIR`` printed ``unloggable_command``, appended
    no record, and exited 0, so a run that happened left nothing in the file
    whose whole purpose is to record what ran. Deriving the check from the
    parser rather than restating the list is what keeps the next command from
    doing the same, in either direction: a vocabulary entry no command answers
    to would put a key in the published summary that can never be anything but
    zero.
    """

    groups = [
        action
        for action in _parser()._actions
        if isinstance(action, argparse._SubParsersAction)
    ]
    assert len(groups) == 1
    assert set(groups[0].choices) == set(COMMANDS)


def test_a_fixtures_export_is_logged_like_every_other_command(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The regression that vocabulary test exists for, exercised end to end."""

    log_dir = tmp_path / "logs"
    assert (
        main(
            [
                "fixtures",
                "export",
                "--directory",
                str(tmp_path / "reference"),
                "--quiet",
                "--log-dir",
                str(log_dir),
            ]
        )
        == EXIT_SUCCESS
    )
    assert capsys.readouterr().err == ""
    counts = summarize_log(log_dir).to_dict()["counts_by_command"]
    assert isinstance(counts, dict)
    assert counts["fixtures"] == 1


def test_an_unknown_events_command_is_refused() -> None:
    """A subcommand this iteration does not implement is refused, not ignored."""

    args = argparse.Namespace(command="events", events_command="tail")
    with pytest.raises(ContextSafeError) as raised:
        _operator_command(args)
    assert raised.value.code == "unsupported_command"
