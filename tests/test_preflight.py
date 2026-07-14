"""Pre-persistence privacy-boundary and descriptor-lifecycle tests."""

import copy
import hashlib
import json
import os
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

import contextsafe.preflight as preflight_module
from contextsafe.cli import main
from contextsafe.errors import ContextSafeError
from contextsafe.evidence import (
    CANONICAL_JSON_MEDIA_TYPE,
    CANONICAL_JSON_SOURCE_TYPE,
    EvidenceScope,
    build_evidence_scope,
    parse_evidence_source,
)
from contextsafe.models import Checkpoint
from contextsafe.plan import ExecutionPlan
from contextsafe.preflight import (
    MAX_EVIDENCE_BYTES,
    open_preflighted_source,
    preflight_source,
)

ROOT = Path(__file__).resolve().parents[1]


def _write_source(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value, separators=(",", ":")), encoding="utf-8")
    return path


def _assert_rejected(
    tmp_path: Path,
    evidence_source_json: dict[str, Any],
    evidence_scope: EvidenceScope,
    expected_code: str,
) -> None:
    source = _write_source(tmp_path / "source.json", evidence_source_json)
    with pytest.raises(ContextSafeError) as raised:
        preflight_source(source, evidence_scope)
    assert raised.value.code == expected_code


def test_reference_source_passes_schema_runtime_and_preflight(
    tmp_path: Path,
    evidence_source_json: dict[str, Any],
    evidence_scope: EvidenceScope,
) -> None:
    schema = json.loads(
        (ROOT / "schemas" / "contextsafe-evidence-source-v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(evidence_source_json)
    envelope = parse_evidence_source(evidence_source_json, scope=evidence_scope)
    assert envelope.to_dict() == evidence_source_json

    source = _write_source(tmp_path / "source.json", evidence_source_json)
    raw = source.read_bytes()
    result = preflight_source(source, evidence_scope)
    assert result.raw_sha256 == hashlib.sha256(raw).hexdigest()
    assert result.raw_byte_count == len(raw)
    assert result.to_dict()["persisted"] is False
    assert list(tmp_path.iterdir()) == [source]


def test_source_schema_marks_runtime_pointer_uniqueness(
    evidence_source_json: dict[str, Any], evidence_scope: EvidenceScope
) -> None:
    schema = json.loads(
        (ROOT / "schemas" / "contextsafe-evidence-source-v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    records_schema = schema["properties"]["records"]
    assert records_schema["x-contextsafe-unique-by"] == "source_pointer"
    second = copy.deepcopy(evidence_source_json["records"][0])
    second["field_code"] = "status"
    evidence_source_json["records"].append(second)
    Draft202012Validator(schema).validate(evidence_source_json)
    with pytest.raises(ContextSafeError) as raised:
        parse_evidence_source(evidence_source_json, scope=evidence_scope)
    assert raised.value.code == "duplicate_source_pointer"

    evidence_source_json["records"][1] = copy.deepcopy(
        evidence_source_json["records"][0]
    )
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(evidence_source_json)


@pytest.mark.parametrize(
    "identifier",
    [
        "person@example.invalid",
        "123-45-6789",
        "415-555-0199",
        "https://patient.invalid/record",
        "1980-01-02",
        "MRN: ABCD1234",
        "123456789",
    ],
)
def test_direct_identifier_patterns_fail_before_profile_acceptance(
    tmp_path: Path,
    evidence_source_json: dict[str, Any],
    evidence_scope: EvidenceScope,
    identifier: str,
) -> None:
    evidence_source_json["records"][0]["value_code"] = identifier
    _assert_rejected(
        tmp_path,
        evidence_source_json,
        evidence_scope,
        "direct_identifier_detected",
    )


def test_safe_schema_location_is_reported_without_echoing_values(
    tmp_path: Path,
    evidence_source_json: dict[str, Any],
    evidence_scope: EvidenceScope,
) -> None:
    evidence_source_json["records"][0]["value_code"] = "person@example.invalid"
    source = _write_source(tmp_path / "source.json", evidence_source_json)
    with pytest.raises(ContextSafeError) as raised:
        preflight_source(source, evidence_scope)
    assert raised.value.path == "$.records[0].value_code"
    assert "person@example.invalid" not in str(raised.value)


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        (lambda value: value.update({"note": "prohibited"}), "prohibited_field"),
        (
            lambda value: value["records"][0].update(
                {"value_code": "CTXSAFE-PHI-CANARY-ALICE"}
            ),
            "phi_canary_detected",
        ),
        (
            lambda value: value["records"][0].update(
                {"value_code": "patient-like prose"}
            ),
            "unapproved_free_text",
        ),
        (
            lambda value: value["records"][0].update(
                {"value_code": "CSYN-SAFE\u200bTOKEN"}
            ),
            "prohibited_unicode",
        ),
        (
            lambda value: value["records"][0].update({"value_code": " CSYN-SAFE"}),
            "unapproved_free_text",
        ),
        (lambda value: value.update({"unexpected": True}), "unknown_field"),
        (
            lambda value: value["synthetic_identifier"].update(
                {"value": "CSYN-CTP-Z99"}
            ),
            "namespace_mismatch",
        ),
        (
            lambda value: value.update({"checkpoint": "interface"}),
            "evidence_scope_mismatch",
        ),
        (
            lambda value: value.update({"plan_id": "PLAN-OTHER-TEST"}),
            "evidence_scope_mismatch",
        ),
        (
            lambda value: value.update({"source_type": "fhir_r4_json"}),
            "unsupported_source_type",
        ),
        (
            lambda value: value["records"].append(value["records"][0]),
            "duplicate_source_pointer",
        ),
    ],
)
def test_field_namespace_free_text_and_canary_fail_closed(
    tmp_path: Path,
    evidence_source_json: dict[str, Any],
    evidence_scope: EvidenceScope,
    mutation: Any,
    expected_code: str,
) -> None:
    mutation(evidence_source_json)
    _assert_rejected(tmp_path, evidence_source_json, evidence_scope, expected_code)


@pytest.mark.parametrize(
    ("raw", "expected_code"),
    [
        (b"{", "invalid_json"),
        (b"\xff", "invalid_utf8"),
        (b'{"plan_id":"A","plan_id":"B"}', "duplicate_json_key"),
        (b"[" * 100 + b"0" + b"]" * 100, "input_too_deep"),
    ],
)
def test_malformed_json_is_rejected_without_content_echo(
    tmp_path: Path,
    evidence_scope: EvidenceScope,
    raw: bytes,
    expected_code: str,
) -> None:
    source = tmp_path / "source.json"
    source.write_bytes(raw)
    with pytest.raises(ContextSafeError) as raised:
        preflight_source(source, evidence_scope)
    assert raised.value.code == expected_code
    assert str(source) not in str(raised.value)


def test_oversized_nonregular_and_final_symlink_sources_are_rejected(
    tmp_path: Path,
    evidence_source_json: dict[str, Any],
    evidence_scope: EvidenceScope,
) -> None:
    large = tmp_path / "large.json"
    large.write_bytes(b" " * (MAX_EVIDENCE_BYTES + 1))
    with pytest.raises(ContextSafeError) as raised:
        preflight_source(large, evidence_scope)
    assert raised.value.code == "input_too_large"

    with pytest.raises(ContextSafeError) as raised:
        preflight_source(tmp_path, evidence_scope)
    assert raised.value.code == "input_path_unsafe"

    target = _write_source(tmp_path / "target.json", evidence_source_json)
    link = tmp_path / "link.json"
    link.symlink_to(target)
    with pytest.raises(ContextSafeError) as raised:
        preflight_source(link, evidence_scope)
    assert raised.value.code == "input_path_unsafe"


def test_source_metadata_change_fails_closed(
    tmp_path: Path,
    evidence_source_json: dict[str, Any],
    evidence_scope: EvidenceScope,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _write_source(tmp_path / "source.json", evidence_source_json)

    def changed(_file_descriptor: int, _expected: object) -> None:
        raise ContextSafeError(
            "source_mutated", "$", "evidence changed during its boundary check"
        )

    monkeypatch.setattr("contextsafe.preflight._assert_unchanged", changed)
    with pytest.raises(ContextSafeError) as raised:
        preflight_source(source, evidence_scope)
    assert raised.value.code == "source_mutated"


@pytest.mark.parametrize(
    ("source_type", "media_type", "expected_code"),
    [
        ("fhir_r4_json", CANONICAL_JSON_MEDIA_TYPE, "unsupported_source_type"),
        (CANONICAL_JSON_SOURCE_TYPE, "application/json", "unsupported_media_type"),
    ],
)
def test_only_the_reviewed_source_profile_is_enabled(
    execution_plan: ExecutionPlan,
    source_type: str,
    media_type: str,
    expected_code: str,
) -> None:
    with pytest.raises(ContextSafeError) as raised:
        build_evidence_scope(
            execution_plan,
            case_token=execution_plan.case_tokens[0],
            checkpoint="ehr",
            source_type=source_type,
            media_type=media_type,
        )
    assert raised.value.code == expected_code


def test_cli_preflight_is_read_only_and_marks_unsigned_limit(
    tmp_path: Path,
    evidence_source_json: dict[str, Any],
    execution_plan: ExecutionPlan,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = _write_source(tmp_path / "source.json", evidence_source_json)
    plan = _write_source(tmp_path / "plan.json", execution_plan.to_dict())
    exit_code = main(
        [
            "evidence",
            "preflight",
            "--source",
            str(source),
            "--plan",
            str(plan),
            "--case-token",
            "CSYN-CTP-I01",
            "--checkpoint",
            "ehr",
            "--source-type",
            CANONICAL_JSON_SOURCE_TYPE,
            "--media-type",
            CANONICAL_JSON_MEDIA_TYPE,
        ]
    )
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert exit_code == 0
    assert captured.err == ""
    assert result["persisted"] is False
    assert "unsigned-plan-cannot-authorize-evidence-import" in result["limitations"]
    assert {item.name for item in tmp_path.iterdir()} == {"source.json", "plan.json"}


def test_cli_rejection_never_echoes_source_content(
    tmp_path: Path,
    evidence_source_json: dict[str, Any],
    execution_plan: ExecutionPlan,
    capsys: pytest.CaptureFixture[str],
) -> None:
    canary = "CTXSAFE-PHI-CANARY-ALICE"
    evidence_source_json["records"][0]["value_code"] = canary
    source = _write_source(tmp_path / "source.json", evidence_source_json)
    plan = _write_source(tmp_path / "plan.json", execution_plan.to_dict())
    assert (
        main(
            [
                "evidence",
                "preflight",
                "--source",
                str(source),
                "--plan",
                str(plan),
                "--case-token",
                "CSYN-CTP-I01",
                "--checkpoint",
                "ehr",
                "--source-type",
                CANONICAL_JSON_SOURCE_TYPE,
                "--media-type",
                CANONICAL_JSON_MEDIA_TYPE,
            ]
        )
        == 2
    )
    captured = capsys.readouterr()
    assert json.loads(captured.err)["error"]["code"] == "phi_canary_detected"
    assert canary not in captured.err
    assert captured.out == ""


def test_second_pass_hash_mismatch_and_seek_failure_are_stable(
    tmp_path: Path,
    evidence_source_json: dict[str, Any],
    evidence_scope: EvidenceScope,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path = _write_source(tmp_path / "source.json", evidence_source_json)
    destination = os.open(tmp_path / "stage", os.O_WRONLY | os.O_CREAT, 0o600)
    try:
        with open_preflighted_source(source_path, evidence_scope) as source:
            source.result = replace(source.result, raw_sha256="0" * 64)
            with pytest.raises(ContextSafeError) as raised:
                source.copy_to(destination)
            assert raised.value.code == "source_mutated"

        with open_preflighted_source(source_path, evidence_scope) as source:
            monkeypatch.setattr(
                preflight_module.os,
                "lseek",
                lambda *_args: (_ for _ in ()).throw(OSError("injected")),
            )
            with pytest.raises(ContextSafeError) as raised:
                source.copy_to(destination)
            assert raised.value.code == "input_not_seekable"
    finally:
        os.close(destination)


def test_low_level_io_failures_remain_value_minimized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case_value = "CSYN-CTP-I01"
    scope = EvidenceScope(
        plan_id="PLAN-SYNTHETIC-TEST",
        case_token=case_value,
        case_id="CTP-I01",
        checkpoint=Checkpoint.EHR,
        source_type=CANONICAL_JSON_SOURCE_TYPE,
        media_type=CANONICAL_JSON_MEDIA_TYPE,
        valid_from=date(2026, 7, 13),
        valid_until=date(2026, 8, 1),
    )
    with pytest.raises(ContextSafeError) as raised:
        preflight_source(tmp_path / "missing.json", scope)
    assert raised.value.code == "input_io_error"

    with pytest.raises(ContextSafeError) as raised:
        preflight_module._descriptor_metadata(-1)
    assert raised.value.code == "input_io_error"

    monkeypatch.setattr(preflight_module.os, "write", lambda *_args: 0)
    with pytest.raises(ContextSafeError) as raised:
        preflight_module._write_all(-1, b"bounded")
    assert raised.value.code == "evidence_store_io_error"


def test_source_inspection_failure_closes_the_new_descriptor(
    tmp_path: Path,
    evidence_scope: EvidenceScope,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _write_source(tmp_path / "source.json", {})
    original_open = os.open
    opened: list[int] = []
    primary = ContextSafeError(
        "input_io_error", "$", "injected descriptor inspection failure"
    )

    def recording_open(*args: Any, **kwargs: Any) -> int:
        descriptor = original_open(*args, **kwargs)
        opened.append(descriptor)
        return descriptor

    def fail_inspection(_file_descriptor: int) -> Any:
        raise primary

    monkeypatch.setattr(preflight_module.os, "open", recording_open)
    monkeypatch.setattr(preflight_module, "_descriptor_metadata", fail_inspection)

    with pytest.raises(ContextSafeError) as raised:
        preflight_source(source, evidence_scope)

    assert raised.value is primary
    assert len(opened) == 1
    with pytest.raises(OSError):
        os.fstat(opened[0])


def test_source_close_failure_preserves_a_primary_boundary_error(
    tmp_path: Path,
    evidence_scope: EvidenceScope,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _write_source(tmp_path / "source.json", {})
    original_close = os.close
    descriptors: list[int] = []
    primary = ContextSafeError("primary_rejection", "$", "injected primary rejection")

    def reject_source(*_args: Any, **_kwargs: Any) -> Any:
        raise primary

    def deny_close(file_descriptor: int) -> None:
        descriptors.append(file_descriptor)
        raise OSError("injected source descriptor close failure")

    try:
        with monkeypatch.context() as scoped_patch:
            scoped_patch.setattr(
                preflight_module, "parse_evidence_source", reject_source
            )
            scoped_patch.setattr(preflight_module.os, "close", deny_close)
            with pytest.raises(ContextSafeError) as raised:
                preflight_source(source, evidence_scope)
        assert raised.value is primary
        assert len(descriptors) == 1
    finally:
        for descriptor in descriptors:
            original_close(descriptor)


def test_source_close_failure_without_primary_is_structured(
    tmp_path: Path,
    evidence_source_json: dict[str, Any],
    evidence_scope: EvidenceScope,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _write_source(tmp_path / "source.json", evidence_source_json)
    original_close = os.close

    def close_then_fail(file_descriptor: int) -> None:
        original_close(file_descriptor)
        raise OSError("injected source descriptor close failure")

    monkeypatch.setattr(preflight_module.os, "close", close_then_fail)
    with pytest.raises(ContextSafeError) as raised:
        preflight_source(source, evidence_scope)

    assert raised.value.code == "input_io_error"
    assert raised.value.message == "evidence source descriptor could not be closed"
    assert isinstance(raised.value.__cause__, OSError)


def test_first_pass_detects_growth_and_read_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "large"
    path.write_bytes(b"x" * (MAX_EVIDENCE_BYTES + 1))
    descriptor = os.open(path, os.O_RDONLY)
    try:
        with pytest.raises(ContextSafeError) as raised:
            preflight_module._read_first_pass(descriptor)
        assert raised.value.code == "input_too_large"
    finally:
        os.close(descriptor)

    monkeypatch.setattr(
        preflight_module.os,
        "read",
        lambda *_args: (_ for _ in ()).throw(OSError("injected")),
    )
    with pytest.raises(ContextSafeError) as raised:
        preflight_module._read_first_pass(-1)
    assert raised.value.code == "input_io_error"


def test_platform_without_nofollow_fails_before_open(
    tmp_path: Path,
    evidence_source_json: dict[str, Any],
    evidence_scope: EvidenceScope,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _write_source(tmp_path / "source.json", evidence_source_json)
    monkeypatch.setattr(preflight_module, "_NOFOLLOW", 0)
    with pytest.raises(ContextSafeError) as raised:
        preflight_source(source, evidence_scope)
    assert raised.value.code == "input_path_unsupported"
