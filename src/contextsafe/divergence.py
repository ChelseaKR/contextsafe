"""First observed divergence, computed over observed boundaries only (B-031).

For each concept the case manifest declares, this module walks the
checkpoints in pathway order (registration, EHR, interface, laboratory
return) and reports two things: the first observed checkpoint at which the
value hashes depart from the case's expected value, and, separately, the
first observed checkpoint at which they depart from the previous *observed*
checkpoint.

Three rules hold everything here, each traced to an assertion in
``docs/05-DATA-AND-EVIDENCE.md`` section 5:

* **An unobserved boundary is never blamed (A-034).** A checkpoint with no
  observation is ``unobserved``. When the checkpoint between two observed
  ones is unobserved, the divergence is located *between* the two observed
  ones: the entry names the last observed checkpoint before it and the
  observed checkpoint at which it was seen, and no field can name the gap.
* **Absence is not agreement (A-032).** ``agreed_where_observed`` says only
  that every boundary with evidence agreed; the per-checkpoint states beside
  it say which boundaries had none. A concept with no observation at all is
  ``unobserved``, and a concept whose observed boundaries cannot be read as
  one state is ``indeterminate``, never agreed.
* **Hashes, checkpoints, and statuses only.** The receipt section carries
  value hashes, closed-vocabulary checkpoint names, and closed-vocabulary
  states. No value, pointer, or identifier enters it.

Everything is a pure function of the validated bundle: observation order
cannot change the result, because the observations at a checkpoint are read
as a sorted set of hashes.
"""

from dataclasses import dataclass

from contextsafe.canonical import JsonValue, sha256_json
from contextsafe.models import (
    PATHWAY,
    SINGLE_VALUED_CONCEPTS,
    Checkpoint,
    ConceptKind,
    DivergenceStatus,
    EvaluationBundle,
    EvidenceState,
    Observation,
    SemanticValue,
    SyntheticCase,
)


@dataclass(frozen=True, slots=True)
class CheckpointState:
    """What the observation set holds for one concept at one checkpoint."""

    checkpoint: Checkpoint
    state: EvidenceState
    value_sha256s: tuple[str, ...]
    """The distinct value hashes observed here, sorted; empty when unobserved."""

    def to_dict(self) -> dict[str, JsonValue]:
        """Return the canonical receipt representation."""

        return {
            "checkpoint": self.checkpoint.value,
            "state": self.state.value,
            "value_sha256s": list(self.value_sha256s),
        }


@dataclass(frozen=True, slots=True)
class FromExpected:
    """Where a concept first departed from the case's expected value."""

    status: DivergenceStatus
    at: Checkpoint | None
    """The observed checkpoint the status is located at, if any."""

    def to_dict(self) -> dict[str, JsonValue]:
        """Return the canonical receipt representation."""

        return {
            "at": None if self.at is None else self.at.value,
            "status": self.status.value,
        }


@dataclass(frozen=True, slots=True)
class FromPrevious:
    """Where a concept first departed from the previous observed checkpoint."""

    status: DivergenceStatus
    after: Checkpoint | None
    """The last observed checkpoint before ``at``, if any: the near side."""
    at: Checkpoint | None
    """The observed checkpoint the status is located at, if any."""

    def to_dict(self) -> dict[str, JsonValue]:
        """Return the canonical receipt representation."""

        return {
            "after": None if self.after is None else self.after.value,
            "at": None if self.at is None else self.at.value,
            "status": self.status.value,
        }


