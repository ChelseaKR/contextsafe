"""Content-addressed evidence index, rollback, crash, and concurrency tests."""

import hashlib
import json
import os
import sqlite3
import stat
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Barrier
from typing import Any, NoReturn

import pytest
from jsonschema import Draft202012Validator

import contextsafe.evidence_store as store_module
from contextsafe.errors import ContextSafeError
from contextsafe.evidence import EvidenceMetadata, EvidenceScope
from contextsafe.evidence_store import (
    EvidenceStore,
    store_internal_synthetic_evidence,
)
from contextsafe.preflight import PreflightedSource

ROOT = Path(__file__).resolve().parents[1]


class _CloseFailingConnection:
    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        fail_statement: str | None = None,
    ) -> None:
        self._connection = connection
        self._fail_statement = fail_statement

    @property
    def in_transaction(self) -> bool:
        return self._connection.in_transaction

    def execute(
        self, statement: str, *args: object, **kwargs: object
    ) -> sqlite3.Cursor:
        if self._fail_statement is not None and self._fail_statement in statement:
            raise sqlite3.OperationalError("injected connection operation failure")
        return self._connection.execute(statement, *args, **kwargs)

    def close(self) -> None:
        self._connection.close()
        raise sqlite3.OperationalError("injected connection close failure")


def _write_source(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value, separators=(",", ":")), encoding="utf-8")
    return path


def _store(
    source: Path,
    workspace: Path,
    scope: EvidenceScope,
    metadata: EvidenceMetadata,
):
    return store_internal_synthetic_evidence(
        source,
        workspace=workspace,
        scope=scope,
        metadata=metadata,
    )


def _object_path(workspace: Path, raw_sha256: str) -> Path:
    return workspace / "evidence" / "raw" / "sha256" / raw_sha256[:2] / raw_sha256


def _tree_snapshot(root: Path) -> dict[str, tuple[int, int, int, int, bytes | None]]:
    paths = (root, *root.rglob("*"))
    snapshot: dict[str, tuple[int, int, int, int, bytes | None]] = {}
    for path in paths:
        details = path.lstat()
        payload = path.read_bytes() if stat.S_ISREG(details.st_mode) else None
        snapshot[str(path.relative_to(root))] = (
            details.st_mode,
            details.st_size,
            details.st_mtime_ns,
            details.st_ctime_ns,
            payload,
        )
    return snapshot


def _sqlite_sequence_rows(database: Path) -> tuple[tuple[object, object], ...]:
    connection = sqlite3.connect(database)
    try:
        return tuple(
            connection.execute(
                "SELECT name, seq FROM sqlite_sequence ORDER BY name"
            ).fetchall()
        )
    finally:
        connection.close()


