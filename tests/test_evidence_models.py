"""Published evidence and ambiguity-preserving observation contract tests."""

import copy
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError

from contextsafe.errors import ContextSafeError
from contextsafe.evidence import (
    CANONICAL_JSON_MEDIA_TYPE,
    CANONICAL_JSON_SOURCE_TYPE,
    EvidenceMetadata,
    build_evidence_record,
    build_evidence_scope,
    parse_canonical_observation,
    parse_evidence_record,
    parse_evidence_source,
)
from contextsafe.plan import ExecutionPlan
from contextsafe.preflight import preflight_source

ROOT = Path(__file__).resolve().parents[1]


def _observation(observations_json: dict[str, Any]) -> dict[str, Any]:
    return _observation_at(observations_json, 0)


def _observation_at(observations_json: dict[str, Any], index: int) -> dict[str, Any]:
    source = observations_json["observations"][index]
    return {
        "schema_version": "contextsafe.observation/1.0.0",
        "observation_id": source["observation_id"],
        "evidence_id": "EVD-" + "0" * 64,
        "case_id": source["case_id"],
        "checkpoint": source["checkpoint"],
        "concept": source["concept"],
        "canonical_path": f"$.concepts.{source['concept']}",
        "context_token": None,
        "mapping": copy.deepcopy(source["mapping"]),
        "ambiguity": "unambiguous",
        "candidates": [
            {
                "source_pointer": source["evidence"]["source_pointer"],
                "typed_value": copy.deepcopy(source["value"]),
            }
        ],
    }


