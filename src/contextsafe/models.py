"""Typed, versioned domain models that keep Gender Harmony concepts distinct."""

from dataclasses import dataclass
from enum import StrEnum

from contextsafe.canonical import JsonValue
from contextsafe.errors import ContextSafeError

CASE_SCHEMA_VERSION = "contextsafe.case/0.1.0"
OBSERVATION_SCHEMA_VERSION = "contextsafe.observation/0.1.0"
OBSERVATION_SET_SCHEMA_VERSION = "contextsafe.observation-set/0.1.0"
RULE_SET_SCHEMA_VERSION = "contextsafe.rule-set/0.1.0"
RECEIPT_SCHEMA_VERSION = "contextsafe.receipt/0.1.0"
RECEIPT_DOCUMENT_SCHEMA_VERSION = "contextsafe.receipt-document/0.1.0"


class ConceptKind(StrEnum):
    """Canonical concepts that may never substitute for one another."""

    GENDER_IDENTITY = "gender_identity"
    RECORDED_SEX_OR_GENDER = "recorded_sex_or_gender"
    SEX_PARAMETER_FOR_CLINICAL_USE = "sex_parameter_for_clinical_use"
    NAME_TO_USE = "name_to_use"
    PRONOUNS = "pronouns"


class ValueStatus(StrEnum):
    """Presence semantics for identity and person-specified values."""

    SPECIFIED = "specified"
    DECLINED = "declined"
    UNKNOWN = "unknown"
    ABSENT = "absent"


class Checkpoint(StrEnum):
    """Observed boundaries in the bounded reference workflow."""

    REGISTRATION = "registration"
    EHR = "ehr"
    INTERFACE = "interface"
    LIS_RETURN = "lis_return"


class OutcomeStatus(StrEnum):
    """V1 status algebra; this slice emits pass, fail, or indeterminate."""

    PASSED = "pass"
    FAIL = "fail"
    INDETERMINATE = "indeterminate"
    BLOCKED = "blocked"
    NOT_APPLICABLE = "not_applicable"


class OutcomeReason(StrEnum):
    """The closed set of reason codes a receipt outcome may publish.

    The published receipt contract repeats this set, so an unreviewed reason
    string cannot reach a receipt without a schema change.
    """

    AFFIRMATIVE_EVIDENCE_MATCH = "affirmative_evidence_match"
    AMBIGUOUS_EVIDENCE = "ambiguous_evidence"
    MISSING_EVIDENCE = "missing_evidence"
    PREDECLARED_NOT_APPLICABLE = "predeclared_not_applicable"
    SEMANTIC_MISMATCH = "semantic_mismatch"


@dataclass(frozen=True, slots=True)
class GenderIdentity:
    """A gender identity value with explicit presence semantics."""

    status: ValueStatus
    value: str | None
    code_system: str

    def to_dict(self) -> dict[str, JsonValue]:
        """Return the canonical exchange representation."""

        return {
            "code_system": self.code_system,
            "status": self.status.value,
            "value": self.value,
        }


@dataclass(frozen=True, slots=True)
class RecordedSexOrGender:
    """An administrative recorded sex or gender with source context."""

    value: str
    context: str
    source: str

    def to_dict(self) -> dict[str, JsonValue]:
        """Return the canonical exchange representation."""

        return {"context": self.context, "source": self.source, "value": self.value}


@dataclass(frozen=True, slots=True)
class SexParameterForClinicalUse:
    """A synthetic, contextual SPCU fixture—not a clinical recommendation."""

    value: str
    context_id: str
    supporting_observation_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, JsonValue]:
        """Return the canonical exchange representation."""

        return {
            "context_id": self.context_id,
            "supporting_observation_ids": list(self.supporting_observation_ids),
            "value": self.value,
        }


@dataclass(frozen=True, slots=True)
class NameToUse:
    """A synthetic name-to-use token with explicit HumanName-like use."""

    status: ValueStatus
    value: str | None
    use: str

    def to_dict(self) -> dict[str, JsonValue]:
        """Return the canonical exchange representation."""

        return {"status": self.status.value, "use": self.use, "value": self.value}


@dataclass(frozen=True, slots=True)
class Pronouns:
    """Person-specified pronouns with explicit presence semantics."""

    status: ValueStatus
    value: str | None

    def to_dict(self) -> dict[str, JsonValue]:
        """Return the canonical exchange representation."""

        return {"status": self.status.value, "value": self.value}


type SemanticValue = (
    GenderIdentity
    | RecordedSexOrGender
    | SexParameterForClinicalUse
    | NameToUse
    | Pronouns
)


@dataclass(frozen=True, slots=True)
class SyntheticIdentifier:
    """The fixed ContextSafe synthetic namespace and case token."""

    system: str
    value: str

    def to_dict(self) -> dict[str, JsonValue]:
        """Return the canonical exchange representation."""

        return {"system": self.system, "value": self.value}


