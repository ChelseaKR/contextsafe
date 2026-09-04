"""First observed divergence and the evidence trace (B-031, A-032 to A-035).

Three things are held here, each in a unit form and a property form.

**A-034: only an observed boundary is ever named.** The divergence for a
concept locates itself at the first observed checkpoint whose value hashes
depart from the expectation (``from_expected``) or from the previous observed
checkpoint (``from_previous``). When the checkpoint between two observed ones
is unobserved, the entry names the two observed sides and there is no field
in which the gap could be named. The property tests hold that reordering the
observations never changes the section, and that deleting every observation
at one checkpoint never moves blame onto a different observed boundary: the
located checkpoint stays put unless it was the one deleted, and it is never
the deleted one.

**A-032: absence is not agreement.** A checkpoint with no evidence is
``unobserved``; a concept with no evidence anywhere is ``unobserved``; a
checkpoint that cannot be read as one state is ``ambiguous`` and the concept
is ``indeterminate`` from there on. None of these is ever
``agreed_where_observed``.

**A-035: every outcome traces to its sources through structural pointers.**
The trace carries the source hash and pointer of each observation the
predicate read and the version and hash of each mapping, and the validator
refuses any pointer whose segments are not in the closed structural
vocabulary, so the property here is that an identity-bearing pointer cannot
enter an observation set at all, and every pointer a receipt carries is a
path of published words and integers.
"""

import json
import re
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from contextsafe.canonical import JsonValue, sha256_json
from contextsafe.divergence import (
    CheckpointState,
    ConceptDivergence,
    Divergence,
    compute_divergence,
)
from contextsafe.errors import ContextSafeError
from contextsafe.evaluator import Trace, evaluate, trace_of
from contextsafe.models import (
    CASE_SCHEMA_VERSION,
    OBSERVATION_SCHEMA_VERSION,
    PATHWAY,
    RULE_SET_SCHEMA_VERSION,
    Checkpoint,
    ConceptKind,
    DivergenceStatus,
    EvaluationBundle,
    EvidencePointer,
    EvidenceState,
    GenderIdentity,
    MappingDescriptor,
    NameToUse,
    Observation,
    OutcomeStatus,
    Pronouns,
    RecordedSexOrGender,
    Rule,
    RuleSet,
    SemanticValue,
    SyntheticCase,
    SyntheticIdentifier,
    ValueStatus,
)
from contextsafe.receipt import build_receipt, render_receipt
from contextsafe.reference_fixtures import REFERENCE_ROOT
from contextsafe.validation import (
    STRUCTURAL_POINTER_SEGMENTS,
    parse_bundle,
    parse_observations,
)

_WORDS = "|".join(sorted(STRUCTURAL_POINTER_SEGMENTS))
_INDEX = r"(?:0|[1-9][0-9]*)"
_STRUCTURAL = re.compile(
    r"^(?:"
    r"\$(?:\.(?:" + _WORDS + r")|\[" + _INDEX + r"\])+"
    r"|\$\.(?:" + _WORDS + r")\[" + _INDEX + r"\]-" + _INDEX + r"\." + _INDEX + r"\." + _INDEX
    + r"|(?:/(?:" + _WORDS + r"|" + _INDEX + r"))+"
    r")$"
)
    + r")|\[(?:0|[1-9][0-9]*)\])+$"
)

_NAME_A = NameToUse(status=ValueStatus.SPECIFIED, value="CSYN-ASTER", use="usual")
_NAME_B = NameToUse(status=ValueStatus.SPECIFIED, value="CSYN-WREN", use="usual")
_NAME_C = NameToUse(status=ValueStatus.SPECIFIED, value="CSYN-ROWAN", use="usual")
_RSG_X = RecordedSexOrGender(value="X", context="government-id", source="synthetic")
_RSG_F = RecordedSexOrGender(value="F", context="payer", source="synthetic")
_RSG_M = RecordedSexOrGender(value="M", context="payer", source="synthetic")

CASE = SyntheticCase(
    schema_version=CASE_SCHEMA_VERSION,
    case_id="CTP-D01",
    synthetic_identifier=SyntheticIdentifier(
        system="urn:contextsafe:synthetic", value="CSYN-CTP-D01"
    ),
    gender_identity=GenderIdentity(
        status=ValueStatus.SPECIFIED,
        value="fixture-gender-1",
        code_system="urn:contextsafe:fixture",
    ),
    recorded_sex_or_gender=(_RSG_X, _RSG_F),
    sex_parameter_for_clinical_use=(),
    name_to_use=_NAME_A,
    pronouns=Pronouns(status=ValueStatus.SPECIFIED, value="they/them"),
    prohibited_inferences=("gender_identity_to_spcu", "recorded_sex_or_gender_to_spcu"),
)

