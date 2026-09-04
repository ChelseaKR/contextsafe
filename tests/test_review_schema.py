"""Published review contracts against the runtime (B-032).

`schemas/contextsafe-review-event-v1.schema.json` is the pre-signature shape
of the review schema `docs/04-ARCHITECTURE.md` section 8 lists, and
`schemas/contextsafe-review-state-v1.schema.json` is what `finding list`
derives. These are the schema/runtime agreement gates for both, in the form
`tests/test_receipt_schema.py` uses for the receipt: every published event
shape validates, every log record validates against the record subschema,
the derived state validates, the closed enums equal the runtime types, the
grammars are the strings the code enforces, an added field fails closed at
every level, and the unsigned constants cannot be relabelled.
"""

import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from contextsafe.contract_validation import (
    PROVENANCE_LABEL_GRAMMAR,
    PROVENANCE_SYSTEM_GRAMMAR,
)
from contextsafe.models import Checkpoint, ConceptKind
from contextsafe.review import (
    EMPTY_LOG_STATE,
    REVIEW_EVENT_SCHEMA_VERSION,
    REVIEW_LOG_SCHEMA_VERSION,
    REVIEW_STATE_SCHEMA_VERSION,
    STATE_LIMITATIONS,
    Decision,
    Disposition,
    OwnerRole,
    RationaleCode,
    Severity,
    SignerRole,
    append_review_event,
    parse_review_event,
)

ROOT = Path(__file__).resolve().parents[1]
EVENT_SCHEMA_PATH = ROOT / "schemas" / "contextsafe-review-event-v1.schema.json"
STATE_SCHEMA_PATH = ROOT / "schemas" / "contextsafe-review-state-v1.schema.json"

EventBuilder = Callable[..., dict[str, Any]]


