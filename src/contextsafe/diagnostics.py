"""Diagnostics, a cleanup enumerator, and a support bundle that cannot leak.

Three operator tools, and one of them is dangerous enough to be the reason this
module is shaped the way it is.

**Diagnostics** answer "is this installation capable of what it claims", not
"what did this installation do". Interpreter version, platform, whether
descriptor-relative no-follow reads exist on this operating system, whether a
workspace is present and how many records its index holds. No case, no token,
no path.

**The cleanup enumerator** lists what the tool created inside a workspace, so
an operator can see it before deciding to remove it. It classifies every entry
it finds — the index, content-addressed objects, staging leftovers, and
anything unexpected — and reports shapes and sizes rather than names. Removal
is a separate, explicit act, it never leaves the workspace, it never follows a
symlink, and it never removes an entry the enumerator could not classify.

**The support bundle** is the dangerous one. A support bundle from this tool
could carry exactly the identity data the product exists to protect. So it is
redacted by construction rather than by filter: every field is a
:mod:`contextsafe.safe_value` ``SafeValue``, there is no constructor that
accepts free text, and the serializer raises on anything else. A filter would
have to recognise a patient name, and no filter recognises one spelled with a
Cyrillic homoglyph, or an MRN written with spaces between the digits, or a name
that sits in a directory component rather than in a filename.

The bundle is then scanned with :func:`contextsafe.preflight.identifier_hits`
before it is written, and refuses to write if anything fires. That scan is belt
and braces and is documented as such: it is a check on the construction, not
the thing that makes the bundle safe. Trusting it would be trusting the
denylist again.
"""

from __future__ import annotations

import errno
import os
import platform
import sys
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from contextsafe import __version__, safe_value
from contextsafe.canonical import JsonValue, canonical_json
from contextsafe.errors import ContextSafeError
from contextsafe.evidence_store import INDEX_SCHEMA_VERSION, EvidenceStore
from contextsafe.jsonio import MAX_INPUT_BYTES
from contextsafe.models import (
    RECEIPT_DOCUMENT_SCHEMA_VERSION,
    RECEIPT_SCHEMA_VERSION,
)
from contextsafe.preflight import identifier_hits

SUPPORT_BUNDLE_SCHEMA_VERSION = "contextsafe.support-bundle/0.1.0"
DIAGNOSTICS_SCHEMA_VERSION = "contextsafe.diagnostics/0.1.0"
CLEANUP_SCHEMA_VERSION = "contextsafe.cleanup/0.1.0"


class EntryKind(StrEnum):
    """What the enumerator decided a filesystem entry is."""

    INDEX = "index"
    OBJECT = "object"
    STAGING = "staging"
    DIRECTORY = "directory"
    UNEXPECTED = "unexpected"


REMOVABLE = frozenset(
    {EntryKind.INDEX, EntryKind.OBJECT, EntryKind.STAGING, EntryKind.DIRECTORY}
)
"""Kinds removal will touch. ``UNEXPECTED`` is reported and left alone."""

_PLATFORMS = frozenset({"Linux", "Darwin", "Windows", "unknown"})
_OUTCOMES = frozenset({"ok", "absent", "unreadable", "rejected"})


@dataclass(frozen=True, slots=True)
class CleanupEntry:
    """One thing the tool created, described without naming it."""

    kind: EntryKind
    relative_path: Path
    byte_count: int
    is_symlink: bool

    @property
    def removable(self) -> bool:
        """Whether removal may touch this entry."""

        return self.kind in REMOVABLE and not self.is_symlink


@dataclass(frozen=True, slots=True)
class CleanupPlan:
    """Everything the enumerator found under one workspace."""

    workspace: Path
    exists: bool
    entries: tuple[CleanupEntry, ...]

    @property
    def removable(self) -> tuple[CleanupEntry, ...]:
        """Entries removal would delete."""

        return tuple(entry for entry in self.entries if entry.removable)

    @property
    def retained(self) -> tuple[CleanupEntry, ...]:
        """Entries removal refuses to delete, and therefore reports."""

        return tuple(entry for entry in self.entries if not entry.removable)

    def to_dict(self) -> dict[str, JsonValue]:
        """Return the operator-facing summary, shapes and counts only."""

        return {
            "exists": self.exists,
            "removable": {
                "count": len(self.removable),
                "byte_count": sum(entry.byte_count for entry in self.removable),
            },
            "retained": {
                "count": len(self.retained),
                "byte_count": sum(entry.byte_count for entry in self.retained),
            },
            "schema_version": CLEANUP_SCHEMA_VERSION,
            "summary_by_kind": {
                kind.value: sum(1 for entry in self.entries if entry.kind is kind)
                for kind in EntryKind
            },
        }


