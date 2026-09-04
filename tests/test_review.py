"""The append-only review state machine (B-032, P0-10, R-05).

Four things are pinned here. The state machine is data, so every pair the
transition table does not contain is enumerated and required to fail as
``illegal_transition``, and every pair it does contain is required to land
where the table says. No free-text field exists: every string field refuses a
sentence, a name, a canary, and a direct identifier, and the rejection never
echoes the value. Signers are declared, not verified: the only writable
``signature_status`` is ``not_verified``, and an accepted residual risk needs
exactly the two mandated roles from distinct organizations. And the log is
append-only: every line re-hashes on every read, a single changed byte
anywhere in the file is refused, and no command ever rewrites a line.
"""

import copy
import itertools
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

import contextsafe.review as review_module
from contextsafe.canonical import canonical_json, sha256_json
from contextsafe.errors import ContextSafeError
from contextsafe.review import (
    DECISION_RULES,
    EMPTY_LOG_STATE,
    GENESIS_SHA256,
    SIGNATURE_STATUS,
    TRANSITIONS,
    Decision,
    Disposition,
    FindingState,
    OutcomeKey,
    ReviewLogState,
    Severity,
    SeverityRule,
    SignerRole,
    append_review_event,
    apply_event,
    derive_review_state,
    parse_receipt_findings,
    parse_review_event,
    replay_log,
)

EventBuilder = Callable[..., dict[str, Any]]

FINDING_OUTCOME: dict[str, str] = {
    "rule_id": "A-I05",
    "case_id": "CTP-I01",
    "checkpoint": "ehr",
    "concept": "pronouns",
}
CHAIR_SIGNER: dict[str, str] = {
    "role": "contextsafe_clinical_safety_chair",
    "organization_id": "ORG-CONTEXTSAFE-TEST",
    "signature_status": "not_verified",
}
CUSTOMER_SIGNER: dict[str, str] = {
    "role": "customer_clinical_owner",
    "organization_id": "ORG-CUSTOMER-TEST",
    "signature_status": "not_verified",
}
"""Restated here rather than imported from ``conftest``: the values the
``review_event`` fixture builds are pinned independently of it."""

_WALKS = itertools.count()

PATH_TO: dict[Disposition, tuple[Decision, ...]] = {
    Disposition.UNREVIEWED: (),
    Disposition.CONFIRMED: (Decision.CONFIRMED,),
    Disposition.OWNED: (Decision.CONFIRMED, Decision.OWNER_ASSIGNED),
    Disposition.REMEDIATED: (
        Decision.CONFIRMED,
        Decision.OWNER_ASSIGNED,
        Decision.REMEDIATED,
    ),
    Disposition.ACCEPTED_RESIDUAL_RISK: (
        Decision.CONFIRMED,
        Decision.OWNER_ASSIGNED,
        Decision.ACCEPTED_RESIDUAL_RISK,
    ),
    Disposition.REJECTED: (Decision.REJECTED,),
    Disposition.WITHDRAWN: (Decision.CONFIRMED, Decision.WITHDRAWN),
}
"""One legal path into every disposition, so each can be the starting state."""

ILLEGAL_PAIRS = [
    (state, decision)
    for state in Disposition
    for decision in Decision
    if decision not in TRANSITIONS[state]
]
LEGAL_PAIRS = [
    (state, decision, target)
    for state in Disposition
    for decision, target in TRANSITIONS[state].items()
]


def _append(
    log: Path,
    receipt: dict[str, Any],
    build: EventBuilder,
    decisions: tuple[Decision, ...],
) -> ReviewLogState:
    state = EMPTY_LOG_STATE
    for decision in decisions:
        state = append_review_event(log, build(decision.value), receipt)
    return state


def _finding(state: ReviewLogState) -> FindingState:
    return state.findings[OutcomeKey(**FINDING_OUTCOME)]


def _assert_code(
    call: Callable[[], object], code: str, *, path: str | None = None
) -> ContextSafeError:
    with pytest.raises(ContextSafeError) as raised:
        call()
    assert raised.value.code == code
    if path is not None:
        assert raised.value.path == path
    return raised.value


# --- the state machine is data ------------------------------------------------


def test_the_transition_table_covers_every_disposition_and_every_decision() -> None:
    assert set(TRANSITIONS) == set(Disposition)
    assert {decision for moves in TRANSITIONS.values() for decision in moves} == set(
        Decision
    )
    assert set(DECISION_RULES) == set(Decision)
    for state, path in PATH_TO.items():
        current = Disposition.UNREVIEWED
        for decision in path:
            current = TRANSITIONS[current][decision]
        assert current is state


def test_terminal_dispositions_have_no_exit() -> None:
    """Rejected, withdrawn, and remediated stay put; nothing quietly reopens them."""

    for state in (Disposition.REJECTED, Disposition.WITHDRAWN, Disposition.REMEDIATED):
        assert TRANSITIONS[state] == {}


