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
    """Coverage declared away has to be as visible as coverage achieved.

    The loop below builds its expected strings from the same tuple the gate
    prints, so with an empty tuple it asserted nothing at all. The count is
    checked against the output independently for that reason.
    """

    assert gate.DECLARED_EXCEPTIONS, "nothing is declared away, so this proves nothing"
    gate.main(["--root", str(_repo(tmp_path))])
    out = capsys.readouterr().out
    printed = [line for line in out.splitlines() if line.startswith("scope: declared ")]
    assert len(printed) == len(gate.DECLARED_EXCEPTIONS)
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


def _claims_but_nothing_tracked(root: Path) -> Path:
    """A repository whose claims all read, with no tracked Python to compare.

    The three refusal tests below used a repository with no Makefile and no
    `pyproject.toml` either, so each of them passed on whichever refusal came
    first rather than on the one it names. Replacing `if not files:` with
    `if False:` left all of them green -- the gate's most-argued property was
    unpinned. The claim files are on disk and unstaged here, so `git ls-files`
    reports nothing while every claim still reads.
    """

    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q")
    (root / "Makefile").write_text(MAKEFILE, encoding="utf-8")
    (root / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    (root / "tools").mkdir(exist_ok=True)
    (root / "tools" / "hygiene_gate.py").write_text(HYGIENE_STUB, encoding="utf-8")
    (root / "README.md").write_text("no tracked python here\n", encoding="utf-8")
    _git(root, "add", "--", "README.md")
    return root


def test_a_repository_with_no_tracked_python_is_a_refusal(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Every claim holds vacuously over an empty tree, which is not a pass."""

    root = _claims_but_nothing_tracked(tmp_path / "unstaged")
    # Every other refusal path is out of the way: the claims all read.
    assert gate.collect_analyses(root)
    assert gate.main(["--root", str(root)]) == 2
    assert "lists no tracked Python file" in capsys.readouterr().err


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


GOOD_TEST_TARGET = "\n\ntest:\n\tuv run pytest --cov --cov-branch\n"
GOOD_TYPECHECK_TARGET = "typecheck:\n\tuv run mypy --strict\n\n"


@pytest.mark.parametrize(
    ("case", "recipe"),
    [
        # The two spellings the check was written against.
        ("a bare path", "typecheck:\n\tuv run mypy --strict src" + GOOD_TEST_TARGET),
        (
            "--cov with its value attached",
            GOOD_TYPECHECK_TARGET + "test:\n\tuv run pytest --cov=contextsafe\n",
        ),
        # Every one of these passed the check clean until 2026-08-31. The rule
        # was four string literals compared to whole tokens on the first line
        # mentioning the tool; each of these is a different spelling of the same
        # override, and one is a different line.
        (
            "a trailing slash",
            "typecheck:\n\tuv run mypy --strict src/" + GOOD_TEST_TARGET,
        ),
        (
            "a quoted path",
            'typecheck:\n\tuv run mypy --strict "src"' + GOOD_TEST_TARGET,
        ),
        (
            "a make variable",
            "typecheck:\n\tuv run mypy --strict $(SRC)" + GOOD_TEST_TARGET,
        ),
        (
            "an argument on a continuation line",
            "typecheck:\n\tuv run mypy --strict \\\n\t\tsrc" + GOOD_TEST_TARGET,
        ),
        (
            "a comment line above the real one",
            "typecheck:\n\t# runs mypy over the configured files\n"
            "\tuv run mypy --strict src" + GOOD_TEST_TARGET,
        ),
        (
            "--cov with its value as the next word",
            GOOD_TYPECHECK_TARGET + "test:\n\tuv run pytest --cov contextsafe\n",
        ),
    ],
)
def test_a_command_that_overrides_the_configured_scope_is_a_refusal(
    tmp_path: Path, case: str, recipe: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """A path on the command line beats the config, so the claim moves."""

    root = _repo(tmp_path)
    (root / "Makefile").write_text(recipe, encoding="utf-8")
    _git(root, "add", "--", "Makefile")
    assert gate.main(["--root", str(root)]) == 2, case
    err = capsys.readouterr().err
    # Either the argument plainly overrides the configured scope, or the gate
    # cannot tell what it is. Both are exit 2: "I cannot establish the claim" is
    # never a pass here, and a gate that guessed would be guessing about scope.
    assert "is not what that command examines" in err, case
    assert "not a clean result" in err, case


def test_a_comment_naming_the_tool_does_not_satisfy_the_check(tmp_path: Path) -> None:
    """A recipe comment is not a command, and this repository's `sync` has one."""

    root = _repo(tmp_path)
    (root / "Makefile").write_text(
        "typecheck:\n\t# this line mentions mypy and runs nothing\n\techo skipped\n"
        + GOOD_TEST_TARGET,
        encoding="utf-8",
    )
    _git(root, "add", "--", "Makefile")
    assert gate.main(["--root", str(root)]) == 2


@pytest.mark.parametrize("root_value", ['(".",)', '("",)', '("./",)'])
def test_a_root_that_claims_the_whole_tree_is_a_refusal(
    tmp_path: Path, root_value: str
) -> None:
    """`MARKER_ROOTS = (".",)` made every file claimed and nothing could fail.

    The gate already refuses a comparison with no files on the grounds that it
    cannot fail. A root that is true of every path is the same tautology from
    the other side, and it reported clean.
    """

    root = _repo(tmp_path)
    (root / "tools" / "hygiene_gate.py").write_text(
        f"MARKER_ROOTS: tuple[str, ...] = {root_value}\n", encoding="utf-8"
    )
    _git(root, "add", "--", "tools/hygiene_gate.py")
    assert gate.main(["--root", str(root)]) == 2


@pytest.mark.parametrize(
    "body",
    [
        "import a_module_that_is_not_installed\n",
        "raise ValueError('nope')\n",
        "MARKER_ROOTS = undefined_name\n",
    ],
)
def test_a_hygiene_gate_that_raises_anything_is_a_refusal(
    tmp_path: Path, body: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """Executing another module's top level can raise anything at all.

    The guard caught `(OSError, SyntaxError)`, so each of these escaped as a
    traceback and exit 1 -- "examined and found something" from a gate that
    never read the claim.
    """

    root = _repo(tmp_path)
    (root / "tools" / "hygiene_gate.py").write_text(body, encoding="utf-8")
    _git(root, "add", "--", "tools/hygiene_gate.py")
    assert gate.main(["--root", str(root)]) == 2
    assert "could not be loaded" in capsys.readouterr().err


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

    assert (
        gate.main(["--root", str(_claims_but_nothing_tracked(tmp_path / "empty"))]) == 2
    )
