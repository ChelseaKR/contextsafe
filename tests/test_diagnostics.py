"""Diagnostics, the cleanup enumerator, the support bundle, and the local log.

The support bundle is the part that has to be right. A bundle from this tool
could carry exactly the identity data the product exists to protect, so the
central fixture here is a hostile one: a workspace path with a synthetic
patient name in a *directory* component, a name spelled with a Cyrillic
homoglyph, and a medical record number written with spaces between its digits.

Every one of those defeats a filter-based redactor, and this file proves that
rather than asserting it: ``test_the_hostile_fixture_defeats_a_filter`` runs the
repository's own boundary detectors over the hostile strings and shows they
come back clean. A bundle built by scanning-then-blanking would have shipped
them. A bundle built out of typed values cannot contain them at all, because
there is no constructor that accepts free text.
"""

from __future__ import annotations

import json
import os
import unicodedata
from pathlib import Path
from typing import Any

import pytest

from contextsafe import safe_value
from contextsafe.canonical import canonical_json
from contextsafe.cli import EXIT_CONTRACT_ERROR, EXIT_SUCCESS, main
from contextsafe.diagnostics import (
    CLEANUP_SCHEMA_VERSION,
    SUPPORT_BUNDLE_SCHEMA_VERSION,
    EntryKind,
    build_diagnostics,
    build_support_bundle,
    enumerate_cleanup,
    remove_cleanup,
)
from contextsafe.errors import ContextSafeError
from contextsafe.eventlog import (
    LOG_FILE_NAME,
    MAX_LOG_BYTES,
    Outcome,
    append_event,
)
from contextsafe.evidence_store import (
    EvidenceStore,
    store_internal_synthetic_evidence,
)
from contextsafe.preflight import identifier_hits

CYRILLIC_A = "\N{CYRILLIC SMALL LETTER A}"
"""CYRILLIC SMALL LETTER A, written by codepoint.

Spelled out rather than pasted so that the linter's ambiguous-character rule
stays on for the rest of the file: the homoglyph is the point of this fixture,
and an exemption here would be an exemption everywhere.
"""

HOSTILE_NAME = f"Jord{CYRILLIC_A}n Rivera"
"""A name whose ``a`` is the Cyrillic homoglyph. Synthetic; no real person."""

HOSTILE_MRN = "MRN 1 2 3 4 5 6 7"
"""A record number spaced out past a seven-consecutive-digit pattern."""

HOSTILE_DIRECTORY = "exports-Jordan-Rivera-1987"
"""A name in a directory component, where a basename redactor never looks."""

HOSTILE_STRINGS = (HOSTILE_NAME, HOSTILE_MRN, HOSTILE_DIRECTORY, "Jordan Rivera")


def _compact(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in normalized if character.isalnum())


@pytest.fixture
def hostile_workspace(tmp_path: Path) -> Path:
    """A workspace whose path itself carries a synthetic patient name."""

    workspace = tmp_path / HOSTILE_DIRECTORY / f"{HOSTILE_NAME}-store"
    workspace.mkdir(parents=True)
    return workspace


def test_the_hostile_fixture_defeats_a_filter() -> None:
    """The premise of the whole design, checked rather than asserted.

    If the repository's own boundary detectors can see these strings, a
    filter-based redactor would be adequate and this module could be simpler.
    They cannot, which is why the bundle is built out of types instead.
    """

    undetected = [value for value in HOSTILE_STRINGS if not identifier_hits(value)]
    assert undetected == list(HOSTILE_STRINGS), (
        "a detector now catches one of these, so the fixture needs a harder case"
    )


def test_no_safe_value_constructor_accepts_free_text() -> None:
    """There must be no path from a hostile string into a bundle."""

    for hostile in HOSTILE_STRINGS:
        for reject in (
            lambda value: safe_value.version(value),
            lambda value: safe_value.enum_value(value, frozenset({"ok"})),
            lambda value: safe_value.count(value),  # type: ignore[arg-type]
            lambda value: safe_value.flag(value),  # type: ignore[arg-type]
        ):
            with pytest.raises(ContextSafeError):
                reject(hostile)
        # digest and path_shape accept the text and destroy it.
        for rendered in (
            canonical_json(safe_value.digest(hostile).to_json()),
            canonical_json(safe_value.path_shape(Path(hostile) / "a.json").to_json()),
        ):
            assert hostile not in rendered
            assert _compact(hostile) not in _compact(rendered)