def test_store_writes_private_content_address_and_append_only_record(
    tmp_path: Path,
    evidence_source_json: dict[str, Any],
    evidence_scope: EvidenceScope,
    evidence_metadata: EvidenceMetadata,
) -> None:
    source = _write_source(tmp_path / "source.json", evidence_source_json)
    workspace = tmp_path / "workspace"
    record = _store(source, workspace, evidence_scope, evidence_metadata)

    raw = source.read_bytes()
    assert record.raw_sha256 == hashlib.sha256(raw).hexdigest()
    assert record.usable_for_execution is False
    assert record.authorization_status == "not_verified_internal_test_only"
    object_path = _object_path(workspace, record.raw_sha256)
    assert object_path.read_bytes() == raw
    assert stat.S_IMODE(object_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(workspace.stat().st_mode) == 0o700
    assert stat.S_IMODE((workspace / "contextsafe.sqlite").stat().st_mode) == 0o600

    store = EvidenceStore(workspace)
    assert store.get(record.evidence_id) == record
    assert store.get("EVD-" + "f" * 64) is None
    assert store.list_records() == (record,)
    store.verify_integrity()

    schema = json.loads(
        (ROOT / "schemas" / "contextsafe-evidence-v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(record.to_dict())


def test_identical_import_is_idempotent_and_metadata_change_appends(
    tmp_path: Path,
    evidence_source_json: dict[str, Any],
    evidence_scope: EvidenceScope,
    evidence_metadata: EvidenceMetadata,
) -> None:
    source = _write_source(tmp_path / "source.json", evidence_source_json)
    workspace = tmp_path / "workspace"
    first = _store(source, workspace, evidence_scope, evidence_metadata)
    second = _store(source, workspace, evidence_scope, evidence_metadata)
    assert first == second
    assert EvidenceStore(workspace).list_records() == (first,)

    later = replace(
        evidence_metadata,
        captured_at=evidence_metadata.captured_at.replace(second=1),
    )
    third = _store(source, workspace, evidence_scope, later)
    assert third.evidence_id != first.evidence_id
    assert third.raw_sha256 == first.raw_sha256
    assert EvidenceStore(workspace).list_records() == (first, third)
    raw_files = [
        path
        for path in (workspace / "evidence" / "raw" / "sha256").glob("*/*")
        if path.is_file()
    ]
    assert raw_files == [_object_path(workspace, first.raw_sha256)]


def test_sqlite_guards_record_updates_and_deletes(
    tmp_path: Path,
    evidence_source_json: dict[str, Any],
    evidence_scope: EvidenceScope,
    evidence_metadata: EvidenceMetadata,
) -> None:
    source = _write_source(tmp_path / "source.json", evidence_source_json)
    workspace = tmp_path / "workspace"
    record = _store(source, workspace, evidence_scope, evidence_metadata)
    connection = sqlite3.connect(workspace / "contextsafe.sqlite")
    try:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE evidence_records SET raw_sha256 = ? WHERE evidence_id = ?",
                ("0" * 64, record.evidence_id),
            )
        connection.rollback()
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "DELETE FROM evidence_records WHERE evidence_id = ?",
                (record.evidence_id,),
            )
    finally:
        connection.close()


def test_rejection_happens_before_workspace_persistence(
    tmp_path: Path,
    evidence_source_json: dict[str, Any],
    evidence_scope: EvidenceScope,
    evidence_metadata: EvidenceMetadata,
) -> None:
    evidence_source_json["records"][0]["value_code"] = "person@example.invalid"
    source = _write_source(tmp_path / "source.json", evidence_source_json)
    workspace = tmp_path / "workspace"
    with pytest.raises(ContextSafeError) as raised:
        _store(source, workspace, evidence_scope, evidence_metadata)
    assert raised.value.code == "direct_identifier_detected"
    assert not workspace.exists()


def test_source_must_remain_outside_workspace(
    tmp_path: Path,
    evidence_source_json: dict[str, Any],
    evidence_scope: EvidenceScope,
    evidence_metadata: EvidenceMetadata,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir(mode=0o700)
    source = _write_source(workspace / "source.json", evidence_source_json)
    with pytest.raises(ContextSafeError) as raised:
        _store(source, workspace, evidence_scope, evidence_metadata)
    assert raised.value.code == "source_not_caller_owned"
    assert not (workspace / "contextsafe.sqlite").exists()


def test_unsafe_workspace_permissions_fail_before_raw_copy(
    tmp_path: Path,
    evidence_source_json: dict[str, Any],
    evidence_scope: EvidenceScope,
    evidence_metadata: EvidenceMetadata,
) -> None:
    source = _write_source(tmp_path / "source.json", evidence_source_json)
    workspace = tmp_path / "workspace"
    workspace.mkdir(mode=0o755)
    os.chmod(workspace, 0o755)  # noqa: S103 - intentionally unsafe fixture
    with pytest.raises(ContextSafeError) as raised:
        _store(source, workspace, evidence_scope, evidence_metadata)
    assert raised.value.code == "workspace_permission_unsafe"
    assert not (workspace / "evidence").exists()


def test_insert_failure_rolls_back_index_object_and_stage(
    tmp_path: Path,
    evidence_source_json: dict[str, Any],
    evidence_scope: EvidenceScope,
    evidence_metadata: EvidenceMetadata,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _write_source(tmp_path / "source.json", evidence_source_json)
    workspace = tmp_path / "workspace"

    def fail(_connection: sqlite3.Connection, _record: object) -> None:
        raise ContextSafeError("injected_index_failure", "$", "injected safe failure")

    monkeypatch.setattr(EvidenceStore, "_append_record", staticmethod(fail))
    with pytest.raises(ContextSafeError) as raised:
        _store(source, workspace, evidence_scope, evidence_metadata)
    assert raised.value.code == "injected_index_failure"
    assert EvidenceStore(workspace).list_records() == ()
    raw_root = workspace / "evidence" / "raw" / "sha256"
    assert not [path for path in raw_root.glob("*/*") if path.is_file()]
    assert not list((raw_root / ".staging").iterdir())


def test_primary_index_error_survives_object_cleanup_denial_and_exposes_orphan(
    tmp_path: Path,
    evidence_source_json: dict[str, Any],
    evidence_scope: EvidenceScope,
    evidence_metadata: EvidenceMetadata,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _write_source(tmp_path / "source.json", evidence_source_json)
    workspace = tmp_path / "workspace"
    raw_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    original_unlink = Path.unlink

    def deny_object_unlink(path: Path, *args: object, **kwargs: object) -> None:
        if path.name == raw_sha256:
            raise PermissionError("injected object cleanup denial")
        original_unlink(path, *args, **kwargs)

    def fail(_connection: sqlite3.Connection, _record: object) -> None:
        raise ContextSafeError("injected_index_failure", "$", "injected failure")

    monkeypatch.setattr(Path, "unlink", deny_object_unlink)
    monkeypatch.setattr(EvidenceStore, "_append_record", staticmethod(fail))

    with pytest.raises(ContextSafeError) as raised:
        _store(source, workspace, evidence_scope, evidence_metadata)

    assert raised.value.code == "injected_index_failure"
    assert _object_path(workspace, raw_sha256).read_bytes() == source.read_bytes()
    connection = sqlite3.connect(workspace / "contextsafe.sqlite")
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM evidence_records"
        ).fetchone() == (0,)
    finally:
        connection.close()
    assert not list((workspace / "evidence" / "raw" / "sha256" / ".staging").iterdir())


def test_object_cleanup_denial_without_primary_is_a_structured_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    object_path = workspace / "orphan"
    workspace.mkdir(mode=0o700)
    object_path.write_bytes(b"orphan")
    os.chmod(object_path, 0o600)

    def deny_unlink(_path: Path, *args: object, **kwargs: object) -> None:
        raise PermissionError("injected cleanup denial")

    monkeypatch.setattr(Path, "unlink", deny_unlink)
    with pytest.raises(ContextSafeError) as raised:
        EvidenceStore(workspace)._remove_object(object_path)
    assert raised.value.code == "evidence_store_io_error"
    assert object_path.read_bytes() == b"orphan"


def test_descriptor_close_denial_is_structured_without_primary_and_preserves_primary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "descriptor"
    path.write_bytes(b"")
    cleanup_descriptor = os.open(path, os.O_RDONLY)
    primary_descriptor = os.open(path, os.O_RDONLY)
    original_close = os.close

    def deny_test_descriptors(descriptor: int) -> None:
        if descriptor in {cleanup_descriptor, primary_descriptor}:
            raise OSError("injected descriptor close denial")
        original_close(descriptor)

    monkeypatch.setattr(os, "close", deny_test_descriptors)
    try:
        with (
            pytest.raises(ContextSafeError) as cleanup_raised,
            store_module._closing_descriptor(
                cleanup_descriptor,
                code="evidence_store_io_error",
                message="injected cleanup failed",
            ),
        ):
            pass
        assert cleanup_raised.value.code == "evidence_store_io_error"

        with (
            pytest.raises(ContextSafeError) as primary_raised,
            store_module._closing_descriptor(
                primary_descriptor,
                code="evidence_store_io_error",
                message="injected cleanup failed",
            ),
        ):
            raise ContextSafeError("injected_primary", "$", "injected primary failure")
        assert primary_raised.value.code == "injected_primary"
    finally:
        original_close(cleanup_descriptor)
        original_close(primary_descriptor)


def test_commit_cleanup_without_primary_reports_stage_and_connection_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir(mode=0o700)
    stage = workspace / "leaked.part"
    stage.write_bytes(b"leaked")
    connection = sqlite3.connect(":memory:")

    def deny_unlink(_path: Path, *args: object, **kwargs: object) -> None:
        raise PermissionError("injected cleanup denial")

    monkeypatch.setattr(Path, "unlink", deny_unlink)
    with pytest.raises(ContextSafeError) as raised:
        EvidenceStore(workspace)._finish_commit_cleanup(connection, stage, None)
    assert raised.value.code == "evidence_store_io_error"
    assert stage.read_bytes() == b"leaked"
    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")

    class FailingConnection:
        def close(self) -> None:
            raise sqlite3.OperationalError("injected connection close denial")

    failing_connection: Any = FailingConnection()
    with pytest.raises(ContextSafeError) as raised:
        EvidenceStore(workspace)._finish_commit_cleanup(failing_connection, None, None)
    assert raised.value.code == "evidence_store_io_error"


def test_object_cleanup_fsync_error_is_structured_unless_primary_exists(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir(mode=0o700)
    object_path = workspace / "orphan"

    def fail_fsync(_path: Path) -> None:
        raise ContextSafeError(
            "evidence_store_io_error", "$", "injected directory fsync denial"
        )

    monkeypatch.setattr(EvidenceStore, "_fsync_directory", staticmethod(fail_fsync))
    object_path.write_bytes(b"first")
    with pytest.raises(ContextSafeError) as raised:
        EvidenceStore(workspace)._remove_object(object_path)
    assert raised.value.code == "evidence_store_io_error"
    assert not object_path.exists()

    object_path.write_bytes(b"second")
    primary = ContextSafeError("injected_primary", "$", "injected primary failure")
    EvidenceStore(workspace)._remove_object(object_path, primary_error=primary)
    assert not object_path.exists()


def test_second_pass_failure_leaves_no_content_or_index_row(
    tmp_path: Path,
    evidence_source_json: dict[str, Any],
    evidence_scope: EvidenceScope,
    evidence_metadata: EvidenceMetadata,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _write_source(tmp_path / "source.json", evidence_source_json)
    workspace = tmp_path / "workspace"

    def fail_copy(self: PreflightedSource, _destination_descriptor: int) -> None:
        raise ContextSafeError(
            "source_mutated", "$", "evidence changed after its boundary check"
        )

    monkeypatch.setattr(PreflightedSource, "copy_to", fail_copy)
    with pytest.raises(ContextSafeError) as raised:
        _store(source, workspace, evidence_scope, evidence_metadata)
    assert raised.value.code == "source_mutated"
    assert EvidenceStore(workspace).list_records() == ()
    raw_root = workspace / "evidence" / "raw" / "sha256"
    assert not [path for path in raw_root.glob("*/*") if path.is_file()]
    assert not list((raw_root / ".staging").iterdir())


def test_primary_copy_error_survives_stage_cleanup_denial_and_exposes_stage_leak(
    tmp_path: Path,
    evidence_source_json: dict[str, Any],
    evidence_scope: EvidenceScope,
    evidence_metadata: EvidenceMetadata,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _write_source(tmp_path / "source.json", evidence_source_json)
    workspace = tmp_path / "workspace"
    original_unlink = Path.unlink

    def fail_copy(self: PreflightedSource, _destination_descriptor: int) -> None:
        raise ContextSafeError(
            "source_mutated", "$", "evidence changed after its boundary check"
        )

    def deny_stage_unlink(path: Path, *args: object, **kwargs: object) -> None:
        if path.suffix == ".part":
            raise PermissionError("injected staging cleanup denial")
        original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(PreflightedSource, "copy_to", fail_copy)
    monkeypatch.setattr(Path, "unlink", deny_stage_unlink)
    with pytest.raises(ContextSafeError) as raised:
        _store(source, workspace, evidence_scope, evidence_metadata)

    assert raised.value.code == "source_mutated"
    raw_root = workspace / "evidence" / "raw" / "sha256"
    assert len(list((raw_root / ".staging").iterdir())) == 1
    assert not [
        path
        for path in raw_root.glob("*/*")
        if path.is_file() and path.parent != raw_root / ".staging"
    ]
    connection = sqlite3.connect(workspace / "contextsafe.sqlite")
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM evidence_records"
        ).fetchone() == (0,)
    finally:
        connection.close()


def test_next_transaction_recovers_crash_orphans_and_staging(
    tmp_path: Path,
    evidence_source_json: dict[str, Any],
    evidence_scope: EvidenceScope,
    evidence_metadata: EvidenceMetadata,
) -> None:
    source = _write_source(tmp_path / "source.json", evidence_source_json)
    workspace = tmp_path / "workspace"
    record = _store(source, workspace, evidence_scope, evidence_metadata)
    raw_root = workspace / "evidence" / "raw" / "sha256"
    orphan_bytes = b"accepted-before-crash"
    orphan_hash = hashlib.sha256(orphan_bytes).hexdigest()
    orphan_dir = raw_root / orphan_hash[:2]
    orphan_dir.mkdir(mode=0o700)
    orphan = orphan_dir / orphan_hash
    orphan.write_bytes(orphan_bytes)
    os.chmod(orphan, 0o600)
    stage = raw_root / ".staging" / "crashed.part"
    stage.write_bytes(orphan_bytes)
    os.chmod(stage, 0o600)

    assert _store(source, workspace, evidence_scope, evidence_metadata) == record
    assert not orphan.exists()
    assert not stage.exists()
    EvidenceStore(workspace).verify_integrity()


def test_concurrent_identical_imports_serialize_to_one_record(
    tmp_path: Path,
    evidence_source_json: dict[str, Any],
    evidence_scope: EvidenceScope,
    evidence_metadata: EvidenceMetadata,
) -> None:
    source = _write_source(tmp_path / "source.json", evidence_source_json)
    workspace = tmp_path / "workspace"

    def run(_index: int):
        return _store(source, workspace, evidence_scope, evidence_metadata)

    with ThreadPoolExecutor(max_workers=6) as executor:
        records = tuple(executor.map(run, range(12)))
    assert len({record.evidence_id for record in records}) == 1
    assert EvidenceStore(workspace).list_records() == (records[0],)
    EvidenceStore(workspace).verify_integrity()


def test_corrupt_content_object_fails_integrity_verification(
    tmp_path: Path,
    evidence_source_json: dict[str, Any],
    evidence_scope: EvidenceScope,
    evidence_metadata: EvidenceMetadata,
) -> None:
    source = _write_source(tmp_path / "source.json", evidence_source_json)
    workspace = tmp_path / "workspace"
    record = _store(source, workspace, evidence_scope, evidence_metadata)
    _object_path(workspace, record.raw_sha256).write_bytes(b"corrupt")
    with pytest.raises(ContextSafeError) as raised:
        EvidenceStore(workspace).verify_integrity()
    assert raised.value.code == "evidence_store_corrupt"


def test_missing_unsafe_and_unsupported_indexes_fail_closed(tmp_path: Path) -> None:
    missing = EvidenceStore(tmp_path / "missing")
    with pytest.raises(ContextSafeError) as raised:
        missing.list_records()
    assert raised.value.code == "evidence_index_missing"

    workspace = tmp_path / "unsafe"
    workspace.mkdir(mode=0o700)
    target = tmp_path / "target.sqlite"
    target.write_bytes(b"")
    (workspace / "contextsafe.sqlite").symlink_to(target)
    with pytest.raises(ContextSafeError) as raised:
        EvidenceStore(workspace).list_records()
    assert raised.value.code == "evidence_store_path_unsafe"


def test_index_version_and_canonical_columns_are_verified_on_next_transaction(
    tmp_path: Path,
    evidence_source_json: dict[str, Any],
    evidence_scope: EvidenceScope,
    evidence_metadata: EvidenceMetadata,
) -> None:
    source = _write_source(tmp_path / "source.json", evidence_source_json)
    workspace = tmp_path / "workspace"
    record = _store(source, workspace, evidence_scope, evidence_metadata)
    connection = sqlite3.connect(workspace / "contextsafe.sqlite")
    try:
        connection.execute(
            "UPDATE evidence_index_metadata SET schema_version = 'future'"
        )
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(ContextSafeError) as raised:
        EvidenceStore(workspace).list_records()
    assert raised.value.code == "unsupported_evidence_index"

    connection = sqlite3.connect(workspace / "contextsafe.sqlite")
    try:
        connection.execute(
            "UPDATE evidence_index_metadata SET schema_version = ?",
            (store_module.INDEX_SCHEMA_VERSION,),
        )
        connection.execute("DROP TRIGGER evidence_records_no_update")
        connection.execute(
            "UPDATE evidence_records SET raw_sha256 = ? WHERE evidence_id = ?",
            ("f" * 64, record.evidence_id),
        )
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(ContextSafeError) as raised:
        _store(source, workspace, evidence_scope, evidence_metadata)
    assert raised.value.code == "evidence_store_corrupt"


@pytest.mark.parametrize(
    ("damage_sql", "remaining_sql"),
    [
        (
            "DROP TABLE evidence_records",
            "SELECT COUNT(*) FROM sqlite_master WHERE name = 'evidence_records'",
        ),
        (
            "DELETE FROM evidence_index_metadata",
            "SELECT COUNT(*) FROM evidence_index_metadata",
        ),
        (
            "DROP TRIGGER evidence_records_no_delete",
            "SELECT COUNT(*) FROM sqlite_master "
            "WHERE name = 'evidence_records_no_delete'",
        ),
    ],
)
def test_existing_index_damage_is_not_repaired_or_allowed_to_delete_objects(
    tmp_path: Path,
    evidence_source_json: dict[str, Any],
    evidence_scope: EvidenceScope,
    evidence_metadata: EvidenceMetadata,
    damage_sql: str,
    remaining_sql: str,
) -> None:
    source = _write_source(tmp_path / "source.json", evidence_source_json)
    workspace = tmp_path / "workspace"
    record = _store(source, workspace, evidence_scope, evidence_metadata)
    object_path = _object_path(workspace, record.raw_sha256)
    original_bytes = object_path.read_bytes()
    database = workspace / "contextsafe.sqlite"
    connection = sqlite3.connect(database)
    try:
        connection.execute(damage_sql)
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(ContextSafeError) as raised:
        EvidenceStore(workspace).list_records()
    assert raised.value.code == "evidence_store_corrupt"
    connection = sqlite3.connect(database)
    try:
        assert connection.execute(remaining_sql).fetchone() == (0,)
    finally:
        connection.close()

    with pytest.raises(ContextSafeError) as raised:
        _store(source, workspace, evidence_scope, evidence_metadata)
    assert raised.value.code == "evidence_store_corrupt"
    assert object_path.read_bytes() == original_bytes


def test_truncated_existing_index_fails_closed_without_reinitialization(
    tmp_path: Path,
    evidence_source_json: dict[str, Any],
    evidence_scope: EvidenceScope,
    evidence_metadata: EvidenceMetadata,
) -> None:
    source = _write_source(tmp_path / "source.json", evidence_source_json)
    workspace = tmp_path / "workspace"
    record = _store(source, workspace, evidence_scope, evidence_metadata)
    object_path = _object_path(workspace, record.raw_sha256)
    original_bytes = object_path.read_bytes()
    database = workspace / "contextsafe.sqlite"
    database.write_bytes(b"")

    with pytest.raises(ContextSafeError) as raised:
        EvidenceStore(workspace).verify_integrity()
    assert raised.value.code == "evidence_store_corrupt"
    assert database.read_bytes() == b""
    with pytest.raises(ContextSafeError) as raised:
        _store(source, workspace, evidence_scope, evidence_metadata)
    assert raised.value.code == "evidence_store_corrupt"
    assert database.read_bytes() == b""
    assert object_path.read_bytes() == original_bytes


def test_missing_index_with_raw_objects_is_not_recreated(
    tmp_path: Path,
    evidence_source_json: dict[str, Any],
    evidence_scope: EvidenceScope,
    evidence_metadata: EvidenceMetadata,
) -> None:
    source = _write_source(tmp_path / "source.json", evidence_source_json)
    workspace = tmp_path / "workspace"
    record = _store(source, workspace, evidence_scope, evidence_metadata)
    object_path = _object_path(workspace, record.raw_sha256)
    original_bytes = object_path.read_bytes()
    database = workspace / "contextsafe.sqlite"
    database.unlink()

    with pytest.raises(ContextSafeError) as raised:
        EvidenceStore(workspace).list_records()
    assert raised.value.code == "evidence_index_missing"
    with pytest.raises(ContextSafeError) as raised:
        _store(source, workspace, evidence_scope, evidence_metadata)
    assert raised.value.code == "evidence_index_missing"
    assert not database.exists()
    assert object_path.read_bytes() == original_bytes


@pytest.mark.parametrize(
    "partial_kind",
    ["raw-object-without-staging", "staged-object", "unexpected-raw-entry"],
)
def test_preexisting_partial_raw_store_fails_without_any_workspace_mutation(
    tmp_path: Path,
    evidence_source_json: dict[str, Any],
    evidence_scope: EvidenceScope,
    evidence_metadata: EvidenceMetadata,
    partial_kind: str,
) -> None:
    source = _write_source(tmp_path / "source.json", evidence_source_json)
    workspace = tmp_path / "workspace"
    evidence = workspace / "evidence"
    raw = evidence / "raw"
    for directory in (workspace, evidence, raw):
        directory.mkdir(mode=0o700)
    if partial_kind == "unexpected-raw-entry":
        partial = raw / "unindexed.part"
    else:
        raw_root = raw / "sha256"
        raw_root.mkdir(mode=0o700)
        if partial_kind == "raw-object-without-staging":
            shard = raw_root / "aa"
            shard.mkdir(mode=0o700)
            partial = shard / ("a" * 64)
        else:
            staging = raw_root / ".staging"
            staging.mkdir(mode=0o700)
            partial = staging / "unindexed.part"
    partial.write_bytes(b"unindexed")
    os.chmod(partial, 0o600)
    before = _tree_snapshot(workspace)

    with pytest.raises(ContextSafeError) as raised:
        _store(source, workspace, evidence_scope, evidence_metadata)

    assert raised.value.code == "evidence_index_missing"
    assert _tree_snapshot(workspace) == before
    assert not (workspace / "contextsafe.sqlite").exists()


@pytest.mark.parametrize(
    "pragma",
    [
        "PRAGMA application_id = 0",
        "PRAGMA user_version = 2",
        "PRAGMA journal_mode = WAL",
    ],
)
def test_index_header_drift_fails_closed(
    tmp_path: Path,
    evidence_source_json: dict[str, Any],
    evidence_scope: EvidenceScope,
    evidence_metadata: EvidenceMetadata,
    pragma: str,
) -> None:
    source = _write_source(tmp_path / "source.json", evidence_source_json)
    workspace = tmp_path / "workspace"
    _store(source, workspace, evidence_scope, evidence_metadata)
    connection = sqlite3.connect(workspace / "contextsafe.sqlite")
    try:
        connection.execute(pragma)
    finally:
        connection.close()
    with pytest.raises(ContextSafeError) as raised:
        EvidenceStore(workspace).list_records()
    assert raised.value.code == "evidence_store_corrupt"


def test_empty_index_has_no_autoincrement_authority_row(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    store = EvidenceStore(workspace)
    store._ensure_store()

    assert store.list_records() == ()
    assert _sqlite_sequence_rows(workspace / "contextsafe.sqlite") == ()


@pytest.mark.parametrize(
    ("damage_sql", "damaged_rows"),
    [
        (
            "DELETE FROM sqlite_sequence WHERE name = 'evidence_records'",
            (),
        ),
        (
            "UPDATE sqlite_sequence SET seq = 0 WHERE name = 'evidence_records'",
            (("evidence_records", 0),),
        ),
        (
            "UPDATE sqlite_sequence SET seq = 2 WHERE name = 'evidence_records'",
            (("evidence_records", 2),),
        ),
        (
            "INSERT INTO sqlite_sequence(name, seq) VALUES ('unexpected', 1)",
            (("evidence_records", 1), ("unexpected", 1)),
        ),
    ],
)
def test_sqlite_sequence_drift_fails_reads_and_writes_without_repair_or_leaks(
    tmp_path: Path,
    evidence_source_json: dict[str, Any],
    evidence_scope: EvidenceScope,
    evidence_metadata: EvidenceMetadata,
    damage_sql: str,
    damaged_rows: tuple[tuple[object, object], ...],
) -> None:
    source = _write_source(tmp_path / "source.json", evidence_source_json)
    workspace = tmp_path / "workspace"
    first = _store(source, workspace, evidence_scope, evidence_metadata)
    database = workspace / "contextsafe.sqlite"
    connection = sqlite3.connect(database)
    try:
        connection.execute(damage_sql)
        connection.commit()
    finally:
        connection.close()
    raw_root = workspace / "evidence" / "raw" / "sha256"
    objects_before = {
        path.relative_to(raw_root) for path in raw_root.glob("*/*") if path.is_file()
    }

    with pytest.raises(ContextSafeError) as raised:
        EvidenceStore(workspace).list_records()
    assert raised.value.code == "evidence_store_corrupt"

    later = replace(
        evidence_metadata,
        captured_at=evidence_metadata.captured_at.replace(second=3),
    )
    with pytest.raises(ContextSafeError) as raised:
        _store(source, workspace, evidence_scope, later)
    assert raised.value.code == "evidence_store_corrupt"

    assert _sqlite_sequence_rows(database) == damaged_rows
    connection = sqlite3.connect(database)
    try:
        assert connection.execute(
            "SELECT sequence, evidence_id FROM evidence_records"
        ).fetchall() == [(1, first.evidence_id)]
    finally:
        connection.close()
    assert {
        path.relative_to(raw_root) for path in raw_root.glob("*/*") if path.is_file()
    } == objects_before
    assert not list((raw_root / ".staging").iterdir())


@pytest.mark.parametrize(
    ("column", "replacement"),
    [
        ("sequence", 7),
        ("evidence_id", "EVD-" + "f" * 64),
        ("raw_sha256", "f" * 64),
        ("record_json", None),
    ],
)
def test_integrity_verification_checks_every_index_column(
    tmp_path: Path,
    evidence_source_json: dict[str, Any],
    evidence_scope: EvidenceScope,
    evidence_metadata: EvidenceMetadata,
    column: str,
    replacement: object,
) -> None:
    source = _write_source(tmp_path / "source.json", evidence_source_json)
    workspace = tmp_path / "workspace"
    record = _store(source, workspace, evidence_scope, evidence_metadata)
    database = workspace / "contextsafe.sqlite"
    connection = sqlite3.connect(database)
    try:
        trigger_sql = connection.execute(
            "SELECT sql FROM sqlite_master "
            "WHERE type = 'trigger' AND name = 'evidence_records_no_update'"
        ).fetchone()
        assert trigger_sql is not None and isinstance(trigger_sql[0], str)
        connection.execute("DROP TRIGGER evidence_records_no_update")
        if column == "record_json":
            stored = connection.execute(
                "SELECT record_json FROM evidence_records WHERE evidence_id = ?",
                (record.evidence_id,),
            ).fetchone()
            assert stored is not None and isinstance(stored[0], str)
            replacement = f" {stored[0]}"
        update_sql = {
            "sequence": "UPDATE evidence_records SET sequence = ? WHERE sequence = 1",
            "evidence_id": (
                "UPDATE evidence_records SET evidence_id = ? WHERE sequence = 1"
            ),
            "raw_sha256": (
                "UPDATE evidence_records SET raw_sha256 = ? WHERE sequence = 1"
            ),
            "record_json": (
                "UPDATE evidence_records SET record_json = ? WHERE sequence = 1"
            ),
        }[column]
        connection.execute(update_sql, (replacement,))
        connection.execute(trigger_sql[0])
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(ContextSafeError) as raised:
        EvidenceStore(workspace).verify_integrity()
    assert raised.value.code == "evidence_store_corrupt"


def test_read_apis_do_not_modify_the_database_or_workspace_shape(
    tmp_path: Path,
    evidence_source_json: dict[str, Any],
    evidence_scope: EvidenceScope,
    evidence_metadata: EvidenceMetadata,
) -> None:
    source = _write_source(tmp_path / "source.json", evidence_source_json)
    workspace = tmp_path / "workspace"
    record = _store(source, workspace, evidence_scope, evidence_metadata)
    database = workspace / "contextsafe.sqlite"
    before = database.stat()
    entries_before = {path.relative_to(workspace) for path in workspace.rglob("*")}

    store = EvidenceStore(workspace)
    assert store.get(record.evidence_id) == record
    assert store.list_records() == (record,)
    store.verify_integrity()

    after = database.stat()
    assert (after.st_size, after.st_mtime_ns, after.st_ctime_ns) == (
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    assert {path.relative_to(workspace) for path in workspace.rglob("*")} == (
        entries_before
    )


def test_open_primary_error_survives_connection_close_failure(
    tmp_path: Path,
    evidence_source_json: dict[str, Any],
    evidence_scope: EvidenceScope,
    evidence_metadata: EvidenceMetadata,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _write_source(tmp_path / "source.json", evidence_source_json)
    workspace = tmp_path / "workspace"
    _store(source, workspace, evidence_scope, evidence_metadata)
    original_connect = sqlite3.connect

    def close_failing_connect(*args: object, **kwargs: object) -> Any:
        return _CloseFailingConnection(
            original_connect(*args, **kwargs),
            fail_statement="PRAGMA trusted_schema",
        )

    monkeypatch.setattr(store_module.sqlite3, "connect", close_failing_connect)
    with pytest.raises(ContextSafeError) as raised:
        EvidenceStore(workspace)._connect(read_only=True)

    assert raised.value.code == "evidence_store_io_error"
    assert isinstance(raised.value.__cause__, sqlite3.OperationalError)
    assert str(raised.value.__cause__) == "injected connection operation failure"


def test_read_primary_error_survives_connection_close_failure(
    tmp_path: Path,
    evidence_source_json: dict[str, Any],
    evidence_scope: EvidenceScope,
    evidence_metadata: EvidenceMetadata,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _write_source(tmp_path / "source.json", evidence_source_json)
    workspace = tmp_path / "workspace"
    _store(source, workspace, evidence_scope, evidence_metadata)
    original_connect = sqlite3.connect

    def close_failing_connect(*args: object, **kwargs: object) -> Any:
        return _CloseFailingConnection(original_connect(*args, **kwargs))

    def fail_read(_self: EvidenceStore, _connection: sqlite3.Connection) -> NoReturn:
        raise ContextSafeError("injected_read_failure", "$", "injected failure")

    monkeypatch.setattr(store_module.sqlite3, "connect", close_failing_connect)
    monkeypatch.setattr(EvidenceStore, "_validate_index", fail_read)
    with pytest.raises(ContextSafeError) as raised:
        EvidenceStore(workspace).list_records()

    assert raised.value.code == "injected_read_failure"


def test_successful_read_close_failure_is_structured_cleanup_error(
    tmp_path: Path,
    evidence_source_json: dict[str, Any],
    evidence_scope: EvidenceScope,
    evidence_metadata: EvidenceMetadata,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _write_source(tmp_path / "source.json", evidence_source_json)
    workspace = tmp_path / "workspace"
    _store(source, workspace, evidence_scope, evidence_metadata)
    original_connect = sqlite3.connect

    def close_failing_connect(*args: object, **kwargs: object) -> Any:
        return _CloseFailingConnection(original_connect(*args, **kwargs))

    monkeypatch.setattr(store_module.sqlite3, "connect", close_failing_connect)
    with pytest.raises(ContextSafeError) as raised:
        EvidenceStore(workspace).list_records()

    assert raised.value.code == "evidence_store_io_error"
    assert raised.value.message == "evidence index read connection cleanup failed"
    assert isinstance(raised.value.__cause__, sqlite3.OperationalError)
    assert str(raised.value.__cause__) == "injected connection close failure"


def test_invalid_factory_scope_fails_before_workspace_creation(
    tmp_path: Path,
    evidence_source_json: dict[str, Any],
    evidence_scope: EvidenceScope,
    evidence_metadata: EvidenceMetadata,
) -> None:
    source = _write_source(tmp_path / "source.json", evidence_source_json)
    workspace = tmp_path / "workspace"
    invalid_scope = replace(evidence_scope, case_id="CTP-Z99")
    with pytest.raises(ContextSafeError) as raised:
        _store(source, workspace, invalid_scope, evidence_metadata)
    assert raised.value.code == "case_scope_mismatch"
    assert not workspace.exists()


@pytest.mark.parametrize("unsafe_kind", ["stage-directory", "bad-shard", "bad-object"])
def test_recovery_rejects_unsafe_filesystem_entries(
    tmp_path: Path,
    evidence_source_json: dict[str, Any],
    evidence_scope: EvidenceScope,
    evidence_metadata: EvidenceMetadata,
    unsafe_kind: str,
) -> None:
    source = _write_source(tmp_path / "source.json", evidence_source_json)
    workspace = tmp_path / "workspace"
    _store(source, workspace, evidence_scope, evidence_metadata)
    raw_root = workspace / "evidence" / "raw" / "sha256"
    if unsafe_kind == "stage-directory":
        (raw_root / ".staging" / "unsafe").mkdir()
    elif unsafe_kind == "bad-shard":
        (raw_root / "zz").mkdir(mode=0o700)
    else:
        shard = raw_root / "aa"
        shard.mkdir(mode=0o700)
        (shard / "not-a-hash").write_bytes(b"unsafe")
    with pytest.raises(ContextSafeError) as raised:
        _store(source, workspace, evidence_scope, evidence_metadata)
    assert raised.value.code == "evidence_store_corrupt"


def test_missing_referenced_object_is_detected_before_new_append(
    tmp_path: Path,
    evidence_source_json: dict[str, Any],
    evidence_scope: EvidenceScope,
    evidence_metadata: EvidenceMetadata,
) -> None:
    source = _write_source(tmp_path / "source.json", evidence_source_json)
    workspace = tmp_path / "workspace"
    record = _store(source, workspace, evidence_scope, evidence_metadata)
    _object_path(workspace, record.raw_sha256).unlink()
    with pytest.raises(ContextSafeError) as raised:
        _store(source, workspace, evidence_scope, evidence_metadata)
    assert raised.value.code == "evidence_store_corrupt"


def test_record_bound_collision_and_payload_parser_guards(
    tmp_path: Path,
    evidence_source_json: dict[str, Any],
    evidence_scope: EvidenceScope,
    evidence_metadata: EvidenceMetadata,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _write_source(tmp_path / "source.json", evidence_source_json)
    workspace = tmp_path / "workspace"
    record = _store(source, workspace, evidence_scope, evidence_metadata)
    connection = sqlite3.connect(workspace / "contextsafe.sqlite", isolation_level=None)
    try:
        connection.execute("BEGIN IMMEDIATE")
        with pytest.raises(ContextSafeError) as raised:
            EvidenceStore._append_record(
                connection, replace(record, system_version="different")
            )
        assert raised.value.code == "evidence_id_collision"
        connection.execute("ROLLBACK")
    finally:
        connection.close()

    later = replace(
        evidence_metadata,
        captured_at=evidence_metadata.captured_at.replace(second=2),
    )
    monkeypatch.setattr(store_module, "MAX_EVIDENCE_RECORDS", 1)
    with pytest.raises(ContextSafeError) as raised:
        _store(source, workspace, evidence_scope, later)
    assert raised.value.code == "evidence_count_exceeded"
    assert EvidenceStore(workspace).list_records() == (record,)

    with pytest.raises(ContextSafeError) as raised:
        EvidenceStore._record_from_json(1)
    assert raised.value.code == "evidence_store_corrupt"
    with pytest.raises(ContextSafeError) as raised:
        EvidenceStore._record_from_json("not-json")
    assert raised.value.code == "evidence_store_corrupt"


def test_stage_name_exhaustion_and_generic_sqlite_failure_are_safe(
    tmp_path: Path,
    evidence_source_json: dict[str, Any],
    evidence_scope: EvidenceScope,
    evidence_metadata: EvidenceMetadata,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _write_source(tmp_path / "source.json", evidence_source_json)
    workspace = tmp_path / "workspace"
    store = EvidenceStore(workspace)
    store._initialize_directories()
    collision = store.staging_root / ("0" * 32 + ".part")
    collision.write_bytes(b"")
    monkeypatch.setattr(store_module.secrets, "token_hex", lambda _size: "0" * 32)
    with pytest.raises(ContextSafeError) as raised:
        store._create_stage_path()
    assert raised.value.code == "evidence_store_io_error"
    collision.unlink()

    def fail(_connection: sqlite3.Connection, _record: object) -> None:
        raise sqlite3.OperationalError("injected")

    monkeypatch.setattr(EvidenceStore, "_append_record", staticmethod(fail))
    with pytest.raises(ContextSafeError) as raised:
        _store(source, workspace, evidence_scope, evidence_metadata)
    assert raised.value.code == "evidence_store_io_error"
    assert EvidenceStore(workspace).list_records() == ()


def test_new_index_primary_error_survives_temporary_cleanup_denial(
    tmp_path: Path,
    evidence_source_json: dict[str, Any],
    evidence_scope: EvidenceScope,
    evidence_metadata: EvidenceMetadata,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _write_source(tmp_path / "source.json", evidence_source_json)
    workspace = tmp_path / "workspace"
    original_unlink = Path.unlink

    def fail_validation(
        _self: EvidenceStore, _connection: sqlite3.Connection
    ) -> NoReturn:
        raise ContextSafeError("injected_index_failure", "$", "injected failure")

    def deny_init_unlink(path: Path, *args: object, **kwargs: object) -> None:
        if path.suffix == ".init":
            raise PermissionError("injected temporary cleanup denial")
        original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(EvidenceStore, "_validate_index", fail_validation)
    monkeypatch.setattr(Path, "unlink", deny_init_unlink)

    with pytest.raises(ContextSafeError) as raised:
        _store(source, workspace, evidence_scope, evidence_metadata)

    assert raised.value.code == "injected_index_failure"
    assert not (workspace / "contextsafe.sqlite").exists()
    assert len(list(workspace.glob(".contextsafe.sqlite.*.init"))) == 1
    raw_root = workspace / "evidence" / "raw" / "sha256"
    assert not list((raw_root / ".staging").iterdir())
    assert not [
        path
        for path in raw_root.glob("*/*")
        if path.is_file() and path.parent != raw_root / ".staging"
    ]


def test_new_index_cleanup_denial_without_primary_is_structured_and_leaves_no_row(
    tmp_path: Path,
    evidence_source_json: dict[str, Any],
    evidence_scope: EvidenceScope,
    evidence_metadata: EvidenceMetadata,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _write_source(tmp_path / "source.json", evidence_source_json)
    workspace = tmp_path / "workspace"
    original_unlink = Path.unlink

    def deny_init_unlink(path: Path, *args: object, **kwargs: object) -> None:
        if path.suffix == ".init":
            raise PermissionError("injected temporary cleanup denial")
        original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", deny_init_unlink)
    with pytest.raises(ContextSafeError) as raised:
        _store(source, workspace, evidence_scope, evidence_metadata)

    assert raised.value.code == "evidence_store_io_error"
    database = workspace / "contextsafe.sqlite"
    assert database.exists()
    assert len(list(workspace.glob(".contextsafe.sqlite.*.init"))) == 1
    connection = sqlite3.connect(database)
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM evidence_records"
        ).fetchone() == (0,)
    finally:
        connection.close()
    raw_root = workspace / "evidence" / "raw" / "sha256"
    assert not list((raw_root / ".staging").iterdir())
    assert not [
        path
        for path in raw_root.glob("*/*")
        if path.is_file() and path.parent != raw_root / ".staging"
    ]


def test_new_index_final_sidecar_cleanup_denial_is_structured(
    tmp_path: Path,
    evidence_source_json: dict[str, Any],
    evidence_scope: EvidenceScope,
    evidence_metadata: EvidenceMetadata,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _write_source(tmp_path / "source.json", evidence_source_json)
    workspace = tmp_path / "workspace"
    original_unlink = Path.unlink

    def deny_journal_cleanup(path: Path, *args: object, **kwargs: object) -> None:
        if str(path).endswith("-journal"):
            raise PermissionError("injected sidecar cleanup denial")
        original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", deny_journal_cleanup)
    with pytest.raises(ContextSafeError) as raised:
        _store(source, workspace, evidence_scope, evidence_metadata)

    assert raised.value.code == "evidence_store_io_error"
    database = workspace / "contextsafe.sqlite"
    assert database.exists()
    connection = sqlite3.connect(database)
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM evidence_records"
        ).fetchone() == (0,)
    finally:
        connection.close()


def test_new_index_publish_os_error_is_structured_and_cleans_temporary_file(
    tmp_path: Path,
    evidence_source_json: dict[str, Any],
    evidence_scope: EvidenceScope,
    evidence_metadata: EvidenceMetadata,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _write_source(tmp_path / "source.json", evidence_source_json)
    workspace = tmp_path / "workspace"
    original_link = os.link

    def deny_database_link(
        source_path: os.PathLike[str] | str,
        destination_path: os.PathLike[str] | str,
        *,
        src_dir_fd: int | None = None,
        dst_dir_fd: int | None = None,
        follow_symlinks: bool = True,
    ) -> None:
        if Path(destination_path) == workspace / "contextsafe.sqlite":
            raise PermissionError("injected database publish denial")
        original_link(
            source_path,
            destination_path,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
            follow_symlinks=follow_symlinks,
        )

    monkeypatch.setattr(os, "link", deny_database_link)
    with pytest.raises(ContextSafeError) as raised:
        _store(source, workspace, evidence_scope, evidence_metadata)

    assert raised.value.code == "evidence_store_io_error"
    assert not (workspace / "contextsafe.sqlite").exists()
    assert not list(workspace.glob(".contextsafe.sqlite.*.init*"))


def test_same_size_hash_corruption_and_missing_object_are_distinctly_detected(
    tmp_path: Path,
    evidence_source_json: dict[str, Any],
    evidence_scope: EvidenceScope,
    evidence_metadata: EvidenceMetadata,
) -> None:
    source = _write_source(tmp_path / "source.json", evidence_source_json)
    workspace = tmp_path / "workspace"
    record = _store(source, workspace, evidence_scope, evidence_metadata)
    object_path = _object_path(workspace, record.raw_sha256)
    object_path.write_bytes(b"x" * record.raw_byte_count)
    with pytest.raises(ContextSafeError) as raised:
        EvidenceStore(workspace).verify_integrity()
    assert raised.value.code == "evidence_store_corrupt"

    object_path.unlink()
    with pytest.raises(ContextSafeError) as raised:
        EvidenceStore._verify_object(
            object_path, record.raw_sha256, record.raw_byte_count
        )
    assert raised.value.code == "evidence_store_corrupt"


def test_permissions_are_rechecked_when_reading_existing_store(
    tmp_path: Path,
    evidence_source_json: dict[str, Any],
    evidence_scope: EvidenceScope,
    evidence_metadata: EvidenceMetadata,
) -> None:
    source = _write_source(tmp_path / "source.json", evidence_source_json)
    workspace = tmp_path / "workspace"
    record = _store(source, workspace, evidence_scope, evidence_metadata)
    os.chmod(workspace, 0o755)  # noqa: S103 - intentionally unsafe fixture
    with pytest.raises(ContextSafeError) as raised:
        EvidenceStore(workspace).list_records()
    assert raised.value.code == "workspace_permission_unsafe"

    os.chmod(workspace, 0o700)
    object_path = _object_path(workspace, record.raw_sha256)
    os.chmod(object_path, 0o644)
    with pytest.raises(ContextSafeError) as raised:
        EvidenceStore(workspace).verify_integrity()
    assert raised.value.code == "evidence_store_corrupt"


def test_mutation_path_directories_fsync_each_parent_on_repeated_attempts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    store = EvidenceStore(workspace)
    fsync_calls: list[Path] = []
    monkeypatch.setattr(
        EvidenceStore,
        "_fsync_directory",
        staticmethod(fsync_calls.append),
    )

    expected = [
        tmp_path,
        workspace,
        workspace / "evidence",
        workspace / "evidence" / "raw",
        store.raw_root,
    ]
    store._initialize_directories()
    assert fsync_calls == expected

    store._initialize_directories()
    assert fsync_calls == expected * 2


def test_concurrent_directory_initializers_both_sync_the_parent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    stores = (EvidenceStore(workspace), EvidenceStore(workspace))
    barrier = Barrier(2)
    fsync_calls: list[Path] = []

    def initialize(store: EvidenceStore) -> None:
        barrier.wait()
        store._ensure_private_directory(workspace)

    monkeypatch.setattr(
        EvidenceStore,
        "_fsync_directory",
        staticmethod(fsync_calls.append),
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        tuple(executor.map(initialize, stores))

    assert workspace.is_dir()
    assert fsync_calls == [tmp_path, tmp_path]


def test_shard_parent_fsync_precedes_staging_creation(
    tmp_path: Path,
    evidence_source_json: dict[str, Any],
    evidence_scope: EvidenceScope,
    evidence_metadata: EvidenceMetadata,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _write_source(tmp_path / "source.json", evidence_source_json)
    workspace = tmp_path / "workspace"
    store = EvidenceStore(workspace)
    store._ensure_store()
    events: list[tuple[str, Path]] = []
    original_create_stage_path = EvidenceStore._create_stage_path

    def record_fsync(path: Path) -> None:
        events.append(("fsync", path))

    def record_stage(self: EvidenceStore) -> Path:
        events.append(("stage", self.staging_root))
        return original_create_stage_path(self)

    monkeypatch.setattr(EvidenceStore, "_fsync_directory", staticmethod(record_fsync))
    monkeypatch.setattr(EvidenceStore, "_create_stage_path", record_stage)

    _store(source, workspace, evidence_scope, evidence_metadata)

    raw_fsync = events.index(("fsync", store.raw_root))
    stage_creation = events.index(("stage", store.staging_root))
    assert raw_fsync < stage_creation


def test_shard_parent_fsync_failure_is_retried_before_consistent_commit(
    tmp_path: Path,
    evidence_source_json: dict[str, Any],
    evidence_scope: EvidenceScope,
    evidence_metadata: EvidenceMetadata,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _write_source(tmp_path / "source.json", evidence_source_json)
    workspace = tmp_path / "workspace"
    store = EvidenceStore(workspace)
    store._ensure_store()
    original_fsync = EvidenceStore._fsync_directory
    raw_root_attempts = 0

    def fail_raw_root_fsync_once(path: Path) -> None:
        nonlocal raw_root_attempts
        if path == store.raw_root:
            raw_root_attempts += 1
            if raw_root_attempts == 1:
                raise PermissionError("injected directory fsync denial")
        original_fsync(path)

    # This is syscall fault injection, not a claim of power-loss proof.
    monkeypatch.setattr(
        EvidenceStore,
        "_fsync_directory",
        staticmethod(fail_raw_root_fsync_once),
    )
    with pytest.raises(ContextSafeError) as raised:
        _store(source, workspace, evidence_scope, evidence_metadata)

    assert raised.value.code == "evidence_store_io_error"
    assert not list(store.staging_root.iterdir())
    shards = [
        entry for entry in store.raw_root.iterdir() if entry != store.staging_root
    ]
    assert len(shards) == 1
    assert shards[0].is_dir()
    assert not list(shards[0].iterdir())
    connection = sqlite3.connect(store.database_path)
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM evidence_records"
        ).fetchone() == (0,)
    finally:
        connection.close()
    assert _sqlite_sequence_rows(store.database_path) == ()

    record = _store(source, workspace, evidence_scope, evidence_metadata)

    assert raw_root_attempts == 2
    assert EvidenceStore(workspace).list_records() == (record,)
    assert _sqlite_sequence_rows(store.database_path) == (("evidence_records", 1),)
    assert (
        _object_path(workspace, record.raw_sha256).read_bytes() == source.read_bytes()
    )
    assert not list(store.staging_root.iterdir())


def test_index_parent_fsync_failure_is_retried_before_consistent_commit(
    tmp_path: Path,
    evidence_source_json: dict[str, Any],
    evidence_scope: EvidenceScope,
    evidence_metadata: EvidenceMetadata,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _write_source(tmp_path / "source.json", evidence_source_json)
    workspace = tmp_path / "workspace"
    store = EvidenceStore(workspace)
    original_fsync = EvidenceStore._fsync_directory
    original_stage = EvidenceStore._create_stage_path
    denied = False
    events: list[str] = []

    def fail_visible_index_parent_once(path: Path) -> None:
        nonlocal denied
        if path == workspace and store.database_path.exists():
            if not denied:
                denied = True
                events.append("index-parent-fsync-denied")
                raise PermissionError("injected index parent fsync denial")
            events.append("index-parent-fsync-retried")
        original_fsync(path)

    def record_stage(self: EvidenceStore) -> Path:
        events.append("stage-created")
        return original_stage(self)

    monkeypatch.setattr(
        EvidenceStore,
        "_fsync_directory",
        staticmethod(fail_visible_index_parent_once),
    )
    monkeypatch.setattr(EvidenceStore, "_create_stage_path", record_stage)

    with pytest.raises(ContextSafeError) as raised:
        _store(source, workspace, evidence_scope, evidence_metadata)
    assert raised.value.code == "evidence_store_io_error"
    assert store.database_path.exists()
    assert store.list_records() == ()
    assert events == ["index-parent-fsync-denied"]

    record = _store(source, workspace, evidence_scope, evidence_metadata)
    assert events.index("index-parent-fsync-retried") < events.index("stage-created")
    assert store.list_records() == (record,)
    assert _sqlite_sequence_rows(store.database_path) == (("evidence_records", 1),)
    assert not list(store.staging_root.iterdir())
    assert _object_path(workspace, record.raw_sha256).is_file()


def test_directory_fsync_open_error_is_structured(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_open = os.open

    def deny_directory_open(
        path: os.PathLike[str] | str,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        if Path(path) == tmp_path:
            raise PermissionError("injected directory open denial")
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(os, "open", deny_directory_open)
    with pytest.raises(ContextSafeError) as raised:
        EvidenceStore._fsync_directory(tmp_path)
    assert raised.value.code == "evidence_store_io_error"