def test_an_accepted_residual_risk_needs_the_two_mandated_roles() -> None:
    rule = DECISION_RULES[Decision.ACCEPTED_RESIDUAL_RISK]
    assert rule.required_signer_roles == frozenset(
        {
            SignerRole.CUSTOMER_CLINICAL_OWNER,
            SignerRole.CONTEXTSAFE_CLINICAL_SAFETY_CHAIR,
        }
    )
    assert rule.distinct_organizations is True
    assert rule.severity is SeverityRule.REQUIRED_UNCHANGED
    assert all(
        not rule.required_signer_roles
        for decision, rule in DECISION_RULES.items()
        if decision is not Decision.ACCEPTED_RESIDUAL_RISK
    )


@pytest.mark.parametrize(
    ("state", "decision"),
    ILLEGAL_PAIRS,
    ids=[f"{state.value}-{decision.value}" for state, decision in ILLEGAL_PAIRS],
)
def test_every_illegal_transition_is_refused_and_nothing_is_appended(
    tmp_path: Path,
    finding_receipt: dict[str, Any],
    review_event: EventBuilder,
    state: Disposition,
    decision: Decision,
) -> None:
    log = tmp_path / "review.jsonl"
    before = _append(log, finding_receipt, review_event, PATH_TO[state])
    size = log.stat().st_size if log.exists() else 0
    event = review_event(decision.value)
    if decision is Decision.SEVERITY_CHANGED:
        event["severity"] = "cs4_low"
    _assert_code(
        lambda: append_review_event(log, event, finding_receipt),
        "illegal_transition",
        path="$.decision",
    )
    assert (log.stat().st_size if log.exists() else 0) == size
    assert derive_review_state(log) == before


@pytest.mark.parametrize(
    ("state", "decision", "target"),
    LEGAL_PAIRS,
    ids=[f"{s.value}-{d.value}" for s, d, _ in LEGAL_PAIRS],
)
def test_every_legal_transition_lands_where_the_table_says(
    tmp_path: Path,
    finding_receipt: dict[str, Any],
    review_event: EventBuilder,
    state: Disposition,
    decision: Decision,
    target: Disposition,
) -> None:
    log = tmp_path / "review.jsonl"
    _append(log, finding_receipt, review_event, PATH_TO[state])
    after = append_review_event(log, review_event(decision.value), finding_receipt)
    finding = _finding(after)
    assert finding.disposition is target
    assert finding.event_count == len(PATH_TO[state]) + 1
    assert after.event_count == finding.event_count


def test_severity_and_owner_survive_events_that_do_not_carry_them(
    tmp_path: Path, finding_receipt: dict[str, Any], review_event: EventBuilder
) -> None:
    log = tmp_path / "review.jsonl"
    state = _append(
        log,
        finding_receipt,
        review_event,
        PATH_TO[Disposition.REMEDIATED],
    )
    finding = _finding(state)
    assert finding.severity is Severity.CS2_HIGH
    assert finding.owner is not None
    assert finding.owner.token_sha256 == "a" * 64
    assert finding.last_event_sha256 == sha256_json(
        parse_review_event(review_event("remediated")).to_dict()
    )


def test_a_severity_change_must_change_the_severity(
    tmp_path: Path, finding_receipt: dict[str, Any], review_event: EventBuilder
) -> None:
    log = tmp_path / "review.jsonl"
    _append(log, finding_receipt, review_event, PATH_TO[Disposition.CONFIRMED])
    _assert_code(
        lambda: append_review_event(
            log, review_event("severity_changed", severity="cs2_high"), finding_receipt
        ),
        "severity_unchanged",
        path="$.severity",
    )


def test_an_accepted_residual_risk_cannot_change_the_severity(
    tmp_path: Path, finding_receipt: dict[str, Any], review_event: EventBuilder
) -> None:
    """The chair confirms the severity; acceptance is not a second rubric."""

    log = tmp_path / "review.jsonl"
    _append(log, finding_receipt, review_event, PATH_TO[Disposition.OWNED])
    _assert_code(
        lambda: append_review_event(
            log,
            review_event("accepted_residual_risk", severity="cs4_low"),
            finding_receipt,
        ),
        "severity_changed_by_acceptance",
        path="$.severity",
    )


@pytest.mark.parametrize(
    ("decision", "field", "value", "code"),
    [
        ("confirmed", "severity", None, "severity_required"),
        ("rejected", "severity", "cs4_low", "severity_forbidden"),
        ("owner_assigned", "severity", "cs4_low", "severity_forbidden"),
        ("remediated", "severity", "cs1_critical", "severity_forbidden"),
        ("withdrawn", "severity", "cs1_critical", "severity_forbidden"),
        ("accepted_residual_risk", "severity", None, "severity_required"),
        ("severity_changed", "severity", None, "severity_required"),
        ("owner_assigned", "owner", None, "owner_required"),
        (
            "confirmed",
            "owner",
            {"role": "customer_clinical_owner", "token_sha256": "b" * 64},
            "owner_forbidden",
        ),
        (
            "accepted_residual_risk",
            "owner",
            {"role": "customer_clinical_owner", "token_sha256": "b" * 64},
            "owner_forbidden",
        ),
    ],
)
def test_each_decision_carries_exactly_what_its_rule_says(
    review_event: EventBuilder, decision: str, field: str, value: object, code: str
) -> None:
    _assert_code(
        lambda: parse_review_event(review_event(decision, **{field: value})),
        code,
        path=f"$.{field}",
    )


