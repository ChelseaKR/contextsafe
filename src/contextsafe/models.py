"""Typed, versioned domain models that keep Gender Harmony concepts distinct."""

from dataclasses import dataclass
from enum import StrEnum

from contextsafe.canonical import JsonValue
from contextsafe.errors import ContextSafeError

CASE_SCHEMA_VERSION = "contextsafe.case/0.1.0"
OBSERVATION_SCHEMA_VERSION = "contextsafe.observation/0.1.0"
OBSERVATION_SET_SCHEMA_VERSION = "contextsafe.observation-set/0.1.0"
RULE_SET_SCHEMA_VERSION = "contextsafe.rule-set/0.1.0"
"""The exact-only rule-set shape: every rule compares one expected hash.

Still accepted unchanged, so an existing ``rules.json`` and the pack contract
that pins this version are untouched by the predicate extension below.
"""
PREDICATE_RULE_SET_SCHEMA_VERSION = "contextsafe.rule-set/0.2.0"
"""The rule-set shape that admits a closed ``predicate`` field (B-028).

``exact`` is the default, so a 0.2.0 document with no predicate field means
what a 0.1.0 document means. The predicates are a reference-only, ungoverned
mechanism: no clinical, laboratory, or community review stands behind any
rule that uses them.
"""
SUPPORTED_RULE_SET_SCHEMA_VERSIONS = frozenset(
    {RULE_SET_SCHEMA_VERSION, PREDICATE_RULE_SET_SCHEMA_VERSION}
)
RECEIPT_SCHEMA_VERSION = "contextsafe.receipt/0.3.0"
"""The receipt payload shape.

0.3 adds the first-observed-divergence section and the per-outcome evidence
trace (B-031, A-034 and A-035) and changes nothing that 0.2 carried.
"""
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
    """Observed boundaries in the bounded reference workflow.

    Declared in pathway order: a value enters at registration, is stored in
    the EHR, crosses the interface, and returns from the laboratory. The
    first-observed-divergence computation walks members in this order.
    """

    REGISTRATION = "registration"
    EHR = "ehr"
    INTERFACE = "interface"
    LIS_RETURN = "lis_return"


PATHWAY: tuple[Checkpoint, ...] = tuple(Checkpoint)
"""The checkpoints in pathway order, which is their declaration order."""


class EvidenceState(StrEnum):
    """What the observation set holds for one concept at one checkpoint.

    ``unobserved`` is the absence of evidence and nothing more: it is never
    agreement, never divergence, and never blamed (A-032, A-034).
    """

    OBSERVED = "observed"
    """Evidence that reads as one state of the concept at this boundary."""

    UNOBSERVED = "unobserved"
    """No observation at this boundary; nothing is known about it."""

    AMBIGUOUS = "ambiguous"
    """Evidence that cannot be read as one state: more than one observation
    of a single-valued concept, or the same record captured twice."""


class DivergenceStatus(StrEnum):
    """The closed set of things a divergence entry may say (A-034).

    A divergence is located only at an observed boundary. An unobserved
    boundary between two observed ones leaves the divergence located between
    those two, and no status here can name the unobserved one.
    """

    DIVERGED = "diverged"
    """The first observed boundary whose value hashes differ."""

    AGREED_WHERE_OBSERVED = "agreed_where_observed"
    """Every observed boundary agreed; unobserved boundaries said nothing."""

    INDETERMINATE = "indeterminate"
    """An ambiguous boundary was reached before any divergence was found."""

    UNOBSERVED = "unobserved"
    """Too few observed boundaries to compare anything at all."""


