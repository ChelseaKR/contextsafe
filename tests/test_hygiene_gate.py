"""The hygiene gate must fail, and must fail differently when it cannot run.

The gate this replaced could not fail at all on a machine without ripgrep:
``! rg ...`` maps "the tool is not installed" onto success exactly as it maps
"the tool found nothing". So the load-bearing tests here are the three-state
ones. A marker present is a finding; a clean tree is a pass; a gate that could
not examine anything - no git, no repository, no tracked file - is exit 2 and
never a pass.

Marker literals are never written out in this file. This file lives under
``tests``, which is one of the trees the real gate scans, so a literal here
would be a finding against the repository itself. Every case builds its marker
from ``gate.MARKERS`` instead, which also keeps the tests honest if that tuple
ever changes.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
GATE_PATH = REPO_ROOT / "tools" / "hygiene_gate.py"


def _load_gate() -> ModuleType:
    spec = importlib.util.spec_from_file_location("hygiene_gate", GATE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


gate = _load_gate()


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],  # noqa: S607 - `git` from PATH is the project's own toolchain
        cwd=root,
        check=True,
        capture_output=True,
    )


def _repo(root: Path, files: dict[str, str]) -> Path:
    """Build a tracked repository at ``root`` and return it."""

    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q")
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        _git(root, "add", "--", rel)
    return root


CLEAN_FILES = {
    "src/pkg/__init__.py": '"""A module with nothing owed."""\n',
    "tests/test_pkg.py": "def test_nothing() -> None:\n    assert True\n",
    "pyproject.toml": "[project]\nname = 'pkg'\n",
}


# --- the tool ran and found nothing ----------------------------------------


def test_clean_repository_passes(tmp_path: Path) -> None:
    assert gate.main(["--root", str(_repo(tmp_path, CLEAN_FILES))]) == 0


def test_the_clean_line_says_how_much_was_read(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A pass that examined less than it should must not look like a real one."""

    gate.main(["--root", str(_repo(tmp_path, CLEAN_FILES))])
    out = capsys.readouterr().out
    assert "2 tracked file(s)" in out
    assert "3 tracked path(s)" in out
    assert "0 exemption(s) honored" in out


def test_this_repository_is_clean() -> None:
    assert gate.main([]) == 0


# --- the tool ran and found something --------------------------------------


@pytest.mark.parametrize("marker", gate.MARKERS)
@pytest.mark.parametrize("root", gate.MARKER_ROOTS)
def test_a_marker_in_a_scanned_tree_is_a_finding(
    tmp_path: Path, marker: str, root: str
) -> None:
    files = dict(CLEAN_FILES)
    files[f"{root}/pkg/planted.py"] = f"# {marker}: finish this later\n"
    assert gate.main(["--root", str(_repo(tmp_path, files))]) == 1


@pytest.mark.parametrize("marker", gate.MARKERS)
def test_a_marker_in_the_gate_implementations_is_a_finding(
    tmp_path: Path, marker: str
) -> None:
    """`tools` was the one tree exempt from the rule its own code enforces.

    The parametrized test above walks ``MARKER_ROOTS``, so it grew this case
    the moment the tuple grew. This one names the tree literally, so shrinking
    the tuple back is a test failure rather than a silently smaller scan.
    """

    files = dict(CLEAN_FILES)
    files["tools/some_gate.py"] = f"# {marker}: finish this later\n"
    assert gate.main(["--root", str(_repo(tmp_path, files))]) == 1


def test_the_gate_implementations_are_in_the_scanned_trees() -> None:
    assert "tools" in gate.MARKER_ROOTS


@pytest.mark.parametrize("marker", gate.MARKERS)
def test_a_marker_outside_the_scanned_trees_is_not_a_finding(
    tmp_path: Path, marker: str
) -> None:
    files = dict(CLEAN_FILES)
    files["docs/notes.md"] = f"{marker}: a note in prose is not product code\n"
    assert gate.main(["--root", str(_repo(tmp_path, files))]) == 0


