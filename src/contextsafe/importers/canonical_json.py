"""The canonical JSON importer: boundary envelope in, observation set out.

Reference-only and ungoverned. The mapping from a record's ``field_code`` to
a canonical concept is the closed table below; no clinical, laboratory, or
community reviewer has approved it, and it is not a mapping profile in the
B-026 sense. Every value it emits is the source's own token, carried
verbatim: a ``value_code`` of ``CSYN-PRONOUN-THEY-THEM`` becomes a pronouns
value of exactly that string, not ``they/them``. Binding a token to the
value a rule expects is what a mapping profile does (B-026), applied after
this conversion and never inside it; until one is applied, evaluating an
imported observation against a rule that expects the bound value reports
``semantic_mismatch``. That is the correct result: the tool has not been
told the two are the same, so it does not say they are.

What the envelope does not carry is not invented from what it does. Gender
identity needs a code system and recorded sex or gender needs a source; the
envelope has neither field, so both are filled with a fixed token that says
so (``urn:contextsafe:unbound-...``) rather than with a value guessed from
the checkpoint or the case. Name to use needs a ``use``; the contract admits
only ``usual``, so that is what is written, fixed by the contract and not
read from the source. A value from another concept's vocabulary (a
recorded-sex code or a laboratory status) offered as a gender identity, name,
or pronouns value rejects the source rather than arriving as that concept's
value under a foreign token. Sex parameter for clinical use needs a
supporting-observation link the envelope cannot express in one record, so a
record for it rejects the source instead of arriving without the link that
makes it safe to evaluate. Nothing here derives SPCU from any other concept.
"""

from collections.abc import Callable, Mapping
from pathlib import Path

from contextsafe.evidence import BoundaryRecord, parse_evidence_envelope
from contextsafe.importers.base import (
    UNBOUND_CODE_SYSTEM,
    UNBOUND_SOURCE,
    ImportErrorCode,
    ImportResult,
    ImportWarningCode,
    import_error,
)
from contextsafe.mapping_profile import SourceToken
from contextsafe.models import (
    OBSERVATION_SCHEMA_VERSION,
    OBSERVATION_SET_SCHEMA_VERSION,
    Checkpoint,
    ConceptKind,
    EvidencePointer,
    GenderIdentity,
    MappingDescriptor,
    NameToUse,
    Observation,
    Pronouns,
    RecordedSexOrGender,
    SemanticValue,
    SyntheticCase,
    ValueStatus,
)
from contextsafe.plan import SYNTHETIC_VALUE_PREFIX
from contextsafe.preflight import ScannedSource, scan_source
from contextsafe.validation import parse_observations

CANONICAL_JSON_FORMAT = "canonical-json"
"""The ``--format`` name of this importer."""

CANONICAL_JSON_MAPPING_VERSION = "0.1.0"
"""Recorded as ``mapping.mapping_version`` on every observation emitted.

The version of this conversion table, not of a reviewed profile. A change to
the table below, to the unbound tokens, or to the presence rules is a change
to this number.
"""

__all__ = [
    "CANONICAL_JSON_CARRIERS",
    "CANONICAL_JSON_FORMAT",
    "CANONICAL_JSON_IMPORTER",
    "CANONICAL_JSON_MAPPING_VERSION",
    "UNBOUND_CODE_SYSTEM",
    "UNBOUND_SOURCE",
    "CanonicalJsonImporter",
    "convert_scanned",
]

_FIELD_CODE_CONCEPTS: Mapping[str, ConceptKind] = {
    "gender_identity": ConceptKind.GENDER_IDENTITY,
    "name_to_use": ConceptKind.NAME_TO_USE,
    "pronouns": ConceptKind.PRONOUNS,
    "recorded_sex_or_gender": ConceptKind.RECORDED_SEX_OR_GENDER,
    "sex_parameter_for_clinical_use": ConceptKind.SEX_PARAMETER_FOR_CLINICAL_USE,
}
"""The closed field-code mapping. A code outside it rejects the source.

The boundary envelope also admits laboratory field codes (``result``,
``reference_range``, ``abnormal_flag``, ``order``, ``status``). The
observation-set contract has no concept for them, so a source carrying one
is not an observation set with some records left out; it is a source this
importer cannot convert.
"""

_UNCONVERTIBLE_FIELD_CODES = frozenset({"sex_parameter_for_clinical_use"})
"""Field codes this table maps and this importer never converts a record of.

The converter below raises ``import_concept_not_convertible`` for each of
them, so no observation and no source token is ever emitted under one.
"""