def test_apply_event_refuses_an_event_for_another_outcome(
    review_event: EventBuilder,
) -> None:
    other = FindingState(outcome=OutcomeKey("A-I01", "CTP-I01", "ehr", "pronouns"))
    event = parse_review_event(review_event("confirmed"))
    _assert_code(
        lambda: apply_event(other, event, "0" * 64),
        "outcome_mismatch",
        path="$.outcome",
    )


# --- signers are declared, not verified --------------------------------------


@pytest.mark.parametrize("value", ["verified", "signed", "valid", "not_signed", ""])
def test_no_other_signature_status_can_be_written(
    review_event: EventBuilder, value: str
) -> None:
    """A later signing layer may not relabel these events in place."""

    _assert_code(
        lambda: parse_review_event(review_event("confirmed", signature_status=value)),
        "signature_status_not_declarable",
        path="$.signature_status",
    )
    signer = {**CHAIR_SIGNER, "signature_status": value}
    _assert_code(
        lambda: parse_review_event(review_event("confirmed", signers=[signer])),
        "signature_status_not_declarable",
        path="$.signers[0].signature_status",
    )


@pytest.mark.parametrize(
    ("signers", "code"),
    [
        ([CUSTOMER_SIGNER], "signer_threshold_unmet"),
        ([CHAIR_SIGNER], "signer_threshold_unmet"),
        (
            [CUSTOMER_SIGNER, {**CHAIR_SIGNER, "role": "laboratory_reviewer"}],
            "signer_threshold_unmet",
        ),
        (
            [
                CUSTOMER_SIGNER,
                CHAIR_SIGNER,
                {**CHAIR_SIGNER, "role": "customer_release_owner"},
            ],
            "signer_threshold_unmet",
        ),
        (
            [CUSTOMER_SIGNER, {**CHAIR_SIGNER, "organization_id": "ORG-CUSTOMER-TEST"}],
            "signer_organizations_not_distinct",
        ),
        (
            [CUSTOMER_SIGNER, {**CUSTOMER_SIGNER, "organization_id": "ORG-OTHER"}],
            "duplicate_signer_role",
        ),
    ],
)
def test_an_accepted_residual_risk_without_both_mandated_signers_is_refused(
    review_event: EventBuilder, signers: list[dict[str, str]], code: str
) -> None:
    """Neither signature substitutes for the other, and one organization cannot hold both."""

    _assert_code(
        lambda: parse_review_event(
            review_event("accepted_residual_risk", signers=signers)
        ),
        code,
        path="$.signers",
    )


@pytest.mark.parametrize("count", [0, 5])
def test_signer_count_is_bounded(review_event: EventBuilder, count: int) -> None:
    roles = [item.value for item in SignerRole][:count]
    signers = [{**CHAIR_SIGNER, "role": role} for role in roles]
    _assert_code(
        lambda: parse_review_event(review_event("confirmed", signers=signers)),
        "signer_count_out_of_bounds",
        path="$.signers",
    )


def test_every_signer_and_the_event_say_not_verified_on_the_way_out(
    review_event: EventBuilder,
) -> None:
    event = parse_review_event(review_event("accepted_residual_risk"))
    document = event.to_dict()
    assert document["signature_status"] == SIGNATURE_STATUS == "not_verified"
    signers = document["signers"]
    assert isinstance(signers, list)
    assert all(
        isinstance(item, dict) and item["signature_status"] == "not_verified"
        for item in signers
    )


# --- no free-text field exists -----------------------------------------------


