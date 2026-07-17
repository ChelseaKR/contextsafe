"""CLI behavior and value-minimizing error tests."""

import json
from pathlib import Path

import pytest

from contextsafe.cli import EXIT_USAGE_ERROR, main
from contextsafe.evidence import CANONICAL_JSON_MEDIA_TYPE, CANONICAL_JSON_SOURCE_TYPE
from contextsafe.plan import ExecutionPlan

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "fixtures" / "reference"


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


def test_validate_cli_emits_machine_readable_summary(capsys: object) -> None:
    assert main(_args("validate")) == 0
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert report["valid"] is True
    assert report["observation_count"] == 5
    assert captured.err == ""


def test_evaluate_cli_can_write_receipt(tmp_path: Path, capsys: object) -> None:
    output = tmp_path / "receipt.json"
    assert main([*_args("evaluate"), "--output", str(output)]) == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    receipt = json.loads(output.read_text(encoding="utf-8"))
    assert receipt["summary"]["pass"] == 5


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
    assert receipt["summary"]["pass"] == 5


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
        (
            0,
            [
                "evidence",
                "preflight",
                "--no-color",
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
            ],
        ),
    ]
    for expected_exit, argv in invocations:
        assert main(argv) == expected_exit
        captured = capsys.readouterr()
        assert "\x1b" not in captured.out
        assert "\x1b" not in captured.err
