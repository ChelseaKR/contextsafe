"""Content-addressed evidence objects with an append-only SQLite index."""

import hashlib
import os
import secrets
import sqlite3
import stat
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path

from contextsafe.canonical import canonical_json
from contextsafe.errors import ContextSafeError
from contextsafe.evidence import (
    EvidenceMetadata,
    EvidenceRecord,
    EvidenceScope,
    build_evidence_record,
    parse_evidence_metadata,
    parse_evidence_record,
)
from contextsafe.jsonio import parse_json_bytes
from contextsafe.preflight import PreflightedSource, open_preflighted_source

INDEX_SCHEMA_VERSION = "contextsafe.evidence-index/1.0.0"
MAX_EVIDENCE_RECORDS = 2_000
_INDEX_APPLICATION_ID = 0x43545853  # "CTXS"
_INDEX_USER_VERSION = 1
_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_DIRECTORY = getattr(os, "O_DIRECTORY", 0)
_STAGING_FLAGS = os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NOFOLLOW | _CLOEXEC
_READ_FLAGS = os.O_RDONLY | _NOFOLLOW | _CLOEXEC
_OWNER_PERMISSIONS_SUPPORTED = os.name == "posix"

_METADATA_TABLE_SQL = """CREATE TABLE evidence_index_metadata (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    schema_version TEXT NOT NULL
)"""
_RECORDS_TABLE_SQL = """CREATE TABLE evidence_records (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    evidence_id TEXT NOT NULL UNIQUE,
    raw_sha256 TEXT NOT NULL,
    record_json TEXT NOT NULL UNIQUE
)"""
_RAW_HASH_INDEX_SQL = """CREATE INDEX evidence_records_raw_sha256
    ON evidence_records(raw_sha256)"""
_NO_UPDATE_TRIGGER_SQL = """CREATE TRIGGER evidence_records_no_update
BEFORE UPDATE ON evidence_records
BEGIN
    SELECT RAISE(ABORT, 'evidence records are append-only');
END"""
_NO_DELETE_TRIGGER_SQL = """CREATE TRIGGER evidence_records_no_delete
BEFORE DELETE ON evidence_records
BEGIN
    SELECT RAISE(ABORT, 'evidence records are append-only');
END"""
# SQLite rejects bound parameters inside a PRAGMA statement ("near \"?\": syntax
# error"), so the two header PRAGMAs that carry a value cannot be parameterized the
# way the INSERT below is. They are rendered once here instead, next to the constants
# they encode and alongside the other _*_SQL statements this module executes, so that
# the strings handed to `execute` are fixed module constants rather than text built at
# the call site. The `:d` conversion accepts only an int and can emit only digits and
# an optional sign, so neither statement can carry SQL syntax even if a future edit
# made the constants configurable. `_validate_index` reads both values back and
# rejects any file that does not carry them, and
# `test_pragma_header_sql_is_a_fixed_integer_assignment` pins the exact rendered text.
_SET_APPLICATION_ID_SQL = f"PRAGMA application_id = {_INDEX_APPLICATION_ID:d}"
_SET_USER_VERSION_SQL = f"PRAGMA user_version = {_INDEX_USER_VERSION:d}"

_SCHEMA_DEFINITIONS = (
    (
        "table",
        "evidence_index_metadata",
        "evidence_index_metadata",
        _METADATA_TABLE_SQL,
    ),
    ("table", "evidence_records", "evidence_records", _RECORDS_TABLE_SQL),
    ("index", "evidence_records_raw_sha256", "evidence_records", _RAW_HASH_INDEX_SQL),
    (
        "trigger",
        "evidence_records_no_update",
        "evidence_records",
        _NO_UPDATE_TRIGGER_SQL,
    ),
    (
        "trigger",
        "evidence_records_no_delete",
        "evidence_records",
        _NO_DELETE_TRIGGER_SQL,
    ),
)