def test_the_event_shape_has_no_string_field_that_admits_prose() -> None:
    """Every string in an event is an enum member, a hash, or a grammar token."""

    schema = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "schemas"
            / "contextsafe-review-event-v1.schema.json"
        ).read_text(encoding="utf-8")
    )

    def unbounded(node: Any) -> list[str]:
        found: list[str] = []
        if isinstance(node, dict):
            if node.get("type") == "string" and not (
                "pattern" in node or "allOf" in node or "const" in node
            ):
                found.append(json.dumps(node))
            for value in node.values():
                found.extend(unbounded(value))
        elif isinstance(node, list):
            for value in node:
                found.extend(unbounded(value))
        return found

    assert unbounded(schema) == []


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("external_reference", "reviewed by Jordan Rivera", "invalid_format"),
        ("external_reference", "1987-03-14", "invalid_format"),
        ("external_reference", "https://tickets.invalid/1", "invalid_format"),
        ("external_reference", "nurse@example.invalid", "invalid_format"),
        ("external_reference", "MRN-1234567", "invalid_format"),
        ("external_reference", "realpatientcanary", "phi_canary_detected"),
        ("external_reference", "ticket.REAL-PATIENT-CANARY", "phi_canary_detected"),
        ("external_reference", "", "invalid_string"),
        ("external_reference", 7, "invalid_string"),
        ("rationale_code", "the evidence looked fine to me", "invalid_enum"),
        ("rationale_code", "", "invalid_string"),
        ("decision", "approved", "invalid_enum"),
        ("severity", "critical", "invalid_enum"),
        ("severity", "CS-1", "invalid_enum"),
        (
            "schema_version",
            "contextsafe.review-event/2.0.0",
            "unsupported_schema_version",
        ),
    ],
)
def test_every_string_field_refuses_prose_names_and_identifiers(
    review_event: EventBuilder, field: str, value: object, code: str
) -> None:
    event = review_event("confirmed")
    event[field] = value
    error = _assert_code(lambda: parse_review_event(event), code, path=f"$.{field}")
    if isinstance(value, str) and value:
        assert value not in json.dumps(error.to_dict())


@pytest.mark.parametrize(
    ("organization_id", "code"),
    [
        ("org-customer", "invalid_format"),
        ("ORG-2026-08-27", "invalid_format"),
        ("ORG-1234567", "invalid_format"),
        ("Jordan Rivera", "invalid_format"),
        ("REALPATIENTCANARY", "phi_canary_detected"),
        ("", "invalid_string"),
    ],
)
def test_a_signer_organization_is_a_label_under_the_system_grammar(
    review_event: EventBuilder, organization_id: str, code: str
) -> None:
    signer = {**CHAIR_SIGNER, "organization_id": organization_id}
    error = _assert_code(
        lambda: parse_review_event(review_event("confirmed", signers=[signer])),
        code,
        path="$.signers[0].organization_id",
    )
    if organization_id:
        assert organization_id not in json.dumps(error.to_dict())


@pytest.mark.parametrize(
    ("owner", "code", "path"),
    [
        (
            {"role": "customer_technical_owner", "token_sha256": "Jordan Rivera"},
            "invalid_format",
            "$.owner.token_sha256",
        ),
        (
            {"role": "customer_technical_owner", "token_sha256": "A" * 64},
            "invalid_format",
            "$.owner.token_sha256",
        ),
        (
            {"role": "customer_technical_owner", "token_sha256": "a" * 63},
            "invalid_format",
            "$.owner.token_sha256",
        ),
        (
            {"role": "clinical_safety_chair", "token_sha256": "a" * 64},
            "invalid_enum",
            "$.owner.role",
        ),
        (
            {"role": "customer_technical_owner", "token_sha256": "a" * 64, "name": "x"},
            "unknown_field",
            "$.owner",
        ),
        ("customer_technical_owner", "invalid_type", "$.owner"),
    ],
)
def test_an_owner_is_a_role_and_a_hash_and_never_a_name(
    review_event: EventBuilder, owner: object, code: str, path: str
) -> None:
    _assert_code(
        lambda: parse_review_event(review_event("owner_assigned", owner=owner)),
        code,
        path=path,
    )


@pytest.mark.parametrize(
    "path",
    [
        (),
        ("outcome",),
        ("receipt",),
        ("signers", 0),
    ],
)
def test_unknown_fields_fail_closed_at_every_level(
    review_event: EventBuilder, path: tuple[str | int, ...]
) -> None:
    event = review_event("confirmed")
    target: Any = event
    for key in path:
        target = target[key]
    target["note"] = "reviewer comment"
    error = _assert_code(lambda: parse_review_event(event), "unknown_field")
    assert "reviewer comment" not in json.dumps(error.to_dict())


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("rule_id", "a-i05", "invalid_format"),
        ("rule_id", "A-I05 pronouns", "invalid_format"),
        ("case_id", "CTP-I01-JORDAN-RIVERA-1987", "invalid_string"),
        ("case_id", "CTP-JORDAN RIVERA", "invalid_format"),
        ("checkpoint", "laboratory", "invalid_enum"),
        ("concept", "sex", "invalid_enum"),
        ("concept", "gender", "invalid_enum"),
    ],
)
def test_the_outcome_key_is_bounded_and_the_concepts_stay_closed(
    review_event: EventBuilder, field: str, value: str, code: str
) -> None:
    outcome = {**FINDING_OUTCOME, field: value}
    _assert_code(
        lambda: parse_review_event(review_event("confirmed", outcome=outcome)),
        code,
        path=f"$.outcome.{field}",
    )


def test_a_missing_field_is_named_and_the_event_is_refused(
    review_event: EventBuilder,
) -> None:
    event = review_event("confirmed")
    del event["rationale_code"]
    _assert_code(
        lambda: parse_review_event(event), "missing_field", path="$.rationale_code"
    )
    _assert_code(lambda: parse_review_event(["confirmed"]), "invalid_type", path="$")


