"""Invariants for comparing one case observed in two systems at once.

The properties asserted here are the ones a cutover comparison can fail
silently: treating absence as agreement, hiding a dropped concept by omitting
its row, leaking a value into a result, or letting observation order change the
finding. Each is a way a migration could look clean while having lost meaning.
"""

from typing import Any

import pytest

from contextsafe.canonical import canonical_json
from contextsafe.migration import (
    COMPARISON_SCHEMA_VERSION,
    DIVERGENT,
    Divergence,
    compare_migration,
)
from contextsafe.models import Checkpoint, ConceptKind, Observation
from contextsafe.validation import parse_bundle


@pytest.fixture
def bundle(
    case_json: dict[str, Any],
    observations_json: dict[str, Any],
    rules_json: dict[str, Any],
) -> Any:
    return parse_bundle(case_json, observations_json, rules_json)


def _drop(
    observations: tuple[Observation, ...], concept: ConceptKind
) -> tuple[Observation, ...]:
    return tuple(item for item in observations if item.concept is not concept)


def _only(
    observations: tuple[Observation, ...], concept: ConceptKind
) -> tuple[Observation, ...]:
    return tuple(item for item in observations if item.concept is concept)


def _find(comparison: Any, checkpoint: Checkpoint, concept: ConceptKind) -> Any:
    return next(
        item
        for item in comparison.comparisons
        if item.checkpoint is checkpoint and item.concept is concept
    )


def test_identical_systems_preserve_every_observed_concept(bundle: Any) -> None:
    result = compare_migration(bundle.case, bundle.observations, bundle.observations)
    assert result.schema_version == COMPARISON_SCHEMA_VERSION
    assert result.divergences == ()
    assert result.measured, "the reference fixture must produce some measurement"
    assert all(item.divergence is Divergence.PRESERVED for item in result.measured), (
        "identical inputs must not produce a difference"
    )


def test_every_checkpoint_and_concept_pair_is_reported(bundle: Any) -> None:
    """A dropped concept must not vanish from the report along with its data."""

    result = compare_migration(bundle.case, bundle.observations, bundle.observations)
    assert len(result.comparisons) == len(Checkpoint) * len(ConceptKind)
    seen = {(item.checkpoint, item.concept) for item in result.comparisons}
    assert seen == {(c, k) for c in Checkpoint for k in ConceptKind}


def test_absence_on_both_sides_is_never_preserved(bundle: Any) -> None:
    """Two systems that observed nothing have not agreed with each other."""

    result = compare_migration(bundle.case, (), ())
    assert result.comparisons, "pairs must still be reported when nothing is observed"
    assert all(item.divergence is Divergence.NO_EVIDENCE for item in result.comparisons)
    assert result.divergences == (), "no evidence is not a measured difference"
    assert result.measured == (), "no evidence is not a measurement"


def test_a_concept_the_target_lost_is_reported_as_lost(bundle: Any) -> None:
    target = _drop(bundle.observations, ConceptKind.PRONOUNS)
    result = compare_migration(bundle.case, bundle.observations, target)
    lost = [item for item in result.divergences if item.divergence is Divergence.LOST]
    assert lost, "dropping a concept in the target must surface as a divergence"
    assert all(item.concept is ConceptKind.PRONOUNS for item in lost)
    assert all(item.target_sha256s == () for item in lost)
    assert all(item.legacy_sha256s != () for item in lost)


def test_a_concept_only_the_target_has_is_reported_as_introduced(bundle: Any) -> None:
    legacy = _drop(bundle.observations, ConceptKind.PRONOUNS)
    result = compare_migration(bundle.case, legacy, bundle.observations)
    introduced = [
        item for item in result.divergences if item.divergence is Divergence.INTRODUCED
    ]
    assert introduced
    assert all(item.concept is ConceptKind.PRONOUNS for item in introduced)