@contextmanager
def _closing_descriptor(descriptor: int, *, code: str, message: str) -> Iterator[int]:
    """Close an fd without allowing cleanup failure to replace a primary error."""

    primary_error: BaseException | None = None
    try:
        yield descriptor
    except BaseException as exc:
        primary_error = exc
        raise
    finally:
        try:
            os.close(descriptor)
        except OSError as exc:
            if primary_error is None:
                raise ContextSafeError(code, "$", message) from exc


class EvidenceStore:
    """Low-level local store; authorization remains outside this iteration."""

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace
        self.database_path = workspace / "contextsafe.sqlite"
        self.raw_root = workspace / "evidence" / "raw" / "sha256"
        self.staging_root = self.raw_root / ".staging"

    def commit(
        self, source: PreflightedSource, metadata: EvidenceMetadata
    ) -> EvidenceRecord:
        """Copy a second validated pass and append its deterministic record."""

        validated_metadata = parse_evidence_metadata(metadata.to_dict())
        record = parse_evidence_record(
            build_evidence_record(source.result, validated_metadata).to_dict()
        )
        self._ensure_store()
        connection = self._connect(read_only=False)
        stage_path: Path | None = None
        final_path = self._object_path(record.raw_sha256)
        created_object = False
        commit_attempted = False
        primary_error: ContextSafeError | None = None
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._recover(connection)
            self._ensure_private_directory(final_path.parent)
            stage_path = self._create_stage_path()
            stage_descriptor = os.open(stage_path, _STAGING_FLAGS, 0o600)
            with _closing_descriptor(
                stage_descriptor,
                code="evidence_store_io_error",
                message="staging descriptor could not be closed",
            ):
                source.copy_to(stage_descriptor)
                os.fsync(stage_descriptor)
            try:
                os.link(stage_path, final_path, follow_symlinks=False)
                created_object = True
                self._fsync_directory(final_path.parent)
            except FileExistsError:
                created_object = False
            self._verify_object(final_path, record.raw_sha256, record.raw_byte_count)
            self._remove_path(
                stage_path,
                primary_error=None,
                message="staging object could not be removed",
            )
            stage_path = None
            self._append_record(connection, record)
            self._validate_index(connection)
            commit_attempted = True
            connection.execute("COMMIT")
            return record
        except ContextSafeError as exc:
            primary_error = exc
            self._rollback(connection)
            if created_object and not commit_attempted:
                self._remove_object(final_path, primary_error=primary_error)
            raise
        except (OSError, sqlite3.Error) as exc:
            primary_error = ContextSafeError(
                "evidence_store_io_error",
                "$",
                "evidence store transaction failed",
            )
            self._rollback(connection)
            if created_object and not commit_attempted:
                self._remove_object(final_path, primary_error=primary_error)
            raise primary_error from exc
        finally:
            self._finish_commit_cleanup(connection, stage_path, primary_error)

    def _finish_commit_cleanup(
        self,
        connection: sqlite3.Connection,
        stage_path: Path | None,
        primary_error: ContextSafeError | None,
    ) -> None:
        cleanup_error: ContextSafeError | None = None
        cleanup_cause: BaseException | None = None
        if stage_path is not None:
            try:
                self._remove_path(
                    stage_path,
                    primary_error=primary_error,
                    message="staging cleanup failed",
                )
            except ContextSafeError as exc:
                cleanup_error = exc
                cleanup_cause = exc.__cause__
        try:
            self._close_connection(
                connection,
                primary_error=primary_error or cleanup_error,
                message="evidence index connection cleanup failed",
            )
        except ContextSafeError as exc:
            cleanup_error = exc
            cleanup_cause = exc.__cause__
        if primary_error is None and cleanup_error is not None:
            raise cleanup_error from cleanup_cause

    @staticmethod
    def _close_connection(
        connection: sqlite3.Connection,
        *,
        primary_error: ContextSafeError | None,
        message: str,
    ) -> None:
        """Close SQLite without replacing a structured primary failure."""

        try:
            connection.close()
        except sqlite3.Error as exc:
            if primary_error is None:
                raise ContextSafeError("evidence_store_io_error", "$", message) from exc

    def get(self, evidence_id: str) -> EvidenceRecord | None:
        """Return one validated immutable index record without changing the store."""

        return next(
            (
                record
                for record in self._read_records(verify_objects=False)
                if record.evidence_id == evidence_id
            ),
            None,
        )

    def list_records(self) -> tuple[EvidenceRecord, ...]:
        """Return records in append sequence while validating each payload."""

        return self._read_records(verify_objects=False)

    def verify_integrity(self) -> None:
        """Fail closed if the index or any referenced content object is corrupt."""

        self._read_records(verify_objects=True)

    def _initialize_directories(self) -> None:
        current = self.workspace
        self._ensure_private_directory(current)
        for component in ("evidence", "raw", "sha256", ".staging"):
            current = current / component
            self._ensure_private_directory(current)

    def _ensure_private_directory(self, path: Path) -> None:
        try:
            path.mkdir(mode=0o700)
        except FileExistsError:
            pass
        except OSError as exc:
            raise ContextSafeError(
                "evidence_store_io_error", "$", "private directory could not be created"
            ) from exc
        self._validate_private_directory(path)
        self._fsync_directory(path.parent)

    @staticmethod
    def _validate_private_directory(path: Path) -> None:
        try:
            details = path.lstat()
        except OSError as exc:
            raise ContextSafeError(
                "evidence_store_io_error",
                "$",
                "private directory could not be inspected",
            ) from exc
        EvidenceStore._validate_private_directory_details(details)

    @staticmethod
    def _validate_private_directory_details(details: os.stat_result) -> None:
        if not stat.S_ISDIR(details.st_mode) or stat.S_ISLNK(details.st_mode):
            raise ContextSafeError(
                "evidence_store_path_unsafe",
                "$",
                "evidence store paths must be real directories",
            )
        if _OWNER_PERMISSIONS_SUPPORTED and stat.S_IMODE(details.st_mode) & 0o077:
            raise ContextSafeError(
                "workspace_permission_unsafe",
                "$",
                "evidence workspace must be owner-only",
            )

    def _ensure_store(self) -> None:
        """Publish a complete new index or validate an existing store without repair."""

        if self._database_file_exists():
            self._validate_existing_store_for_mutation()
            return
        self._classify_missing_index_state()
        if self._database_file_exists():
            self._validate_existing_store_for_mutation()
            return
        self._initialize_directories()
        if self._database_file_exists():
            self._validate_existing_store_for_mutation()
            return
        self._classify_missing_index_state()
        if self._database_file_exists():
            self._validate_existing_store_for_mutation()
            return
        self._publish_new_database()
        self._validate_database_file(missing_code="evidence_store_io_error")
        self._validate_existing_store_for_mutation()

    def _validate_existing_store_for_mutation(self) -> None:
        """Validate and durably acknowledge a visible index before writing through it."""

        self._validate_store_directories()
        self._fsync_directory(self.workspace)

    def _classify_missing_index_state(self) -> None:
        """Inspect a missing-index namespace without changing its filesystem shape."""

        try:
            workspace_details = self.workspace.lstat()
        except FileNotFoundError:
            return
        except OSError as exc:
            raise ContextSafeError(
                "evidence_store_io_error",
                "$",
                "unindexed evidence workspace could not be inspected",
            ) from exc
        self._validate_private_directory_details(workspace_details)
        hierarchy: tuple[tuple[Path, str | None], ...] = (
            (self.workspace / "evidence", "raw"),
            (self.workspace / "evidence" / "raw", "sha256"),
            (self.raw_root, ".staging"),
            (self.staging_root, None),
        )
        try:
            for directory, permitted_child in hierarchy:
                try:
                    details = directory.lstat()
                except FileNotFoundError:
                    return
                self._validate_private_directory_details(details)
                if any(
                    permitted_child is None or entry.name != permitted_child
                    for entry in directory.iterdir()
                ):
                    if self._database_file_exists():
                        return
                    raise ContextSafeError(
                        "evidence_index_missing",
                        "$",
                        "raw evidence exists without an authoritative index",
                    )
        except ContextSafeError:
            raise
        except OSError as exc:
            raise ContextSafeError(
                "evidence_store_io_error",
                "$",
                "unindexed evidence store could not be inspected",
            ) from exc

    def _database_file_exists(self) -> bool:
        try:
            details = self.database_path.lstat()
        except FileNotFoundError:
            return False
        except OSError as exc:
            raise ContextSafeError(
                "evidence_store_io_error",
                "$",
                "evidence index could not be inspected",
            ) from exc
        self._validate_database_details(details)
        return True

    def _validate_store_directories(self) -> None:
        for path in (
            self.workspace,
            self.workspace / "evidence",
            self.workspace / "evidence" / "raw",
            self.raw_root,
            self.staging_root,
        ):
            self._validate_private_directory(path)

    def _publish_new_database(self) -> None:
        temporary_path = (
            self.workspace / f".contextsafe.sqlite.{secrets.token_hex(16)}.init"
        )
        connection: sqlite3.Connection | None = None
        primary_error: ContextSafeError | None = None
        try:
            descriptor = os.open(temporary_path, _STAGING_FLAGS, 0o600)
            with _closing_descriptor(
                descriptor,
                code="evidence_store_io_error",
                message="temporary evidence index descriptor could not be closed",
            ):
                pass
            connection = sqlite3.connect(
                temporary_path,
                timeout=10,
                isolation_level=None,
            )
            connection.execute("PRAGMA busy_timeout = 10000")
            connection.execute("PRAGMA journal_mode = DELETE")
            connection.execute("PRAGMA synchronous = FULL")
            connection.execute("PRAGMA trusted_schema = OFF")
            connection.execute(_SET_APPLICATION_ID_SQL)
            connection.execute(_SET_USER_VERSION_SQL)
            connection.execute("BEGIN IMMEDIATE")
            for _kind, _name, _table, statement in _SCHEMA_DEFINITIONS:
                connection.execute(statement)
            connection.execute(
                "INSERT INTO evidence_index_metadata(singleton, schema_version) "
                "VALUES (1, ?)",
                (INDEX_SCHEMA_VERSION,),
            )
            connection.execute("COMMIT")
            connection.execute("BEGIN")
            self._validate_index(connection)
            connection.execute("ROLLBACK")
            self._close_connection(
                connection,
                primary_error=None,
                message="temporary evidence index connection cleanup failed",
            )
            connection = None

            descriptor = os.open(temporary_path, _READ_FLAGS)
            with _closing_descriptor(
                descriptor,
                code="evidence_store_io_error",
                message="temporary evidence index descriptor could not be closed",
            ):
                os.fsync(descriptor)
            with suppress(FileExistsError):
                os.link(temporary_path, self.database_path, follow_symlinks=False)
            self._remove_path(
                temporary_path,
                primary_error=None,
                message="temporary evidence index could not be removed",
            )
            self._fsync_directory(self.workspace)
        except ContextSafeError as exc:
            primary_error = exc
            raise
        except (OSError, sqlite3.Error) as exc:
            primary_error = ContextSafeError(
                "evidence_store_io_error", "$", "evidence index could not be created"
            )
            raise primary_error from exc
        finally:
            cleanup_error: ContextSafeError | None = None
            cleanup_cause: BaseException | None = None
            if connection is not None:
                self._rollback(connection)
                try:
                    self._close_connection(
                        connection,
                        primary_error=primary_error,
                        message=("temporary evidence index connection cleanup failed"),
                    )
                except ContextSafeError as exc:
                    cleanup_error = exc
                    cleanup_cause = exc.__cause__
            for suffix in ("", "-journal", "-wal", "-shm"):
                try:
                    self._remove_path(
                        Path(f"{temporary_path}{suffix}"),
                        primary_error=primary_error or cleanup_error,
                        message="temporary evidence index cleanup failed",
                    )
                except ContextSafeError as exc:
                    cleanup_error = exc
                    cleanup_cause = exc.__cause__
            if primary_error is None and cleanup_error is not None:
                raise cleanup_error from cleanup_cause

    def _connect(self, *, read_only: bool) -> sqlite3.Connection:
        self._validate_database_file(missing_code="evidence_index_missing")
        self._validate_store_directories()
        connection: sqlite3.Connection | None = None
        mode = "ro" if read_only else "rw"
        uri = f"{self.database_path.absolute().as_uri()}?mode={mode}"
        try:
            connection = sqlite3.connect(
                uri,
                uri=True,
                timeout=10,
                isolation_level=None,
            )
            connection.execute("PRAGMA busy_timeout = 10000")
            connection.execute("PRAGMA trusted_schema = OFF")
            if read_only:
                connection.execute("PRAGMA query_only = ON")
            else:
                connection.execute("PRAGMA synchronous = FULL")
            return connection
        except sqlite3.Error as exc:
            primary_error = ContextSafeError(
                "evidence_store_io_error", "$", "evidence index could not be opened"
            )
            if connection is not None:
                self._close_connection(
                    connection,
                    primary_error=primary_error,
                    message="evidence index open connection cleanup failed",
                )
            raise primary_error from exc

    def _validate_database_file(self, *, missing_code: str) -> None:
        try:
            details = self.database_path.lstat()
        except FileNotFoundError as exc:
            raise ContextSafeError(
                missing_code,
                "$",
                "evidence index does not exist",
            ) from exc
        except OSError as exc:
            raise ContextSafeError(
                "evidence_store_io_error",
                "$",
                "evidence index could not be inspected",
            ) from exc
        self._validate_database_details(details)

    @staticmethod
    def _validate_database_details(details: os.stat_result) -> None:
        if not stat.S_ISREG(details.st_mode) or stat.S_ISLNK(details.st_mode):
            raise ContextSafeError(
                "evidence_store_path_unsafe",
                "$",
                "evidence index must be a regular file",
            )
        if _OWNER_PERMISSIONS_SUPPORTED and stat.S_IMODE(details.st_mode) & 0o077:
            raise ContextSafeError(
                "workspace_permission_unsafe",
                "$",
                "evidence index must be owner-only",
            )

    def _read_records(self, *, verify_objects: bool) -> tuple[EvidenceRecord, ...]:
        connection = self._connect(read_only=True)
        primary_error: ContextSafeError | None = None
        try:
            connection.execute("BEGIN")
            records = self._validate_index(connection)
            if verify_objects:
                self._verify_referenced_objects(records)
            connection.execute("ROLLBACK")
            return records
        except ContextSafeError as exc:
            primary_error = exc
            self._rollback(connection)
            raise
        except sqlite3.Error as exc:
            primary_error = ContextSafeError(
                "evidence_store_io_error",
                "$",
                "evidence index could not be read",
            )
            self._rollback(connection)
            raise primary_error from exc
        finally:
            self._close_connection(
                connection,
                primary_error=primary_error,
                message="evidence index read connection cleanup failed",
            )

    @staticmethod
    def _normalized_schema_sql(value: object) -> str | None:
        if not isinstance(value, str):
            return None
        return " ".join(value.strip().removesuffix(";").split())

    def _validate_index(
        self, connection: sqlite3.Connection
    ) -> tuple[EvidenceRecord, ...]:
        """Validate one transaction-consistent authoritative index snapshot."""

        try:
            self._validate_schema_authority(connection)
            return self._validate_record_rows(connection)
        except ContextSafeError:
            raise
        except sqlite3.Error as exc:
            raise ContextSafeError(
                "evidence_store_corrupt", "$", "evidence index validation failed"
            ) from exc

    def _validate_schema_authority(self, connection: sqlite3.Connection) -> None:
        integrity_rows = connection.execute("PRAGMA integrity_check").fetchall()
        if integrity_rows != [("ok",)]:
            raise ContextSafeError(
                "evidence_store_corrupt", "$", "SQLite integrity check failed"
            )
        schema_rows = connection.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%'"
        ).fetchall()
        actual_schema = {
            (row[0], row[1], row[2], self._normalized_schema_sql(row[3]))
            for row in schema_rows
        }
        expected_schema = {
            (kind, name, table, self._normalized_schema_sql(statement))
            for kind, name, table, statement in _SCHEMA_DEFINITIONS
        }
        if actual_schema != expected_schema:
            raise ContextSafeError(
                "evidence_store_corrupt",
                "$",
                "evidence index schema objects do not match the supported schema",
            )
        header = (
            connection.execute("PRAGMA application_id").fetchone(),
            connection.execute("PRAGMA user_version").fetchone(),
            connection.execute("PRAGMA journal_mode").fetchone(),
        )
        if header != (
            (_INDEX_APPLICATION_ID,),
            (_INDEX_USER_VERSION,),
            ("delete",),
        ):
            raise ContextSafeError(
                "evidence_store_corrupt",
                "$",
                "evidence index header does not match the supported store",
            )
        metadata_rows = connection.execute(
            "SELECT singleton, schema_version FROM evidence_index_metadata"
        ).fetchall()
        if len(metadata_rows) != 1 or metadata_rows[0][0] != 1:
            raise ContextSafeError(
                "evidence_store_corrupt",
                "$",
                "evidence index metadata is incomplete",
            )
        if metadata_rows[0][1] != INDEX_SCHEMA_VERSION:
            raise ContextSafeError(
                "unsupported_evidence_index",
                "$",
                "evidence index schema is unsupported",
            )

    def _validate_record_rows(
        self, connection: sqlite3.Connection
    ) -> tuple[EvidenceRecord, ...]:
        rows = connection.execute(
            "SELECT sequence, evidence_id, raw_sha256, record_json "
            "FROM evidence_records ORDER BY sequence"
        ).fetchall()
        if len(rows) > MAX_EVIDENCE_RECORDS:
            raise ContextSafeError(
                "evidence_store_corrupt",
                "$",
                "evidence index exceeds the supported record bound",
            )
        records: list[EvidenceRecord] = []
        for row in rows:
            sequence, evidence_id, raw_sha256, record_json = row
            if (
                isinstance(sequence, bool)
                or not isinstance(sequence, int)
                or sequence != len(records) + 1
            ):
                raise ContextSafeError(
                    "evidence_store_corrupt", "$", "evidence index sequence is invalid"
                )
            record = self._record_from_json(record_json)
            if (
                evidence_id != record.evidence_id
                or raw_sha256 != record.raw_sha256
                or record_json != canonical_json(record.to_dict())
            ):
                raise ContextSafeError(
                    "evidence_store_corrupt",
                    "$",
                    "evidence index columns do not match canonical records",
                )
            records.append(record)
        self._validate_sequence_authority(
            connection,
            maximum_sequence=rows[-1][0] if rows else None,
        )
        return tuple(records)

    @staticmethod
    def _validate_sequence_authority(
        connection: sqlite3.Connection, *, maximum_sequence: int | None
    ) -> None:
        sequence_rows = connection.execute(
            "SELECT name, seq FROM sqlite_sequence ORDER BY name"
        ).fetchall()
        expected_rows = (
            [] if maximum_sequence is None else [("evidence_records", maximum_sequence)]
        )
        if sequence_rows != expected_rows:
            raise ContextSafeError(
                "evidence_store_corrupt",
                "$",
                "evidence index sequence authority is invalid",
            )

    def _recover(self, connection: sqlite3.Connection) -> None:
        records = self._validate_index(connection)
        referenced = {record.raw_sha256 for record in records}
        try:
            self._verify_referenced_objects(records)
            self._recover_staging()
            self._recover_objects(referenced)
        except ContextSafeError:
            raise
        except OSError as exc:
            raise ContextSafeError(
                "evidence_store_io_error", "$", "evidence recovery failed"
            ) from exc

    def _verify_referenced_objects(self, records: tuple[EvidenceRecord, ...]) -> None:
        for record in records:
            self._verify_object(
                self._object_path(record.raw_sha256),
                record.raw_sha256,
                record.raw_byte_count,
            )

    def _recover_staging(self) -> None:
        for entry in self.staging_root.iterdir():
            details = entry.lstat()
            if not stat.S_ISREG(details.st_mode) or stat.S_ISLNK(details.st_mode):
                raise ContextSafeError(
                    "evidence_store_corrupt",
                    "$",
                    "staging area contains an unsafe entry",
                )
            entry.unlink()

    def _recover_objects(self, referenced: set[str]) -> None:
        for shard in self.raw_root.iterdir():
            if shard.name == ".staging":
                continue
            details = shard.lstat()
            if (
                not stat.S_ISDIR(details.st_mode)
                or stat.S_ISLNK(details.st_mode)
                or not re_full_hex(shard.name, 2)
                or (
                    _OWNER_PERMISSIONS_SUPPORTED
                    and bool(stat.S_IMODE(details.st_mode) & 0o077)
                )
            ):
                raise ContextSafeError(
                    "evidence_store_corrupt",
                    "$",
                    "raw object store contains an unsafe entry",
                )
            self._recover_shard(shard, referenced)

    @staticmethod
    def _recover_shard(shard: Path, referenced: set[str]) -> None:
        for candidate in shard.iterdir():
            details = candidate.lstat()
            if (
                not stat.S_ISREG(details.st_mode)
                or stat.S_ISLNK(details.st_mode)
                or not re_full_hex(candidate.name, 64)
                or candidate.name[:2] != shard.name
                or (
                    _OWNER_PERMISSIONS_SUPPORTED
                    and bool(stat.S_IMODE(details.st_mode) & 0o077)
                )
            ):
                raise ContextSafeError(
                    "evidence_store_corrupt",
                    "$",
                    "raw object store contains an invalid object",
                )
            if candidate.name not in referenced:
                candidate.unlink()

    @staticmethod
    def _append_record(connection: sqlite3.Connection, record: EvidenceRecord) -> None:
        record_json = canonical_json(record.to_dict())
        existing = connection.execute(
            "SELECT record_json FROM evidence_records WHERE evidence_id = ?",
            (record.evidence_id,),
        ).fetchone()
        if existing is not None:
            if existing[0] != record_json:
                raise ContextSafeError(
                    "evidence_id_collision",
                    "$",
                    "evidence ID is bound to different canonical content",
                )
            return
        count_row = connection.execute(
            "SELECT COUNT(*) FROM evidence_records"
        ).fetchone()
        if count_row is None or count_row[0] >= MAX_EVIDENCE_RECORDS:
            raise ContextSafeError(
                "evidence_count_exceeded",
                "$",
                "evidence index reached the supported record bound",
            )
        connection.execute(
            "INSERT INTO evidence_records(evidence_id, raw_sha256, record_json) "
            "VALUES (?, ?, ?)",
            (record.evidence_id, record.raw_sha256, record_json),
        )

    def _create_stage_path(self) -> Path:
        for _attempt in range(10):
            path = self.staging_root / f"{secrets.token_hex(16)}.part"
            if not path.exists():
                return path
        raise ContextSafeError(
            "evidence_store_io_error", "$", "staging object could not be allocated"
        )

    def _object_path(self, raw_sha256: str) -> Path:
        return self.raw_root / raw_sha256[:2] / raw_sha256

    @staticmethod
    def _verify_object(path: Path, expected_hash: str, expected_size: int) -> None:
        digest = hashlib.sha256()
        try:
            descriptor = os.open(path, _READ_FLAGS)
            with _closing_descriptor(
                descriptor,
                code="evidence_store_corrupt",
                message="raw object descriptor could not be closed",
            ):
                details = os.fstat(descriptor)
                if (
                    not stat.S_ISREG(details.st_mode)
                    or details.st_size != expected_size
                ):
                    raise ContextSafeError(
                        "evidence_store_corrupt", "$", "raw object metadata is invalid"
                    )
                if (
                    _OWNER_PERMISSIONS_SUPPORTED
                    and stat.S_IMODE(details.st_mode) & 0o077
                ):
                    raise ContextSafeError(
                        "evidence_store_corrupt",
                        "$",
                        "raw object permissions are unsafe",
                    )
                while True:
                    chunk = os.read(descriptor, 65_536)
                    if not chunk:
                        break
                    digest.update(chunk)
        except ContextSafeError:
            raise
        except OSError as exc:
            raise ContextSafeError(
                "evidence_store_corrupt", "$", "raw object could not be verified"
            ) from exc
        if digest.hexdigest() != expected_hash:
            raise ContextSafeError(
                "evidence_store_corrupt", "$", "raw object hash is invalid"
            )

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        if _DIRECTORY == 0:
            return
        try:
            descriptor = os.open(path, os.O_RDONLY | _DIRECTORY | _CLOEXEC)
            with _closing_descriptor(
                descriptor,
                code="evidence_store_io_error",
                message="directory descriptor could not be closed",
            ):
                os.fsync(descriptor)
        except ContextSafeError:
            raise
        except OSError as exc:
            raise ContextSafeError(
                "evidence_store_io_error",
                "$",
                "directory entry could not be synchronized",
            ) from exc

    def _remove_path(
        self,
        path: Path,
        *,
        primary_error: ContextSafeError | None,
        message: str,
        fsync_parent: bool = False,
    ) -> None:
        try:
            path.unlink()
        except FileNotFoundError:
            return
        except OSError as exc:
            if primary_error is None:
                raise ContextSafeError("evidence_store_io_error", "$", message) from exc
            return
        if not fsync_parent:
            return
        try:
            self._fsync_directory(path.parent)
        except ContextSafeError:
            if primary_error is None:
                raise
        except OSError as exc:
            if primary_error is None:
                raise ContextSafeError("evidence_store_io_error", "$", message) from exc

    def _remove_object(
        self,
        path: Path,
        *,
        primary_error: ContextSafeError | None = None,
    ) -> None:
        self._remove_path(
            path,
            primary_error=primary_error,
            message="uncommitted evidence object cleanup failed",
            fsync_parent=True,
        )

    @staticmethod
    def _rollback(connection: sqlite3.Connection) -> None:
        if connection.in_transaction:
            with suppress(sqlite3.Error):
                connection.execute("ROLLBACK")

    @staticmethod
    def _record_from_json(raw: object) -> EvidenceRecord:
        if not isinstance(raw, str):
            raise ContextSafeError(
                "evidence_store_corrupt", "$", "evidence index payload is invalid"
            )
        try:
            parsed = parse_json_bytes(raw.encode("utf-8"))
            return parse_evidence_record(parsed)
        except ContextSafeError as exc:
            raise ContextSafeError(
                "evidence_store_corrupt", "$", "evidence index payload is invalid"
            ) from exc