RULE = Rule(
    rule_id="A-I01",
    version="0.1.0",
    case_id=CASE.case_id,
    checkpoint=Checkpoint.EHR,
    concept=ConceptKind.NAME_TO_USE,
    expected=_NAME_A,
    required=True,
)


def _observation(
    checkpoint: Checkpoint,
    value: SemanticValue,
    index: int,
    *,
    concept: ConceptKind = ConceptKind.NAME_TO_USE,
    pointer: str = "$.concepts.name_to_use",
    mapping_version: str = "0.1.0",
) -> Observation:
    return Observation(
        schema_version=OBSERVATION_SCHEMA_VERSION,
        observation_id=f"OBS-D{index:02d}",
        case_id=CASE.case_id,
        checkpoint=checkpoint,
        concept=concept,
        value=value,
        evidence=EvidencePointer(
            source_sha256=sha256_json([checkpoint.value, index]),
            source_pointer=pointer,
        ),
        mapping=MappingDescriptor(
            source_concept=concept,
            target_concept=concept,
            mapping_version=mapping_version,
        ),
    )


def _bundle(*observations: Observation) -> EvaluationBundle:
    return EvaluationBundle(
        case=CASE,
        observations=observations,
        rule_set=RuleSet(schema_version=RULE_SET_SCHEMA_VERSION, rules=(RULE,)),
    )


def _entry(divergence: Divergence, concept: ConceptKind) -> ConceptDivergence:
    return next(item for item in divergence.concepts if item.concept is concept)


def _name(*observations: Observation) -> ConceptDivergence:
    return _entry(compute_divergence(_bundle(*observations)), ConceptKind.NAME_TO_USE)


def _states(entry: ConceptDivergence) -> list[EvidenceState]:
    return [item.state for item in entry.checkpoints]


# --- unit: each status, and what it may and may not say -------------------


def test_a_concept_with_no_evidence_anywhere_is_unobserved_not_agreed() -> None:
    entry = _name()
    assert _states(entry) == [EvidenceState.UNOBSERVED] * 4
    assert entry.from_expected.status is DivergenceStatus.UNOBSERVED
    assert entry.from_expected.at is None
    assert entry.from_previous.status is DivergenceStatus.UNOBSERVED
    assert (entry.from_previous.after, entry.from_previous.at) == (None, None)


def test_one_faithful_observation_agrees_where_observed_and_compares_nothing() -> None:
    entry = _name(_observation(Checkpoint.EHR, _NAME_A, 0))
    assert _states(entry) == [
        EvidenceState.UNOBSERVED,
        EvidenceState.OBSERVED,
        EvidenceState.UNOBSERVED,
        EvidenceState.UNOBSERVED,
    ]
    assert entry.from_expected.status is DivergenceStatus.AGREED_WHERE_OBSERVED
    assert entry.from_previous.status is DivergenceStatus.UNOBSERVED
    assert entry.checkpoints[1].value_sha256s == entry.expected_sha256s


def test_the_first_departure_from_the_expectation_is_named_and_later_ones_are_not() -> (
    None
):
    entry = _name(
        _observation(Checkpoint.REGISTRATION, _NAME_A, 0),
        _observation(Checkpoint.EHR, _NAME_B, 1),
        _observation(Checkpoint.INTERFACE, _NAME_C, 2),
        _observation(Checkpoint.LIS_RETURN, _NAME_C, 3),
    )
    assert entry.from_expected.status is DivergenceStatus.DIVERGED
    assert entry.from_expected.at is Checkpoint.EHR
    assert entry.from_previous.status is DivergenceStatus.DIVERGED
    assert entry.from_previous.after is Checkpoint.REGISTRATION
    assert entry.from_previous.at is Checkpoint.EHR


def test_a_value_wrong_everywhere_diverges_from_expected_but_not_from_itself() -> None:
    """The two comparisons are separate claims: wrong and stable is both."""

    entry = _name(
        _observation(Checkpoint.REGISTRATION, _NAME_B, 0),
        _observation(Checkpoint.LIS_RETURN, _NAME_B, 1),
    )
    assert entry.from_expected.status is DivergenceStatus.DIVERGED
    assert entry.from_expected.at is Checkpoint.REGISTRATION
    assert entry.from_previous.status is DivergenceStatus.AGREED_WHERE_OBSERVED


