"""Fail-closed validation for the bounded synthetic JSON contracts."""

import re
from collections.abc import Callable
from enum import StrEnum
from typing import TypeVar, cast

from contextsafe.errors import ContextSafeError
from contextsafe.models import (
    CASE_SCHEMA_VERSION,
    OBSERVATION_SCHEMA_VERSION,
    OBSERVATION_SET_SCHEMA_VERSION,
    RULE_SET_SCHEMA_VERSION,
    SUPPORTED_RULE_SET_SCHEMA_VERSIONS,
    Checkpoint,
    ConceptKind,
    EvaluationBundle,
    EvidencePointer,
    GenderIdentity,
    MappingDescriptor,
    NameToUse,
    Observation,
    Pronouns,
    RecordedSexOrGender,
    Rule,
    RulePredicate,
    RuleSet,
    SemanticValue,
    SexParameterForClinicalUse,
    SyntheticCase,
    SyntheticIdentifier,
    ValueStatus,
    coercion_key,
)

_CASE_ID = re.compile(r"^CTP-[A-Z0-9]{3,16}$")
_OBSERVATION_ID = re.compile(r"^OBS-[A-Z0-9-]{3,48}$")
_RULE_ID = re.compile(r"^A-I[0-9]{2}$")
_SEMVER = re.compile(r"^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
MAX_STRING_LENGTH = 128
"""Characters any string this validator accepts may carry.

Every string reaching `_string` is held to this, whatever field it is, so it
is the bound a published contract has to state for a field whose own grammar
is looser. The source pointer is that field: `_SOURCE_POINTER` bounds the
RFC 6901 dialect by depth and not by length, and this is what stops a
sixteen-token pointer of the longest vocabulary word -- 496 characters -- from
being accepted anyway.
"""
SOURCE_POINTER_MAX_LENGTH = 128
"""Characters a ``$``-rooted source pointer may carry, the root included.

Named because the published receipt contract has to state the same bound and
stated a different one: `schemas/contextsafe-receipt-v0.3.schema.json` carried
``maxLength: 160`` while this pattern stopped at 128, so a 129-character path
of nothing but vocabulary words validated against the published contract and
was refused here (#72). Separate from `MAX_STRING_LENGTH` because they are two
bounds that happen to be equal, not one bound named twice: moving the bound on
strings in general should not silently rewrite the pointer grammar. The
published bound for the field is the smaller of the two, and
`tools/pattern_gate.py` derives it that way.
"""
JSON_POINTER_MAX_SEGMENTS = 16
"""Reference tokens an RFC 6901 source pointer may carry.

The RFC 6901 dialect is bounded by its depth rather than by its length, so a
published contract has to state both this and a length: neither implies the
other, and seventeen ``/0`` tokens are 34 characters.
"""
_SEGMENT_INDEX = r"(?:0|[1-9][0-9]*)"
"""A pointer's array index: a non-negative integer without a leading zero."""
_HL7_SEGMENT_NAME = r"[A-Z][A-Z0-9]{2}"
"""An HL7 v2 segment name's shape, before the vocabulary is applied to it."""
_SOURCE_POINTER = re.compile(
    rf"^(?:\$[.\[\]A-Za-z0-9_-]{{1,{SOURCE_POINTER_MAX_LENGTH - 1}}}"
    rf"|(?:/[A-Za-z0-9_.-]+){{1,{JSON_POINTER_MAX_SEGMENTS}}})$"
)
"""Where in its source an observation was read from: the alphabet.

Two grammars, one field. The first is the ``$``-rooted path every ContextSafe
document has always used; the HL7 v2 reader (B-024) writes its
``$.SEG[n]-field.rep.comp`` pointers in it. The second is an RFC 6901 JSON
Pointer, which is how a FHIR document names an element; it is admitted since
the FHIR R4 reader (B-023) with unescaped alphanumeric reference tokens only,
because every element name the reader accepts is one, and at most sixteen
deep. Both are structural: neither can carry a value from the source. This
pattern bounds the alphabet; ``_structural_pointer`` bounds the words.
"""
_POINTER_SEGMENT = re.compile(r"\.([A-Za-z0-9_-]+)|\[(0|[1-9][0-9]*)\]")
_HL7_POINTER = re.compile(
    rf"^\$\.({_HL7_SEGMENT_NAME})\[{_SEGMENT_INDEX}\]-{_SEGMENT_INDEX}"
    rf"\.{_SEGMENT_INDEX}\.{_SEGMENT_INDEX}$"
)
_POINTER_INDEX = re.compile(rf"^{_SEGMENT_INDEX}$")
STRUCTURAL_POINTER_SEGMENTS: frozenset[str] = frozenset(
    {
        # the canonical case manifest and the canonical JSON evidence envelope
        "concepts",
        "gender_identity",
        "recorded_sex_or_gender",
        "sex_parameter_for_clinical_use",
        "name_to_use",
        "pronouns",
        "status",
        "value",
        "code_system",
        "context",
        "source",
        "context_id",
        "supporting_observation_ids",
        "use",
        "records",
        "field_code",
        "value_code",
        "context_code",
        # the FHIR R4 reader (B-023): the element names on the path to a carrier
        "entry",
        "resource",
        "name",
        "extension",
        # the HL7 v2 ER7 reader (B-024): its segment allowlist
        "MSH",
        "PID",
        "GSP",
        "OBR",
        "OBX",
        # the LIS export readers (B-025): the row array and the identity columns
        "rows",
        "sex",
    }
)
"""The closed vocabulary a source pointer may be built from (B-031, A-035).

A pointer names where in a source a value was read, and the receipt trace
carries it verbatim, so it must be a structural path and nothing else. Three
dialects are admitted, each over this one vocabulary: the ``$``-rooted path of
the canonical case manifest, the canonical JSON evidence envelope, and the LIS
export readers, joined by ``.`` and indexed by ``[n]``; the RFC 6901 JSON
Pointer the FHIR R4 reader emits, whose reference tokens are element names or
indices; and the HL7 v2 reader's ``$.SEG[n]-field.rep.comp``, whose only word
is the segment name. A word outside this set is free text where none is
allowed, and the whole observation set is refused rather than the segment
being carried, hashed, or dropped. A source profile that needs more names
extends this set under review, not by widening a grammar.
"""
SYNTHETIC_NAME_PREFIX = "CSYN-"
"""The prefix a name to use must carry, and the whole of what a pattern can say.

Every published contract that carries a name-to-use value states this prefix
and nothing more, because the rest of the rule is not writable as a regular
expression: the boundary scan in `contextsafe.identifiers` is what refuses
``CSYN-Jordan Rivera 555-01-0199``, and #58 is what that costs when the prefix
is mistaken for the grammar. Named so `tools/pattern_gate.py` can hold the four
published ``^CSYN-`` patterns to the constant this validator actually applies.
"""
_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9:/_.-]{1,96}$")
_ORDER_CONTEXT_TOKEN = re.compile(r"^ORDER-CSYN-[A-Za-z0-9:/_.-]+$")
_SUPPORT_OBSERVATION_TOKEN = re.compile(r"^SUP-CSYN-[A-Za-z0-9:/_.-]+$")
_PROHIBITED_KEYS = frozenset(
    {
        "address",
        "birth_date",
        "contained",
        "date_of_birth",
        "diagnosis",
        "email",
        "free_text",
        "legal_name",
        "medical_record_number",
        "mrn",
        "narrative",
        "note",
        "phone",
        "ssn",
        "telecom",
        "text",
    }
)
_REQUIRED_INFERENCES = frozenset(
    {"gender_identity_to_spcu", "recorded_sex_or_gender_to_spcu"}
)
_PROFILE_BINDING_KEYS = frozenset({"profile_sha256", "profile_version"})
"""The optional pair on an observation's mapping block naming its profile (B-026)."""
RSG_VALUES = frozenset({"F", "M", "X", "unknown"})
"""The closed recorded-sex-or-gender alphabet this contract admits.

Public so that a reader can refuse a value outside it at the source's own
location before conversion, instead of the converted document being rejected
here at a path the source never had. The set is the contract's, not the
reader's: nothing else may extend it, and nothing maps a value into it.
"""
_RULE_KEYS = frozenset(
    {"rule_id", "version", "case_id", "checkpoint", "concept", "expected", "required"}
)
_PREDICATE_FIELDS: dict[RulePredicate, frozenset[str]] = {
    RulePredicate.EXACT: frozenset(),
    RulePredicate.PRESENT: frozenset(),
    RulePredicate.STATUS_PRESERVED: frozenset(),
    RulePredicate.NOT_COERCED: frozenset({"forbidden"}),
    RulePredicate.RECORD_COUNT: frozenset({"expected_count"}),
    RulePredicate.PRESERVED_ACROSS: frozenset({"preserved_from"}),
    RulePredicate.NOT_OVERWRITTEN_BY: frozenset(),
}
"""The one field each predicate reads; any other predicate field is unknown."""
_STATUS_CONCEPTS = frozenset(
    {ConceptKind.GENDER_IDENTITY, ConceptKind.NAME_TO_USE, ConceptKind.PRONOUNS}
)
"""Concepts whose values carry presence semantics (a ``status``)."""
_PREDICATE_CONCEPTS: dict[RulePredicate, frozenset[ConceptKind]] = {
    RulePredicate.PRESENT: _STATUS_CONCEPTS,
    RulePredicate.STATUS_PRESERVED: _STATUS_CONCEPTS,
    RulePredicate.NOT_OVERWRITTEN_BY: frozenset({ConceptKind.GENDER_IDENTITY}),
}
"""Predicates that are only meaningful for some concepts.

``present`` and ``status_preserved`` on a concept with no status would pass on
every observation, and A-011 is a claim about gender identity. A rule that
would be vacuously true is rejected rather than allowed to look like evidence.
"""
_MAX_FORBIDDEN = 16
_MAX_EXPECTED_COUNT = 64


