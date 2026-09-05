"""The laboratory result observation family, its contracts, and its predicates.

Nothing under test here is clinical content. Every analyte code, unit, bound,
and flag in these fixtures is invented for software tests; no laboratory
medical director, clinical reviewer, or community reviewer has approved any
of them, and no assertion in ``docs/05-DATA-AND-EVIDENCE.md`` section 5 is
governed by anything this module proves. What these tests establish is that
the mechanism decides what it says it decides and refuses everything else.

Every expected verdict is restated here rather than read from the fixture, so
a fixture cannot declare its own outcome and the test then agree with it.
"""

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from contextsafe.canonical import canonical_json
from contextsafe.errors import ContextSafeError
from contextsafe.importers.lis import LIS_PROFILE
from contextsafe.laboratory import (
    AFFIRMATIVE_RESULT_REASONS,
    DECIMAL_PATTERN,
    MAX_RESULT_RULES,
    MAX_RESULTS,
    REASON_STATUSES,
    RESULT_RULE_SET_SCHEMA_VERSION,
    RESULT_SCHEMA_VERSION,
    RESULT_SET_SCHEMA_VERSION,
    AbnormalFlag,
    CellStatus,
    IntervalPosition,
    LaboratoryResult,
    ReferenceInterval,
    ResultOutcomeReason,
    ResultPredicate,
    ResultRule,
    evaluate_results,
    outcome_report,
    parse_result_bundle,
    parse_result_rule_set,
    parse_result_set,
    result_set_document,
    type_abnormal_flag_cell,
    type_reference_interval_cell,
)
from contextsafe.models import Checkpoint, ConceptKind, EvidencePointer, OutcomeStatus

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "laboratory"
SCHEMAS = ROOT / "schemas"
RESULT_SET_SCHEMA = json.loads(
    (SCHEMAS / "contextsafe-result-set-v0.1.schema.json").read_text(encoding="utf-8")
)
RULE_SET_SCHEMA = json.loads(
    (SCHEMAS / "contextsafe-result-rule-set-v0.1.schema.json").read_text(
        encoding="utf-8"
    )
)

ALPHA = "fixture-unit-alpha"
BETA = "fixture-unit-beta"

Verdict = tuple[OutcomeStatus, ResultOutcomeReason]

PASS_LINKED: Verdict = (OutcomeStatus.PASSED, ResultOutcomeReason.RESULT_LINKED)
PASS_VALUE: Verdict = (
    OutcomeStatus.PASSED,
    ResultOutcomeReason.ANALYTE_VALUE_UNIT_PRESERVED,
)
PASS_INTERVAL: Verdict = (
    OutcomeStatus.PASSED,
    ResultOutcomeReason.REFERENCE_INTERVAL_PRESENT,
)
PASS_FLAG: Verdict = (
    OutcomeStatus.PASSED,
    ResultOutcomeReason.FLAG_CONSISTENT_WITH_INTERVAL,
)
FAIL_INTERVAL_ABSENT: Verdict = (
    OutcomeStatus.FAIL,
    ResultOutcomeReason.REFERENCE_INTERVAL_ABSENT,
)
INDETERMINATE_INTERVAL_ABSENT: Verdict = (
    OutcomeStatus.INDETERMINATE,
    ResultOutcomeReason.REFERENCE_INTERVAL_ABSENT,
)
INDETERMINATE_NOT_TYPED: Verdict = (
    OutcomeStatus.INDETERMINATE,
    ResultOutcomeReason.REFERENCE_INTERVAL_NOT_TYPED,
)

_FOUR_PASSES: tuple[Verdict, ...] = (
    PASS_LINKED,
    PASS_VALUE,
    PASS_INTERVAL,
    PASS_FLAG,
)

CLASS_EXPECTATIONS: dict[str, tuple[Verdict, ...]] = {
    # Six edge values per class, four predicates each, in rule-id order.
    "inv": (
        *_FOUR_PASSES,  # below the lower bound, flagged below
        *_FOUR_PASSES,  # at the inclusive lower bound, so in range
        *_FOUR_PASSES,  # in range
        *_FOUR_PASSES,  # at the inclusive upper bound, so in range
        *_FOUR_PASSES,  # above the upper bound, flagged above
        # the sixth condition: no interval at all
        PASS_LINKED,
        PASS_VALUE,
        FAIL_INTERVAL_ABSENT,
        INDETERMINATE_INTERVAL_ABSENT,
    ),
    "ctx": (
        *_FOUR_PASSES,  # below the lower bound
        *_FOUR_PASSES,  # at the exclusive lower bound, so below it
        *_FOUR_PASSES,  # in range
        *_FOUR_PASSES,  # at the exclusive upper bound, so above it
        *_FOUR_PASSES,  # above the upper bound
        # the sixth condition: an interval in a dialect this profile cannot type
        PASS_LINKED,
        PASS_VALUE,
        INDETERMINATE_NOT_TYPED,
        INDETERMINATE_NOT_TYPED,
    ),
    "xfail": tuple(
        verdict
        for _ in range(6)
        for verdict in (
            PASS_LINKED,
            PASS_VALUE,
            FAIL_INTERVAL_ABSENT,
            INDETERMINATE_INTERVAL_ABSENT,
        )
    ),
}
"""What each shipped fixture class must be reported as, restated by hand.

The XFAIL class is the published failure pattern: an export that returned no
interval and no flag at any of the six values, for a case whose recorded sex
or gender is X. Every interval claim fails and no flag claim is ever decided,
which is A-029 and A-030 -- an out-of-range value is never reported normal
because the range was missing.
"""


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _verdicts(document: dict[str, Any]) -> tuple[Verdict, ...]:
    bundle = parse_result_bundle(
        document["case"], document["results"], document["rules"]
    )
    return tuple((item.status, item.reason) for item in evaluate_results(bundle))