def test_a_divergence_across_an_unobserved_gap_is_located_between_the_observed_sides() -> (
    None
):
    """A-034 and F-025: the unobserved EHR is never the answer."""

    entry = _name(
        _observation(Checkpoint.REGISTRATION, _NAME_A, 0),
        _observation(Checkpoint.INTERFACE, _NAME_B, 1),
        _observation(Checkpoint.LIS_RETURN, _NAME_B, 2),
    )
    assert entry.checkpoints[1].state is EvidenceState.UNOBSERVED
    assert entry.from_expected.at is Checkpoint.INTERFACE
    assert entry.from_previous.after is Checkpoint.REGISTRATION
    assert entry.from_previous.at is Checkpoint.INTERFACE
    assert Checkpoint.EHR not in (
        entry.from_expected.at,
        entry.from_previous.after,
        entry.from_previous.at,
    )


def test_two_values_of_a_single_valued_concept_at_one_boundary_are_ambiguous() -> None:
    """A-032: ambiguity is indeterminate, never a divergence and never a pass."""

    entry = _name(
        _observation(Checkpoint.REGISTRATION, _NAME_A, 0),
        _observation(Checkpoint.EHR, _NAME_A, 1),
        _observation(Checkpoint.EHR, _NAME_B, 2),
        _observation(Checkpoint.LIS_RETURN, _NAME_B, 3),
    )
    assert entry.checkpoints[1].state is EvidenceState.AMBIGUOUS
    assert len(entry.checkpoints[1].value_sha256s) == 2
    assert entry.from_expected.status is DivergenceStatus.INDETERMINATE
    assert entry.from_expected.at is Checkpoint.EHR
    assert entry.from_previous.status is DivergenceStatus.INDETERMINATE
    assert entry.from_previous.after is Checkpoint.REGISTRATION
    assert entry.from_previous.at is Checkpoint.EHR


def test_the_same_single_value_captured_twice_is_still_ambiguous() -> None:
    entry = _name(
        _observation(Checkpoint.EHR, _NAME_A, 0),
        _observation(Checkpoint.EHR, _NAME_A, 1),
    )
    assert entry.checkpoints[1].state is EvidenceState.AMBIGUOUS
    assert entry.from_expected.status is DivergenceStatus.INDETERMINATE
    assert entry.from_previous.status is DivergenceStatus.INDETERMINATE
    assert entry.from_previous.after is None


def test_an_ambiguous_boundary_reached_first_stops_the_walk_there() -> None:
    """A later clean divergence is not reported past an ambiguity."""

    entry = _name(
        _observation(Checkpoint.REGISTRATION, _NAME_A, 0),
        _observation(Checkpoint.REGISTRATION, _NAME_B, 1),
        _observation(Checkpoint.INTERFACE, _NAME_C, 2),
    )
    assert entry.from_expected.status is DivergenceStatus.INDETERMINATE
    assert entry.from_expected.at is Checkpoint.REGISTRATION
    assert entry.from_previous.at is Checkpoint.REGISTRATION


def _rsg(*observations: Observation) -> ConceptDivergence:
    return _entry(
        compute_divergence(_bundle(*observations)), ConceptKind.RECORDED_SEX_OR_GENDER
    )


def _rsg_observation(
    checkpoint: Checkpoint, value: SemanticValue, index: int
) -> Observation:
    return _observation(
        checkpoint,
        value,
        index,
        concept=ConceptKind.RECORDED_SEX_OR_GENDER,
        pointer="$.concepts.recorded_sex_or_gender[0]",
    )


def test_two_distinct_records_of_a_record_list_are_one_observed_state() -> None:
    entry = _rsg(
        _rsg_observation(Checkpoint.REGISTRATION, _RSG_X, 0),
        _rsg_observation(Checkpoint.REGISTRATION, _RSG_F, 1),
    )
    assert entry.checkpoints[0].state is EvidenceState.OBSERVED
    assert entry.checkpoints[0].value_sha256s == entry.expected_sha256s
    assert len(entry.expected_sha256s) == 2
    assert entry.from_expected.status is DivergenceStatus.AGREED_WHERE_OBSERVED