def _error(code: str, path: str, message: str) -> ContextSafeError:
    return ContextSafeError(code=code, path=path, message=message)


def _object(value: object, path: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise _error("invalid_type", path, "expected a JSON object")
    return cast(dict[str, object], value)


def _array(value: object, path: str) -> list[object]:
    if not isinstance(value, list):
        raise _error("invalid_type", path, "expected a JSON array")
    return cast(list[object], value)


def _exact_keys(
    data: dict[str, object],
    expected: frozenset[str],
    path: str,
    *,
    optional: frozenset[str] = frozenset(),
) -> None:
    unexpected = data.keys() - expected - optional
    if unexpected:
        raise _error("unknown_field", path, "field is not allowed")
    missing = sorted(expected - data.keys())
    if missing:
        raise _error(
            "missing_field", f"{path}.{missing[0]}", "required field is missing"
        )


def _string(value: object, path: str, *, pattern: re.Pattern[str] | None = None) -> str:
    if not isinstance(value, str) or not value or len(value) > MAX_STRING_LENGTH:
        raise _error("invalid_string", path, "expected a bounded non-empty string")
    if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
        raise _error(
            "invalid_unicode", path, "string must contain only Unicode scalar values"
        )
    if pattern is not None and pattern.fullmatch(value) is None:
        raise _error(
            "invalid_format", path, "string does not match the required format"
        )
    return value


def _structural_pointer(value: object, path: str) -> str:
    """Return a source pointer built only from structural segments.

    ``_SOURCE_POINTER`` bounds the alphabet; this bounds the words, in whichever
    of the three dialects the pointer is written. ``$`` alone is not a location,
    so at least one segment is required, and the segments must account for
    every character after the root.
    """

    pointer = _string(value, path, pattern=_SOURCE_POINTER)
    if pointer.startswith("/"):
        structural = all(
            _POINTER_INDEX.fullmatch(token) is not None
            or token in STRUCTURAL_POINTER_SEGMENTS
            for token in pointer[1:].split("/")
        )
    elif (hl7 := _HL7_POINTER.fullmatch(pointer)) is not None:
        structural = hl7.group(1) in STRUCTURAL_POINTER_SEGMENTS
    else:
        structural = _walks_the_vocabulary(pointer[1:])
    if not structural:
        raise _error(
            "non_structural_pointer",
            path,
            "source pointer must be a path of structural segments only",
        )
    return pointer


def _walks_the_vocabulary(body: str) -> bool:
    """True when ``body`` is wholly ``.word`` and ``[n]`` segments over the set."""

    position = 0
    for match in _POINTER_SEGMENT.finditer(body):
        if match.start() != position:
            return False
        name = match.group(1)
        if name is not None and name not in STRUCTURAL_POINTER_SEGMENTS:
            return False
        position = match.end()
    return position == len(body)


def _nullable_string(value: object, path: str) -> str | None:
    if value is None:
        return None
    return _string(value, path)


_EnumT = TypeVar("_EnumT", bound=StrEnum)
"""The enum a parsed value is narrowed to.

Written as a ``TypeVar`` rather than in PEP 695 form. The SAST gate's parser
does not read ``def _enum[T: StrEnum](...)``: it stops at that line and reports
the rest of this module as "partially analyzed", so the scanner was passing
over a safety module it had not finished reading. A gate that reports clean
over content it did not examine is the defect class docs/18-ASSURANCE-PROGRAM.md
exists to name, so the syntax gives way to the scanner rather than the other
way round.
"""


def _boolean(value: object, path: str) -> bool:
    if not isinstance(value, bool):
        raise _error("invalid_type", path, "expected a boolean")
    return value


def _enum(enum_type: type[_EnumT], value: object, path: str) -> _EnumT:
    if not isinstance(value, str):
        raise _error("invalid_enum", path, "expected a supported string value")
    try:
        return enum_type(value)
    except ValueError as exc:
        raise _error("invalid_enum", path, "value is not supported") from exc


def _reject_prohibited_fields(value: object) -> None:
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            for raw_key, child in item.items():
                if isinstance(raw_key, str):
                    normalized = raw_key.lower().replace("-", "_")
                    if normalized in _PROHIBITED_KEYS:
                        raise _error(
                            "prohibited_field",
                            "$",
                            "prohibited free-text or identifying field",
                        )
                pending.append(child)
        elif isinstance(item, list):
            pending.extend(item)


def _status_value(
    data: dict[str, object], path: str, expected: frozenset[str]
) -> tuple[ValueStatus, str | None]:
    _exact_keys(data, expected, path)
    status = _enum(ValueStatus, data["status"], f"{path}.status")
    value = _nullable_string(data["value"], f"{path}.value")
    if (status is ValueStatus.SPECIFIED) != (value is not None):
        raise _error(
            "invalid_presence_semantics",
            path,
            "specified requires a value and every other status requires null",
        )
    return status, value


def _gender_identity(value: object, path: str) -> GenderIdentity:
    data = _object(value, path)
    status, semantic_value = _status_value(
        data, path, frozenset({"status", "value", "code_system"})
    )
    code_system = _string(
        data["code_system"], f"{path}.code_system", pattern=_SAFE_TOKEN
    )
    return GenderIdentity(status=status, value=semantic_value, code_system=code_system)


def _recorded_sex_or_gender(value: object, path: str) -> RecordedSexOrGender:
    data = _object(value, path)
    _exact_keys(data, frozenset({"value", "context", "source"}), path)
    rsg_value = _string(data["value"], f"{path}.value")
    if rsg_value not in RSG_VALUES:
        raise _error("invalid_rsg_value", f"{path}.value", "value is not supported")
    return RecordedSexOrGender(
        value=rsg_value,
        context=_string(data["context"], f"{path}.context", pattern=_SAFE_TOKEN),
        source=_string(data["source"], f"{path}.source", pattern=_SAFE_TOKEN),
    )


def _spcu(value: object, path: str) -> SexParameterForClinicalUse:
    data = _object(value, path)
    _exact_keys(
        data,
        frozenset({"value", "context_id", "supporting_observation_ids"}),
        path,
    )
    context_id = _string(data["context_id"], f"{path}.context_id", pattern=_SAFE_TOKEN)
    if _ORDER_CONTEXT_TOKEN.fullmatch(context_id) is None:
        raise _error(
            "non_synthetic_context",
            f"{path}.context_id",
            "SPCU context must use the synthetic order namespace",
        )
    support_raw = _array(
        data["supporting_observation_ids"], f"{path}.supporting_observation_ids"
    )
    support = tuple(
        _string(
            item, f"{path}.supporting_observation_ids[{index}]", pattern=_SAFE_TOKEN
        )
        for index, item in enumerate(support_raw)
    )
    if not support or any(
        _SUPPORT_OBSERVATION_TOKEN.fullmatch(item) is None for item in support
    ):
        raise _error(
            "invalid_support",
            f"{path}.supporting_observation_ids",
            "SPCU requires synthetic supporting-observation tokens",
        )
    return SexParameterForClinicalUse(
        value=_string(data["value"], f"{path}.value", pattern=_SAFE_TOKEN),
        context_id=context_id,
        supporting_observation_ids=support,
    )


def _name_to_use(value: object, path: str) -> NameToUse:
    data = _object(value, path)
    status, semantic_value = _status_value(
        data, path, frozenset({"status", "value", "use"})
    )
    use = _string(data["use"], f"{path}.use")
    if use != "usual":
        raise _error(
            "invalid_name_use", f"{path}.use", "name-to-use must have usual use"
        )
    if semantic_value is not None and not semantic_value.startswith(
        SYNTHETIC_NAME_PREFIX
    ):
        raise _error(
            "non_synthetic_name",
            f"{path}.value",
            "name-to-use must use a synthetic token",
        )
    return NameToUse(status=status, value=semantic_value, use=use)


def _pronouns(value: object, path: str) -> Pronouns:
    data = _object(value, path)
    status, semantic_value = _status_value(data, path, frozenset({"status", "value"}))
    return Pronouns(status=status, value=semantic_value)


_SEMANTIC_PARSERS: dict[ConceptKind, Callable[[object, str], SemanticValue]] = {
    ConceptKind.GENDER_IDENTITY: _gender_identity,
    ConceptKind.RECORDED_SEX_OR_GENDER: _recorded_sex_or_gender,
    ConceptKind.SEX_PARAMETER_FOR_CLINICAL_USE: _spcu,
    ConceptKind.NAME_TO_USE: _name_to_use,
    ConceptKind.PRONOUNS: _pronouns,
}


def _semantic_value(concept: ConceptKind, value: object, path: str) -> SemanticValue:
    return _SEMANTIC_PARSERS[concept](value, path)


def parse_semantic_value(
    concept: ConceptKind, value: object, path: str
) -> SemanticValue:
    """Parse one typed canonical value for a previously validated concept."""

    return _semantic_value(concept, value, path)


def parse_case(value: object) -> SyntheticCase:
    """Validate and parse one canonical synthetic case."""

    _reject_prohibited_fields(value)
    data = _object(value, "$")
    _exact_keys(
        data,
        frozenset(
            {
                "schema_version",
                "case_id",
                "synthetic_identifier",
                "concepts",
                "prohibited_inferences",
            }
        ),
        "$",
    )
    schema_version = _string(data["schema_version"], "$.schema_version")
    if schema_version != CASE_SCHEMA_VERSION:
        raise _error(
            "unsupported_schema", "$.schema_version", "case schema is unsupported"
        )
    case_id = _string(data["case_id"], "$.case_id", pattern=_CASE_ID)
    identifier_data = _object(data["synthetic_identifier"], "$.synthetic_identifier")
    _exact_keys(
        identifier_data, frozenset({"system", "value"}), "$.synthetic_identifier"
    )
    identifier = SyntheticIdentifier(
        system=_string(identifier_data["system"], "$.synthetic_identifier.system"),
        value=_string(identifier_data["value"], "$.synthetic_identifier.value"),
    )
    if (
        identifier.system != "urn:contextsafe:synthetic"
        or identifier.value != f"CSYN-{case_id}"
    ):
        raise _error(
            "invalid_synthetic_identifier",
            "$.synthetic_identifier",
            "identifier must match the ContextSafe synthetic case namespace",
        )
    concepts = _object(data["concepts"], "$.concepts")
    _exact_keys(concepts, frozenset(item.value for item in ConceptKind), "$.concepts")
    rsg_values = _array(
        concepts[ConceptKind.RECORDED_SEX_OR_GENDER.value],
        "$.concepts.recorded_sex_or_gender",
    )
    spcu_values = _array(
        concepts[ConceptKind.SEX_PARAMETER_FOR_CLINICAL_USE.value],
        "$.concepts.sex_parameter_for_clinical_use",
    )
    inference_values = tuple(
        _string(item, f"$.prohibited_inferences[{index}]")
        for index, item in enumerate(
            _array(data["prohibited_inferences"], "$.prohibited_inferences")
        )
    )
    if (
        frozenset(inference_values) != _REQUIRED_INFERENCES
        or len(inference_values) != 2
    ):
        raise _error(
            "missing_safety_guard",
            "$.prohibited_inferences",
            "both GI-to-SPCU and RSG-to-SPCU prohibitions are required exactly once",
        )
    return SyntheticCase(
        schema_version=schema_version,
        case_id=case_id,
        synthetic_identifier=identifier,
        gender_identity=_gender_identity(
            concepts[ConceptKind.GENDER_IDENTITY.value], "$.concepts.gender_identity"
        ),
        recorded_sex_or_gender=tuple(
            _recorded_sex_or_gender(item, f"$.concepts.recorded_sex_or_gender[{index}]")
            for index, item in enumerate(rsg_values)
        ),
        sex_parameter_for_clinical_use=tuple(
            _spcu(item, f"$.concepts.sex_parameter_for_clinical_use[{index}]")
            for index, item in enumerate(spcu_values)
        ),
        name_to_use=_name_to_use(
            concepts[ConceptKind.NAME_TO_USE.value], "$.concepts.name_to_use"
        ),
        pronouns=_pronouns(concepts[ConceptKind.PRONOUNS.value], "$.concepts.pronouns"),
        prohibited_inferences=inference_values,
    )


def _profile_binding(
    data: dict[str, object], path: str
) -> tuple[str | None, str | None]:
    """The optional mapping-profile binding: both fields, or neither.

    A digest without a version, or a version without a digest, is a binding
    a reader could not check, so it rejects rather than being read as one.
    """

    present = _PROFILE_BINDING_KEYS & data.keys()
    if not present:
        return None, None
    if present != _PROFILE_BINDING_KEYS:
        raise _error(
            "mapping_profile_binding_incomplete",
            path,
            "a profile binding carries both profile_sha256 and profile_version",
        )
    return (
        _string(data["profile_sha256"], f"{path}.profile_sha256", pattern=_SHA256),
        _string(data["profile_version"], f"{path}.profile_version", pattern=_SEMVER),
    )


def _mapping(value: object, path: str, concept: ConceptKind) -> MappingDescriptor:
    data = _object(value, path)
    _exact_keys(
        data,
        frozenset({"source_concept", "target_concept", "mapping_version"}),
        path,
        optional=_PROFILE_BINDING_KEYS,
    )
    profile_sha256, profile_version = _profile_binding(data, path)
    source = _enum(ConceptKind, data["source_concept"], f"{path}.source_concept")
    target = _enum(ConceptKind, data["target_concept"], f"{path}.target_concept")
    if target is ConceptKind.SEX_PARAMETER_FOR_CLINICAL_USE and source in {
        ConceptKind.GENDER_IDENTITY,
        ConceptKind.RECORDED_SEX_OR_GENDER,
    }:
        raise _error(
            "prohibited_spcu_mapping",
            path,
            "GI and RSG can never be mapped into SPCU",
        )
    if source is not target:
        raise _error(
            "concept_type_mismatch",
            path,
            "canonical concept types cannot be assigned across types",
        )
    if target is not concept:
        raise _error(
            "observation_target_mismatch",
            path,
            "mapping target must match the observation concept",
        )
    return MappingDescriptor(
        source_concept=source,
        target_concept=target,
        mapping_version=_string(
            data["mapping_version"], f"{path}.mapping_version", pattern=_SEMVER
        ),
        profile_sha256=profile_sha256,
        profile_version=profile_version,
    )


def parse_mapping_descriptor(
    value: object, path: str, concept: ConceptKind
) -> MappingDescriptor:
    """Parse a mapping while enforcing concept separation."""

    return _mapping(value, path, concept)


def _observation(value: object, path: str) -> Observation:
    data = _object(value, path)
    _exact_keys(
        data,
        frozenset(
            {
                "schema_version",
                "observation_id",
                "case_id",
                "checkpoint",
                "concept",
                "value",
                "evidence",
                "mapping",
            }
        ),
        path,
    )
    schema_version = _string(data["schema_version"], f"{path}.schema_version")
    if schema_version != OBSERVATION_SCHEMA_VERSION:
        raise _error(
            "unsupported_schema",
            f"{path}.schema_version",
            "observation schema is unsupported",
        )
    concept = _enum(ConceptKind, data["concept"], f"{path}.concept")
    evidence_data = _object(data["evidence"], f"{path}.evidence")
    _exact_keys(
        evidence_data,
        frozenset({"source_sha256", "source_pointer"}),
        f"{path}.evidence",
    )
    evidence = EvidencePointer(
        source_sha256=_string(
            evidence_data["source_sha256"],
            f"{path}.evidence.source_sha256",
            pattern=_SHA256,
        ),
        source_pointer=_structural_pointer(
            evidence_data["source_pointer"], f"{path}.evidence.source_pointer"
        ),
    )
    return Observation(
        schema_version=schema_version,
        observation_id=_string(
            data["observation_id"], f"{path}.observation_id", pattern=_OBSERVATION_ID
        ),
        case_id=_string(data["case_id"], f"{path}.case_id", pattern=_CASE_ID),
        checkpoint=_enum(Checkpoint, data["checkpoint"], f"{path}.checkpoint"),
        concept=concept,
        value=_semantic_value(concept, data["value"], f"{path}.value"),
        evidence=evidence,
        mapping=_mapping(data["mapping"], f"{path}.mapping", concept),
    )


def parse_observations(value: object) -> tuple[Observation, ...]:
    """Validate and parse a versioned canonical observation set."""

    _reject_prohibited_fields(value)
    data = _object(value, "$")
    _exact_keys(data, frozenset({"schema_version", "observations"}), "$")
    schema_version = _string(data["schema_version"], "$.schema_version")
    if schema_version != OBSERVATION_SET_SCHEMA_VERSION:
        raise _error(
            "unsupported_schema",
            "$.schema_version",
            "observation-set schema is unsupported",
        )
    raw_observations = _array(data["observations"], "$.observations")
    observations = tuple(
        _observation(item, f"$.observations[{index}]")
        for index, item in enumerate(raw_observations)
    )
    ids = [item.observation_id for item in observations]
    if len(ids) != len(set(ids)):
        raise _error("duplicate_observation_id", "$.observations", "IDs must be unique")
    return observations


def _rule_keys(
    data: dict[str, object], path: str, *, predicates: bool
) -> RulePredicate:
    """Return the rule's predicate after checking its key set fails closed.

    Under the 0.1.0 shape no predicate key exists at all. Under 0.2.0 the
    predicate is optional and defaults to ``exact``; the field a predicate
    reads is required for that predicate and unknown for every other.
    """

    if not predicates:
        _exact_keys(data, _RULE_KEYS, path)
        return RulePredicate.EXACT
    predicate = RulePredicate.EXACT
    if "predicate" in data:
        predicate = _enum(RulePredicate, data["predicate"], f"{path}.predicate")
    specific = _PREDICATE_FIELDS[predicate]
    unexpected = data.keys() - _RULE_KEYS - {"predicate"} - specific
    if unexpected:
        raise _error("unknown_field", path, "field is not allowed for this predicate")
    missing = sorted((_RULE_KEYS | specific) - data.keys())
    if missing:
        raise _error(
            "missing_field", f"{path}.{missing[0]}", "required field is missing"
        )
    return predicate


def _forbidden(
    data: dict[str, object], path: str, concept: ConceptKind, expected: SemanticValue
) -> tuple[SemanticValue, ...]:
    raw = _array(data["forbidden"], f"{path}.forbidden")
    if not raw or len(raw) > _MAX_FORBIDDEN:
        raise _error(
            "invalid_forbidden_set",
            f"{path}.forbidden",
            f"between 1 and {_MAX_FORBIDDEN} forbidden values are required",
        )
    forbidden = tuple(
        _semantic_value(concept, item, f"{path}.forbidden[{index}]")
        for index, item in enumerate(raw)
    )
    keys = {coercion_key(item) for item in forbidden}
    if len(keys) != len(forbidden):
        raise _error(
            "duplicate_forbidden_value",
            f"{path}.forbidden",
            "values must be distinct in status and scalar",
        )
    if coercion_key(expected) in keys:
        raise _error(
            "forbidden_expected_conflict",
            f"{path}.forbidden",
            "the expected value cannot also be forbidden",
        )
    return forbidden


def _expected_count(data: dict[str, object], path: str) -> int:
    value = data["expected_count"]
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 1 <= value <= _MAX_EXPECTED_COUNT
    ):
        raise _error(
            "invalid_expected_count",
            f"{path}.expected_count",
            f"expected an integer between 1 and {_MAX_EXPECTED_COUNT}",
        )
    return value


