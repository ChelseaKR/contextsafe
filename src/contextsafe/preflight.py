"""Read-only, pre-persistence boundary checks for caller-owned evidence."""

import errno
import hashlib
import os
import re
import stat
import unicodedata
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from contextsafe.errors import ContextSafeError
from contextsafe.evidence import (
    EvidenceScope,
    PreflightResult,
    parse_evidence_source,
)
from contextsafe.jsonio import parse_json_bytes

MAX_EVIDENCE_BYTES = 1_048_576
_CHUNK_BYTES = 65_536
_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_NONBLOCK = getattr(os, "O_NONBLOCK", 0)
_SOURCE_FLAGS = os.O_RDONLY | _NOFOLLOW | _NONBLOCK | _CLOEXEC
_UNSAFE_PATH_ERRNOS = frozenset({errno.ELOOP, errno.ENOTDIR})
_PROHIBITED_KEYS = frozenset(
    {
        "accountnumber",
        "address",
        "birthdate",
        "comment",
        "contained",
        "dateofbirth",
        "diagnosis",
        "email",
        "freetext",
        "legalname",
        "medicalrecordnumber",
        "mrn",
        "name",
        "narrative",
        "note",
        "patientname",
        "phone",
        "socialsecuritynumber",
        "ssn",
        "telecom",
        "text",
    }
)
_SAFE_PATH_KEYS = frozenset(
    {
        "case_token",
        "checkpoint",
        "context_code",
        "field_code",
        "plan_id",
        "records",
        "schema_version",
        "source_pointer",
        "source_type",
        "synthetic_identifier",
        "system",
        "value",
        "value_code",
    }
)
_KNOWN_CANARIES = frozenset(
    {
        "contextsafephicanary",
        "ctxsafephicanaryalice",
        "realpatientcanary",
    }
)
_DIRECT_IDENTIFIER_PATTERNS = (
    re.compile(
        r"(?i)(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![A-Za-z0-9])"
    ),
    re.compile(r"(?<![0-9])[0-9]{3}-[0-9]{2}-[0-9]{4}(?![0-9])"),
    re.compile(
        r"(?<![0-9])(?:\+?1[ .-]?)?(?:\([0-9]{3}\)|[0-9]{3})[ .-][0-9]{3}[ .-][0-9]{4}(?![0-9])"
    ),
    re.compile(r"(?i)(?:https?://|www\.)"),
    re.compile(r"(?<![0-9])(?:19|20)[0-9]{2}-[0-9]{2}-[0-9]{2}(?![0-9])"),
    re.compile(r"(?i)\b(?:mrn|medical[ _-]?record|account)[ :#_-]+[A-Za-z0-9]{4,}\b"),
    re.compile(r"(?<![A-Za-z0-9])[0-9]{7,}(?![A-Za-z0-9])"),
)


@dataclass(frozen=True, slots=True)
class _DescriptorMetadata:
    device: int
    inode: int
    mode: int
    size: int
    modified_ns: int
    changed_ns: int


@dataclass(slots=True)
class PreflightedSource:
    """A validated source whose original descriptor remains open."""

    file_descriptor: int
    initial_metadata: _DescriptorMetadata
    result: PreflightResult

    def copy_to(self, destination_descriptor: int) -> None:
        """Repeat the read against the same descriptor and require an exact hash."""

        _assert_unchanged(self.file_descriptor, self.initial_metadata)
        try:
            os.lseek(self.file_descriptor, 0, os.SEEK_SET)
        except OSError as exc:
            raise ContextSafeError(
                "input_not_seekable", "$", "evidence source must be seekable"
            ) from exc
        digest = hashlib.sha256()
        count = 0
        try:
            while True:
                chunk = os.read(self.file_descriptor, _CHUNK_BYTES)
                if not chunk:
                    break
                count += len(chunk)
                if count > MAX_EVIDENCE_BYTES:
                    raise ContextSafeError(
                        "input_too_large",
                        "$",
                        "evidence exceeds the one MiB boundary limit",
                    )
                digest.update(chunk)
                _write_all(destination_descriptor, chunk)
        except ContextSafeError:
            raise
        except OSError as exc:
            raise ContextSafeError(
                "input_io_error", "$", "evidence source could not be read"
            ) from exc
        _assert_unchanged(self.file_descriptor, self.initial_metadata)
        if (
            count != self.result.raw_byte_count
            or digest.hexdigest() != self.result.raw_sha256
        ):
            raise ContextSafeError(
                "source_mutated",
                "$",
                "evidence changed after its boundary check",
            )


def _write_all(file_descriptor: int, value: bytes) -> None:
    offset = 0
    while offset < len(value):
        try:
            written = os.write(file_descriptor, value[offset:])
        except OSError as exc:
            raise ContextSafeError(
                "evidence_store_io_error",
                "$",
                "evidence staging write failed",
            ) from exc
        if written <= 0:
            raise ContextSafeError(
                "evidence_store_io_error",
                "$",
                "evidence staging write failed",
            )
        offset += written


def _descriptor_metadata(file_descriptor: int) -> _DescriptorMetadata:
    try:
        details = os.fstat(file_descriptor)
    except OSError as exc:
        raise ContextSafeError(
            "input_io_error", "$", "evidence source could not be inspected"
        ) from exc
    return _DescriptorMetadata(
        device=details.st_dev,
        inode=details.st_ino,
        mode=details.st_mode,
        size=details.st_size,
        modified_ns=details.st_mtime_ns,
        changed_ns=details.st_ctime_ns,
    )


def _assert_unchanged(file_descriptor: int, expected: _DescriptorMetadata) -> None:
    if _descriptor_metadata(file_descriptor) != expected:
        raise ContextSafeError(
            "source_mutated", "$", "evidence changed during its boundary check"
        )