def test_a_collapsed_record_list_diverges_at_the_boundary_it_collapsed() -> None:
    entry = _rsg(
        _rsg_observation(Checkpoint.REGISTRATION, _RSG_X, 0),
        _rsg_observation(Checkpoint.REGISTRATION, _RSG_F, 1),
        _rsg_observation(Checkpoint.EHR, _RSG_F, 2),
    )
    assert entry.from_expected.status is DivergenceStatus.DIVERGED
    assert entry.from_expected.at is Checkpoint.EHR
    assert entry.from_previous.after is Checkpoint.REGISTRATION
    assert entry.from_previous.at is Checkpoint.EHR


def test_a_record_captured_twice_is_ambiguous_not_two_records() -> None:
    entry = _rsg(
        _rsg_observation(Checkpoint.REGISTRATION, _RSG_X, 0),
        _rsg_observation(Checkpoint.REGISTRATION, _RSG_X, 1),
    )
    assert entry.checkpoints[0].state is EvidenceState.AMBIGUOUS
    assert entry.from_expected.status is DivergenceStatus.INDETERMINATE


def test_a_record_the_manifest_never_declared_is_a_divergence() -> None:
    entry = _rsg(
        _rsg_observation(Checkpoint.REGISTRATION, _RSG_X, 0),
        _rsg_observation(Checkpoint.REGISTRATION, _RSG_M, 1),
    )
    assert entry.from_expected.status is DivergenceStatus.DIVERGED
    assert entry.from_expected.at is Checkpoint.REGISTRATION


def test_a_concept_the_manifest_declares_nothing_for_expects_no_hashes() -> None:
    """SPCU is empty in this case: anything observed there is a divergence."""

    entry = _entry(
        compute_divergence(_bundle()), ConceptKind.SEX_PARAMETER_FOR_CLINICAL_USE
    )
    assert entry.expected_sha256s == ()
    assert entry.from_expected.status is DivergenceStatus.UNOBSERVED


def test_the_section_covers_every_concept_in_manifest_order() -> None:
    divergence = compute_divergence(_bundle())
    assert [item.concept for item in divergence.concepts] == list(ConceptKind)
    rendered = divergence.to_dict()
    assert rendered["pathway"] == [item.value for item in PATHWAY]
    for entry in divergence.concepts:
        assert [item.checkpoint for item in entry.checkpoints] == list(PATHWAY)


def test_observations_of_another_case_are_not_read() -> None:
    foreign = Observation(
        schema_version=OBSERVATION_SCHEMA_VERSION,
        observation_id="OBS-D99",
        case_id="CTP-D02",
        checkpoint=Checkpoint.EHR,
        concept=ConceptKind.NAME_TO_USE,
        value=_NAME_B,
        evidence=EvidencePointer(
            source_sha256="0" * 64, source_pointer="$.concepts.name_to_use"
        ),
        mapping=MappingDescriptor(
            source_concept=ConceptKind.NAME_TO_USE,
            target_concept=ConceptKind.NAME_TO_USE,
            mapping_version="0.1.0",
        ),
    )
    entry = _name(foreign)
    assert entry.from_expected.status is DivergenceStatus.UNOBSERVED


def test_rules_do_not_reach_the_divergence_section() -> None:
    """The section is a property of the evidence against the manifest."""

    with_rule = _bundle(_observation(Checkpoint.EHR, _NAME_B, 0))
    without = EvaluationBundle(
        case=with_rule.case,
        observations=with_rule.observations,
        rule_set=RuleSet(
            schema_version=RULE_SET_SCHEMA_VERSION,
            rules=(
                Rule(
                    rule_id="A-I02",
                    version="0.1.0",
                    case_id=CASE.case_id,
                    checkpoint=Checkpoint.LIS_RETURN,
                    concept=ConceptKind.PRONOUNS,
                    expected=CASE.pronouns,
                    required=False,
                ),
            ),
        ),
    )
    assert compute_divergence(with_rule) == compute_divergence(without)


def test_the_receipt_section_carries_hashes_checkpoints_and_statuses_only() -> None:
    bundle = _bundle(
        _observation(Checkpoint.REGISTRATION, _NAME_A, 0),
        _observation(Checkpoint.INTERFACE, _NAME_B, 1),
    )
    rendered = render_receipt(build_receipt(bundle, evaluate(bundle)))
    section = json.loads(rendered)["divergence"]
    assert set(section) == {"concepts", "pathway"}
    for entry in section["concepts"]:
        assert set(entry) == {
            "checkpoints",
            "concept",
            "expected_sha256s",
            "from_expected",
            "from_previous",
        }
        assert set(entry["from_expected"]) == {"at", "status"}
        assert set(entry["from_previous"]) == {"after", "at", "status"}
    for token in ("CSYN-ASTER", "CSYN-WREN", "government-id", "they/them"):
        assert token not in json.dumps(section)


