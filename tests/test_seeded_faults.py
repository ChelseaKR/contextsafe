"""The seeded-fault library for the identity predicates (B-028, P0-05) and
the evidence-integrity faults of the divergence slice (B-031, P0-08).

``docs/09-TEST-AND-EVALUATION.md`` section 4 names 36 seeded faults and the
assertion expected to detect each. This module holds the seven that the
identity, name-to-use, pronoun, and recorded-sex-or-gender predicates can
detect today, plus F-023 and F-025, which are faults of the evaluator rather
than of the system under test: a checkpoint omitted yet reported as pass
(A-032), and a first divergence inferred across an unobserved boundary
(A-034). All are complete synthetic fixtures under
``tests/fixtures/seeded-faults/``: each file carries the case, the rule set,
and the observation set with exactly one fault applied, so a reviewer can read
what was injected without running anything.

Each predicate fault must be reported as ``fail`` with the reason the
predicate publishes, and never as ``pass``. Each evidence-integrity fault must
be reported the way the assertion demands: indeterminate and unobserved for
F-023, located only at observed boundaries for F-025. The companion ``clean/``
directory holds the un-faulted form of every case variant, so the tests also
prove that the fault is what turned the outcome, not the variant itself.

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
from contextsafe.divergence import ConceptDivergence, compute_divergence
from contextsafe.evaluator import Outcome, evaluate
from contextsafe.models import (
    FAILURE_REASONS,
    Checkpoint,
    ConceptKind,
    DivergenceStatus,
    EvidenceState,
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

EVIDENCE_FAULTS: dict[str, str] = {"F-023": "A-032", "F-025": "A-034"}
"""The two faults the divergence slice detects; each has its own test below."""


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _outcomes(document: dict[str, Any]) -> tuple[Outcome, ...]:
    bundle = parse_bundle(document["case"], document["observations"], document["rules"])
    return evaluate(bundle)


def _by_rule(outcomes: tuple[Outcome, ...], rule_id: str) -> Outcome:
    return next(item for item in outcomes if item.rule_id == rule_id)


ALL_FAULT_FILES = sorted(FAULTS.glob("F-*.json"))
FAULT_FILES = [path for path in ALL_FAULT_FILES if path.stem in EXPECTED_DETECTION]
EVIDENCE_FAULT_FILES = [
    path for path in ALL_FAULT_FILES if path.stem in EVIDENCE_FAULTS
]
CLEAN_FILES = sorted((FAULTS / "clean").glob("*.json"))


def test_the_library_holds_exactly_the_faults_the_tables_expect() -> None:
    """The denominator: nine files, nine rows, and nothing unaccounted for."""

    assert [path.stem for path in ALL_FAULT_FILES] == sorted(
        {*EXPECTED_DETECTION, *EVIDENCE_FAULTS}
    )
    assert len(FAULT_FILES) == 7
    assert len(EVIDENCE_FAULT_FILES) == 2
    assert not set(EXPECTED_DETECTION) & set(EVIDENCE_FAULTS)


def test_every_fault_file_names_the_assertion_the_table_names() -> None:
    expected = {
        **{fault: row[0] for fault, row in EXPECTED_DETECTION.items()},
        **EVIDENCE_FAULTS,
    }
    for path in ALL_FAULT_FILES:
        document = _load(path)
        assert document["fault"] == path.stem
        assert document["assertion"] == expected[path.stem]
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
    for path in (*ALL_FAULT_FILES, *CLEAN_FILES):
        validator.validate(_load(path)["rules"])


def test_faults_against_a_variant_case_have_a_clean_counterpart() -> None:
    """A variant without its clean form could hide a rule that never passes."""

    clean_cases = {path.stem for path in CLEAN_FILES}
    for path in ALL_FAULT_FILES:
        case_id = _load(path)["case"]["case_id"]
        assert case_id == "CTP-I01" or case_id in clean_cases


def _name_divergence(document: dict[str, Any]) -> ConceptDivergence:
    bundle = parse_bundle(document["case"], document["observations"], document["rules"])
    return next(
        item
        for item in compute_divergence(bundle).concepts
        if item.concept is ConceptKind.NAME_TO_USE
    )


def test_f023_an_omitted_checkpoint_can_never_be_reported_as_pass() -> None:
    """F-023, A-032: no evidence at the laboratory return, so nothing passes there.

    Both rules that read the missing boundary are indeterminate with
    ``missing_evidence``; the rule at the observed boundary still passes, so
    the fixture shows that it is the omission and not the case that turned
    them. The divergence section marks the boundary unobserved and says
    nothing about it: not agreed, not diverged, not blamed.
    """

    document = _load(FAULTS / "F-023.json")
    outcomes = _outcomes(document)
    assert _by_rule(outcomes, "A-I01").status is OutcomeStatus.PASSED
    for rule_id in ("A-I02", "A-I03"):
        outcome = _by_rule(outcomes, rule_id)
        assert outcome.status is OutcomeStatus.INDETERMINATE
        assert outcome.reason is OutcomeReason.MISSING_EVIDENCE
        assert outcome.status is not OutcomeStatus.PASSED
        assert outcome.observed_sha256s == ()
    entry = _name_divergence(document)
    lis = next(s for s in entry.checkpoints if s.checkpoint is Checkpoint.LIS_RETURN)
    assert lis.state is EvidenceState.UNOBSERVED
    assert lis.value_sha256s == ()
    assert entry.from_expected.status is DivergenceStatus.AGREED_WHERE_OBSERVED
    assert entry.from_expected.at is None
    assert Checkpoint.LIS_RETURN not in (
        entry.from_previous.after,
        entry.from_previous.at,
    )
    bundle = parse_bundle(document["case"], document["observations"], document["rules"])
    receipt = build_receipt(bundle, outcomes)
    assert receipt["summary"]["pass"] == 1
    assert receipt["summary"]["indeterminate"] == 2


def test_f023_would_pass_if_the_omitted_checkpoint_were_observed() -> None:
    """The omission is what turned the outcomes, not the rules."""

    document = _load(FAULTS / "F-023.json")
    restored = json.loads(json.dumps(document["observations"]["observations"][0]))
    restored["observation_id"] = "OBS-I01-NTU-LIS"
    restored["checkpoint"] = "lis_return"
    document["observations"]["observations"].append(restored)
    assert all(item.status is OutcomeStatus.PASSED for item in _outcomes(document))


def test_f025_a_divergence_is_never_inferred_across_an_unobserved_boundary() -> None:
    """F-025, A-034: the EHR was never observed, so the EHR is never named.

    The value is faithful at registration and changed at the interface. The
    divergence is located at the interface, between registration and the
    interface, and every field that can name a checkpoint avoids the EHR.
    """

    document = _load(FAULTS / "F-025.json")
    entry = _name_divergence(document)
    ehr = next(s for s in entry.checkpoints if s.checkpoint is Checkpoint.EHR)
    assert ehr.state is EvidenceState.UNOBSERVED
    assert entry.from_expected.status is DivergenceStatus.DIVERGED
    assert entry.from_expected.at is Checkpoint.INTERFACE
    assert entry.from_previous.status is DivergenceStatus.DIVERGED
    assert entry.from_previous.after is Checkpoint.REGISTRATION
    assert entry.from_previous.at is Checkpoint.INTERFACE
    named = {entry.from_expected.at, entry.from_previous.after, entry.from_previous.at}
    assert Checkpoint.EHR not in named
    rendered = json.dumps(entry.to_dict())
    assert '"at": "ehr"' not in rendered
    assert '"after": "ehr"' not in rendered
    outcomes = _outcomes(document)
    assert _by_rule(outcomes, "A-I01").status is OutcomeStatus.PASSED
    changed = _by_rule(outcomes, "A-I02")
    assert changed.status is OutcomeStatus.FAIL
    assert changed.reason is OutcomeReason.VALUE_CHANGED_ACROSS_CHECKPOINTS


def test_f025_observing_the_gap_faithfully_moves_nothing_but_the_near_side() -> None:
    """Filling the EHR with the faithful value leaves the location unchanged."""

    document = _load(FAULTS / "F-025.json")
    filled = json.loads(json.dumps(document["observations"]["observations"][0]))
    filled["observation_id"] = "OBS-I01-NTU-EHR"
    filled["checkpoint"] = "ehr"
    document["observations"]["observations"].append(filled)
    entry = _name_divergence(document)
    assert entry.from_expected.at is Checkpoint.INTERFACE
    assert entry.from_previous.after is Checkpoint.EHR
    assert entry.from_previous.at is Checkpoint.INTERFACE


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
    for path in (*ALL_FAULT_FILES, *CLEAN_FILES):
        document = _load(path)
        identifier = document["case"]["synthetic_identifier"]
        assert identifier["system"] == "urn:contextsafe:synthetic"
        assert identifier["value"] == f"CSYN-{document['case']['case_id']}"
        name = document["case"]["concepts"]["name_to_use"]["value"]
        assert name is None or name.startswith("CSYN-")