def _input_io_error(exc: OSError) -> ContextSafeError:
    if exc.errno in _UNSAFE_PATH_ERRNOS:
        return ContextSafeError(
            "input_path_unsafe",
            "$",
            "evidence path must name a regular file without a final link",
        )
    return ContextSafeError("input_io_error", "$", "evidence source could not be read")


def _close_source_descriptor(
    file_descriptor: int, *, primary_error: BaseException | None
) -> None:
    """Close a retained source without replacing an error already in flight."""

    try:
        os.close(file_descriptor)
    except OSError as exc:
        if primary_error is None:
            raise ContextSafeError(
                "input_io_error",
                "$",
                "evidence source descriptor could not be closed",
            ) from exc


def _open_source(path: Path) -> int:
    if _NOFOLLOW == 0:
        raise ContextSafeError(
            "input_path_unsupported",
            "$",
            "platform cannot enforce no-follow evidence input",
        )
    try:
        file_descriptor = os.open(path, _SOURCE_FLAGS)
    except OSError as exc:
        raise _input_io_error(exc) from exc
    try:
        metadata = _descriptor_metadata(file_descriptor)
        if not stat.S_ISREG(metadata.mode):
            raise ContextSafeError(
                "input_path_unsafe", "$", "evidence source must be a regular file"
            )
        if metadata.size > MAX_EVIDENCE_BYTES:
            raise ContextSafeError(
                "input_too_large",
                "$",
                "evidence exceeds the one MiB boundary limit",
            )
        try:
            os.lseek(file_descriptor, 0, os.SEEK_SET)
        except OSError as exc:
            raise ContextSafeError(
                "input_not_seekable", "$", "evidence source must be seekable"
            ) from exc
    except BaseException as exc:
        _close_source_descriptor(file_descriptor, primary_error=exc)
        raise
    return file_descriptor


def _read_first_pass(file_descriptor: int) -> tuple[bytes, str]:
    chunks: list[bytes] = []
    digest = hashlib.sha256()
    count = 0
    try:
        while True:
            chunk = os.read(file_descriptor, _CHUNK_BYTES)
            if not chunk:
                break
            count += len(chunk)
            if count > MAX_EVIDENCE_BYTES:
                raise ContextSafeError(
                    "input_too_large",
                    "$",
                    "evidence exceeds the one MiB boundary limit",
                )
            chunks.append(chunk)
            digest.update(chunk)
    except ContextSafeError:
        raise
    except OSError as exc:
        raise ContextSafeError(
            "input_io_error", "$", "evidence source could not be read"
        ) from exc
    return b"".join(chunks), digest.hexdigest()


def _normalized(value: str) -> str:
    return unicodedata.normalize("NFKC", value)


def _reject_unsafe_string(value: str, path: str) -> None:
    if value != value.strip():
        raise ContextSafeError(
            "unapproved_free_text",
            path,
            "strings cannot contain boundary whitespace",
        )
    if any(unicodedata.category(character) in {"Cc", "Cf"} for character in value):
        raise ContextSafeError(
            "prohibited_unicode",
            path,
            "control and format characters are prohibited",
        )
    normalized = _normalized(value)
    compact = re.sub(r"[^a-z0-9]", "", normalized.casefold())
    if any(canary in compact for canary in _KNOWN_CANARIES):
        raise ContextSafeError(
            "phi_canary_detected", path, "a configured PHI canary was detected"
        )
    if any(
        pattern.search(normalized) is not None
        for pattern in _DIRECT_IDENTIFIER_PATTERNS
    ):
        raise ContextSafeError(
            "direct_identifier_detected",
            path,
            "a direct-identifier pattern was detected",
        )


def _normalized_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", _normalized(value).casefold())


def _boundary_scan(value: object) -> None:
    pending: list[tuple[object, str]] = [(value, "$")]
    while pending:
        item, path = pending.pop()
        if isinstance(item, dict):
            for key, child in item.items():
                _reject_unsafe_string(key, path)
                if _normalized_key(key) in _PROHIBITED_KEYS:
                    raise ContextSafeError(
                        "prohibited_field",
                        path,
                        "a free-text or identifying field is prohibited",
                    )
                child_path = f"{path}.{key}" if key in _SAFE_PATH_KEYS else path
                pending.append((child, child_path))
        elif isinstance(item, list):
            pending.extend(
                (child, f"{path}[{index}]") for index, child in enumerate(item)
            )
        elif isinstance(item, str):
            _reject_unsafe_string(item, path)


@contextmanager
def open_preflighted_source(
    path: Path, scope: EvidenceScope
) -> Iterator[PreflightedSource]:
    """Validate a first pass and retain the exact descriptor for a second pass."""

    file_descriptor = _open_source(path)
    primary_error: BaseException | None = None
    try:
        initial = _descriptor_metadata(file_descriptor)
        raw, raw_sha256 = _read_first_pass(file_descriptor)
        _assert_unchanged(file_descriptor, initial)
        parsed = parse_json_bytes(raw)
        _boundary_scan(parsed)
        parse_evidence_source(parsed, scope=scope)
        yield PreflightedSource(
            file_descriptor=file_descriptor,
            initial_metadata=initial,
            result=PreflightResult(
                scope=scope,
                raw_sha256=raw_sha256,
                raw_byte_count=len(raw),
            ),
        )
    except BaseException as exc:
        primary_error = exc
        raise
    finally:
        _close_source_descriptor(file_descriptor, primary_error=primary_error)


def preflight_source(path: Path, scope: EvidenceScope) -> PreflightResult:
    """Run a complete read-only pass without creating a workspace or log."""

    with open_preflighted_source(path, scope) as source:
        return source.result
