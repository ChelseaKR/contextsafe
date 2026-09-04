"""Pure evaluator over typed synthetic fixture expectations.

Every rule names one predicate from the closed ``RulePredicate`` set, and every
predicate here is a pure function of the validated bundle and the rule: no
clock, no environment, no clinical judgment, and no value that is not already
a hash by the time it reaches an ``Outcome``.

The status algebra is decided before any predicate runs. A rule that is not
required is ``not_applicable``. A required rule with no matching observation
is ``indeterminate`` with ``missing_evidence``; one with more than one matching
observation is ``indeterminate`` with ``ambiguous_evidence`` (``record_count``
is the one predicate that reads several observations, and it decides count,
not identity). Only a rule with exactly the evidence its predicate reads can
pass or fail, so absence never becomes pass.

The predicates are a reference-only mechanism for the identity, name-to-use,
pronoun, and recorded-sex-or-gender assertions in
``docs/05-DATA-AND-EVIDENCE.md`` section 5. No clinical, laboratory, or
community review has approved any rule that uses them.
"""

from collections.abc import Callable
from dataclasses import dataclass

from contextsafe.canonical import JsonValue, sha256_json
from contextsafe.models import (
    Checkpoint,
    ConceptKind,
    EvaluationBundle,
    GenderIdentity,
    NameToUse,
    Observation,
    OutcomeReason,
    OutcomeStatus,
    Pronouns,
    Rule,
    RulePredicate,
    SemanticValue,
    SyntheticCase,
    ValueStatus,
)


@dataclass(frozen=True, slots=True)
class Outcome:
    """A claim-minimal outcome with hashes instead of semantic field values."""

    rule_id: str
    rule_version: str
    case_id: str
    checkpoint: str
    concept: ConceptKind
    status: OutcomeStatus
    reason: OutcomeReason
    expected_sha256: str
    observed_sha256s: tuple[str, ...]
    evidence_sha256s: tuple[str, ...]

    def to_dict(self) -> dict[str, JsonValue]:
        """Return the deterministic, value-minimized receipt representation."""

        return {
            "case_id": self.case_id,
            "checkpoint": self.checkpoint,
            "concept": self.concept.value,
            "evidence_sha256s": list(self.evidence_sha256s),
            "expected_sha256": self.expected_sha256,
            "observed_sha256s": list(self.observed_sha256s),
            "reason": self.reason.value,
            "rule_id": self.rule_id,
            "rule_version": self.rule_version,
            "status": self.status.value,
        }


@dataclass(frozen=True, slots=True)
class _Verdict:
    """What a predicate decided, before it is bound to a rule."""

    status: OutcomeStatus
    reason: OutcomeReason
    observed_sha256s: tuple[str, ...]
    evidence_sha256s: tuple[str, ...]


def _matches(
    observations: tuple[Observation, ...], rule: Rule, checkpoint: Checkpoint
) -> tuple[Observation, ...]:
    return tuple(
        observation
        for observation in observations
        if observation.case_id == rule.case_id
        and observation.checkpoint is checkpoint
        and observation.concept is rule.concept
    )


def _value_sha256(observation: Observation) -> str:
    return sha256_json(observation.value.to_dict())


def _observed(matches: tuple[Observation, ...]) -> tuple[str, ...]:
    return tuple(sorted(_value_sha256(item) for item in matches))


def _evidence(matches: tuple[Observation, ...]) -> tuple[str, ...]:
    return tuple(sorted(item.evidence.source_sha256 for item in matches))


def _decided(
    passed: bool,
    affirmative: OutcomeReason,
    failure: OutcomeReason,
    matches: tuple[Observation, ...],
) -> _Verdict:
    return _Verdict(
        status=OutcomeStatus.PASSED if passed else OutcomeStatus.FAIL,
        reason=affirmative if passed else failure,
        observed_sha256s=_observed(matches),
        evidence_sha256s=_evidence(matches),
    )


def _evidence_gate(matches: tuple[Observation, ...]) -> _Verdict | None:
    """Return the indeterminate verdict a single-observation predicate owes.

    None means exactly one observation matched and the predicate may decide.
    """

    if not matches:
        return _Verdict(
            OutcomeStatus.INDETERMINATE, OutcomeReason.MISSING_EVIDENCE, (), ()
        )
    if len(matches) > 1:
        return _Verdict(
            OutcomeStatus.INDETERMINATE,
            OutcomeReason.AMBIGUOUS_EVIDENCE,
            _observed(matches),
            _evidence(matches),
        )
    return None


