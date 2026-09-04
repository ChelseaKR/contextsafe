"""The seeded-fault library for the identity predicates (B-028, P0-05).

``docs/09-TEST-AND-EVALUATION.md`` section 4 names 36 seeded faults and the
assertion expected to detect each. This module holds the seven that the
identity, name-to-use, pronoun, and recorded-sex-or-gender predicates can
detect today, as complete synthetic fixtures under
``tests/fixtures/seeded-faults/``: each file carries the case, the rule set,
and the observation set with exactly one fault applied, so a reviewer can read
what was injected without running anything.

Each fault must be reported as ``fail`` with the reason the predicate
publishes, and never as ``pass``. The companion ``clean/`` directory holds the
un-faulted form of every case variant, so the tests also prove that the fault
is what turned the outcome, not the variant itself.

The case variants are synthetic and shaped like CTP-007, CTP-008, and
CTP-010 in ``docs/05-DATA-AND-EVIDENCE.md`` section 3 because the packaged
CTP-I01 has no declined, unknown, or second recorded-sex-or-gender value to
corrupt. They are fault-library inputs, not additions to any canonical pack,
and nothing here is governed content.
"""

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from contextsafe.canonical import sha256_json
from contextsafe.evaluator import Outcome, evaluate
from contextsafe.models import (
    FAILURE_REASONS,
    OutcomeReason,
    OutcomeStatus,
)
from contextsafe.receipt import build_receipt
from contextsafe.validation import parse_bundle

ROOT = Path(__file__).resolve().parents[1]
FAULTS = ROOT / "tests" / "fixtures" / "seeded-faults"
RULE_SET_SCHEMA = json.loads(
    (ROOT / "schemas" / "contextsafe-rule-set-v0.2.schema.json").read_text(
        encoding="utf-8"
    )
)

EXPECTED_DETECTION: dict[str, tuple[str, str, OutcomeReason]] = {
    # fault: (assertion from docs/09 section 4, detector rule id, reason)
    "F-004": ("A-008", "A-I02", OutcomeReason.VALUE_NOT_PRESENT),
    "F-005": ("A-009", "A-I01", OutcomeReason.STATUS_NOT_PRESERVED),
    "F-006": ("A-011", "A-I05", OutcomeReason.OVERWRITTEN_BY_OTHER_CONCEPT),
    "F-007": ("A-014", "A-I06", OutcomeReason.VALUE_COERCED),
    "F-008": ("A-014", "A-I01", OutcomeReason.VALUE_COERCED),
    "F-010": ("A-013", "A-I01", OutcomeReason.RECORD_COUNT_CHANGED),
    "F-031": ("A-009", "A-I01", OutcomeReason.STATUS_NOT_PRESERVED),
}
"""Restated here rather than read from the fixture, so the fixture cannot
declare its own expected verdict and the test then agree with it."""


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _outcomes(document: dict[str, Any]) -> tuple[Outcome, ...]:
    bundle = parse_bundle(document["case"], document["observations"], document["rules"])
    return evaluate(bundle)


def _by_rule(outcomes: tuple[Outcome, ...], rule_id: str) -> Outcome:
    return next(item for item in outcomes if item.rule_id == rule_id)


FAULT_FILES = sorted(FAULTS.glob("F-*.json"))
CLEAN_FILES = sorted((FAULTS / "clean").glob("*.json"))


def test_the_library_holds_exactly_the_faults_the_table_expects() -> None:
    """The denominator: seven files, seven rows, and nothing unaccounted for."""

    assert [path.stem for path in FAULT_FILES] == sorted(EXPECTED_DETECTION)
    assert len(FAULT_FILES) == 7


def test_every_fault_file_names_the_assertion_the_table_names() -> None:
    for path in FAULT_FILES:
        document = _load(path)
        assert document["fault"] == path.stem
        assert document["assertion"] == EXPECTED_DETECTION[path.stem][0]
        assert document["mutation"].strip()
        assert set(document) == {
            "fault",
            "mutation",
            "assertion",
            "case",
            "rules",
            "observations",
        }


