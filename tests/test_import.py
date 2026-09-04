"""The canonical JSON importer and the registry the adapters will share (B-022).

Four things this module pins. The conversion is exact: one record, one
observation, the source's tokens verbatim, the source's digest and pointer
on every observation, and the document validates against the published
observation-set contract and parses with the runtime the same way. The
conversion is whole: an unmapped field code, an untyped value, or an
identifier outside the synthetic namespace rejects the source and produces
nothing, and the rejection names a location and never a value. The
conversion is read-only: it opens the source through the evidence boundary
and writes, copies, indexes, and logs nothing. And the conversion does not
claim what it cannot: evaluating an imported token against the reference
rule set reports ``semantic_mismatch``, no result carries ``profile_reviewed``,
and the mapping is an identity over concepts, so nothing here can derive one
concept from another.
"""

import copy
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from jsonschema import Draft202012Validator

import contextsafe.preflight as preflight_module
from contextsafe.canonical import canonical_json
from contextsafe.cli import EXIT_CONTRACT_ERROR, EXIT_SUCCESS, EXIT_USAGE_ERROR, main
from contextsafe.errors import ContextSafeError
from contextsafe.evaluator import evaluate
from contextsafe.importers import (
    REGISTRY,
    ImportErrorCode,
    ImportResult,
    ImportWarningCode,
    available_formats,
    checkpoint_value,
    import_source,
    importer_for,
)
from contextsafe.importers.canonical_json import (
    _FIELD_CODE_CONCEPTS,
    CANONICAL_JSON_FORMAT,
    CANONICAL_JSON_MAPPING_VERSION,
    UNBOUND_CODE_SYSTEM,
    UNBOUND_SOURCE,
    convert_scanned,
)
from contextsafe.jsonio import parse_json_bytes
from contextsafe.models import Checkpoint, ConceptKind, SyntheticCase
from contextsafe.preflight import MAX_EVIDENCE_BYTES, ScannedSource
from contextsafe.receipt import build_receipt, render_receipt
from contextsafe.reference_fixtures import REFERENCE_ROOT
from contextsafe.validation import parse_bundle, parse_case, parse_observations

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = REFERENCE_ROOT
OBSERVATION_SET_SCHEMA = json.loads(
    (ROOT / "schemas" / "contextsafe-observation-set-v0.1.schema.json").read_text(
        encoding="utf-8"
    )
)
_LAB_FIELD_CODES = ("abnormal_flag", "order", "reference_range", "result", "status")
"""Field codes the envelope admits and the observation contract has no concept for."""


def _write(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value, separators=(",", ":")), encoding="utf-8")
    return path


def _record(
    field_code: str,
    value_code: str | None,
    context_code: str | None,
    index: int,
) -> dict[str, Any]:
    return {
        "field_code": field_code,
        "value_code": value_code,
        "context_code": context_code,
        "source_pointer": f"$.records[{index}]",
    }


def _scanned(value: object) -> ScannedSource:
    raw = canonical_json(json.loads(json.dumps(value))).encode("utf-8")
    return ScannedSource(
        raw_sha256=hashlib.sha256(raw).hexdigest(),
        raw_byte_count=len(raw),
        value=parse_json_bytes(raw),
    )


@pytest.fixture
def case(case_json: dict[str, Any]) -> SyntheticCase:
    return parse_case(case_json)


@pytest.fixture
def four_concept_source(evidence_source_json: dict[str, Any]) -> dict[str, Any]:
    """One record for each concept the importer converts."""

    evidence_source_json["records"] = [
        _record("gender_identity", "CSYN-GI-TOKEN", None, 0),
        _record("recorded_sex_or_gender", "X", "CSYN-GOVERNMENT-ID", 1),
        _record("name_to_use", "CSYN-ASTER", None, 2),
        _record("pronouns", "CSYN-PRONOUN-THEY-THEM", "CSYN-EHR-DISPLAY", 3),
    ]
    return evidence_source_json


def _import_args(source: Path, case_path: Path, checkpoint: str = "ehr") -> list[str]:
    return [
        "import",
        "--format",
        CANONICAL_JSON_FORMAT,
        "--source",
        str(source),
        "--case",
        str(case_path),
        "--checkpoint",
        checkpoint,
    ]


def _assert_rejected(
    source_value: object, case: SyntheticCase, expected_code: str
) -> ContextSafeError:
    with pytest.raises(ContextSafeError) as raised:
        convert_scanned(_scanned(source_value), case=case, checkpoint=Checkpoint.EHR)
    assert raised.value.code == expected_code
    return raised.value