def _status_of(value: SemanticValue) -> ValueStatus:
    """Return a value's presence status.

    Recorded sex or gender and SPCU values carry no status field: the
    validator admits them only with a non-empty value, so they are specified
    by construction.
    """

    if isinstance(value, GenderIdentity | NameToUse | Pronouns):
        return value.status
    return ValueStatus.SPECIFIED


def _scalar_of(value: SemanticValue) -> str | None:
    """Return the one scalar a value carries, or None when it carries none."""

    return value.value


def _exact(bundle: EvaluationBundle, rule: Rule) -> _Verdict:
    matches = _matches(bundle.observations, rule, rule.checkpoint)
    gated = _evidence_gate(matches)
    if gated is not None:
        return gated
    return _decided(
        _value_sha256(matches[0]) == sha256_json(rule.expected.to_dict()),
        OutcomeReason.AFFIRMATIVE_EVIDENCE_MATCH,
        OutcomeReason.SEMANTIC_MISMATCH,
        matches,
    )


def _present(bundle: EvaluationBundle, rule: Rule) -> _Verdict:
    matches = _matches(bundle.observations, rule, rule.checkpoint)
    gated = _evidence_gate(matches)
    if gated is not None:
        return gated
    return _decided(
        _status_of(matches[0].value) is ValueStatus.SPECIFIED,
        OutcomeReason.VALUE_PRESENT,
        OutcomeReason.VALUE_NOT_PRESENT,
        matches,
    )


def _status_preserved(bundle: EvaluationBundle, rule: Rule) -> _Verdict:
    """A-009: declined stays declined; it never becomes unknown, absent, or a value."""

    matches = _matches(bundle.observations, rule, rule.checkpoint)
    gated = _evidence_gate(matches)
    if gated is not None:
        return gated
    return _decided(
        _status_of(matches[0].value) is _status_of(rule.expected),
        OutcomeReason.STATUS_PRESERVED,
        OutcomeReason.STATUS_NOT_PRESERVED,
        matches,
    )


def _not_coerced(bundle: EvaluationBundle, rule: Rule) -> _Verdict:
    """A-014: the observed hash is in none of the rule's forbidden hashes.

    The comparison is over whole typed values, so a coercion that also
    rewrites the value's context or source is not in the forbidden set and is
    not reported here; an ``exact`` rule on the same field is what catches it.
    """

    matches = _matches(bundle.observations, rule, rule.checkpoint)
    gated = _evidence_gate(matches)
    if gated is not None:
        return gated
    forbidden = {sha256_json(item.to_dict()) for item in rule.forbidden}
    return _decided(
        _value_sha256(matches[0]) not in forbidden,
        OutcomeReason.VALUE_NOT_COERCED,
        OutcomeReason.VALUE_COERCED,
        matches,
    )


def _record_count(bundle: EvaluationBundle, rule: Rule) -> _Verdict:
    """A-013: n distinct records remain n distinct records.

    No observation at all is missing evidence, not a count of zero: the
    boundary may simply not have been observed. A rule with no declared
    count cannot pass.
    """

    matches = _matches(bundle.observations, rule, rule.checkpoint)
    if not matches:
        return _Verdict(
            OutcomeStatus.INDETERMINATE, OutcomeReason.MISSING_EVIDENCE, (), ()
        )
    observed = _observed(matches)
    return _decided(
        rule.expected_count is not None
        and len(observed) == rule.expected_count
        and len(set(observed)) == rule.expected_count,
        OutcomeReason.RECORD_COUNT_PRESERVED,
        OutcomeReason.RECORD_COUNT_CHANGED,
        matches,
    )


