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

Since B-028 the generated rules name every predicate in ``RulePredicate``,
with the field each predicate reads drawn under the same constraints the
validator enforces, so the invariants are held over the whole predicate set
and not only over ``exact``: a pass always carries an affirmative reason and
at least one observation; a fail always carries a failure reason; no
observation at the rule's checkpoint is never pass; and every reason a receipt
publishes belongs to the status it accompanies.

The same generated bundles also feed the property-layer half of the
published receipt contract (B-033): every receipt document a generated
bundle produces must validate against
``schemas/contextsafe-receipt-v0.2.schema.json``.
"""

import json
from pathlib import Path
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st
from jsonschema import Draft202012Validator, FormatChecker

from contextsafe.canonical import sha256_json
from contextsafe.errors import ContextSafeError
from contextsafe.evaluator import Outcome, evaluate
from contextsafe.models import (
    AFFIRMATIVE_REASONS,
    CASE_SCHEMA_VERSION,
    FAILURE_REASONS,
    INDETERMINATE_REASONS,
    OBSERVATION_SCHEMA_VERSION,
    PREDICATE_RULE_SET_SCHEMA_VERSION,
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
)
from contextsafe.receipt import build_receipt, build_receipt_document, render_receipt
from contextsafe.reference_fixtures import REFERENCE_ROOT
from contextsafe.validation import parse_bundle

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = REFERENCE_ROOT
RECEIPT_SCHEMA = json.loads(
    (ROOT / "schemas" / "contextsafe-receipt-v0.2.schema.json").read_text(
        encoding="utf-8"
    )
)

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


_STATUS_CONCEPTS = (
    ConceptKind.GENDER_IDENTITY,
    ConceptKind.NAME_TO_USE,
    ConceptKind.PRONOUNS,
)


@st.composite
def _rules(draw: st.DrawFn, index: int) -> Rule:
    """Draw one rule under the concept constraints the validator enforces."""

    predicate = draw(st.sampled_from(tuple(RulePredicate)))
    if predicate in (RulePredicate.PRESENT, RulePredicate.STATUS_PRESERVED):
        concept = draw(st.sampled_from(_STATUS_CONCEPTS))
    elif predicate is RulePredicate.NOT_OVERWRITTEN_BY:
        concept = ConceptKind.GENDER_IDENTITY
    else:
        concept = draw(st.sampled_from(tuple(ConceptKind)))
    checkpoint = draw(st.sampled_from(tuple(Checkpoint)))
    expected = draw(_semantic_values(concept))
    forbidden: tuple[SemanticValue, ...] = ()
    if predicate is RulePredicate.NOT_COERCED:
        forbidden = tuple(
            item
            for item in draw(
                st.lists(_semantic_values(concept), min_size=1, max_size=3)
            )
            if item != expected
        ) or (draw(_semantic_values(concept).filter(lambda v: v != expected)),)
    return Rule(
        rule_id=f"A-I{index:02d}",
        version="0.1.0",
        case_id=draw(st.sampled_from(("CTP-P01", "CTP-P02"))),
        checkpoint=checkpoint,
        concept=concept,
        expected=expected,
        required=draw(st.booleans()),
        predicate=predicate,
        forbidden=forbidden,
        expected_count=(
            draw(st.integers(min_value=1, max_value=3))
            if predicate is RulePredicate.RECORD_COUNT
            else None
        ),
        preserved_from=(
            draw(
                st.sampled_from(tuple(Checkpoint)).filter(lambda c: c is not checkpoint)
            )
            if predicate is RulePredicate.PRESERVED_ACROSS
            else None
        ),
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
        rule_set=RuleSet(schema_version=PREDICATE_RULE_SET_SCHEMA_VERSION, rules=rules),
    )


def _outcome_for(rule: Rule, outcomes: tuple[Outcome, ...]) -> Outcome:
    matched = [item for item in outcomes if item.rule_id == rule.rule_id]
    assert len(matched) == 1
    return matched[0]


def _rule_of(bundle: EvaluationBundle, outcome: Outcome) -> Rule:
    return next(
        rule for rule in bundle.rule_set.rules if rule.rule_id == outcome.rule_id
    )


def _at_checkpoint(bundle: EvaluationBundle, rule: Rule, checkpoint: Checkpoint) -> int:
    return sum(
        1
        for item in bundle.observations
        if item.case_id == rule.case_id
        and item.checkpoint is checkpoint
        and item.concept is rule.concept
    )


@settings(max_examples=200, deadline=None)
@given(bundle=_bundles())
def test_pass_requires_affirmative_evidence_under_every_predicate(
    bundle: EvaluationBundle,
) -> None:
    """Invariant 1: missing or ambiguous evidence can never produce pass.

    ``exact`` keeps its stronger form: exactly one observation whose hash is
    the expected hash. Every other predicate still needs at least one
    observation at the rule's checkpoint, and the single-observation
    predicates need exactly one.
    """

    for outcome in evaluate(bundle):
        rule = _rule_of(bundle, outcome)
        at_checkpoint = _at_checkpoint(bundle, rule, rule.checkpoint)
        if outcome.status.value == "pass":
            assert outcome.observed_sha256s
            assert at_checkpoint >= 1
            if rule.predicate is RulePredicate.EXACT:
                assert outcome.observed_sha256s == (outcome.expected_sha256,)
            if rule.predicate not in (
                RulePredicate.RECORD_COUNT,
                RulePredicate.PRESERVED_ACROSS,
            ):
                assert at_checkpoint == 1
                assert len(outcome.observed_sha256s) == 1
            if rule.predicate is RulePredicate.PRESERVED_ACROSS:
                assert rule.preserved_from is not None
                assert _at_checkpoint(bundle, rule, rule.preserved_from) == 1
                assert len(set(outcome.observed_sha256s)) == 1
        if not outcome.observed_sha256s:
            assert outcome.status.value in {"indeterminate", "not_applicable"}
        if at_checkpoint == 0:
            assert outcome.status.value in {"indeterminate", "not_applicable"}
        if len(outcome.observed_sha256s) > 1 and rule.predicate not in (
            RulePredicate.RECORD_COUNT,
            RulePredicate.PRESERVED_ACROSS,
        ):
            assert outcome.status.value in {"indeterminate", "not_applicable"}


@settings(max_examples=200, deadline=None)
@given(bundle=_bundles())
def test_every_reason_belongs_to_the_status_it_accompanies(
    bundle: EvaluationBundle,
) -> None:
    """A receipt may not say pass with a failure reason, or the reverse."""

    for outcome in evaluate(bundle):
        if outcome.status.value == "pass":
            assert outcome.reason in AFFIRMATIVE_REASONS
        elif outcome.status.value == "fail":
            assert outcome.reason in FAILURE_REASONS
        elif outcome.status.value == "indeterminate":
            assert outcome.reason in INDETERMINATE_REASONS
        else:
            assert outcome.reason == "predeclared_not_applicable"


@settings(max_examples=200, deadline=None)
@given(bundle=_bundles())
def test_unsupported_values_are_never_coerced_into_a_forbidden_one(
    bundle: EvaluationBundle,
) -> None:
    """Invariant 4 over ``not_coerced``: an observation equal to a forbidden
    value is fail, and a pass never carries a forbidden hash."""

    for outcome in evaluate(bundle):
        rule = _rule_of(bundle, outcome)
        if rule.predicate is not RulePredicate.NOT_COERCED or not rule.required:
            continue
        forbidden = {sha256_json(item.to_dict()) for item in rule.forbidden}
        if outcome.status.value == "pass":
            assert forbidden.isdisjoint(outcome.observed_sha256s)
        if outcome.status.value == "fail":
            assert outcome.observed_sha256s[0] in forbidden


@settings(max_examples=200, deadline=None)
@given(bundle=_bundles())
def test_a_status_that_moved_never_passes_status_preserved(
    bundle: EvaluationBundle,
) -> None:
    """A-009 as an invariant: declined (or any status) that becomes another
    status is fail, whatever the value did."""

    for outcome in evaluate(bundle):
        rule = _rule_of(bundle, outcome)
        if rule.predicate is not RulePredicate.STATUS_PRESERVED:
            continue
        if outcome.status.value not in {"pass", "fail"}:
            continue
        observed = next(
            item
            for item in bundle.observations
            if item.case_id == rule.case_id
            and item.checkpoint is rule.checkpoint
            and item.concept is rule.concept
        )
        expected_status = getattr(rule.expected, "status")  # noqa: B009 - typed union
        observed_status = getattr(observed.value, "status")  # noqa: B009 - typed union
        assert (outcome.status.value == "pass") == (observed_status is expected_status)


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


@settings(max_examples=200, deadline=None)
@given(bundle=_bundles())
def test_generated_receipts_match_the_published_receipt_contract(
    bundle: EvaluationBundle,
) -> None:
    """B-033: every emitted document conforms to the published contract."""

    validator = Draft202012Validator(RECEIPT_SCHEMA, format_checker=FormatChecker())
    validator.validate(build_receipt_document(bundle, evaluate(bundle)))


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