@pytest.mark.parametrize("path", FAULT_FILES, ids=[path.stem for path in FAULT_FILES])
def test_each_fault_is_reported_as_fail_with_its_own_reason_and_never_as_pass(
    path: Path,
) -> None:
    _, rule_id, reason = EXPECTED_DETECTION[path.stem]
    outcomes = _outcomes(_load(path))
    detector = _by_rule(outcomes, rule_id)
    assert detector.status is OutcomeStatus.FAIL
    assert detector.reason is reason
    assert detector.status is not OutcomeStatus.PASSED
    assert reason in FAILURE_REASONS
    assert detector.observed_sha256s
    assert detector.expected_sha256 not in detector.observed_sha256s


@pytest.mark.parametrize("path", FAULT_FILES, ids=[path.stem for path in FAULT_FILES])
def test_each_fault_leaves_a_fail_count_in_the_receipt_summary(path: Path) -> None:
    document = _load(path)
    bundle = parse_bundle(document["case"], document["observations"], document["rules"])
    receipt = build_receipt(bundle, evaluate(bundle))
    assert receipt["summary"]["fail"] >= 1


@pytest.mark.parametrize("path", CLEAN_FILES, ids=[path.stem for path in CLEAN_FILES])
def test_each_case_variant_passes_every_rule_before_its_fault_is_applied(
    path: Path,
) -> None:
    outcomes = _outcomes(_load(path))
    assert outcomes
    assert all(item.status is OutcomeStatus.PASSED for item in outcomes)


def test_every_fault_rule_set_validates_against_the_published_contract() -> None:
    validator = Draft202012Validator(RULE_SET_SCHEMA)
    for path in (*FAULT_FILES, *CLEAN_FILES):
        validator.validate(_load(path)["rules"])


def test_faults_against_a_variant_case_have_a_clean_counterpart() -> None:
    """A variant without its clean form could hide a rule that never passes."""

    clean_cases = {path.stem for path in CLEAN_FILES}
    for path in FAULT_FILES:
        case_id = _load(path)["case"]["case_id"]
        assert case_id == "CTP-I01" or case_id in clean_cases


def test_the_declined_fault_would_pass_if_declined_became_declined_again() -> None:
    """F-005 and F-031 fail because the status moved, not because of the case."""

    for name in ("F-005", "F-031"):
        document = _load(FAULTS / f"{name}.json")
        clean = _load(FAULTS / "clean" / "CTP-I07.json")
        document["observations"] = clean["observations"]
        assert all(item.status is OutcomeStatus.PASSED for item in _outcomes(document))


@pytest.mark.parametrize(
    "restamp",
    [
        {"context": "payer"},
        {"source": "interface-engine"},
        {"context": "payer", "source": "interface-engine"},
    ],
    ids=["context", "source", "both"],
)
@pytest.mark.parametrize("name", ["F-007", "F-008"])
def test_the_coercion_faults_are_still_detected_when_the_boundary_restamps_the_record(
    name: str, restamp: dict[str, str]
) -> None:
    """F-007 and F-008 with the boundary's own context or source on the record.

    The coerced value then hashes like nothing in the forbidden set, and the
    detector must still report ``fail``/``value_coerced``: A-014 is a claim
    about the value, and a boundary that relabels what it rewrote does not
    earn a pass for it.
    """

    document = _load(FAULTS / f"{name}.json")
    _, rule_id, reason = EXPECTED_DETECTION[name]
    coerced = next(
        item
        for item in document["observations"]["observations"]
        if item["concept"] == "recorded_sex_or_gender"
    )
    coerced["value"].update(restamp)
    bundle = parse_bundle(document["case"], document["observations"], document["rules"])
    detector = _by_rule(evaluate(bundle), rule_id)
    forbidden_hashes = {
        sha256_json(item.to_dict())
        for rule in bundle.rule_set.rules
        for item in rule.forbidden
    }
    assert detector.status is OutcomeStatus.FAIL
    assert detector.reason is reason
    assert forbidden_hashes.isdisjoint(detector.observed_sha256s)


def test_no_fault_fixture_carries_a_non_synthetic_identifier() -> None:
    for path in (*FAULT_FILES, *CLEAN_FILES):
        document = _load(path)
        identifier = document["case"]["synthetic_identifier"]
        assert identifier["system"] == "urn:contextsafe:synthetic"
        assert identifier["value"] == f"CSYN-{document['case']['case_id']}"
        name = document["case"]["concepts"]["name_to_use"]["value"]
        assert name is None or name.startswith("CSYN-")