def _classify(store: EvidenceStore, path: Path, *, is_directory: bool) -> EntryKind:
    if is_directory:
        return EntryKind.DIRECTORY
    if path == store.database_path:
        return EntryKind.INDEX
    try:
        relative = path.relative_to(store.staging_root)
    except ValueError:
        relative = None
    if relative is not None:
        return EntryKind.STAGING if path.suffix == ".part" else EntryKind.UNEXPECTED
    try:
        object_relative = path.relative_to(store.raw_root)
    except ValueError:
        return EntryKind.UNEXPECTED
    parts = object_relative.parts
    if len(parts) == 2 and len(parts[0]) == 2 and len(parts[1]) == 64:
        return EntryKind.OBJECT
    return EntryKind.UNEXPECTED


def _walk(root: Path) -> Iterator[Path]:
    """Yield every entry under ``root``, deepest first, never following links."""

    for parent, directories, files in os.walk(root, topdown=False, followlinks=False):
        base = Path(parent)
        for name in sorted(files):
            yield base / name
        for name in sorted(directories):
            yield base / name


def enumerate_cleanup(workspace: Path) -> CleanupPlan:
    """List what the tool created under ``workspace``, without naming it."""

    store = EvidenceStore(workspace)
    if not workspace.is_dir() or workspace.is_symlink():
        return CleanupPlan(workspace=workspace, exists=False, entries=())
    entries: list[CleanupEntry] = []
    for path in _walk(workspace):
        is_symlink, is_directory, size = _describe(path)
        entries.append(
            CleanupEntry(
                kind=_classify(store, path, is_directory=is_directory),
                relative_path=path.relative_to(workspace),
                byte_count=size,
                is_symlink=is_symlink,
            )
        )
    return CleanupPlan(workspace=workspace, exists=True, entries=tuple(entries))


def _describe(path: Path) -> tuple[bool, bool, int]:
    """Return link, directory, and size, tolerating an entry that vanished.

    A walk of a live directory races with anything else touching it. An entry
    that disappears between listing and stat is reported as an entry of unknown
    size rather than aborting the enumeration, because an operator who cannot
    enumerate cannot clean up.
    """

    try:
        is_symlink = path.is_symlink()
        is_directory = path.is_dir() and not is_symlink
        size = 0 if is_symlink or is_directory else path.stat().st_size
    except OSError:
        return False, False, 0
    return is_symlink, is_directory, size


def remove_cleanup(plan: CleanupPlan) -> tuple[int, int]:
    """Remove the removable entries in ``plan``; return removed and retained.

    Deletion is deliberately narrow: only inside the workspace, only entries
    the enumerator classified, never a symlink, and never the workspace root
    itself. An unclassifiable entry is somebody else's file until they say
    otherwise.
    """

    if not plan.exists:
        raise ContextSafeError(
            "cleanup_workspace_absent", "$", "there is no workspace to clean"
        )
    removed = 0
    retained = len(plan.retained)
    for entry in plan.entries:
        target = plan.workspace / entry.relative_path
        if not entry.removable:
            continue
        if not target.resolve().is_relative_to(plan.workspace.resolve()):
            continue  # pragma: no cover - defensive; entries come from a walk
        if entry.kind is EntryKind.DIRECTORY:
            # A directory still holding something the enumerator refused to
            # touch is retained with its contents. Emptying it would mean
            # deleting the thing we just declined to delete.
            try:
                target.rmdir()
            except OSError as exc:
                if exc.errno in (errno.ENOTEMPTY, errno.EEXIST):
                    retained += 1
                    continue
                raise ContextSafeError(
                    "cleanup_io_error", "$", "a workspace entry could not be removed"
                ) from exc
        else:
            try:
                target.unlink()
            except OSError as exc:
                raise ContextSafeError(
                    "cleanup_io_error", "$", "a workspace entry could not be removed"
                ) from exc
        removed += 1
    return removed, retained


