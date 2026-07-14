"""Bounded, strict JSON loading shared by offline ContextSafe commands."""

import errno
import json
import os
import stat
from pathlib import Path
from typing import Any, BinaryIO

from contextsafe.canonical import JsonValue, as_json_value
from contextsafe.errors import ContextSafeError

MAX_INPUT_BYTES = 1_048_576
MAX_JSON_DEPTH = 64
_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
_DIRECTORY = getattr(os, "O_DIRECTORY", 0)
_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_NONBLOCK = getattr(os, "O_NONBLOCK", 0)
_DIRECTORY_FLAGS = os.O_RDONLY | _DIRECTORY | _NOFOLLOW | _CLOEXEC
_REGULAR_FILE_FLAGS = os.O_RDONLY | _NOFOLLOW | _NONBLOCK | _CLOEXEC
_DESCRIPTOR_RELATIVE_SUPPORTED = (
    os.open in os.supports_dir_fd and _DIRECTORY != 0 and _NOFOLLOW != 0
)
_UNSAFE_PATH_ERRNOS = frozenset({errno.ELOOP, errno.ENOTDIR})


class _DuplicateKeyError(ValueError):
    """Signal that JSON contained a duplicate object member."""


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError
        result[key] = value
    return result


def _reject_nonstandard_number(_value: str) -> None:
    raise ValueError


def _reject_excessive_depth(value: object) -> None:
    stack: list[tuple[object, int]] = [(value, 0)]
    while stack:
        item, depth = stack.pop()
        if depth > MAX_JSON_DEPTH:
            raise ContextSafeError(
                "input_too_deep", "$", "input exceeds the JSON nesting limit"
            )
        if isinstance(item, dict):
            stack.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            stack.extend((child, depth + 1) for child in item)


def _parse_json_bytes(raw: bytes) -> JsonValue:
    """Parse one already-bounded immutable byte buffer."""

    if len(raw) > MAX_INPUT_BYTES:
        raise ContextSafeError(
            "input_too_large", "$", "input exceeds the one MiB limit"
        )
    try:
        parsed = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_no_duplicate_keys,
            parse_constant=_reject_nonstandard_number,
        )
    except UnicodeDecodeError as exc:
        raise ContextSafeError("invalid_utf8", "$", "input must be UTF-8") from exc
    except _DuplicateKeyError as exc:
        raise ContextSafeError(
            "duplicate_json_key", "$", "duplicate object key is forbidden"
        ) from exc
    except RecursionError as exc:
        raise ContextSafeError(
            "input_too_deep", "$", "input exceeds the JSON nesting limit"
        ) from exc
    except json.JSONDecodeError as exc:
        raise ContextSafeError("invalid_json", "$", "input is not valid JSON") from exc
    except ValueError as exc:
        raise ContextSafeError("invalid_json", "$", "input is not valid JSON") from exc
    _reject_excessive_depth(parsed)
    return as_json_value(parsed)


def _read_bounded(handle: BinaryIO) -> bytes:
    return handle.read(MAX_INPUT_BYTES + 1)


def _read_bounded_fd(file_descriptor: int) -> bytes:
    chunks: list[bytes] = []
    remaining = MAX_INPUT_BYTES + 1
    while remaining:
        chunk = os.read(file_descriptor, remaining)
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _input_io_error(exc: OSError) -> ContextSafeError:
    if exc.errno in _UNSAFE_PATH_ERRNOS:
        return ContextSafeError(
            "input_path_unsafe",
            "$",
            "input path must not traverse links or non-directories",
        )
    return ContextSafeError("input_io_error", "$", "input could not be read")


def load_json(path: Path) -> JsonValue:
    """Load a bounded UTF-8 JSON value without duplicate keys or NaN values."""

    try:
        with path.open("rb") as handle:
            raw = _read_bounded(handle)
    except OSError as exc:
        raise _input_io_error(exc) from exc
    return _parse_json_bytes(raw)


def load_json_beneath(root: Path, relative_path: str) -> JsonValue:
    """Read one regular file beneath ``root`` without following any links.

    macOS and Linux both support descriptor-relative ``open`` with ``O_NOFOLLOW``.
    Retaining each directory descriptor prevents rename or symlink swaps from
    changing the object reached by a later path traversal.
    """

    if not _DESCRIPTOR_RELATIVE_SUPPORTED:
        raise ContextSafeError(
            "input_path_unsupported",
            "$",
            "platform cannot enforce descriptor-relative no-follow input",
        )
    parts = relative_path.split("/")
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise ContextSafeError(
            "input_path_unsafe", "$", "input path must remain beneath its root"
        )
    directory_descriptors: list[int] = []
    file_descriptor: int | None = None
    try:
        root_descriptor = os.open(root, _DIRECTORY_FLAGS)
        directory_descriptors.append(root_descriptor)
        parent_descriptor = root_descriptor
        for part in parts[:-1]:
            parent_descriptor = os.open(
                part, _DIRECTORY_FLAGS, dir_fd=parent_descriptor
            )
            directory_descriptors.append(parent_descriptor)
        file_descriptor = os.open(
            parts[-1], _REGULAR_FILE_FLAGS, dir_fd=parent_descriptor
        )
        if not stat.S_ISREG(os.fstat(file_descriptor).st_mode):
            raise ContextSafeError(
                "input_path_unsafe", "$", "input path must name a regular file"
            )
        return _parse_json_bytes(_read_bounded_fd(file_descriptor))
    except OSError as exc:
        raise _input_io_error(exc) from exc
    finally:
        if file_descriptor is not None:
            os.close(file_descriptor)
        for descriptor in reversed(directory_descriptors):
            os.close(descriptor)