def re_full_hex(value: str, length: int) -> bool:
    """Return whether a path component is lowercase hexadecimal of exact length."""

    return len(value) == length and all(
        character in "0123456789abcdef" for character in value
    )


def _require_caller_owned_source(source_path: Path, workspace: Path) -> None:
    try:
        source_resolved = source_path.resolve(strict=True)
    except OSError as exc:
        raise ContextSafeError(
            "input_io_error", "$", "evidence source could not be read"
        ) from exc
    workspace_resolved = workspace.resolve(strict=False)
    if source_resolved == workspace_resolved or source_resolved.is_relative_to(
        workspace_resolved
    ):
        raise ContextSafeError(
            "source_not_caller_owned",
            "$",
            "evidence source must remain outside the ContextSafe workspace",
        )


def store_internal_synthetic_evidence(
    source_path: Path,
    *,
    workspace: Path,
    scope: EvidenceScope,
    metadata: EvidenceMetadata,
) -> EvidenceRecord:
    """Exercise B-018 without claiming unsigned evidence is authorized.

    This primitive has no CLI route and every resulting record is permanently marked
    non-executable. A future verified-plan layer must invoke the durable store through
    a separately reviewed authorization path; it must not relabel these records.
    """

    _require_caller_owned_source(source_path, workspace)
    with open_preflighted_source(source_path, scope) as source:
        return EvidenceStore(workspace).commit(source, metadata)
