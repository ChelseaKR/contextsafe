"""``contextsafe fixtures export`` and the packaged reference set it copies."""

import argparse
import json
import re
from pathlib import Path

import pytest

from contextsafe import reference_fixtures
from contextsafe.cli import EXIT_CONTRACT_ERROR, EXIT_SUCCESS, _operator_command, main
from contextsafe.errors import ContextSafeError
from contextsafe.reference_fixtures import (
    DEFAULT_EXPORT_DIRECTORY,
    REFERENCE_FILES,
    REFERENCE_ROOT,
    export_reference_fixtures,
)

DIGEST = re.compile(r"[0-9a-f]{64}")
ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "docs" / "PUBLICATION-READINESS.md"
NUMBER_WORDS = (
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
)


def test_the_packaged_set_is_exactly_the_named_set() -> None:
    """The names are the denominator: each exists, and nothing else is there."""

    assert sorted(path.name for path in REFERENCE_ROOT.iterdir()) == sorted(
        REFERENCE_FILES
    )


def test_the_publication_audit_describes_the_packaged_set_it_names() -> None:
    """Section 4 of the audit states the count, the byte total, and a row per file.

    The figures went stale once (five files and 7,957 bytes after a sixth was
    added), and the claims gate cannot see prose. Deriving them here from the
    packaged set is what makes the document move with it.
    """

    text = AUDIT.read_text(encoding="utf-8")
    start = text.index("### §4 Synthetic-data confirmation")
    section = " ".join(text[start : text.index("### §5", start)].split())
    total = sum(len((REFERENCE_ROOT / name).read_bytes()) for name in REFERENCE_FILES)
    word = NUMBER_WORDS[len(REFERENCE_FILES)]
    assert f"holds exactly {word} files, {total:,} bytes total" in section
    for name in REFERENCE_FILES:
        assert f"| `{name}` |" in section, name
    assert f"| {word.capitalize()} synthetic fixtures using invented tokens" in text


def test_export_writes_every_fixture_byte_for_byte(tmp_path: Path) -> None:
    target = tmp_path / "out"

    manifest = export_reference_fixtures(target)

    for name in REFERENCE_FILES:
        assert (target / name).read_bytes() == (REFERENCE_ROOT / name).read_bytes()
    assert manifest["directory"] == target.as_posix()
    files = manifest["files"]
    assert isinstance(files, dict)
    assert set(files) == set(REFERENCE_FILES)
    for name, entry in files.items():
        assert isinstance(entry, dict)
        assert entry["status"] == "written"
        digest = entry["sha256"]
        assert isinstance(digest, str) and DIGEST.fullmatch(digest)
        assert len((target / name).read_bytes()) > 0


def test_export_leaves_an_identical_file_alone_and_says_so(tmp_path: Path) -> None:
    target = tmp_path / "out"
    export_reference_fixtures(target)
    before = {name: (target / name).stat().st_mtime_ns for name in REFERENCE_FILES}

    manifest = export_reference_fixtures(target)

    files = manifest["files"]
    assert isinstance(files, dict)
    for name in REFERENCE_FILES:
        entry = files[name]
        assert isinstance(entry, dict)
        assert entry["status"] == "unchanged"
        assert (target / name).stat().st_mtime_ns == before[name]


def test_export_refuses_a_differing_file_and_writes_nothing(tmp_path: Path) -> None:
    target = tmp_path / "out"
    target.mkdir()
    (target / "rules.json").write_bytes(b"{}")

    with pytest.raises(ContextSafeError) as info:
        export_reference_fixtures(target)

    assert info.value.code == "fixture_export_conflict"
    assert info.value.path == "$.rules.json"
    assert "nothing was written" in info.value.message
    assert [path.name for path in target.iterdir()] == ["rules.json"]
    assert (target / "rules.json").read_bytes() == b"{}"