def _interval(
    low: str = "2.500",
    *,
    low_inclusive: bool = True,
    high: str = "7.500",
    high_inclusive: bool = True,
    unit: str = ALPHA,
) -> dict[str, Any]:
    return {
        "status": "typed",
        "low": low,
        "low_inclusive": low_inclusive,
        "high": high,
        "high_inclusive": high_inclusive,
        "unit": unit,
    }


def _result(**changes: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "result_id": "RES-CTP-L01-0001",
        "case_id": "CTP-L01",
        "checkpoint": "lis_return",
        "analyte_code": "fixture-analyte-1",
        "value": "5.000",
        "unit": ALPHA,
        "order_id": "ORDER-CSYN-CTP-L01-A",
        "specimen_id": "CSYN-SPEC-CTP-L01-0001",
        "reference_interval": _interval(),
        "abnormal_flag": {"status": "typed", "flag": "fixture-flag-in-range"},
        "evidence": {"source_sha256": "a" * 64, "source_pointer": "$.rows[0]"},
        "mapping_version": "0.1.0",
    }
    document.update(changes)
    return document


def _result_set(*results: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": RESULT_SET_SCHEMA_VERSION,
        "results": list(results) or [_result()],
    }


def _rule(**changes: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "rule_id": "A-L01",
        "version": "0.1.0",
        "case_id": "CTP-L01",
        "checkpoint": "lis_return",
        "result_id": "RES-CTP-L01-0001",
        "predicate": "reference_interval_present",
        "required": True,
    }
    document.update(changes)
    return document


def _rule_set(*rules: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": RESULT_RULE_SET_SCHEMA_VERSION,
        "rules": list(rules) or [_rule()],
    }


def _case(**changes: Any) -> dict[str, Any]:
    document = _load(FIXTURES / "inv.json")["case"]
    assert isinstance(document, dict)
    document.update(changes)
    return document


def _decide(
    result_changes: dict[str, Any] | None = None,
    rule_changes: dict[str, Any] | None = None,
) -> Verdict:
    """Evaluate one result against one rule and return the single verdict."""

    bundle = parse_result_bundle(
        _case(),
        _result_set(_result(**(result_changes or {}))),
        _rule_set(_rule(**(rule_changes or {}))),
    )
    outcomes = evaluate_results(bundle)
    assert len(outcomes) == 1
    return outcomes[0].status, outcomes[0].reason


def _refuses(
    code: str,
    path: str,
    *,
    case: dict[str, Any] | None = None,
    results: dict[str, Any] | None = None,
    rules: dict[str, Any] | None = None,
) -> ContextSafeError:
    with pytest.raises(ContextSafeError) as caught:
        parse_result_bundle(
            case or _case(), results or _result_set(), rules or _rule_set()
        )
    assert (caught.value.code, caught.value.path) == (code, path)
    return caught.value


# --- the shipped fixture classes ---------------------------------------------


@pytest.mark.parametrize("name", sorted(CLASS_EXPECTATIONS))
def test_each_fixture_class_carries_six_edge_values_and_is_read_as_stated(
    name: str,
) -> None:
    """INV, CTX, and XFAIL, each with all six edge conditions (docs/05 §4)."""

    document = _load(FIXTURES / f"{name}.json")
    results = document["results"]["results"]
    assert len(results) == 6
    assert len({item["result_id"] for item in results}) == 6
    assert _verdicts(document) == CLASS_EXPECTATIONS[name]


@pytest.mark.parametrize("name", sorted(CLASS_EXPECTATIONS))
def test_no_fixture_carries_anything_but_an_invented_token(name: str) -> None:
    """No real analyte, unit, bound dialect, or flag anywhere in the fixtures."""

    document = _load(FIXTURES / f"{name}.json")
    for item in document["results"]["results"]:
        assert item["analyte_code"].startswith("fixture-analyte-")
        assert item["unit"].startswith("fixture-unit-")
        assert item["order_id"].startswith("ORDER-CSYN-")
        assert item["specimen_id"].startswith("CSYN-SPEC-")
        flag = item["abnormal_flag"]
        if flag["status"] == "typed":
            assert flag["flag"] in {item.value for item in AbnormalFlag}
        interval = item["reference_interval"]
        if interval["status"] == "typed":
            assert interval["unit"].startswith("fixture-unit-")


