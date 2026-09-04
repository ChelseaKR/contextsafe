"""CLI behavior and value-minimizing error tests."""

import json
from pathlib import Path

import pytest

from contextsafe.cli import EXIT_USAGE_ERROR, main
from contextsafe.evidence import CANONICAL_JSON_MEDIA_TYPE, CANONICAL_JSON_SOURCE_TYPE
from contextsafe.plan import ExecutionPlan
from contextsafe.reference_fixtures import REFERENCE_ROOT

REFERENCE = REFERENCE_ROOT


def _args(command: str) -> list[str]:
    return [
        command,
        "--case",
        str(REFERENCE / "case.json"),
        "--observations",
        str(REFERENCE / "observations.json"),
        "--rules",
        str(REFERENCE / "rules.json"),
    ]


def _evidence_preflight_args(plan_path: Path) -> list[str]:
    return [
        "evidence",
        "preflight",
        "--source",
        str(REFERENCE / "evidence-source.json"),
        "--plan",
        str(plan_path),
        "--case-token",
        "CSYN-CTP-I01",
        "--checkpoint",
        "ehr",
        "--source-type",
        CANONICAL_JSON_SOURCE_TYPE,
        "--media-type",
        CANONICAL_JSON_MEDIA_TYPE,
    ]


def test_validate_cli_emits_machine_readable_summary(capsys: object) -> None:
    assert main(_args("validate")) == 0
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert report["valid"] is True
    assert report["observation_count"] == 5
    assert captured.err == ""


def _mismatched_observations_args(tmp_path: Path) -> list[str]:
    """The issue-22 reproduction: one pronoun observation the EHR contradicts."""

    observations = json.loads(
        (REFERENCE / "observations.json").read_text(encoding="utf-8")
    )
    observations["observations"][4]["value"]["value"] = "ze/hir"
    path = tmp_path / "mismatched-observations.json"
    path.write_text(json.dumps(observations), encoding="utf-8")
    args = _args("evaluate")
    args[4] = str(path)
    return args


def test_evaluate_default_exit_stays_zero_when_a_receipt_records_findings(
    tmp_path: Path, capsys: object
) -> None:
    """The documented contract is preserved: a receipt generator that ran.

    Issue #22 reports that ``evaluate`` exits 0 on a semantic mismatch. That
    remains true by default — this test pins it as the documented behaviour,
    not as an accident — while ``--fail-on finding`` becomes the opt-in gate.
    """

    assert main(_mismatched_observations_args(tmp_path)) == 0
    document = json.loads(capsys.readouterr().out)
    assert document["payload"]["summary"]["fail"] == 1
    assert document["payload"]["summary"]["pass"] == 4


def test_evaluate_fail_on_finding_exits_one_and_still_emits_the_receipt(
    tmp_path: Path, capsys: object
) -> None:
    args = [*_mismatched_observations_args(tmp_path), "--fail-on", "finding"]
    assert main(args) == 1
    captured = capsys.readouterr()
    document = json.loads(captured.out)
    assert document["payload"]["summary"]["fail"] == 1
    assert captured.err == ""


def test_evaluate_fail_on_finding_clean_fixture_exits_zero(capsys: object) -> None:
    assert main([*_args("evaluate"), "--fail-on", "finding"]) == 0
    document = json.loads(capsys.readouterr().out)
    assert document["payload"]["summary"]["fail"] == 0


def test_evaluate_fail_on_finding_writes_output_file_before_exiting_one(
    tmp_path: Path,
) -> None:
    output = tmp_path / "receipt.json"
    args = [
        *_mismatched_observations_args(tmp_path),
        "--fail-on",
        "finding",
        "--output",
        str(output),
    ]
    assert main(args) == 1
    document = json.loads(output.read_text(encoding="utf-8"))
    assert document["payload"]["summary"]["fail"] == 1


def test_evaluate_fail_on_finding_artifact_is_byte_identical_to_default(
    tmp_path: Path,
) -> None:
    default_path = tmp_path / "default.json"
    finding_path = tmp_path / "finding.json"
    assert (
        main([*_mismatched_observations_args(tmp_path), "--output", str(default_path)])
        == 0
    )
    assert (
        main(
            [
                *_mismatched_observations_args(tmp_path),
                "--output",
                str(finding_path),
                "--fail-on",
                "finding",
            ]
        )
        == 1
    )
    assert default_path.read_bytes() == finding_path.read_bytes()


def test_evaluate_rejects_unknown_fail_on_value(capsys: object) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main([*_args("evaluate"), "--fail-on", "sometimes"])
    assert excinfo.value.code == EXIT_USAGE_ERROR
    assert "invalid choice" in capsys.readouterr().err


def test_evaluate_cli_can_write_receipt(tmp_path: Path, capsys: object) -> None:
    output = tmp_path / "receipt.json"
    assert main([*_args("evaluate"), "--output", str(output)]) == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    document = json.loads(output.read_text(encoding="utf-8"))
    assert set(document) == {"envelope", "payload", "payload_sha256", "schema_version"}
    assert document["payload"]["summary"]["pass"] == 5
    assert document["envelope"]["claimed_generated_at"] is None
    assert document["envelope"]["signature_status"] == "not_signed"