def _preserved_from(
    data: dict[str, object], path: str, checkpoint: Checkpoint
) -> Checkpoint:
    preserved_from = _enum(Checkpoint, data["preserved_from"], f"{path}.preserved_from")
    if preserved_from is checkpoint:
        raise _error(
            "invalid_checkpoint_pair",
            f"{path}.preserved_from",
            "preserved_from must name a different checkpoint",
        )
    return preserved_from


def _rule(value: object, path: str, *, predicates: bool) -> Rule:
    data = _object(value, path)
    predicate = _rule_keys(data, path, predicates=predicates)
    concept = _enum(ConceptKind, data["concept"], f"{path}.concept")
    allowed_concepts = _PREDICATE_CONCEPTS.get(predicate)
    if allowed_concepts is not None and concept not in allowed_concepts:
        raise _error(
            "predicate_concept_mismatch",
            f"{path}.predicate",
            "predicate is not defined for this concept",
        )
    checkpoint = _enum(Checkpoint, data["checkpoint"], f"{path}.checkpoint")
    expected = _semantic_value(concept, data["expected"], f"{path}.expected")
    return Rule(
        rule_id=_string(data["rule_id"], f"{path}.rule_id", pattern=_RULE_ID),
        version=_string(data["version"], f"{path}.version", pattern=_SEMVER),
        case_id=_string(data["case_id"], f"{path}.case_id", pattern=_CASE_ID),
        checkpoint=checkpoint,
        concept=concept,
        expected=expected,
        required=_boolean(data["required"], f"{path}.required"),
        predicate=predicate,
        forbidden=(
            _forbidden(data, path, concept, expected)
            if predicate is RulePredicate.NOT_COERCED
            else ()
        ),
        expected_count=(
            _expected_count(data, path)
            if predicate is RulePredicate.RECORD_COUNT
            else None
        ),
        preserved_from=(
            _preserved_from(data, path, checkpoint)
            if predicate is RulePredicate.PRESERVED_ACROSS
            else None
        ),
    )