# --- the reference round trip -------------------------------------------------


def test_reference_source_round_trips_to_one_token_carrying_observation(
    case: SyntheticCase,
) -> None:
    source = REFERENCE / "evidence-source.json"
    raw = source.read_bytes()
    result = import_source(
        CANONICAL_JSON_FORMAT, source, case=case, checkpoint=Checkpoint.EHR
    )

    assert result.record_count == 1
    assert len(result.observations) == 1
    observation = result.observations[0]
    assert observation.concept is ConceptKind.PRONOUNS
    assert observation.case_id == "CTP-I01"
    assert observation.checkpoint is Checkpoint.EHR
    assert observation.value.to_dict() == {
        "status": "specified",
        "value": "CSYN-PRONOUN-THEY-THEM",
    }
    assert observation.evidence.source_sha256 == hashlib.sha256(raw).hexdigest()
    assert observation.evidence.source_pointer == "$.records[0]"
    assert observation.mapping.mapping_version == CANONICAL_JSON_MAPPING_VERSION
    assert observation.mapping.source_concept is observation.mapping.target_concept
    assert result.source_sha256 == observation.evidence.source_sha256
    assert result.source_byte_count == len(raw)
    assert result.profile_reviewed is False
    assert set(result.warnings) == {
        ImportWarningCode.MAPPING_PROFILE_NOT_BOUND,
        ImportWarningCode.PLAN_BINDING_NOT_CHECKED,
    }
    report = result.to_dict()
    assert report["persisted"] is False
    assert report["profile_reviewed"] is False
    assert report["observation_count"] == report["record_count"] == 1


def test_imported_document_is_exactly_what_evaluate_accepts(
    case: SyntheticCase,
    case_json: dict[str, Any],
    rules_json: dict[str, Any],
) -> None:
    """Contract and runtime agree on the emitted shape, and evaluate runs on it."""

    result = import_source(
        CANONICAL_JSON_FORMAT,
        REFERENCE / "evidence-source.json",
        case=case,
        checkpoint=Checkpoint.EHR,
    )
    document = result.observation_set()
    Draft202012Validator.check_schema(OBSERVATION_SET_SCHEMA)
    Draft202012Validator(OBSERVATION_SET_SCHEMA).validate(document)
    assert [item.to_dict() for item in parse_observations(document)] == document[
        "observations"
    ]
    assert set(document) == {"observations", "schema_version"}
    bundle = parse_bundle(case_json, document, rules_json)
    assert len(bundle.observations) == 1


def test_an_unbound_token_evaluates_as_semantic_mismatch_not_pass(
    case: SyntheticCase,
    case_json: dict[str, Any],
    rules_json: dict[str, Any],
) -> None:
    """A-033: the token is carried, not normalized to the value the rule expects.

    ``CSYN-PRONOUN-THEY-THEM`` is not ``they/them`` until a mapping profile
    says so, and none has. The correct report is a mismatch, and the four
    rules with no imported observation stay indeterminate rather than pass.
    """

    result = import_source(
        CANONICAL_JSON_FORMAT,
        REFERENCE / "evidence-source.json",
        case=case,
        checkpoint=Checkpoint.EHR,
    )
    bundle = parse_bundle(case_json, result.observation_set(), rules_json)
    by_rule = {item.rule_id: item for item in evaluate(bundle)}
    assert by_rule["A-I05"].status.value == "fail"
    assert by_rule["A-I05"].reason.value == "semantic_mismatch"
    assert by_rule["A-I05"].evidence_sha256s == (result.source_sha256,)
    for rule_id in ("A-I01", "A-I02", "A-I03", "A-I04"):
        assert by_rule[rule_id].status.value == "indeterminate"
        assert by_rule[rule_id].reason.value == "missing_evidence"
    assert not any(item.status.value == "pass" for item in by_rule.values())


# --- every concept the closed mapping converts -------------------------------