# --- unit: the evidence trace (A-035) ---------------------------------------


def test_every_outcome_traces_to_the_sources_and_mappings_it_read() -> None:
    bundle = _bundle(_observation(Checkpoint.EHR, _NAME_A, 0, mapping_version="0.2.0"))
    (outcome,) = evaluate(bundle)
    (observation,) = bundle.observations
    assert outcome.status is OutcomeStatus.PASSED
    assert outcome.trace.sources == (observation.evidence,)
    (mapping,) = outcome.trace.mappings
    assert mapping.mapping_version == "0.2.0"
    assert mapping.mapping_sha256 == sha256_json(observation.mapping.to_dict())
    rendered = outcome.to_dict()["trace"]
    assert rendered == {
        "mappings": [
            {"mapping_sha256": mapping.mapping_sha256, "mapping_version": "0.2.0"}
        ],
        "sources": [
            {
                "source_pointer": "$.concepts.name_to_use",
                "source_sha256": observation.evidence.source_sha256,
            }
        ],
    }


def test_missing_evidence_has_an_empty_trace() -> None:
    (outcome,) = evaluate(_bundle())
    assert outcome.status is OutcomeStatus.INDETERMINATE
    assert outcome.trace == Trace()
    assert outcome.to_dict()["trace"] == {"mappings": [], "sources": []}


def test_an_ambiguous_outcome_traces_every_observation_it_saw() -> None:
    bundle = _bundle(
        _observation(Checkpoint.EHR, _NAME_A, 0),
        _observation(Checkpoint.EHR, _NAME_B, 1, mapping_version="0.2.0"),
    )
    (outcome,) = evaluate(bundle)
    assert outcome.status is OutcomeStatus.INDETERMINATE
    assert len(outcome.trace.sources) == 2
    assert [item.mapping_version for item in outcome.trace.mappings] == [
        "0.1.0",
        "0.2.0",
    ]


def test_the_trace_is_independent_of_observation_order() -> None:
    first = _observation(Checkpoint.EHR, _NAME_A, 0)
    second = _observation(Checkpoint.EHR, _NAME_B, 1, mapping_version="0.2.0")
    assert trace_of((first, second)) == trace_of((second, first))


def test_a_mapping_version_change_changes_the_trace_and_the_payload() -> None:
    """F-035 in the one form this slice can see: the mapping is bound."""

    before = _bundle(_observation(Checkpoint.EHR, _NAME_A, 0))
    after = _bundle(_observation(Checkpoint.EHR, _NAME_A, 0, mapping_version="0.2.0"))
    first = build_receipt(before, evaluate(before))
    second = build_receipt(after, evaluate(after))
    assert first["hashes"]["result_sha256"] != second["hashes"]["result_sha256"]
    assert first["hashes"]["input_sha256"] != second["hashes"]["input_sha256"]


# --- unit: what a pointer may be (A-035) ------------------------------------


@pytest.mark.parametrize(
    "pointer",
    [
        "$.CSYN-ASTER",
        "$.concepts.Aster",
        "$.patient.name",
        "$.concepts.name_to_use.they-them",
        "$.concepts.legal_name",
        "$.records[01]",
        "$..concepts",
        "$.concepts.",
        "$.concepts[0]x",
        "$.Concepts",
    ],
)
def test_an_observation_with_a_non_structural_pointer_is_refused(
    observations_json: dict[str, Any], pointer: str
) -> None:
    """The whole set is refused; the pointer is not carried, hashed, or dropped."""

    observations_json["observations"][0]["evidence"]["source_pointer"] = pointer
    with pytest.raises(ContextSafeError) as raised:
        parse_observations(observations_json)
    assert raised.value.code == "non_structural_pointer"
    assert raised.value.path == "$.observations[0].evidence.source_pointer"
    assert pointer not in raised.value.message


@pytest.mark.parametrize(
    "pointer",
    [
        "$.concepts",
        "$.concepts.recorded_sex_or_gender[1]",
        "$.records[12].value_code",
        "$[0]",
        "$.records[0].context_code",
    ],
)
def test_a_structural_pointer_is_accepted(
    observations_json: dict[str, Any], pointer: str
) -> None:
    observations_json["observations"][0]["evidence"]["source_pointer"] = pointer
    parsed = parse_observations(observations_json)
    assert parsed[0].evidence.source_pointer == pointer