def test_export_refuses_a_symbolic_link_without_following_it(tmp_path: Path) -> None:
    elsewhere = tmp_path / "elsewhere.json"
    elsewhere.write_bytes((REFERENCE_ROOT / "case.json").read_bytes())
    target = tmp_path / "out"
    target.mkdir()
    (target / "case.json").symlink_to(elsewhere)

    with pytest.raises(ContextSafeError) as info:
        export_reference_fixtures(target)

    assert info.value.code == "fixture_export_conflict"
    assert info.value.path == "$.case.json"
    assert [path.name for path in target.iterdir()] == ["case.json"]


def test_export_refuses_a_path_it_cannot_compare(tmp_path: Path) -> None:
    target = tmp_path / "out"
    (target / "observations.json").mkdir(parents=True)

    with pytest.raises(ContextSafeError) as info:
        export_reference_fixtures(target)

    assert info.value.code == "fixture_export_conflict"
    assert info.value.path == "$.observations.json"
    assert [path.name for path in target.iterdir()] == ["observations.json"]


def test_export_fails_before_writing_when_the_install_is_incomplete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """All but one fixture is not an export; it is a broken install."""

    partial = tmp_path / "partial"
    partial.mkdir()
    for name in REFERENCE_FILES[:-1]:
        (partial / name).write_bytes((REFERENCE_ROOT / name).read_bytes())
    monkeypatch.setattr(reference_fixtures, "REFERENCE_ROOT", partial)

    with pytest.raises(ContextSafeError) as info:
        export_reference_fixtures(tmp_path / "out")

    assert info.value.code == "fixture_missing"
    assert info.value.path == f"$.{REFERENCE_FILES[-1]}"
    assert not (tmp_path / "out").exists()


def test_export_reports_an_unwritable_directory(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("not a directory", encoding="utf-8")

    with pytest.raises(ContextSafeError) as info:
        export_reference_fixtures(blocker / "out")

    assert info.value.code == "output_io_error"


def test_cli_exports_to_the_documented_path_and_the_documented_commands_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """From an empty directory, the README's relative paths work as written."""

    monkeypatch.chdir(tmp_path)

    assert main(["fixtures", "export"]) == EXIT_SUCCESS

    captured = capsys.readouterr()
    assert captured.err == ""
    manifest = json.loads(captured.out)
    assert (
        manifest["directory"]
        == DEFAULT_EXPORT_DIRECTORY.as_posix()
        == ("fixtures/reference")
    )
    assert set(manifest["files"]) == set(REFERENCE_FILES)
    assert (
        main(
            [
                "evaluate",
                "--case",
                "fixtures/reference/case.json",
                "--observations",
                "fixtures/reference/observations.json",
                "--rules",
                "fixtures/reference/rules.json",
                "--output",
                "receipt.json",
            ]
        )
        == EXIT_SUCCESS
    )
    receipt = json.loads((tmp_path / "receipt.json").read_text(encoding="utf-8"))
    assert receipt["payload"]["case_id"] == "CTP-I01"
    assert (
        main(["render", "--receipt", "receipt.json", "--output", "receipt.html"])
        == EXIT_SUCCESS
    )
    assert "<html" in (tmp_path / "receipt.html").read_text(encoding="utf-8")


def test_cli_export_honours_directory_and_quiet(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "somewhere" / "else"

    assert (
        main(["fixtures", "export", "--quiet", "--directory", str(target)])
        == EXIT_SUCCESS
    )

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
    assert sorted(path.name for path in target.iterdir()) == sorted(REFERENCE_FILES)


def test_cli_export_conflict_is_a_contract_error_with_no_value_in_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "out"
    target.mkdir()
    (target / "case.json").write_bytes(b'{"case_id": "edited by hand"}')

    assert (
        main(["fixtures", "export", "--directory", str(target)]) == EXIT_CONTRACT_ERROR
    )

    captured = capsys.readouterr()
    assert captured.out == ""
    error = json.loads(captured.err)["error"]
    assert error["code"] == "fixture_export_conflict"
    assert error["path"] == "$.case.json"
    assert str(tmp_path) not in captured.err
    assert "edited by hand" not in captured.err


def test_an_unknown_fixtures_command_is_refused() -> None:
    args = argparse.Namespace(command="fixtures", fixtures_command="import")

    with pytest.raises(ContextSafeError) as info:
        _operator_command(args)

    assert info.value.code == "unsupported_command"
