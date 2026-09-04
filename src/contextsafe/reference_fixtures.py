"""The packaged synthetic reference fixtures, and the command that exports them.

The reference inputs under ``fixtures/reference`` beside this module are
package data, so an installed wheel carries them exactly as a checkout does.
Every documented quickstart names them by the relative path
``fixtures/reference/<name>``; ``contextsafe fixtures export`` writes them to
that path, or to ``--directory``, so the same commands run verbatim from a
clone and from an installed wheel. Until 2026-09-02 they lived at the
repository root, the wheel did not carry them, and the README's own first
command failed closed with ``input_io_error`` from any install -- a path no
test could see, because every test runs from the checkout.

The export is fail-closed and byte-exact. It reads every packaged file before
it writes anything, so an install missing one fixture cannot export four and
report success. An existing target that is byte-identical is left alone and
reported as ``unchanged``; one that differs, or that is not a plain file, is a
contract error and nothing is written -- a fixture someone edited for an
experiment must not be silently reverted, and a fixture that drifted from the
package must not be silently accepted. The manifest states its denominator:
every name, its digest, and what was done with it.
"""

import hashlib
from pathlib import Path

from contextsafe.canonical import JsonValue
from contextsafe.errors import ContextSafeError

REFERENCE_ROOT = Path(__file__).parent / "fixtures" / "reference"
"""Where the packaged reference fixtures live, in a checkout and in a wheel."""

REFERENCE_FILES: tuple[str, ...] = (
    "case.json",
    "evidence-source.json",
    "fhir-patient.json",
    "hl7v2-er7-message.hl7",
    "lis-export.csv",
    "lis-export.json",
    "mapping-canonical-json.json",
    "mapping-fhir-r4-json.json",
    "mapping-hl7v2-er7.json",
    "mapping-lis-csv.json",
    "mapping-lis-json.json",
    "observations.json",
    "observations-predicates.json",
    "pack-draft.json",
    "rules.json",
    "rules-predicates.json",
)
"""The complete reference set, named rather than globbed.

A glob over an incomplete install would export a shorter list and call it
done. Naming the files makes a missing one a failure instead. The two
``lis-export`` files are the synthetic laboratory export the ``lis-csv`` and
``lis-json`` importers read (B-025); their tokens are invented and they are
not the shape of any real system's export. The five ``mapping-*`` files are
one reference mapping profile per registered importer (B-026), each binding
that importer's reference fixture tokens to the reference case's values;
every one says ``not_reviewed``, and none is the profile of any real system.

done. Naming the files makes a missing one a failure instead.

``rules-predicates.json`` and ``observations-predicates.json`` are the B-028
pair: an ungoverned, reference-only rule set that exercises every predicate of
the 0.2.0 rule-set contract against the same case, and the observation set it
needs (the reference observations plus one name-to-use observation at
registration, so a cross-checkpoint predicate has two checkpoints to read).
They do not change ``rules.json`` or ``observations.json``.
"""

DEFAULT_EXPORT_DIRECTORY = Path("fixtures") / "reference"
"""The relative path every documented command uses."""


def _packaged(name: str) -> bytes:
    try:
        return (REFERENCE_ROOT / name).read_bytes()
    except OSError as exc:
        raise ContextSafeError(
            "fixture_missing",
            f"$.{name}",
            "a packaged reference fixture could not be read; the installation "
            "is incomplete and nothing was written",
        ) from exc


def _conflict(name: str, message: str) -> ContextSafeError:
    return ContextSafeError(
        "fixture_export_conflict", f"$.{name}", f"{message}; nothing was written"
    )


def _status(target: Path, name: str, data: bytes) -> str:
    """Decide what the export would do at ``target`` without touching it."""

    if target.is_symlink():
        raise _conflict(name, "a symbolic link is already at the export path")
    if not target.exists():
        return "written"
    try:
        existing = target.read_bytes()
    except OSError as exc:
        raise _conflict(
            name,
            "something already at the export path could not be compared with "
            "the packaged fixture",
        ) from exc
    if existing != data:
        raise _conflict(
            name,
            "a file already at the export path differs from the packaged fixture",
        )
    return "unchanged"


def export_reference_fixtures(directory: Path) -> dict[str, JsonValue]:
    """Copy every packaged reference fixture into ``directory``.

    Returns the manifest the CLI prints: the directory as given, and for each
    fixture its SHA-256 and whether it was ``written`` or found already there
    and ``unchanged``. Raises ``ContextSafeError`` before writing anything if a
    packaged file is missing (``fixture_missing``) or an existing target is
    not byte-identical (``fixture_export_conflict``), and ``output_io_error``
    if the directory or a file could not be written.
    """

    packaged = {name: _packaged(name) for name in REFERENCE_FILES}
    statuses = {
        name: _status(directory / name, name, data) for name, data in packaged.items()
    }
    try:
        directory.mkdir(parents=True, exist_ok=True)
        for name, status in statuses.items():
            if status == "written":
                (directory / name).write_bytes(packaged[name])
    except OSError as exc:
        raise ContextSafeError(
            "output_io_error", "$", "output could not be written"
        ) from exc
    files: dict[str, JsonValue] = {
        name: {
            "sha256": hashlib.sha256(packaged[name]).hexdigest(),
            "status": statuses[name],
        }
        for name in REFERENCE_FILES
    }
    return {"directory": directory.as_posix(), "files": files}