def test_the_reference_receipt_carries_only_structural_pointers(
    case_json: dict[str, Any],
    observations_json: dict[str, Any],
    rules_json: dict[str, Any],
) -> None:
    bundle = parse_bundle(case_json, observations_json, rules_json)
    receipt = build_receipt(bundle, evaluate(bundle))
    pointers = [
        source["source_pointer"]
        for outcome in receipt["results"]
        for source in outcome["trace"]["sources"]  # type: ignore[index]
    ]
    assert pointers
    for pointer in pointers:
        assert _STRUCTURAL.fullmatch(str(pointer))


_POINTER_CHARS = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-.[]",
    min_size=1,
    max_size=40,
)
_SEGMENT_WORDS = st.sampled_from(sorted(STRUCTURAL_POINTER_SEGMENTS))
_STRUCTURAL_POINTERS = st.lists(
    st.one_of(
        _SEGMENT_WORDS.map(lambda word: f".{word}"),
        st.integers(min_value=0, max_value=999).map(lambda n: f"[{n}]"),
    ),
    min_size=1,
    max_size=6,
).map(lambda parts: "$" + "".join(parts))


@settings(max_examples=300, deadline=None)
@given(pointer=st.one_of(_POINTER_CHARS.map(lambda s: f"${s}"), _STRUCTURAL_POINTERS))
def test_nothing_but_structural_segments_can_reach_a_receipt(pointer: str) -> None:
    """A-035 as an invariant: refused at the boundary, or provably structural.

    Half the pointers are drawn from the pointer alphabet at random, so they
    include identity-shaped words; half are built from the vocabulary. The
    validator refuses the first kind and accepts the second, and whatever it
    accepts satisfies the published grammar, which admits no other word.
    """

    document = json.loads(
        (REFERENCE_ROOT / "observations.json").read_text(encoding="utf-8")
    )
    document["observations"][0]["evidence"]["source_pointer"] = pointer
    try:
        parsed = parse_observations(document)
    except ContextSafeError as exc:
        assert exc.code in {
            "non_structural_pointer",
            "invalid_format",
            "invalid_string",
        }
        assert _STRUCTURAL.fullmatch(pointer) is None
        return
    accepted = parsed[0].evidence.source_pointer
    assert accepted == pointer
    assert _STRUCTURAL.fullmatch(accepted)
    for segment in re.findall(r"[./]([A-Za-z_][A-Za-z0-9_-]*)", accepted):
        assert segment in STRUCTURAL_POINTER_SEGMENTS


# --- the three pointer dialects ------------------------------------------------

_READER_POINTERS = (
    "/name/0",
    "/entry/0/resource/extension/1",
    "$.PID[1]-5.1.1",
    "$.rows[0].sex",
    "$.records[0]",
)
_FREE_TEXT_POINTERS = (
    "/text/0",
    "/name/x",
    "$.ZZZ[1]-5.1.1",
    "$.PID[1]-5.1",
    "$.rows[0].patient",
)


def _with_pointer(pointer: str) -> dict[str, JsonValue]:
    document = json.loads(
        (REFERENCE_ROOT / "observations.json").read_text(encoding="utf-8")
    )
    document["observations"][0]["evidence"]["source_pointer"] = pointer
    return document  # type: ignore[no-any-return]


@pytest.mark.parametrize("pointer", _READER_POINTERS)
def test_every_reader_dialect_is_accepted_over_the_vocabulary(pointer: str) -> None:
    """Canonical, FHIR (RFC 6901), HL7 v2 and LIS pointers all pass, unchanged."""

    parsed = parse_observations(_with_pointer(pointer))
    assert parsed[0].evidence.source_pointer == pointer
    assert _STRUCTURAL.fullmatch(pointer)


@pytest.mark.parametrize("pointer", _FREE_TEXT_POINTERS)
def test_a_word_outside_the_vocabulary_is_refused_in_every_dialect(
    pointer: str,
) -> None:
    """The alphabet admits each of these; the vocabulary does not."""

    with pytest.raises(ContextSafeError) as raised:
        parse_observations(_with_pointer(pointer))
    assert raised.value.code == "non_structural_pointer"
    assert _STRUCTURAL.fullmatch(pointer) is None


# --- property: A-034 over generated observation sets ------------------------

_VALUES = (_NAME_A, _NAME_B, _NAME_C)