@dataclass(frozen=True, slots=True)
class ConceptDivergence:
    """The divergence entry for one concept."""

    concept: ConceptKind
    expected_sha256s: tuple[str, ...]
    checkpoints: tuple[CheckpointState, ...]
    from_expected: FromExpected
    from_previous: FromPrevious

    def to_dict(self) -> dict[str, JsonValue]:
        """Return the canonical receipt representation."""

        return {
            "checkpoints": [item.to_dict() for item in self.checkpoints],
            "concept": self.concept.value,
            "expected_sha256s": list(self.expected_sha256s),
            "from_expected": self.from_expected.to_dict(),
            "from_previous": self.from_previous.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class Divergence:
    """The receipt's divergence section: one entry per concept, in order."""

    concepts: tuple[ConceptDivergence, ...]

    def to_dict(self) -> dict[str, JsonValue]:
        """Return the canonical receipt representation."""

        return {
            "concepts": [item.to_dict() for item in self.concepts],
            "pathway": [item.value for item in PATHWAY],
        }


def _declared(case: SyntheticCase, concept: ConceptKind) -> tuple[SemanticValue, ...]:
    declared: dict[ConceptKind, tuple[SemanticValue, ...]] = {
        ConceptKind.GENDER_IDENTITY: (case.gender_identity,),
        ConceptKind.RECORDED_SEX_OR_GENDER: case.recorded_sex_or_gender,
        ConceptKind.SEX_PARAMETER_FOR_CLINICAL_USE: (
            case.sex_parameter_for_clinical_use
        ),
        ConceptKind.NAME_TO_USE: (case.name_to_use,),
        ConceptKind.PRONOUNS: (case.pronouns,),
    }
    return declared[concept]


def _expected_sha256s(case: SyntheticCase, concept: ConceptKind) -> tuple[str, ...]:
    return tuple(
        sorted({sha256_json(item.to_dict()) for item in _declared(case, concept)})
    )


def _checkpoint_state(
    observations: tuple[Observation, ...], concept: ConceptKind, checkpoint: Checkpoint
) -> CheckpointState:
    """Read one boundary as one state, or say that it cannot be read as one.

    A single-valued concept seen more than once is ambiguous whatever the
    values are: two gender identities at the EHR are not one state. A record
    list is one state when every record is distinct; the same record twice is
    a double capture that cannot be told from a duplicated record, so it is
    ambiguous rather than counted once.
    """

    hashes = tuple(
        sha256_json(item.value.to_dict())
        for item in observations
        if item.concept is concept and item.checkpoint is checkpoint
    )
    if not hashes:
        return CheckpointState(checkpoint, EvidenceState.UNOBSERVED, ())
    distinct = tuple(sorted(set(hashes)))
    if len(distinct) != len(hashes) or (
        concept in SINGLE_VALUED_CONCEPTS and len(hashes) > 1
    ):
        return CheckpointState(checkpoint, EvidenceState.AMBIGUOUS, distinct)
    return CheckpointState(checkpoint, EvidenceState.OBSERVED, distinct)


def _from_expected(
    states: tuple[CheckpointState, ...], expected: tuple[str, ...]
) -> FromExpected:
    """The first observed boundary whose hashes are not the expected hashes."""

    observed = False
    for state in states:
        if state.state is EvidenceState.UNOBSERVED:
            continue
        if state.state is EvidenceState.AMBIGUOUS:
            return FromExpected(DivergenceStatus.INDETERMINATE, state.checkpoint)
        if state.value_sha256s != expected:
            return FromExpected(DivergenceStatus.DIVERGED, state.checkpoint)
        observed = True
    if observed:
        return FromExpected(DivergenceStatus.AGREED_WHERE_OBSERVED, None)
    return FromExpected(DivergenceStatus.UNOBSERVED, None)


def _from_previous(states: tuple[CheckpointState, ...]) -> FromPrevious:
    """The first observed boundary whose hashes differ from the last observed.

    ``previous`` only ever advances over observed boundaries, so a divergence
    found after an unobserved gap is located between the two observed sides
    of the gap and the gap itself is never named.
    """

    previous: CheckpointState | None = None
    compared = 0
    for state in states:
        if state.state is EvidenceState.UNOBSERVED:
            continue
        before = None if previous is None else previous.checkpoint
        if state.state is EvidenceState.AMBIGUOUS:
            return FromPrevious(
                DivergenceStatus.INDETERMINATE, before, state.checkpoint
            )
        if previous is not None and state.value_sha256s != previous.value_sha256s:
            return FromPrevious(DivergenceStatus.DIVERGED, before, state.checkpoint)
        previous = state
        compared += 1
    if compared < 2:
        return FromPrevious(DivergenceStatus.UNOBSERVED, None, None)
    return FromPrevious(DivergenceStatus.AGREED_WHERE_OBSERVED, None, None)


def _concept_divergence(
    case: SyntheticCase, observations: tuple[Observation, ...], concept: ConceptKind
) -> ConceptDivergence:
    expected = _expected_sha256s(case, concept)
    states = tuple(
        _checkpoint_state(observations, concept, checkpoint) for checkpoint in PATHWAY
    )
    return ConceptDivergence(
        concept=concept,
        expected_sha256s=expected,
        checkpoints=states,
        from_expected=_from_expected(states, expected),
        from_previous=_from_previous(states),
    )


def compute_divergence(bundle: EvaluationBundle) -> Divergence:
    """Compute the first observed divergence of every concept in the bundle.

    Reads only observations that name the bundle's case, which ``parse_bundle``
    already guarantees is all of them, and never reads a rule: divergence is
    a property of the evidence against the manifest, not of any assertion.
    """

    observations = tuple(
        item for item in bundle.observations if item.case_id == bundle.case.case_id
    )
    return Divergence(
        concepts=tuple(
            _concept_divergence(bundle.case, observations, concept)
            for concept in ConceptKind
        )
    )