# --- binding to the receipt -------------------------------------------------


def test_parse_receipt_findings_reads_only_hashes_and_finding_outcomes(
    finding_receipt: dict[str, Any],
) -> None:
    findings = parse_receipt_findings(finding_receipt)
    assert findings.binding.payload_sha256 == finding_receipt["payload_sha256"]
    assert findings.findings == frozenset({OutcomeKey(**FINDING_OUTCOME)})


def test_a_passing_outcome_is_not_a_finding_and_cannot_be_reviewed(
    tmp_path: Path, finding_receipt: dict[str, Any], review_event: EventBuilder
) -> None:
    outcome = {**FINDING_OUTCOME, "rule_id": "A-I01", "concept": "gender_identity"}
    _assert_code(
        lambda: append_review_event(
            tmp_path / "review.jsonl",
            review_event("confirmed", outcome=outcome),
            finding_receipt,
        ),
        "outcome_not_a_finding",
        path="$.outcome",
    )
    assert not (tmp_path / "review.jsonl").exists()


def test_an_event_bound_to_another_receipt_is_refused(
    tmp_path: Path, finding_receipt: dict[str, Any], review_event: EventBuilder
) -> None:
    event = review_event("confirmed")
    event["receipt"]["rule_set_sha256"] = "f" * 64
    _assert_code(
        lambda: append_review_event(tmp_path / "review.jsonl", event, finding_receipt),
        "receipt_binding_mismatch",
        path="$.receipt",
    )


def test_a_receipt_whose_payload_hash_does_not_rehash_is_refused(
    tmp_path: Path, finding_receipt: dict[str, Any], review_event: EventBuilder
) -> None:
    tampered = copy.deepcopy(finding_receipt)
    tampered["payload"]["summary"]["fail"] = 0
    _assert_code(
        lambda: append_review_event(
            tmp_path / "review.jsonl", review_event("confirmed"), tampered
        ),
        "receipt_hash_mismatch",
        path="$.payload_sha256",
    )


@pytest.mark.parametrize(
    ("mutate", "code", "path"),
    [
        (lambda r: r.pop("payload_sha256"), "missing_field", "$.payload_sha256"),
        (
            lambda r: r.update(schema_version="contextsafe.receipt-document/0.2.0"),
            "unsupported_schema_version",
            "$.schema_version",
        ),
        (lambda r: r.update(payload=[]), "invalid_type", "$.payload"),
        (lambda r: r["payload"].pop("hashes"), "invalid_type", "$.payload.hashes"),
        (
            lambda r: r["payload"].update(results={}),
            "invalid_type",
            "$.payload.results",
        ),
        (
            lambda r: r["payload"]["results"][0].pop("status"),
            "missing_field",
            "$.payload.results[0].status",
        ),
        (
            lambda r: r["payload"]["results"][0].update(concept="sex"),
            "invalid_enum",
            "$.payload.results[0].concept",
        ),
    ],
)
def test_a_receipt_outside_the_shape_review_needs_is_refused(
    finding_receipt: dict[str, Any],
    mutate: Callable[[dict[str, Any]], object],
    code: str,
    path: str,
) -> None:
    """Each mutation is applied before re-hashing, so the hash check is not what fails."""

    mutate(finding_receipt)
    if "payload_sha256" in finding_receipt and isinstance(
        finding_receipt["payload"], dict
    ):
        finding_receipt["payload_sha256"] = sha256_json(finding_receipt["payload"])
    _assert_code(lambda: parse_receipt_findings(finding_receipt), code, path=path)


def test_a_log_is_bound_to_one_receipt(
    tmp_path: Path, finding_receipt: dict[str, Any], review_event: EventBuilder
) -> None:
    log = tmp_path / "review.jsonl"
    _append(log, finding_receipt, review_event, PATH_TO[Disposition.CONFIRMED])
    other = copy.deepcopy(finding_receipt)
    other["payload"]["runner_version"] = "9.9.9"
    other["payload_sha256"] = sha256_json(other["payload"])
    event = review_event("owner_assigned")
    event["receipt"]["payload_sha256"] = other["payload_sha256"]
    _assert_code(
        lambda: append_review_event(log, event, other),
        "receipt_binding_mismatch",
        path="$.receipt",
    )
    assert derive_review_state(log).event_count == 1


# --- the log is append-only and re-hashes on every read ----------------------


def test_the_log_chains_every_record_to_the_one_before_it(
    tmp_path: Path, finding_receipt: dict[str, Any], review_event: EventBuilder
) -> None:
    log = tmp_path / "review.jsonl"
    state = _append(log, finding_receipt, review_event, PATH_TO[Disposition.OWNED])
    lines = log.read_bytes().split(b"\n")
    assert lines[-1] == b""
    records = [json.loads(line) for line in lines[:-1]]
    previous = GENESIS_SHA256
    for index, record in enumerate(records):
        assert record["sequence"] == index
        assert record["previous_record_sha256"] == previous
        assert record["event_sha256"] == sha256_json(record["event"])
        assert canonical_json(record).encode() == lines[index]
        previous = sha256_json(record)
    assert state.head_sha256 == previous
    assert derive_review_state(log) == state


