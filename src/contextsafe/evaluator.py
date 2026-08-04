"""Pure evaluator for exact, typed synthetic fixture expectations."""

from dataclasses import dataclass

from contextsafe.canonical import JsonValue, sha256_json
from contextsafe.models import (
    ConceptKind,
    EvaluationBundle,
    Observation,
    OutcomeReason,
    OutcomeStatus,
    Rule,
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


def _matches(
    rule: Rule, observations: tuple[Observation, ...]
) -> tuple[Observation, ...]:
    return tuple(
        observation
        for observation in observations
        if observation.case_id == rule.case_id
        and observation.checkpoint is rule.checkpoint
        and observation.concept is rule.concept
    )


def _outcome(rule: Rule, matches: tuple[Observation, ...]) -> Outcome:
    expected_sha256 = sha256_json(rule.expected.to_dict())
    observed_sha256s = tuple(
        sorted(sha256_json(item.value.to_dict()) for item in matches)
    )
    evidence_sha256s = tuple(sorted(item.evidence.source_sha256 for item in matches))
    if not rule.required:
        status = OutcomeStatus.NOT_APPLICABLE
        reason = OutcomeReason.PREDECLARED_NOT_APPLICABLE
    elif not matches:
        status = OutcomeStatus.INDETERMINATE
        reason = OutcomeReason.MISSING_EVIDENCE
    elif len(matches) > 1:
        status = OutcomeStatus.INDETERMINATE
        reason = OutcomeReason.AMBIGUOUS_EVIDENCE
    elif observed_sha256s[0] == expected_sha256:
        status = OutcomeStatus.PASSED
        reason = OutcomeReason.AFFIRMATIVE_EVIDENCE_MATCH
    else:
        status = OutcomeStatus.FAIL
        reason = OutcomeReason.SEMANTIC_MISMATCH
    return Outcome(
        rule_id=rule.rule_id,
        rule_version=rule.version,
        case_id=rule.case_id,
        checkpoint=rule.checkpoint.value,
        concept=rule.concept,
        status=status,
        reason=reason,
        expected_sha256=expected_sha256,
        observed_sha256s=observed_sha256s,
        evidence_sha256s=evidence_sha256s,
    )


def evaluate(bundle: EvaluationBundle) -> tuple[Outcome, ...]:
    """Evaluate rules deterministically without inference or clinical judgment."""

    return tuple(
        _outcome(rule, _matches(rule, bundle.observations))
        for rule in sorted(bundle.rule_set.rules, key=lambda item: item.rule_id)
    )
