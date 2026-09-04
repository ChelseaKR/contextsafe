"""Format importers and the registry the command line reads them from.

`contextsafe import --format NAME` selects an importer by the name it is
registered under here. Adding a format is one new module implementing
:class:`contextsafe.importers.base.Importer` and one entry in
:data:`REGISTRY`; the command line derives its ``--format`` choices from the
registry and does not change. Every importer is a read-only conversion that
never persists the source and never sets ``profile_reviewed``.

The registry is also the authority a mapping profile (B-026) is validated
against: :func:`carrier_table` collects every importer's declared carriers,
so a profile can name only a carrier an importer reads and only under a
concept that importer emits it as, and :func:`import_source` applies a
validated profile after the conversion, never during it.
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
from contextsafe.importers.fhir_r4_json import FHIR_R4_JSON_IMPORTER
from contextsafe.importers.hl7v2_er7 import HL7V2_ER7_IMPORTER
from contextsafe.importers.lis import LIS_CSV_IMPORTER, LIS_JSON_IMPORTER
from contextsafe.importers.mapping import apply_profile
from contextsafe.mapping_profile import (
    CarrierTable,
    MappingProfile,
    MappingProfileCompilation,
    compile_mapping_profile,
    parse_mapping_profile,
)
from contextsafe.models import Checkpoint, SyntheticCase

__all__ = [
    "REGISTRY",
    "ImportErrorCode",
    "ImportResult",
    "ImportWarningCode",
    "Importer",
    "apply_profile",
    "available_formats",
    "carrier_table",
    "checkpoint_value",
    "compile_profile",
    "import_source",
    "importer_for",
    "load_profile",
]

REGISTRY: Mapping[str, Importer] = MappingProxyType(
    {
        CANONICAL_JSON_IMPORTER.format_name: CANONICAL_JSON_IMPORTER,
        FHIR_R4_JSON_IMPORTER.format_name: FHIR_R4_JSON_IMPORTER,
        HL7V2_ER7_IMPORTER.format_name: HL7V2_ER7_IMPORTER,
        LIS_CSV_IMPORTER.format_name: LIS_CSV_IMPORTER,
        LIS_JSON_IMPORTER.format_name: LIS_JSON_IMPORTER,
    }
)
"""Every registered format, by the name ``--format`` selects it with.

``lis-csv`` and ``lis-json`` (B-025) read the identity columns of a
laboratory result export at ``lis_return`` and nothing else; the result
columns wait for the laboratory observation family.
"""


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


def carrier_table() -> CarrierTable:
    """Every registered format's carriers, as the profile validator needs them."""

    return MappingProxyType(
        {name: importer.carriers for name, importer in REGISTRY.items()}
    )


def load_profile(value: object) -> MappingProfile:
    """Validate a mapping profile document against the registered carriers."""

    return parse_mapping_profile(value, carriers=carrier_table())


def compile_profile(value: object) -> MappingProfileCompilation:
    """Validate a mapping profile and return its canonical form and digest."""

    return compile_mapping_profile(value, carriers=carrier_table())


def import_source(
    format_name: object,
    source: Path,
    *,
    case: SyntheticCase,
    checkpoint: Checkpoint,
    profile: MappingProfile | None = None,
) -> ImportResult:
    """Convert ``source`` with the importer registered under ``format_name``.

    With a ``profile``, the conversion runs exactly as without one and the
    profile is applied to what it produced; without one, every value is the
    source's own token, verbatim.
    """

    result = importer_for(format_name).convert(source, case=case, checkpoint=checkpoint)
    if profile is None:
        return result
    return apply_profile(result, profile)
