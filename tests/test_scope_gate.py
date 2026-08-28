"""The scope gate must fail on a tree nobody claimed, and refuse on no answer.

The gap this closes is one the other gates cannot see. `make hygiene` and the
coverage floor both reported clean over `src` and `tests` while `tools/` held
four gate implementations neither had been pointed at. Both were telling the
truth about the trees they were given. Nothing was in a position to notice the
third tree.

So the load-bearing cases here are: a file under no claimed root is a finding;
an exception that excuses nothing is a finding; a claimed root with nothing
under it is a finding; and a gate that cannot read what an analysis claims is
exit 2 and never a pass.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
GATE_PATH = REPO_ROOT / "tools" / "scope_gate.py"


def _load_gate() -> ModuleType:
    spec = importlib.util.spec_from_file_location("scope_gate", GATE_PATH)
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


MAKEFILE = """\
typecheck:
\tuv run mypy --strict

test:
\tuv run pytest --cov --cov-branch
\tuv run coverage report --fail-under=95
"""

PYPROJECT = """\
[tool.mypy]
files = ["src", "tools"]

[tool.coverage.run]
source = ["src", "tools"]
"""

HYGIENE_STUB = 'MARKER_ROOTS: tuple[str, ...] = ("src", "tests", "tools")\n'


def _repo(root: Path, files: dict[str, str] | None = None) -> Path:
    """Build a tracked repository whose claims all hold, and return it."""

    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q")
    contents = {
        "Makefile": MAKEFILE,
        "pyproject.toml": PYPROJECT,
        "tools/hygiene_gate.py": HYGIENE_STUB,
        "src/pkg.py": "value = 1\n",
        # The real declared exceptions name `tests/`, and an exception that
        # excuses nothing is a finding, so a fixture repository has to have one.
        "tests/test_pkg.py": "def test_nothing() -> None:\n    assert True\n",
        **(files or {}),
    }
    for rel, text in contents.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        _git(root, "add", "--", rel)
    return root


def _analysis(name: str, *roots: str) -> object:
    return gate.Analysis(name, "a test", roots)


# --- the gate ran and found nothing ----------------------------------------


def test_a_repository_whose_claims_all_hold_passes(tmp_path: Path) -> None:
    assert gate.main(["--root", str(_repo(tmp_path))]) == 0


def test_the_clean_line_names_every_claim(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    gate.main(["--root", str(_repo(tmp_path))])
    out = capsys.readouterr().out
    assert "3 tracked Python file(s)" in out
    assert "marker-scan [src tests tools]" in out
    assert "strict-typing [src tools]" in out


def test_this_repository_declares_every_tree_it_does_not_examine() -> None:
    assert gate.main([]) == 0


# --- the gate ran and found something --------------------------------------


def test_a_file_under_no_claimed_root_is_a_finding() -> None:
    """The `tools/` hole, in the shape this gate sees it."""

    findings, _ = gate.check(
        [_analysis("marker-scan", "src")],
        ["src/pkg.py", "tools/some_gate.py"],
        exceptions=(),
    )
    assert [(f.rule_id, f.subject) for f in findings] == [
        ("unclaimed-file", "marker-scan:tools/some_gate.py")
    ]


def test_the_gate_fails_the_repository_when_a_tree_is_unclaimed(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    (root / "pyproject.toml").write_text(
        PYPROJECT.replace('files = ["src", "tools"]', 'files = ["src"]'),
        encoding="utf-8",
    )
    _git(root, "add", "--", "pyproject.toml")
    assert gate.main(["--root", str(root)]) == 1


def test_a_declared_exception_that_excuses_nothing_is_a_finding() -> None:
    """A stale exception describes a repository that is not this one."""

    findings, excused = gate.check(
        [_analysis("strict-typing", "src")],
        ["src/pkg.py"],
        exceptions=(gate.DeclaredException("strict-typing", "tests/", "a reason"),),
    )
    assert [f.rule_id for f in findings] == ["stale-exception"]
    assert excused == {("strict-typing", "tests/"): 0}


def test_a_claimed_root_with_nothing_under_it_is_a_finding() -> None:
    """An analysis pointed at a tree that is not there covers less than it says."""

    findings, _ = gate.check(
        [_analysis("marker-scan", "src", "benchmarks")],
        ["src/pkg.py"],
        exceptions=(),
    )
    assert [(f.rule_id, f.subject) for f in findings] == [
        ("empty-claim", "marker-scan:benchmarks")
    ]


def test_a_declared_exception_excuses_the_file_and_is_counted() -> None:
    findings, excused = gate.check(
        [_analysis("strict-typing", "src")],
        ["src/pkg.py", "tests/test_pkg.py", "tests/conftest.py"],
        exceptions=(gate.DeclaredException("strict-typing", "tests/", "a reason"),),
    )
    assert findings == []
    assert excused == {("strict-typing", "tests/"): 2}


def test_an_exception_only_excuses_the_analysis_it_names() -> None:
    findings, _ = gate.check(
        [_analysis("strict-typing", "src"), _analysis("marker-scan", "src")],
        ["src/pkg.py", "tests/test_pkg.py"],
        exceptions=(gate.DeclaredException("strict-typing", "tests/", "a reason"),),
    )
    assert [f.subject for f in findings] == ["marker-scan:tests/test_pkg.py"]


def test_every_declared_exception_is_printed_on_a_clean_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Coverage declared away has to be as visible as coverage achieved."""

    gate.main(["--root", str(_repo(tmp_path))])
    out = capsys.readouterr().out
    for declared in gate.DECLARED_EXCEPTIONS:
        assert f"declared {declared.analysis} excludes {declared.prefix}" in out
        assert declared.reason in out