def test_nothing_ever_rewrites_an_earlier_line(
    tmp_path: Path, finding_receipt: dict[str, Any], review_event: EventBuilder
) -> None:
    log = tmp_path / "review.jsonl"
    _append(log, finding_receipt, review_event, PATH_TO[Disposition.CONFIRMED])
    first = log.read_bytes()
    _append(log, finding_receipt, review_event, (Decision.OWNER_ASSIGNED,))
    assert log.read_bytes().startswith(first)
    assert log.read_bytes().count(b"\n") == 2


def test_an_empty_log_derives_the_empty_state(tmp_path: Path) -> None:
    log = tmp_path / "review.jsonl"
    log.write_bytes(b"")
    state = derive_review_state(log)
    assert state == EMPTY_LOG_STATE
    document = state.to_dict()
    assert document["receipt"] is None
    assert document["findings"] == []
    assert document["log_head_sha256"] == GENESIS_SHA256


def _valid_log(
    tmp_path: Path, receipt: dict[str, Any], build: EventBuilder
) -> tuple[Path, bytes]:
    log = tmp_path / "review.jsonl"
    _append(log, receipt, build, PATH_TO[Disposition.OWNED])
    return log, log.read_bytes()


@pytest.mark.parametrize(
    ("edit", "code", "path"),
    [
        (
            lambda r: r[0].update(sequence=1),
            "log_sequence_mismatch",
            "$.log[0].sequence",
        ),
        (
            lambda r: r[1].update(previous_record_sha256="0" * 64),
            "log_chain_broken",
            "$.log[1].previous_record_sha256",
        ),
        (
            lambda r: r[1]["event"].update(external_reference="ticket.later"),
            "log_chain_broken",
            "$.log[1].event_sha256",
        ),
        (
            lambda r: r[1]["event"].update(severity="cs1_critical"),
            "severity_forbidden",
            "$.log[1].severity",
        ),
        (
            lambda r: r.append(copy.deepcopy(r[1])),
            "log_sequence_mismatch",
            "$.log[2].sequence",
        ),
        (lambda r: r.reverse(), "log_sequence_mismatch", "$.log[0].sequence"),
        (lambda r: r[0].pop("event_sha256"), "missing_field", "$.log[0].event_sha256"),
        (lambda r: r[0].update(note="edited"), "unknown_field", "$.log[0]"),
    ],
)
def test_a_log_that_does_not_rehash_or_replay_is_refused_whole(
    tmp_path: Path,
    finding_receipt: dict[str, Any],
    review_event: EventBuilder,
    edit: Callable[[list[dict[str, Any]]], object],
    code: str,
    path: str,
) -> None:
    """Editing a line, reordering, or duplicating one is caught at that line."""

    log, raw = _valid_log(tmp_path, finding_receipt, review_event)
    records = [json.loads(line) for line in raw.split(b"\n")[:-1]]
    edit(records)
    log.write_bytes(b"".join(canonical_json(r).encode() + b"\n" for r in records))
    _assert_code(lambda: derive_review_state(log), code, path=path)
    _assert_code(
        lambda: append_review_event(log, review_event("remediated"), finding_receipt),
        code,
    )


def test_a_line_that_is_not_canonical_is_refused_even_when_it_parses(
    tmp_path: Path, finding_receipt: dict[str, Any], review_event: EventBuilder
) -> None:
    """Whitespace, key order, and a boolean where an integer belongs all fail."""

    log, raw = _valid_log(tmp_path, finding_receipt, review_event)
    line, rest = raw.split(b"\n", 1)
    log.write_bytes(line.replace(b'"sequence":0', b'"sequence": 0') + b"\n" + rest)
    _assert_code(lambda: derive_review_state(log), "invalid_log_line", path="$.log[0]")
    log.write_bytes(line.replace(b'"sequence":0', b'"sequence":false') + b"\n" + rest)
    _assert_code(lambda: derive_review_state(log), "invalid_log_line", path="$.log[0]")
    log.write_bytes(raw[:-1])
    _assert_code(lambda: derive_review_state(log), "invalid_log_line", path="$.log")


def _raw_log(build: EventBuilder) -> bytes:
    """The bytes the runtime would write for one legal walk, built directly."""

    raw = b""
    previous = GENESIS_SHA256
    for sequence, decision in enumerate(PATH_TO[Disposition.OWNED]):
        event = parse_review_event(build(decision.value))
        record = review_module.LogRecord(
            sequence=sequence,
            previous_record_sha256=previous,
            event_sha256=sha256_json(event.to_dict()),
            event=event,
        )
        raw += record.line()
        previous = record.sha256()
    return raw