def parse_rule_set(value: object) -> RuleSet:
    """Validate and parse a deterministic fixture rule set."""

    _reject_prohibited_fields(value)
    data = _object(value, "$")
    _exact_keys(data, frozenset({"schema_version", "rules"}), "$")
    schema_version = _string(data["schema_version"], "$.schema_version")
    if schema_version not in SUPPORTED_RULE_SET_SCHEMA_VERSIONS:
        raise _error(
            "unsupported_schema", "$.schema_version", "rule-set schema is unsupported"
        )
    predicates = schema_version != RULE_SET_SCHEMA_VERSION
    rules = tuple(
        _rule(item, f"$.rules[{index}]", predicates=predicates)
        for index, item in enumerate(_array(data["rules"], "$.rules"))
    )
    ids = [rule.rule_id for rule in rules]
    if not rules:
        raise _error("empty_rule_set", "$.rules", "at least one rule is required")
    if len(ids) != len(set(ids)):
        raise _error("duplicate_rule_id", "$.rules", "IDs must be unique")
    return RuleSet(schema_version=schema_version, rules=rules)


def parse_bundle(
    case_value: object, observation_value: object, rule_value: object
) -> EvaluationBundle:
    """Validate all inputs and their cross-document synthetic-case contract."""

    case = parse_case(case_value)
    observations = parse_observations(observation_value)
    rule_set = parse_rule_set(rule_value)
    if any(item.case_id != case.case_id for item in observations):
        raise _error(
            "case_mismatch",
            "$.observations",
            "every observation must reference the case manifest",
        )
    if any(rule.case_id != case.case_id for rule in rule_set.rules):
        raise _error(
            "case_mismatch", "$.rules", "every rule must reference the case manifest"
        )
    case_values: dict[ConceptKind, tuple[SemanticValue, ...]] = {
        ConceptKind.GENDER_IDENTITY: (case.gender_identity,),
        ConceptKind.RECORDED_SEX_OR_GENDER: case.recorded_sex_or_gender,
        ConceptKind.SEX_PARAMETER_FOR_CLINICAL_USE: (
            case.sex_parameter_for_clinical_use
        ),
        ConceptKind.NAME_TO_USE: (case.name_to_use,),
        ConceptKind.PRONOUNS: (case.pronouns,),
    }
    for index, rule in enumerate(rule_set.rules):
        _check_rule_against_case(rule, case_values, f"$.rules[{index}]")
    return EvaluationBundle(case=case, observations=observations, rule_set=rule_set)