@dataclass(frozen=True, slots=True)
class SyntheticCase:
    """A canonical case manifest with separately typed concepts."""

    schema_version: str
    case_id: str
    synthetic_identifier: SyntheticIdentifier
    gender_identity: GenderIdentity
    recorded_sex_or_gender: tuple[RecordedSexOrGender, ...]
    sex_parameter_for_clinical_use: tuple[SexParameterForClinicalUse, ...]
    name_to_use: NameToUse
    pronouns: Pronouns
    prohibited_inferences: tuple[str, ...]

    def to_dict(self) -> dict[str, JsonValue]:
        """Return the canonical exchange representation."""

        return {
            "case_id": self.case_id,
            "concepts": {
                "gender_identity": self.gender_identity.to_dict(),
                "name_to_use": self.name_to_use.to_dict(),
                "pronouns": self.pronouns.to_dict(),
                "recorded_sex_or_gender": [
                    item.to_dict() for item in self.recorded_sex_or_gender
                ],
                "sex_parameter_for_clinical_use": [
                    item.to_dict() for item in self.sex_parameter_for_clinical_use
                ],
            },
            "prohibited_inferences": list(self.prohibited_inferences),
            "schema_version": self.schema_version,
            "synthetic_identifier": self.synthetic_identifier.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class MappingDescriptor:
    """A typed mapping that cannot cross canonical concept boundaries.

    ``profile_sha256`` and ``profile_version`` are the mapping profile
    (B-026) that was applied to the observation, or both ``None`` when none
    was. They are written only when set, so an observation no profile
    touched is byte-identical to what it was before profiles existed, and
    when they are written the evaluator's input hash binds them.
    """

    source_concept: ConceptKind
    target_concept: ConceptKind
    mapping_version: str
    profile_sha256: str | None = None
    profile_version: str | None = None

    def __post_init__(self) -> None:
        if (self.profile_sha256 is None) != (self.profile_version is None):
            raise ContextSafeError(
                "mapping_profile_binding_incomplete",
                "$.mapping",
                "a profile binding carries both profile_sha256 and profile_version",
            )

    def to_dict(self) -> dict[str, JsonValue]:
        """Return the canonical exchange representation."""

        descriptor: dict[str, JsonValue] = {
            "mapping_version": self.mapping_version,
            "source_concept": self.source_concept.value,
            "target_concept": self.target_concept.value,
        }
        if self.profile_sha256 is not None:
            descriptor["profile_sha256"] = self.profile_sha256
            descriptor["profile_version"] = self.profile_version
        return descriptor


@dataclass(frozen=True, slots=True)
class EvidencePointer:
    """A content hash and constrained pointer into synthetic source evidence."""

    source_sha256: str
    source_pointer: str

    def to_dict(self) -> dict[str, JsonValue]:
        """Return the canonical exchange representation."""

        return {
            "source_pointer": self.source_pointer,
            "source_sha256": self.source_sha256,
        }


@dataclass(frozen=True, slots=True)
class Observation:
    """One typed semantic observation at a workflow checkpoint."""

    schema_version: str
    observation_id: str
    case_id: str
    checkpoint: Checkpoint
    concept: ConceptKind
    value: SemanticValue
    evidence: EvidencePointer
    mapping: MappingDescriptor

    def to_dict(self) -> dict[str, JsonValue]:
        """Return the canonical exchange representation."""

        return {
            "case_id": self.case_id,
            "checkpoint": self.checkpoint.value,
            "concept": self.concept.value,
            "evidence": self.evidence.to_dict(),
            "mapping": self.mapping.to_dict(),
            "observation_id": self.observation_id,
            "schema_version": self.schema_version,
            "value": self.value.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class Rule:
    """A pure fixture rule comparing one expected typed semantic value."""

    rule_id: str
    version: str
    case_id: str
    checkpoint: Checkpoint
    concept: ConceptKind
    expected: SemanticValue
    required: bool

    def to_dict(self) -> dict[str, JsonValue]:
        """Return the canonical exchange representation."""

        return {
            "case_id": self.case_id,
            "checkpoint": self.checkpoint.value,
            "concept": self.concept.value,
            "expected": self.expected.to_dict(),
            "required": self.required,
            "rule_id": self.rule_id,
            "version": self.version,
        }


@dataclass(frozen=True, slots=True)
class RuleSet:
    """A versioned collection of deterministic fixture rules."""

    schema_version: str
    rules: tuple[Rule, ...]

    def to_dict(self) -> dict[str, JsonValue]:
        """Return rules in deterministic rule-ID order."""

        return {
            "rules": [
                rule.to_dict() for rule in sorted(self.rules, key=lambda x: x.rule_id)
            ],
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True, slots=True)
class EvaluationBundle:
    """Validated inputs to the pure evaluator."""

    case: SyntheticCase
    observations: tuple[Observation, ...]
    rule_set: RuleSet
