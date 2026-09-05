"""The dependency audit's three states, asserted without a network call.

`tools/audit_gate.py` exists because pip-audit answers with two exit codes and
this repository's gates answer with three (ADR 0008). The state that matters is
the one that used to be invisible: an advisory service that never answered
looked exactly like a vulnerability, which is how a transient PyPI reset failed
the merge gate on an unrelated change (#74, observed on pull request #61).

Every test here drives the gate with a stand-in auditor, the way
`tests/test_gate_exit_contract.py` drives the secret scan with a stand-in
gitleaks. That is deliberate: a test that reached PyPI would be the flake it is
testing for, and the property under test — that "did not examine" is never
reported as clean — is a property of this gate, not of the advisory service.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

CLEAN, FOUND, UNAVAILABLE = 0, 1, 2


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "_audit_gate", REPO_ROOT / "tools" / "audit_gate.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


GATE = _load()


def _stand_in(
    directory: Path,
    *,
    report: str | None,
    exit_code: int,
    stderr: str = "",
    fail_first: int = 0,
) -> Path:
    """Write an auditor that answers with a chosen report and exit code.

    ``fail_first`` makes the first N runs behave like a dropped connection --
    no report, non-zero exit -- so the retry path can be driven without waiting
    on a real one. The attempt count is kept in a file beside the script, which
    is also what lets a test assert how many times the gate actually ran it.
    """

    directory.mkdir(parents=True, exist_ok=True)
    script = directory / "auditor.py"
    counter = directory / "attempts"
    body = f"""#!{sys.executable}
import pathlib, sys

counter = pathlib.Path({str(counter)!r})
seen = int(counter.read_text()) if counter.is_file() else 0
counter.write_text(str(seen + 1))

sys.stderr.write({stderr!r})
if seen < {fail_first}:
    sys.exit(1)

report = {report!r}
if report is not None:
    output = sys.argv[sys.argv.index("--output") + 1]
    pathlib.Path(output).write_text(report, encoding="utf-8")
sys.exit({exit_code})
"""
    script.write_text(body, encoding="utf-8")
    script.chmod(0o755)
    return script


def _attempts(auditor: Path) -> int:
    counter = auditor.parent / "attempts"
    return int(counter.read_text()) if counter.is_file() else 0


def _report(*dependencies: dict[str, Any]) -> str:
    return json.dumps({"dependencies": list(dependencies), "fixes": []})


def _clean_dependency(name: str = "certifi") -> dict[str, Any]:
    return {"name": name, "version": "2026.6.17", "vulns": []}


def _vulnerable_dependency() -> dict[str, Any]:
    return {
        "name": "example",
        "version": "1.0.0",
        "vulns": [{"id": "GHSA-fixture-0000", "fix_versions": ["1.0.1"]}],
    }


def _run(auditor: Path, *extra: str) -> int:
    return int(
        GATE.main(["--auditor", str(auditor), "--backoff", "0", *extra]),
    )


# --- the happy path ---------------------------------------------------------


def test_a_completed_audit_with_no_advisory_is_clean(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    auditor = _stand_in(
        tmp_path,
        report=_report(
            _clean_dependency(),
            {"name": "contextsafe", "skip_reason": "distribution marked as editable"},
        ),
        exit_code=CLEAN,
    )
    assert _run(auditor) == CLEAN
    out = capsys.readouterr().out
    assert "1 distribution(s) audited" in out
    assert "1 skipped as editable" in out


def test_the_clean_line_counts_what_was_audited_not_what_was_listed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A skipped distribution is not an audited one, and the line says so."""

    auditor = _stand_in(
        tmp_path,
        report=_report(
            _clean_dependency("a"),
            _clean_dependency("b"),
            {"name": "c", "skip_reason": "distribution marked as editable"},
        ),
        exit_code=CLEAN,
    )
    assert _run(auditor) == CLEAN
    assert "2 distribution(s) audited" in capsys.readouterr().out


# --- a real advisory --------------------------------------------------------


