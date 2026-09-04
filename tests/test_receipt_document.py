"""Payload/envelope separation invariants for receipt documents (B-021, P0-14)."""

from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest

from contextsafe.canonical import sha256_json
from contextsafe.errors import ContextSafeError
from contextsafe.evaluator import evaluate
from contextsafe.receipt import (
    build_envelope,
    build_receipt,
    build_receipt_document,
    render_receipt,
)
from contextsafe.validation import parse_bundle

CLAIMED = datetime(2026, 7, 17, 1, 2, 3, tzinfo=UTC)
LATER = datetime(2026, 7, 18, 4, 5, 6, tzinfo=UTC)


def _document(
    case_json: dict[str, Any],
    observations_json: dict[str, Any],
    rules_json: dict[str, Any],
    claimed_generated_at: datetime | None,
) -> dict[str, Any]:
    bundle = parse_bundle(case_json, observations_json, rules_json)
    return build_receipt_document(
        bundle, evaluate(bundle), claimed_generated_at=claimed_generated_at
    )


def test_document_has_exact_versioned_shape(
    case_json: dict[str, Any],
    observations_json: dict[str, Any],
    rules_json: dict[str, Any],
) -> None:
    document = _document(case_json, observations_json, rules_json, CLAIMED)
    assert set(document) == {"envelope", "payload", "payload_sha256", "schema_version"}
    assert document["schema_version"] == "contextsafe.receipt-document/0.1.0"
    assert set(document["envelope"]) == {
        "claimed_generated_at",
        "signature_status",
        "trusted_time",
    }
    assert document["envelope"]["claimed_generated_at"] == "2026-07-17T01:02:03Z"
    assert document["envelope"]["signature_status"] == "not_signed"
    assert document["envelope"]["trusted_time"] is False
    assert document["payload"]["schema_version"] == "contextsafe.receipt/0.2.0"


def test_envelope_never_changes_payload_or_its_hash(
    case_json: dict[str, Any],
    observations_json: dict[str, Any],
    rules_json: dict[str, Any],
) -> None:
    first = _document(case_json, observations_json, rules_json, CLAIMED)
    second = _document(case_json, observations_json, rules_json, LATER)
    third = _document(case_json, observations_json, rules_json, None)
    assert first["payload"] == second["payload"] == third["payload"]
    assert (
        first["payload_sha256"] == second["payload_sha256"] == third["payload_sha256"]
    )
    assert first["envelope"] != second["envelope"]
    assert third["envelope"]["claimed_generated_at"] is None
    assert "2026-07-17T01:02:03Z" not in render_receipt(first["payload"])


def test_payload_hash_covers_exactly_the_payload(
    case_json: dict[str, Any],
    observations_json: dict[str, Any],
    rules_json: dict[str, Any],
) -> None:
    document = _document(case_json, observations_json, rules_json, CLAIMED)
    assert document["payload_sha256"] == sha256_json(document["payload"])
    observations_json["observations"][4]["value"]["value"] = "ze/hir"
    changed = _document(case_json, observations_json, rules_json, CLAIMED)
    assert changed["payload_sha256"] != document["payload_sha256"]
    assert changed["envelope"] == document["envelope"]


def test_document_is_deterministic_and_input_order_independent(
    case_json: dict[str, Any],
    observations_json: dict[str, Any],
    rules_json: dict[str, Any],
) -> None:
    first = render_receipt(_document(case_json, observations_json, rules_json, CLAIMED))
    observations_json["observations"].reverse()
    rules_json["rules"].reverse()
    second = render_receipt(
        _document(case_json, observations_json, rules_json, CLAIMED)
    )
    assert first == second
    assert first.endswith("\n")


def test_document_contains_no_semantic_or_source_values(
    case_json: dict[str, Any],
    observations_json: dict[str, Any],
    rules_json: dict[str, Any],
) -> None:
    rendered = render_receipt(
        _document(case_json, observations_json, rules_json, CLAIMED)
    )
    for prohibited in (
        "CSYN-ASTER",
        "fixture-gender-1",
        "fixture-context-1",
        "they/them",
        "government-id",
        "source_pointer",
    ):
        assert prohibited not in rendered


@pytest.mark.parametrize(
    "claimed",
    [
        datetime(2026, 7, 17, 1, 2, 3),
        datetime(2026, 7, 17, 1, 2, 3, tzinfo=timezone(timedelta(hours=1))),
        datetime(2026, 7, 17, 1, 2, 3, 500_000, tzinfo=UTC),
    ],
)
def test_envelope_rejects_naive_offset_and_subsecond_time(claimed: datetime) -> None:
    with pytest.raises(ContextSafeError) as excinfo:
        build_envelope(claimed)
    assert excinfo.value.code == "invalid_timestamp"
    assert excinfo.value.path == "$.envelope.claimed_generated_at"


def test_payload_builder_remains_available_and_identical(
    case_json: dict[str, Any],
    observations_json: dict[str, Any],
    rules_json: dict[str, Any],
) -> None:
    bundle = parse_bundle(case_json, observations_json, rules_json)
    outcomes = evaluate(bundle)
    document = build_receipt_document(bundle, outcomes)
    assert document["payload"] == build_receipt(bundle, outcomes)