def test_a_marker_finding_carries_its_line() -> None:
    text = "one\ntwo\n# " + gate.MARKERS[0] + " here\n"
    findings, exemptions = gate.find_markers("src/pkg/x.py", text)
    assert [(f.rule_id, f.line_number) for f in findings] == [("marker", 3)]
    assert exemptions == []


def test_an_untracked_marker_file_is_not_yet_the_repository_s_problem(
    tmp_path: Path,
) -> None:
    """Only tracked files reach CI, so only tracked files are scanned."""

    root = _repo(tmp_path, CLEAN_FILES)
    (root / "src" / "scratch.py").write_text(f"# {gate.MARKERS[0]}\n", encoding="utf-8")
    assert gate.main(["--root", str(root)]) == 0


@pytest.mark.parametrize("name", sorted(gate.STRAY_CONFIG_NAMES))
def test_a_stray_tool_config_is_a_finding(tmp_path: Path, name: str) -> None:
    files = dict(CLEAN_FILES)
    files[name] = "# a second source of truth\n"
    assert gate.main(["--root", str(_repo(tmp_path, files))]) == 1


def test_a_stray_config_one_directory_down_is_still_a_finding() -> None:
    assert [f.rule_id for f in gate.find_stray_configs(["tools/setup.py"])] == [
        "stray-config"
    ]


def test_a_config_deeper_than_two_segments_is_not_flagged() -> None:
    assert gate.find_stray_configs(["tools/a11y/node_modules/setup.py"]) == []


def test_the_repository_s_own_config_is_not_flagged() -> None:
    assert gate.find_stray_configs(["pyproject.toml", "uv.lock", "Makefile"]) == []


def test_a_listed_file_that_cannot_be_read_is_reported_not_skipped(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path, CLEAN_FILES)
    (root / "src" / "pkg" / "__init__.py").unlink()
    findings, examined, exemptions = gate.scan_markers(root, ["src/pkg/__init__.py"])
    assert [f.rule_id for f in findings] == ["unreadable"]
    assert examined == 0
    assert exemptions == []
    assert gate.main(["--root", str(root)]) == 1


# --- the exemption mechanism ------------------------------------------------


def _exempted(marker: str, reason: str) -> str:
    return f"# {marker} {gate.ALLOW_MARKER} {reason}\n"


@pytest.mark.parametrize("marker", gate.MARKERS)
def test_an_exempted_marker_is_not_a_finding(tmp_path: Path, marker: str) -> None:
    files = dict(CLEAN_FILES)
    files["src/pkg/documented.py"] = _exempted(marker, "quoted, not deferred work")
    assert gate.main(["--root", str(_repo(tmp_path, files))]) == 0


def test_an_exemption_is_printed_on_a_clean_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The one thing the gate deliberately does not report as a finding.

    An exemption that nobody can see is the hole the mechanism exists to avoid,
    so it is printed whether the run passes or fails, and counted in the clean
    line.
    """

    files = dict(CLEAN_FILES)
    files["src/pkg/documented.py"] = _exempted(gate.MARKERS[0], "the stated reason")
    assert gate.main(["--root", str(_repo(tmp_path, files))]) == 0
    out = capsys.readouterr().out
    assert "exempted src/pkg/documented.py:1" in out
    assert "the stated reason" in out
    assert "1 exemption(s) honored" in out


def test_exemptions_are_printed_even_when_the_run_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    files = dict(CLEAN_FILES)
    files["src/pkg/documented.py"] = _exempted(gate.MARKERS[0], "the stated reason")
    files["src/pkg/planted.py"] = f"# {gate.MARKERS[1]}\n"
    assert gate.main(["--root", str(_repo(tmp_path, files))]) == 1
    captured = capsys.readouterr()
    assert "exempted src/pkg/documented.py:1" in captured.out
    assert "marker: src/pkg/planted.py:1" in captured.err


@pytest.mark.parametrize("trailing", ["", " ", "\t"])
def test_an_exemption_without_a_reason_is_a_finding(
    tmp_path: Path, trailing: str
) -> None:
    """An exemption asserts something a reader cannot see in the line itself."""

    files = dict(CLEAN_FILES)
    files["src/pkg/bare.py"] = f"# {gate.MARKERS[0]} {gate.ALLOW_MARKER}{trailing}\n"
    assert gate.main(["--root", str(_repo(tmp_path, files))]) == 1


def test_the_unreasoned_exemption_is_its_own_rule() -> None:
    text = f"x = 1  # {gate.MARKERS[0]} {gate.ALLOW_MARKER}\n"
    findings, exemptions = gate.find_markers("src/pkg/bare.py", text)
    assert [f.rule_id for f in findings] == ["unreasoned-exemption"]
    assert exemptions == []


def test_an_exemption_records_the_marker_and_the_reason() -> None:
    text = f"x = 1  # {gate.MARKERS[2]} {gate.ALLOW_MARKER} because it is quoted\n"
    findings, exemptions = gate.find_markers("tools/some_gate.py", text)
    assert findings == []
    assert [(e.location, e.line_number, e.marker, e.reason) for e in exemptions] == [
        ("tools/some_gate.py", 1, gate.MARKERS[2], "because it is quoted")
    ]


def test_an_allow_marker_on_a_line_with_no_marker_is_not_inspected() -> None:
    """The gate's own source defines ``ALLOW_MARKER``; that line owes nothing."""

    text = f'ALLOW_MARKER = "{gate.ALLOW_MARKER}"\n'
    assert gate.find_markers("tools/some_gate.py", text) == ([], [])


