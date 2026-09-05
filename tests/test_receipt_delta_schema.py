"""Published receipt-delta contract tests (B-037).

`schemas/contextsafe-receipt-delta-v0.1.schema.json` is the contract for the
document `contextsafe receipt diff` emits. These tests are its schema/runtime
agreement gate, modeled on `tests/test_receipt_schema.py`: the emitted delta
must validate, the published enums must equal the runtime types, an added
claim or a stripped, reworded, or padded limitation must fail closed, and the
negative gate is parametrized from the contract's own `required` lists so a
field added later cannot escape it.

The runtime has no dependencies and does not validate its own output at run
time; the published contract is enforced here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from jsonschema import Draft202012Validator

from contextsafe.canonical import canonical_json
from contextsafe.cli import EXIT_SUCCESS, main
from contextsafe.evaluator import evaluate
from contextsafe.models import OutcomeReason, OutcomeStatus
from contextsafe.receipt import build_receipt_document
from contextsafe.receipt_delta import (
    DELTA_LIMITATIONS,
    DELTA_SCHEMA_VERSION,
    ParsedReceipt,
    ReceiptResult,
    RuleChange,
    diff_receipts,
    parse_receipt_document,
)
from contextsafe.validation import parse_bundle

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "contextsafe-receipt-delta-v0.1.schema.json"

PINNED_LIMITATIONS = (
    "receipts-are-unsigned",
    "run-order-is-not-established",
    "payload-hash-agreement-is-not-verification",
)
"""The disclosures a delta must carry, restated independently of the runner."""


def _schema() -> dict[str, Any]:
    value = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _validator() -> Draft202012Validator:
    return Draft202012Validator(_schema())


def _declared_required_count(node: Any) -> int:
    if isinstance(node, dict):
        required = node.get("required")
        counted = len(required) if isinstance(required, list) else 0
        return counted + sum(_declared_required_count(value) for value in node.values())
    if isinstance(node, list):
        return sum(_declared_required_count(value) for value in node)
    return 0


def _required_field_cases() -> list[tuple[tuple[str | int, ...], str]]:
    schema = _schema()
    defs = schema["$defs"]
    cases: list[tuple[tuple[str | int, ...], str]] = []

    def resolve(node: dict[str, Any]) -> dict[str, Any]:
        while "$ref" in node:
            resolved = defs[node["$ref"].removeprefix("#/$defs/")]
            assert isinstance(resolved, dict)
            node = resolved
        return node

    def walk(node: dict[str, Any], path: tuple[str | int, ...]) -> None:
        node = resolve(node)
        for key in node.get("required", []):
            cases.append((path, key))
        for key, subschema in node.get("properties", {}).items():
            walk(subschema, (*path, key))
        items = node.get("items")
        if isinstance(items, dict):
            walk(items, (*path, 0))

    walk(schema, ())
    return cases


REQUIRED_FIELD_CASES = _required_field_cases()
REQUIRED_FIELD_IDS = [
    "-".join(str(part) for part in (*path, key)) for path, key in REQUIRED_FIELD_CASES
]


def _at(document: dict[str, Any], path: tuple[str | int, ...]) -> Any:
    target: Any = document
    for key in path:
        target = target[key]
    return target


@pytest.fixture
def delta(
    case_json: dict[str, Any],
    observations_json: dict[str, Any],
    rules_json: dict[str, Any],
) -> dict[str, Any]:
    """The delta between the reference receipt and one with a contradiction."""

    bundle = parse_bundle(case_json, observations_json, rules_json)
    before = parse_receipt_document(build_receipt_document(bundle, evaluate(bundle)))
    observations_json["observations"][4]["value"]["value"] = "ze/hir"
    rerun = parse_bundle(case_json, observations_json, rules_json)
    after = parse_receipt_document(build_receipt_document(rerun, evaluate(rerun)))
    return diff_receipts(before, after).to_dict()


def test_published_contract_accepts_the_reference_delta(
    delta: dict[str, Any],
) -> None:
    schema = _schema()
    Draft202012Validator.check_schema(schema)
    assert schema["$id"].endswith("/schemas/contextsafe-receipt-delta-v0.1.schema.json")
    _validator().validate(delta)


def test_cli_delta_artifact_validates_against_the_published_contract(
    tmp_path: Path,
    case_json: dict[str, Any],
    observations_json: dict[str, Any],
    rules_json: dict[str, Any],
) -> None:
    bundle = parse_bundle(case_json, observations_json, rules_json)
    receipt = tmp_path / "receipt.json"
    receipt.write_bytes(
        canonical_json(build_receipt_document(bundle, evaluate(bundle))).encode("utf-8")
        + b"\n"
    )
    output = tmp_path / "delta.json"
    code = main(
        [
            "receipt",
            "diff",
            "--before",
            str(receipt),
            "--after",
            str(receipt),
            "--output",
            str(output),
        ]
    )
    assert code == EXIT_SUCCESS
    _validator().validate(json.loads(output.read_text(encoding="utf-8")))


def test_contract_version_matches_the_runtime_constant() -> None:
    assert _schema()["properties"]["schema_version"]["const"] == DELTA_SCHEMA_VERSION


def test_contract_enums_equal_the_runtime_types() -> None:
    schema = _schema()
    summary = schema["properties"]["summary"]
    changes = {member.value for member in RuleChange}
    assert set(schema["$defs"]["rule_change"]["enum"]) == changes
    assert set(summary["required"]) == changes
    assert set(summary["properties"]) == changes
    assert set(schema["$defs"]["outcome_status"]["enum"]) == {
        member.value for member in OutcomeStatus
    }
    assert set(schema["$defs"]["outcome_reason"]["enum"]) == {
        member.value for member in OutcomeReason
    }


def test_contract_and_runtime_pin_the_same_limitations() -> None:
    limitations = _schema()["properties"]["limitations"]
    assert tuple(item["const"] for item in limitations["prefixItems"]) == (
        PINNED_LIMITATIONS
    )
    assert DELTA_LIMITATIONS == PINNED_LIMITATIONS
    assert limitations["minItems"] == len(PINNED_LIMITATIONS)
    assert limitations["maxItems"] == len(PINNED_LIMITATIONS)


@pytest.mark.parametrize(
    "path",
    [(), ("receipts",), ("receipts", "before"), ("summary",), ("rules", 0)],
)
def test_unknown_fields_fail_closed_at_every_level(
    delta: dict[str, Any], path: tuple[str | int, ...]
) -> None:
    _at(delta, path)["contextsafe_extension"] = "unreviewed"
    assert not _validator().is_valid(delta)


@pytest.mark.parametrize(
    "field",
    [
        "claimed_generated_at",
        "generated_at",
        "signature_status",
        "trusted_time",
        "envelope",
        "run_order",
        "reviewers",
    ],
)
def test_the_delta_rejects_time_signature_and_order_claims(
    delta: dict[str, Any], field: str
) -> None:
    """Envelope-free is machine-checkable: no field can carry a time or order."""

    delta[field] = "2026-08-04T09:30:00Z"
    assert not _validator().is_valid(delta)


@pytest.mark.parametrize(
    "field",
    ["expected_sha256", "observed_sha256s", "evidence_sha256s", "value", "name_to_use"],
)
def test_rule_entries_reject_copied_hashes_and_semantic_values(
    delta: dict[str, Any], field: str
) -> None:
    delta["rules"][0][field] = "CSYN-ASTER"
    assert not _validator().is_valid(delta)


@pytest.mark.parametrize(
    "limitations",
    [
        [],
        list(PINNED_LIMITATIONS[:2]),
        [PINNED_LIMITATIONS[0]] * 3,
        [*PINNED_LIMITATIONS, "reviewed-and-approved"],
        [*PINNED_LIMITATIONS[:2], "run-order-is-established"],
    ],
)
def test_stripped_reworded_or_padded_limitations_fail_the_contract(
    delta: dict[str, Any], limitations: list[str]
) -> None:
    delta["limitations"] = limitations
    assert not _validator().is_valid(delta)


def test_limitations_cannot_be_reordered(delta: dict[str, Any]) -> None:
    reordered = list(PINNED_LIMITATIONS)
    reordered[0], reordered[1] = reordered[1], reordered[0]
    delta["limitations"] = reordered
    assert not _validator().is_valid(delta)


@pytest.mark.parametrize("value", ["A" * 64, "0" * 63, "", None])
def test_payload_hashes_must_be_canonical_lowercase_hex(
    delta: dict[str, Any], value: object
) -> None:
    delta["receipts"]["before"]["payload_sha256"] = value
    assert not _validator().is_valid(delta)


@pytest.mark.parametrize("value", ["worse", "PASS", 1, None])
def test_an_unpublished_change_code_or_status_fails_closed(
    delta: dict[str, Any], value: object
) -> None:
    delta["rules"][0]["change"] = value
    assert not _validator().is_valid(delta)
    delta["rules"][0]["change"] = "unchanged"
    delta["rules"][0]["status_after"] = value
    assert not _validator().is_valid(delta)


@pytest.mark.parametrize("value", [-1, 1.5, True, "1"])
def test_summary_counts_are_non_negative_integers(
    delta: dict[str, Any], value: object
) -> None:
    delta["summary"]["regressed"] = value
    assert not _validator().is_valid(delta)


def test_every_required_field_the_contract_declares_is_exercised() -> None:
    assert len(REQUIRED_FIELD_CASES) == _declared_required_count(_schema())


@pytest.mark.parametrize(("path", "key"), REQUIRED_FIELD_CASES, ids=REQUIRED_FIELD_IDS)
def test_missing_required_fields_fail_closed(
    delta: dict[str, Any], path: tuple[str | int, ...], key: str
) -> None:
    del _at(delta, path)[key]
    assert not _validator().is_valid(delta)


def test_an_empty_rule_list_fails_the_contract(delta: dict[str, Any]) -> None:
    """The runtime refuses a receipt with no results, so the contract must too."""

    delta["rules"] = []
    assert not _validator().is_valid(delta)


_HEX = st.binary(min_size=32, max_size=32).map(bytes.hex)


@st.composite
def _receipts(draw: st.DrawFn) -> tuple[ParsedReceipt, ParsedReceipt]:
    indices = draw(st.lists(st.integers(0, 99), min_size=1, max_size=6, unique=True))

    def result(index: int, expected: str) -> ReceiptResult:
        return ReceiptResult(
            rule_id=f"A-I{index:02d}",
            rule_version="0.1.0",
            case_id="CTP-P01",
            checkpoint="ehr",
            concept="pronouns",
            status=draw(st.sampled_from(tuple(OutcomeStatus))),
            reason=draw(st.sampled_from(tuple(OutcomeReason))),
            expected_sha256=expected,
            observed_sha256s=(),
            evidence_sha256s=tuple(draw(st.lists(_HEX, max_size=2))),
        )

    expected = {index: draw(_HEX) for index in indices}
    rule_set = draw(_HEX)
    return (
        ParsedReceipt(
            case_id="CTP-P01",
            rule_set_sha256=rule_set,
            runner_version="0.1.0",
            payload_sha256=draw(_HEX),
            results=tuple(result(index, expected[index]) for index in indices),
        ),
        ParsedReceipt(
            case_id="CTP-P01",
            rule_set_sha256=rule_set,
            runner_version="0.1.0",
            payload_sha256=draw(_HEX),
            results=tuple(result(index, expected[index]) for index in indices),
        ),
    )


@settings(max_examples=200, deadline=None)
@given(pair=_receipts())
def test_generated_deltas_match_the_published_contract(
    pair: tuple[ParsedReceipt, ParsedReceipt],
) -> None:
    """Every status and reason combination the algebra allows must validate."""

    before, after = pair
    _validator().validate(diff_receipts(before, after).to_dict())