CANONICAL_JSON_CARRIERS: Mapping[str, frozenset[ConceptKind]] = {
    code: frozenset({concept})
    for code, concept in _FIELD_CODE_CONCEPTS.items()
    if code not in _UNCONVERTIBLE_FIELD_CODES
}
"""What a mapping profile for this format may name as a carrier: a field code.

Each reads as exactly the concept it names, so a profile row cannot read a
``recorded_sex_or_gender`` record as anything else.
``sex_parameter_for_clinical_use`` is absent for the same reason the FHIR
reader omits the sex-parameter extension URL: the converter always refuses
that record, so this importer emits no token under that carrier and a row
naming it could never match. A table whose purpose is to say what an
importer can emit may not name a carrier it never emits.
"""

_STATUS_CODES: Mapping[str, ValueStatus] = {
    ValueStatus.DECLINED.value: ValueStatus.DECLINED,
    ValueStatus.UNKNOWN.value: ValueStatus.UNKNOWN,
    ValueStatus.ABSENT.value: ValueStatus.ABSENT,
}
"""Value codes that are presence states rather than values."""

_WARNINGS: tuple[ImportWarningCode, ...] = (
    ImportWarningCode.MAPPING_PROFILE_NOT_BOUND,
    ImportWarningCode.PLAN_BINDING_NOT_CHECKED,
)
"""Every conversion this importer makes carries both limits."""


def _presence(record: BoundaryRecord, path: str) -> tuple[ValueStatus, str | None]:
    """Type a status-bearing record without guessing what null means.

    ``declined``, ``unknown``, and ``absent`` are presence states and carry
    no value. A null value code is none of those: the source did not say,
    and the importer does not say for it. A value code of ``specified`` is
    a claim that a value exists without the value, which is ambiguous in
    the same way. A synthetic token (``CSYN-...``) is the value, verbatim.

    Anything else the envelope admits is a code from another concept's
    vocabulary: the recorded-sex-or-gender codes and the laboratory status
    codes. Carrying one of those into a gender identity, name, or pronouns
    value would let a sex code arrive as a gender identity with nothing but
    the token to show for it, which is the substitution the concept
    separation rule forbids, so the record rejects the source instead.
    """

    code = record.value_code
    if code is None:
        raise import_error(
            ImportErrorCode.VALUE_MISSING,
            f"{path}.value_code",
            "a record without a value code is not typed; absence is not a value",
        )
    status = _STATUS_CODES.get(code)
    if status is not None:
        return status, None
    if code == ValueStatus.SPECIFIED.value:
        raise import_error(
            ImportErrorCode.VALUE_AMBIGUOUS,
            f"{path}.value_code",
            "a record that says specified must carry the value itself",
        )
    if not code.startswith(SYNTHETIC_VALUE_PREFIX):
        raise import_error(
            ImportErrorCode.CONCEPT_NOT_CONVERTIBLE,
            f"{path}.value_code",
            "value code belongs to another concept's vocabulary; a presence-bearing "
            "concept carries a presence state or a synthetic token",
        )
    return ValueStatus.SPECIFIED, code


def _required_value(record: BoundaryRecord, path: str) -> str:
    if record.value_code is None:
        raise import_error(
            ImportErrorCode.VALUE_MISSING,
            f"{path}.value_code",
            "a record without a value code is not typed; absence is not a value",
        )
    return record.value_code


def _required_context(record: BoundaryRecord, path: str) -> str:
    if record.context_code is None:
        raise import_error(
            ImportErrorCode.CONTEXT_MISSING,
            f"{path}.context_code",
            "this concept is defined by its context and the record has none",
        )
    return record.context_code


def _gender_identity(record: BoundaryRecord, path: str) -> SemanticValue:
    status, value = _presence(record, path)
    return GenderIdentity(status=status, value=value, code_system=UNBOUND_CODE_SYSTEM)


def _name_to_use(record: BoundaryRecord, path: str) -> SemanticValue:
    # ``use`` is fixed by the observation contract, which admits only
    # ``usual``; the envelope carries no name-use field and none is read.
    status, value = _presence(record, path)
    return NameToUse(status=status, value=value, use="usual")


def _pronouns(record: BoundaryRecord, path: str) -> SemanticValue:
    status, value = _presence(record, path)
    return Pronouns(status=status, value=value)


def _recorded_sex_or_gender(record: BoundaryRecord, path: str) -> SemanticValue:
    return RecordedSexOrGender(
        value=_required_value(record, path),
        context=_required_context(record, path),
        source=UNBOUND_SOURCE,
    )


def _sex_parameter_for_clinical_use(
    _record: BoundaryRecord, path: str
) -> SemanticValue:
    raise import_error(
        ImportErrorCode.CONCEPT_NOT_CONVERTIBLE,
        f"{path}.field_code",
        "sex parameter for clinical use needs a supporting-observation link "
        "the canonical envelope does not carry; a mapping profile must bind it",
    )