def test_the_serializer_refuses_anything_that_is_not_a_safe_value() -> None:
    """ "Somebody added a plain string next year" is a test failure."""

    for node in (HOSTILE_NAME, 7, None, object()):
        with pytest.raises(ContextSafeError) as excinfo:
            safe_value.to_json({"leak": node})  # type: ignore[dict-item]
        assert excinfo.value.code == "unsafe_bundle_value"


def test_the_serializer_refuses_a_key_that_carries_free_text() -> None:
    """A dict key is free text in the same document as the value.

    Every guarantee in `safe_value`'s docstring held for values and none of it
    held for names: `to_json` sorted the keys and wrote them out untouched, so
    the same hostile strings this module exists to keep out serialized cleanly
    as field names, at any depth. `test_the_hostile_fixture_defeats_a_filter`
    above is the proof that the belt-and-braces detector scan would not have
    caught them either.
    """

    for hostile in HOSTILE_STRINGS:
        for section in (
            {hostile: safe_value.count(1)},
            {"runtime": {hostile: safe_value.flag(True)}},
            {"runtime": [{hostile: safe_value.flag(True)}]},
        ):
            with pytest.raises(ContextSafeError) as excinfo:
                safe_value.to_json(section)  # type: ignore[arg-type]
            assert excinfo.value.code == "unsafe_bundle_value"
            assert "field name" in str(excinfo.value)


def test_the_published_field_names_are_the_ones_the_bundle_uses() -> None:
    """The rule has to admit the real bundle, or it is not the rule."""

    accepted = {
        "capabilities",
        "contracts",
        "evidence_index",
        "index_outcome",
        "object_count",
        "path_shape",
        "python",
        "record_count",
        "reported_errors",
        "runner_version",
        "runtime",
        "workspace",
    }
    for name in accepted:
        assert safe_value.field_name(name) == name
    for rejected in ("", "Runtime", "1st", "a b", "a-b", "a" * 65, 7, None):
        with pytest.raises(ContextSafeError):
            safe_value.field_name(rejected)


def test_safe_value_constructors_reject_wrong_types() -> None:
    """Each constructor is total: a safe value, or a rejection."""

    for bad in (-1, True, "3"):
        with pytest.raises(ContextSafeError):
            safe_value.count(bad)  # type: ignore[arg-type]
        with pytest.raises(ContextSafeError):
            safe_value.byte_count(bad)  # type: ignore[arg-type]
    with pytest.raises(ContextSafeError):
        safe_value.flag(1)  # type: ignore[arg-type]
    with pytest.raises(ContextSafeError):
        safe_value.enum_value("ok", frozenset())
    with pytest.raises(ContextSafeError):
        safe_value.enum_value("x" * 65, frozenset({"x" * 65}))
    with pytest.raises(ContextSafeError):
        safe_value.digest(7)  # type: ignore[arg-type]
    assert safe_value.count(0).value == 0
    assert safe_value.byte_count(3).value == 3
    assert safe_value.flag(False).value is False


def test_path_shape_keeps_no_component_of_the_path() -> None:
    """Depth and extension survive. Nothing that names anybody does."""

    shape = safe_value.path_shape(
        Path("/private") / HOSTILE_DIRECTORY / f"{HOSTILE_NAME}.json"
    )
    rendered = canonical_json(shape.to_json())
    assert '"suffix":".json"' in rendered
    assert '"depth":3' in rendered
    for hostile in HOSTILE_STRINGS:
        assert _compact(hostile) not in _compact(rendered)
    other = safe_value.path_shape(Path("x.docx"))
    assert canonical_json(other.to_json()).count('"suffix":"other"') == 1