def test_every_convertible_concept_is_typed_verbatim_and_validates(
    case: SyntheticCase, four_concept_source: dict[str, Any]
) -> None:
    result = convert_scanned(
        _scanned(four_concept_source), case=case, checkpoint=Checkpoint.EHR
    )
    Draft202012Validator(OBSERVATION_SET_SCHEMA).validate(result.observation_set())
    values = {item.concept: item.value.to_dict() for item in result.observations}
    assert values == {
        ConceptKind.GENDER_IDENTITY: {
            "code_system": UNBOUND_CODE_SYSTEM,
            "status": "specified",
            "value": "CSYN-GI-TOKEN",
        },
        ConceptKind.RECORDED_SEX_OR_GENDER: {
            "context": "CSYN-GOVERNMENT-ID",
            "source": UNBOUND_SOURCE,
            "value": "X",
        },
        ConceptKind.NAME_TO_USE: {
            "status": "specified",
            "use": "usual",
            "value": "CSYN-ASTER",
        },
        ConceptKind.PRONOUNS: {
            "status": "specified",
            "value": "CSYN-PRONOUN-THEY-THEM",
        },
    }
    ids = [item.observation_id for item in result.observations]
    assert ids == [f"OBS-CTP-I01-R{index:04d}" for index in range(4)]
    assert all(
        item.evidence.source_sha256 == result.source_sha256
        for item in result.observations
    )
    assert [item.evidence.source_pointer for item in result.observations] == [
        f"$.records[{index}]" for index in range(4)
    ]


@pytest.mark.parametrize("field_code", ["gender_identity", "name_to_use", "pronouns"])
@pytest.mark.parametrize("status", ["declined", "unknown", "absent"])
def test_presence_states_carry_no_value(
    case: SyntheticCase,
    evidence_source_json: dict[str, Any],
    field_code: str,
    status: str,
) -> None:
    evidence_source_json["records"] = [_record(field_code, status, None, 0)]
    result = convert_scanned(
        _scanned(evidence_source_json), case=case, checkpoint=Checkpoint.EHR
    )
    value = result.observations[0].value.to_dict()
    assert value["status"] == status
    assert value["value"] is None


def test_imported_values_are_not_replaced_by_the_case_manifest(
    case: SyntheticCase, evidence_source_json: dict[str, Any]
) -> None:
    """The case document is a cross-check, never a source of observed values."""

    evidence_source_json["records"] = [_record("name_to_use", "CSYN-OTHER", None, 0)]
    result = convert_scanned(
        _scanned(evidence_source_json), case=case, checkpoint=Checkpoint.EHR
    )
    observed = result.observations[0].value.to_dict()
    assert observed["value"] == "CSYN-OTHER"
    assert observed != case.name_to_use.to_dict()


# --- rejections: whole source, category and location, never content ----------


@pytest.mark.parametrize("field_code", _LAB_FIELD_CODES)
def test_an_envelope_field_code_outside_the_mapping_rejects_the_source(
    case: SyntheticCase, evidence_source_json: dict[str, Any], field_code: str
) -> None:
    evidence_source_json["records"].append(_record(field_code, "final", None, 1))
    error = _assert_rejected(
        evidence_source_json, case, ImportErrorCode.FIELD_CODE_UNMAPPED.value
    )
    assert error.path == "$.records[1].field_code"


def test_a_field_code_outside_the_envelope_enum_rejects_the_source(
    case: SyntheticCase, evidence_source_json: dict[str, Any]
) -> None:
    evidence_source_json["records"][0]["field_code"] = "legal_sex"
    error = _assert_rejected(evidence_source_json, case, "invalid_enum")
    assert "legal_sex" not in str(error)


def test_spcu_records_reject_rather_than_arrive_without_their_support_link(
    case: SyntheticCase, evidence_source_json: dict[str, Any]
) -> None:
    evidence_source_json["records"] = [
        _record("sex_parameter_for_clinical_use", "CSYN-CONTEXT-1", "ORDER-CSYN-1", 0)
    ]
    error = _assert_rejected(
        evidence_source_json, case, ImportErrorCode.CONCEPT_NOT_CONVERTIBLE.value
    )
    assert error.path == "$.records[0].field_code"