def _check_rule_against_case(
    rule: Rule,
    case_values: dict[ConceptKind, tuple[SemanticValue, ...]],
    path: str,
) -> None:
    """Refuse a rule the case manifest contradicts.

    A rule can only expect what the manifest declares (every predicate), can
    only forbid what the manifest does not declare in status and scalar under
    any context (``not_coerced``), can only demand presence of a value the
    manifest specifies (``present``), can only count records the manifest
    carries as distinct (``record_count``), and can only expect a scalar no
    other concept of the manifest carries (``not_overwritten_by``). Each of
    these would otherwise be a rule that could not pass or could not fail.
    """

    declared = case_values[rule.concept]
    if rule.expected not in declared:
        raise _error(
            "rule_expectation_mismatch",
            f"{path}.expected",
            "rule expectation must be declared by the case manifest",
        )
    declared_keys = {coercion_key(item) for item in declared}
    if any(coercion_key(item) in declared_keys for item in rule.forbidden):
        raise _error(
            "forbidden_case_conflict",
            f"{path}.forbidden",
            "a forbidden value cannot be declared by the case manifest",
        )
    if (
        rule.predicate is RulePredicate.PRESENT
        and getattr(rule.expected, "status", None) is not ValueStatus.SPECIFIED
    ):
        raise _error(
            "predicate_expectation_mismatch",
            f"{path}.expected",
            "present requires an expected value with specified status",
        )
    if rule.expected_count is not None:
        _check_record_count(rule.expected_count, declared, path)
    if rule.predicate is RulePredicate.NOT_OVERWRITTEN_BY:
        _check_overwritten_expectation(rule, case_values, path)


