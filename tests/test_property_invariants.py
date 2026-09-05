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

An invariant is only as strong as the branches the generator reaches, so the
generator reaches ``pass`` and ``fail`` under every predicate by design rather
than by coincidence: for each rule it may emit one observation at every
checkpoint the predicate reads (both checkpoints of ``preserved_across``,
``expected_count`` of them for ``record_count``), and an aligned observation's
value is drawn from the cases each predicate decides on: the faithful value, a
forbidden value, a status-moved copy, another concept's scalar, or a fresh
value. ``test_the_generator_reaches_pass_and_fail_under_every_predicate`` is
the guard: a strategy change that stops reaching a branch fails there instead
of silently making the invariant above it vacuous.

The same generated bundles also feed the property-layer half of the
published receipt contract (B-033): every receipt document a generated
bundle produces must validate against
``schemas/contextsafe-receipt-v0.3.schema.json``.
"""

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from hypothesis import Phase, event, example, find, given, settings
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
    coercion_key,
)
from contextsafe.receipt import build_receipt, build_receipt_document, render_receipt
from contextsafe.reference_fixtures import REFERENCE_ROOT
from contextsafe.validation import parse_bundle

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = REFERENCE_ROOT
RECEIPT_SCHEMA = json.loads(
    (ROOT / "schemas" / "contextsafe-receipt-v0.3.schema.json").read_text(
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
_CASE_IDS = st.sampled_from(("CTP-P01", "CTP-P02"))


def _status_value(
    concept: ConceptKind, status: ValueStatus, token: str
) -> SemanticValue:
    """Build the status-bearing value of ``concept`` with ``status``."""

    scalar = token if status is ValueStatus.SPECIFIED else None
    if concept is ConceptKind.GENDER_IDENTITY:
        return GenderIdentity(
            status=status, value=scalar, code_system="urn:contextsafe:fixture"
        )
    if concept is ConceptKind.NAME_TO_USE:
        return NameToUse(
            status=status,
            value=None if scalar is None else f"CSYN-{scalar}",
            use="usual",
        )
    return Pronouns(status=status, value=scalar)


@st.composite
def _semantic_values(draw: st.DrawFn, concept: ConceptKind) -> SemanticValue:
    token = draw(_TOKENS)
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
    return _status_value(concept, draw(_STATUSES), token)


_STATUS_CONCEPTS = (
    ConceptKind.GENDER_IDENTITY,
    ConceptKind.NAME_TO_USE,
    ConceptKind.PRONOUNS,
)


@st.composite
def _forbidden_sets(
    draw: st.DrawFn, concept: ConceptKind, expected: SemanticValue
) -> tuple[SemanticValue, ...]:
    """Draw a forbidden set under the validator's constraints: one to three
    values, distinct in status and scalar, none sharing the expected value's
    status and scalar."""

    seen = {coercion_key(expected)}
    chosen: list[SemanticValue] = []
    for item in draw(st.lists(_semantic_values(concept), min_size=1, max_size=4)):
        if coercion_key(item) not in seen and len(chosen) < 3:
            seen.add(coercion_key(item))
            chosen.append(item)
    if not chosen:
        chosen.append(
            draw(
                _semantic_values(concept).filter(
                    lambda v: coercion_key(v) != coercion_key(expected)
                )
            )
        )
    return tuple(chosen)


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
        forbidden = draw(_forbidden_sets(concept, expected))
    return Rule(
        rule_id=f"A-I{index:02d}",
        version="0.1.0",
        case_id=draw(_CASE_IDS),
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


def _other_concept_scalars(
    case: SyntheticCase, concept: ConceptKind
) -> tuple[str, ...]:
    """Every scalar the case declares under a concept other than ``concept``."""

    declared: dict[ConceptKind, tuple[SemanticValue, ...]] = {
        ConceptKind.GENDER_IDENTITY: (case.gender_identity,),
        ConceptKind.RECORDED_SEX_OR_GENDER: case.recorded_sex_or_gender,
        ConceptKind.SEX_PARAMETER_FOR_CLINICAL_USE: (
            case.sex_parameter_for_clinical_use
        ),
        ConceptKind.NAME_TO_USE: (case.name_to_use,),
        ConceptKind.PRONOUNS: (case.pronouns,),
    }
    return tuple(
        value.value
        for other, values in declared.items()
        if other is not concept
        for value in values
        if value.value is not None
    )


def _restamped(value: SemanticValue, token: str) -> SemanticValue:
    """Return ``value`` with every descriptor around its status and scalar
    rewritten, the way a boundary that stamps its own context, source, code
    system, or order context on a record would leave it."""

    if isinstance(value, RecordedSexOrGender):
        return replace(value, context=token, source="interface-engine")
    if isinstance(value, GenderIdentity):
        return replace(value, code_system=f"urn:contextsafe:{token}")
    if isinstance(value, SexParameterForClinicalUse):
        return replace(value, context_id=f"ORDER-CSYN-{token}")
    return value


@st.composite
def _aligned_values(draw: st.DrawFn, rule: Rule, case: SyntheticCase) -> SemanticValue:
    """Draw the value of an observation the rule reads.

    The kinds are the branches the predicates decide on, faithful first so
    that predicates comparing two observations (``preserved_across``,
    ``record_count``) reach equality, then the faults: a forbidden value,
    verbatim or with its descriptors restamped by the boundary (A-014), a
    copy whose status moved (A-009), a gender identity that carries another
    concept's scalar (A-011), and last a fresh value. Hypothesis favours low
    indices when it simplifies, so the order is what keeps every fault kind
    reachable under a derandomized search.
    """

    kinds = ["faithful"]
    if rule.forbidden:
        kinds.extend(("forbidden", "restamped"))
    if rule.concept in _STATUS_CONCEPTS:
        kinds.append("moved")
    overwriting = _other_concept_scalars(case, rule.concept)
    if rule.concept is ConceptKind.GENDER_IDENTITY and overwriting:
        kinds.append("overwritten")
    kinds.append("fresh")
    kind = draw(st.sampled_from(kinds))
    if kind == "faithful":
        return rule.expected
    if kind == "forbidden":
        return draw(st.sampled_from(rule.forbidden))
    if kind == "restamped":
        return _restamped(draw(st.sampled_from(rule.forbidden)), draw(_TOKENS))
    if kind == "moved":
        expected_status = getattr(rule.expected, "status")  # noqa: B009 - typed union
        moved = draw(
            st.sampled_from(tuple(ValueStatus)).filter(
                lambda s: s is not expected_status
            )
        )
        return _status_value(rule.concept, moved, draw(_TOKENS))
    if kind == "overwritten":
        return GenderIdentity(
            status=ValueStatus.SPECIFIED,
            value=draw(st.sampled_from(overwriting)),
            code_system="urn:contextsafe:fixture",
        )
    return draw(_semantic_values(rule.concept))


def _observation_of(
    case_id: str,
    checkpoint: Checkpoint,
    concept: ConceptKind,
    value: SemanticValue,
    index: int,
) -> Observation:
    return Observation(
        schema_version=OBSERVATION_SCHEMA_VERSION,
        observation_id=f"OBS-P{index:02d}",
        case_id=case_id,
        checkpoint=checkpoint,
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


def _checkpoints_read(rule: Rule) -> tuple[Checkpoint, ...]:
    """The checkpoints the rule's predicate reads, one entry per observation
    the deliberate plan emits there."""

    if rule.predicate is RulePredicate.PRESERVED_ACROSS:
        assert rule.preserved_from is not None
        return (rule.preserved_from, rule.checkpoint)
    if rule.predicate is RulePredicate.RECORD_COUNT:
        assert rule.expected_count is not None
        return (rule.checkpoint,) * rule.expected_count
    return (rule.checkpoint,)


@st.composite
def _observations(
    draw: st.DrawFn, rule: Rule, index: int, case: SyntheticCase
) -> Observation:
    """One observation that may or may not be one the rule reads.

    An aligned observation sits at one of the checkpoints the predicate reads
    with a value from ``_aligned_values``; anything else is drawn at random
    so the evaluator's matching is exercised on case, checkpoint, and concept.
    """

    if draw(st.booleans()):
        checkpoint = draw(st.sampled_from(sorted(set(_checkpoints_read(rule)))))
        value = draw(_aligned_values(rule, case))
        return _observation_of(rule.case_id, checkpoint, rule.concept, value, index)
    concept = draw(st.sampled_from(tuple(ConceptKind)))
    return _observation_of(
        draw(_CASE_IDS),
        draw(st.sampled_from(tuple(Checkpoint))),
        concept,
        draw(_semantic_values(concept)),
        index,
    )


@st.composite
def _cases(draw: st.DrawFn) -> SyntheticCase:
    gender_identity = draw(_semantic_values(ConceptKind.GENDER_IDENTITY))
    name_to_use = draw(_semantic_values(ConceptKind.NAME_TO_USE))
    pronouns = draw(_semantic_values(ConceptKind.PRONOUNS))
    assert isinstance(gender_identity, GenderIdentity)
    assert isinstance(name_to_use, NameToUse)
    assert isinstance(pronouns, Pronouns)
    return SyntheticCase(
        schema_version=CASE_SCHEMA_VERSION,
        case_id="CTP-P01",
        synthetic_identifier=SyntheticIdentifier(
            system="urn:contextsafe:synthetic", value="CSYN-CTP-P01"
        ),
        gender_identity=gender_identity,
        recorded_sex_or_gender=(),
        sex_parameter_for_clinical_use=(),
        name_to_use=name_to_use,
        pronouns=pronouns,
        prohibited_inferences=(
            "gender_identity_to_spcu",
            "recorded_sex_or_gender_to_spcu",
        ),
    )


@st.composite
def _bundles(draw: st.DrawFn) -> EvaluationBundle:
    case = draw(_cases())
    rule_count = draw(st.integers(min_value=1, max_value=4))
    rules = tuple(draw(_rules(index)) for index in range(rule_count))
    observations: list[Observation] = []
    index = 0
    for rule in rules:
        if draw(st.booleans()):
            # The deliberate plan: exactly what the predicate reads, so pass
            # and fail are decided by the values and not by evidence count.
            for checkpoint in _checkpoints_read(rule):
                value = draw(_aligned_values(rule, case))
                observations.append(
                    _observation_of(
                        rule.case_id, checkpoint, rule.concept, value, index
                    )
                )
                index += 1
            continue
        for _ in range(draw(st.integers(min_value=0, max_value=3))):
            observations.append(draw(_observations(rule, index, case)))
            index += 1
    return EvaluationBundle(
        case=case,
        observations=tuple(observations),
        rule_set=RuleSet(schema_version=PREDICATE_RULE_SET_SCHEMA_VERSION, rules=rules),
    )


_EXAMPLE_CASE = SyntheticCase(
    schema_version=CASE_SCHEMA_VERSION,
    case_id="CTP-P01",
    synthetic_identifier=SyntheticIdentifier(
        system="urn:contextsafe:synthetic", value="CSYN-CTP-P01"
    ),
    gender_identity=GenderIdentity(
        status=ValueStatus.SPECIFIED,
        value=f"{_VALUE_MARKER}-A",
        code_system="urn:contextsafe:fixture",
    ),
    recorded_sex_or_gender=(),
    sex_parameter_for_clinical_use=(),
    name_to_use=NameToUse(
        status=ValueStatus.SPECIFIED, value=f"CSYN-{_VALUE_MARKER}-B", use="usual"
    ),
    pronouns=Pronouns(status=ValueStatus.SPECIFIED, value=f"{_VALUE_MARKER}-C"),
    prohibited_inferences=(
        "gender_identity_to_spcu",
        "recorded_sex_or_gender_to_spcu",
    ),
)
_EXAMPLE_RULE = Rule(
    rule_id="A-I00",
    version="0.1.0",
    case_id="CTP-P01",
    checkpoint=Checkpoint.EHR,
    concept=ConceptKind.NAME_TO_USE,
    expected=_EXAMPLE_CASE.name_to_use,
    required=True,
    predicate=RulePredicate.PRESERVED_ACROSS,
    preserved_from=Checkpoint.REGISTRATION,
)
PRESERVED_ACROSS_PASS = EvaluationBundle(
    case=_EXAMPLE_CASE,
    observations=(
        _observation_of(
            "CTP-P01",
            Checkpoint.REGISTRATION,
            ConceptKind.NAME_TO_USE,
            _EXAMPLE_CASE.name_to_use,
            0,
        ),
        _observation_of(
            "CTP-P01",
            Checkpoint.EHR,
            ConceptKind.NAME_TO_USE,
            _EXAMPLE_CASE.name_to_use,
            1,
        ),
    ),
    rule_set=RuleSet(
        schema_version=PREDICATE_RULE_SET_SCHEMA_VERSION, rules=(_EXAMPLE_RULE,)
    ),
)
"""The one bundle every run must see: a source and a target observation with
the same hash, so the ``preserved_across`` pass branch is exercised even if
the generator never draws it."""


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


def _reaches(bundle: EvaluationBundle, predicate: RulePredicate, status: str) -> bool:
    return any(
        outcome.status.value == status
        and _rule_of(bundle, outcome).predicate is predicate
        for outcome in evaluate(bundle)
    )


def _single_observation(bundle: EvaluationBundle, rule: Rule) -> Observation:
    """The one observation a decided single-observation predicate read."""

    return next(
        item
        for item in bundle.observations
        if item.case_id == rule.case_id
        and item.checkpoint is rule.checkpoint
        and item.concept is rule.concept
    )


@settings(max_examples=200, deadline=None)
@example(bundle=PRESERVED_ACROSS_PASS)
@given(bundle=_bundles())
def test_pass_requires_affirmative_evidence_under_every_predicate(
    bundle: EvaluationBundle,
) -> None:
    """Invariant 1: missing or ambiguous evidence can never produce pass.

    ``exact`` keeps its stronger form: exactly one observation whose hash is
    the expected hash. Every other predicate still needs at least one
    observation at the rule's checkpoint, the single-observation predicates
    need exactly one, and ``preserved_across`` needs exactly one at each of
    its two checkpoints with one hash between them.
    """

    for outcome in evaluate(bundle):
        rule = _rule_of(bundle, outcome)
        event(f"{rule.predicate.value}:{outcome.status.value}")
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
                assert at_checkpoint == 1
                assert _at_checkpoint(bundle, rule, rule.preserved_from) == 1
                assert len(outcome.observed_sha256s) == 2
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


def test_the_explicit_example_is_a_preserved_across_pass() -> None:
    """The pinned example must itself be the branch it is there to exercise."""

    (outcome,) = evaluate(PRESERVED_ACROSS_PASS)
    assert outcome.status.value == "pass"
    assert outcome.reason == "value_preserved_across_checkpoints"
    assert outcome.reason in AFFIRMATIVE_REASONS
    assert len(outcome.observed_sha256s) == 2
    assert set(outcome.observed_sha256s) == {outcome.expected_sha256}


@pytest.mark.parametrize(
    ("predicate", "status"),
    [(predicate, status) for predicate in RulePredicate for status in ("pass", "fail")],
    ids=lambda value: value.value if isinstance(value, RulePredicate) else value,
)
def test_the_generator_reaches_pass_and_fail_under_every_predicate(
    predicate: RulePredicate, status: str
) -> None:
    """The coverage guard for every ``@given`` above.

    A generated bundle in which some rule with ``predicate`` is reported with
    ``status`` must exist within a bounded search; otherwise an invariant over
    that branch is asserting nothing and the strategy, not the evaluator, is
    what changed. ``find`` raises ``NoSuchExample`` when the search fails.
    The search is derandomized, so the same bundle is found on every run.
    """

    found = find(
        _bundles(),
        lambda bundle: _reaches(bundle, predicate, status),
        settings=settings(
            max_examples=500,
            deadline=None,
            database=None,
            derandomize=True,
            # The guard asks whether the branch is reachable, not for the
            # smallest bundle that reaches it, so it does not shrink.
            phases=(Phase.generate,),
        ),
    )
    assert _reaches(found, predicate, status)


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
    """Invariant 4 over ``not_coerced``: an observation whose status and
    scalar are a forbidden value's is fail, whatever else the boundary wrote
    around it, and a pass never carries a forbidden status and scalar."""

    for outcome in evaluate(bundle):
        rule = _rule_of(bundle, outcome)
        if rule.predicate is not RulePredicate.NOT_COERCED or not rule.required:
            continue
        if outcome.status.value not in {"pass", "fail"}:
            continue
        forbidden = {coercion_key(item) for item in rule.forbidden}
        observed = coercion_key(_single_observation(bundle, rule).value)
        assert (outcome.status.value == "fail") == (observed in forbidden)


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
        observed = _single_observation(bundle, rule)
        expected_status = getattr(rule.expected, "status")  # noqa: B009 - typed union
        observed_status = getattr(observed.value, "status")  # noqa: B009 - typed union
        assert (outcome.status.value == "pass") == (observed_status is expected_status)


@settings(max_examples=200, deadline=None)
@given(bundle=_bundles())
def test_a_gender_identity_carrying_another_concepts_scalar_never_passes(
    bundle: EvaluationBundle,
) -> None:
    """A-011 as an invariant: an observed gender identity whose scalar the
    case declares under another concept is fail, and a pass never carries
    one."""

    for outcome in evaluate(bundle):
        rule = _rule_of(bundle, outcome)
        if rule.predicate is not RulePredicate.NOT_OVERWRITTEN_BY:
            continue
        if outcome.status.value not in {"pass", "fail"}:
            continue
        observed = _single_observation(bundle, rule).value.value
        overwritten = observed is not None and (
            observed in _other_concept_scalars(bundle.case, rule.concept)
        )
        assert (outcome.status.value == "fail") == overwritten


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