def _workspace_state(workspace: Path | None) -> tuple[str, int, int]:
    """Return the index outcome, record count, and object count."""

    if workspace is None:
        return "absent", 0, 0
    plan = enumerate_cleanup(workspace)
    objects = sum(1 for entry in plan.entries if entry.kind is EntryKind.OBJECT)
    if not plan.exists:
        return "absent", 0, 0
    try:
        records = len(EvidenceStore(workspace).list_records())
    except ContextSafeError:
        return "rejected", 0, objects
    except OSError:  # pragma: no cover - defensive
        return "unreadable", 0, objects
    return "ok", records, objects


def build_diagnostics(workspace: Path | None = None) -> dict[str, JsonValue]:
    """Return what this installation is capable of, not what it has done."""

    outcome, records, objects = _workspace_state(workspace)
    return {
        "capabilities": {
            "descriptor_relative_reads": os.open in os.supports_dir_fd,
            "no_follow_open": hasattr(os, "O_NOFOLLOW") and os.O_NOFOLLOW != 0,
            "owner_only_permissions": os.name == "posix",
        },
        "contracts": {
            "evidence_index": INDEX_SCHEMA_VERSION,
            "receipt": RECEIPT_SCHEMA_VERSION,
            "receipt_document": RECEIPT_DOCUMENT_SCHEMA_VERSION,
        },
        "limits": {"max_input_bytes": MAX_INPUT_BYTES},
        "runtime": {
            "implementation": sys.implementation.name,
            "platform": platform.system() or "unknown",
            "python": platform.python_version(),
        },
        "runner_version": __version__,
        "schema_version": DIAGNOSTICS_SCHEMA_VERSION,
        "workspace": {
            "index_outcome": outcome,
            "object_count": objects,
            "record_count": records,
        },
    }


def build_support_bundle(
    workspace: Path | None = None,
    *,
    error_codes: Sequence[str] = (),
) -> dict[str, JsonValue]:
    """Assemble a support bundle out of values that cannot carry free text.

    ``error_codes`` are ContextSafe error codes an operator wants included.
    They are recorded as digests rather than as text: an error code is already
    a closed vocabulary, but this function has no way to know that the string
    it was handed is one, and a bundle is not the place to find out.
    """

    outcome, records, objects = _workspace_state(workspace)
    section: dict[str, object] = {
        "capabilities": {
            "descriptor_relative_reads": safe_value.flag(os.open in os.supports_dir_fd),
            "owner_only_permissions": safe_value.flag(os.name == "posix"),
        },
        "contracts": {
            "evidence_index": safe_value.digest(INDEX_SCHEMA_VERSION),
            "receipt": safe_value.digest(RECEIPT_SCHEMA_VERSION),
        },
        "reported_errors": [
            safe_value.digest(code, pointer=f"$.reported_errors[{index}]")
            for index, code in enumerate(error_codes)
        ],
        "runtime": {
            "implementation": safe_value.enum_value(
                sys.implementation.name, frozenset({"cpython", "pypy", "other"})
            )
            if sys.implementation.name in ("cpython", "pypy")
            else safe_value.enum_value("other", frozenset({"other"})),
            "platform": safe_value.enum_value(
                platform.system() if platform.system() in _PLATFORMS else "unknown",
                _PLATFORMS,
            ),
            "python": safe_value.version(platform.python_version()),
        },
        "runner_version": safe_value.version(__version__),
        "workspace": {
            "index_outcome": safe_value.enum_value(outcome, _OUTCOMES),
            "object_count": safe_value.count(objects),
            "path_shape": safe_value.path_shape(workspace or Path(".")),
            "record_count": safe_value.count(records),
        },
    }
    bundle: dict[str, JsonValue] = {
        "schema_version": SUPPORT_BUNDLE_SCHEMA_VERSION,
        "sections": safe_value.to_json(section),  # type: ignore[arg-type]
    }
    _verify_bundle(bundle)
    return bundle


def _verify_bundle(bundle: dict[str, JsonValue]) -> None:
    """Scan the assembled bundle, and refuse to emit it if anything fires.

    This is the second pass, not the first. The bundle is already incapable of
    carrying free text; if a detector fires here, the constructive layer is
    broken and the right response is to write nothing and say so.
    """

    hits = identifier_hits(canonical_json(bundle))
    if hits:
        raise ContextSafeError(
            "support_bundle_rejected",
            "$",
            "the assembled bundle tripped a boundary detector and was not "
            f"written ({len(hits)} detector(s))",
        )