def test_a_prefix_match_is_on_path_segments_not_characters() -> None:
    """`src` must not claim `srcery/`, or a claim would cover a tree by accident."""

    findings, _ = gate.check(
        [_analysis("strict-typing", "src")],
        ["src/pkg.py", "srcery/pkg.py"],
        exceptions=(),
    )
    assert [(f.rule_id, f.subject) for f in findings] == [
        ("unclaimed-file", "strict-typing:srcery/pkg.py")
    ]


# --- the gate did not run: exit 2, never a pass ----------------------------


def test_a_repository_with_no_tracked_python_is_a_refusal(tmp_path: Path) -> None:
    """Every claim holds vacuously over an empty tree, which is not a pass."""

    _git(tmp_path, "init", "-q")
    (tmp_path / "README.md").write_text("no python here\n", encoding="utf-8")
    _git(tmp_path, "add", "--", "README.md")
    assert gate.main(["--root", str(tmp_path)]) == 2


def test_git_missing_from_path_is_a_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path)

    def no_git(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        raise FileNotFoundError(2, "No such file or directory: 'git'")

    monkeypatch.setattr(gate.subprocess, "run", no_git)
    assert gate.main(["--root", str(root)]) == 2
    err = capsys.readouterr().err
    assert "git is not on PATH" in err
    assert "not a clean result" in err


@pytest.mark.parametrize(
    ("filename", "content"),
    [
        ("pyproject.toml", "[tool.coverage.run]\nsource = ['src']\n"),
        ("pyproject.toml", "[tool.mypy]\nfiles = []\n"),
        ("pyproject.toml", "this is not toml =\n"),
    ],
)
def test_a_claim_the_gate_cannot_read_is_a_refusal(
    tmp_path: Path, filename: str, content: str
) -> None:
    """An unreadable claim is no answer about scope, so it is never a pass."""

    root = _repo(tmp_path)
    (root / filename).write_text(content, encoding="utf-8")
    _git(root, "add", "--", filename)
    assert gate.main(["--root", str(root)]) == 2


def test_a_missing_makefile_target_is_a_refusal(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    (root / "Makefile").write_text("lint:\n\truff check .\n", encoding="utf-8")
    _git(root, "add", "--", "Makefile")
    assert gate.main(["--root", str(root)]) == 2


@pytest.mark.parametrize(
    "recipe",
    [
        "typecheck:\n\tuv run mypy --strict src\n\ntest:\n\tuv run pytest --cov\n",
        "typecheck:\n\tuv run mypy --strict\n\ntest:\n\tuv run pytest --cov=contextsafe\n",
    ],
)
def test_a_command_that_overrides_the_configured_scope_is_a_refusal(
    tmp_path: Path, recipe: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """A path on the command line beats the config, so the claim moves."""

    root = _repo(tmp_path)
    (root / "Makefile").write_text(recipe, encoding="utf-8")
    _git(root, "add", "--", "Makefile")
    assert gate.main(["--root", str(root)]) == 2
    assert "overrides the scope configured" in capsys.readouterr().err


def test_a_target_that_never_runs_the_tool_is_a_refusal(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    (root / "Makefile").write_text(
        "typecheck:\n\techo skipped\n\ntest:\n\tuv run pytest --cov\n", encoding="utf-8"
    )
    _git(root, "add", "--", "Makefile")
    assert gate.main(["--root", str(root)]) == 2


def test_a_target_with_no_command_lines_is_a_refusal(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    (root / "Makefile").write_text(
        "typecheck:\n\nother:\n\techo hi\n", encoding="utf-8"
    )
    _git(root, "add", "--", "Makefile")
    assert gate.main(["--root", str(root)]) == 2


def test_a_marker_roots_the_gate_cannot_read_is_a_refusal(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    (root / "tools" / "hygiene_gate.py").write_text("ROOTS = ()\n", encoding="utf-8")
    _git(root, "add", "--", "tools/hygiene_gate.py")
    assert gate.main(["--root", str(root)]) == 2


def test_a_hygiene_gate_that_will_not_import_is_a_refusal(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    (root / "tools" / "hygiene_gate.py").write_text("def (\n", encoding="utf-8")
    _git(root, "add", "--", "tools/hygiene_gate.py")
    assert gate.main(["--root", str(root)]) == 2


def test_the_refusal_is_a_distinct_exit_code_from_a_finding(tmp_path: Path) -> None:
    """Exit 1 and exit 2 must not collapse: one is a gap, one is no answer."""

    found = _repo(tmp_path / "found")
    (found / "pyproject.toml").write_text(
        PYPROJECT.replace('files = ["src", "tools"]', 'files = ["src"]'),
        encoding="utf-8",
    )
    _git(found, "add", "--", "pyproject.toml")
    assert gate.main(["--root", str(found)]) == 1

    empty = tmp_path / "empty"
    empty.mkdir()
    _git(empty, "init", "-q")
    (empty / "README.md").write_text("nothing\n", encoding="utf-8")
    _git(empty, "add", "--", "README.md")
    assert gate.main(["--root", str(empty)]) == 2
