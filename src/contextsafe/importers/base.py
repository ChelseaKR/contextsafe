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
may set it to ``True``. A mapping profile can now be applied
(:mod:`contextsafe.importers.mapping`), and the result then carries the
profile's digest and version; its review status is ``not_reviewed`` and
``profile_reviewed`` stays ``False``.

**Every observation says what the source said.** Beside each observation an
importer records the :class:`~contextsafe.mapping_profile.SourceToken` it was
read from -- the carrier (a field code, an extension URL, a segment-field, a
column) and the verbatim token -- so a mapping profile row matches on the
source's own words rather than on the canonical value the importer built.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from contextsafe.canonical import JsonValue
from contextsafe.contract_validation import bounded_string, contract_error
from contextsafe.errors import ContextSafeError
from contextsafe.laboratory import LaboratoryResult, result_set_document
from contextsafe.mapping_profile import SourceToken
from contextsafe.models import (
    OBSERVATION_SET_SCHEMA_VERSION,
    Checkpoint,
    ConceptKind,
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

    RESOURCE_UNSUPPORTED = "import_resource_unsupported"
    """A resource, segment, or document kind is outside the format's allowlist."""

    ELEMENT_UNSUPPORTED = "import_element_unsupported"
    """An element is outside the format's allowlist; nothing was stripped."""

    EXTENSION_UNKNOWN = "import_extension_unknown"
    """An extension or sub-extension name has no entry in the format's profile."""

    IDENTIFIER_NOT_SYNTHETIC = "import_identifier_not_synthetic"
    """An identifier, resource id, or identifier cell is outside the synthetic namespace."""

    VALUE_UNSUPPORTED = "import_value_unsupported"
    """A coded value or name part is outside the closed alphabet the profile admits."""

    REFERENCE_OUTSIDE_DOCUMENT = "import_reference_outside_document"
    """A reference points at something the document does not carry."""

    CARDINALITY_UNSUPPORTED = "import_cardinality_unsupported"
    """A count the profile fixes (exactly one, at least one, at most N) was not met."""

    REPETITION_NOT_ALLOWED = "import_repetition_not_allowed"
    """A field repeats where the importer's profile admits exactly one value."""

    SEGMENT_NOT_ALLOWED = "import_segment_not_allowed"
    """A segment or record kind is outside the importer's closed allowlist."""

    FIELD_NOT_IN_PROFILE = "import_field_not_in_profile"
    """A populated field has no entry in the importer's closed profile."""

    VALUE_NOT_IN_PROFILE = "import_value_not_in_profile"
    """A coded value, type, or shape is outside the profile's closed set."""

    SOURCE_MALFORMED = "import_source_malformed"
    """The source does not follow the grammar its format requires."""

    BOUND_EXCEEDED = "import_bound_exceeded"
    """A row, column, or cell count or length is outside the format's bounds."""

    COLUMN_UNKNOWN = "import_column_unknown"
    """A header or key is outside the format's closed column allowlist."""

    COLUMN_DUPLICATE = "import_column_duplicate"
    """A header or key appears more than once in the same table."""

    COLUMN_MISSING = "import_column_missing"
    """A column the format requires, or a column another row carries, is absent."""

    FORMULA_CELL = "import_formula_cell"
    """A cell begins with a character a spreadsheet would execute."""

    CELL_FREE_TEXT = "import_cell_free_text"
    """A cell is free text where a bounded token is required, which is everywhere."""


class ImportWarningCode(StrEnum):
    """Everything an importer may say about a conversion beyond its output."""

    PLAN_BINDING_NOT_CHECKED = "plan_binding_not_checked"
    """The source's plan ID was carried, not verified against a plan."""

    MAPPING_PROFILE_NOT_BOUND = "mapping_profile_not_bound"
    """Values are carried as source tokens; no profile has bound them."""

    CHECKPOINT_ASSERTED_BY_CALLER = "checkpoint_asserted_by_caller"
    """The source names no checkpoint; the one recorded is the caller's claim."""

    CHECKPOINT_NOT_IN_SOURCE = "checkpoint_not_in_source"
    """The source cannot state a checkpoint; the requested one was applied."""

    RESULT_COLUMNS_NOT_OBSERVED = "result_columns_not_observed"
    """The source carries laboratory result columns that became no observation.

    Attached when a row's result cells became no laboratory result: the
    source names only some of the result columns, or the row leaves a column
    that identifies a result empty. The cells are recognized, bounded,
    scanned, and counted, and nothing is claimed from them. It can appear
    beside ``result_observations_not_written`` when some rows became results
    and others did not.
    """

    RESULT_OBSERVATIONS_NOT_WRITTEN = "result_observations_not_written"
    """The conversion produced laboratory result observations that no file carries.

    ``contextsafe import`` writes the observation-set document and nothing
    else, and no receipt section carries a laboratory outcome yet, so a
    caller that wants the results holds the :class:`ImportResult` in
    process. The warning exists so that a caller reading only the written
    document cannot mistake it for everything the source produced.
    """

    MAPPING_PROFILE_ROW_UNMATCHED = "mapping_profile_row_unmatched"
    """A profile was applied and at least one token had no row; it stays verbatim."""


UNBOUND_CODE_SYSTEM = "urn:contextsafe:unbound-code-system"
"""Gender identity's ``code_system`` when the source names none.

A source that carries a code and no code system has not said where the code
came from. A profile binds a token to the system it belongs to; until one
does, the observation says the system is unbound rather than claiming one.
"""

UNBOUND_SOURCE = "urn:contextsafe:unbound-source"
"""Recorded sex or gender's ``source`` when the source names none.

The recording context of an RSG value is a property of the system that
recorded it, not of the checkpoint it was observed at, so the checkpoint is
never written here in its place.
"""


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

    ``unobserved_cell_count`` is the number of cells the importer recognized
    under a column its profile names and deliberately did not convert: the
    laboratory result columns of an LIS export, whose observation family is
    a later item. It counts what was read and not claimed, so a caller
    holding the result can see that the source carried more than the
    observations say. It is zero for a format with no such column.

    ``results`` is the laboratory result observation family
    (:mod:`contextsafe.laboratory`): one result per row of a source that
    carries the whole result column set. It is a separate observation kind
    with its own document, so it is not counted in ``record_count`` and
    never appears in ``observation_set()``; no command writes it, which is
    what ``result_observations_not_written`` says.

    ``source_tokens`` is one :class:`SourceToken` per observation, in the
    same order: what the source said before anything bound it. Every
    registered importer records them; a result built without them cannot
    have a mapping profile applied. ``profile_sha256`` and
    ``profile_version`` name the profile that was applied, or are ``None``.
    """

    format_name: str
    mapping_version: str
    source_sha256: str
    source_byte_count: int
    record_count: int
    observations: tuple[Observation, ...]
    warnings: tuple[ImportWarningCode, ...]
    profile_reviewed: bool = False
    unobserved_cell_count: int = 0
    results: tuple[LaboratoryResult, ...] = ()
    source_tokens: tuple[SourceToken, ...] = ()
    profile_sha256: str | None = None
    profile_version: str | None = None

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
        if self.unobserved_cell_count < 0:
            raise contract_error(
                "import_count_mismatch",
                "$.unobserved_cell_count",
                "a count of unobserved cells cannot be negative",
            )
        if self.source_tokens and len(self.source_tokens) != len(self.observations):
            raise contract_error(
                "import_count_mismatch",
                "$.source_tokens",
                "every observation records exactly one source token",
            )
        if (self.profile_sha256 is None) != (self.profile_version is None):
            raise contract_error(
                "mapping_profile_binding_incomplete",
                "$.profile_sha256",
                "a profile binding carries both profile_sha256 and profile_version",
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

    def result_set(self) -> dict[str, JsonValue]:
        """Return the laboratory result-set document this conversion produced.

        A separate contract from the observation set
        (``contextsafe.result-set/0.1.0``) because a laboratory result is a
        separate observation kind, not a sixth canonical concept. No command
        writes it yet.
        """

        return result_set_document(self.results)

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
            "profile_sha256": self.profile_sha256,
            "profile_version": self.profile_version,
            "record_count": self.record_count,
            "result_count": len(self.results),
            "source_byte_count": self.source_byte_count,
            "source_sha256": self.source_sha256,
            "unobserved_cell_count": self.unobserved_cell_count,
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

    @property
    def carriers(self) -> Mapping[str, frozenset[ConceptKind]]:
        """Every carrier this importer reads a token from, and as which concepts.

        The closed vocabulary a mapping profile for this format may name in
        a row's ``source.carrier``, each with the concepts the importer can
        emit that carrier as. A carrier the importer reads as exactly one
        concept lists exactly one, so a profile cannot read it as another.
        """

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
