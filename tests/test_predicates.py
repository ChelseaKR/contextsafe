"""The B-028 rule-set predicates: mechanism, contract, and what must not happen.

Every predicate in ``RulePredicate`` is a pure function over the validated
bundle. These tests hold, per predicate, the happy path against the packaged
``rules-predicates.json``, the fail-closed contract at the validator, the
boundary values the contract publishes, and the safety negative: the thing a
predicate must never report as ``pass``. ``docs/05-DATA-AND-EVIDENCE.md``
section 5 names the assertions (A-005, A-008 to A-015); nothing here is
governed content, and no clinical, laboratory, or community review has
approved any rule these tests run.
"""

import copy
import json
from typing import Any

import pytest

from contextsafe.errors import ContextSafeError
from contextsafe.evaluator import Outcome, evaluate
from contextsafe.models import (
    AFFIRMATIVE_REASONS,
    FAILURE_REASONS,
    INDETERMINATE_REASONS,
    PREDICATE_RULE_SET_SCHEMA_VERSION,
    RULE_SET_SCHEMA_VERSION,
    OutcomeReason,
    OutcomeStatus,
    RulePredicate,
)
from contextsafe.receipt import build_receipt, render_receipt
from contextsafe.reference_fixtures import REFERENCE_ROOT
from contextsafe.validation import parse_bundle, parse_rule_set

GI_DECLINED = {
    "status": "declined",
    "value": None,
    "code_system": "urn:contextsafe:fixture",
}
GI_UNKNOWN = {
    "status": "unknown",
    "value": None,
    "code_system": "urn:contextsafe:fixture",
}
GI_ABSENT = {
    "status": "absent",
    "value": None,
    "code_system": "urn:contextsafe:fixture",
}
RSG_M = {"value": "M", "context": "government-id", "source": "synthetic-fixture"}
RSG_F = {"value": "F", "context": "government-id", "source": "synthetic-fixture"}