@st.composite
def _observation_sets(draw: st.DrawFn) -> tuple[Observation, ...]:
    """Zero to two name-to-use observations at each checkpoint, any values.

    Two at one checkpoint makes that checkpoint ambiguous, so every evidence
    state and every divergence status is reachable.
    """

    observations: list[Observation] = []
    index = 0
    for checkpoint in PATHWAY:
        for _ in range(draw(st.integers(min_value=0, max_value=2))):
            value = draw(st.sampled_from(_VALUES))
            observations.append(_observation(checkpoint, value, index))
            index += 1
    return tuple(observations)


def _observed_checkpoints(entry: ConceptDivergence) -> set[Checkpoint]:
    return {
        item.checkpoint
        for item in entry.checkpoints
        if item.state is not EvidenceState.UNOBSERVED
    }


def _state_at(entry: ConceptDivergence, checkpoint: Checkpoint) -> CheckpointState:
    return next(item for item in entry.checkpoints if item.checkpoint is checkpoint)


@settings(max_examples=300, deadline=None)
@given(observations=_observation_sets(), seed=st.randoms(use_true_random=False))
def test_reordering_observations_never_changes_the_divergence(
    observations: tuple[Observation, ...], seed: Any
) -> None:
    shuffled = list(observations)
    seed.shuffle(shuffled)
    assert compute_divergence(_bundle(*shuffled)) == compute_divergence(
        _bundle(*observations)
    )
    first = render_receipt(build_receipt(_bundle(*observations), ()))
    second = render_receipt(build_receipt(_bundle(*shuffled), ()))
    assert first == second


@settings(max_examples=300, deadline=None)
@given(observations=_observation_sets())
def test_a_divergence_names_only_an_observed_boundary_that_actually_differs(
    observations: tuple[Observation, ...],
) -> None:
    """A-034 and A-032: every named checkpoint has evidence, and it differs."""

    entry = _name(*observations)
    observed = _observed_checkpoints(entry)
    expected = entry.from_expected
    previous = entry.from_previous
    for named in (expected.at, previous.after, previous.at):
        assert named is None or named in observed
    if expected.status is DivergenceStatus.DIVERGED:
        assert expected.at is not None
        state = _state_at(entry, expected.at)
        assert state.state is EvidenceState.OBSERVED
        assert state.value_sha256s != entry.expected_sha256s
        for earlier in entry.checkpoints[: PATHWAY.index(expected.at)]:
            assert earlier.state is EvidenceState.UNOBSERVED or (
                earlier.value_sha256s == entry.expected_sha256s
            )
    if previous.status is DivergenceStatus.DIVERGED:
        assert previous.after is not None and previous.at is not None
        assert PATHWAY.index(previous.after) < PATHWAY.index(previous.at)
        between = entry.checkpoints[
            PATHWAY.index(previous.after) + 1 : PATHWAY.index(previous.at)
        ]
        assert all(item.state is EvidenceState.UNOBSERVED for item in between)
        assert (
            _state_at(entry, previous.after).value_sha256s
            != _state_at(entry, previous.at).value_sha256s
        )
    if expected.status is DivergenceStatus.AGREED_WHERE_OBSERVED:
        assert observed
        assert all(
            _state_at(entry, checkpoint).value_sha256s == entry.expected_sha256s
            for checkpoint in observed
        )
    if not observed:
        assert expected.status is DivergenceStatus.UNOBSERVED
        assert previous.status is DivergenceStatus.UNOBSERVED
    if any(item.state is EvidenceState.AMBIGUOUS for item in entry.checkpoints):
        assert expected.status is not DivergenceStatus.AGREED_WHERE_OBSERVED
        assert previous.status is not DivergenceStatus.AGREED_WHERE_OBSERVED


def _observed_predecessor(
    entry: ConceptDivergence, checkpoint: Checkpoint
) -> CheckpointState | None:
    """The last observed checkpoint before ``checkpoint``, if any."""

    earlier = [
        item
        for item in entry.checkpoints[: PATHWAY.index(checkpoint)]
        if item.state is not EvidenceState.UNOBSERVED
    ]
    return earlier[-1] if earlier else None


