"""Fail-closed validation for the bounded synthetic JSON contracts."""

import re
from collections.abc import Callable
from enum import StrEnum
from typing import cast

from contextsafe.errors import ContextSafeError
from contextsafe.models import (
    CASE_SCHEMA_VERSION,
    OBSERVATION_SCHEMA_VERSION,
    OBSERVATION_SET_SCHEMA_VERSION,
    RULE_SET_SCHEMA_VERSION,
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
    RuleSet,
    SemanticValue,
    SexParameterForClinicalUse,
    SyntheticCase,
    SyntheticIdentifier,
    ValueStatus,
)

_CASE_ID = re.compile(r"^CTP-[A-Z0-9]{3,16}$")
_OBSERVATION_ID = re.compile(r"^OBS-[A-Z0-9-]{3,48}$")
_RULE_ID = re.compile(r"^A-I[0-9]{2}$")
_SEMVER = re.compile(r"^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SOURCE_POINTER = re.compile(r"^\$[.\[\]A-Za-z0-9_-]{1,127}$")
_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9:/_.-]{1,96}$")
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
_RSG_VALUES = frozenset({"F", "M", "X", "unknown"})


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


def _exact_keys(data: dict[str, object], expected: frozenset[str], path: str) -> None:
    unexpected = data.keys() - expected
    if unexpected:
        raise _error("unknown_field", path, "field is not allowed")
    missing = sorted(expected - data.keys())
    if missing:
        raise _error(
            "missing_field", f"{path}.{missing[0]}", "required field is missing"
        )


def _string(value: object, path: str, *, pattern: re.Pattern[str] | None = None) -> str:
    if not isinstance(value, str) or not value or len(value) > 128:
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


def _nullable_string(value: object, path: str) -> str | None:
    if value is None:
        return None
    return _string(value, path)


def _boolean(value: object, path: str) -> bool:
    if not isinstance(value, bool):
        raise _error("invalid_type", path, "expected a boolean")
    return value


def _enum[T: StrEnum](enum_type: type[T], value: object, path: str) -> T:
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
    if rsg_value not in _RSG_VALUES:
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
    if not context_id.startswith("ORDER-CSYN-"):
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
    if not support or any(not item.startswith("SUP-CSYN-") for item in support):
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
    if semantic_value is not None and not semantic_value.startswith("CSYN-"):
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


def _mapping(value: object, path: str, concept: ConceptKind) -> MappingDescriptor:
    data = _object(value, path)
    _exact_keys(
        data,
        frozenset({"source_concept", "target_concept", "mapping_version"}),
        path,
    )
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
    )


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
        source_pointer=_string(
            evidence_data["source_pointer"],
            f"{path}.evidence.source_pointer",
            pattern=_SOURCE_POINTER,
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


def _rule(value: object, path: str) -> Rule:
    data = _object(value, path)
    _exact_keys(
        data,
        frozenset(
            {
                "rule_id",
                "version",
                "case_id",
                "checkpoint",
                "concept",
                "expected",
                "required",
            }
        ),
        path,
    )
    concept = _enum(ConceptKind, data["concept"], f"{path}.concept")
    return Rule(
        rule_id=_string(data["rule_id"], f"{path}.rule_id", pattern=_RULE_ID),
        version=_string(data["version"], f"{path}.version", pattern=_SEMVER),
        case_id=_string(data["case_id"], f"{path}.case_id", pattern=_CASE_ID),
        checkpoint=_enum(Checkpoint, data["checkpoint"], f"{path}.checkpoint"),
        concept=concept,
        expected=_semantic_value(concept, data["expected"], f"{path}.expected"),
        required=_boolean(data["required"], f"{path}.required"),
    )


def parse_rule_set(value: object) -> RuleSet:
    """Validate and parse a deterministic fixture rule set."""

    _reject_prohibited_fields(value)
    data = _object(value, "$")
    _exact_keys(data, frozenset({"schema_version", "rules"}), "$")
    schema_version = _string(data["schema_version"], "$.schema_version")
    if schema_version != RULE_SET_SCHEMA_VERSION:
        raise _error(
            "unsupported_schema", "$.schema_version", "rule-set schema is unsupported"
        )
    rules = tuple(
        _rule(item, f"$.rules[{index}]")
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
        if rule.expected not in case_values[rule.concept]:
            raise _error(
                "rule_expectation_mismatch",
                f"$.rules[{index}].expected",
                "rule expectation must be declared by the case manifest",
            )
    return EvaluationBundle(case=case, observations=observations, rule_set=rule_set)
