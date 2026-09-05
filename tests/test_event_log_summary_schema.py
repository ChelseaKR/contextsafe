"""The published event-log summary contract against the runtime.

`schemas/contextsafe-event-log-summary-v0.1.schema.json` is what a consumer of
`contextsafe events summarize` validates against, in the form
`tests/test_review_schema.py` uses for the review contracts: what the runtime
emits validates, the closed key sets equal the runtime's closed sets, the
grammar is the string the code enforces, and a field the contract does not
publish fails closed.

The `counts_by_command` agreement is the one with teeth. The contract names
every command as a required key, so a command added to
`contextsafe.eventlog.COMMANDS` without a new contract version fails here
rather than in a partner's validator.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from contextsafe.eventlog import (
    COMMANDS,
    ERROR_CODE_PATTERN,
    SUMMARY_SCHEMA_VERSION,
    Outcome,
    append_event,
    summarize_bytes,
    summarize_log,
)

ROOT = Path(__file__).resolve().parents[1]
SUMMARY_SCHEMA_PATH = (
    ROOT / "schemas" / "contextsafe-event-log-summary-v0.1.schema.json"
)


def _schema() -> dict[str, Any]:
    value = json.loads(SUMMARY_SCHEMA_PATH.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _validator() -> Draft202012Validator:
    return Draft202012Validator(_schema())


@pytest.fixture
def summary(tmp_path: Path) -> dict[str, Any]:
    """A summary of a log holding one of each outcome and two commands."""

    log_dir = tmp_path / "logs"
    append_event(log_dir, command="evaluate", outcome=Outcome.ACCEPTED)
    append_event(
        log_dir,
        command="cleanup",
        outcome=Outcome.REJECTED,
        error_code="cleanup_not_confirmed",
    )
    return dict(summarize_log(log_dir).to_dict())


def test_the_contract_is_a_valid_draft_2020_12_schema() -> None:
    """A contract that does not compile checks nothing."""

    Draft202012Validator.check_schema(_schema())


def test_what_the_runtime_emits_validates(summary: dict[str, Any]) -> None:
    """The agreement gate: the emitted document against the published shape."""

    _validator().validate(summary)


def test_the_empty_summary_validates_too() -> None:
    """A log of no runs is a document a consumer must still be able to read."""

    _validator().validate(summarize_bytes(b"").to_dict())


def test_the_contract_version_matches_the_runtime_constant() -> None:
    """One version string, in the code and in the contract."""

    schema = _schema()
    assert schema["properties"]["schema_version"]["const"] == SUMMARY_SCHEMA_VERSION
    assert SUMMARY_SCHEMA_PATH.name.endswith("v0.1.schema.json")


def test_the_contract_names_every_command_the_log_publishes() -> None:
    """Widening the log's command vocabulary moves this contract's version."""

    counts = _schema()["properties"]["counts_by_command"]
    assert set(counts["properties"]) == set(COMMANDS)
    assert set(counts["required"]) == set(COMMANDS)
    assert counts["additionalProperties"] is False


def test_the_contract_names_every_outcome_the_log_publishes() -> None:
    """The outcome set is closed in the contract exactly as it is in the code."""

    counts = _schema()["properties"]["counts_by_outcome"]
    assert set(counts["properties"]) == {outcome.value for outcome in Outcome}
    assert counts["additionalProperties"] is False


def test_the_published_error_code_grammar_is_the_one_the_code_enforces() -> None:
    """A code the contract admits is a code the writer would have written."""

    published = _schema()["properties"]["counts_by_error_code"]["propertyNames"]
    assert published["pattern"] == ERROR_CODE_PATTERN.pattern


def test_the_contract_has_no_free_text_field_to_add_to() -> None:
    """Every published property is a count, a digest, or the version constant."""

    properties = _schema()["properties"]
    assert set(properties) == {
        "counts_by_command",
        "counts_by_error_code",
        "counts_by_outcome",
        "log_sha256",
        "record_count",
        "schema_version",
    }
    assert _schema()["additionalProperties"] is False


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(
            lambda document: document.update(
                {"log_dir": "logs/contextsafe-events.jsonl"}
            ),
            id="a-path-at-the-top-level",
        ),
        pytest.param(
            lambda document: document["counts_by_command"].update({"tail": 1}),
            id="a-command-the-log-does-not-publish",
        ),
        pytest.param(
            lambda document: document["counts_by_outcome"].update({"maybe": 1}),
            id="an-outcome-the-log-does-not-publish",
        ),
        pytest.param(
            lambda document: document["counts_by_error_code"].update(
                {"failed reading case.json": 1}
            ),
            id="an-error-code-that-is-a-message",
        ),
        pytest.param(
            lambda document: document.update({"record_count": -1}),
            id="a-negative-count",
        ),
        pytest.param(
            lambda document: document.update({"log_sha256": "not-a-digest"}),
            id="a-digest-that-is-not-one",
        ),
        pytest.param(
            lambda document: document.pop("counts_by_error_code"),
            id="a-required-section-removed",
        ),
    ],
)
def test_a_document_outside_the_contract_fails_closed(
    summary: dict[str, Any], mutate: Any
) -> None:
    """The contract refuses what the runtime would never emit."""

    document = copy.deepcopy(summary)
    mutate(document)
    assert not _validator().is_valid(document)