def test_this_repository_s_exemptions_all_sit_in_the_gate_that_defines_them() -> None:
    """A marker word is legitimate in exactly one place: the rule that bans it.

    Pinning that keeps the mechanism from spreading quietly. A new exemption
    anywhere else fails here and has to be argued for in review.
    """

    result = gate.run_gate(gate.repo_root())
    assert result.findings == []
    assert {e.location for e in result.exemptions} == {"tools/hygiene_gate.py"}
    assert all(e.reason for e in result.exemptions)


# --- the tool did not run: exit 2, never a pass ----------------------------


def test_a_directory_that_is_not_a_repository_is_a_refusal(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    assert gate.main(["--root", str(tmp_path)]) == 2


def test_a_repository_with_nothing_tracked_is_a_refusal(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-q")
    assert gate.main(["--root", str(tmp_path)]) == 2


def test_a_repository_with_nothing_under_the_scanned_trees_is_a_refusal(
    tmp_path: Path,
) -> None:
    """The exact shape of the old defect: a green result over zero bytes."""

    root = _repo(tmp_path, {"README.md": "no source, no tests\n"})
    assert gate.main(["--root", str(root)]) == 2


def test_git_missing_from_path_is_a_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The rg defect, in the tool this gate actually depends on."""

    root = _repo(tmp_path, CLEAN_FILES)

    def no_git(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        raise FileNotFoundError(2, "No such file or directory: 'git'")

    monkeypatch.setattr(gate.subprocess, "run", no_git)
    assert gate.main(["--root", str(root)]) == 2
    err = capsys.readouterr().err
    assert "git is not on PATH" in err
    assert "not a clean result" in err


def test_a_failing_git_is_a_refusal_not_a_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path, CLEAN_FILES)

    def broken_git(
        *args: object, **kwargs: object
    ) -> subprocess.CompletedProcess[bytes]:
        raise subprocess.CalledProcessError(128, ["git"], b"", b"fatal: bad object")

    monkeypatch.setattr(gate.subprocess, "run", broken_git)
    assert gate.main(["--root", str(root)]) == 2


def test_the_refusal_is_a_distinct_exit_code_from_a_finding(tmp_path: Path) -> None:
    """Exit 1 and exit 2 must not collapse: one is a defect, one is no answer."""

    found = dict(CLEAN_FILES)
    found["src/planted.py"] = f"# {gate.MARKERS[0]}\n"
    assert gate.main(["--root", str(_repo(tmp_path / "found", found))]) == 1
    empty = _repo(tmp_path / "empty", {"README.md": "nothing here\n"})
    assert gate.main(["--root", str(empty)]) == 2