def _preserved_across(bundle: EvaluationBundle, rule: Rule) -> _Verdict:
    """A-005, A-010, A-012: the same value hash at two named checkpoints.

    This is a preservation claim, not a correctness claim: a value that is
    wrong at both checkpoints is preserved. A rule with no source checkpoint
    has nothing to read and is missing evidence.
    """

    source = (
        ()
        if rule.preserved_from is None
        else _matches(bundle.observations, rule, rule.preserved_from)
    )
    target = _matches(bundle.observations, rule, rule.checkpoint)
    gated = _evidence_gate(source) or _evidence_gate(target)
    if gated is not None:
        return gated
    return _decided(
        _value_sha256(source[0]) == _value_sha256(target[0]),
        OutcomeReason.VALUE_PRESERVED_ACROSS_CHECKPOINTS,
        OutcomeReason.VALUE_CHANGED_ACROSS_CHECKPOINTS,
        (*source, *target),
    )


def _other_concept_scalars(case: SyntheticCase, concept: ConceptKind) -> set[str]:
    """Hashes of every scalar the case declares under a different concept."""

    declared: dict[ConceptKind, tuple[SemanticValue, ...]] = {
        ConceptKind.GENDER_IDENTITY: (case.gender_identity,),
        ConceptKind.RECORDED_SEX_OR_GENDER: case.recorded_sex_or_gender,
        ConceptKind.SEX_PARAMETER_FOR_CLINICAL_USE: (
            case.sex_parameter_for_clinical_use
        ),
        ConceptKind.NAME_TO_USE: (case.name_to_use,),
        ConceptKind.PRONOUNS: (case.pronouns,),
    }
    return {
        sha256_json(scalar)
        for other, values in declared.items()
        if other is not concept
        for value in values
        if (scalar := _scalar_of(value)) is not None
    }


def _not_overwritten_by(bundle: EvaluationBundle, rule: Rule) -> _Verdict:
    """A-011: the observed value is not another concept's declared value.

    Whole typed values of different concepts never hash alike, so the check
    is over the scalar each value carries. An observation with no scalar
    (declined, unknown, absent) is not carrying another concept's value.
    """

    matches = _matches(bundle.observations, rule, rule.checkpoint)
    gated = _evidence_gate(matches)
    if gated is not None:
        return gated
    scalar = _scalar_of(matches[0].value)
    overwritten = scalar is not None and sha256_json(scalar) in _other_concept_scalars(
        bundle.case, rule.concept
    )
    return _decided(
        not overwritten,
        OutcomeReason.VALUE_NOT_OVERWRITTEN,
        OutcomeReason.OVERWRITTEN_BY_OTHER_CONCEPT,
        matches,
    )


_PREDICATES: dict[RulePredicate, Callable[[EvaluationBundle, Rule], _Verdict]] = {
    RulePredicate.EXACT: _exact,
    RulePredicate.PRESENT: _present,
    RulePredicate.STATUS_PRESERVED: _status_preserved,
    RulePredicate.NOT_COERCED: _not_coerced,
    RulePredicate.RECORD_COUNT: _record_count,
    RulePredicate.PRESERVED_ACROSS: _preserved_across,
    RulePredicate.NOT_OVERWRITTEN_BY: _not_overwritten_by,
}


def _outcome(bundle: EvaluationBundle, rule: Rule) -> Outcome:
    if rule.required:
        verdict = _PREDICATES[rule.predicate](bundle, rule)
    else:
        verdict = _Verdict(
            OutcomeStatus.NOT_APPLICABLE,
            OutcomeReason.PREDECLARED_NOT_APPLICABLE,
            _observed(_matches(bundle.observations, rule, rule.checkpoint)),
            _evidence(_matches(bundle.observations, rule, rule.checkpoint)),
        )
    return Outcome(
        rule_id=rule.rule_id,
        rule_version=rule.version,
        case_id=rule.case_id,
        checkpoint=rule.checkpoint.value,
        concept=rule.concept,
        status=verdict.status,
        reason=verdict.reason,
        expected_sha256=sha256_json(rule.expected.to_dict()),
        observed_sha256s=verdict.observed_sha256s,
        evidence_sha256s=verdict.evidence_sha256s,
    )


def evaluate(bundle: EvaluationBundle) -> tuple[Outcome, ...]:
    """Evaluate rules deterministically without inference or clinical judgment."""

    return tuple(
        _outcome(bundle, rule)
        for rule in sorted(bundle.rule_set.rules, key=lambda item: item.rule_id)
    )