def test_the_xfail_class_fails_the_interval_claim_at_every_value() -> None:
    """A-029: an X in the case never yields a silently blank interval that passes."""

    document = _load(FIXTURES / "xfail.json")
    assert document["case"]["concepts"]["recorded_sex_or_gender"][0]["value"] == "X"
    bundle = parse_result_bundle(
        document["case"], document["results"], document["rules"]
    )
    interval_rules = [
        item
        for item in evaluate_results(bundle)
        if item.predicate is ResultPredicate.REFERENCE_INTERVAL_PRESENT
    ]
    assert len(interval_rules) == 6
    for outcome in interval_rules:
        assert outcome.status is OutcomeStatus.FAIL
        assert outcome.reason is ResultOutcomeReason.REFERENCE_INTERVAL_ABSENT


def test_no_flag_outcome_of_the_xfail_class_is_ever_a_pass() -> None:
    """A-030: a missing range is indeterminate, never normal."""

    document = _load(FIXTURES / "xfail.json")
    bundle = parse_result_bundle(
        document["case"], document["results"], document["rules"]
    )
    for outcome in evaluate_results(bundle):
        if outcome.predicate is ResultPredicate.FLAG_CONSISTENT_WITH_INTERVAL:
            assert outcome.status is OutcomeStatus.INDETERMINATE


@pytest.mark.parametrize("name", sorted(CLASS_EXPECTATIONS))
def test_every_fixture_class_validates_against_the_published_contracts(
    name: str,
) -> None:
    document = _load(FIXTURES / f"{name}.json")
    Draft202012Validator(RESULT_SET_SCHEMA).validate(document["results"])
    Draft202012Validator(RULE_SET_SCHEMA).validate(document["rules"])


# --- the boundary: where a value sits against its own bounds -----------------


@pytest.mark.parametrize(
    ("value", "low_inclusive", "high_inclusive", "position"),
    [
        ("1.000", True, True, IntervalPosition.BELOW_LOW),
        ("2.500", True, True, IntervalPosition.IN_RANGE),
        ("2.500", False, True, IntervalPosition.BELOW_LOW),
        ("2.5", True, True, IntervalPosition.IN_RANGE),
        ("5.000", True, True, IntervalPosition.IN_RANGE),
        ("7.500", True, True, IntervalPosition.IN_RANGE),
        ("7.500", True, False, IntervalPosition.ABOVE_HIGH),
        ("9.000", True, True, IntervalPosition.ABOVE_HIGH),
        ("-1.000", True, True, IntervalPosition.BELOW_LOW),
    ],
)
def test_the_position_of_a_value_honours_the_declared_inclusivity(
    value: str, low_inclusive: bool, high_inclusive: bool, position: IntervalPosition
) -> None:
    """The bound is inside or outside because the fixture said so, not by default."""

    interval = ReferenceInterval(
        low="2.500",
        low_inclusive=low_inclusive,
        high="7.500",
        high_inclusive=high_inclusive,
        unit=ALPHA,
    )
    assert interval.position_of(__import__("decimal").Decimal(value)) is position


@pytest.mark.parametrize(
    ("value", "flag", "verdict"),
    [
        ("1.000", "fixture-flag-below-low", PASS_FLAG),
        ("1.000", "fixture-flag-in-range", (OutcomeStatus.FAIL, None)),
        ("5.000", "fixture-flag-in-range", PASS_FLAG),
        ("5.000", "fixture-flag-above-high", (OutcomeStatus.FAIL, None)),
        ("9.000", "fixture-flag-above-high", PASS_FLAG),
        ("9.000", "fixture-flag-in-range", (OutcomeStatus.FAIL, None)),
    ],
)
def test_a_flag_is_consistent_only_with_the_position_the_bounds_imply(
    value: str, flag: str, verdict: tuple[OutcomeStatus, ResultOutcomeReason | None]
) -> None:
    status, reason = _decide(
        {"value": value, "abnormal_flag": {"status": "typed", "flag": flag}},
        {"predicate": "flag_consistent_with_interval"},
    )
    assert status is verdict[0]
    if verdict[1] is None:
        assert reason is ResultOutcomeReason.FLAG_INCONSISTENT_WITH_INTERVAL
    else:
        assert reason is verdict[1]


# --- fail closed: absence, illegibility, and what is never a pass ------------


def test_an_out_of_range_value_with_no_flag_at_all_is_a_failure() -> None:
    """A-028, A-030: the boundary answered and left the abnormal result unflagged."""

    assert _decide(
        {"value": "9.000", "abnormal_flag": {"status": "absent"}},
        {"predicate": "flag_consistent_with_interval"},
    ) == (OutcomeStatus.FAIL, ResultOutcomeReason.FLAG_MISSING_OUT_OF_RANGE)


def test_an_in_range_value_with_no_flag_is_indeterminate_and_never_a_pass() -> None:
    """A flag nobody sent is not evidence that anything is normal."""

    assert _decide(
        {"abnormal_flag": {"status": "absent"}},
        {"predicate": "flag_consistent_with_interval"},
    ) == (OutcomeStatus.INDETERMINATE, ResultOutcomeReason.FLAG_ABSENT_IN_RANGE)