def test_an_advisory_is_a_finding(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    auditor = _stand_in(
        tmp_path,
        report=_report(_clean_dependency(), _vulnerable_dependency()),
        exit_code=FOUND,
    )
    assert _run(auditor) == FOUND
    err = capsys.readouterr().err
    assert "example 1.0.0: GHSA-fixture-0000" in err
    assert "not a failure to look" in err


def test_an_advisory_is_reported_even_when_the_auditor_exits_zero(
    tmp_path: Path,
) -> None:
    """The report decides, not the exit code.

    A gate that trusted the exit code alone would report clean over a report
    naming an advisory, which is the failure mode in the opposite direction
    from the one this file is mostly about.
    """

    auditor = _stand_in(
        tmp_path, report=_report(_vulnerable_dependency()), exit_code=CLEAN
    )
    assert _run(auditor) == FOUND


def test_an_advisory_is_never_retried(tmp_path: Path) -> None:
    """A finding is an answer. Asking again is not a second opinion."""

    auditor = _stand_in(
        tmp_path, report=_report(_vulnerable_dependency()), exit_code=FOUND
    )
    assert _run(auditor, "--attempts", "3") == FOUND
    assert _attempts(auditor) == 1


def test_an_unnamed_advisory_still_counts(tmp_path: Path) -> None:
    """An entry with no id is still a vulnerability, not a clean line."""

    auditor = _stand_in(
        tmp_path,
        report=_report(
            {"name": "example", "version": "1.0.0", "vulns": [{"fix_versions": []}, 7]}
        ),
        exit_code=FOUND,
    )
    assert _run(auditor) == FOUND


# --- the state that used to be invisible ------------------------------------


def test_an_unreachable_advisory_service_is_not_a_clean_audit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The whole point. #74's ConnectionError path writes no report.

    Before this gate, `make audit` reported that as exit 1 -- the same code as
    a real vulnerability -- and `make verify` failed with a traceback nobody
    could distinguish from a supply-chain finding.
    """

    auditor = _stand_in(
        tmp_path,
        report=None,
        exit_code=1,
        stderr="requests.exceptions.ConnectionError: Connection reset by peer\n",
    )
    assert _run(auditor, "--attempts", "1") == UNAVAILABLE
    err = capsys.readouterr().err
    assert "wrote no report" in err
    assert "not a clean result" in err
    assert "Connection reset by peer" in err


def test_the_three_states_are_three_distinct_codes(tmp_path: Path) -> None:
    """Two states is how a gate lies. These have to be three values."""

    codes = {
        _run(
            _stand_in(
                tmp_path / "clean", report=_report(_clean_dependency()), exit_code=CLEAN
            )
        ),
        _run(
            _stand_in(
                tmp_path / "found",
                report=_report(_vulnerable_dependency()),
                exit_code=FOUND,
            )
        ),
        _run(
            _stand_in(tmp_path / "silent", report=None, exit_code=1),
            "--attempts",
            "1",
        ),
    }
    assert codes == {CLEAN, FOUND, UNAVAILABLE}


def test_an_auditor_that_cannot_be_run_is_not_a_clean_audit(tmp_path: Path) -> None:
    assert _run(tmp_path / "absent", "--attempts", "1") == UNAVAILABLE


def test_a_report_that_audited_nothing_is_not_a_clean_audit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Every entry skipped is a run that established nothing about anything."""

    auditor = _stand_in(
        tmp_path,
        report=_report({"name": "contextsafe", "skip_reason": "editable"}),
        exit_code=CLEAN,
    )
    assert _run(auditor, "--attempts", "1") == UNAVAILABLE
    assert "examined no distribution" in capsys.readouterr().err


def test_an_empty_report_is_not_a_clean_audit(tmp_path: Path) -> None:
    auditor = _stand_in(tmp_path, report=_report(), exit_code=CLEAN)
    assert _run(auditor, "--attempts", "1") == UNAVAILABLE


def test_a_nonzero_exit_over_a_report_naming_no_advisory_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An unexplained disagreement establishes nothing, so it is not clean."""

    auditor = _stand_in(tmp_path, report=_report(_clean_dependency()), exit_code=FOUND)
    assert _run(auditor, "--attempts", "1") == UNAVAILABLE
    assert "disagreement is not a clean audit" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("case", "text"),
    [
        ("not JSON at all", "no known vulnerabilities found\n"),
        ("a JSON array", "[]"),
        ("no dependencies key", '{"fixes": []}'),
        ("dependencies that is not a list", '{"dependencies": 3}'),
        ("a dependency that is not an object", '{"dependencies": ["certifi"]}'),
    ],
)
def test_an_unreadable_report_is_refused(tmp_path: Path, case: str, text: str) -> None:
    """Each of these is a report that cannot answer the question asked."""

    auditor = _stand_in(tmp_path / case.replace(" ", "-"), report=text, exit_code=CLEAN)
    assert _run(auditor, "--attempts", "1") == UNAVAILABLE, case


@pytest.mark.parametrize(
    ("case", "vulns"),
    [
        ("null", None),
        ("a string", "none"),
        ("an object", {}),
        ("a number", 0),
    ],
)
def test_a_dependency_whose_vulns_field_is_not_a_list_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], case: str, vulns: object
) -> None:
    """An unreadable advisory list is a distribution nobody audited.

    It names no advisory, so it is not exit 1. It is also not exit 0: a
    `vulns` that cannot be read establishes nothing about that distribution,
    and counting it as audited would put it behind the gate's own "clean" line
    (ADR 0011). The distinction is the whole reason this file exists.
    """

    auditor = _stand_in(
        tmp_path / case.replace(" ", "-"),
        report=_report({"name": "example", "version": "1.0.0", "vulns": vulns}),
        exit_code=CLEAN,
    )
    assert _run(auditor, "--attempts", "1") == UNAVAILABLE, case
    assert "advisory list cannot be read" in capsys.readouterr().err


def test_a_dependency_with_no_vulns_field_at_all_is_refused(
    tmp_path: Path,
) -> None:
    """An absent field is not an empty one; nothing was answered about it."""

    auditor = _stand_in(
        tmp_path,
        report=_report({"name": "example", "version": "1.0.0"}),
        exit_code=CLEAN,
    )
    assert _run(auditor, "--attempts", "1") == UNAVAILABLE


def test_one_unreadable_entry_refuses_the_whole_report(
    tmp_path: Path,
) -> None:
    """Fail closed over the report, not over the entry.

    A run that audited nine distributions and could not read the tenth has not
    audited the environment, and answering 0 would report the tenth as clean.
    """

    auditor = _stand_in(
        tmp_path,
        report=_report(
            _clean_dependency("a"),
            {"name": "b", "version": "1.0.0", "vulns": None},
        ),
        exit_code=CLEAN,
    )
    assert _run(auditor, "--attempts", "1") == UNAVAILABLE


def test_an_empty_vulns_list_is_still_a_clean_answer(tmp_path: Path) -> None:
    """The boundary the refusal above must not swallow: nothing was reported."""

    auditor = _stand_in(
        tmp_path,
        report=_report({"name": "example", "version": "1.0.0", "vulns": []}),
        exit_code=CLEAN,
    )
    assert _run(auditor, "--attempts", "1") == CLEAN


# --- retries ----------------------------------------------------------------


def test_a_transient_failure_is_retried_and_then_answered(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """#61's failure: one dropped connection, then the same commit passing."""

    auditor = _stand_in(
        tmp_path,
        report=_report(_clean_dependency()),
        exit_code=CLEAN,
        fail_first=2,
    )
    assert _run(auditor, "--attempts", "3") == CLEAN
    assert _attempts(auditor) == 3
    assert "retrying in 0s" in capsys.readouterr().err


def test_retries_run_out_rather_than_running_forever(tmp_path: Path) -> None:
    auditor = _stand_in(tmp_path, report=None, exit_code=1)
    assert _run(auditor, "--attempts", "2") == UNAVAILABLE
    assert _attempts(auditor) == 2


def test_the_backoff_doubles(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A retry that does not back off is three requests at a struggling service."""

    slept: list[float] = []
    monkeypatch.setattr(GATE.time, "sleep", slept.append)
    auditor = _stand_in(tmp_path, report=None, exit_code=1)
    assert (
        int(GATE.main(["--auditor", str(auditor), "--attempts", "4", "--backoff", "1"]))
        == UNAVAILABLE
    )
    assert slept == [1.0, 2.0, 4.0]


def test_zero_attempts_is_refused_rather_than_reported_as_clean(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--attempts 0` audits nothing, and nothing audited is never clean."""

    auditor = _stand_in(tmp_path, report=_report(_clean_dependency()), exit_code=CLEAN)
    assert _run(auditor, "--attempts", "0") == UNAVAILABLE
    assert "at least 1" in capsys.readouterr().err
    assert _attempts(auditor) == 0


# --- the invocation itself --------------------------------------------------


def test_the_default_auditor_is_this_environments_pip_audit(tmp_path: Path) -> None:
    """No `--auditor` means the locked environment's own pip-audit, not a PATH lookup."""

    command = GATE.auditor_command(None, tmp_path / "report.json")
    assert command[:3] == [sys.executable, "-m", "pip_audit"]


def test_every_audit_skips_the_editable_install_and_asks_for_json(
    tmp_path: Path,
) -> None:
    """The pre-existing behaviour, kept: `--skip-editable`, plus a readable report."""

    command = GATE.auditor_command(None, tmp_path / "report.json")
    assert "--skip-editable" in command
    assert command[command.index("--format") + 1] == "json"
    assert command[command.index("--output") + 1] == str(tmp_path / "report.json")


def test_the_report_is_written_outside_the_working_tree(tmp_path: Path) -> None:
    """A gate that leaves a file behind is a gate that changes what it measures."""

    auditor = _stand_in(tmp_path, report=_report(_clean_dependency()), exit_code=CLEAN)
    before = sorted(p.name for p in REPO_ROOT.iterdir())
    assert _run(auditor) == CLEAN
    assert sorted(p.name for p in REPO_ROOT.iterdir()) == before


def test_the_stderr_tail_is_bounded(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A gate that reprints an unbounded subprocess log is a gate nobody reads."""

    noisy = "".join(f"line {n}\n" for n in range(200))
    auditor = _stand_in(tmp_path, report=None, exit_code=1, stderr=noisy)
    assert _run(auditor, "--attempts", "1") == UNAVAILABLE
    err = capsys.readouterr().err
    assert "line 199" in err
    assert "line 100" not in err


def test_an_auditor_that_says_nothing_prints_no_empty_heading(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    auditor = _stand_in(tmp_path, report=None, exit_code=1, stderr="")
    assert _run(auditor, "--attempts", "1") == UNAVAILABLE
    assert "the auditor said" not in capsys.readouterr().err