def test_evaluate_cli_claimed_time_stays_outside_the_payload(
    tmp_path: Path, capsys: object
) -> None:
    baseline = tmp_path / "baseline.json"
    claimed = tmp_path / "claimed.json"
    assert main([*_args("evaluate"), "--output", str(baseline)]) == 0
    assert (
        main(
            [
                *_args("evaluate"),
                "--output",
                str(claimed),
                "--claimed-generated-at",
                "2026-07-17T01:02:03Z",
            ]
        )
        == 0
    )
    baseline_document = json.loads(baseline.read_text(encoding="utf-8"))
    claimed_document = json.loads(claimed.read_text(encoding="utf-8"))
    assert claimed_document["envelope"]["claimed_generated_at"] == (
        "2026-07-17T01:02:03Z"
    )
    assert claimed_document["payload"] == baseline_document["payload"]
    assert claimed_document["payload_sha256"] == baseline_document["payload_sha256"]


def test_evaluate_cli_rejects_noncanonical_claimed_time_without_echo(
    capsys: object,
) -> None:
    for value, code in (
        ("2026-07-17T01:02:03+00:00", "invalid_format"),
        ("2026-07-17T01:02:03.500Z", "invalid_format"),
        ("2026-13-17T01:02:03Z", "invalid_timestamp"),
    ):
        assert main([*_args("evaluate"), "--claimed-generated-at", value]) == 2
        captured = capsys.readouterr()
        assert json.loads(captured.err)["error"]["code"] == code
        assert value not in captured.err
        assert captured.out == ""


def test_cli_prohibited_field_fails_without_echoing_value(
    tmp_path: Path, capsys: object
) -> None:
    case = json.loads((REFERENCE / "case.json").read_text(encoding="utf-8"))
    case["narrative"] = "never echo this patient-like content"
    path = tmp_path / "case.json"
    path.write_text(json.dumps(case), encoding="utf-8")
    args = _args("validate")
    args[2] = str(path)
    assert main(args) == 2
    captured = capsys.readouterr()
    error = json.loads(captured.err)["error"]
    assert error["code"] == "prohibited_field"
    assert "patient-like" not in captured.err


def test_cli_rejects_invalid_json_duplicate_keys_and_utf8(
    tmp_path: Path, capsys: object
) -> None:
    args = _args("validate")
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{", encoding="utf-8")
    args[2] = str(invalid)
    assert main(args) == 2
    assert json.loads(capsys.readouterr().err)["error"]["code"] == "invalid_json"
    invalid.write_text('{"schema_version":"a","schema_version":"b"}', encoding="utf-8")
    assert main(args) == 2
    assert json.loads(capsys.readouterr().err)["error"]["code"] == "duplicate_json_key"
    invalid.write_bytes(b"\xff")
    assert main(args) == 2
    assert json.loads(capsys.readouterr().err)["error"]["code"] == "invalid_utf8"


def test_cli_rejects_nonstandard_and_oversized_numbers(
    tmp_path: Path, capsys: object
) -> None:
    args = _args("validate")
    invalid = tmp_path / "invalid-number.json"
    args[2] = str(invalid)
    for numeric_literal in ("NaN", "1" * 5_000):
        invalid.write_text(f'{{"value":{numeric_literal}}}', encoding="utf-8")
        assert main(args) == 2
        error = json.loads(capsys.readouterr().err)["error"]
        assert error["code"] == "invalid_json"


def test_cli_rejects_non_scalar_unicode_without_crashing(
    tmp_path: Path, capsys: object
) -> None:
    case = json.loads((REFERENCE / "case.json").read_text(encoding="utf-8"))
    case["concepts"]["pronouns"]["value"] = json.loads('"\\ud800"')
    path = tmp_path / "case.json"
    path.write_text(json.dumps(case), encoding="utf-8")
    args = _args("validate")
    args[2] = str(path)

    assert main(args) == 2
    error = json.loads(capsys.readouterr().err)["error"]
    assert error["code"] == "invalid_unicode"


def test_cli_rejects_unreadable_and_oversized_inputs(
    tmp_path: Path, capsys: object
) -> None:
    args = _args("validate")
    args[2] = str(tmp_path / "missing.json")
    assert main(args) == 2
    assert json.loads(capsys.readouterr().err)["error"]["code"] == "input_io_error"
    large = tmp_path / "large.json"
    large.write_bytes(b" " * 1_048_577)
    args[2] = str(large)
    assert main(args) == 2
    assert json.loads(capsys.readouterr().err)["error"]["code"] == "input_too_large"


def test_cli_rejects_excessively_nested_json_without_crashing(
    tmp_path: Path, capsys: object
) -> None:
    args = _args("validate")
    deeply_nested = tmp_path / "deep.json"
    deeply_nested.write_text("[" * 2_000 + "0" + "]" * 2_000, encoding="utf-8")
    args[2] = str(deeply_nested)

    assert main(args) == 2
    error = json.loads(capsys.readouterr().err)["error"]
    assert error["code"] == "input_too_deep"


def test_cli_reports_output_failure(tmp_path: Path, capsys: object) -> None:
    assert main([*_args("evaluate"), "--output", str(tmp_path)]) == 2
    assert json.loads(capsys.readouterr().err)["error"]["code"] == "output_io_error"


def test_evidence_preflight_reports_output_failure(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    execution_plan: ExecutionPlan,
) -> None:
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(execution_plan.to_dict()), encoding="utf-8")
    args = [*_evidence_preflight_args(plan_path), "--output", str(tmp_path)]
    assert main(args) == 2
    error = json.loads(capsys.readouterr().err)["error"]
    assert error["code"] == "output_io_error"