@given(index=st.integers(min_value=0), replacement=st.binary(min_size=1, max_size=1))
@settings(max_examples=200, deadline=None, suppress_health_check=list(HealthCheck))
def test_any_single_changed_byte_anywhere_in_the_log_is_refused(
    review_event: EventBuilder, index: int, replacement: bytes
) -> None:
    """The append-only claim, stated over the whole file rather than a field."""

    raw = _raw_log(review_event)
    assume(index < len(raw))
    assume(raw[index : index + 1] != replacement)
    assert _finding(replay_log(raw)).disposition is Disposition.OWNED
    with pytest.raises(ContextSafeError):
        replay_log(raw[:index] + replacement + raw[index + 1 :])


@given(data=st.data())
@settings(max_examples=60, deadline=None, suppress_health_check=list(HealthCheck))
def test_any_legal_walk_replays_to_the_same_state_bytes(
    tmp_path: Path,
    finding_receipt: dict[str, Any],
    review_event: EventBuilder,
    data: st.DataObject,
) -> None:
    """Replaying a log is a pure function of its bytes: no clock, no order effect."""

    log = tmp_path / f"walk-{next(_WALKS)}.jsonl"
    current = Disposition.UNREVIEWED
    severity: str | None = None
    state = EMPTY_LOG_STATE
    for _ in range(data.draw(st.integers(0, 6))):
        moves = sorted(TRANSITIONS[current], key=lambda item: item.value)
        if not moves:
            break
        decision = data.draw(st.sampled_from(moves))
        event = review_event(decision.value)
        if decision is Decision.SEVERITY_CHANGED:
            event["severity"] = data.draw(
                st.sampled_from(
                    [item.value for item in Severity if item.value != severity]
                )
            )
        if decision is Decision.ACCEPTED_RESIDUAL_RISK:
            event["severity"] = severity
        state = append_review_event(log, event, finding_receipt)
        current = TRANSITIONS[current][decision]
        severity = event["severity"] or severity
    if state.event_count:
        replayed = derive_review_state(log)
        assert replayed == state
        assert _finding(replayed).disposition is current
        assert canonical_json(replayed.to_dict()) == canonical_json(state.to_dict())


# --- the file boundary --------------------------------------------------------


def test_a_missing_log_cannot_be_listed(tmp_path: Path) -> None:
    _assert_code(lambda: derive_review_state(tmp_path / "absent.jsonl"), "log_io_error")


def test_a_symbolic_link_is_never_followed(
    tmp_path: Path, finding_receipt: dict[str, Any], review_event: EventBuilder
) -> None:
    target = tmp_path / "target.jsonl"
    target.write_bytes(b"")
    link = tmp_path / "review.jsonl"
    link.symlink_to(target)
    _assert_code(lambda: derive_review_state(link), "log_io_error")
    _assert_code(
        lambda: append_review_event(link, review_event("confirmed"), finding_receipt),
        "log_io_error",
    )
    assert target.read_bytes() == b""


def test_a_directory_is_not_a_log(
    tmp_path: Path, finding_receipt: dict[str, Any], review_event: EventBuilder
) -> None:
    _assert_code(lambda: derive_review_state(tmp_path), "input_path_unsafe")
    _assert_code(
        lambda: append_review_event(
            tmp_path, review_event("confirmed"), finding_receipt
        ),
        "log_io_error",
    )