def test_reference_observation_passes_schema_and_runtime(
    observations_json: dict[str, Any],
) -> None:
    value = _observation(observations_json)
    parsed = parse_canonical_observation(value)
    assert parsed.to_dict() == value
    schema = json.loads(
        (ROOT / "schemas" / "contextsafe-observation-v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(value)


def test_every_reference_runtime_observation_passes_published_schema(
    observations_json: dict[str, Any],
) -> None:
    schema = json.loads(
        (ROOT / "schemas" / "contextsafe-observation-v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    validator = Draft202012Validator(schema)
    for index in range(len(observations_json["observations"])):
        parsed = parse_canonical_observation(_observation_at(observations_json, index))
        validator.validate(parsed.to_dict())


@pytest.mark.parametrize(
    ("field", "expected_code"),
    [
        ("context_id", "non_synthetic_context"),
        ("supporting_observation_ids", "invalid_support"),
    ],
)
def test_spcu_runtime_rejects_empty_synthetic_suffixes_required_by_schema(
    observations_json: dict[str, Any], field: str, expected_code: str
) -> None:
    value = _observation_at(observations_json, 2)
    typed_value = value["candidates"][0]["typed_value"]
    if field == "context_id":
        typed_value[field] = "ORDER-CSYN-"
    else:
        typed_value[field] = ["SUP-CSYN-"]

    with pytest.raises(ContextSafeError) as raised:
        parse_canonical_observation(value)
    assert raised.value.code == expected_code

    schema = json.loads(
        (ROOT / "schemas" / "contextsafe-observation-v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(value)


def test_observation_schema_marks_runtime_pointer_uniqueness(
    observations_json: dict[str, Any],
) -> None:
    value = _observation(observations_json)
    value["ambiguity"] = "ambiguous"
    second = copy.deepcopy(value["candidates"][0])
    second["typed_value"]["value"] = "fixture-gender-2"
    value["candidates"].append(second)
    schema = json.loads(
        (ROOT / "schemas" / "contextsafe-observation-v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    candidates_schema = schema["properties"]["candidates"]
    assert candidates_schema["x-contextsafe-unique-by"] == "source_pointer"
    Draft202012Validator(schema).validate(value)
    with pytest.raises(ContextSafeError) as raised:
        parse_canonical_observation(value)
    assert raised.value.code == "duplicate_source_pointer"

    value["candidates"][1] = copy.deepcopy(value["candidates"][0])
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(value)


def test_ambiguous_observation_retains_every_typed_candidate(
    observations_json: dict[str, Any],
) -> None:
    value = _observation(observations_json)
    value["ambiguity"] = "ambiguous"
    second = copy.deepcopy(value["candidates"][0])
    second["source_pointer"] = "$.concepts.gender_identity[1]"
    second["typed_value"]["value"] = "fixture-gender-2"
    value["candidates"].append(second)
    parsed = parse_canonical_observation(value)
    assert [candidate.typed_value.value for candidate in parsed.candidates] == [
        "fixture-gender-1",
        "fixture-gender-2",
    ]


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        (
            lambda value: value.update({"ambiguity": "ambiguous"}),
            "ambiguity_mismatch",
        ),
        (
            lambda value: value["candidates"].append(value["candidates"][0]),
            "ambiguity_mismatch",
        ),
        (
            lambda value: value.update({"canonical_path": "$.concepts.pronouns"}),
            "canonical_path_mismatch",
        ),
        (
            lambda value: value["mapping"].update(
                {"source_concept": "recorded_sex_or_gender"}
            ),
            "concept_type_mismatch",
        ),
    ],
)
def test_observation_ambiguity_path_and_mapping_fail_closed(
    observations_json: dict[str, Any], mutation: Any, expected_code: str
) -> None:
    value = _observation(observations_json)
    mutation(value)
    with pytest.raises(ContextSafeError) as raised:
        parse_canonical_observation(value)
    assert raised.value.code == expected_code


def test_evidence_record_id_binds_every_canonical_field(
    tmp_path: Path,
    evidence_source_json: dict[str, Any],
    evidence_scope: Any,
    evidence_metadata: Any,
) -> None:
    source = tmp_path / "source.json"
    source.write_text(json.dumps(evidence_source_json), encoding="utf-8")
    record = build_evidence_record(
        preflight_source(source, evidence_scope), evidence_metadata
    )
    assert parse_evidence_record(record.to_dict()) == record
    tampered = record.to_dict()
    tampered["system_version"] = "fixture-2.0"
    with pytest.raises(ContextSafeError) as raised:
        parse_evidence_record(tampered)
    assert raised.value.code == "evidence_id_mismatch"


def test_evidence_record_cannot_claim_executable(
    tmp_path: Path,
    evidence_source_json: dict[str, Any],
    evidence_scope: Any,
    evidence_metadata: Any,
) -> None:
    source = tmp_path / "source.json"
    source.write_text(json.dumps(evidence_source_json), encoding="utf-8")
    value = build_evidence_record(
        preflight_source(source, evidence_scope), evidence_metadata
    ).to_dict()
    value["usable_for_execution"] = True
    with pytest.raises(ContextSafeError) as raised:
        parse_evidence_record(value)
    assert raised.value.code == "authorization_not_verified"


def test_evidence_timestamp_schema_and_models_require_canonical_utc(
    tmp_path: Path,
    evidence_source_json: dict[str, Any],
    evidence_scope: Any,
    evidence_metadata: Any,
) -> None:
    source = tmp_path / "source.json"
    source.write_text(json.dumps(evidence_source_json), encoding="utf-8")
    value = build_evidence_record(
        preflight_source(source, evidence_scope), evidence_metadata
    ).to_dict()
    value["captured_at"] = "2026-02-31T12:00:00Z"
    schema = json.loads(
        (ROOT / "schemas" / "contextsafe-evidence-v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    with pytest.raises(ValidationError):
        validator.validate(value)
    with pytest.raises(ContextSafeError) as raised:
        parse_evidence_record(value)
    assert raised.value.code == "invalid_timestamp"

    value["captured_at"] = "2025-02-29T12:00:00Z"
    Draft202012Validator(schema).validate(value)
    with pytest.raises(ContextSafeError) as raised:
        parse_evidence_record(value)
    assert raised.value.code == "invalid_timestamp"

    invalid_timestamps = (
        datetime(2026, 7, 13, 12),
        datetime(2026, 7, 13, 12, tzinfo=timezone(timedelta(hours=-7))),
        datetime(2026, 7, 13, 12, microsecond=1, tzinfo=UTC),
    )
    for captured_at in invalid_timestamps:
        with pytest.raises(ContextSafeError) as raised:
            EvidenceMetadata(
                captured_at=captured_at,
                collector_id="TEST-COLLECTOR",
                system_id="SYS-STAGING-EHR",
                system_version="fixture-1.0",
            )
        assert raised.value.code == "invalid_timestamp"


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        (
            lambda plan: replace(
                plan,
                environment=replace(plan.environment, non_production_attested=False),
            ),
            "non_production_attestation_missing",
        ),
        (
            lambda plan: replace(plan, case_tokens=("CSYN-CTP-Z99",)),
            "case_scope_mismatch",
        ),
        (
            lambda plan: replace(plan, checkpoints=()),
            "checkpoint_scope_mismatch",
        ),
        (
            lambda plan: replace(
                plan,
                synthetic_namespace=replace(
                    plan.synthetic_namespace, value_prefix="OTHER-"
                ),
            ),
            "namespace_mismatch",
        ),
    ],
)
def test_evidence_scope_rechecks_critical_plan_guards(
    execution_plan: ExecutionPlan, mutation: Any, expected_code: str
) -> None:
    plan = mutation(execution_plan)
    with pytest.raises(ContextSafeError) as raised:
        build_evidence_scope(
            plan,
            case_token=execution_plan.case_tokens[0],
            checkpoint="ehr",
            source_type=CANONICAL_JSON_SOURCE_TYPE,
            media_type=CANONICAL_JSON_MEDIA_TYPE,
        )
    assert raised.value.code == expected_code


def test_evidence_scope_rejects_unknown_checkpoint(
    execution_plan: ExecutionPlan,
) -> None:
    with pytest.raises(ContextSafeError) as raised:
        build_evidence_scope(
            execution_plan,
            case_token=execution_plan.case_tokens[0],
            checkpoint="unknown-boundary",
            source_type=CANONICAL_JSON_SOURCE_TYPE,
            media_type=CANONICAL_JSON_MEDIA_TYPE,
        )
    assert raised.value.code == "unsupported_checkpoint"


def test_evidence_capture_must_fall_inside_plan_validity(
    tmp_path: Path,
    evidence_source_json: dict[str, Any],
    evidence_scope: Any,
    evidence_metadata: Any,
) -> None:
    source = tmp_path / "source.json"
    source.write_text(json.dumps(evidence_source_json), encoding="utf-8")
    outside = replace(
        evidence_metadata,
        captured_at=evidence_metadata.captured_at.replace(year=2027),
    )
    with pytest.raises(ContextSafeError) as raised:
        build_evidence_record(preflight_source(source, evidence_scope), outside)
    assert raised.value.code == "capture_outside_plan"


def test_source_envelope_supports_explicit_null_codes_and_rejects_bounds(
    evidence_source_json: dict[str, Any], evidence_scope: Any
) -> None:
    evidence_source_json["records"][0]["value_code"] = None
    evidence_source_json["records"][0]["context_code"] = None
    assert (
        parse_evidence_source(evidence_source_json, scope=evidence_scope)
        .records[0]
        .value_code
        is None
    )

    evidence_source_json["schema_version"] = "contextsafe.evidence-source/2.0.0"
    with pytest.raises(ContextSafeError) as raised:
        parse_evidence_source(evidence_source_json, scope=evidence_scope)
    assert raised.value.code == "unsupported_schema"

    evidence_source_json["schema_version"] = "contextsafe.evidence-source/1.0.0"
    evidence_source_json["records"] = []
    with pytest.raises(ContextSafeError) as raised:
        parse_evidence_source(evidence_source_json, scope=evidence_scope)
    assert raised.value.code == "invalid_record_count"


@pytest.mark.parametrize(
    ("field", "value", "expected_code"),
    [
        ("schema_version", "contextsafe.evidence/2.0.0", "unsupported_schema"),
        ("case_id", "CTP-Z99", "case_scope_mismatch"),
        ("media_type", "application/json", "unsupported_media_type"),
        ("raw_byte_count", 0, "invalid_integer"),
    ],
)
def test_evidence_record_rejects_contract_drift_before_id_check(
    tmp_path: Path,
    evidence_source_json: dict[str, Any],
    evidence_scope: Any,
    evidence_metadata: Any,
    field: str,
    value: object,
    expected_code: str,
) -> None:
    source = tmp_path / "source.json"
    source.write_text(json.dumps(evidence_source_json), encoding="utf-8")
    record = build_evidence_record(
        preflight_source(source, evidence_scope), evidence_metadata
    ).to_dict()
    record[field] = value
    with pytest.raises(ContextSafeError) as raised:
        parse_evidence_record(record)
    assert raised.value.code == expected_code


def test_observation_rejects_schema_concept_duplicate_pointer_and_accepts_context(
    observations_json: dict[str, Any],
) -> None:
    value = _observation(observations_json)
    scope_context = "CSYN-EHR-CONTEXT"
    value["context_token"] = scope_context
    assert parse_canonical_observation(value).context_token == scope_context

    value["schema_version"] = "contextsafe.observation/2.0.0"
    with pytest.raises(ContextSafeError) as raised:
        parse_canonical_observation(value)
    assert raised.value.code == "unsupported_schema"

    value = _observation(observations_json)
    value["concept"] = "unsupported"
    with pytest.raises(ContextSafeError) as raised:
        parse_canonical_observation(value)
    assert raised.value.code == "invalid_enum"

    value = _observation(observations_json)
    value["ambiguity"] = "ambiguous"
    value["candidates"].append(copy.deepcopy(value["candidates"][0]))
    with pytest.raises(ContextSafeError) as raised:
        parse_canonical_observation(value)
    assert raised.value.code == "duplicate_source_pointer"