@pytest.mark.parametrize(
    ("record", "expected_code"),
    [
        (
            _record("pronouns", None, None, 0),
            ImportErrorCode.VALUE_MISSING.value,
        ),
        (
            _record("gender_identity", "specified", None, 0),
            ImportErrorCode.VALUE_AMBIGUOUS.value,
        ),
        (
            _record("recorded_sex_or_gender", None, "CSYN-GOVERNMENT-ID", 0),
            ImportErrorCode.VALUE_MISSING.value,
        ),
        (
            _record("recorded_sex_or_gender", "X", None, 0),
            ImportErrorCode.CONTEXT_MISSING.value,
        ),
        (
            _record("recorded_sex_or_gender", "declined", "CSYN-ID", 0),
            "invalid_rsg_value",
        ),
        (
            _record("recorded_sex_or_gender", "CSYN-NB", "CSYN-ID", 0),
            "invalid_rsg_value",
        ),
        (_record("name_to_use", "F", None, 0), "non_synthetic_name"),
        (
            _record("recorded_sex_or_gender", "X", "CSYN-" + "A" * 96, 0),
            "invalid_format",
        ),
    ],
    ids=[
        "null-value",
        "specified-without-value",
        "rsg-null-value",
        "rsg-without-context",
        "rsg-presence-code",
        "rsg-synthetic-token",
        "name-not-synthetic",
        "context-over-observation-bound",
    ],
)
def test_untyped_or_unsupported_values_reject_instead_of_normalizing(
    case: SyntheticCase,
    evidence_source_json: dict[str, Any],
    record: dict[str, Any],
    expected_code: str,
) -> None:
    """A-033 and fail-closed: no closest supported value, no dropped record."""

    evidence_source_json["records"] = [record]
    _assert_rejected(evidence_source_json, case, expected_code)


def test_one_bad_record_rejects_a_source_with_good_records(
    case: SyntheticCase, four_concept_source: dict[str, Any]
) -> None:
    four_concept_source["records"].insert(2, _record("result", "normal", None, 9))
    _assert_rejected(
        four_concept_source, case, ImportErrorCode.FIELD_CODE_UNMAPPED.value
    )


def test_case_token_outside_the_case_document_rejects(
    case: SyntheticCase, evidence_source_json: dict[str, Any]
) -> None:
    other_case = "CSYN-CTP-Z99"
    evidence_source_json["case_token"] = other_case
    evidence_source_json["synthetic_identifier"]["value"] = other_case
    error = _assert_rejected(
        evidence_source_json, case, ImportErrorCode.CASE_MISMATCH.value
    )
    assert error.path == "$.case_token"


def test_identifier_that_contradicts_the_envelope_rejects(
    case: SyntheticCase, evidence_source_json: dict[str, Any]
) -> None:
    evidence_source_json["synthetic_identifier"]["value"] = "CSYN-CTP-Z99"
    _assert_rejected(evidence_source_json, case, "namespace_mismatch")
    evidence_source_json["synthetic_identifier"]["value"] = "CSYN-CTP-I01"
    evidence_source_json["synthetic_identifier"]["system"] = "urn:example:real"
    _assert_rejected(evidence_source_json, case, "namespace_mismatch")


def test_checkpoint_other_than_requested_rejects(
    case: SyntheticCase, evidence_source_json: dict[str, Any]
) -> None:
    with pytest.raises(ContextSafeError) as raised:
        convert_scanned(
            _scanned(evidence_source_json), case=case, checkpoint=Checkpoint.INTERFACE
        )
    assert raised.value.code == ImportErrorCode.CHECKPOINT_MISMATCH.value
    assert raised.value.path == "$.checkpoint"


@pytest.mark.parametrize("value", ["production", "", 3, None, "EHR"])
def test_unsupported_checkpoint_names_fail_closed(value: object) -> None:
    with pytest.raises(ContextSafeError) as raised:
        checkpoint_value(value, "$.checkpoint")
    assert raised.value.code in {"unsupported_checkpoint", "invalid_string"}


def test_record_count_bounds_are_the_envelope_bounds(
    case: SyntheticCase, evidence_source_json: dict[str, Any]
) -> None:
    template = evidence_source_json["records"][0]
    evidence_source_json["records"] = [
        {**template, "source_pointer": f"$.records[{index}]"} for index in range(2000)
    ]
    result = convert_scanned(
        _scanned(evidence_source_json), case=case, checkpoint=Checkpoint.EHR
    )
    assert result.record_count == len(result.observations) == 2000
    assert result.observations[-1].observation_id == "OBS-CTP-I01-R1999"
    evidence_source_json["records"].append(
        {**template, "source_pointer": "$.records[2000]"}
    )
    _assert_rejected(evidence_source_json, case, "invalid_record_count")


