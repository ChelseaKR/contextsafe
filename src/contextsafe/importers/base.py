"""The boundary every format importer shares: result, warnings, rejections.

An importer is the read-only conversion step between a caller-owned source
and the observation-set document `contextsafe evaluate --observations`
accepts. It runs the evidence-source boundary scan, converts what the scan
accepted into typed observations, and returns an :class:`ImportResult`. It
never persists, copies, indexes, or logs the source, and it never authorizes
anything: the persisting, plan-bound `evidence import` in Architecture
section 7 is a different command that does not exist.

Three rules hold across every format, and this module is where they are
stated once rather than once per adapter.

**A source converts whole or not at all.** A record the importer cannot map,
a value it cannot type, or an identifier outside the synthetic namespace
rejects the source. There is no partial result, no skipped record, and no
closest-supported-value substitution (A-033). The rejection names a code and
a location and never the content.

**Warnings are a closed vocabulary.** :class:`ImportWarningCode` lists every
warning an importer may attach. A warning is not free text about the source;
it names a limit of the conversion the caller must not mistake for a check
that happened.

**No profile is reviewed.** ``profile_reviewed`` is ``False`` on every
result this iteration can produce. The field exists so that the adapters
that follow cannot omit the question, and so that a mapping profile (B-026)
has a place to answer it once a governed one exists. Nothing in this package
may set it to ``True``.
"""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from contextsafe.canonical import JsonValue
from contextsafe.contract_validation import bounded_string, contract_error
from contextsafe.errors import ContextSafeError
from contextsafe.models import (
    OBSERVATION_SET_SCHEMA_VERSION,
    Checkpoint,
    Observation,
    SyntheticCase,
)


class ImportErrorCode(StrEnum):
    """The rejection family an importer's own decisions may raise.

    These cover what an importer decides. Codes the observation contract
    raises when the converted document is re-validated (``invalid_rsg_value``,
    ``non_synthetic_name``, ``invalid_support``, and the rest) pass through
    unchanged: the validator, not the importer, is the authority on what an
    observation is, and renaming its rejection would hide which rule fired.
    """

    FORMAT_UNSUPPORTED = "import_format_unsupported"
    """No registered importer carries the requested format name."""

    FIELD_CODE_UNMAPPED = "import_field_code_unmapped"
    """A record's field code has no entry in the importer's closed mapping."""

    CONCEPT_NOT_CONVERTIBLE = "import_concept_not_convertible"
    """The concept is mapped but the source cannot carry what it needs."""

    VALUE_MISSING = "import_value_missing"
    """A record carries no value; absence is not a value and is not typed."""

    VALUE_AMBIGUOUS = "import_value_ambiguous"
    """A record says a value is specified without carrying one."""

    CONTEXT_MISSING = "import_context_missing"
    """A concept that needs a context was given a record without one."""

    CASE_MISMATCH = "import_case_mismatch"
    """The source names a case or identifier the case document does not."""

    CHECKPOINT_MISMATCH = "import_checkpoint_mismatch"
    """The source names a checkpoint other than the one requested."""


class ImportWarningCode(StrEnum):
    """Everything an importer may say about a conversion beyond its output."""

    PLAN_BINDING_NOT_CHECKED = "plan_binding_not_checked"
    """The source's plan ID was carried, not verified against a plan."""

    MAPPING_PROFILE_NOT_BOUND = "mapping_profile_not_bound"
    """Values are carried as source tokens; no profile has bound them."""


def import_error(code: ImportErrorCode, path: str, message: str) -> ContextSafeError:
    """Build a value-minimized rejection in the importer family."""

    return contract_error(code.value, path, message)


@dataclass(frozen=True, slots=True)
class ImportResult:
    """What one conversion produced, and what it could not claim.

    ``observations`` is the whole output: every record became exactly one
    observation, or the conversion raised and there is no result. The counts
    are the denominator a caller can check that against. ``warnings`` is the
    closed set of limits this conversion carries. ``profile_reviewed`` is
    always ``False`` here and is not a field a caller sets.
    """

    format_name: str
    mapping_version: str
    source_sha256: str
    source_byte_count: int
    record_count: int
    observations: tuple[Observation, ...]
    warnings: tuple[ImportWarningCode, ...]
    profile_reviewed: bool = False

    def __post_init__(self) -> None:
        if self.profile_reviewed:
            raise contract_error(
                "profile_review_not_available",
                "$.profile_reviewed",
                "no mapping profile has been reviewed; the flag cannot be set",
            )
        if len(self.observations) != self.record_count:
            raise contract_error(
                "import_count_mismatch",
                "$.observations",
                "every accepted record must become exactly one observation",
            )

    def observation_set(self) -> dict[str, JsonValue]:
        """Return the document ``evaluate --observations`` accepts, and no more.

        The observation-set contract is closed, so the counts, warnings, and
        flags on this result have no place in it; they are for the caller
        that holds the result in process, and :meth:`to_dict` carries them.
        """

        return {
            "observations": [item.to_dict() for item in self.observations],
            "schema_version": OBSERVATION_SET_SCHEMA_VERSION,
        }

    def to_dict(self) -> dict[str, JsonValue]:
        """Return the value-minimized report of this conversion.

        In-process and test-only. This shape has no schema in ``schemas/``
        and no command emits it: the CLI writes only the observation set.
        If a second output document is ever decided, it gets a contract, a
        row in ``schemas/README.md``, and an emitter in that item, not here.
        """

        return {
            "format": self.format_name,
            "mapping_version": self.mapping_version,
            "observation_count": len(self.observations),
            "persisted": False,
            "profile_reviewed": self.profile_reviewed,
            "record_count": self.record_count,
            "source_byte_count": self.source_byte_count,
            "source_sha256": self.source_sha256,
            "warnings": [item.value for item in self.warnings],
        }


class Importer(Protocol):
    """One registered source format.

    Adding a format is one module that implements this protocol and one entry
    in :data:`contextsafe.importers.REGISTRY`. The command line reads the
    registry; it does not name formats.
    """

    @property
    def format_name(self) -> str:
        """The name the ``--format`` option selects this importer by."""

    @property
    def mapping_version(self) -> str:
        """The version every emitted observation records as its mapping."""

    def convert(
        self, source: Path, *, case: SyntheticCase, checkpoint: Checkpoint
    ) -> ImportResult:
        """Scan ``source`` and convert it whole, or raise and produce nothing."""


def checkpoint_value(value: object, path: str) -> Checkpoint:
    """Require one supported checkpoint name."""

    try:
        return Checkpoint(bounded_string(value, path))
    except ValueError as exc:
        raise contract_error(
            "unsupported_checkpoint", path, "checkpoint is unsupported"
        ) from exc