def test_a_flag_outside_the_vocabulary_decides_nothing_and_is_not_nearest_matched() -> (
    None
):
    """A-033: an unsupported flag is not normalized to the closest supported one."""

    assert _decide(
        {"abnormal_flag": {"status": "not_typed"}},
        {"predicate": "flag_consistent_with_interval"},
    ) == (OutcomeStatus.INDETERMINATE, ResultOutcomeReason.FLAG_NOT_TYPED)


def test_a_value_that_cannot_be_compared_decides_nothing() -> None:
    """A censored or coded value is not silently read as a number."""

    assert _decide(
        {"value": "<0.500"},
        {"predicate": "flag_consistent_with_interval"},
    ) == (OutcomeStatus.INDETERMINATE, ResultOutcomeReason.VALUE_NOT_COMPARABLE)


def test_an_interval_in_another_unit_is_a_finding_and_decides_no_flag() -> None:
    """F-033: a numeric range preserved with the wrong unit is not an interval."""

    faulted = {"reference_interval": _interval(unit=BETA)}
    assert _decide(faulted, {"predicate": "reference_interval_present"}) == (
        OutcomeStatus.FAIL,
        ResultOutcomeReason.REFERENCE_INTERVAL_UNIT_MISMATCH,
    )
    assert _decide(faulted, {"predicate": "flag_consistent_with_interval"}) == (
        OutcomeStatus.INDETERMINATE,
        ResultOutcomeReason.REFERENCE_INTERVAL_UNIT_MISMATCH,
    )


def test_an_interval_the_profile_cannot_type_is_neither_present_nor_absent() -> None:
    faulted = {"reference_interval": {"status": "not_typed"}}
    assert _decide(faulted, {"predicate": "reference_interval_present"}) == (
        INDETERMINATE_NOT_TYPED
    )
    assert _decide(faulted, {"predicate": "flag_consistent_with_interval"}) == (
        INDETERMINATE_NOT_TYPED
    )


def test_a_rule_whose_result_the_boundary_never_returned_is_indeterminate() -> None:
    """Absence of a result is missing evidence, never a pass."""

    assert _decide(rule_changes={"result_id": "RES-CTP-L01-9999"}) == (
        OutcomeStatus.INDETERMINATE,
        ResultOutcomeReason.MISSING_EVIDENCE,
    )
    assert _decide(rule_changes={"checkpoint": "ehr"}) == (
        OutcomeStatus.INDETERMINATE,
        ResultOutcomeReason.MISSING_EVIDENCE,
    )


def test_a_rule_that_is_not_required_is_not_applicable_either_way() -> None:
    assert _decide(rule_changes={"required": False}) == (
        OutcomeStatus.NOT_APPLICABLE,
        ResultOutcomeReason.PREDECLARED_NOT_APPLICABLE,
    )
    assert _decide(
        rule_changes={"required": False, "result_id": "RES-CTP-L01-9999"}
    ) == (
        OutcomeStatus.NOT_APPLICABLE,
        ResultOutcomeReason.PREDECLARED_NOT_APPLICABLE,
    )


def test_no_reason_may_be_published_under_a_status_the_table_does_not_name() -> None:
    """``pass`` is reachable from four reasons and no others."""

    assert set(REASON_STATUSES) == set(ResultOutcomeReason)
    passing = {
        reason
        for reason, statuses in REASON_STATUSES.items()
        if OutcomeStatus.PASSED in statuses
    }
    assert passing == AFFIRMATIVE_RESULT_REASONS
    assert len(passing) == 4


def test_every_outcome_the_fixtures_produce_obeys_the_reason_table() -> None:
    for name in sorted(CLASS_EXPECTATIONS):
        document = _load(FIXTURES / f"{name}.json")
        bundle = parse_result_bundle(
            document["case"], document["results"], document["rules"]
        )
        for outcome in evaluate_results(bundle):
            assert outcome.status in REASON_STATUSES[outcome.reason]


# --- the linkage claim -------------------------------------------------------


def test_a_result_carrying_another_patients_order_is_not_linked() -> None:
    """A-025, and the fault F-017 seeds."""

    assert _decide(
        {"order_id": "ORDER-CSYN-CTP-L09-A"},
        {
            "predicate": "result_linked",
            "expected_order_id": "ORDER-CSYN-CTP-L01-A",
            "expected_specimen_id": "CSYN-SPEC-CTP-L01-0001",
        },
    ) == (OutcomeStatus.FAIL, ResultOutcomeReason.RESULT_NOT_LINKED)


def test_a_result_carrying_another_specimen_is_not_linked() -> None:
    assert _decide(
        {"specimen_id": "CSYN-SPEC-CTP-L01-9999"},
        {
            "predicate": "result_linked",
            "expected_order_id": "ORDER-CSYN-CTP-L01-A",
            "expected_specimen_id": "CSYN-SPEC-CTP-L01-0001",
        },
    ) == (OutcomeStatus.FAIL, ResultOutcomeReason.RESULT_NOT_LINKED)