def _read(name: str) -> dict[str, Any]:
    value = json.loads((REFERENCE_ROOT / name).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


@pytest.fixture
def predicate_rules_json() -> dict[str, Any]:
    return _read("rules-predicates.json")


@pytest.fixture
def predicate_observations_json() -> dict[str, Any]:
    return _read("observations-predicates.json")


def _rule(rules_json: dict[str, Any], rule_id: str) -> dict[str, Any]:
    rule = next(item for item in rules_json["rules"] if item["rule_id"] == rule_id)
    assert isinstance(rule, dict)
    return rule


def _observation(observations_json: dict[str, Any], obs_id: str) -> dict[str, Any]:
    item = next(
        item
        for item in observations_json["observations"]
        if item["observation_id"] == obs_id
    )
    assert isinstance(item, dict)
    return item


def _outcome(
    case_json: dict[str, Any],
    observations_json: dict[str, Any],
    rules_json: dict[str, Any],
    rule_id: str,
) -> Outcome:
    outcomes = evaluate(parse_bundle(case_json, observations_json, rules_json))
    return next(item for item in outcomes if item.rule_id == rule_id)


def _assert_code(code: str, call: Any, *args: object) -> None:
    with pytest.raises(ContextSafeError) as caught:
        call(*args)
    assert caught.value.code == code


# --- the packaged reference set exercises every predicate -------------------


def test_the_packaged_predicate_rule_set_names_every_predicate_once_or_more(
    predicate_rules_json: dict[str, Any],
) -> None:
    rule_set = parse_rule_set(predicate_rules_json)
    assert rule_set.schema_version == PREDICATE_RULE_SET_SCHEMA_VERSION
    assert {rule.predicate for rule in rule_set.rules} == set(RulePredicate)


def test_the_packaged_predicate_set_passes_on_its_own_observations(
    case_json: dict[str, Any],
    predicate_observations_json: dict[str, Any],
    predicate_rules_json: dict[str, Any],
) -> None:
    outcomes = evaluate(
        parse_bundle(case_json, predicate_observations_json, predicate_rules_json)
    )
    assert len(outcomes) == 9
    assert all(item.status is OutcomeStatus.PASSED for item in outcomes)
    assert {item.reason for item in outcomes} == AFFIRMATIVE_REASONS


def test_reason_sets_partition_the_closed_reason_vocabulary() -> None:
    predeclared = {OutcomeReason.PREDECLARED_NOT_APPLICABLE}
    assert AFFIRMATIVE_REASONS.isdisjoint(FAILURE_REASONS)
    assert AFFIRMATIVE_REASONS.isdisjoint(INDETERMINATE_REASONS)
    assert FAILURE_REASONS.isdisjoint(INDETERMINATE_REASONS)
    assert (
        AFFIRMATIVE_REASONS | FAILURE_REASONS | INDETERMINATE_REASONS | predeclared
    ) == set(OutcomeReason)
    assert len(AFFIRMATIVE_REASONS) == len(FAILURE_REASONS) == len(RulePredicate)


# --- the 0.1.0 contract is untouched -----------------------------------------


def test_the_exact_only_rule_set_still_parses_and_hashes_identically(
    rules_json: dict[str, Any],
) -> None:
    rule_set = parse_rule_set(rules_json)
    assert rule_set.schema_version == RULE_SET_SCHEMA_VERSION
    assert all(rule.predicate is RulePredicate.EXACT for rule in rule_set.rules)
    assert rule_set.to_dict() == rules_json


def test_a_predicate_field_is_unknown_under_the_exact_only_contract(
    rules_json: dict[str, Any],
) -> None:
    rules_json["rules"][0]["predicate"] = "exact"
    _assert_code("unknown_field", parse_rule_set, rules_json)


def test_an_explicit_exact_predicate_has_the_default_canonical_form(
    rules_json: dict[str, Any],
) -> None:
    """Writing ``exact`` out and leaving it off are the same rule."""

    rules_json["schema_version"] = PREDICATE_RULE_SET_SCHEMA_VERSION
    implicit = parse_rule_set(copy.deepcopy(rules_json))
    rules_json["rules"][0]["predicate"] = "exact"
    explicit = parse_rule_set(rules_json)
    assert explicit == implicit
    assert "predicate" not in explicit.to_dict()["rules"][0]


def test_an_unknown_predicate_is_refused(rules_json: dict[str, Any]) -> None:
    rules_json["schema_version"] = PREDICATE_RULE_SET_SCHEMA_VERSION
    rules_json["rules"][0]["predicate"] = "closest_supported_value"
    _assert_code("invalid_enum", parse_rule_set, rules_json)


def test_an_unsupported_rule_set_version_is_refused(
    rules_json: dict[str, Any],
) -> None:
    rules_json["schema_version"] = "contextsafe.rule-set/0.3.0"
    _assert_code("unsupported_schema", parse_rule_set, rules_json)


# --- predicate fields: only the field the predicate reads --------------------


@pytest.mark.parametrize(
    ("rule_id", "field", "value"),
    [
        ("A-I02", "forbidden", [{"status": "absent", "value": None}]),
        ("A-I02", "expected_count", 1),
        ("A-I02", "preserved_from", "registration"),
        ("A-I06", "expected_count", 1),
        ("A-I07", "forbidden", [RSG_M]),
        ("A-I08", "expected_count", 1),
        ("A-I01", "preserved_from", "registration"),
    ],
)
def test_a_field_another_predicate_reads_is_an_unknown_field(
    predicate_rules_json: dict[str, Any], rule_id: str, field: str, value: object
) -> None:
    _rule(predicate_rules_json, rule_id)[field] = value
    _assert_code("unknown_field", parse_rule_set, predicate_rules_json)


@pytest.mark.parametrize(
    ("rule_id", "field"),
    [("A-I06", "forbidden"), ("A-I07", "expected_count"), ("A-I08", "preserved_from")],
)
def test_the_field_a_predicate_reads_is_required(
    predicate_rules_json: dict[str, Any], rule_id: str, field: str
) -> None:
    del _rule(predicate_rules_json, rule_id)[field]
    _assert_code("missing_field", parse_rule_set, predicate_rules_json)


@pytest.mark.parametrize(
    ("rule_id", "mutation", "code"),
    [
        ("A-I06", {"forbidden": []}, "invalid_forbidden_set"),
        ("A-I06", {"forbidden": [RSG_M] * 17}, "invalid_forbidden_set"),
        ("A-I06", {"forbidden": [RSG_M, RSG_M]}, "duplicate_forbidden_value"),
        (
            "A-I06",
            {"forbidden": [{"value": "Q", "context": "c", "source": "s"}]},
            "invalid_rsg_value",
        ),
        (
            "A-I06",
            {"forbidden": [{"status": "absent", "value": None}]},
            "unknown_field",
        ),
        ("A-I07", {"expected_count": 0}, "invalid_expected_count"),
        ("A-I07", {"expected_count": 65}, "invalid_expected_count"),
        ("A-I07", {"expected_count": True}, "invalid_expected_count"),
        ("A-I07", {"expected_count": "1"}, "invalid_expected_count"),
        ("A-I08", {"preserved_from": "ehr"}, "invalid_checkpoint_pair"),
        ("A-I08", {"preserved_from": "elsewhere"}, "invalid_enum"),
    ],
)
def test_predicate_fields_fail_closed_at_their_bounds(
    predicate_rules_json: dict[str, Any],
    rule_id: str,
    mutation: dict[str, Any],
    code: str,
) -> None:
    _rule(predicate_rules_json, rule_id).update(mutation)
    _assert_code(code, parse_rule_set, predicate_rules_json)


def test_expected_count_of_exactly_the_bound_is_accepted(
    predicate_rules_json: dict[str, Any],
) -> None:
    _rule(predicate_rules_json, "A-I07")["expected_count"] = 64
    assert parse_rule_set(predicate_rules_json).rules[6].expected_count == 64


def test_a_forbidden_set_of_exactly_the_bound_is_accepted(
    predicate_rules_json: dict[str, Any],
) -> None:
    forbidden = [
        {"value": "M", "context": f"context-{index}", "source": "synthetic-fixture"}
        for index in range(16)
    ]
    _rule(predicate_rules_json, "A-I06")["forbidden"] = forbidden
    assert len(parse_rule_set(predicate_rules_json).rules[5].forbidden) == 16


def test_the_expected_value_cannot_also_be_forbidden(
    predicate_rules_json: dict[str, Any],
) -> None:
    rule = _rule(predicate_rules_json, "A-I06")
    rule["forbidden"] = [RSG_M, rule["expected"]]
    _assert_code("forbidden_expected_conflict", parse_rule_set, predicate_rules_json)


@pytest.mark.parametrize(
    ("predicate", "concept", "expected"),
    [
        ("present", "recorded_sex_or_gender", None),
        ("status_preserved", "sex_parameter_for_clinical_use", None),
        (
            "not_overwritten_by",
            "pronouns",
            {"status": "specified", "value": "they/them"},
        ),
        ("not_overwritten_by", "recorded_sex_or_gender", None),
    ],
)
def test_a_predicate_that_would_be_vacuous_for_a_concept_is_refused(
    predicate_rules_json: dict[str, Any],
    case_json: dict[str, Any],
    predicate: str,
    concept: str,
    expected: dict[str, Any] | None,
) -> None:
    rule = _rule(predicate_rules_json, "A-I01")
    rule["predicate"] = predicate
    rule["concept"] = concept
    rule["expected"] = expected or case_json["concepts"][concept][0]
    _assert_code("predicate_concept_mismatch", parse_rule_set, predicate_rules_json)


# --- cross-document checks in parse_bundle -----------------------------------


def test_a_forbidden_value_the_case_declares_is_refused(
    case_json: dict[str, Any],
    predicate_observations_json: dict[str, Any],
    predicate_rules_json: dict[str, Any],
) -> None:
    case_json["concepts"]["recorded_sex_or_gender"].append(RSG_F)
    _rule(predicate_rules_json, "A-I07")["expected_count"] = 2
    _assert_code(
        "forbidden_case_conflict",
        parse_bundle,
        case_json,
        predicate_observations_json,
        predicate_rules_json,
    )


def test_present_requires_the_case_to_specify_the_value(
    case_json: dict[str, Any],
    predicate_observations_json: dict[str, Any],
    predicate_rules_json: dict[str, Any],
) -> None:
    declined = {"status": "declined", "value": None}
    case_json["concepts"]["pronouns"] = declined
    for rule_id in ("A-I02", "A-I04"):
        _rule(predicate_rules_json, rule_id)["expected"] = declined
    _assert_code(
        "predicate_expectation_mismatch",
        parse_bundle,
        case_json,
        predicate_observations_json,
        predicate_rules_json,
    )


def test_expected_count_must_equal_the_records_the_case_declares(
    case_json: dict[str, Any],
    predicate_observations_json: dict[str, Any],
    predicate_rules_json: dict[str, Any],
) -> None:
    _rule(predicate_rules_json, "A-I07")["expected_count"] = 2
    _assert_code(
        "rule_count_mismatch",
        parse_bundle,
        case_json,
        predicate_observations_json,
        predicate_rules_json,
    )


def _pronouns_equal_to_the_expected_gender_identity(
    case_json: dict[str, Any], predicate_rules_json: dict[str, Any]
) -> None:
    """Make the case declare GI's expected scalar under pronouns as well."""

    colliding = {"status": "specified", "value": "fixture-gender-1"}
    case_json["concepts"]["pronouns"] = colliding
    for rule_id in ("A-I02", "A-I04"):
        _rule(predicate_rules_json, rule_id)["expected"] = colliding


def test_not_overwritten_by_cannot_expect_a_scalar_another_concept_declares(
    case_json: dict[str, Any],
    predicate_observations_json: dict[str, Any],
    predicate_rules_json: dict[str, Any],
) -> None:
    """A faithful GI observation would be reported as overwritten, so the rule
    could never pass; the bundle is refused instead of evaluated."""

    _pronouns_equal_to_the_expected_gender_identity(case_json, predicate_rules_json)
    with pytest.raises(ContextSafeError) as caught:
        parse_bundle(case_json, predicate_observations_json, predicate_rules_json)
    assert caught.value.code == "overwritten_expectation_conflict"
    assert caught.value.path == "$.rules[4].expected"
    assert "fixture-gender" not in caught.value.message


def test_the_overwritten_expectation_check_is_only_for_not_overwritten_by(
    case_json: dict[str, Any],
    predicate_observations_json: dict[str, Any],
    predicate_rules_json: dict[str, Any],
) -> None:
    """The same manifest is accepted once no rule makes the A-011 claim."""

    _pronouns_equal_to_the_expected_gender_identity(case_json, predicate_rules_json)
    _observation(predicate_observations_json, "OBS-I01-PRONOUNS")["value"] = {
        "status": "specified",
        "value": "fixture-gender-1",
    }
    del _rule(predicate_rules_json, "A-I05")["predicate"]
    outcome = _outcome(
        case_json, predicate_observations_json, predicate_rules_json, "A-I05"
    )
    assert outcome.status is OutcomeStatus.PASSED
    assert outcome.reason is OutcomeReason.AFFIRMATIVE_EVIDENCE_MATCH


def test_a_predicate_rule_still_needs_an_expectation_the_case_declares(
    case_json: dict[str, Any],
    predicate_observations_json: dict[str, Any],
    predicate_rules_json: dict[str, Any],
) -> None:
    _rule(predicate_rules_json, "A-I02")["expected"] = {
        "status": "specified",
        "value": "ze/hir",
    }
    _assert_code(
        "rule_expectation_mismatch",
        parse_bundle,
        case_json,
        predicate_observations_json,
        predicate_rules_json,
    )


# --- present (A-008) ---------------------------------------------------------


@pytest.mark.parametrize("status", ["declined", "unknown", "absent"])
def test_present_fails_on_every_status_that_carries_no_value(
    case_json: dict[str, Any],
    predicate_observations_json: dict[str, Any],
    predicate_rules_json: dict[str, Any],
    status: str,
) -> None:
    _observation(predicate_observations_json, "OBS-I01-PRONOUNS")["value"] = {
        "status": status,
        "value": None,
    }
    outcome = _outcome(
        case_json, predicate_observations_json, predicate_rules_json, "A-I02"
    )
    assert outcome.status is OutcomeStatus.FAIL
    assert outcome.reason is OutcomeReason.VALUE_NOT_PRESENT


def test_present_passes_on_a_different_specified_value(
    case_json: dict[str, Any],
    predicate_observations_json: dict[str, Any],
    predicate_rules_json: dict[str, Any],
) -> None:
    """Presence is not equality: the exact rule is what decides the value."""

    _observation(predicate_observations_json, "OBS-I01-PRONOUNS")["value"] = {
        "status": "specified",
        "value": "ze/hir",
    }
    outcome = _outcome(
        case_json, predicate_observations_json, predicate_rules_json, "A-I02"
    )
    assert outcome.status is OutcomeStatus.PASSED
    assert outcome.reason is OutcomeReason.VALUE_PRESENT


# --- status_preserved (A-009) ------------------------------------------------


def _declined_bundle(
    case_json: dict[str, Any],
    predicate_observations_json: dict[str, Any],
    predicate_rules_json: dict[str, Any],
) -> None:
    """Turn the reference case into one whose GI is explicitly declined."""

    case_json["concepts"]["gender_identity"] = GI_DECLINED
    _observation(predicate_observations_json, "OBS-I01-GI")["value"] = GI_DECLINED
    for rule_id in ("A-I01", "A-I03", "A-I05"):
        _rule(predicate_rules_json, rule_id)["expected"] = GI_DECLINED


@pytest.mark.parametrize(
    "observed",
    [
        GI_UNKNOWN,
        GI_ABSENT,
        {
            "status": "specified",
            "value": "fixture-gender-1",
            "code_system": "urn:contextsafe:fixture",
        },
    ],
    ids=["unknown", "absent", "populated"],
)
def test_declined_never_becomes_unknown_absent_or_populated(
    case_json: dict[str, Any],
    predicate_observations_json: dict[str, Any],
    predicate_rules_json: dict[str, Any],
    observed: dict[str, Any],
) -> None:
    """A-009, F-005, F-031: the three ways a declined value can be rewritten."""

    _declined_bundle(case_json, predicate_observations_json, predicate_rules_json)
    _observation(predicate_observations_json, "OBS-I01-GI")["value"] = observed
    outcome = _outcome(
        case_json, predicate_observations_json, predicate_rules_json, "A-I03"
    )
    assert outcome.status is OutcomeStatus.FAIL
    assert outcome.reason is OutcomeReason.STATUS_NOT_PRESERVED


def test_declined_that_stays_declined_passes(
    case_json: dict[str, Any],
    predicate_observations_json: dict[str, Any],
    predicate_rules_json: dict[str, Any],
) -> None:
    _declined_bundle(case_json, predicate_observations_json, predicate_rules_json)
    outcome = _outcome(
        case_json, predicate_observations_json, predicate_rules_json, "A-I03"
    )
    assert outcome.status is OutcomeStatus.PASSED
    assert outcome.reason is OutcomeReason.STATUS_PRESERVED


def test_status_preserved_ignores_the_value_itself(
    case_json: dict[str, Any],
    predicate_observations_json: dict[str, Any],
    predicate_rules_json: dict[str, Any],
) -> None:
    """A status-only claim: the exact rule beside it is what decides the value."""

    _observation(predicate_observations_json, "OBS-I01-GI")["value"]["value"] = (
        "fixture-gender-9"
    )
    status_outcome = _outcome(
        case_json, predicate_observations_json, predicate_rules_json, "A-I03"
    )
    exact_outcome = _outcome(
        case_json, predicate_observations_json, predicate_rules_json, "A-I01"
    )
    assert status_outcome.status is OutcomeStatus.PASSED
    assert exact_outcome.status is OutcomeStatus.FAIL


# --- not_coerced (A-014) -----------------------------------------------------


@pytest.mark.parametrize("coerced", [RSG_M, RSG_F])
def test_x_coerced_into_m_or_f_fails(
    case_json: dict[str, Any],
    predicate_observations_json: dict[str, Any],
    predicate_rules_json: dict[str, Any],
    coerced: dict[str, Any],
) -> None:
    _observation(predicate_observations_json, "OBS-I01-RSG")["value"] = coerced
    outcome = _outcome(
        case_json, predicate_observations_json, predicate_rules_json, "A-I06"
    )
    assert outcome.status is OutcomeStatus.FAIL
    assert outcome.reason is OutcomeReason.VALUE_COERCED


@pytest.mark.parametrize("coerced_to", ["M", "F"])
def test_a_coercion_that_also_rewrites_context_is_caught_by_the_paired_exact_rule(
    case_json: dict[str, Any],
    predicate_observations_json: dict[str, Any],
    predicate_rules_json: dict[str, Any],
    coerced_to: str,
) -> None:
    """The documented limit, held against the packaged pair as shipped.

    ``not_coerced`` compares whole typed values, so X rewritten to M or F
    together with its context is outside A-I06's forbidden set and A-I06
    reports ``pass``. A-I09, the ``exact`` rule the reference set pairs with
    it on the same field, is what turns the receipt: the bundle is reported
    with a failure and the summary counts it, without any rule being edited.
    """

    _observation(predicate_observations_json, "OBS-I01-RSG")["value"] = {
        "value": coerced_to,
        "context": "payer",
        "source": "synthetic-fixture",
    }
    bundle = parse_bundle(case_json, predicate_observations_json, predicate_rules_json)
    outcomes = evaluate(bundle)
    by_rule = {item.rule_id: item for item in outcomes}
    assert by_rule["A-I06"].status is OutcomeStatus.PASSED
    assert by_rule["A-I06"].reason is OutcomeReason.VALUE_NOT_COERCED
    assert by_rule["A-I09"].status is OutcomeStatus.FAIL
    assert by_rule["A-I09"].reason is OutcomeReason.SEMANTIC_MISMATCH
    assert by_rule["A-I09"].expected_sha256 not in by_rule["A-I09"].observed_sha256s
    summary = build_receipt(bundle, outcomes)["summary"]
    assert summary["fail"] == 1
    assert summary["pass"] == 8


def test_the_packaged_pair_carries_the_exact_rule_beside_not_coerced(
    predicate_rules_json: dict[str, Any],
) -> None:
    """The pairing the docs prescribe is present in the shipped set, not only
    described: for every ``not_coerced`` rule there is an ``exact`` rule on the
    same case, checkpoint, concept, and expected value."""

    rule_set = parse_rule_set(predicate_rules_json)
    exact_keys = {
        (rule.case_id, rule.checkpoint, rule.concept, rule.expected)
        for rule in rule_set.rules
        if rule.predicate is RulePredicate.EXACT
    }
    not_coerced = [
        rule for rule in rule_set.rules if rule.predicate is RulePredicate.NOT_COERCED
    ]
    assert not_coerced
    for rule in not_coerced:
        assert (
            rule.case_id,
            rule.checkpoint,
            rule.concept,
            rule.expected,
        ) in exact_keys


# --- record_count (A-013) ----------------------------------------------------


def test_a_second_record_where_one_is_declared_fails(
    case_json: dict[str, Any],
    predicate_observations_json: dict[str, Any],
    predicate_rules_json: dict[str, Any],
) -> None:
    extra = copy.deepcopy(_observation(predicate_observations_json, "OBS-I01-RSG"))
    extra["observation_id"] = "OBS-I01-RSG-2"
    extra["value"]["context"] = "payer"
    predicate_observations_json["observations"].append(extra)
    outcome = _outcome(
        case_json, predicate_observations_json, predicate_rules_json, "A-I07"
    )
    assert outcome.status is OutcomeStatus.FAIL
    assert outcome.reason is OutcomeReason.RECORD_COUNT_CHANGED
    assert len(outcome.observed_sha256s) == 2


def test_two_records_that_remain_two_distinct_records_pass(
    case_json: dict[str, Any],
    predicate_observations_json: dict[str, Any],
    predicate_rules_json: dict[str, Any],
) -> None:
    case_json["concepts"]["recorded_sex_or_gender"].append(
        {"value": "F", "context": "payer", "source": "synthetic-fixture"}
    )
    _rule(predicate_rules_json, "A-I06")["forbidden"] = [RSG_M]
    _rule(predicate_rules_json, "A-I07")["expected_count"] = 2
    extra = copy.deepcopy(_observation(predicate_observations_json, "OBS-I01-RSG"))
    extra["observation_id"] = "OBS-I01-RSG-2"
    extra["value"] = {"value": "F", "context": "payer", "source": "synthetic-fixture"}
    predicate_observations_json["observations"].append(extra)
    outcome = _outcome(
        case_json, predicate_observations_json, predicate_rules_json, "A-I07"
    )
    assert outcome.status is OutcomeStatus.PASSED
    assert outcome.reason is OutcomeReason.RECORD_COUNT_PRESERVED
    assert len(outcome.observed_sha256s) == 2


def test_two_copies_of_one_record_are_not_two_records(
    case_json: dict[str, Any],
    predicate_observations_json: dict[str, Any],
    predicate_rules_json: dict[str, Any],
) -> None:
    """Collapse followed by duplication keeps the count and loses the record."""

    case_json["concepts"]["recorded_sex_or_gender"].append(
        {"value": "F", "context": "payer", "source": "synthetic-fixture"}
    )
    _rule(predicate_rules_json, "A-I06")["forbidden"] = [RSG_M]
    _rule(predicate_rules_json, "A-I07")["expected_count"] = 2
    extra = copy.deepcopy(_observation(predicate_observations_json, "OBS-I01-RSG"))
    extra["observation_id"] = "OBS-I01-RSG-2"
    predicate_observations_json["observations"].append(extra)
    outcome = _outcome(
        case_json, predicate_observations_json, predicate_rules_json, "A-I07"
    )
    assert outcome.status is OutcomeStatus.FAIL
    assert outcome.reason is OutcomeReason.RECORD_COUNT_CHANGED


def test_record_count_with_no_observation_is_missing_evidence_not_zero(
    case_json: dict[str, Any],
    predicate_observations_json: dict[str, Any],
    predicate_rules_json: dict[str, Any],
) -> None:
    predicate_observations_json["observations"] = [
        item
        for item in predicate_observations_json["observations"]
        if item["observation_id"] != "OBS-I01-RSG"
    ]
    outcome = _outcome(
        case_json, predicate_observations_json, predicate_rules_json, "A-I07"
    )
    assert outcome.status is OutcomeStatus.INDETERMINATE
    assert outcome.reason is OutcomeReason.MISSING_EVIDENCE
    assert outcome.observed_sha256s == ()


# --- preserved_across (A-005, A-010, A-012) ----------------------------------


def test_a_value_that_changes_between_checkpoints_fails(
    case_json: dict[str, Any],
    predicate_observations_json: dict[str, Any],
    predicate_rules_json: dict[str, Any],
) -> None:
    _observation(predicate_observations_json, "OBS-I01-NTU")["value"]["value"] = (
        "CSYN-OTHER"
    )
    _rule(predicate_rules_json, "A-I08")["expected"] = case_json["concepts"][
        "name_to_use"
    ]
    outcome = _outcome(
        case_json, predicate_observations_json, predicate_rules_json, "A-I08"
    )
    assert outcome.status is OutcomeStatus.FAIL
    assert outcome.reason is OutcomeReason.VALUE_CHANGED_ACROSS_CHECKPOINTS
    assert len(outcome.observed_sha256s) == 2
    assert len(set(outcome.observed_sha256s)) == 2


@pytest.mark.parametrize("dropped", ["OBS-I01-NTU", "OBS-I01-NTU-REG"])
def test_preserved_across_with_either_checkpoint_unobserved_is_indeterminate(
    case_json: dict[str, Any],
    predicate_observations_json: dict[str, Any],
    predicate_rules_json: dict[str, Any],
    dropped: str,
) -> None:
    predicate_observations_json["observations"] = [
        item
        for item in predicate_observations_json["observations"]
        if item["observation_id"] != dropped
    ]
    outcome = _outcome(
        case_json, predicate_observations_json, predicate_rules_json, "A-I08"
    )
    assert outcome.status is OutcomeStatus.INDETERMINATE
    assert outcome.reason is OutcomeReason.MISSING_EVIDENCE


def test_preserved_across_with_an_ambiguous_checkpoint_is_indeterminate(
    case_json: dict[str, Any],
    predicate_observations_json: dict[str, Any],
    predicate_rules_json: dict[str, Any],
) -> None:
    extra = copy.deepcopy(_observation(predicate_observations_json, "OBS-I01-NTU-REG"))
    extra["observation_id"] = "OBS-I01-NTU-REG-2"
    predicate_observations_json["observations"].append(extra)
    outcome = _outcome(
        case_json, predicate_observations_json, predicate_rules_json, "A-I08"
    )
    assert outcome.status is OutcomeStatus.INDETERMINATE
    assert outcome.reason is OutcomeReason.AMBIGUOUS_EVIDENCE


def test_preserved_across_is_a_preservation_claim_not_a_correctness_claim(
    case_json: dict[str, Any],
    predicate_observations_json: dict[str, Any],
    predicate_rules_json: dict[str, Any],
) -> None:
    """Wrong at both checkpoints is preserved; the reason code says which."""

    for obs_id in ("OBS-I01-NTU", "OBS-I01-NTU-REG"):
        _observation(predicate_observations_json, obs_id)["value"]["value"] = (
            "CSYN-OTHER"
        )
    outcome = _outcome(
        case_json, predicate_observations_json, predicate_rules_json, "A-I08"
    )
    assert outcome.status is OutcomeStatus.PASSED
    assert outcome.reason is OutcomeReason.VALUE_PRESERVED_ACROSS_CHECKPOINTS
    assert outcome.expected_sha256 not in outcome.observed_sha256s


# --- not_overwritten_by (A-011) ----------------------------------------------


@pytest.mark.parametrize(
    "scalar", ["X", "CSYN-ASTER", "they/them", "fixture-context-1"]
)
def test_gi_carrying_any_other_concepts_value_fails(
    case_json: dict[str, Any],
    predicate_observations_json: dict[str, Any],
    predicate_rules_json: dict[str, Any],
    scalar: str,
) -> None:
    """RSG, name to use, pronouns, and SPCU each overwrite GI in turn."""

    _observation(predicate_observations_json, "OBS-I01-GI")["value"]["value"] = scalar
    outcome = _outcome(
        case_json, predicate_observations_json, predicate_rules_json, "A-I05"
    )
    assert outcome.status is OutcomeStatus.FAIL
    assert outcome.reason is OutcomeReason.OVERWRITTEN_BY_OTHER_CONCEPT


def test_gi_with_a_different_but_own_value_is_not_overwritten(
    case_json: dict[str, Any],
    predicate_observations_json: dict[str, Any],
    predicate_rules_json: dict[str, Any],
) -> None:
    _observation(predicate_observations_json, "OBS-I01-GI")["value"]["value"] = (
        "fixture-gender-9"
    )
    outcome = _outcome(
        case_json, predicate_observations_json, predicate_rules_json, "A-I05"
    )
    assert outcome.status is OutcomeStatus.PASSED
    assert outcome.reason is OutcomeReason.VALUE_NOT_OVERWRITTEN


def test_a_gi_with_no_scalar_is_not_carrying_another_concepts_value(
    case_json: dict[str, Any],
    predicate_observations_json: dict[str, Any],
    predicate_rules_json: dict[str, Any],
) -> None:
    _observation(predicate_observations_json, "OBS-I01-GI")["value"] = GI_DECLINED
    outcome = _outcome(
        case_json, predicate_observations_json, predicate_rules_json, "A-I05"
    )
    assert outcome.status is OutcomeStatus.PASSED
    assert outcome.reason is OutcomeReason.VALUE_NOT_OVERWRITTEN


# --- the algebra over every predicate ----------------------------------------


@pytest.mark.parametrize(
    "rule_id",
    ["A-I01", "A-I02", "A-I03", "A-I04", "A-I05", "A-I06", "A-I07", "A-I09"],
)
def test_every_single_observation_predicate_is_indeterminate_without_evidence(
    case_json: dict[str, Any],
    predicate_observations_json: dict[str, Any],
    predicate_rules_json: dict[str, Any],
    rule_id: str,
) -> None:
    rule = _rule(predicate_rules_json, rule_id)
    predicate_observations_json["observations"] = [
        item
        for item in predicate_observations_json["observations"]
        if not (
            item["concept"] == rule["concept"]
            and item["checkpoint"] == rule["checkpoint"]
        )
    ]
    outcome = _outcome(
        case_json, predicate_observations_json, predicate_rules_json, rule_id
    )
    assert outcome.status is OutcomeStatus.INDETERMINATE
    assert outcome.reason is OutcomeReason.MISSING_EVIDENCE


@pytest.mark.parametrize(
    "rule_id", ["A-I01", "A-I02", "A-I03", "A-I04", "A-I05", "A-I06", "A-I09"]
)
def test_every_single_observation_predicate_is_indeterminate_when_ambiguous(
    case_json: dict[str, Any],
    predicate_observations_json: dict[str, Any],
    predicate_rules_json: dict[str, Any],
    rule_id: str,
) -> None:
    rule = _rule(predicate_rules_json, rule_id)
    original = next(
        item
        for item in predicate_observations_json["observations"]
        if item["concept"] == rule["concept"]
        and item["checkpoint"] == rule["checkpoint"]
    )
    duplicate = copy.deepcopy(original)
    duplicate["observation_id"] = f"{original['observation_id']}-DUP"
    predicate_observations_json["observations"].append(duplicate)
    outcome = _outcome(
        case_json, predicate_observations_json, predicate_rules_json, rule_id
    )
    assert outcome.status is OutcomeStatus.INDETERMINATE
    assert outcome.reason is OutcomeReason.AMBIGUOUS_EVIDENCE


def test_a_non_required_predicate_rule_is_not_applicable(
    case_json: dict[str, Any],
    predicate_observations_json: dict[str, Any],
    predicate_rules_json: dict[str, Any],
) -> None:
    for rule in predicate_rules_json["rules"]:
        rule["required"] = False
    outcomes = evaluate(
        parse_bundle(case_json, predicate_observations_json, predicate_rules_json)
    )
    assert all(item.status is OutcomeStatus.NOT_APPLICABLE for item in outcomes)
    assert all(
        item.reason is OutcomeReason.PREDECLARED_NOT_APPLICABLE for item in outcomes
    )


def test_predicate_receipts_carry_hashes_and_never_a_forbidden_or_observed_value(
    case_json: dict[str, Any],
    predicate_observations_json: dict[str, Any],
    predicate_rules_json: dict[str, Any],
) -> None:
    _observation(predicate_observations_json, "OBS-I01-RSG")["value"] = RSG_F
    bundle = parse_bundle(case_json, predicate_observations_json, predicate_rules_json)
    rendered = render_receipt(build_receipt(bundle, evaluate(bundle)))
    for prohibited in (
        "government-id",
        "CSYN-ASTER",
        "fixture-gender-1",
        "they/them",
        '"F"',
        '"M"',
        '"X"',
        "forbidden",
        "expected_count",
        "preserved_from",
    ):
        assert prohibited not in rendered