_CONVERTERS: Mapping[ConceptKind, Callable[[BoundaryRecord, str], SemanticValue]] = {
    ConceptKind.GENDER_IDENTITY: _gender_identity,
    ConceptKind.NAME_TO_USE: _name_to_use,
    ConceptKind.PRONOUNS: _pronouns,
    ConceptKind.RECORDED_SEX_OR_GENDER: _recorded_sex_or_gender,
    ConceptKind.SEX_PARAMETER_FOR_CLINICAL_USE: _sex_parameter_for_clinical_use,
}


def _concept(field_code: str, path: str) -> ConceptKind:
    concept = _FIELD_CODE_CONCEPTS.get(field_code)
    if concept is None:
        raise import_error(
            ImportErrorCode.FIELD_CODE_UNMAPPED,
            f"{path}.field_code",
            "field code has no entry in the closed concept mapping",
        )
    return concept


def _observation(
    record: BoundaryRecord,
    index: int,
    *,
    case_id: str,
    checkpoint: Checkpoint,
    source_sha256: str,
) -> Observation:
    path = f"$.records[{index}]"
    concept = _concept(record.field_code, path)
    return Observation(
        schema_version=OBSERVATION_SCHEMA_VERSION,
        observation_id=f"OBS-{case_id}-R{index:04d}",
        case_id=case_id,
        checkpoint=checkpoint,
        concept=concept,
        value=_CONVERTERS[concept](record, path),
        evidence=EvidencePointer(
            source_sha256=source_sha256, source_pointer=record.source_pointer
        ),
        mapping=MappingDescriptor(
            source_concept=concept,
            target_concept=concept,
            mapping_version=CANONICAL_JSON_MAPPING_VERSION,
        ),
    )


def convert_scanned(
    scanned: ScannedSource, *, case: SyntheticCase, checkpoint: Checkpoint
) -> ImportResult:
    """Convert an already boundary-scanned source against a case document.

    The envelope is parsed structurally, cross-checked against the case
    document the caller holds and the checkpoint the caller asked for, and
    converted one record to one observation. The converted document is then
    re-validated by the observation contract itself, so a value this table
    typed and the contract rejects (a non-synthetic name, an unsupported RSG
    value, an over-long context) rejects the source with the contract's own
    code. The plan ID the envelope carries is checked for shape only.
    """

    envelope = parse_evidence_envelope(scanned.value)
    if (
        envelope.case_token != case.synthetic_identifier.value
        or envelope.identifier_system != case.synthetic_identifier.system
        or envelope.case_token != f"{SYNTHETIC_VALUE_PREFIX}{case.case_id}"
    ):
        raise import_error(
            ImportErrorCode.CASE_MISMATCH,
            "$.case_token",
            "source case token and identifier must match the case document",
        )
    if envelope.checkpoint is not checkpoint:
        raise import_error(
            ImportErrorCode.CHECKPOINT_MISMATCH,
            "$.checkpoint",
            "source checkpoint must match the requested checkpoint",
        )
    converted = tuple(
        _observation(
            record,
            index,
            case_id=case.case_id,
            checkpoint=checkpoint,
            source_sha256=scanned.raw_sha256,
        )
        for index, record in enumerate(envelope.records)
    )
    # A record that converted carried a value code; the carrier is its field
    # code and the token is that code, verbatim, before any profile binds it.
    tokens = tuple(
        SourceToken(
            concept=item.concept,
            carrier=record.field_code,
            token=_required_value(record, f"$.records[{index}]"),
        )
        for index, (record, item) in enumerate(
            zip(envelope.records, converted, strict=True)
        )
    )
    validated = parse_observations(
        {
            "observations": [item.to_dict() for item in converted],
            "schema_version": OBSERVATION_SET_SCHEMA_VERSION,
        }
    )
    return ImportResult(
        format_name=CANONICAL_JSON_FORMAT,
        mapping_version=CANONICAL_JSON_MAPPING_VERSION,
        source_sha256=scanned.raw_sha256,
        source_byte_count=scanned.raw_byte_count,
        record_count=len(envelope.records),
        observations=validated,
        warnings=_WARNINGS,
        source_tokens=tokens,
    )


class CanonicalJsonImporter:
    """The registered importer for ``contextsafe.evidence-source/1.0.0``."""

    @property
    def format_name(self) -> str:
        return CANONICAL_JSON_FORMAT

    @property
    def mapping_version(self) -> str:
        return CANONICAL_JSON_MAPPING_VERSION

    @property
    def carriers(self) -> Mapping[str, frozenset[ConceptKind]]:
        return CANONICAL_JSON_CARRIERS

    def convert(
        self, source: Path, *, case: SyntheticCase, checkpoint: Checkpoint
    ) -> ImportResult:
        """Scan ``source`` through the evidence boundary, then convert it."""

        return convert_scanned(scan_source(source), case=case, checkpoint=checkpoint)


CANONICAL_JSON_IMPORTER = CanonicalJsonImporter()