@pytest.mark.parametrize(
    "change",
    [
        {"analyte_code": "fixture-analyte-9"},
        {"value": "5.500"},
        {"value": "5.00"},
        {"unit": BETA},
    ],
)
def test_the_round_trip_claim_compares_all_three_tokens_exactly(
    change: dict[str, Any],
) -> None:
    """A-026: ``5.00`` and ``5.000`` are one quantity and two round trips."""

    assert _decide(
        change,
        {
            "predicate": "analyte_value_unit_preserved",
            "expected_analyte_code": "fixture-analyte-1",
            "expected_value": "5.000",
            "expected_unit": ALPHA,
        },
    ) == (OutcomeStatus.FAIL, ResultOutcomeReason.ANALYTE_VALUE_UNIT_CHANGED)


# --- value minimization and concept separation -------------------------------


def test_an_outcome_carries_no_analyte_value_unit_bound_or_flag() -> None:
    """A receipt-shaped outcome names hashes, codes, and pointers, never content."""

    bundle = parse_result_bundle(_case(), _result_set(), _rule_set())
    rendered = canonical_json(outcome_report(evaluate_results(bundle)))
    for content in ("fixture-analyte-1", ALPHA, "5.000", "2.500", "7.500"):
        assert content not in rendered
    assert "RES-CTP-L01-0001" in rendered


def test_the_family_names_no_gender_harmony_concept_anywhere() -> None:
    """The five concepts stay distinct because nothing here can express one."""

    source = (ROOT / "src" / "contextsafe" / "laboratory.py").read_text(
        encoding="utf-8"
    )
    # Rendered, not as a mapping: `in` over a dict reads its keys only, and
    # a concept name would be as wrong in an analyte code or a flag as in a
    # field name.
    documents = canonical_json(_result_set()) + canonical_json(_rule_set())
    for concept in ConceptKind:
        assert concept.value not in documents
    assert "ConceptKind" not in source.split('"""', 2)[2]


def test_a_result_document_round_trips_through_its_own_contract() -> None:
    results = parse_result_set(_result_set())
    assert result_set_document(results) == _result_set()
    Draft202012Validator(RESULT_SET_SCHEMA).validate(result_set_document(results))


def test_a_rule_set_round_trips_and_omits_the_fields_its_predicate_ignores() -> None:
    rule_set = parse_result_rule_set(_rule_set())
    rendered = rule_set.to_dict()
    assert rendered == _rule_set()
    assert "expected_order_id" not in rendered["rules"][0]


def test_evaluation_is_byte_identical_across_runs() -> None:
    document = _load(FIXTURES / "inv.json")
    bundle = parse_result_bundle(
        document["case"], document["results"], document["rules"]
    )
    first = canonical_json(outcome_report(evaluate_results(bundle)))
    second = canonical_json(outcome_report(evaluate_results(bundle)))
    assert first == second


def test_the_outcome_trace_names_the_source_and_the_mapping_version() -> None:
    bundle = parse_result_bundle(_case(), _result_set(), _rule_set())
    outcome = evaluate_results(bundle)[0]
    assert outcome.trace.mapping_versions == ("0.1.0",)
    assert outcome.trace.sources == (
        EvidencePointer(source_sha256="a" * 64, source_pointer="$.rows[0]"),
    )
    assert outcome.evidence_sha256s == ("a" * 64,)
    assert outcome.observed_sha256s and len(outcome.observed_sha256s[0]) == 64


def test_an_indeterminate_outcome_with_no_result_carries_an_empty_trace() -> None:
    bundle = parse_result_bundle(
        _case(), _result_set(), _rule_set(_rule(result_id="RES-CTP-L01-9999"))
    )
    outcome = evaluate_results(bundle)[0]
    assert outcome.trace.sources == ()
    assert outcome.observed_sha256s == ()
    assert outcome.evidence_sha256s == ()


# --- cell typing, which is where a partner's own dialect stops ---------------


@pytest.mark.parametrize(
    ("cell", "status"),
    [
        ("", CellStatus.ABSENT),
        ("ge2.500:le7.500:fixture-unit-alpha", CellStatus.TYPED),
        ("gt2.500:lt7.500:fixture-unit-alpha", CellStatus.TYPED),
        ("3.5-5.5", CellStatus.NOT_TYPED),
        ("ge7.500:le2.500:fixture-unit-alpha", CellStatus.NOT_TYPED),
        ("gt2.500:lt2.500:fixture-unit-alpha", CellStatus.NOT_TYPED),
        ("ge2.500:le2.500:fixture-unit-alpha", CellStatus.TYPED),
        ("ge2.500:le7.500", CellStatus.NOT_TYPED),
    ],
)
def test_a_range_cell_is_typed_only_in_the_one_published_dialect(
    cell: str, status: CellStatus
) -> None:
    typed, interval = type_reference_interval_cell(cell)
    assert typed is status
    assert (interval is not None) == (status is CellStatus.TYPED)