def _check_record_count(
    expected_count: int, declared: tuple[SemanticValue, ...], path: str
) -> None:
    """Refuse a ``record_count`` rule the manifest cannot be observed to meet.

    The predicate demands ``expected_count`` observations with distinct hashes,
    so a manifest that declares the same record twice could only ever be
    reported as ``record_count_changed``; that is a contradiction between the
    rule and the manifest, refused here, not a fault at the boundary.
    """

    if expected_count != len(declared):
        raise _error(
            "rule_count_mismatch",
            f"{path}.expected_count",
            "expected_count must equal the records the case manifest declares",
        )
    if len(set(declared)) != len(declared):
        raise _error(
            "indistinct_declared_records",
            f"{path}.expected_count",
            "record_count needs distinct records in the case manifest",
        )


def _check_overwritten_expectation(
    rule: Rule,
    case_values: dict[ConceptKind, tuple[SemanticValue, ...]],
    path: str,
) -> None:
    """Refuse a ``not_overwritten_by`` rule whose faithful value is ruled out.

    The predicate reports fail when the observed scalar equals a scalar the
    manifest declares under another concept. If the expected scalar itself is
    one of those, a faithful observation fails and the rule can never pass, so
    the manifest and the rule contradict each other and the bundle is refused
    rather than evaluated.
    """

    other_scalars = {
        value.value
        for concept, values in case_values.items()
        if concept is not rule.concept
        for value in values
        if value.value is not None
    }
    if rule.expected.value in other_scalars:
        raise _error(
            "overwritten_expectation_conflict",
            f"{path}.expected",
            "the expected value is declared by another concept of the case manifest",
        )