def test_the_support_bundle_carries_no_part_of_a_hostile_path(
    hostile_workspace: Path,
) -> None:
    """The bundle is assembled from the hostile workspace and stays clean."""

    bundle = build_support_bundle(
        hostile_workspace, error_codes=(HOSTILE_MRN, HOSTILE_NAME)
    )
    rendered = canonical_json(bundle)
    assert bundle["schema_version"] == SUPPORT_BUNDLE_SCHEMA_VERSION
    for hostile in HOSTILE_STRINGS:
        assert hostile not in rendered
        assert _compact(hostile) not in _compact(rendered)
    assert str(hostile_workspace) not in rendered
    assert _compact(str(hostile_workspace)) not in _compact(rendered)


def test_the_support_bundle_is_all_typed_values(hostile_workspace: Path) -> None:
    """Every leaf declares its own kind, which is what makes it reviewable."""

    bundle = build_support_bundle(hostile_workspace)
    kinds = set(_leaf_kinds(bundle["sections"]))
    assert kinds
    assert kinds <= {kind.value for kind in safe_value.SafeKind}


def _leaf_kinds(node: Any) -> list[str]:
    if isinstance(node, dict):
        if set(node) == {"kind", "value"}:
            return [str(node["kind"])]
        return [kind for child in node.values() for kind in _leaf_kinds(child)]
    if isinstance(node, list):
        return [kind for child in node for kind in _leaf_kinds(child)]
    return []


def test_the_bundle_refuses_to_be_emitted_if_the_second_pass_fires(
    monkeypatch: pytest.MonkeyPatch, hostile_workspace: Path
) -> None:
    """Belt and braces: if the constructive layer ever broke, write nothing."""

    monkeypatch.setattr(
        "contextsafe.diagnostics.identifier_hits",
        lambda _text: ("direct-identifier:0",),
    )
    with pytest.raises(ContextSafeError) as excinfo:
        build_support_bundle(hostile_workspace)
    assert excinfo.value.code == "support_bundle_rejected"


def test_diagnostics_report_capability_not_history(tmp_path: Path) -> None:
    """Diagnostics say what the installation can do, not what it has seen."""

    report = build_diagnostics(tmp_path / "absent")
    assert report["workspace"] == {
        "index_outcome": "absent",
        "object_count": 0,
        "record_count": 0,
    }
    rendered = canonical_json(report)
    assert str(tmp_path) not in rendered
    assert "case" not in rendered
    assert "token" not in rendered


def test_diagnostics_report_an_unreadable_index_as_rejected(tmp_path: Path) -> None:
    """A workspace that exists but does not validate is not reported as ok."""

    workspace = tmp_path / "ws"
    workspace.mkdir(mode=0o700)
    (workspace / "contextsafe.sqlite").write_bytes(b"not a database")
    report = build_diagnostics(workspace)
    assert report["workspace"]["index_outcome"] == "rejected"  # type: ignore[index]


def test_diagnostics_with_no_workspace_say_absent() -> None:
    """Calling without a workspace is legitimate and says so."""

    report = build_diagnostics()
    assert report["workspace"]["index_outcome"] == "absent"  # type: ignore[index]
    assert report["runtime"]["implementation"]  # type: ignore[index]


@pytest.fixture
def populated_workspace(
    tmp_path: Path,
    evidence_source_json: dict[str, Any],
    evidence_scope: Any,
    evidence_metadata: Any,
) -> Path:
    """A workspace with one committed object, plus leftovers to classify."""

    workspace = tmp_path / "ws"
    source = tmp_path / "source.json"
    source.write_bytes(canonical_json(evidence_source_json).encode("utf-8"))
    store_internal_synthetic_evidence(
        source,
        workspace=workspace,
        scope=evidence_scope,
        metadata=evidence_metadata,
    )
    store = EvidenceStore(workspace)
    (store.staging_root / "abandoned.part").write_bytes(b"x" * 5)
    (workspace / "notes.txt").write_bytes(b"an operator's own file")
    return workspace


def test_the_enumerator_classifies_everything_it_finds(
    populated_workspace: Path,
) -> None:
    """Index, object, staging, directory, and one thing that is none of those."""

    plan = enumerate_cleanup(populated_workspace)
    kinds = {entry.kind for entry in plan.entries}
    assert plan.exists
    assert EntryKind.INDEX in kinds
    assert EntryKind.OBJECT in kinds
    assert EntryKind.STAGING in kinds
    assert EntryKind.DIRECTORY in kinds
    assert EntryKind.UNEXPECTED in kinds
    summary = plan.to_dict()
    assert summary["schema_version"] == CLEANUP_SCHEMA_VERSION
    assert summary["removable"]["count"] > 0  # type: ignore[index]
    rendered = canonical_json(summary)
    assert "notes.txt" not in rendered
    assert str(populated_workspace) not in rendered