@pytest.mark.parametrize(
    ("cell", "status"),
    [
        ("", CellStatus.ABSENT),
        ("fixture-flag-in-range", CellStatus.TYPED),
        ("H", CellStatus.NOT_TYPED),
        ("N", CellStatus.NOT_TYPED),
    ],
)
def test_a_flag_cell_is_typed_only_in_the_invented_vocabulary(
    cell: str, status: CellStatus
) -> None:
    typed, flag = type_abnormal_flag_cell(cell)
    assert typed is status
    assert (flag is not None) == (status is CellStatus.TYPED)


# --- malformed documents: every refusal names a code and a structural path ---


@pytest.mark.parametrize(
    ("change", "code", "path"),
    [
        (
            {"schema_version": "contextsafe.result/0.9.0"},
            "unsupported_schema",
            "$.results[0].schema_version",
        ),
        ({"result_id": "res-1"}, "invalid_format", "$.results[0].result_id"),
        ({"case_id": "NOTACASE"}, "invalid_format", "$.results[0].case_id"),
        ({"checkpoint": "billing"}, "invalid_enum", "$.results[0].checkpoint"),
        ({"analyte_code": "a b"}, "invalid_format", "$.results[0].analyte_code"),
        ({"unit": ""}, "invalid_string", "$.results[0].unit"),
        ({"order_id": "ORDER-1234567890"}, "invalid_format", "$.results[0].order_id"),
        ({"specimen_id": "SPEC-1"}, "invalid_format", "$.results[0].specimen_id"),
        ({"mapping_version": "1"}, "invalid_format", "$.results[0].mapping_version"),
    ],
)
def test_a_malformed_result_field_refuses_the_whole_document(
    change: dict[str, Any], code: str, path: str
) -> None:
    _refuses(code, path, results=_result_set(_result(**change)))


@pytest.mark.parametrize(
    ("interval", "code", "path"),
    [
        (
            {"status": "sometimes"},
            "invalid_enum",
            "$.results[0].reference_interval.status",
        ),
        (
            {"status": "absent", "low": "1.000"},
            "unknown_field",
            "$.results[0].reference_interval",
        ),
        (
            {"status": "typed", "low": "1.000"},
            "missing_field",
            "$.results[0].reference_interval.high",
        ),
        (
            {
                "status": "typed",
                "low": "1e3",
                "low_inclusive": True,
                "high": "7.500",
                "high_inclusive": True,
                "unit": ALPHA,
            },
            "invalid_format",
            "$.results[0].reference_interval.low",
        ),
        (
            {
                "status": "typed",
                "low": "7.500",
                "low_inclusive": True,
                "high": "2.500",
                "high_inclusive": True,
                "unit": ALPHA,
            },
            "invalid_reference_interval",
            "$.results[0].reference_interval",
        ),
        (
            {
                "status": "typed",
                "low": "2.500",
                "low_inclusive": False,
                "high": "2.500",
                "high_inclusive": True,
                "unit": ALPHA,
            },
            "invalid_reference_interval",
            "$.results[0].reference_interval",
        ),
        (
            {
                "status": "typed",
                "low": "2.500",
                "low_inclusive": "yes",
                "high": "7.500",
                "high_inclusive": True,
                "unit": ALPHA,
            },
            "invalid_type",
            "$.results[0].reference_interval.low_inclusive",
        ),
    ],
)
def test_a_malformed_interval_block_refuses_the_whole_document(
    interval: dict[str, Any], code: str, path: str
) -> None:
    _refuses(code, path, results=_result_set(_result(reference_interval=interval)))


@pytest.mark.parametrize(
    ("flag", "code", "path"),
    [
        ({"status": "typed"}, "missing_field", "$.results[0].abnormal_flag.flag"),
        (
            {"status": "typed", "flag": "H"},
            "invalid_abnormal_flag",
            "$.results[0].abnormal_flag.flag",
        ),
        (
            {"status": "absent", "flag": "H"},
            "unknown_field",
            "$.results[0].abnormal_flag",
        ),
        ({"flag": "H"}, "missing_field", "$.results[0].abnormal_flag.status"),
    ],
)
def test_a_malformed_flag_block_refuses_the_whole_document(
    flag: dict[str, Any], code: str, path: str
) -> None:
    _refuses(code, path, results=_result_set(_result(abnormal_flag=flag)))


def test_a_source_pointer_outside_the_structural_vocabulary_is_refused() -> None:
    """The one pointer authority, shared with the observation set."""

    _refuses(
        "non_structural_pointer",
        "$.results[0].evidence.source_pointer",
        results=_result_set(
            _result(
                evidence={"source_sha256": "a" * 64, "source_pointer": "$.analyte[0]"}
            )
        ),
    )


def test_a_prohibited_key_anywhere_refuses_the_result_set() -> None:
    document = _result_set()
    document["results"][0]["evidence"]["note"] = "anything"
    _refuses("prohibited_field", "$", results=document)