def test_quiet_suppresses_stdout_success_payload(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main([*_args("validate"), "--quiet"]) == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_quiet_still_writes_output_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "receipt.json"
    assert main([*_args("evaluate"), "--quiet", "--output", str(output)]) == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
    receipt = json.loads(output.read_text(encoding="utf-8"))
    assert receipt["payload"]["summary"]["pass"] == 5


def test_evidence_preflight_cli_can_write_result(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    execution_plan: ExecutionPlan,
) -> None:
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(execution_plan.to_dict()), encoding="utf-8")
    output = tmp_path / "preflight-result.json"
    args = [*_evidence_preflight_args(plan_path), "--output", str(output)]
    assert main(args) == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["boundary_check_status"] == "passed"
    assert result["persisted"] is False
    assert result["raw_sha256"]


def test_evidence_preflight_quiet_still_writes_output_file(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    execution_plan: ExecutionPlan,
) -> None:
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(execution_plan.to_dict()), encoding="utf-8")
    output = tmp_path / "preflight-result.json"
    args = [*_evidence_preflight_args(plan_path), "--quiet", "--output", str(output)]
    assert main(args) == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["boundary_check_status"] == "passed"


def test_evidence_preflight_without_output_still_prints_result(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    execution_plan: ExecutionPlan,
) -> None:
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(execution_plan.to_dict()), encoding="utf-8")
    assert main(_evidence_preflight_args(plan_path)) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    result = json.loads(captured.out)
    assert result["boundary_check_status"] == "passed"


def test_quiet_preserves_structured_stderr_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = _args("validate")
    args[2] = str(tmp_path / "missing.json")
    assert main([*args, "--quiet"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err)["error"]["code"] == "input_io_error"


def test_usage_errors_exit_with_dedicated_code(
    capsys: pytest.CaptureFixture[str],
) -> None:
    usage_errors: list[list[str]] = [
        [],
        ["validate"],
        [*_args("validate"), "--unknown-flag"],
        ["pack"],
        ["evidence", "preflight"],
        ["import"],
        ["import", "--format", "canonical-json"],
        ["mapping"],
        ["mapping", "validate"],
    ]
    for argv in usage_errors:
        with pytest.raises(SystemExit) as raised:
            main(argv)
        assert raised.value.code == EXIT_USAGE_ERROR
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "error:" in captured.err


def test_help_exits_zero_and_documents_exit_codes(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["--help"])
    assert raised.value.code == 0
    help_text = capsys.readouterr().out
    assert "exit codes" in help_text
    assert "64" in help_text


def test_no_color_accepted_and_output_never_contains_ansi(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    execution_plan: ExecutionPlan,
) -> None:
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(execution_plan.to_dict()), encoding="utf-8")
    draft_pack = str(REFERENCE / "pack-draft.json")
    invocations: list[tuple[int, list[str]]] = [
        (0, [*_args("validate"), "--no-color"]),
        (0, [*_args("evaluate"), "--no-color"]),
        (
            2,
            [
                "pack",
                "validate",
                "--no-color",
                "--pack",
                draft_pack,
                "--as-of",
                "2026-07-13",
            ],
        ),
        (
            2,
            [
                "plan",
                "validate",
                "--no-color",
                "--engagement",
                draft_pack,
                "--plan",
                str(plan_path),
                "--pack",
                draft_pack,
                "--as-of",
                "2026-07-13",
            ],
        ),
        (0, [*_evidence_preflight_args(plan_path), "--no-color"]),
        (
            0,
            [
                "import",
                "--no-color",
                "--format",
                "canonical-json",
                "--source",
                str(REFERENCE / "evidence-source.json"),
                "--case",
                str(REFERENCE / "case.json"),
                "--checkpoint",
                "ehr",
            ],
        ),
        (
            0,
            [
                "import",
                "--no-color",
                "--format",
                "canonical-json",
                "--source",
                str(REFERENCE / "evidence-source.json"),
                "--case",
                str(REFERENCE / "case.json"),
                "--checkpoint",
                "ehr",
                "--mapping",
                str(REFERENCE / "mapping-canonical-json.json"),
            ],
        ),
        (
            0,
            [
                "mapping",
                "validate",
                "--no-color",
                "--profile",
                str(REFERENCE / "mapping-canonical-json.json"),
            ],
        ),
    ]
    for expected_exit, argv in invocations:
        assert main(argv) == expected_exit
        captured = capsys.readouterr()
        assert "\x1b" not in captured.out
        assert "\x1b" not in captured.err
