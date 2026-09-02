"""The accessibility gate, and every way it is made to fail.

A gate that can report success without having examined anything is worse than
no gate, because it converts an absence of evidence into a claim. So the
assertions here are mostly negative controls: point the gate at an error page,
at an empty page set, at a page rendered from a different receipt, at a page
whose status is carried by colour alone, and require it to fail each time and
name the reason.

The one test that exercises axe-core itself is skipped when the node harness is
not installed — but a companion test that always runs asserts that requesting
axe without the harness produces ``engine-unavailable`` rather than a pass, so
a missing engine can never be mistaken for a clean result at the gate level.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
GATE_PATH = REPO_ROOT / "tools" / "a11y_gate.py"

_ERROR_PAGE = (
    '<!DOCTYPE html>\n<html lang="en-US"><head><meta charset="utf-8">'
    "<title>404 Not Found</title></head><body><h1>404 Not Found</h1>"
    "<p>The requested page does not exist.</p></body></html>\n"
)


def _load_gate() -> ModuleType:
    spec = importlib.util.spec_from_file_location("a11y_gate", GATE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


gate = _load_gate()

HARNESS_INSTALLED = gate.HARNESS_MODULES.is_dir()


@pytest.fixture
def subjects() -> tuple[object, ...]:
    """Return the real rendered pages the gate audits."""

    return gate.build_subjects(("en-US", "es-US"))


def _replace(subject: object, html: str) -> object:
    return gate.Subject(
        name=subject.name,  # type: ignore[attr-defined]
        locale=subject.locale,  # type: ignore[attr-defined]
        html=html,
        payload_sha256=subject.payload_sha256,  # type: ignore[attr-defined]
        case_id=subject.case_id,  # type: ignore[attr-defined]
        required_text=subject.required_text,  # type: ignore[attr-defined]
    )


def _rules(report: object) -> set[str]:
    return {finding.rule for finding in report.findings}  # type: ignore[attr-defined]


def _audit(
    subjects: tuple[object, ...],
    tmp_path: Path,
    engines: tuple[str, ...] = ("builtin",),
) -> object:
    return gate.audit(subjects, engines=engines, workdir=tmp_path)


def test_the_real_pages_pass_the_builtin_checks(
    subjects: tuple[object, ...], tmp_path: Path
) -> None:
    """The shipped pages have to pass the gate the repository ships."""

    report = _audit(subjects, tmp_path)
    assert report.findings == []  # type: ignore[attr-defined]
    assert report.audited == report.declared == 2  # type: ignore[attr-defined]


def test_every_builtin_check_examined_something(
    subjects: tuple[object, ...], tmp_path: Path
) -> None:
    """A clean result is only meaningful if the check looked at something."""

    report = _audit(subjects, tmp_path)
    examined = {check.name: check.examined for check in report.checks}  # type: ignore[attr-defined]
    assert set(examined) == set(gate.BUILTIN_CHECKS)
    assert all(count > 0 for count in examined.values()), examined


def test_an_empty_page_set_fails_instead_of_passing(tmp_path: Path) -> None:
    """The failure this whole design is aimed at: exit 0 on nothing."""

    report = _audit((), tmp_path)
    assert _rules(report) == {"no-pages"}
    assert report.audited == 0  # type: ignore[attr-defined]


def test_an_error_page_is_refused_rather_than_reported_clean(
    subjects: tuple[object, ...], tmp_path: Path
) -> None:
    """A 404 page has no violations. That is not the same as being fine."""

    report = _audit((_replace(subjects[0], _ERROR_PAGE),), tmp_path)
    rules = _rules(report)
    assert "wrong-subject" in rules
    assert "coverage" in rules
    assert report.audited == 0  # type: ignore[attr-defined]


def test_an_empty_file_is_refused(subjects: tuple[object, ...], tmp_path: Path) -> None:
    """Neither does an empty page have violations."""

    report = _audit((_replace(subjects[0], "   "),), tmp_path)
    assert "wrong-subject" in _rules(report)


def test_a_page_rendered_from_another_receipt_is_refused(
    subjects: tuple[object, ...], tmp_path: Path
) -> None:
    """The expected hash comes from the receipt, not from the page."""

    subject = subjects[0]
    swapped = _replace(
        subject,
        subject.html.replace(  # type: ignore[attr-defined]
            subject.payload_sha256,  # type: ignore[attr-defined]
            "0" * 64,
        ),
    )
    report = _audit((swapped,), tmp_path)
    assert "wrong-subject" in _rules(report)
    detail = " ".join(finding.detail for finding in report.findings)  # type: ignore[attr-defined]
    assert "payload hash" in detail


def test_a_page_missing_a_mandated_limitation_is_refused(
    subjects: tuple[object, ...], tmp_path: Path
) -> None:
    """Dropping a required disclosure must not be an accessible page."""

    subject = subjects[0]
    stripped = _replace(
        subject,
        subject.html.replace(subject.required_text[0], ""),  # type: ignore[attr-defined]
    )
    report = _audit((stripped,), tmp_path)
    assert "wrong-subject" in _rules(report)


def test_a_contrast_violation_is_caught(
    subjects: tuple[object, ...], tmp_path: Path
) -> None:
    """Grey on white is the classic one, and it must not pass."""

    subject = subjects[0]
    broken = _replace(
        subject,
        subject.html.replace(  # type: ignore[attr-defined]
            "dt { background-color: #ffffff; color: #3d3d3d;",
            "dt { background-color: #ffffff; color: #b8b8b8;",
        ),
    )
    report = _audit((broken,), tmp_path)
    assert "contrast" in _rules(report)
    assert any(":1, below" in f.detail for f in report.findings)  # type: ignore[attr-defined]


def test_a_colour_with_no_background_is_caught(
    subjects: tuple[object, ...], tmp_path: Path
) -> None:
    """An unknowable pair is how a contrast check quietly examines nothing."""

    subject = subjects[0]
    broken = _replace(
        subject,
        subject.html.replace(  # type: ignore[attr-defined]
            "dt { background-color: #ffffff; color: #3d3d3d;",
            "dt { color: #3d3d3d;",
        ),
    )
    report = _audit((broken,), tmp_path)
    assert any("cannot be checked" in f.detail for f in report.findings)  # type: ignore[attr-defined]


def test_status_carried_by_colour_alone_is_caught(
    subjects: tuple[object, ...], tmp_path: Path
) -> None:
    """Remove the word and the symbol and only the class remains."""

    subject = subjects[0]
    without_symbol = subject.html.replace(  # type: ignore[attr-defined]
        'class="status-symbol"', 'class="swatch"'
    )
    report = _audit((_replace(subject, without_symbol),), tmp_path)
    assert "color-only" in _rules(report)
    assert any("non-colour symbol" in f.detail for f in report.findings)  # type: ignore[attr-defined]


def test_status_with_no_published_label_is_caught(
    subjects: tuple[object, ...], tmp_path: Path
) -> None:
    """A symbol on its own is still an encoding a reader has to decode."""

    subject = subjects[0]
    without_word = subject.html.replace(">Pass<", "><")  # type: ignore[attr-defined]
    report = _audit((_replace(subject, without_word),), tmp_path)
    assert any("no published text label" in f.detail for f in report.findings)  # type: ignore[attr-defined]


def test_a_missing_print_stylesheet_is_caught(
    subjects: tuple[object, ...], tmp_path: Path
) -> None:
    """The receipt is a document people print."""

    subject = subjects[0]
    html = subject.html  # type: ignore[attr-defined]
    start = html.index("@media print {")
    end = html.index("\n}", start) + 2
    report = _audit((_replace(subject, html[:start] + html[end:]),), tmp_path)
    rules = _rules(report)
    assert "print" in rules or "check-examined-nothing" in rules


def test_hiding_a_disclosure_in_print_is_caught(
    subjects: tuple[object, ...], tmp_path: Path
) -> None:
    """Printing must not be a way to lose the safety notice."""

    subject = subjects[1]
    broken = subject.html.replace(  # type: ignore[attr-defined]
        "  .skip-link { display: none; }",
        "  .skip-link { display: none; }\n  .notice { display: none; }",
    )
    report = _audit((_replace(subject, broken),), tmp_path)
    assert any("hides content" in f.detail for f in report.findings)  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("mutation", "needle"),
    [
        (("<style>", "<script>void 0;</script><style>"), "<script"),
        (('<main id="receipt"', '<main id="scope"'), "duplicate ids"),
        (("</footer>", "</footer></section>"), "unbalanced"),
        (("<h3 lang", "<h5 lang"), "heading level jumps"),
        (('aria-labelledby="scope"', 'aria-labelledby="nowhere"'), "points at no"),
        (('<th scope="col"', "<th"), "no scope"),
        (('href="#receipt"', 'href="#gone"'), "points at no element"),
        (
            (
                "<style>",
                '<link rel="stylesheet" href="https://x.invalid/a.css"><style>',
            ),
            "external resource",
        ),
    ],
)
def test_structural_defects_are_caught(
    subjects: tuple[object, ...],
    tmp_path: Path,
    mutation: tuple[str, str],
    needle: str,
) -> None:
    """Each of these is a real defect an automated check should refuse."""

    subject = subjects[0]
    broken = _replace(
        subject,
        subject.html.replace(*mutation, 1),  # type: ignore[attr-defined]
    )
    report = _audit((broken,), tmp_path)
    detail = " ".join(finding.detail for finding in report.findings)  # type: ignore[attr-defined]
    assert needle in detail, detail


def test_a_check_that_examined_nothing_is_a_finding(
    monkeypatch: pytest.MonkeyPatch, subjects: tuple[object, ...], tmp_path: Path
) -> None:
    """The per-check version of refusing to pass on nothing."""

    monkeypatch.setitem(
        gate._CHECKS, "contrast", lambda subject: gate.CheckResult("contrast")
    )
    report = _audit(subjects, tmp_path)
    assert "check-examined-nothing" in _rules(report)


def test_an_unknown_engine_is_a_finding(
    subjects: tuple[object, ...], tmp_path: Path
) -> None:
    """Asking for an engine that does not exist must not silently do nothing."""

    report = _audit(subjects, tmp_path, engines=("builtin", "pa11y"))
    assert "engine-unknown" in _rules(report)


def test_requesting_no_engine_at_all_is_a_finding(
    subjects: tuple[object, ...], tmp_path: Path
) -> None:
    """`--engines ''` used to render two real pages and call them clean."""

    report = _audit(subjects, tmp_path, engines=())
    assert "no-engines" in _rules(report)
    assert report.engines_executed == []  # type: ignore[attr-defined]


def test_the_cli_refuses_to_pass_when_no_engine_was_requested(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """The exit code has to disagree too, not just the report body.

    Exit 2, not 1: "no engine was requested" is the gate saying it did not
    examine, which is the same sentence as an absent node harness. It answered
    1 here until 2026-08-31 -- "examined and found something" over a run in
    which nothing examined anything. See ADR 0008.
    """

    assert gate.main(["--engines", "", "--workdir", str(tmp_path)]) == 2
    assert "no-engines" in capsys.readouterr().out


def test_a_requested_engine_that_cannot_run_fails_rather_than_skipping(
    monkeypatch: pytest.MonkeyPatch, subjects: tuple[object, ...], tmp_path: Path
) -> None:
    """A missing engine is a failure. This is the rule, and it always runs."""

    monkeypatch.setattr(gate, "HARNESS_MODULES", tmp_path / "absent")
    report = _audit(subjects, tmp_path, engines=("builtin", "axe"))
    rules = _rules(report)
    assert "engine-unavailable" in rules
    assert "engine-not-executed" in rules
    assert "axe" not in report.engines_executed  # type: ignore[attr-defined]


def test_an_engine_that_executed_no_rules_fails(
    monkeypatch: pytest.MonkeyPatch, subjects: tuple[object, ...], tmp_path: Path
) -> None:
    """axe reporting zero violations having run zero rules is not a pass."""

    present = tmp_path / "node_modules"
    present.mkdir()
    monkeypatch.setattr(gate, "HARNESS_MODULES", present)
    payload = {
        "ok": True,
        "pages": [{"page": "receipt.en-US.html", "executedRules": 0, "violations": []}],
    }

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([], 0, json.dumps(payload), "")

    monkeypatch.setattr(gate.subprocess, "run", fake_run)
    findings, undetermined, ran = gate.run_axe(subjects[:1], tmp_path)
    assert ran is True
    assert [finding.rule for finding in findings] == ["engine-examined-nothing"]
    assert undetermined == []


def test_an_undetermined_rule_nothing_else_covers_is_a_finding(
    subjects: tuple[object, ...], tmp_path: Path
) -> None:
    """ "Could not determine" must never quietly become "fine"."""

    report = gate.Report(declared=1, audited=1, engines_requested=("axe",))
    report.undetermined.append("some-new-axe-rule")
    findings = list(gate._undetermined_findings(report))
    assert [finding.rule for finding in findings] == ["undetermined-uncovered"]


def test_every_undetermined_rule_axe_reports_here_is_covered() -> None:
    """The coverage map is a claim, so pin what it currently claims."""

    assert gate.UNDETERMINED_COVERAGE == {
        "color-contrast": "contrast",
        "landmark-one-main": "html-validity",
        "page-has-heading-one": "html-validity",
    }
    assert set(gate.UNDETERMINED_COVERAGE.values()) <= set(gate.BUILTIN_CHECKS)


@pytest.mark.skipif(
    not HARNESS_INSTALLED,
    reason="tools/a11y/node_modules is absent; `make a11y-install` installs it. "
    "The gate itself fails rather than skipping — see the test above.",
)
def test_axe_actually_runs_and_examines_the_pages(
    subjects: tuple[object, ...], tmp_path: Path
) -> None:
    """Prove the engine ran, not merely that it reported nothing."""

    report = _audit(subjects, tmp_path, engines=("builtin", "axe"))
    assert "axe" in report.engines_executed  # type: ignore[attr-defined]
    assert report.findings == [], report.findings  # type: ignore[attr-defined]
    assert set(report.undetermined) <= set(gate.UNDETERMINED_COVERAGE)  # type: ignore[attr-defined]


@pytest.mark.skipif(not HARNESS_INSTALLED, reason="node harness not installed")
def test_axe_catches_a_defect_the_builtin_checks_do_not(
    subjects: tuple[object, ...], tmp_path: Path
) -> None:
    """Negative control for the engine itself, not just for the wrapper."""

    subject = subjects[0]
    broken = _replace(
        subject,
        subject.html.replace(  # type: ignore[attr-defined]
            "<header>", '<header><button aria-label=""></button>'
        ),
    )
    report = _audit((broken,), tmp_path, engines=("builtin", "axe"))
    assert "axe" in _rules(report), report.findings  # type: ignore[attr-defined]


def test_contrast_ratio_matches_the_published_examples() -> None:
    """Black on white is 21:1; identical colours are 1:1."""

    assert round(gate.contrast_ratio("#000000", "#ffffff"), 2) == 21.0
    assert round(gate.contrast_ratio("#ffffff", "#ffffff"), 2) == 1.0
    assert round(gate.contrast_ratio("#fff", "#000"), 2) == 21.0
    assert gate.contrast_ratio("#767676", "#ffffff") >= 4.5


def test_the_cli_reports_and_writes_a_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The command-line entry point has to agree with the library."""

    target = tmp_path / "report.json"
    code = gate.main(
        [
            "--engines",
            "builtin",
            "--locale",
            "en-US",
            "--json",
            str(target),
            "--workdir",
            str(tmp_path / "work"),
        ]
    )
    assert code == 0
    printed = capsys.readouterr().out
    assert "1/1 page(s) audited" in printed
    assert "a11y-gate: clean" in printed
    report = json.loads(target.read_text(encoding="utf-8"))
    assert report["declared_pages"] == report["audited_pages"] == 1
    assert report["engines_executed"] == ["builtin"]
    assert all(check["examined"] > 0 for check in report["checks"])


def test_the_cli_fails_when_the_gate_finds_something(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A finding has to reach the exit code, not only the report."""

    monkeypatch.setattr(
        gate,
        "audit",
        lambda subjects, engines, workdir: gate.Report(
            declared=1, audited=1, findings=[gate.Finding("r", "s", "d")]
        ),
    )
    assert gate.main(["--workdir", str(tmp_path)]) == 1
    assert "1 finding(s)" in capsys.readouterr().out