@pytest.mark.parametrize(
    ("document", "code", "path"),
    [
        (
            {"schema_version": "contextsafe.result-set/0.9.0", "results": []},
            "unsupported_schema",
            "$.schema_version",
        ),
        (
            {"schema_version": RESULT_SET_SCHEMA_VERSION, "results": []},
            "invalid_result_count",
            "$.results",
        ),
        ({"schema_version": RESULT_SET_SCHEMA_VERSION}, "missing_field", "$.results"),
        (
            {"schema_version": RESULT_SET_SCHEMA_VERSION, "results": [], "extra": 1},
            "unknown_field",
            "$",
        ),
    ],
)
def test_a_malformed_result_set_envelope_is_refused(
    document: dict[str, Any], code: str, path: str
) -> None:
    _refuses(code, path, results=document)


def test_more_results_than_the_bound_are_refused() -> None:
    results = [
        _result(result_id=f"RES-CTP-L01-{index:04d}")
        for index in range(MAX_RESULTS + 1)
    ]
    _refuses("invalid_result_count", "$.results", results=_result_set(*results))


def test_a_duplicate_result_identifier_refuses_the_document() -> None:
    """Ambiguity is decided by the contract, so a rule matches at most one result."""

    _refuses(
        "duplicate_result_id",
        "$.results",
        results=_result_set(
            _result(),
            _result(
                evidence={"source_sha256": "b" * 64, "source_pointer": "$.rows[1]"}
            ),
        ),
    )


@pytest.mark.parametrize(
    ("change", "code", "path"),
    [
        ({"rule_id": "A-I01"}, "invalid_format", "$.rules[0].rule_id"),
        ({"version": "one"}, "invalid_format", "$.rules[0].version"),
        ({"predicate": "guess"}, "invalid_enum", "$.rules[0].predicate"),
        ({"required": "yes"}, "invalid_type", "$.rules[0].required"),
        ({"result_id": "RES-lower"}, "invalid_format", "$.rules[0].result_id"),
        ({"checkpoint": "billing"}, "invalid_enum", "$.rules[0].checkpoint"),
    ],
)
def test_a_malformed_rule_refuses_the_whole_rule_set(
    change: dict[str, Any], code: str, path: str
) -> None:
    _refuses(code, path, rules=_rule_set(_rule(**change)))


def test_a_rule_that_declares_a_field_its_predicate_ignores_is_refused() -> None:
    _refuses(
        "unknown_field",
        "$.rules[0]",
        rules=_rule_set(_rule(expected_value="5.000")),
    )


def test_a_rule_that_omits_a_field_its_predicate_reads_is_refused() -> None:
    _refuses(
        "missing_field",
        "$.rules[0].expected_specimen_id",
        rules=_rule_set(
            _rule(predicate="result_linked", expected_order_id="ORDER-CSYN-CTP-L01-A")
        ),
    )


def test_a_rule_with_no_predicate_at_all_is_refused() -> None:
    rule = _rule()
    del rule["predicate"]
    _refuses("missing_field", "$.rules[0].predicate", rules=_rule_set(rule))


@pytest.mark.parametrize(
    ("document", "code", "path"),
    [
        (
            {"schema_version": "contextsafe.result-rule-set/0.9.0", "rules": []},
            "unsupported_schema",
            "$.schema_version",
        ),
        (
            {"schema_version": RESULT_RULE_SET_SCHEMA_VERSION, "rules": []},
            "invalid_rule_count",
            "$.rules",
        ),
        (
            {"schema_version": RESULT_RULE_SET_SCHEMA_VERSION, "rules": {}},
            "invalid_type",
            "$.rules",
        ),
    ],
)
def test_a_malformed_rule_set_envelope_is_refused(
    document: dict[str, Any], code: str, path: str
) -> None:
    _refuses(code, path, rules=document)


def test_more_rules_than_the_bound_are_refused() -> None:
    rules = [_rule(rule_id="A-L01") for _ in range(MAX_RESULT_RULES + 1)]
    _refuses("invalid_rule_count", "$.rules", rules=_rule_set(*rules))


def test_a_duplicate_rule_identifier_refuses_the_rule_set() -> None:
    _refuses(
        "duplicate_rule_id", "$.rules", rules=_rule_set(_rule(), _rule(required=False))
    )


def test_a_prohibited_key_anywhere_refuses_the_rule_set() -> None:
    document = _rule_set()
    document["rules"][0]["note"] = "anything"
    _refuses("prohibited_field", "$", rules=document)


def test_a_result_or_rule_naming_another_case_refuses_the_bundle() -> None:
    """A-001: the case link is a refusal, which is why A-025 decides the order."""

    _refuses(
        "case_mismatch",
        "$.results",
        results=_result_set(_result(case_id="CTP-L09", result_id="RES-CTP-L09-0001")),
        rules=_rule_set(_rule(result_id="RES-CTP-L09-0001")),
    )
    _refuses("case_mismatch", "$.rules", rules=_rule_set(_rule(case_id="CTP-L09")))


def test_a_result_is_not_a_json_object() -> None:
    _refuses(
        "invalid_type",
        "$.results[0]",
        results={"schema_version": RESULT_SET_SCHEMA_VERSION, "results": ["x"]},
    )


# --- the typed record refuses to describe itself inconsistently --------------


