"""CLI behavior and value-minimizing error tests."""

import json
from pathlib import Path

from contextsafe.cli import main

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