# --- the boundary scan runs first, on the file, through one descriptor --------


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        (
            lambda value: value["records"][0].update(
                {"value_code": "CTXSAFE-PHI-CANARY-ALICE"}
            ),
            "phi_canary_detected",
        ),
        (
            lambda value: value["records"][0].update(
                {"value_code": "person@example.invalid"}
            ),
            "direct_identifier_detected",
        ),
        (lambda value: value.update({"note": "prohibited"}), "prohibited_field"),
        (lambda value: value.update({"unexpected": True}), "unknown_field"),
    ],
)
def test_boundary_rejections_reach_the_importer_unchanged(
    tmp_path: Path,
    case: SyntheticCase,
    evidence_source_json: dict[str, Any],
    mutation: Any,
    expected_code: str,
) -> None:
    mutation(evidence_source_json)
    source = _write(tmp_path / "source.json", evidence_source_json)
    with pytest.raises(ContextSafeError) as raised:
        import_source(
            CANONICAL_JSON_FORMAT, source, case=case, checkpoint=Checkpoint.EHR
        )
    assert raised.value.code == expected_code
    assert "ALICE" not in str(raised.value)
    assert "example.invalid" not in str(raised.value)


def test_oversized_symlinked_and_unsupported_platform_sources_fail_closed(
    tmp_path: Path,
    case: SyntheticCase,
    evidence_source_json: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    large = tmp_path / "large.json"
    large.write_bytes(b" " * (MAX_EVIDENCE_BYTES + 1))
    with pytest.raises(ContextSafeError) as raised:
        import_source(
            CANONICAL_JSON_FORMAT, large, case=case, checkpoint=Checkpoint.EHR
        )
    assert raised.value.code == "input_too_large"

    target = _write(tmp_path / "target.json", evidence_source_json)
    link = tmp_path / "link.json"
    link.symlink_to(target)
    with pytest.raises(ContextSafeError) as raised:
        import_source(CANONICAL_JSON_FORMAT, link, case=case, checkpoint=Checkpoint.EHR)
    assert raised.value.code == "input_path_unsafe"

    monkeypatch.setattr(preflight_module, "_NOFOLLOW", 0)
    with pytest.raises(ContextSafeError) as raised:
        import_source(
            CANONICAL_JSON_FORMAT, target, case=case, checkpoint=Checkpoint.EHR
        )
    assert raised.value.code == "input_path_unsupported"


def test_scan_source_closes_its_descriptor_on_success_and_on_failure(
    tmp_path: Path,
    evidence_source_json: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_open = os.open
    opened: list[int] = []

    def recording_open(*args: Any, **kwargs: Any) -> int:
        descriptor = original_open(*args, **kwargs)
        opened.append(descriptor)
        return descriptor

    monkeypatch.setattr(preflight_module.os, "open", recording_open)
    source = _write(tmp_path / "source.json", evidence_source_json)
    scanned = preflight_module.scan_source(source)
    assert scanned.raw_byte_count == len(source.read_bytes())
    assert scanned.value == evidence_source_json

    broken = tmp_path / "broken.json"
    broken.write_bytes(b"{")
    with pytest.raises(ContextSafeError) as raised:
        preflight_module.scan_source(broken)
    assert raised.value.code == "invalid_json"
    assert len(opened) == 2
    for descriptor in opened:
        with pytest.raises(OSError):
            os.fstat(descriptor)


# --- the command line ---------------------------------------------------------


def test_cli_import_is_read_only_and_emits_the_observation_set(
    tmp_path: Path,
    case_json: dict[str, Any],
    evidence_source_json: dict[str, Any],
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    source = _write(tmp_path / "source.json", evidence_source_json)
    case_path = _write(tmp_path / "case.json", case_json)
    before = source.read_bytes()

    assert main(_import_args(source, case_path)) == EXIT_SUCCESS

    captured = capsys.readouterr()
    assert captured.err == ""
    document = json.loads(captured.out)
    assert document["schema_version"] == "contextsafe.observation-set/0.1.0"
    assert document["observations"][0]["value"]["value"] == "CSYN-PRONOUN-THEY-THEM"
    assert {item.name for item in tmp_path.iterdir()} == {"source.json", "case.json"}
    assert source.read_bytes() == before


def test_cli_output_file_matches_stdout_and_honours_quiet(
    tmp_path: Path,
    case_json: dict[str, Any],
    evidence_source_json: dict[str, Any],
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = _write(tmp_path / "source.json", evidence_source_json)
    case_path = _write(tmp_path / "case.json", case_json)
    assert main(_import_args(source, case_path)) == EXIT_SUCCESS
    printed = capsys.readouterr().out

    output = tmp_path / "observations.json"
    assert (
        main([*_import_args(source, case_path), "--quiet", "--output", str(output)])
        == EXIT_SUCCESS
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
    assert output.read_bytes() == printed.encode("utf-8")
    assert printed.endswith("\n") and printed.count("\n") == 1


def test_cli_imported_document_evaluates_with_the_reference_rules(
    tmp_path: Path,
    case_json: dict[str, Any],
    evidence_source_json: dict[str, Any],
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = _write(tmp_path / "source.json", evidence_source_json)
    case_path = _write(tmp_path / "case.json", case_json)
    output = tmp_path / "observations.json"
    assert (
        main([*_import_args(source, case_path), "--output", str(output)])
        == EXIT_SUCCESS
    )
    assert (
        main(
            [
                "evaluate",
                "--case",
                str(case_path),
                "--observations",
                str(output),
                "--rules",
                str(REFERENCE / "rules.json"),
            ]
        )
        == EXIT_SUCCESS
    )
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["payload"]["summary"] == {
        "blocked": 0,
        "fail": 1,
        "indeterminate": 4,
        "not_applicable": 0,
        "pass": 0,
    }


def test_cli_rejection_is_one_json_error_without_source_content(
    tmp_path: Path,
    case_json: dict[str, Any],
    evidence_source_json: dict[str, Any],
    capsys: pytest.CaptureFixture[str],
) -> None:
    evidence_source_json["records"].append(
        _record("result", "CSYN-SECRET-VALUE", None, 1)
    )
    source = _write(tmp_path / "source.json", evidence_source_json)
    case_path = _write(tmp_path / "case.json", case_json)
    output = tmp_path / "observations.json"

    assert (
        main([*_import_args(source, case_path), "--output", str(output)])
        == EXIT_CONTRACT_ERROR
    )

    captured = capsys.readouterr()
    assert captured.out == ""
    error = json.loads(captured.err)["error"]
    assert error["code"] == ImportErrorCode.FIELD_CODE_UNMAPPED.value
    assert error["path"] == "$.records[1].field_code"
    assert "CSYN-SECRET-VALUE" not in captured.err
    assert str(tmp_path) not in captured.err
    assert not output.exists()


def test_cli_checkpoint_mismatch_and_unsupported_checkpoint(
    tmp_path: Path,
    case_json: dict[str, Any],
    evidence_source_json: dict[str, Any],
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = _write(tmp_path / "source.json", evidence_source_json)
    case_path = _write(tmp_path / "case.json", case_json)
    assert main(_import_args(source, case_path, "interface")) == EXIT_CONTRACT_ERROR
    assert json.loads(capsys.readouterr().err)["error"]["code"] == (
        ImportErrorCode.CHECKPOINT_MISMATCH.value
    )
    assert main(_import_args(source, case_path, "production")) == EXIT_CONTRACT_ERROR
    assert json.loads(capsys.readouterr().err)["error"]["code"] == (
        "unsupported_checkpoint"
    )


def test_cli_unknown_format_is_a_usage_error_before_any_file_opens(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = _import_args(tmp_path / "absent.json", tmp_path / "absent-case.json")
    args[2] = "fhir-r4-json"
    with pytest.raises(SystemExit) as raised:
        main(args)
    assert raised.value.code == EXIT_USAGE_ERROR
    assert "invalid choice" in capsys.readouterr().err


def test_cli_log_dir_records_the_command_and_outcome_only(
    tmp_path: Path,
    case_json: dict[str, Any],
    evidence_source_json: dict[str, Any],
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = _write(tmp_path / "source.json", evidence_source_json)
    case_path = _write(tmp_path / "case.json", case_json)
    log_dir = tmp_path / "log"
    assert (
        main([*_import_args(source, case_path), "--quiet", "--log-dir", str(log_dir)])
        == EXIT_SUCCESS
    )
    assert capsys.readouterr().err == ""
    records = [
        json.loads(line)
        for path in log_dir.iterdir()
        for line in path.read_text(encoding="utf-8").splitlines()
    ]
    assert len(records) == 1
    assert records[0]["command"] == "import"
    assert records[0]["outcome"] == "accepted"
    assert "CSYN" not in json.dumps(records)
    assert str(tmp_path) not in json.dumps(records)


def test_cli_reports_output_failure(
    tmp_path: Path,
    case_json: dict[str, Any],
    evidence_source_json: dict[str, Any],
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = _write(tmp_path / "source.json", evidence_source_json)
    case_path = _write(tmp_path / "case.json", case_json)
    assert (
        main([*_import_args(source, case_path), "--output", str(tmp_path)])
        == EXIT_CONTRACT_ERROR
    )
    assert json.loads(capsys.readouterr().err)["error"]["code"] == "output_io_error"


# --- the registry and the shared result -------------------------------------


def test_registry_is_read_only_and_names_the_command_line_choices() -> None:
    assert available_formats() == (CANONICAL_JSON_FORMAT,)
    importer = importer_for(CANONICAL_JSON_FORMAT)
    assert importer is REGISTRY[CANONICAL_JSON_FORMAT]
    assert importer.format_name == CANONICAL_JSON_FORMAT
    assert importer.mapping_version == CANONICAL_JSON_MAPPING_VERSION
    with pytest.raises(TypeError):
        REGISTRY["fhir-r4-json"] = REGISTRY[CANONICAL_JSON_FORMAT]  # type: ignore[index]
    for name in ("fhir-r4-json", "", None, 1):
        with pytest.raises(ContextSafeError) as raised:
            importer_for(name)
        assert raised.value.code in {
            ImportErrorCode.FORMAT_UNSUPPORTED.value,
            "invalid_string",
        }


def test_every_importer_rejection_code_is_in_the_family() -> None:
    assert all(code.value.startswith("import_") for code in ImportErrorCode)
    assert len({code.value for code in ImportErrorCode}) == len(ImportErrorCode)


def test_the_field_code_mapping_is_an_identity_over_concepts() -> None:
    """No field code may arrive at a concept other than the one it names.

    That is the structural form of the rule that GI and RSG never become
    SPCU: the mapping cannot express it, so no profile-free path can either.
    """

    assert set(_FIELD_CODE_CONCEPTS) == {item.value for item in ConceptKind}
    for field_code, concept in _FIELD_CODE_CONCEPTS.items():
        assert field_code == concept.value


def test_a_result_cannot_claim_a_reviewed_profile_or_a_partial_count(
    case: SyntheticCase,
) -> None:
    result = import_source(
        CANONICAL_JSON_FORMAT,
        REFERENCE / "evidence-source.json",
        case=case,
        checkpoint=Checkpoint.EHR,
    )
    fields = {
        "format_name": result.format_name,
        "mapping_version": result.mapping_version,
        "source_sha256": result.source_sha256,
        "source_byte_count": result.source_byte_count,
        "observations": result.observations,
        "warnings": result.warnings,
    }
    with pytest.raises(ContextSafeError) as raised:
        ImportResult(**fields, record_count=1, profile_reviewed=True)
    assert raised.value.code == "profile_review_not_available"
    with pytest.raises(ContextSafeError) as raised:
        ImportResult(**fields, record_count=2)
    assert raised.value.code == "import_count_mismatch"
    with pytest.raises((AttributeError, TypeError)):
        result.profile_reviewed = True  # type: ignore[misc]


# --- properties ---------------------------------------------------------------

_TOKEN_SUFFIX = st.text(alphabet="ABCDEFGH0123456789", min_size=1, max_size=8)
_CHECKPOINTS = st.sampled_from(tuple(Checkpoint))


@st.composite
def _convertible_record(draw: st.DrawFn, index: int) -> dict[str, Any]:
    field_code = draw(
        st.sampled_from(
            ("gender_identity", "name_to_use", "pronouns", "recorded_sex_or_gender")
        )
    )
    context = draw(st.one_of(st.none(), _TOKEN_SUFFIX.map(lambda s: f"CSYN-CTX-{s}")))
    if field_code == "recorded_sex_or_gender":
        value = draw(st.sampled_from(("F", "M", "X", "unknown")))
        context = context or "CSYN-CTX-DEFAULT"
    else:
        value = draw(
            st.one_of(
                st.sampled_from(("declined", "unknown", "absent")),
                _TOKEN_SUFFIX.map(lambda s: f"CSYN-VAL-{s}"),
            )
        )
    return _record(field_code, value, context, index)


@st.composite
def _envelopes(draw: st.DrawFn) -> tuple[dict[str, Any], Checkpoint]:
    checkpoint = draw(_CHECKPOINTS)
    count = draw(st.integers(min_value=1, max_value=6))
    template = json.loads(
        (REFERENCE / "evidence-source.json").read_text(encoding="utf-8")
    )
    template["checkpoint"] = checkpoint.value
    template["records"] = [draw(_convertible_record(index)) for index in range(count)]
    return template, checkpoint


_CASE = parse_case(json.loads((REFERENCE / "case.json").read_text(encoding="utf-8")))
_CASE_JSON = json.loads((REFERENCE / "case.json").read_text(encoding="utf-8"))


def _rules_for(checkpoint: Checkpoint) -> dict[str, Any]:
    """One required rule per concept, expecting what the case manifest declares."""

    expected = {
        "gender_identity": _CASE.gender_identity.to_dict(),
        "recorded_sex_or_gender": _CASE.recorded_sex_or_gender[0].to_dict(),
        "name_to_use": _CASE.name_to_use.to_dict(),
        "pronouns": _CASE.pronouns.to_dict(),
    }
    return {
        "schema_version": "contextsafe.rule-set/0.1.0",
        "rules": [
            {
                "rule_id": f"A-I{index + 1:02d}",
                "version": "0.1.0",
                "case_id": _CASE.case_id,
                "checkpoint": checkpoint.value,
                "concept": concept,
                "expected": value,
                "required": True,
            }
            for index, (concept, value) in enumerate(sorted(expected.items()))
        ],
    }


@settings(max_examples=150, deadline=None)
@given(example=_envelopes())
def test_import_then_evaluate_is_deterministic(
    example: tuple[dict[str, Any], Checkpoint],
) -> None:
    """Same bytes in, same observation set and same receipt out, every time."""

    envelope, checkpoint = example
    first = convert_scanned(_scanned(envelope), case=_CASE, checkpoint=checkpoint)
    second = convert_scanned(
        _scanned(copy.deepcopy(envelope)), case=_CASE, checkpoint=checkpoint
    )
    assert canonical_json(first.observation_set()) == canonical_json(
        second.observation_set()
    )
    assert first.to_dict() == second.to_dict()
    rules = _rules_for(checkpoint)
    receipts = [
        render_receipt(build_receipt(bundle, evaluate(bundle)))
        for bundle in (
            parse_bundle(_CASE_JSON, first.observation_set(), rules),
            parse_bundle(_CASE_JSON, second.observation_set(), rules),
        )
    ]
    assert receipts[0] == receipts[1]
    assert all(
        item.evidence.source_sha256 == first.source_sha256
        for item in first.observations
    )
    for outcome in evaluate(parse_bundle(_CASE_JSON, first.observation_set(), rules)):
        if outcome.status.value == "pass":
            assert outcome.observed_sha256s == (outcome.expected_sha256,)


@settings(max_examples=150, deadline=None)
@given(
    example=_envelopes(),
    position=st.integers(min_value=0, max_value=6),
    field_code=st.one_of(
        st.sampled_from(_LAB_FIELD_CODES),
        st.text(min_size=1, max_size=24).filter(
            lambda s: s not in _FIELD_CODE_CONCEPTS
        ),
    ),
)
def test_any_unknown_field_code_rejects_the_whole_source(
    example: tuple[dict[str, Any], Checkpoint], position: int, field_code: str
) -> None:
    envelope, checkpoint = example
    records = envelope["records"]
    bad = _record(field_code, "CSYN-VAL-X", None, len(records))
    records.insert(min(position, len(records)), bad)
    with pytest.raises(ContextSafeError) as raised:
        convert_scanned(_scanned(envelope), case=_CASE, checkpoint=checkpoint)
    assert raised.value.code in {
        ImportErrorCode.FIELD_CODE_UNMAPPED.value,
        "invalid_enum",
        "invalid_string",
        "invalid_unicode",
    }
    assert field_code not in raised.value.message


@settings(max_examples=150, deadline=None)
@given(
    example=_envelopes(),
    identifier=st.one_of(
        st.sampled_from(("CTP-I01", "CSYN-CTP-Z99", "MRN-12345", "12345678", "")),
        st.text(min_size=1, max_size=24).filter(lambda s: s != "CSYN-CTP-I01"),
    ),
    system=st.sampled_from(("urn:contextsafe:synthetic", "urn:example:real")),
)
def test_any_non_synthetic_identifier_rejects_the_whole_source(
    example: tuple[dict[str, Any], Checkpoint], identifier: str, system: str
) -> None:
    envelope, checkpoint = example
    envelope["synthetic_identifier"] = {"system": system, "value": identifier}
    with pytest.raises(ContextSafeError) as raised:
        convert_scanned(_scanned(envelope), case=_CASE, checkpoint=checkpoint)
    assert raised.value.code in {
        "namespace_mismatch",
        "invalid_format",
        "invalid_string",
        "invalid_unicode",
        "invalid_type",
    }
    assert not identifier or identifier not in raised.value.message