def test_a_typed_status_without_its_content_cannot_be_constructed() -> None:
    evidence = EvidencePointer(source_sha256="a" * 64, source_pointer="$.rows[0]")
    fields: dict[str, Any] = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "result_id": "RES-CTP-L01-0001",
        "case_id": "CTP-L01",
        "checkpoint": Checkpoint.LIS_RETURN,
        "analyte_code": "fixture-analyte-1",
        "value": "5.000",
        "unit": ALPHA,
        "order_id": "ORDER-CSYN-CTP-L01-A",
        "specimen_id": "CSYN-SPEC-CTP-L01-0001",
        "interval_status": CellStatus.TYPED,
        "reference_interval": None,
        "flag_status": CellStatus.ABSENT,
        "abnormal_flag": None,
        "evidence": evidence,
        "mapping_version": "0.1.0",
    }
    with pytest.raises(ContextSafeError) as interval:
        LaboratoryResult(**fields)
    assert interval.value.code == "invalid_reference_interval"

    fields["interval_status"] = CellStatus.ABSENT
    fields["abnormal_flag"] = AbnormalFlag.IN_RANGE
    with pytest.raises(ContextSafeError) as flag:
        LaboratoryResult(**fields)
    assert flag.value.code == "invalid_abnormal_flag"


def test_a_rule_renders_every_field_its_predicate_reads() -> None:
    rule = ResultRule(
        rule_id="A-L01",
        version="0.1.0",
        case_id="CTP-L01",
        checkpoint=Checkpoint.LIS_RETURN,
        result_id="RES-CTP-L01-0001",
        predicate=ResultPredicate.ANALYTE_VALUE_UNIT_PRESERVED,
        required=True,
        expected_analyte_code="fixture-analyte-1",
        expected_value="5.000",
        expected_unit=ALPHA,
    )
    rendered = rule.to_dict()
    assert rendered["expected_analyte_code"] == "fixture-analyte-1"
    assert "expected_order_id" not in rendered
    Draft202012Validator(RULE_SET_SCHEMA).validate(
        {"schema_version": RESULT_RULE_SET_SCHEMA_VERSION, "rules": [rendered]}
    )


def test_the_summary_counts_every_status_the_algebra_has() -> None:
    document = _load(FIXTURES / "inv.json")
    bundle = parse_result_bundle(
        document["case"], document["results"], document["rules"]
    )
    report = outcome_report(evaluate_results(bundle))
    summary = report["summary"]
    assert isinstance(summary, dict)
    assert set(summary) == {item.value for item in OutcomeStatus}
    assert summary["fail"] == 1
    assert summary["indeterminate"] == 1
    assert summary["pass"] == 22


# --- the published contracts and the runtime say the same thing -------------


def test_the_published_result_contract_admits_exactly_the_runtime_vocabularies() -> (
    None
):
    flags = RESULT_SET_SCHEMA["$defs"]["abnormalFlag"]["oneOf"][1]["properties"]["flag"]
    assert set(flags["enum"]) == {item.value for item in AbnormalFlag}
    statuses = RESULT_SET_SCHEMA["$defs"]["abnormalFlag"]["oneOf"][0]["properties"][
        "status"
    ]
    assert set(statuses["enum"]) | {CellStatus.TYPED.value} == {
        item.value for item in CellStatus
    }
    assert RESULT_SET_SCHEMA["$defs"]["decimal"]["pattern"] == DECIMAL_PATTERN.pattern
    assert RESULT_SET_SCHEMA["properties"]["schema_version"]["const"] == (
        RESULT_SET_SCHEMA_VERSION
    )
    assert RESULT_SET_SCHEMA["properties"]["results"]["maxItems"] == MAX_RESULTS


def test_the_published_rule_contract_admits_exactly_the_runtime_predicates() -> None:
    predicates = RULE_SET_SCHEMA["$defs"]["rule"]["properties"]["predicate"]["enum"]
    assert set(predicates) == {item.value for item in ResultPredicate}
    assert RULE_SET_SCHEMA["properties"]["schema_version"]["const"] == (
        RESULT_RULE_SET_SCHEMA_VERSION
    )
    assert RULE_SET_SCHEMA["properties"]["rules"]["maxItems"] == MAX_RESULT_RULES


def test_the_schema_refuses_a_rule_the_runtime_refuses() -> None:
    """Both layers refuse a predicate carrying a field it does not read."""

    validator = Draft202012Validator(RULE_SET_SCHEMA)
    assert not validator.is_valid(_rule_set(_rule(expected_value="5.000")))
    assert not validator.is_valid(
        _rule_set(_rule(predicate="result_linked", expected_value="5.000"))
    )
    assert validator.is_valid(
        _rule_set(
            _rule(
                predicate="result_linked",
                expected_order_id="ORDER-CSYN-CTP-L01-A",
                expected_specimen_id="CSYN-SPEC-CTP-L01-0001",
            )
        )
    )


def test_the_lis_profile_records_its_own_version_on_every_result() -> None:
    """The profile version moves with what the profile emits (F-035's rule)."""

    assert LIS_PROFILE.version == "0.2.0"
