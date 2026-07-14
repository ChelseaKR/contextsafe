"""Determinism and safety invariants for evaluation and receipts."""

from typing import Any

from contextsafe.evaluator import evaluate
from contextsafe.models import OutcomeStatus
from contextsafe.receipt import build_receipt, render_receipt
from contextsafe.validation import parse_bundle


def _bundle(
    case_json: dict[str, Any],
    observations_json: dict[str, Any],
    rules_json: dict[str, Any],
) -> Any:
    return parse_bundle(case_json, observations_json, rules_json)


def test_reference_fixture_passes_only_on_affirmative_evidence(
    case_json: dict[str, Any],
    observations_json: dict[str, Any],
    rules_json: dict[str, Any],
) -> None:
    outcomes = evaluate(_bundle(case_json, observations_json, rules_json))
    assert len(outcomes) == 5
    assert all(item.status is OutcomeStatus.PASSED for item in outcomes)
    assert all(item.reason == "affirmative_evidence_match" for item in outcomes)


def test_missing_evidence_is_indeterminate_never_pass(
    case_json: dict[str, Any],
    observations_json: dict[str, Any],
    rules_json: dict[str, Any],
) -> None:
    observations_json["observations"] = observations_json["observations"][:-1]
    outcomes = evaluate(_bundle(case_json, observations_json, rules_json))
    missing = next(item for item in outcomes if item.rule_id == "A-I05")
    assert missing.status is OutcomeStatus.INDETERMINATE
    assert missing.reason == "missing_evidence"
    assert missing.observed_sha256s == ()


def test_mismatched_evidence_fails(
    case_json: dict[str, Any],
    observations_json: dict[str, Any],
    rules_json: dict[str, Any],
) -> None:
    observations_json["observations"][4]["value"]["value"] = "ze/hir"
    outcome = evaluate(_bundle(case_json, observations_json, rules_json))[-1]
    assert outcome.status is OutcomeStatus.FAIL
    assert outcome.reason == "semantic_mismatch"


def test_multiple_matching_observations_are_indeterminate(
    case_json: dict[str, Any],
    observations_json: dict[str, Any],
    rules_json: dict[str, Any],
) -> None:
    duplicate = observations_json["observations"][4].copy()
    duplicate["observation_id"] = "OBS-I01-PRONOUNS-2"
    observations_json["observations"].append(duplicate)
    outcome = evaluate(_bundle(case_json, observations_json, rules_json))[-1]
    assert outcome.status is OutcomeStatus.INDETERMINATE
    assert outcome.reason == "ambiguous_evidence"


def test_predeclared_nonrequired_rule_is_not_applicable(
    case_json: dict[str, Any],
    observations_json: dict[str, Any],
    rules_json: dict[str, Any],
) -> None:
    rules_json["rules"][0]["required"] = False
    outcome = evaluate(_bundle(case_json, observations_json, rules_json))[0]
    assert outcome.status is OutcomeStatus.NOT_APPLICABLE
    assert outcome.reason == "predeclared_not_applicable"


def test_deterministic_replay_is_byte_identical_and_order_independent(
    case_json: dict[str, Any],
    observations_json: dict[str, Any],
    rules_json: dict[str, Any],
) -> None:
    first_bundle = _bundle(case_json, observations_json, rules_json)
    first = render_receipt(build_receipt(first_bundle, evaluate(first_bundle)))
    observations_json["observations"].reverse()
    rules_json["rules"].reverse()
    second_bundle = _bundle(case_json, observations_json, rules_json)
    second = render_receipt(build_receipt(second_bundle, evaluate(second_bundle)))
    assert first == second
    assert first.endswith("\n")


def test_receipt_contains_hashes_but_no_semantic_or_source_values(
    case_json: dict[str, Any],
    observations_json: dict[str, Any],
    rules_json: dict[str, Any],
) -> None:
    bundle = _bundle(case_json, observations_json, rules_json)
    receipt = build_receipt(bundle, evaluate(bundle))
    rendered = render_receipt(receipt)
    assert set(receipt["hashes"]) == {
        "input_sha256",
        "rule_set_sha256",
        "result_sha256",
    }
    for prohibited in (
        "CSYN-ASTER",
        "fixture-gender-1",
        "fixture-context-1",
        "they/them",
        "government-id",
        "source_pointer",
    ):
        assert prohibited not in rendered
    assert receipt["summary"]["pass"] == 5
    assert receipt["scope"]["clinical_oracle_approved"] is False
    assert any("cannot prove" in item for item in receipt["limitations"])


def test_hashes_change_with_inputs_rules_and_results(
    case_json: dict[str, Any],
    observations_json: dict[str, Any],
    rules_json: dict[str, Any],
) -> None:
    baseline = _bundle(case_json, observations_json, rules_json)
    baseline_receipt = build_receipt(baseline, evaluate(baseline))
    observations_json["observations"][4]["value"]["value"] = "ze/hir"
    changed_input = _bundle(case_json, observations_json, rules_json)
    changed_receipt = build_receipt(changed_input, evaluate(changed_input))
    assert (
        baseline_receipt["hashes"]["input_sha256"]
        != changed_receipt["hashes"]["input_sha256"]
    )
    assert (
        baseline_receipt["hashes"]["result_sha256"]
        != changed_receipt["hashes"]["result_sha256"]
    )
    rules_json["rules"][0]["version"] = "0.1.1"
    changed_rules = _bundle(case_json, observations_json, rules_json)
    final_receipt = build_receipt(changed_rules, evaluate(changed_rules))
    assert (
        changed_receipt["hashes"]["rule_set_sha256"]
        != final_receipt["hashes"]["rule_set_sha256"]
    )