SINGLE_VALUED_CONCEPTS: frozenset[ConceptKind] = frozenset(
    {ConceptKind.GENDER_IDENTITY, ConceptKind.NAME_TO_USE, ConceptKind.PRONOUNS}
)
"""Concepts the case manifest declares exactly once.

More than one observation of one of these at one boundary is ambiguous
evidence. Recorded sex or gender and SPCU are record lists, so several
distinct records at one boundary are one observed state.
"""


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
    string cannot reach a receipt without a schema change. Every predicate in
    ``RulePredicate`` has one affirmative and one failure reason, so a receipt
    says which claim was decided, not only that something passed or failed.
    """

    AFFIRMATIVE_EVIDENCE_MATCH = "affirmative_evidence_match"
    AMBIGUOUS_EVIDENCE = "ambiguous_evidence"
    MISSING_EVIDENCE = "missing_evidence"
    PREDECLARED_NOT_APPLICABLE = "predeclared_not_applicable"
    SEMANTIC_MISMATCH = "semantic_mismatch"
    VALUE_PRESENT = "value_present"
    VALUE_NOT_PRESENT = "value_not_present"
    STATUS_PRESERVED = "status_preserved"
    STATUS_NOT_PRESERVED = "status_not_preserved"
    VALUE_NOT_COERCED = "value_not_coerced"
    VALUE_COERCED = "value_coerced"
    RECORD_COUNT_PRESERVED = "record_count_preserved"
    RECORD_COUNT_CHANGED = "record_count_changed"
    VALUE_PRESERVED_ACROSS_CHECKPOINTS = "value_preserved_across_checkpoints"
    VALUE_CHANGED_ACROSS_CHECKPOINTS = "value_changed_across_checkpoints"
    VALUE_NOT_OVERWRITTEN = "value_not_overwritten"
    OVERWRITTEN_BY_OTHER_CONCEPT = "overwritten_by_other_concept"


AFFIRMATIVE_REASONS: frozenset[OutcomeReason] = frozenset(
    {
        OutcomeReason.AFFIRMATIVE_EVIDENCE_MATCH,
        OutcomeReason.VALUE_PRESENT,
        OutcomeReason.STATUS_PRESERVED,
        OutcomeReason.VALUE_NOT_COERCED,
        OutcomeReason.RECORD_COUNT_PRESERVED,
        OutcomeReason.VALUE_PRESERVED_ACROSS_CHECKPOINTS,
        OutcomeReason.VALUE_NOT_OVERWRITTEN,
    }
)
"""The only reasons a ``pass`` outcome may carry."""

FAILURE_REASONS: frozenset[OutcomeReason] = frozenset(
    {
        OutcomeReason.SEMANTIC_MISMATCH,
        OutcomeReason.VALUE_NOT_PRESENT,
        OutcomeReason.STATUS_NOT_PRESERVED,
        OutcomeReason.VALUE_COERCED,
        OutcomeReason.RECORD_COUNT_CHANGED,
        OutcomeReason.VALUE_CHANGED_ACROSS_CHECKPOINTS,
        OutcomeReason.OVERWRITTEN_BY_OTHER_CONCEPT,
    }
)
"""The only reasons a ``fail`` outcome may carry."""

INDETERMINATE_REASONS: frozenset[OutcomeReason] = frozenset(
    {OutcomeReason.MISSING_EVIDENCE, OutcomeReason.AMBIGUOUS_EVIDENCE}
)
"""The only reasons an ``indeterminate`` outcome may carry."""


class RulePredicate(StrEnum):
    """The closed set of pure predicates a 0.2.0 rule may name (B-028).

    Reference-only and ungoverned: these are mechanisms for the assertions in
    ``docs/05-DATA-AND-EVIDENCE.md`` section 5 (A-005, A-008 to A-015), not
    approved assertions. ``exact`` is the default and the only predicate a
    0.1.0 rule set can express.
    """

    EXACT = "exact"
    """The single observed value hash equals the expected hash."""

    PRESENT = "present"
    """The single observed value has status ``specified`` (A-008)."""

    STATUS_PRESERVED = "status_preserved"
    """The observed status equals the expected status; value ignored (A-009)."""

    NOT_COERCED = "not_coerced"
    """The observed status and scalar are none of the rule's forbidden (A-014)."""

    RECORD_COUNT = "record_count"
    """Exactly ``expected_count`` distinct records were observed (A-013)."""

    PRESERVED_ACROSS = "preserved_across"
    """The same hash at ``preserved_from`` and at ``checkpoint`` (A-005, A-010)."""

    NOT_OVERWRITTEN_BY = "not_overwritten_by"
    """The observed value is not another concept's case value (A-011)."""


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


def coercion_key(value: SemanticValue) -> tuple[str, str | None]:
    """Return the projection of a value that A-014 is a claim about.

    A coercion rewrites what a value says (X becomes F, declined becomes a
    value), not the descriptors around it. The key is therefore the presence
    status and the scalar, and nothing else: a recorded sex or gender's
    context and source, a gender identity's code system, and an SPCU's order
    context are outside it, so a boundary that stamps its own context or
    source on a coerced record is still reported as a coercion. Recorded sex
    or gender and SPCU carry no status field and are specified by
    construction. The key is a comparison key only; receipts still carry the
    whole-value hash.
    """

    status = (
        value.status
        if isinstance(value, GenderIdentity | NameToUse | Pronouns)
        else ValueStatus.SPECIFIED
    )
    return (status.value, value.value)


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
    """A pure fixture rule over one expected typed semantic value.

    ``predicate`` defaults to ``exact``; the three predicate-specific fields
    are present only for the predicate that reads them, which the validator
    enforces. The canonical form omits every default, so a rule that says
    ``exact`` hashes exactly as it did before predicates existed.
    """

    rule_id: str
    version: str
    case_id: str
    checkpoint: Checkpoint
    concept: ConceptKind
    expected: SemanticValue
    required: bool
    predicate: RulePredicate = RulePredicate.EXACT
    forbidden: tuple[SemanticValue, ...] = ()
    expected_count: int | None = None
    preserved_from: Checkpoint | None = None

    def to_dict(self) -> dict[str, JsonValue]:
        """Return the canonical exchange representation."""

        value: dict[str, JsonValue] = {
            "case_id": self.case_id,
            "checkpoint": self.checkpoint.value,
            "concept": self.concept.value,
            "expected": self.expected.to_dict(),
            "required": self.required,
            "rule_id": self.rule_id,
            "version": self.version,
        }
        if self.predicate is not RulePredicate.EXACT:
            value["predicate"] = self.predicate.value
        if self.forbidden:
            value["forbidden"] = [item.to_dict() for item in self.forbidden]
        if self.expected_count is not None:
            value["expected_count"] = self.expected_count
        if self.preserved_from is not None:
            value["preserved_from"] = self.preserved_from.value
        return value


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