def test_the_enumerator_reports_an_absent_workspace(tmp_path: Path) -> None:
    """No workspace is a fact, not an error."""

    plan = enumerate_cleanup(tmp_path / "nothing")
    assert not plan.exists
    assert plan.entries == ()
    with pytest.raises(ContextSafeError) as excinfo:
        remove_cleanup(plan)
    assert excinfo.value.code == "cleanup_workspace_absent"


def test_removal_leaves_what_it_could_not_classify(
    populated_workspace: Path,
) -> None:
    """An unclassifiable entry is somebody else's file until they say so."""

    plan = enumerate_cleanup(populated_workspace)
    removed, retained = remove_cleanup(plan)
    assert removed == len(plan.removable)
    assert retained == len(plan.retained)
    assert (populated_workspace / "notes.txt").exists()
    assert not (populated_workspace / "contextsafe.sqlite").exists()
    assert populated_workspace.exists()


def test_removal_never_follows_a_symbolic_link(
    populated_workspace: Path, tmp_path: Path
) -> None:
    """A link out of the workspace must not become a way to delete elsewhere."""

    outside = tmp_path / "precious.json"
    outside.write_bytes(b"{}")
    link = populated_workspace / "evidence" / "escape"
    link.symlink_to(outside)
    plan = enumerate_cleanup(populated_workspace)
    linked = [entry for entry in plan.entries if entry.is_symlink]
    assert linked and all(not entry.removable for entry in linked)
    remove_cleanup(plan)
    assert outside.exists()
    assert link.is_symlink()


