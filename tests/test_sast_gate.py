"""The SAST gate must fail on a file the scanner could not finish reading.

The defect this closes is #114. The scanner's parser stopped at a PEP 695
generic function in `src/contextsafe/validation.py` -- a safety module -- and
reported the rest of the module as partially analyzed, in a warning that left
the job green. It went red only on a branch whose file set was larger, which
means the verdict depended on the size of the tree rather than on the code.

So the load-bearing cases here are: a clean report passes and says what it
counted; a rule match is exit 1; a partial parse is exit 2 and not exit 1, even
when the same run also carries a real finding; a report that lists a scanned
file set missing one of the sources this gate claims is exit 2; and every way of
not getting a report at all -- absent scanner, a scanner that did not complete,
no file written, unreadable, not JSON, or JSON in a shape this gate does not
understand -- is exit 2 rather than a clean scan of nothing.

The error shapes below are the scanner's own, copied from a semgrep 1.175.0
`--json` run over a file with a syntax error in it, not invented here.

One more thing is asserted rather than described: the constraint ADR 0012
records. While this scanner is the SAST gate, no function or class in the trees
the gate claims may carry PEP 695 type parameters, because that is the construct
the parser stopped at. `pyproject.toml` ignores ruff's UP047 for the same
reason; this is what makes the rule enforceable rather than remembered.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import subprocess
import sys
import tomllib
from collections.abc import Sequence
from pathlib import Path, PurePosixPath
from types import ModuleType
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
GATE_PATH = REPO_ROOT / "tools" / "sast_gate.py"

CLEAN, FOUND, UNAVAILABLE = 0, 1, 2


def _load_gate() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_sast_gate_under_test", GATE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


gate = _load_gate()


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)  # noqa: S607


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A repository with two tracked sources under the trees the gate claims."""

    root = tmp_path / "repo"
    (root / "src" / "pkg").mkdir(parents=True)
    (root / "tools").mkdir()
    (root / "src" / "pkg" / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / "tools" / "gate.py").write_text("VALUE = 2\n", encoding="utf-8")
    (root / "README.md").write_text("not python\n", encoding="utf-8")
    _git(root.parent, "init", "-q", root.name)
    _git(root, "add", "--", "src", "tools", "README.md")
    return root


SOURCES = ("src/pkg/module.py", "tools/gate.py")


def _report(
    *,
    scanned: Sequence[str] = SOURCES,
    errors: Sequence[dict[str, Any]] = (),
    results: Sequence[dict[str, Any]] = (),
    version: str = gate.PINNED_SCANNER_VERSION,
) -> dict[str, Any]:
    """A report in the scanner's own shape.

    ``version`` defaults to the pinned one because every other case here is
    about something else; the pin has its own tests below. The key is where
    semgrep writes it, at the top level of the `--json` document.
    """

    return {
        "version": version,
        "results": list(results),
        "errors": list(errors),
        "paths": {"scanned": list(scanned)},
    }


PARTIAL_PARSE_ERROR: dict[str, Any] = {
    "code": 3,
    "level": "warn",
    "type": [
        "PartialParsing",
        [{"path": "src/pkg/module.py", "start": {"line": 6, "col": 5}}],
    ],
    "message": "Syntax error at line src/pkg/module.py:6:\n `???` was unexpected",
    "path": "src/pkg/module.py",
}

RULE_MATCH: dict[str, Any] = {
    "check_id": "python.lang.security.audit.eval-detected",
    "path": "src/pkg/module.py",
    "start": {"line": 9, "col": 12},
    "extra": {"severity": "ERROR"},
}


def _judge(
    repo: Path, report: dict[str, Any], tmp_path: Path, *, extra: Sequence[str] = ()
) -> int:
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    return int(gate.main(["--root", str(repo), "--report", str(path), *extra]))


# --- the three states -------------------------------------------------------


