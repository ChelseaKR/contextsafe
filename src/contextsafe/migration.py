"""Pure comparison of one synthetic case observed in two systems at once.

A migration replaces one system with another. While both are live, the same
synthetic case can be observed in each, which is the only period in which
semantic preservation across the cutover can be measured rather than inferred.
Once the legacy system is retired the comparison is not reconstructable, because
the quantity under test is exactly what changed in translation.

This module answers one question per (checkpoint, concept) pair: did the two
systems represent the same thing? It answers nothing else. In particular it does
not decide which system is correct, does not rank the systems, and performs no
clinical judgment. A divergence is a finding for a reviewer, not a verdict.

Three invariants are carried over from `evaluator`, deliberately:

* **Value minimization.** Comparison is by content hash. No identity value, not
  even a synthetic one, appears in a result.
* **Purity and determinism.** Same inputs, same output, no ordering dependence.
* **Absence is never agreement.** Two systems that both fail to produce an
  observation have not agreed with each other; they have produced no evidence.
  That is `no_evidence`, and it is never `preserved`.
"""

from dataclasses import dataclass
from enum import StrEnum

from contextsafe.canonical import JsonValue, sha256_json
from contextsafe.models import Checkpoint, ConceptKind, Observation, SyntheticCase

COMPARISON_SCHEMA_VERSION = "contextsafe.migration-comparison/0.1.0"


class SystemRole(StrEnum):
    """Which side of a cutover a set of observations came from."""

    LEGACY = "legacy"
    TARGET = "target"


class Divergence(StrEnum):
    """The closed set of comparison findings.

    Kept separate from `OutcomeReason` on purpose: the published receipt
    contract repeats that set, so extending it would be a receipt schema
    change. A migration comparison is a different artifact with its own
    version, and must not silently widen the receipt's vocabulary.
    """

    PRESERVED = "preserved"
    """Both systems produced exactly one observation and the values agree."""

    CHANGED = "changed"
    """Both systems observed, and the values differ. Meaning moved."""

    LOST = "lost"
    """The legacy system observed a value and the target produced none."""

    INTRODUCED = "introduced"
    """The target produced a value the legacy system did not observe."""

    NO_EVIDENCE = "no_evidence"
    """Neither system produced an observation. Not agreement; no measurement."""

    AMBIGUOUS = "ambiguous"
    """At least one system produced multiple observations. Not comparable."""


#: Findings that mean the cutover did not carry the concept across unchanged.
#: `NO_EVIDENCE` and `AMBIGUOUS` are excluded because they are failures to
#: measure, not measured differences, and reporting them as drift would
#: overstate what was observed.
DIVERGENT: frozenset[Divergence] = frozenset(
    {Divergence.CHANGED, Divergence.LOST, Divergence.INTRODUCED}
)


@dataclass(frozen=True, slots=True)
class ConceptComparison:
    """One comparison at one checkpoint for one canonical concept."""

    case_id: str
    checkpoint: Checkpoint
    concept: ConceptKind
    divergence: Divergence
    legacy_sha256s: tuple[str, ...]
    target_sha256s: tuple[str, ...]
    legacy_evidence_sha256s: tuple[str, ...]
    target_evidence_sha256s: tuple[str, ...]

    @property
    def is_divergent(self) -> bool:
        """Whether this comparison is a measured difference between systems."""

        return self.divergence in DIVERGENT

    def to_dict(self) -> dict[str, JsonValue]:
        """Return the deterministic, value-minimized representation."""

        return {
            "case_id": self.case_id,
            "checkpoint": self.checkpoint.value,
            "concept": self.concept.value,
            "divergence": self.divergence.value,
            "legacy_evidence_sha256s": list(self.legacy_evidence_sha256s),
            "legacy_sha256s": list(self.legacy_sha256s),
            "target_evidence_sha256s": list(self.target_evidence_sha256s),
            "target_sha256s": list(self.target_sha256s),
        }


@dataclass(frozen=True, slots=True)
class MigrationComparison:
    """Every comparison for one case across one cutover."""

    schema_version: str
    case_id: str
    comparisons: tuple[ConceptComparison, ...]

    @property
    def divergences(self) -> tuple[ConceptComparison, ...]:
        """Only the comparisons that are measured differences."""

        return tuple(item for item in self.comparisons if item.is_divergent)

    @property
    def measured(self) -> tuple[ConceptComparison, ...]:
        """Comparisons where both systems were actually comparable."""

        return tuple(
            item
            for item in self.comparisons
            if item.divergence is not Divergence.NO_EVIDENCE
        )

    def to_dict(self) -> dict[str, JsonValue]:
        """Return comparisons in a stable checkpoint then concept order."""

        return {
            "case_id": self.case_id,
            "comparisons": [item.to_dict() for item in self.comparisons],
            "schema_version": self.schema_version,
        }


def _select(
    observations: tuple[Observation, ...],
    case_id: str,
    checkpoint: Checkpoint,
    concept: ConceptKind,
) -> tuple[Observation, ...]:
    return tuple(
        item
        for item in observations
        if item.case_id == case_id
        and item.checkpoint is checkpoint
        and item.concept is concept
    )


def _hashes(observations: tuple[Observation, ...]) -> tuple[str, ...]:
    return tuple(sorted(sha256_json(item.value.to_dict()) for item in observations))


def _evidence(observations: tuple[Observation, ...]) -> tuple[str, ...]:
    return tuple(sorted(item.evidence.source_sha256 for item in observations))


def _classify(
    legacy: tuple[Observation, ...], target: tuple[Observation, ...]
) -> Divergence:
    """Classify one pair of observation groups.

    Ambiguity is checked before absence: a system that emitted two conflicting
    observations has not told us anything we can compare, and calling that
    `lost` or `changed` would attribute a specific finding to what is really an
    unusable measurement.
    """

    if len(legacy) > 1 or len(target) > 1:
        return Divergence.AMBIGUOUS
    if not legacy and not target:
        return Divergence.NO_EVIDENCE
    if not target:
        return Divergence.LOST
    if not legacy:
        return Divergence.INTRODUCED
    legacy_hash = sha256_json(legacy[0].value.to_dict())
    target_hash = sha256_json(target[0].value.to_dict())
    if legacy_hash == target_hash:
        return Divergence.PRESERVED
    return Divergence.CHANGED


def compare_migration(
    case: SyntheticCase,
    legacy_observations: tuple[Observation, ...],
    target_observations: tuple[Observation, ...],
) -> MigrationComparison:
    """Compare one case observed in a legacy and a target system.

    Every checkpoint and concept pair is reported, including those where
    neither system produced evidence. Reporting only the pairs that happened to
    be observed would let a cutover that dropped a concept entirely appear as a
    clean comparison with fewer rows, which is the failure mode this function
    exists to make visible.
    """

    comparisons = tuple(
        ConceptComparison(
            case_id=case.case_id,
            checkpoint=checkpoint,
            concept=concept,
            divergence=_classify(legacy, target),
            legacy_sha256s=_hashes(legacy),
            target_sha256s=_hashes(target),
            legacy_evidence_sha256s=_evidence(legacy),
            target_evidence_sha256s=_evidence(target),
        )
        for checkpoint in Checkpoint
        for concept in ConceptKind
        for legacy, target in (
            (
                _select(legacy_observations, case.case_id, checkpoint, concept),
                _select(target_observations, case.case_id, checkpoint, concept),
            ),
        )
    )
    return MigrationComparison(
        schema_version=COMPARISON_SCHEMA_VERSION,
        case_id=case.case_id,
        comparisons=comparisons,
    )