@settings(max_examples=300, deadline=None)
@given(observations=_observation_sets(), deleted=st.sampled_from(PATHWAY))
def test_deleting_an_observed_checkpoint_never_moves_blame_onto_another(
    observations: tuple[Observation, ...], deleted: Checkpoint
) -> None:
    """A-034 and F-025 as an invariant.

    Remove every observation at one checkpoint. Then, in every case, the
    deleted checkpoint is named nowhere. When it was neither side of the
    located divergence, the entry is unchanged: blame does not move. When it
    was the near side, the located boundary keeps its place and the near side
    moves only to an earlier observed boundary; if there is none, the walk
    restarts at the located boundary and can only locate a boundary that
    already differed from its own observed predecessor. When it was the
    located boundary itself, whatever is located next differs from the same
    near side across a gap that is entirely unobserved: the deletion can
    unmask a divergence that was already an observed fact, and it can never
    manufacture one at a boundary that agreed.
    """

    before = _name(*observations)
    after = _name(*(item for item in observations if item.checkpoint is not deleted))
    assert _state_at(after, deleted).state is EvidenceState.UNOBSERVED
    for named in (
        after.from_expected.at,
        after.from_previous.after,
        after.from_previous.at,
    ):
        assert named is not deleted
    _check_from_expected_after_deletion(before, after, deleted)
    _check_from_previous_after_deletion(before, after, deleted)


_NO_DIVERGENCE = (DivergenceStatus.AGREED_WHERE_OBSERVED, DivergenceStatus.UNOBSERVED)


def _check_from_expected_after_deletion(
    before: ConceptDivergence, after: ConceptDivergence, deleted: Checkpoint
) -> None:
    if before.from_expected.at is None:
        # Nothing was located; taking evidence away cannot locate anything.
        assert after.from_expected.at is None
        assert after.from_expected.status in _NO_DIVERGENCE
        return
    if before.from_expected.at is not deleted:
        assert after.from_expected == before.from_expected
        return
    located = after.from_expected.at
    if located is None:
        return
    assert PATHWAY.index(located) > PATHWAY.index(deleted)
    state = _state_at(before, located)
    assert state == _state_at(after, located)
    if after.from_expected.status is DivergenceStatus.DIVERGED:
        assert state.state is EvidenceState.OBSERVED
        assert state.value_sha256s != before.expected_sha256s
    else:
        assert after.from_expected.status is DivergenceStatus.INDETERMINATE
        assert state.state is EvidenceState.AMBIGUOUS


def _check_from_previous_after_deletion(
    before: ConceptDivergence, after: ConceptDivergence, deleted: Checkpoint
) -> None:
    near, far = before.from_previous.after, before.from_previous.at
    if far is None:
        assert after.from_previous.at is None
        assert after.from_previous.status in _NO_DIVERGENCE
        return
    if deleted not in (near, far):
        assert after.from_previous == before.from_previous
        return
    if deleted is near:
        earlier = _observed_predecessor(before, deleted)
        if earlier is not None:
            assert after.from_previous.at is far
            assert after.from_previous.after is earlier.checkpoint
            assert after.from_previous.status is before.from_previous.status
            return
        assert far is not None
        relocated = after.from_previous.at
        if relocated is None:
            return
        if relocated is far:
            # An ambiguous boundary stays located with no near side to name.
            assert after.from_previous.status is DivergenceStatus.INDETERMINATE
            assert after.from_previous.after is None
            assert _state_at(before, far).state is EvidenceState.AMBIGUOUS
            return
        assert PATHWAY.index(relocated) > PATHWAY.index(far)
        predecessor = _observed_predecessor(before, relocated)
        assert predecessor is not None
        state = _state_at(before, relocated)
        assert state.state is EvidenceState.AMBIGUOUS or (
            state.value_sha256s != predecessor.value_sha256s
        )
        return
    # The located boundary itself was deleted. Whatever is located next is a
    # divergence between two observed boundaries that already existed before
    # the deletion: either the same pair, or the near side and the boundary
    # that used to sit behind the deleted one, across a gap that is now
    # entirely unobserved. Never a boundary that agreed with its predecessor.
    relocated = after.from_previous.at
    if relocated is None:
        return
    assert PATHWAY.index(relocated) > PATHWAY.index(deleted)
    state = _state_at(after, relocated)
    if after.from_previous.status is DivergenceStatus.INDETERMINATE:
        assert state.state is EvidenceState.AMBIGUOUS
        return
    assert after.from_previous.status is DivergenceStatus.DIVERGED
    side = after.from_previous.after
    assert side is not None
    assert state.value_sha256s != _state_at(after, side).value_sha256s
    between = after.checkpoints[PATHWAY.index(side) + 1 : PATHWAY.index(relocated)]
    assert all(item.state is EvidenceState.UNOBSERVED for item in between)
    predecessor = _observed_predecessor(before, relocated)
    assert predecessor is not None
    if predecessor.checkpoint is deleted:
        assert side is near
    else:
        assert predecessor.checkpoint is side
        assert predecessor.value_sha256s != _state_at(before, relocated).value_sha256s
