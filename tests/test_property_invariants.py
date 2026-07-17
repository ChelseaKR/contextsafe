"""Property-based tests for the merge-blocking status-algebra invariants.

These generate synthetic bundles and mutations to exercise the
machine-checkable subset of the invariants in
``docs/09-TEST-AND-EVALUATION.md`` section 3 against the iteration-1
evaluator: no pass without affirmative evidence (1), not-applicable only
from a predeclared rule (3), no cross-concept coercion (4 and 9), and
deterministic identical payloads for identical inputs (10). Invariants
that need pack lifecycle, review signatures, HTML rendering, or
signature verification (2, 5, 6, 7, 8) have no shipped component yet and
are deliberately absent here.
"""

import json
from pathlib import Path
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from contextsafe.canonical import sha256_json
from contextsafe.errors import ContextSafeError
from contextsafe.evaluator import Outcome, evaluate
from contextsafe.models import (
    CASE_SCHEMA_VERSION,
    OBSERVATION_SCHEMA_VERSION,
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
from contextsafe.receipt import build_receipt, render_receipt
from contextsafe.validation import parse_bundle

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "fixtures" / "reference"

_VALUE_MARKER = "CSYNPROPVAL"
_TOKENS = st.text(alphabet="ABCDEFGH", min_size=1, max_size=6).map(
    lambda suffix: f"{_VALUE_MARKER}-{suffix}"
)
_STATUSES = st.sampled_from(
    (ValueStatus.SPECIFIED, ValueStatus.DECLINED, ValueStatus.UNKNOWN)
)


@st.composite
def _semantic_values(draw: st.DrawFn, concept: ConceptKind) -> SemanticValue:
    token = draw(_TOKENS)
    status = draw(_STATUSES)
    value = token if status is ValueStatus.SPECIFIED else None
    if concept is ConceptKind.GENDER_IDENTITY:
        return GenderIdentity(
            status=status, value=value, code_system="urn:contextsafe:fixture"
        )
    if concept is ConceptKind.RECORDED_SEX_OR_GENDER:
        return RecordedSexOrGender(
            value=draw(st.sampled_from(("F", "M", "X", "unknown"))),
            context=token,
            source="synthetic-fixture",
        )
    if concept is ConceptKind.SEX_PARAMETER_FOR_CLINICAL_USE:
        return SexParameterForClinicalUse(
            value=token,
            context_id=f"ORDER-CSYN-{draw(_TOKENS)}",
            supporting_observation_ids=(f"SUP-CSYN-{draw(_TOKENS)}",),
        )
    if concept is ConceptKind.NAME_TO_USE:
        return NameToUse(
            status=status,
            value=None if value is None else f"CSYN-{value}",
            use="usual",
        )
    return Pronouns(status=status, value=value)


@st.composite
def _rules(draw: st.DrawFn, index: int) -> Rule:
    concept = draw(st.sampled_from(tuple(ConceptKind)))
    return Rule(
        rule_id=f"A-I{index:02d}",
        version="0.1.0",
        case_id=draw(st.sampled_from(("CTP-P01", "CTP-P02"))),
        checkpoint=draw(st.sampled_from(tuple(Checkpoint))),
        concept=concept,
        expected=draw(_semantic_values(concept)),
        required=draw(st.booleans()),
    )


@st.composite
def _observations(draw: st.DrawFn, rule: Rule, index: int) -> Observation:
    aligned = draw(st.booleans())
    concept = rule.concept if aligned else draw(st.sampled_from(tuple(ConceptKind)))
    matches_expected = draw(st.booleans())
    value = (
        rule.expected
        if aligned and matches_expected and concept is rule.concept
        else draw(_semantic_values(concept))
    )
    return Observation(
        schema_version=OBSERVATION_SCHEMA_VERSION,
        observation_id=f"OBS-P{index:02d}",
        case_id=rule.case_id
        if aligned
        else draw(st.sampled_from(("CTP-P01", "CTP-P02"))),
        checkpoint=rule.checkpoint
        if aligned
        else draw(st.sampled_from(tuple(Checkpoint))),
        concept=concept,
        value=value,
        evidence=EvidencePointer(
            source_sha256=sha256_json(value.to_dict()),
            source_pointer="$.concepts",
        ),
        mapping=MappingDescriptor(
            source_concept=concept,
            target_concept=concept,
            mapping_version="0.1.0",
        ),
    )


@st.composite
def _bundles(draw: st.DrawFn) -> EvaluationBundle:
    rule_count = draw(st.integers(min_value=1, max_value=4))
    rules = tuple(draw(_rules(index)) for index in range(rule_count))
    observations: list[Observation] = []
    observation_index = 0
    for rule in rules:
        for _ in range(draw(st.integers(min_value=0, max_value=3))):
            observations.append(draw(_observations(rule, observation_index)))
            observation_index += 1
    case = SyntheticCase(
        schema_version=CASE_SCHEMA_VERSION,
        case_id="CTP-P01",
        synthetic_identifier=SyntheticIdentifier(
            system="urn:contextsafe:synthetic", value="CSYN-CTP-P01"
        ),
        gender_identity=draw(_semantic_values(ConceptKind.GENDER_IDENTITY)),
        recorded_sex_or_gender=(),
        sex_parameter_for_clinical_use=(),
        name_to_use=draw(_semantic_values(ConceptKind.NAME_TO_USE)),
        pronouns=draw(_semantic_values(ConceptKind.PRONOUNS)),
        prohibited_inferences=(
            "gender_identity_to_spcu",
            "recorded_sex_or_gender_to_spcu",
        ),
    )
    return EvaluationBundle(
        case=case,
        observations=tuple(observations),
        rule_set=RuleSet(schema_version=RULE_SET_SCHEMA_VERSION, rules=rules),
    )


def _outcome_for(rule: Rule, outcomes: tuple[Outcome, ...]) -> Outcome:
    matched = [item for item in outcomes if item.rule_id == rule.rule_id]
    assert len(matched) == 1
    return matched[0]


@settings(max_examples=200, deadline=None)
@given(bundle=_bundles())
def test_pass_requires_exactly_one_affirmative_evidence_match(
    bundle: EvaluationBundle,
) -> None:
    """Invariant 1: missing or ambiguous evidence can never produce pass."""

    for outcome in evaluate(bundle):
        if outcome.status.value == "pass":
            assert len(outcome.observed_sha256s) == 1
            assert outcome.observed_sha256s[0] == outcome.expected_sha256
            assert outcome.reason == "affirmative_evidence_match"
        if not outcome.observed_sha256s:
            assert outcome.status.value in {"indeterminate", "not_applicable"}
        if len(outcome.observed_sha256s) > 1:
            assert outcome.status.value in {"indeterminate", "not_applicable"}


@settings(max_examples=200, deadline=None)
@given(bundle=_bundles())
def test_not_applicable_comes_only_from_a_predeclared_rule(
    bundle: EvaluationBundle,
) -> None:
    """Invariant 3: not-applicable requires a pre-observation rule."""

    outcomes = evaluate(bundle)
    for rule in bundle.rule_set.rules:
        outcome = _outcome_for(rule, outcomes)
        if rule.required:
            assert outcome.status.value != "not_applicable"
        else:
            assert outcome.status.value == "not_applicable"
            assert outcome.reason == "predeclared_not_applicable"


@settings(max_examples=200, deadline=None)
@given(
    bundle=_bundles(),
    observation_seed=st.randoms(use_true_random=False),
)
def test_identical_inputs_yield_byte_identical_receipts(
    bundle: EvaluationBundle, observation_seed: Any
) -> None:
    """Invariant 10: identical deterministic inputs, identical payloads."""

    first = render_receipt(build_receipt(bundle, evaluate(bundle)))
    permuted_observations = list(bundle.observations)
    permuted_rules = list(bundle.rule_set.rules)
    observation_seed.shuffle(permuted_observations)
    observation_seed.shuffle(permuted_rules)
    permuted = EvaluationBundle(
        case=bundle.case,
        observations=tuple(permuted_observations),
        rule_set=RuleSet(
            schema_version=bundle.rule_set.schema_version,
            rules=tuple(permuted_rules),
        ),
    )
    second = render_receipt(build_receipt(permuted, evaluate(permuted)))
    assert first == second


@settings(max_examples=200, deadline=None)
@given(bundle=_bundles())
def test_receipt_never_echoes_generated_semantic_values(
    bundle: EvaluationBundle,
) -> None:
    """Receipts stay value-minimized: hashes appear, semantic values do not."""

    rendered = render_receipt(build_receipt(bundle, evaluate(bundle)))
    assert _VALUE_MARKER not in rendered


@settings(max_examples=100, deadline=None)
@given(
    source_index=st.integers(min_value=0, max_value=4),
    target_concept=st.sampled_from(tuple(ConceptKind)),
)
def test_cross_concept_assignment_is_rejected_not_coerced(
    source_index: int, target_concept: ConceptKind
) -> None:
    """Invariants 4 and 9: a value can never cross canonical concept types."""

    case = json.loads((REFERENCE / "case.json").read_text(encoding="utf-8"))
    observations = json.loads(
        (REFERENCE / "observations.json").read_text(encoding="utf-8")
    )
    rules = json.loads((REFERENCE / "rules.json").read_text(encoding="utf-8"))
    entry = observations["observations"][source_index]
    if entry["concept"] == target_concept.value:
        parse_bundle(case, observations, rules)
        return
    entry["concept"] = target_concept.value
    try:
        parse_bundle(case, observations, rules)
    except ContextSafeError:
        return
    raise AssertionError("cross-concept observation was accepted")
