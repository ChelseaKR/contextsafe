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

from contextsafe.canonical import JsonValue
from contextsafe.errors import ContextSafeError
from contextsafe.evidence import (
    EvidenceScope,
    PreflightResult,
    parse_evidence_source,
)
from contextsafe.identifiers import (
    DETECTORS,
    KNOWN_CANARIES,
    identifier_hits,
    normalized,
)
from contextsafe.jsonio import parse_json_bytes

# The detectors themselves live in `identifiers`, a leaf module, so the evidence
# layer can reach one definition of them without importing this one and creating
# a cycle. `identifier_hits` is re-exported here because that is the documented
# extension point and where every caller already imports it from.
__all__ = [
    "CANONICAL_JSON_PROFILE",
    "MAX_EVIDENCE_BYTES",
    "BoundaryProfile",
    "ScannedSource",
    "identifier_hits",
    "open_preflighted_source",
    "scan_source",
]

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


@dataclass(frozen=True, slots=True)
class BoundaryProfile:
    """What one source format's boundary scan differs in from the canonical scan.

    The scan is one set of rules for every format: size, regular file, no
    final link, strict JSON, prohibited keys, Unicode controls, canaries, and
    direct-identifier patterns. A format that has to carry something the
    canonical rules name declares it here, as a delta from the canonical
    profile rather than as a second rule set, so that what a format relaxes
    is written down in one place and is exactly as long as the list below.

    ``permitted_keys`` are prohibited keys the format carries by name and
    bounds itself: a FHIR ``Patient`` cannot say who a person is to be called
    without ``name``. Permitting the key does not permit its content; the
    format's own closed parser decides what may be under it, and every
    string under it is still scanned.

    ``path_keys`` are the format's element names that may appear in an
    error location, so a rejection can say where without echoing a key the
    scan has not seen before.

    ``published_constants`` are string values that are the format's own
    published identifiers, such as an extension URL the standard defines.
    They are not content, and the URL detector would otherwise reject every
    one of them. A value is exempt only when it is equal to one of these
    exactly; a value that merely starts like one is scanned in full.
    """

    permitted_keys: frozenset[str] = frozenset()
    path_keys: frozenset[str] = frozenset()
    published_constants: frozenset[str] = frozenset()

    def prohibited_keys(self) -> frozenset[str]:
        """The canonical prohibited keys, less the ones this format permits."""

        return _PROHIBITED_KEYS - self.permitted_keys

    def safe_path_keys(self) -> frozenset[str]:
        """The canonical path keys plus this format's element names."""

        return _SAFE_PATH_KEYS | self.path_keys


CANONICAL_JSON_PROFILE = BoundaryProfile()
"""The canonical envelope's scan: no key permitted, no constant exempt."""


@dataclass(frozen=True, slots=True)
class _DescriptorMetadata:
    device: int
    inode: int
    mode: int
    size: int
    modified_ns: int
    changed_ns: int


@dataclass(frozen=True, slots=True)
class ScannedSource:
    """One complete, read-only first pass over a caller-owned source.

    What the pass established and nothing more: the digest and length of the
    bytes it read, and the parsed value after the boundary scan accepted it.
    The scan is the profile-independent half of a preflight — size, regular
    file, no final link, strict JSON, prohibited fields, Unicode controls,
    canaries, and direct-identifier patterns — and it binds the value to no
    plan, case, or checkpoint. A caller that needs that binding runs
    :func:`open_preflighted_source`; a caller that reads the envelope against
    something other than an execution plan starts here.
    """

    raw_sha256: str
    raw_byte_count: int
    value: JsonValue


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
    text = normalized(value)
    compact = re.sub(r"[^a-z0-9]", "", text.casefold())
    if any(canary in compact for canary in KNOWN_CANARIES):
        raise ContextSafeError(
            "phi_canary_detected", path, "a configured PHI canary was detected"
        )
    if any(detector.pattern.search(text) is not None for detector in DETECTORS):
        raise ContextSafeError(
            "direct_identifier_detected",
            path,
            "a direct-identifier pattern was detected",
        )


def _normalized_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", normalized(value).casefold())


def _boundary_scan(value: object, profile: BoundaryProfile) -> None:
    prohibited = profile.prohibited_keys()
    safe_path_keys = profile.safe_path_keys()
    pending: list[tuple[object, str]] = [(value, "$")]
    while pending:
        item, path = pending.pop()
        if isinstance(item, dict):
            for key, child in item.items():
                _reject_unsafe_string(key, path)
                if _normalized_key(key) in prohibited:
                    raise ContextSafeError(
                        "prohibited_field",
                        path,
                        "a free-text or identifying field is prohibited",
                    )
                child_path = f"{path}.{key}" if key in safe_path_keys else path
                pending.append((child, child_path))
        elif isinstance(item, list):
            pending.extend(
                (child, f"{path}[{index}]") for index, child in enumerate(item)
            )
        elif isinstance(item, str) and item not in profile.published_constants:
            # The exemption is by exact equality at any position, by design: a
            # published identifier is not content wherever the format puts it.
            _reject_unsafe_string(item, path)


def _scan_open_descriptor(
    file_descriptor: int, profile: BoundaryProfile
) -> tuple[_DescriptorMetadata, ScannedSource]:
    """Read, hash, parse, and boundary-scan one already-open descriptor."""

    initial = _descriptor_metadata(file_descriptor)
    raw, raw_sha256 = _read_first_pass(file_descriptor)
    _assert_unchanged(file_descriptor, initial)
    parsed = parse_json_bytes(raw)
    _boundary_scan(parsed, profile)
    return initial, ScannedSource(
        raw_sha256=raw_sha256, raw_byte_count=len(raw), value=parsed
    )


def scan_source(
    path: Path, profile: BoundaryProfile = CANONICAL_JSON_PROFILE
) -> ScannedSource:
    """Run the complete read-only boundary scan and close the descriptor.

    Opens the path once with the same no-follow, regular-file, and one MiB
    rules as a preflight, reads the whole first pass, and returns only what
    that pass established. It creates no workspace, copy, index, or log, and
    it does not bind the value to a plan scope: that is the caller's check,
    made against whatever contract the caller is authorized to hold. The
    ``profile`` is the format's declared delta from the canonical scan; the
    size, link, JSON, Unicode, canary, and detector rules are not part of it
    and apply to every format alike.
    """

    file_descriptor = _open_source(path)
    primary_error: BaseException | None = None
    try:
        _initial, scanned = _scan_open_descriptor(file_descriptor, profile)
        return scanned
    except BaseException as exc:
        primary_error = exc
        raise
    finally:
        _close_source_descriptor(file_descriptor, primary_error=primary_error)


@contextmanager
def open_preflighted_source(
    path: Path, scope: EvidenceScope
) -> Iterator[PreflightedSource]:
    """Validate a first pass and retain the exact descriptor for a second pass."""

    file_descriptor = _open_source(path)
    primary_error: BaseException | None = None
    try:
        initial, scanned = _scan_open_descriptor(
            file_descriptor, CANONICAL_JSON_PROFILE
        )
        parse_evidence_source(scanned.value, scope=scope)
        yield PreflightedSource(
            file_descriptor=file_descriptor,
            initial_metadata=initial,
            result=PreflightResult(
                scope=scope,
                raw_sha256=scanned.raw_sha256,
                raw_byte_count=scanned.raw_byte_count,
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
