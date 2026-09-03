"""Published receipt-contract tests (B-033, P0-09, RG-10).

`schemas/contextsafe-receipt-v0.1.schema.json` is the pre-1.0 shape of the
receipt schema that `docs/04-ARCHITECTURE.md` section 8 requires ContextSafe to
publish. These tests are the schema/runtime agreement gate named in
`docs/09-TEST-AND-EVALUATION.md` section 8 (T-RECEIPT schema) and section 9
gate 6: the emitted document must validate, the published enums must equal the
runtime types, an added claim or a stripped, reworded, or padded limitation
must fail closed, and the unsigned envelope constants may not be relabelled by
hand.

The runtime has no dependencies and does not validate its own output against
the schema at run time; the published contract is enforced here, exactly as the
case, observation, pack, plan, and evidence contracts are.
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from contextsafe.canonical import sha256_json
from contextsafe.cli import EXIT_SUCCESS, main
from contextsafe.evaluator import Outcome, evaluate
from contextsafe.models import (
    RECEIPT_DOCUMENT_SCHEMA_VERSION,
    RECEIPT_SCHEMA_VERSION,
    Checkpoint,
    ConceptKind,
    EvaluationBundle,
    OutcomeReason,
    OutcomeStatus,
)
from contextsafe.receipt import build_receipt_document
from contextsafe.reference_fixtures import REFERENCE_ROOT
from contextsafe.validation import parse_bundle

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = REFERENCE_ROOT
SCHEMA_PATH = ROOT / "schemas" / "contextsafe-receipt-v0.1.schema.json"

CLAIMED = datetime(2026, 8, 4, 9, 30, 0, tzinfo=UTC)

MANDATED_LIMITATIONS = (
    "Synthetic reference fixture only; not an approved clinical oracle.",
    "A passing result does not establish safety, compliance, or certification.",
    "Patient data is prohibited; bounded checks cannot prove an input is synthetic.",
    "This iteration does not ingest FHIR or sign artifacts.",
)
"""The disclosures a receipt must carry, restated independently of the runner.