def test_a_changed_value_is_reported_as_changed(bundle: Any) -> None:
    """Swapping in a different concept's value must read as changed, not lost."""

    pronouns = _only(bundle.observations, ConceptKind.PRONOUNS)
    assert pronouns, "fixture must observe pronouns for this test to mean anything"
    original = pronouns[0]
    other = next(
        item
        for item in bundle.observations
        if item.concept is ConceptKind.PRONOUNS and item is original
    )
    mutated = Observation(
        schema_version=other.schema_version,
        observation_id=other.observation_id,
        case_id=other.case_id,
        checkpoint=other.checkpoint,
        concept=other.concept,
        value=bundle.case.name_to_use,
        evidence=other.evidence,
        mapping=other.mapping,
    )
    target = (*_drop(bundle.observations, ConceptKind.PRONOUNS), mutated)
    found = _find(
        compare_migration(bundle.case, bundle.observations, target),
        other.checkpoint,
        ConceptKind.PRONOUNS,
    )
    assert found.divergence is Divergence.CHANGED
    assert found.legacy_sha256s != found.target_sha256s


def test_duplicate_observations_are_ambiguous_not_a_finding(bundle: Any) -> None:
    """An unusable measurement must not be reported as a specific difference."""

    pronouns = _only(bundle.observations, ConceptKind.PRONOUNS)
    doubled = bundle.observations + pronouns
    found = _find(
        compare_migration(bundle.case, doubled, bundle.observations),
        pronouns[0].checkpoint,
        ConceptKind.PRONOUNS,
    )
    assert found.divergence is Divergence.AMBIGUOUS
    assert not found.is_divergent, "ambiguity is a failure to measure, not drift"


def test_ambiguity_is_decided_before_absence(bundle: Any) -> None:
    """A doubled legacy against an empty target is ambiguous, not lost."""

    pronouns = _only(bundle.observations, ConceptKind.PRONOUNS)
    found = _find(
        compare_migration(bundle.case, pronouns + pronouns, ()),
        pronouns[0].checkpoint,
        ConceptKind.PRONOUNS,
    )
    assert found.divergence is Divergence.AMBIGUOUS


def _semantic_strings(payload: Any) -> set[str]:
    """Collect every string carried under a `value` key, at any depth.

    Walking the payload rather than naming fields means a concept added later
    is covered by this guard automatically, instead of silently escaping it.
    """

    found: set[str] = set()
    if isinstance(payload, dict):
        for key, item in payload.items():
            if key == "value" and isinstance(item, str) and len(item) >= 3:
                found.add(item)
            else:
                found |= _semantic_strings(item)
    elif isinstance(payload, list):
        for item in payload:
            found |= _semantic_strings(item)
    return found


def test_no_identity_value_appears_anywhere_in_the_result(bundle: Any) -> None:
    """Value minimization: the comparison must carry hashes, never values."""

    result = compare_migration(bundle.case, bundle.observations, bundle.observations)
    serialized = canonical_json(result.to_dict())

    sensitive = _semantic_strings(bundle.case.to_dict()["concepts"])
    for observation in bundle.observations:
        sensitive |= _semantic_strings(observation.value.to_dict())
    assert sensitive, (
        "fixture must carry semantic values for this guard to mean anything"
    )

    leaks = sorted(value for value in sensitive if value in serialized)
    assert leaks == [], f"identity values leaked into the comparison: {leaks}"


def test_result_is_order_independent_and_deterministic(bundle: Any) -> None:
    forward = compare_migration(bundle.case, bundle.observations, bundle.observations)
    reversed_inputs = compare_migration(
        bundle.case,
        tuple(reversed(bundle.observations)),
        tuple(reversed(bundle.observations)),
    )
    assert canonical_json(forward.to_dict()) == canonical_json(
        reversed_inputs.to_dict()
    )


def test_divergent_set_excludes_failures_to_measure() -> None:
    """Guards the classification itself, not one comparison."""

    divergent = set(DIVERGENT)
    assert Divergence.NO_EVIDENCE not in divergent
    assert Divergence.AMBIGUOUS not in divergent
    assert Divergence.PRESERVED not in divergent
    assert divergent == {
        Divergence.CHANGED,
        Divergence.LOST,
        Divergence.INTRODUCED,
    }


def test_observations_for_another_case_are_ignored(bundle: Any) -> None:
    """Cross-case contamination must not register as evidence."""

    foreign = tuple(
        Observation(
            schema_version=item.schema_version,
            observation_id=item.observation_id,
            case_id="CSYN-SOME-OTHER-CASE",
            checkpoint=item.checkpoint,
            concept=item.concept,
            value=item.value,
            evidence=item.evidence,
            mapping=item.mapping,
        )
        for item in bundle.observations
    )
    result = compare_migration(bundle.case, foreign, foreign)
    assert all(item.divergence is Divergence.NO_EVIDENCE for item in result.comparisons)