def test_platforms_without_no_follow_open_fail_closed(
    tmp_path: Path,
    finding_receipt: dict[str, Any],
    review_event: EventBuilder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(review_module, "_NOFOLLOW", 0)
    log = tmp_path / "review.jsonl"
    _assert_code(
        lambda: append_review_event(log, review_event("confirmed"), finding_receipt),
        "input_path_unsupported",
    )
    assert not log.exists()
    _assert_code(lambda: derive_review_state(log), "input_path_unsupported")


def test_the_log_has_a_published_size_limit(
    tmp_path: Path,
    finding_receipt: dict[str, Any],
    review_event: EventBuilder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log = tmp_path / "review.jsonl"
    _append(log, finding_receipt, review_event, PATH_TO[Disposition.CONFIRMED])
    size = log.stat().st_size
    monkeypatch.setattr(review_module, "MAX_LOG_BYTES", size + 10)
    _assert_code(
        lambda: append_review_event(
            log, review_event("owner_assigned"), finding_receipt
        ),
        "log_full",
    )
    assert log.stat().st_size == size
    monkeypatch.setattr(review_module, "MAX_LOG_BYTES", size - 1)
    _assert_code(lambda: derive_review_state(log), "input_too_large")


def test_a_log_that_grows_during_the_read_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / "review.jsonl"
    log.write_bytes(b"x" * 20)
    descriptor = os.open(log, os.O_RDONLY)
    try:
        monkeypatch.setattr(review_module, "MAX_LOG_BYTES", 10)
        _assert_code(lambda: review_module._read_log(descriptor), "input_too_large")
    finally:
        os.close(descriptor)


def test_a_log_that_changes_between_read_and_append_is_left_alone(
    tmp_path: Path,
    finding_receipt: dict[str, Any],
    review_event: EventBuilder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log = tmp_path / "review.jsonl"
    _append(log, finding_receipt, review_event, PATH_TO[Disposition.CONFIRMED])
    original = review_module._read_log

    def read_then_grow(descriptor: int) -> bytes:
        raw = original(descriptor)
        os.write(descriptor, b"\n")
        return raw

    monkeypatch.setattr(review_module, "_read_log", read_then_grow)
    _assert_code(
        lambda: append_review_event(
            log, review_event("owner_assigned"), finding_receipt
        ),
        "log_concurrent_append",
    )
    assert log.read_bytes().count(b"sequence") == 1


def test_io_failures_are_reported_as_log_io_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = os.open(tmp_path, os.O_RDONLY)
    try:
        _assert_code(lambda: review_module._read_log(directory), "log_io_error")
        directory_size = os.fstat(directory).st_size
        _assert_code(
            lambda: review_module._append_line(
                directory, b"x\n", expected_size=directory_size
            ),
            "log_io_error",
        )
    finally:
        os.close(directory)
    _assert_code(
        lambda: review_module._append_line(directory, b"x\n", expected_size=0),
        "log_io_error",
    )
    log = tmp_path / "short.jsonl"
    log.write_bytes(b"")
    descriptor = os.open(log, os.O_RDWR | os.O_APPEND)
    try:
        monkeypatch.setattr(os, "write", lambda _fd, _data: 0)
        _assert_code(
            lambda: review_module._append_line(descriptor, b"x\n", expected_size=0),
            "log_io_error",
        )
    finally:
        os.close(descriptor)


# --- value minimization -------------------------------------------------------


def test_the_state_and_the_log_carry_no_clock_and_no_name(
    tmp_path: Path, finding_receipt: dict[str, Any], review_event: EventBuilder
) -> None:
    log = tmp_path / "review.jsonl"
    state = _append(
        log,
        finding_receipt,
        review_event,
        PATH_TO[Disposition.ACCEPTED_RESIDUAL_RISK],
    )
    document = canonical_json(state.to_dict())
    for key in ("timestamp", "generated_at", "signed_at", "name", "note", "message"):
        assert f'"{key}"' not in document
        assert f'"{key}"' not in log.read_text(encoding="utf-8")
    assert "ze/hir" not in document
    assert "ze/hir" not in log.read_text(encoding="utf-8")
    assert str(tmp_path) not in log.read_text(encoding="utf-8")


def test_the_same_events_produce_the_same_bytes_in_another_directory(
    tmp_path: Path, finding_receipt: dict[str, Any], review_event: EventBuilder
) -> None:
    first = tmp_path / "one" / "review.jsonl"
    second = tmp_path / "a-much-longer-directory-name" / "review.jsonl"
    first.parent.mkdir()
    second.parent.mkdir()
    path = PATH_TO[Disposition.REMEDIATED]
    state_one = _append(first, finding_receipt, review_event, path)
    state_two = _append(second, finding_receipt, review_event, path)
    assert first.read_bytes() == second.read_bytes()
    assert canonical_json(state_one.to_dict()) == canonical_json(state_two.to_dict())


# --- belt and braces ----------------------------------------------------------


def test_a_detector_firing_on_a_grammar_admitted_token_still_refuses(
    review_event: EventBuilder, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR 0006: the grammar makes a direct identifier unwritable in these
    fields, so the scan's non-canary branch is unreachable today. It is the
    second layer, not decoration: if a detector ever fires on a value the
    grammar admitted, the event is refused rather than passed."""

    monkeypatch.setattr(
        review_module,
        "provenance_hits",
        lambda _value: ("direct-identifier:telephone",),
    )
    _assert_code(
        lambda: parse_review_event(
            review_event("confirmed", external_reference="ticket.synthetic-a")
        ),
        "direct_identifier_detected",
        path="$.external_reference",
    )


def test_a_log_whose_lines_name_two_receipts_is_refused_on_replay(
    review_event: EventBuilder,
) -> None:
    """The append path checks the binding first; replay must hold it too."""

    first = parse_review_event(review_event("confirmed"))
    second_value = review_event("owner_assigned")
    second_value["receipt"]["rule_set_sha256"] = "f" * 64
    second = parse_review_event(second_value)
    records: list[review_module.LogRecord] = []
    previous = GENESIS_SHA256
    for sequence, event in enumerate((first, second)):
        record = review_module.LogRecord(
            sequence=sequence,
            previous_record_sha256=previous,
            event_sha256=sha256_json(event.to_dict()),
            event=event,
        )
        records.append(record)
        previous = record.sha256()
    raw = b"".join(record.line() for record in records)
    _assert_code(
        lambda: replay_log(raw), "receipt_binding_mismatch", path="$.log[1].receipt"
    )