def _schema(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _event_validator() -> Draft202012Validator:
    return Draft202012Validator(_schema(EVENT_SCHEMA_PATH))


def _record_validator() -> Draft202012Validator:
    """The log-record subschema, with its ``{"$ref": "#"}`` event inlined.

    ``#`` names the root of the resource it appears in, so lifting
    ``log_record`` to be a root of its own would make the event reference
    point back at the record. Inlining the event schema keeps the reference
    pointing at what the published file means.
    """

    schema = _schema(EVENT_SCHEMA_PATH)
    record = copy.deepcopy(schema["$defs"]["log_record"])
    assert record["properties"]["event"] == {"$ref": "#"}
    record["properties"]["event"] = {
        key: value
        for key, value in schema.items()
        if key not in {"$id", "$schema", "$defs"}
    }
    return Draft202012Validator(
        {"$schema": schema["$schema"], **record, "$defs": schema["$defs"]}
    )


def _state_validator() -> Draft202012Validator:
    return Draft202012Validator(_schema(STATE_SCHEMA_PATH))


def _log_records(log: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in log.read_text(encoding="utf-8").split("\n") if line
    ]


def _walked_log(
    tmp_path: Path, receipt: dict[str, Any], build: EventBuilder
) -> tuple[Path, dict[str, Any]]:
    log = tmp_path / "review.jsonl"
    state: dict[str, Any] = {}
    for decision in ("confirmed", "owner_assigned", "accepted_residual_risk"):
        state = append_review_event(log, build(decision), receipt).to_dict()
    return log, state


def test_both_contracts_are_valid_and_reserved() -> None:
    for path in (EVENT_SCHEMA_PATH, STATE_SCHEMA_PATH):
        schema = _schema(path)
        Draft202012Validator.check_schema(schema)
        assert schema["$id"] == f"https://contextsafe.invalid/schemas/{path.name}"


@pytest.mark.parametrize("decision", [item.value for item in Decision])
def test_every_published_decision_has_a_valid_event_shape(
    review_event: EventBuilder, decision: str
) -> None:
    """Runtime and contract agree on every decision, both ways."""

    event = review_event(decision)
    _event_validator().validate(event)
    assert parse_review_event(event).to_dict() == event


def test_an_optional_external_reference_validates(review_event: EventBuilder) -> None:
    event = review_event("confirmed", external_reference="ticket.synthetic-a")
    _event_validator().validate(event)
    assert parse_review_event(event).external_reference == "ticket.synthetic-a"


def test_every_log_record_validates_against_the_record_subschema(
    tmp_path: Path, finding_receipt: dict[str, Any], review_event: EventBuilder
) -> None:
    log, _state = _walked_log(tmp_path, finding_receipt, review_event)
    validator = _record_validator()
    records = _log_records(log)
    assert len(records) == 3
    for record in records:
        validator.validate(record)
        assert record["schema_version"] == REVIEW_LOG_SCHEMA_VERSION


def test_the_derived_state_validates_against_the_state_contract(
    tmp_path: Path, finding_receipt: dict[str, Any], review_event: EventBuilder
) -> None:
    _log, state = _walked_log(tmp_path, finding_receipt, review_event)
    _state_validator().validate(state)
    assert state["schema_version"] == REVIEW_STATE_SCHEMA_VERSION
    assert tuple(state["limitations"]) == STATE_LIMITATIONS


def test_the_empty_state_validates_too() -> None:
    _state_validator().validate(EMPTY_LOG_STATE.to_dict())


def test_contract_versions_match_the_runtime_constants() -> None:
    event_schema = _schema(EVENT_SCHEMA_PATH)
    assert (
        event_schema["properties"]["schema_version"]["const"]
        == REVIEW_EVENT_SCHEMA_VERSION
    )
    assert (
        event_schema["$defs"]["log_record"]["properties"]["schema_version"]["const"]
        == REVIEW_LOG_SCHEMA_VERSION
    )
    assert (
        _schema(STATE_SCHEMA_PATH)["properties"]["schema_version"]["const"]
        == REVIEW_STATE_SCHEMA_VERSION
    )


def test_contract_enums_equal_the_runtime_closed_sets() -> None:
    event = _schema(EVENT_SCHEMA_PATH)
    state = _schema(STATE_SCHEMA_PATH)
    properties = event["properties"]
    defs = event["$defs"]
    finding = state["$defs"]["finding"]["properties"]

    assert set(properties["decision"]["enum"]) == {item.value for item in Decision}
    assert set(properties["severity"]["oneOf"][1]["enum"]) == {
        item.value for item in Severity
    }
    assert set(properties["rationale_code"]["enum"]) == {
        item.value for item in RationaleCode
    }
    assert set(defs["owner"]["properties"]["role"]["enum"]) == {
        item.value for item in OwnerRole
    }
    assert set(defs["declared_signer"]["properties"]["role"]["enum"]) == {
        item.value for item in SignerRole
    }
    outcome = defs["outcome_key"]["properties"]
    assert set(outcome["checkpoint"]["enum"]) == {item.value for item in Checkpoint}
    assert set(outcome["concept"]["enum"]) == {item.value for item in ConceptKind}
    assert set(finding["disposition"]["enum"]) == {item.value for item in Disposition}
    assert set(finding["severity"]["oneOf"][1]["enum"]) == {
        item.value for item in Severity
    }
    assert finding["outcome"]["properties"] == outcome
    assert set(finding["owner"]["oneOf"][1]["properties"]["role"]["enum"]) == {
        item.value for item in OwnerRole
    }


def test_the_published_grammars_are_the_strings_the_code_enforces() -> None:
    """Code and contract cannot drift: the strings are compared, not described."""

    event = _schema(EVENT_SCHEMA_PATH)
    reference = event["properties"]["external_reference"]["oneOf"][1]
    organization = event["$defs"]["declared_signer"]["properties"]["organization_id"]
    for published, grammar in (
        (reference, PROVENANCE_LABEL_GRAMMAR),
        (organization, PROVENANCE_SYSTEM_GRAMMAR),
    ):
        assert published["maxLength"] == grammar.max_length
        clauses = published["allOf"]
        assert clauses[0]["pattern"] == grammar.base
        assert [clause["not"]["pattern"] for clause in clauses[1:]] == [
            expression for expression, _ in grammar.exclusions
        ]


@pytest.mark.parametrize(
    "path",
    [(), ("outcome",), ("receipt",), ("owner",), ("signers", 0)],
)
def test_unknown_fields_fail_closed_at_every_level(
    review_event: EventBuilder, path: tuple[str | int, ...]
) -> None:
    event = review_event("owner_assigned")
    target: Any = event
    for key in path:
        target = target[key]
    target["contextsafe_extension"] = "unreviewed"
    assert not _event_validator().is_valid(event)


@pytest.mark.parametrize("field", ["note", "comment", "rationale", "reviewer_name"])
def test_the_contract_has_no_free_text_field_to_add_to(
    review_event: EventBuilder, field: str
) -> None:
    event = review_event("confirmed")
    event[field] = "reviewed and found satisfactory"
    assert not _event_validator().is_valid(event)


@pytest.mark.parametrize("value", ["verified", "signed", "not_signed", None])
def test_the_unsigned_constants_cannot_be_relabelled(
    review_event: EventBuilder, value: object
) -> None:
    event = review_event("confirmed", signature_status=value)
    assert not _event_validator().is_valid(event)
    event = review_event("confirmed")
    event["signers"][0]["signature_status"] = value
    assert not _event_validator().is_valid(event)


def test_the_state_contract_pins_its_limitations_and_its_status(
    tmp_path: Path, finding_receipt: dict[str, Any], review_event: EventBuilder
) -> None:
    _log, state = _walked_log(tmp_path, finding_receipt, review_event)
    validator = _state_validator()
    for limitations in ([], list(STATE_LIMITATIONS[:2]), [*STATE_LIMITATIONS, "x"]):
        assert not validator.is_valid({**state, "limitations": limitations})
    reordered = [STATE_LIMITATIONS[1], STATE_LIMITATIONS[0], STATE_LIMITATIONS[2]]
    assert not validator.is_valid({**state, "limitations": reordered})
    assert not validator.is_valid({**state, "signature_status": "verified"})
    assert not validator.is_valid({**state, "generated_at": "2026-09-04T00:00:00Z"})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("token_sha256", "Jordan Rivera"),
        ("token_sha256", "A" * 64),
        ("role", "clinical_safety_chair"),
    ],
)
def test_the_contract_owner_is_a_role_and_a_hash(
    review_event: EventBuilder, field: str, value: str
) -> None:
    event = review_event("owner_assigned")
    event["owner"][field] = value
    assert not _event_validator().is_valid(event)


@pytest.mark.parametrize(
    "value",
    ["reviewed by Jordan Rivera", "1987-03-14", "https://t.invalid/1", "x@y.invalid"],
)
def test_the_contract_external_reference_rejects_what_the_grammar_rejects(
    review_event: EventBuilder, value: str
) -> None:
    event = review_event("confirmed", external_reference=value)
    assert not _event_validator().is_valid(event)


def test_a_missing_required_field_fails_closed(review_event: EventBuilder) -> None:
    schema = _schema(EVENT_SCHEMA_PATH)
    for field in schema["required"]:
        event = review_event("confirmed")
        del event[field]
        assert not _event_validator().is_valid(event)
