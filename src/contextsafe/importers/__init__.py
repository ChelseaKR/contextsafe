"""Format importers and the registry the command line reads them from.

`contextsafe import --format NAME` selects an importer by the name it is
registered under here. Adding a format is one new module implementing
:class:`contextsafe.importers.base.Importer` and one entry in
:data:`REGISTRY`; the command line derives its ``--format`` choices from the
registry and does not change. Every importer is a read-only conversion that
never persists the source and never sets ``profile_reviewed``.
"""

from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType

from contextsafe.contract_validation import bounded_string
from contextsafe.importers.base import (
    Importer,
    ImportErrorCode,
    ImportResult,
    ImportWarningCode,
    checkpoint_value,
    import_error,
)
from contextsafe.importers.canonical_json import CANONICAL_JSON_IMPORTER
from contextsafe.models import Checkpoint, SyntheticCase

__all__ = [
    "REGISTRY",
    "ImportErrorCode",
    "ImportResult",
    "ImportWarningCode",
    "Importer",
    "available_formats",
    "checkpoint_value",
    "import_source",
    "importer_for",
]

REGISTRY: Mapping[str, Importer] = MappingProxyType(
    {CANONICAL_JSON_IMPORTER.format_name: CANONICAL_JSON_IMPORTER}
)
"""Every registered format, by the name ``--format`` selects it with."""


def available_formats() -> tuple[str, ...]:
    """Return the registered format names in a stable order."""

    return tuple(sorted(REGISTRY))


def importer_for(format_name: object) -> Importer:
    """Return the importer registered under ``format_name`` or fail closed."""

    name = bounded_string(format_name, "$.format")
    importer = REGISTRY.get(name)
    if importer is None:
        raise import_error(
            ImportErrorCode.FORMAT_UNSUPPORTED,
            "$.format",
            "no importer is registered for the requested format",
        )
    return importer


def import_source(
    format_name: object,
    source: Path,
    *,
    case: SyntheticCase,
    checkpoint: Checkpoint,
) -> ImportResult:
    """Convert ``source`` with the importer registered under ``format_name``."""

    return importer_for(format_name).convert(source, case=case, checkpoint=checkpoint)