def test_a_fully_parsed_scan_with_no_match_is_clean(
    repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _judge(repo, _report(), tmp_path) == CLEAN
    out = capsys.readouterr().out
    assert "2 file(s) scanned and fully parsed" in out
    assert "2 tracked source(s)" in out
    assert f"semgrep {gate.PINNED_SCANNER_VERSION}" in out


def test_a_rule_match_is_a_finding(repo: Path, tmp_path: Path) -> None:
    assert _judge(repo, _report(results=[RULE_MATCH]), tmp_path) == FOUND


def test_a_partial_parse_is_a_failure_to_examine_not_a_finding(
    repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """#114 itself: the scanner exits 0 over this and calls it a warning."""

    assert _judge(repo, _report(errors=[PARTIAL_PARSE_ERROR]), tmp_path) == UNAVAILABLE
    err = capsys.readouterr().err
    assert "partial-parse: src/pkg/module.py" in err
    assert "not a finding about the code" in err


def test_a_partial_parse_beside_a_real_finding_is_still_a_failure_to_examine(
    repo: Path, tmp_path: Path
) -> None:
    """The finding set is incomplete and nothing in it says so, so refusal wins."""

    report = _report(errors=[PARTIAL_PARSE_ERROR], results=[RULE_MATCH])
    assert _judge(repo, report, tmp_path) == UNAVAILABLE


def test_any_other_analysis_error_is_also_a_failure_to_examine(
    repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A rule abandoned on a file has not examined that file.

    This is the scanner's own Timeout shape, which is why the gate runs the scan
    with no per-rule limit: with the default one, the registry configuration
    produced 16 of these over this repository on 2026-09-05, so the verdict
    would have tracked how loaded the machine was. Reported here rather than
    excused, in case one survives the flag.
    """

    error = {
        "level": "warn",
        "type": "Timeout",
        "code": 2,
        "rule_id": "python.lang.security.dangerous-system-call",
        "message": "Timeout when running a rule on tools/gate.py",
        "path": "tools/gate.py",
    }
    assert _judge(repo, _report(errors=[error]), tmp_path) == UNAVAILABLE
    assert "analysis-error: tools/gate.py" in capsys.readouterr().err


def test_an_error_entry_the_gate_cannot_read_is_not_a_clean_run(
    repo: Path, tmp_path: Path
) -> None:
    assert _judge(repo, _report(errors=["a bare string"]), tmp_path) == UNAVAILABLE


def test_a_result_entry_the_gate_cannot_read_is_still_a_finding(
    repo: Path, tmp_path: Path
) -> None:
    assert _judge(repo, _report(results=["a bare string"]), tmp_path) == FOUND


def test_a_result_without_a_line_is_reported_by_path(
    repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    match = {"check_id": "some.rule", "path": "tools/gate.py"}
    assert _judge(repo, _report(results=[match]), tmp_path) == FOUND
    assert "scanner-finding: tools/gate.py: some.rule" in capsys.readouterr().err


# --- the denominator: what the scan is held to ------------------------------


def test_a_source_the_scanner_never_opened_is_a_hole(
    repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The gate's own subject one level up: clean over a file nobody read."""

    report = _report(scanned=["src/pkg/module.py"])
    assert _judge(repo, report, tmp_path) == UNAVAILABLE
    assert "unscanned-source: tools/gate.py" in capsys.readouterr().err


def test_a_scan_of_nothing_is_not_a_clean_scan(
    repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """ADR 0004's Defect 2 -- a green SAST check over zero scanned files.

    The exit code alone does not test this guard: with nothing scanned, the
    coverage check below already emits a finding per tracked source and would
    carry the same exit 2 with the guard deleted. So the assertion is on the
    guard's own message, and removing it changes this result.
    """

    assert _judge(repo, _report(scanned=[]), tmp_path) == UNAVAILABLE
    assert "zero scanned files" in capsys.readouterr().err


def test_a_source_deleted_from_the_working_tree_is_not_demanded_of_the_scanner(
    repo: Path, tmp_path: Path
) -> None:
    """`git ls-files` lists the index, and the scanner walks the working tree.

    A tracked file deleted and not yet staged is in one and not the other. The
    gate would otherwise fail by name over a file nothing can read because it is
    not there -- fail-closed, but a denominator that counts absent files is not
    the denominator it claims.
    """

    (repo / "tools" / "gate.py").unlink()
    assert _judge(repo, _report(scanned=["src/pkg/module.py"]), tmp_path) == CLEAN


def test_a_report_that_does_not_say_what_it_scanned_is_refused(
    repo: Path, tmp_path: Path
) -> None:
    report = _report()
    report["paths"] = {"skipped": []}
    assert _judge(repo, report, tmp_path) == UNAVAILABLE


def test_the_version_control_tool_being_absent_is_not_a_clean_scan(
    repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The list of sources the scan is held to is read through git.

    Without it the gate has no denominator, and a gate with no denominator has
    no clean result -- the same reason `make hygiene` refuses.
    """

    empty = tmp_path / "no-tools"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    assert _judge(repo, _report(), tmp_path) == UNAVAILABLE
    assert "not on PATH" in capsys.readouterr().err


def test_a_tree_with_no_tracked_python_leaves_the_gate_nothing_to_hold_to(
    tmp_path: Path,
) -> None:
    root = tmp_path / "empty"
    root.mkdir()
    (root / "README.md").write_text("no python here\n", encoding="utf-8")
    _git(tmp_path, "init", "-q", root.name)
    _git(root, "add", "--", "README.md")
    assert _judge(root, _report(scanned=["README.md"]), tmp_path) == UNAVAILABLE


def test_a_root_that_is_not_a_repository_is_refused(tmp_path: Path) -> None:
    outside = tmp_path / "not-a-repo"
    outside.mkdir()
    assert _judge(outside, _report(), tmp_path) == UNAVAILABLE


# --- every way of not having a report at all --------------------------------


def test_a_report_that_is_not_there_is_not_a_clean_scan(
    repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "never-written.json"
    assert gate.main(["--root", str(repo), "--report", str(missing)]) == UNAVAILABLE
    assert "not a clean result" in capsys.readouterr().err


def test_a_report_that_is_not_json_is_not_a_clean_scan(
    repo: Path, tmp_path: Path
) -> None:
    path = tmp_path / "report.json"
    path.write_text("not json at all", encoding="utf-8")
    assert gate.main(["--root", str(repo), "--report", str(path)]) == UNAVAILABLE


def test_a_report_that_is_not_an_object_is_not_a_clean_scan(
    repo: Path, tmp_path: Path
) -> None:
    path = tmp_path / "report.json"
    path.write_text("[]", encoding="utf-8")
    assert gate.main(["--root", str(repo), "--report", str(path)]) == UNAVAILABLE


@pytest.mark.parametrize("key", ["results", "errors", "paths"])
def test_a_report_missing_a_key_this_gate_reads_is_refused(
    repo: Path, tmp_path: Path, key: str
) -> None:
    """Fail closed on the document itself.

    A missing key read as an empty list is no errors, no findings and no scanned
    files: a clean verdict derived from a report the gate did not understand.
    """

    report = _report()
    del report[key]
    assert _judge(repo, report, tmp_path) == UNAVAILABLE


# --- which scanner the verdict is about -------------------------------------


def test_a_report_from_an_unpinned_scanner_is_not_a_clean_scan(
    repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A shared argv is not a shared scan while the parsers differ.

    This is #114 one layer over. The pinned CI scanner cannot read a PEP 695
    generic function; a newer one reads it without complaint. If this gate took
    whatever semgrep is on a maintainer's PATH, `make sast` would report clean
    over exactly the construct the job cannot finish -- a green result about a
    scan CI never ran.
    """

    assert _judge(repo, _report(version="1.175.0"), tmp_path) == UNAVAILABLE
    err = capsys.readouterr().err
    assert "semgrep 1.175.0 produced this report" in err
    assert gate.PINNED_SCANNER_VERSION in err
    assert "not a clean result" in err


def test_running_an_unpinned_scanner_can_be_chosen_and_is_then_declared(
    repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The secret scan's escape hatch, spelled the same and just as loud."""

    code = _judge(
        repo, _report(version="1.175.0"), tmp_path, extra=["--allow-version-drift"]
    )
    assert code == CLEAN
    captured = capsys.readouterr()
    assert "WARNING - semgrep 1.175.0 is not the pinned" in captured.err
    assert "semgrep 1.175.0" in captured.out


def test_the_drift_override_is_taken_from_the_environment(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(gate.VERSION_DRIFT_ENV, "1")
    assert _judge(repo, _report(version="1.175.0"), tmp_path) == CLEAN
    monkeypatch.setenv(gate.VERSION_DRIFT_ENV, "yes")
    assert _judge(repo, _report(version="1.175.0"), tmp_path) == UNAVAILABLE


@pytest.mark.parametrize("version", [None, "", "   ", 1168, ["1.168.0"]])
def test_a_report_that_does_not_name_its_scanner_is_refused(
    repo: Path, tmp_path: Path, version: Any
) -> None:
    """Fail closed on the pin too: an unnamed scanner cannot be the pinned one."""

    report = _report()
    if version is None:
        del report["version"]
    else:
        report["version"] = version
    assert _judge(repo, report, tmp_path) == UNAVAILABLE


def test_the_pinned_scanner_is_the_one_the_workflow_runs() -> None:
    """Re-derived from the workflow, not kept in step by hand.

    The container is pinned by digest, so the version it is lives in the comment
    beside it -- which `tests/test_ci_workflows.py` already requires every pinned
    image and action to carry. Reading it here is what keeps the gate's pin and
    the job's image from drifting apart silently, which is the failure this whole
    gate is about wearing a different hat.
    """

    workflow = (REPO_ROOT / ".github" / "workflows" / "security.yml").read_text(
        encoding="utf-8"
    )
    pinned = [
        line.split("#", 1)[1].strip()
        for line in workflow.splitlines()
        if "image: semgrep/semgrep@sha256:" in line and "#" in line
    ]
    assert pinned == [gate.PINNED_SCANNER_VERSION], (
        "the SAST job's container and tools/sast_gate.py PINNED_SCANNER_VERSION "
        f"disagree: the workflow names {pinned}"
    )


def test_the_gate_claims_the_trees_the_other_analyses_do() -> None:
    """`SCAN_ROOTS` is a fourth copy of a scope `make scope` does not read.

    `make scope` reads `[tool.mypy] files`, `[tool.coverage.run] source` and the
    marker scan's own tuple, so a third tree of Python adopted by those would
    satisfy it while quietly falling outside this gate's denominator. This is
    what holds the copy to the claims: every tree either configuration names
    must be inside a root this gate scans, and every root this gate scans must
    be named by one of them.
    """

    with (REPO_ROOT / "pyproject.toml").open("rb") as handle:
        config = tomllib.load(handle)
    claimed = tuple(config["tool"]["mypy"]["files"]) + tuple(
        config["tool"]["coverage"]["run"]["source"]
    )
    for tree in claimed:
        assert any(
            PurePosixPath(tree).parts[: len(PurePosixPath(root).parts)]
            == PurePosixPath(root).parts
            for root in gate.SCAN_ROOTS
        ), f"{tree} is analysed elsewhere and outside the SAST gate's SCAN_ROOTS"
    for root in gate.SCAN_ROOTS:
        assert any(
            PurePosixPath(tree).parts[: len(PurePosixPath(root).parts)]
            == PurePosixPath(root).parts
            for tree in claimed
        ), f"{root} is claimed by the SAST gate and by no other analysis"


# --- driving the scanner ----------------------------------------------------


def _stand_in_scanner(
    directory: Path, *, report: dict[str, Any] | None, code: int = 0
) -> Path:
    """A scanner that records its argv and writes the report it was given.

    The real scanner is not in `uv.lock` and a clean clone does not carry it,
    which is why this gate sits outside `make verify`. Driving it with a stand-in
    is what lets the run path be checked anyway, including that the argv the gate
    builds carries the config and the output path it claims to.
    """

    path = directory / "stand-in-semgrep"
    log = directory / "argv.log"
    body = [
        "#!/usr/bin/env bash",
        f'printf "%s\\n" "$*" >>"{log}"',
        'out=""',
        'prev=""',
        'for arg in "$@"; do',
        '  if [ "$prev" = "--output" ]; then out="$arg"; fi',
        '  prev="$arg"',
        "done",
    ]
    if report is not None:
        body.append(f"cat >\"$out\" <<'JSON'\n{json.dumps(report)}\nJSON")
    body.append(f"exit {code}")
    path.write_text("\n".join(body) + "\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def _argv(binary: Path) -> str:
    return (binary.parent / "argv.log").read_text(encoding="utf-8")


def test_the_gate_runs_the_scanner_and_judges_what_it_wrote(
    repo: Path, tmp_path: Path
) -> None:
    binary = _stand_in_scanner(tmp_path, report=_report())
    assert gate.main(["--root", str(repo), "--semgrep", str(binary)]) == CLEAN
    invocation = _argv(binary)
    assert invocation.startswith("scan --config auto --timeout 0 --json --output ")


def test_the_scan_the_gate_runs_is_the_one_it_was_asked_for(
    repo: Path, tmp_path: Path
) -> None:
    binary = _stand_in_scanner(tmp_path, report=_report(errors=[PARTIAL_PARSE_ERROR]))
    code = gate.main(
        ["--root", str(repo), "--semgrep", str(binary), "--config", "p/python"]
    )
    assert code == UNAVAILABLE
    assert "--config p/python" in _argv(binary)


def test_an_absent_scanner_is_not_a_clean_scan(
    repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The failure most easily mistaken for a clean one."""

    absent = tmp_path / "no-such-scanner"
    assert gate.main(["--root", str(repo), "--semgrep", str(absent)]) == UNAVAILABLE
    assert "the scanner was not found" in capsys.readouterr().err


def test_a_scanner_that_did_not_complete_is_not_a_clean_scan(
    repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Exit 3 is the code the scanner uses for an analysis error it could not pass."""

    binary = _stand_in_scanner(tmp_path, report=_report(), code=3)
    assert gate.main(["--root", str(repo), "--semgrep", str(binary)]) == UNAVAILABLE
    assert "exited 3" in capsys.readouterr().err


def test_a_scanner_that_wrote_no_report_is_not_a_clean_scan(
    repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    binary = _stand_in_scanner(tmp_path, report=None)
    assert gate.main(["--root", str(repo), "--semgrep", str(binary)]) == UNAVAILABLE
    assert "wrote no report" in capsys.readouterr().err


# --- the rules, and the constraint the gate puts on this codebase -----------


def test_every_rule_the_gate_emits_has_a_declared_exit_code() -> None:
    """A rule in neither list has an exit code nobody decided on.

    Driven rather than restated: each producer is called and the rules it
    actually emits are compared with the two declared sets, in both directions,
    so a rule added later without a classification fails here and a declared
    rule the gate never emits does too.
    """

    emitted = {
        finding.rule_id
        for finding in gate.error_findings(
            _report(
                errors=[
                    PARTIAL_PARSE_ERROR,
                    {"type": "Timeout", "message": "rule timed out"},
                    "not a mapping",
                ]
            )
        )
    }
    emitted |= {f.rule_id for f in gate.result_findings(_report(results=[RULE_MATCH]))}
    emitted |= {
        f.rule_id for f in gate.coverage_findings(["src/pkg/module.py"], frozenset())
    }
    assert emitted == gate.UNAVAILABLE_RULES | gate.DEFECT_RULES
    assert not (gate.UNAVAILABLE_RULES & gate.DEFECT_RULES)


def test_the_three_states_are_three_distinct_codes() -> None:
    defect = gate.Finding(gate.SCANNER_FINDING, "src/pkg/module.py:9", "some.rule")
    unread = gate.Finding(gate.PARTIAL_PARSE, "src/pkg/module.py", "syntax error")
    assert gate.exit_code([]) == CLEAN
    assert gate.exit_code([defect]) == FOUND
    assert gate.exit_code([unread]) == UNAVAILABLE
    assert gate.exit_code([defect, unread]) == UNAVAILABLE


def _tracked_python() -> list[Path]:
    listing = subprocess.run(
        ["git", "ls-files", "-z", "--", *gate.SCAN_ROOTS],  # noqa: S607
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    ).stdout.decode("utf-8")
    files = [REPO_ROOT / part for part in listing.split("\0") if part.endswith(".py")]
    assert files, "no tracked source was read, so the check below examined nothing"
    return files


def _pep695_offenders(source: str, label: str) -> list[str]:
    """Every PEP 695 type parameter list on a function or class in ``source``.

    One predicate, used by both tests below: the constraint over the real tree,
    and the two directions that show what the constraint is. A second copy of
    the rule written for the second test would be a check that cannot disagree
    with the first, which is the shape this gate exists to remove.
    """

    kinds = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
    return [
        f"{label}:{node.lineno}"
        for node in ast.walk(ast.parse(source))
        if isinstance(node, kinds) and node.type_params
    ]


def test_no_source_uses_pep695_type_parameters_on_a_function_or_class() -> None:
    """ADR 0012's constraint, asserted rather than left in a config comment.

    `def _enum[T: StrEnum](...)` is where the scanner's parser stopped, and the
    rest of a safety module went unread behind it. The PEP 695 `type` alias form
    is unaffected and is deliberately not what this checks.
    """

    offenders = [
        offender
        for path in _tracked_python()
        for offender in _pep695_offenders(
            path.read_text(encoding="utf-8"), str(path.relative_to(REPO_ROOT))
        )
    ]
    assert offenders == [], (
        "PEP 695 type parameters on a function or class; the SAST parser stops "
        "there and reports the rest of the module as partially analyzed. Use a "
        "TypeVar instead. See docs/adr/0012-sast-partial-parse-and-the-syntax-"
        "it-forbids.md"
    )


def test_the_constraint_bans_the_generic_form_and_not_the_type_alias() -> None:
    """Both directions of the predicate the check above runs, not a copy of it.

    The ban has to catch `def f[T](...)` and it must not catch `type X = ...`,
    which four modules use. Asserting the second against a re-implemented,
    weaker predicate would pass no matter what the real one did.
    """

    assert _pep695_offenders("type Rows = list[str]\n", "alias.py") == []
    assert _pep695_offenders("def f[T](x: T) -> T: ...\n", "generic.py") == [
        "generic.py:1"
    ]
    assert _pep695_offenders("class C[T]:\n    pass\n", "generic.py") == [
        "generic.py:1"
    ]
