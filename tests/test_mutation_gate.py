"""The mutation gate must report a survivor, and refuse when it has no evidence.

A gate that has only ever been seen green is a gate nobody should trust, and
that is doubly true here: this one is green on the repository today, so the only
way to know it can fail is to build a repository where it must. Both fixtures
below are the same three-line module. One is tested at its boundary and one is
not, and the gate has to tell them apart.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
GATE_PATH = REPO_ROOT / "tools" / "mutation_gate.py"


def _load_gate() -> ModuleType:
    spec = importlib.util.spec_from_file_location("mutation_gate", GATE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


gate = _load_gate()

MODULE = '''\
def over(value: int) -> bool:
    """Return whether ``value`` is over the bound."""

    return value > 10
'''

WEAK_TEST = """\
from pkg.bounds import over


def test_over() -> None:
    assert over(50) is True
"""

STRONG_TEST = """\
from pkg.bounds import over


def test_over() -> None:
    assert over(50) is True
    assert over(11) is True
    assert over(10) is False
"""

TARGETS = ("src/pkg/bounds.py",)
SCREENING = ("tests/test_bounds.py",)
PACKAGE = "src/pkg"


def _fixture(root: Path, test_source: str) -> Path:
    """Build a repository the gate can measure, and return it.

    The package sits under ``src`` and is reachable only through the directory
    the gate puts on ``PYTHONPATH``. If it sat at the root, pytest would insert
    the root ahead of that and every mutant would survive because none of them
    was ever imported.
    """

    (root / "src" / "pkg").mkdir(parents=True)
    (root / "src" / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (root / "src" / "pkg" / "bounds.py").write_text(MODULE, encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests" / "test_bounds.py").write_text(test_source, encoding="utf-8")
    return root


def _run(root: Path) -> tuple[list[object], int, int]:
    return gate.run_gate(  # type: ignore[no-any-return]
        root, targets=TARGETS, screening=SCREENING, package=PACKAGE, suite="tests"
    )


def _tree_snapshot(root: Path) -> dict[str, bytes]:
    """Every tracked-shaped file under ``root``, by relative path and content."""

    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and "__pycache__" not in path.parts
    }


def _watch_during_run(monkeypatch: pytest.MonkeyPatch, module: Path) -> list[bytes]:
    """Record ``module``'s content at the moment each test run is launched.

    A before-and-after comparison cannot distinguish a gate that never touched
    the working tree from one that mutated it and restored it in `finally`. The
    question is what was on disk while the tests were running.
    """

    seen: list[bytes] = []
    real = gate._run

    def spy(argv: object, cwd: object, env: object) -> object:
        seen.append(module.read_bytes())
        return real(argv, cwd, env)

    monkeypatch.setattr(gate, "_run", spy)
    return seen


# --- generating mutants -----------------------------------------------------


def _identities(source: str, covered: set[int]) -> list[str]:
    return [
        mutant.identity
        for mutant, _ in gate.generate("m.py", source, frozenset(covered))
    ]


def test_a_comparison_is_mutated_to_its_neighbour() -> None:
    mutants = gate.generate("m.py", "x = 1\nif x > 2:\n    pass\n", frozenset({2}))
    swapped = [source for mutant, source in mutants if mutant.operator == "comparison"]
    assert len(swapped) == 1
    assert "if x >= 2:" in swapped[0]


def test_a_boolean_operator_is_flipped() -> None:
    mutants = gate.generate("m.py", "a = 1\nb = a and a\n", frozenset({2}))
    assert [m.operator for m, _ in mutants] == ["boolean"]
    assert "a or a" in mutants[0][1]


def test_a_negation_is_removed() -> None:
    mutants = gate.generate("m.py", "a = 1\nb = not a\n", frozenset({2}))
    assert [m.operator for m, _ in mutants] == ["negation"]
    assert mutants[0][1].strip().endswith("b = a")


def test_a_boolean_constant_is_flipped() -> None:
    mutants = gate.generate("m.py", "a = True\n", frozenset({1}))
    assert [m.operator for m, _ in mutants] == ["constant"]
    assert "a = False" in mutants[0][1]


def test_a_numeric_bound_is_moved_by_one() -> None:
    mutants = gate.generate("m.py", "a = 253\n", frozenset({1}))
    assert [m.operator for m, _ in mutants] == ["bound"]
    assert "a = 254" in mutants[0][1]


def test_a_string_constant_is_not_mutated() -> None:
    """A mutated regular expression is a different program, not a bug probe."""

    assert gate.generate("m.py", "a = 'pattern'\n", frozenset({1})) == []


def test_only_covered_lines_are_mutated() -> None:
    source = "a = 1 > 2\nb = 3 > 4\n"
    assert {identity.split(":")[1] for identity in _identities(source, {1})} == {"1"}
    assert "m.py:1:4:comparison" in _identities(source, {1})
    assert _identities(source, set()) == []


def test_two_mutants_on_one_line_have_distinct_identities() -> None:
    """Column is part of the identity, or a survivor could hide behind a twin."""

    identities = _identities("a = True and True\n", {1})
    assert len(identities) == len(set(identities))


def test_mutant_order_is_deterministic() -> None:
    source = "a = 1 > 2\nb = 3 >= 4 and True\n"
    assert _identities(source, {1, 2}) == _identities(source, {1, 2})


# --- the gate ran and found something ---------------------------------------


def test_a_mutant_no_test_kills_is_reported(tmp_path: Path) -> None:
    """The proof that this gate can fail.

    ``over(50)`` is true whether the bound is ``>`` or ``>=``, so a suite that
    only asserts that case executes the line and checks nothing about it. That
    is the whole thing mutation evidence is for, and branch coverage of this
    module is 100% either way.
    """

    survivors, total, covered = _run(_fixture(tmp_path, WEAK_TEST))
    assert total >= 2
    assert covered > 0
    # Two survivors, and both are real: `over(50)` is true whether the operator
    # is `>` or `>=`, and whether the bound is 10 or 11.
    assert {survivor.description for survivor in survivors} == {
        "Gt became GtE",
        "10 became 11",
    }


def test_the_same_module_is_clean_once_the_boundary_is_asserted(
    tmp_path: Path,
) -> None:
    """Two more assertions, and the survivors are gone. Nothing else changed.

    ``over(11) is True`` kills the moved bound, ``over(10) is False`` kills the
    widened comparison. That is the shape of every fix a survivor asks for: a
    case at the edge, not more code.
    """

    survivors, total, _ = _run(_fixture(tmp_path, STRONG_TEST))
    assert survivors == []
    assert total >= 2


def test_a_survivor_is_exit_one_and_a_clean_run_is_exit_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gate, "DECLARED_TARGETS", TARGETS)
    monkeypatch.setattr(gate, "SCREENING_TESTS", SCREENING)
    monkeypatch.setattr(gate, "PACKAGE_DIR", PACKAGE)
    weak = _fixture(tmp_path / "weak", WEAK_TEST)
    strong = _fixture(tmp_path / "strong", STRONG_TEST)
    assert gate.main(["--root", str(weak)]) == 1
    assert gate.main(["--root", str(strong)]) == 0


# --- the gate produced no evidence: exit 2, never a pass --------------------


def test_a_suite_that_fails_unmutated_is_a_refusal(tmp_path: Path) -> None:
    """A mutant killed by an already-broken suite is evidence of nothing."""

    root = _fixture(tmp_path, "def test_broken() -> None:\n    assert False\n")
    with pytest.raises(gate.GateUnavailable, match="does not pass"):
        _run(root)


def test_a_target_the_tests_never_import_is_a_refusal(tmp_path: Path) -> None:
    root = _fixture(tmp_path, STRONG_TEST)
    (root / "src" / "pkg" / "unused.py").write_text("x = 1 > 2\n", encoding="utf-8")
    with pytest.raises(gate.GateUnavailable, match="executed no line"):
        gate.run_gate(
            root,
            targets=("src/pkg/unused.py",),
            screening=SCREENING,
            package=PACKAGE,
            suite="tests",
        )


def test_a_module_with_nothing_to_mutate_is_a_refusal(tmp_path: Path) -> None:
    """Zero mutants is not a suite that killed them all."""

    root = _fixture(tmp_path, STRONG_TEST)
    (root / "src" / "pkg" / "bounds.py").write_text(
        'def over(value: int) -> bool:\n    """Doc."""\n\n    return bool(value)\n',
        encoding="utf-8",
    )
    (root / "tests" / "test_bounds.py").write_text(
        "from pkg.bounds import over\n\n\ndef test_over() -> None:\n"
        "    assert over(1) is True\n",
        encoding="utf-8",
    )
    with pytest.raises(gate.GateUnavailable, match="no mutant"):
        _run(root)


def test_a_root_with_no_declared_tests_is_exit_two(tmp_path: Path) -> None:
    assert gate.main(["--root", str(tmp_path)]) == 2


def test_a_declared_path_that_is_not_in_the_tree_is_a_refusal(tmp_path: Path) -> None:
    """`SCREENING_TESTS` is a declaration, and nothing compared it to the tree.

    Rename one of the four modules it names and every screening run exits 4 --
    pytest's usage error -- which the kill decision counted as a kill. Combined,
    that printed `clean` over a run in which no test was ever collected.
    """

    root = _fixture(tmp_path, STRONG_TEST)
    with pytest.raises(gate.GateUnavailable, match="not in the tree"):
        gate.run_gate(
            root,
            targets=TARGETS,
            screening=("tests/test_renamed_away.py",),
            package=PACKAGE,
            suite="tests",
        )


@pytest.mark.parametrize("code", [2, 3, 4, 5])
def test_a_pytest_exit_that_is_not_a_verdict_is_never_a_kill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, code: int
) -> None:
    """Interrupted, internal error, usage error and nothing-collected.

    pytest returns each of these as readily as it returns 1 for a failed
    assertion, and the kill decision was `!= 0`, so each of them counted as a
    mutant killed over output that is captured and discarded.
    """

    root = _fixture(tmp_path, STRONG_TEST)
    real = gate._run
    baseline_done = {"yes": False}

    def flaky(argv: object, cwd: object, env: object) -> object:
        assert isinstance(argv, list)
        if "pytest" not in argv or not baseline_done["yes"]:
            # The unmutated baseline and the coverage report still run for real.
            baseline_done["yes"] = baseline_done["yes"] or "pytest" in argv
            return real(argv, cwd, env)
        return gate.Outcome(code, "stand-in pytest failure")

    monkeypatch.setattr(gate, "_run", flaky)
    with pytest.raises(gate.GateUnavailable, match=f"pytest exited {code}"):
        _run(root)


def test_the_gate_never_writes_to_the_working_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A mutated source file left behind would be the worst kind of side effect.

    This test asserted nothing until 2026-08-31, and ADR 0009 and the changelog
    both cited it. `gate.main` reads the module-level declarations, and they were
    not patched, so the run refused at exit 2 against the real
    `src/contextsafe` targets before it staged anything -- and then the file it
    checked was found unchanged by a run that never touched it. Its second
    assertion shelled out to `git status` in the *real* repository, which the run
    also never touched and which fails for anyone with uncommitted work in
    `src`.

    The declarations are patched now, so a whole run really does happen over the
    fixture, and the tree compared is the fixture's own.
    """

    root = _fixture(tmp_path, STRONG_TEST)
    monkeypatch.setattr(gate, "DECLARED_TARGETS", TARGETS)
    monkeypatch.setattr(gate, "SCREENING_TESTS", SCREENING)
    monkeypatch.setattr(gate, "PACKAGE_DIR", PACKAGE)

    module = root / "src" / "pkg" / "bounds.py"
    seen = _watch_during_run(monkeypatch, module)
    before = _tree_snapshot(root)

    assert gate.main(["--root", str(root)]) == 0

    # Every test run happened while the fixture's own source was unmutated, so
    # the mutants were somewhere else. Comparing only before and after would
    # pass for a gate that mutated in place and put the file back afterwards.
    assert seen, "no test run was observed, so this proves nothing"
    assert set(seen) == {module.read_bytes()}
    assert _tree_snapshot(root) == before


def test_the_working_tree_check_would_notice_a_gate_that_mutated_in_place(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The proof above has to be able to fail, or it is decoration.

    Staging is replaced by one that hands back the fixture's own package
    directory, which is what a gate mutating in place would do. The restore in
    `finally` puts the file back, so a before-and-after comparison would not
    notice; watching the file while the tests run does.
    """

    root = _fixture(tmp_path, STRONG_TEST)
    monkeypatch.setattr(gate, "DECLARED_TARGETS", TARGETS)
    monkeypatch.setattr(gate, "SCREENING_TESTS", SCREENING)
    monkeypatch.setattr(gate, "PACKAGE_DIR", PACKAGE)
    monkeypatch.setattr(gate, "_stage", lambda root, workspace, package: root / "src")

    module = root / "src" / "pkg" / "bounds.py"
    seen = _watch_during_run(monkeypatch, module)
    before = module.read_bytes()

    gate.main(["--root", str(root)])

    assert module.read_bytes() == before, "the restore in `finally` still ran"
    assert any(observed != before for observed in seen)