def test_the_cleanup_command_will_not_delete_without_confirmation(
    populated_workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Two flags, because one flag is how an operator loses a workspace."""

    code = main(["cleanup", "--workspace", str(populated_workspace), "--remove"])
    assert code == EXIT_CONTRACT_ERROR
    assert "cleanup_not_confirmed" in capsys.readouterr().err
    assert (populated_workspace / "contextsafe.sqlite").exists()


def test_the_cleanup_command_removes_when_confirmed(
    populated_workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """And with both flags it does exactly what it enumerated."""

    code = main(
        [
            "cleanup",
            "--workspace",
            str(populated_workspace),
            "--remove",
            "--confirm",
        ]
    )
    assert code == EXIT_SUCCESS
    summary = json.loads(capsys.readouterr().out)
    assert summary["removed"] > 0
    assert summary["retained_count"] == 1
    assert not (populated_workspace / "contextsafe.sqlite").exists()


def test_the_operator_commands_emit_canonical_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Every operator command is a machine artifact like the others."""

    for argv in (
        ["diagnostics"],
        ["support-bundle"],
        ["cleanup", "--workspace", str(tmp_path / "absent")],
    ):
        assert main(argv) == EXIT_SUCCESS
        printed = capsys.readouterr().out
        assert printed.endswith("\n")
        assert canonical_json(json.loads(printed)) + "\n" == printed


def test_no_command_writes_a_log_unless_asked(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The default remains what the privacy canary assumes: nothing is written."""

    before = set(_all_files(tmp_path))
    assert main(["diagnostics", "--workspace", str(tmp_path)]) == EXIT_SUCCESS
    capsys.readouterr()
    assert set(_all_files(tmp_path)) == before


def _all_files(root: Path) -> list[Path]:
    return [
        Path(parent) / name
        for parent, _directories, files in os.walk(root)
        for name in files
    ]


def test_the_log_records_a_closed_vocabulary(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """One line per run: command, outcome, error code. Nothing else."""

    log_dir = tmp_path / "logs"
    assert main(["diagnostics", "--log-dir", str(log_dir)]) == EXIT_SUCCESS
    assert (
        main(
            [
                "cleanup",
                "--workspace",
                str(tmp_path / "gone"),
                "--remove",
                "--log-dir",
                str(log_dir),
            ]
        )
        == EXIT_CONTRACT_ERROR
    )
    capsys.readouterr()
    lines = (log_dir / LOG_FILE_NAME).read_text(encoding="utf-8").splitlines()
    records = [json.loads(line) for line in lines]
    assert [record["command"] for record in records] == ["diagnostics", "cleanup"]
    assert [record["outcome"] for record in records] == ["accepted", "rejected"]
    assert records[1]["error_code"] == "cleanup_not_confirmed"
    assert [record["sequence"] for record in records] == [0, 1]
    assert all(
        set(record)
        == {"command", "error_code", "outcome", "schema_version", "sequence"}
        for record in records
    )
    assert str(tmp_path) not in "".join(lines)


def test_the_log_refuses_a_command_it_does_not_publish(tmp_path: Path) -> None:
    """A record is drawn from a closed set, not from whatever was passed."""

    with pytest.raises(ContextSafeError) as excinfo:
        append_event(tmp_path, command="rm -rf /", outcome=Outcome.ACCEPTED)
    assert excinfo.value.code == "unloggable_command"


def test_the_log_refuses_an_error_code_that_is_a_message(tmp_path: Path) -> None:
    """There is no message field, and an error code may not become one."""

    with pytest.raises(ContextSafeError) as excinfo:
        append_event(
            tmp_path,
            command="evaluate",
            outcome=Outcome.REJECTED,
            error_code=f"failed reading {HOSTILE_NAME}",
        )
    assert excinfo.value.code == "unloggable_error_code"


def test_the_log_refuses_a_symbolic_link(tmp_path: Path) -> None:
    """Appending through a link is how a log becomes a write primitive."""

    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / LOG_FILE_NAME).symlink_to(tmp_path / "elsewhere")
    with pytest.raises(ContextSafeError) as excinfo:
        append_event(log_dir, command="evaluate", outcome=Outcome.ACCEPTED)
    assert excinfo.value.code == "log_io_error"


def test_the_log_stops_at_its_published_size_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unbounded log is an operational hazard of its own."""

    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / LOG_FILE_NAME).write_bytes(b"\n" * MAX_LOG_BYTES)
    with pytest.raises(ContextSafeError) as excinfo:
        append_event(log_dir, command="evaluate", outcome=Outcome.ACCEPTED)
    assert excinfo.value.code == "log_full"


def test_a_logging_failure_does_not_change_the_command_result(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The command already succeeded. A full log must not rewrite that."""

    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / LOG_FILE_NAME).write_bytes(b"\n" * MAX_LOG_BYTES)
    assert main(["diagnostics", "--quiet", "--log-dir", str(log_dir)]) == EXIT_SUCCESS
    assert "log_full" in capsys.readouterr().err


def test_the_log_directory_is_owner_only_where_the_platform_allows(
    tmp_path: Path,
) -> None:
    """A log of what an operator ran is not something to leave world-readable."""

    log_dir = tmp_path / "logs"
    append_event(log_dir, command="evaluate", outcome=Outcome.ACCEPTED)
    if os.name == "posix":
        assert log_dir.stat().st_mode & 0o077 == 0
        assert (log_dir / LOG_FILE_NAME).stat().st_mode & 0o077 == 0


def test_an_unrecognised_object_path_is_unexpected(populated_workspace: Path) -> None:
    """A file in the object tree that is not shaped like a hash is not one."""

    store = EvidenceStore(populated_workspace)
    (store.raw_root / "stray.bin").write_bytes(b"x")
    (store.staging_root / "stray.bin").write_bytes(b"x")
    plan = enumerate_cleanup(populated_workspace)
    unexpected = [entry for entry in plan.entries if entry.kind is EntryKind.UNEXPECTED]
    assert len(unexpected) >= 3
    assert all(not entry.removable for entry in unexpected)


def test_an_unstattable_entry_is_counted_as_zero_bytes(
    monkeypatch: pytest.MonkeyPatch, populated_workspace: Path
) -> None:
    """A file that vanishes mid-walk must not abort the enumeration."""

    real_stat = Path.stat

    def flaky(self: Path, *args: Any, **kwargs: Any) -> Any:
        if self.suffix == ".part":
            raise OSError("vanished")
        return real_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", flaky)
    plan = enumerate_cleanup(populated_workspace)
    staging = [entry for entry in plan.entries if entry.kind is EntryKind.STAGING]
    assert staging and all(entry.byte_count == 0 for entry in staging)


def test_removal_reports_a_file_it_cannot_delete(
    monkeypatch: pytest.MonkeyPatch, populated_workspace: Path
) -> None:
    """A file that will not unlink is an error, not a silent partial cleanup."""

    def refuse(self: Path, *args: Any, **kwargs: Any) -> None:
        raise OSError("refused")

    plan = enumerate_cleanup(populated_workspace)
    monkeypatch.setattr(Path, "unlink", refuse)
    with pytest.raises(ContextSafeError) as excinfo:
        remove_cleanup(plan)
    assert excinfo.value.code == "cleanup_io_error"


def test_an_unreadable_log_is_reported_not_overwritten(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Failing to count existing records must not restart the sequence at zero."""

    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / LOG_FILE_NAME).write_bytes(b"")

    def refuse(self: Path, *args: Any, **kwargs: Any) -> Any:
        raise OSError("refused")

    monkeypatch.setattr(Path, "open", refuse)
    with pytest.raises(ContextSafeError) as excinfo:
        append_event(log_dir, command="evaluate", outcome=Outcome.ACCEPTED)
    assert excinfo.value.code == "log_io_error"


def test_a_log_directory_that_cannot_be_created_is_reported(tmp_path: Path) -> None:
    """A file where the log directory should be is a rejection, not a crash."""

    blocked = tmp_path / "logs"
    blocked.write_bytes(b"not a directory")
    with pytest.raises(ContextSafeError) as excinfo:
        append_event(blocked, command="evaluate", outcome=Outcome.ACCEPTED)
    assert excinfo.value.code == "log_io_error"


def test_a_log_file_that_cannot_be_opened_is_reported(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The append open is the last chance to fail closed, and it takes it."""

    real_open = os.open

    def refuse(path: Any, flags: int, *args: Any, **kwargs: Any) -> int:
        if str(path).endswith(LOG_FILE_NAME):
            raise OSError("refused")
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", refuse)
    with pytest.raises(ContextSafeError) as excinfo:
        append_event(tmp_path / "logs", command="evaluate", outcome=Outcome.ACCEPTED)
    assert excinfo.value.code == "log_io_error"


@pytest.mark.skipif(os.name == "nt", reason="POSIX directory permissions")
@pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0,
    reason="root bypasses the permission bit this test relies on",
)
def test_removal_reports_a_directory_it_cannot_delete(
    populated_workspace: Path,
) -> None:
    """A directory that will not rmdir is an error, exactly as a file is.

    Not a mock: the parent is made read-only, so ``rmdir`` fails the way it
    fails on an operator's machine. Before the narrowing this returned a
    retained count and a success exit, and the directory was still there.
    """

    store = EvidenceStore(populated_workspace)
    plan = enumerate_cleanup(populated_workspace)
    guarded = store.raw_root
    guarded.chmod(0o500)
    try:
        with pytest.raises(ContextSafeError) as excinfo:
            remove_cleanup(plan)
    finally:
        guarded.chmod(0o700)
    assert excinfo.value.code == "cleanup_io_error"


@pytest.mark.skipif(os.name == "nt", reason="POSIX directory permissions")
@pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0,
    reason="root bypasses the permission bit this test relies on",
)
def test_the_cleanup_command_exits_two_when_a_removal_fails(
    populated_workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The exit code this change moves, pinned so it cannot move back.

    A removal that fails used to leave the command on ``EXIT_SUCCESS`` with a
    ``retained_count`` covering for it. It is a contract error now, and an
    operator's ``&&`` no longer runs on a cleanup that did not happen.
    """

    store = EvidenceStore(populated_workspace)
    guarded = store.raw_root
    guarded.chmod(0o500)
    try:
        code = main(
            [
                "cleanup",
                "--workspace",
                str(populated_workspace),
                "--remove",
                "--confirm",
            ]
        )
    finally:
        guarded.chmod(0o700)
    assert code == EXIT_CONTRACT_ERROR
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err)["error"]["code"] == "cleanup_io_error"