F-030 in `docs/09-TEST-AND-EVALUATION.md` section 4 is "strip limitations from
report template", detected by the receipt schema/presentation gate. Reading the
runner's own constant — or the schema's pinned one — here would make that gate
tautological, so this restatement holds both to the same wording.
"""


def _schema() -> dict[str, Any]:
    value = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _declared_required_count(node: Any) -> int:
    """Count every entry in every `required` list the contract declares."""

    if isinstance(node, dict):
        required = node.get("required")
        counted = len(required) if isinstance(required, list) else 0
        return counted + sum(_declared_required_count(value) for value in node.values())
    if isinstance(node, list):
        return sum(_declared_required_count(value) for value in node)
    return 0


def _required_field_cases() -> list[tuple[tuple[str | int, ...], str]]:
    """Return every (object location, required field) pair the contract declares.

    Derived by walking the published schema rather than listed by hand, so a
    required field added to the contract later cannot silently escape the
    negative gate.
    """

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
        for index, subschema in enumerate(node.get("prefixItems", [])):
            walk(subschema, (*path, index))
        items = node.get("items")
        if isinstance(items, dict):
            walk(items, (*path, 0))

    walk(schema, ())
    return cases


REQUIRED_FIELD_CASES = _required_field_cases()

REQUIRED_FIELD_IDS = [
    "-".join(str(part) for part in (*path, key)) for path, key in REQUIRED_FIELD_CASES
]


def _validator() -> Draft202012Validator:
    return Draft202012Validator(_schema(), format_checker=FormatChecker())


def _payload_validator() -> Draft202012Validator:
    schema = _schema()
    return Draft202012Validator(
        {
            "$schema": schema["$schema"],
            "$ref": "#/$defs/deterministic_payload",
            "$defs": schema["$defs"],
        }
    )


def _at(document: dict[str, Any], path: tuple[str | int, ...]) -> Any:
    target: Any = document
    for key in path:
        target = target[key]
    return target


@pytest.fixture
def bundle(
    case_json: dict[str, Any],
    observations_json: dict[str, Any],
    rules_json: dict[str, Any],
) -> EvaluationBundle:
    """Return the parsed synthetic reference bundle."""

    return parse_bundle(case_json, observations_json, rules_json)


@pytest.fixture
def document(bundle: EvaluationBundle) -> dict[str, Any]:
    """Return the receipt document the runner emits for that bundle."""

    return build_receipt_document(
        bundle, evaluate(bundle), claimed_generated_at=CLAIMED
    )


def test_published_contract_accepts_the_reference_receipt_document(
    document: dict[str, Any],
) -> None:
    schema = _schema()
    Draft202012Validator.check_schema(schema)
    assert schema["$id"].endswith("/schemas/contextsafe-receipt-v0.1.schema.json")
    _validator().validate(document)


def test_published_contract_accepts_an_absent_claimed_time(
    bundle: EvaluationBundle,
) -> None:
    unclaimed = build_receipt_document(bundle, evaluate(bundle))
    assert unclaimed["envelope"]["claimed_generated_at"] is None
    _validator().validate(unclaimed)


def test_deterministic_payload_validates_against_its_standalone_subschema(
    document: dict[str, Any],
) -> None:
    _payload_validator().validate(document["payload"])
    assert not _payload_validator().is_valid(document)


def test_cli_receipt_artifact_validates_against_the_published_contract(
    tmp_path: Path,
) -> None:
    output = tmp_path / "receipt.json"
    code = main(
        [
            "evaluate",
            "--case",
            str(REFERENCE / "case.json"),
            "--observations",
            str(REFERENCE / "observations.json"),
            "--rules",
            str(REFERENCE / "rules.json"),
            "--claimed-generated-at",
            "2026-08-04T09:30:00Z",
            "--output",
            str(output),
        ]
    )
    assert code == EXIT_SUCCESS
    _validator().validate(json.loads(output.read_text(encoding="utf-8")))


def test_contract_versions_match_the_runtime_constants() -> None:
    schema = _schema()
    payload = schema["$defs"]["deterministic_payload"]
    assert (
        schema["properties"]["schema_version"]["const"]
        == RECEIPT_DOCUMENT_SCHEMA_VERSION
    )
    assert payload["properties"]["schema_version"]["const"] == RECEIPT_SCHEMA_VERSION


def test_contract_enums_equal_the_runtime_status_algebra_and_types() -> None:
    schema = _schema()
    payload = schema["$defs"]["deterministic_payload"]
    outcome = schema["$defs"]["outcome"]
    statuses = {member.value for member in OutcomeStatus}
    summary = payload["properties"]["summary"]
    assert set(schema["$defs"]["outcome_status"]["enum"]) == statuses
    assert set(summary["required"]) == statuses
    assert set(summary["properties"]) == statuses
    assert set(outcome["properties"]["reason"]["enum"]) == {
        member.value for member in OutcomeReason
    }
    assert set(outcome["properties"]["checkpoint"]["enum"]) == {
        member.value for member in Checkpoint
    }
    assert set(outcome["properties"]["concept"]["enum"]) == {
        member.value for member in ConceptKind
    }


@pytest.mark.parametrize("status", list(OutcomeStatus))
@pytest.mark.parametrize("reason", list(OutcomeReason))
def test_contract_accepts_every_published_status_and_reason(
    bundle: EvaluationBundle, status: OutcomeStatus, reason: OutcomeReason
) -> None:
    """Statuses the iteration-1 evaluator cannot yet emit must still validate."""

    outcome = Outcome(
        rule_id="A-I01",
        rule_version="0.1.0",
        case_id=bundle.case.case_id,
        checkpoint=Checkpoint.EHR.value,
        concept=ConceptKind.PRONOUNS,
        status=status,
        reason=reason,
        expected_sha256="0" * 64,
        observed_sha256s=("1" * 64,),
        evidence_sha256s=("2" * 64,),
    )
    _validator().validate(build_receipt_document(bundle, (outcome,)))


@pytest.mark.parametrize(
    "path",
    [
        (),
        ("envelope",),
        ("payload",),
        ("payload", "hashes"),
        ("payload", "scope"),
        ("payload", "summary"),
        ("payload", "results", 0),
    ],
)
def test_unknown_fields_fail_closed_at_every_level(
    document: dict[str, Any], path: tuple[str | int, ...]
) -> None:
    _at(document, path)["contextsafe_extension"] = "unreviewed"
    assert not _validator().is_valid(document)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("signature_status", "signed"),
        ("signature_status", "verified"),
        ("signature_status", "not_verified"),
        ("trusted_time", True),
    ],
)
def test_unsigned_envelope_cannot_be_relabelled(
    document: dict[str, Any], field: str, value: object
) -> None:
    """A later signing layer may not relabel these documents in place."""

    document["envelope"][field] = value
    assert not _validator().is_valid(document)


@pytest.mark.parametrize(
    "field",
    [
        "claimed_generated_at",
        "generated_at",
        "signature",
        "signatures",
        "signature_status",
        "trusted_time",
        "reviewers",
        "run_host",
    ],
)
def test_payload_rejects_time_signature_and_environment_claims(
    document: dict[str, Any], field: str
) -> None:
    """Claim minimality is machine-checkable, not only a code convention."""

    document["payload"][field] = "2026-08-04T09:30:00Z"
    assert not _validator().is_valid(document)


@pytest.mark.parametrize(
    "field", ["value", "observed_value", "expected", "name_to_use", "source_pointer"]
)
def test_outcomes_reject_semantic_and_source_values(
    document: dict[str, Any], field: str
) -> None:
    document["payload"]["results"][0][field] = "CSYN-ASTER"
    assert not _validator().is_valid(document)


def test_runtime_publishes_every_mandated_limitation(
    document: dict[str, Any],
) -> None:
    assert tuple(document["payload"]["limitations"]) == MANDATED_LIMITATIONS


def test_contract_pins_every_mandated_limitation_in_publication_order() -> None:
    """F-030: the published contract, not only the runner, fixes the wording."""

    limitations = _schema()["$defs"]["deterministic_payload"]["properties"][
        "limitations"
    ]
    assert tuple(item["const"] for item in limitations["prefixItems"]) == (
        MANDATED_LIMITATIONS
    )
    assert limitations["minItems"] == len(MANDATED_LIMITATIONS)
    assert limitations["maxItems"] == len(MANDATED_LIMITATIONS)


@pytest.mark.parametrize(
    "limitations",
    [
        [],
        list(MANDATED_LIMITATIONS[:3]),
        [MANDATED_LIMITATIONS[0]] * 4,
        [""] * 4,
    ],
)
def test_stripped_or_padded_limitations_fail_the_contract(
    document: dict[str, Any], limitations: list[str]
) -> None:
    """F-030: a report template may not drop a mandated disclosure."""

    document["payload"]["limitations"] = limitations
    assert not _validator().is_valid(document)


@pytest.mark.parametrize("index", range(len(MANDATED_LIMITATIONS)))
def test_a_mandated_disclosure_cannot_be_reworded(
    document: dict[str, Any], index: int
) -> None:
    """Replacing a disclosure with plausible filler is the F-030 fault itself."""

    limitations = list(MANDATED_LIMITATIONS)
    limitations[index] = "This evaluation was reviewed and found satisfactory."
    document["payload"]["limitations"] = limitations
    assert not _validator().is_valid(document)


def test_mandated_disclosures_cannot_be_reordered(document: dict[str, Any]) -> None:
    """Publication order is fixed, so receipt bytes stay comparable."""

    reordered = list(MANDATED_LIMITATIONS)
    reordered[0], reordered[1] = reordered[1], reordered[0]
    document["payload"]["limitations"] = reordered
    assert not _validator().is_valid(document)


@pytest.mark.parametrize("extra", ["Reviewed by the vendor.", "", "A" * 512])
def test_limitations_are_bounded_against_free_text(
    document: dict[str, Any], extra: str
) -> None:
    """The payload carries hashes, statuses, and counts — not a prose channel."""

    document["payload"]["limitations"] = [*MANDATED_LIMITATIONS, extra]
    assert not _validator().is_valid(document)


@pytest.mark.parametrize(
    "scope_field", ["clinical_oracle_approved", "patient_data_allowed"]
)
def test_scope_cannot_claim_approval_or_patient_data(
    document: dict[str, Any], scope_field: str
) -> None:
    document["payload"]["scope"][scope_field] = True
    assert not _validator().is_valid(document)


@pytest.mark.parametrize(
    "value",
    ["A" * 64, "0" * 63, "0" * 65, "not-a-hash", "", None],
)
def test_payload_hash_must_be_canonical_lowercase_hex(
    document: dict[str, Any], value: object
) -> None:
    document["payload_sha256"] = value
    assert not _validator().is_valid(document)


@pytest.mark.parametrize(
    "claimed",
    [
        "2026-08-04T09:30:00+01:00",
        "2026-08-04T09:30:00.500Z",
        "2026-08-04 09:30:00Z",
        "2026-02-30T09:30:00Z",
        "2026-08-04T24:30:00Z",
        1754301000,
    ],
)
def test_claimed_time_must_be_whole_second_utc_or_absent(
    document: dict[str, Any], claimed: object
) -> None:
    document["envelope"]["claimed_generated_at"] = claimed
    assert not _validator().is_valid(document)


def test_every_required_field_the_contract_declares_is_exercised() -> None:
    """The negative gate is parametrized from the contract, so it cannot drift.

    A lower count means the walk never reached a declared `required` list; a
    higher one means one definition is counted from two references.
    """

    assert len(REQUIRED_FIELD_CASES) == _declared_required_count(_schema())


@pytest.mark.parametrize(("path", "key"), REQUIRED_FIELD_CASES, ids=REQUIRED_FIELD_IDS)
def test_missing_required_fields_fail_closed(
    document: dict[str, Any], path: tuple[str | int, ...], key: str
) -> None:
    del _at(document, path)[key]
    assert not _validator().is_valid(document)


def test_empty_result_set_fails_the_contract(document: dict[str, Any]) -> None:
    """The runtime rejects an empty rule set, so the contract must too."""

    document["payload"]["results"] = []
    assert not _validator().is_valid(document)


def test_structural_validity_is_not_tamper_detection(
    document: dict[str, Any],
) -> None:
    """The contract bounds shape; hash agreement is a separate check (B-036)."""

    assert document["payload_sha256"] == sha256_json(document["payload"])
    document["payload"]["summary"]["pass"] += 1
    assert _validator().is_valid(document)
    assert document["payload_sha256"] != sha256_json(document["payload"])
