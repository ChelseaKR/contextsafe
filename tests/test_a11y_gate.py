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
        presentable=subject.presentable,  # type: ignore[attr-defined]
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


@pytest.mark.parametrize(
    ("rule", "technique"),
    [
        (".notice { display: none; }", "display"),
        (".notice { visibility: hidden; }", "visibility"),
        (".notice { opacity: 0; }", "opacity"),
        (".notice { opacity: 0.0; }", "opacity"),
        (".notice { font-size: 0; }", "font-size"),
        (".notice p { font-size: 0px; }", "font-size"),
        (".notice { clip: rect(0 0 0 0); }", "clip"),
        (".source-text { clip-path: inset(50%); }", "clip"),
        (".notice { height: 0; overflow: hidden; }", "overflow"),
        (".notice { max-height: 0px; overflow: hidden; }", "overflow"),
        ("main { width: 0; overflow: hidden; }", "overflow"),
        (".notice { position: absolute; left: -9999px; }", "position"),
        ("section { position: fixed; top: -100em; }", "position"),
        ("li { display: none; }", "display"),
        ("#limitations { display: none; }", "display"),
        ("ol, dl { display: none; }", "display"),
        ("p { visibility: hidden; }", "visibility"),
        ("body { font-size: 0; }", "font-size"),
        (".skip-link, .notice { display: none; }", "display"),
        (".notice { display: none !important; }", "display"),
        (".notice { display: none ! IMPORTANT; }", "display"),
        (".notice { DISPLAY: NONE; }", "display"),
        (".notice { visibility: HIDDEN; }", "visibility"),
        ("tr { visibility: collapse; }", "visibility"),
        ("li { visibility: collapse; }", "visibility"),
        (".notice { position: relative; left: -9999px; }", "position"),
        (".notice { position: sticky; top: -9999px; }", "position"),
        (".notice { position: absolute; left: -50em; }", "position"),
        (".notice { position: absolute; top: -2in; }", "position"),
        (".notice { position: absolute; left: -100%; }", "position"),
        (".notice { font-size: 0.01px; }", "font-size"),
        (".notice { font-size: 0.05em; }", "font-size"),
        (".notice { font-size: 5%; }", "font-size"),
        (".notice { height: 0; overflow: clip; }", "overflow"),
        (".notice { content-visibility: hidden; }", "content-visibility"),
        (".notice { transform: scale(0); }", "transform"),
        (".notice { transform: scale3d(1, 0, 1); }", "transform"),
        (".notice { transform: translateX(-9999px); }", "transform"),
        (".notice { transform: translate(0, 200vh); }", "transform"),
        (".notice { text-indent: -9999px; }", "offset"),
        (".notice { margin-left: -100in; }", "offset"),
        (".notice { margin-top: -10cm; }", "offset"),
    ],
)
def test_hiding_a_disclosure_in_print_is_caught(
    subjects: tuple[object, ...], tmp_path: Path, rule: str, technique: str
) -> None:
    """Printing must not be a way to lose the safety notice, by any technique.

    Until 2026-09-04 only ``display`` and ``visibility`` counted, and an
    ``opacity: 0`` on the notice produced no finding at all. The selector
    rows are the selector half of the same gap: a check that protected five
    named selectors let ``li { display: none; }`` through, and that rule hides
    every limitation on the page. The rows from ``!important`` on are the
    spelling half, found by review of the first fix: the predicates compared
    the verbatim declaration, so ``DISPLAY: NONE``, ``display: none
    !important`` and ``visibility: HIDDEN`` were not findings, ``collapse``
    was not ``hidden`` although it removes a row or a list item, a relatively
    positioned box offset off the sheet did not count as positioned, and
    ``left: -50em`` was compared as the number 50 against 100 pixels.
    """

    subject = subjects[1]
    broken = subject.html.replace(  # type: ignore[attr-defined]
        "  .skip-link { display: none; }",
        f"  .skip-link {{ display: none; }}\n  {rule}",
    )
    report = _audit((_replace(subject, broken),), tmp_path)
    assert "print" in _rules(report)
    hiding = [f.detail for f in report.findings if "hides content" in f.detail]  # type: ignore[attr-defined]
    assert hiding, report.findings  # type: ignore[attr-defined]
    assert any(f"(by {technique})" in detail for detail in hiding), hiding


@pytest.mark.parametrize(
    "rule",
    [
        ".skip-link { opacity: 0; }",
        ".notice { opacity: 1; }",
        ".notice { font-size: 10pt; }",
        ".notice { height: 0; }",
        ".notice { overflow: hidden; }",
        ".notice { position: absolute; left: -1px; }",
        ".notice { position: absolute; left: -2em; }",
        ".notice { position: absolute; left: 0; }",
        ".notice { position: static; left: -9999px; }",
        ".notice { left: -9999px; }",
        ".notice { font-size: 1px; }",
        ".notice { font-size: 0.85rem; }",
        ".notice { overflow: clip; }",
        ".notice { content-visibility: auto; }",
        ".notice { transform: translateY(2px) scale(1); }",
        ".notice { text-indent: 1em; margin-left: -1rem; }",
        ".notice { opacity: ; }",
    ],
)
def test_a_print_rule_that_hides_nothing_is_not_a_finding(
    subjects: tuple[object, ...], tmp_path: Path, rule: str
) -> None:
    """The accepting half: a rule on the skip link, or one that leaves an
    element visible, must not be reported as hiding it.

    ``position: relative; left: -9999px`` sat in this list until the review
    of 2026-09-04 pointed out that it hides the notice; it is a catching row
    now. An offset with no ``position``, or with ``static``, does nothing.
    """

    subject = subjects[1]
    html = subject.html.replace(  # type: ignore[attr-defined]
        "  .skip-link { display: none; }",
        f"  .skip-link {{ display: none; }}\n  {rule}",
    )
    report = _audit((_replace(subject, html),), tmp_path)
    assert not any("hides content" in f.detail for f in report.findings)  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    "block",
    [
        "@media print {\n  .notice { display: none; }\n}\n",
        "@media print{.notice{display:none}}\n",
        "@media print and (min-width: 0) {\n  .notice { display: none; }\n}\n",
        "@media only print {\n  .notice { display: none; }\n}\n",
        "@media screen, print {\n  .notice { display: none; }\n}\n",
        "@media all {\n  .notice { display: none; }\n}\n",
        "@media (min-width: 0) {\n  .notice { display: none; }\n}\n",
        "@media print {\n  @page { margin: 1cm; }\n  .notice { display: none; }\n}\n",
        "@media print {\n  .notice { display: none; }\n",
    ],
    ids=[
        "second-block",
        "no-space",
        "with-feature",
        "only",
        "screen-and-print",
        "all",
        "no-medium",
        "nested-at-rule",
        "unterminated",
    ],
)
def test_a_print_block_spelled_another_way_is_still_read(
    subjects: tuple[object, ...], tmp_path: Path, block: str
) -> None:
    """Every block that reaches the printer is print rules, however spelled.

    The first fix matched one block written exactly ``@media print {`` and
    closed at the first ``\\n}``; a second block, ``print{`` without the
    space, ``print and (...)``, or ``screen, print`` was folded into the
    screen rules, where nothing checked it for hiding, and a browser applied
    it when printing. Each of these hides the notice and each is a finding.
    """

    subject = subjects[1]
    html = subject.html.replace("</style>", block + "</style>", 1)  # type: ignore[attr-defined]
    report = _audit((_replace(subject, html),), tmp_path)
    hiding = [f.detail for f in report.findings if "hides content" in f.detail]  # type: ignore[attr-defined]
    assert hiding, report.findings  # type: ignore[attr-defined]
    assert any("'.notice'" in detail and "(by display)" in detail for detail in hiding)


def test_a_screen_only_block_is_not_print_and_an_unknown_medium_is_a_finding(
    subjects: tuple[object, ...], tmp_path: Path
) -> None:
    """The other two outcomes: screen rules stay screen, and a medium the gate
    cannot place is reported rather than filed as screen."""

    subject = subjects[1]
    screen_only = subject.html.replace(  # type: ignore[attr-defined]
        "</style>", "@media screen {\n  .notice { display: none; }\n}\n</style>", 1
    )
    report = _audit((_replace(subject, screen_only),), tmp_path)
    assert "print" not in _rules(report), report.findings  # type: ignore[attr-defined]
    unknown = subject.html.replace(  # type: ignore[attr-defined]
        "</style>", "@media not screen {\n  .notice { display: none; }\n}\n</style>", 1
    )
    report = _audit((_replace(subject, unknown),), tmp_path)
    assert "print" in _rules(report)
    assert any("cannot classify" in f.detail for f in report.findings)  # type: ignore[attr-defined]


def test_the_stylesheet_is_split_block_by_block() -> None:
    """The parser, on its own: bodies land where the query says, brace-balanced."""

    sheet = gate._split_media(
        ".aa { color: #000; }\n"
        "@media screen { .bb { color: #111; } }\n"
        "@media print { .cc { color: #222; } @page { margin: 0; } }\n"
        "@media screen, print { .dd { color: #333; } }\n"
        "@media speech { .ee { color: #444; } }\n"
        ".ff { color: #555; }\n"
    )
    assert ".aa {" in sheet.screen and ".ff {" in sheet.screen
    assert ".bb {" in sheet.screen and ".bb {" not in sheet.printed
    assert ".cc {" in sheet.printed and ".cc {" not in sheet.screen
    assert "@page" in sheet.printed
    assert ".dd {" in sheet.printed and ".dd {" in sheet.screen
    assert ".ee {" not in sheet.printed and ".ee {" not in sheet.screen
    assert sheet.unclassified == ("speech",)
    assert gate._media_scopes("") is None
    assert gate._media_scopes("not print") is None


@pytest.mark.parametrize(
    ("rule", "needle"),
    [
        ("tbody tr { break-inside: auto; }", "break-inside"),
        ("tr { page-break-inside: auto; }", "page-break-inside"),
        ("li { break-inside: AUTO !important; }", "break-inside"),
        ("h2 { break-after: auto; }", "break-after"),
        ("caption { page-break-after: always; }", "page-break-after"),
        ("table thead { display: block; }", "headers would not repeat"),
        ("thead { display: none; }", "headers would not repeat"),
    ],
)
def test_a_print_rule_that_undoes_a_keep_together_rule_is_caught(
    subjects: tuple[object, ...], tmp_path: Path, rule: str, needle: str
) -> None:
    """The keep-together check looked for the declaration on the simple
    selector and not for a later rule overriding it: ``tbody tr {
    break-inside: auto; }`` wins the cascade and splits a result row, with
    zero findings, until the review of 2026-09-04."""

    subject = subjects[1]
    html = subject.html.replace(  # type: ignore[attr-defined]
        "  .skip-link { display: none; }",
        f"  .skip-link {{ display: none; }}\n  {rule}",
    )
    report = _audit((_replace(subject, html),), tmp_path)
    assert "print" in _rules(report)
    detail = " ".join(f.detail for f in report.findings)  # type: ignore[attr-defined]
    assert needle in detail, detail


@pytest.mark.parametrize(
    ("value", "pixels"),
    [
        ("-9999px", -9999.0),
        ("-50em", -800.0),
        ("-2rem", -32.0),
        ("-1in", -96.0),
        ("-75pt", -100.0),
        ("-100%", -100.0),
        ("10", 10.0),
        ("", None),
        ("auto", None),
        (None, None),
    ],
)
def test_lengths_are_measured_in_their_unit(
    value: str | None, pixels: float | None
) -> None:
    """``-50em`` is 800 pixels off the sheet, not the number 50."""

    measured = gate._pixels(value)
    assert measured == pixels if pixels is None else abs(measured - pixels) < 1e-9


def test_a_receipt_value_in_an_announced_attribute_is_caught(
    subjects: tuple[object, ...], tmp_path: Path
) -> None:
    """A ``title``, ``aria-label`` or ``alt`` is read aloud and is text on the page.

    The renderer emits none of these today; this pins that one could not
    carry a value past the minimization check if it did.
    """

    subject = subjects[0]
    value = "CSYN-FIXTURE-VALUE-IN-AN-ATTRIBUTE"
    for attribute in ("title", "aria-label", "alt"):
        leaked = subject.html.replace(  # type: ignore[attr-defined]
            "<main ", f'<main {attribute}="{value}" ', 1
        )
        report = _audit((_replace(subject, leaked),), tmp_path)
        assert "minimization" in _rules(report), attribute
        detail = " ".join(f.detail for f in report.findings)  # type: ignore[attr-defined]
        assert value not in detail
    clean = gate.visible_runs(
        '<html><head><title t="x">y</title></head><body><p title=" ">z</p></body></html>'
    )
    assert clean == ["z"]


@pytest.mark.parametrize(
    ("mutation", "needle"),
    [
        (
            ("  thead { display: table-header-group; }\n", ""),
            "headers would not repeat",
        ),
        (("section, table, tr, li,", "section, table, li,"), "orphaned"),
        (("section, table, tr, li,", "section, table, tr,"), "orphaned"),
        (("  h1, h2, h3, caption { break-after: avoid; }\n", ""), "with what follows"),
        (("<thead>", ""), "no <thead>"),
    ],
)
def test_a_print_layout_that_could_orphan_a_finding_is_caught(
    subjects: tuple[object, ...],
    tmp_path: Path,
    mutation: tuple[str, str],
    needle: str,
) -> None:
    """B-038 negative controls: each protection, removed, is a `print` finding.

    Repeated headers, a result row kept whole, a limitation kept with its
    original, a heading kept with its section, and a table that has a header
    group to repeat at all.
    """

    subject = subjects[1]
    html = subject.html  # type: ignore[attr-defined]
    assert mutation[0] in html
    broken = html.replace(*mutation)
    if mutation[0] == "<thead>":
        broken = broken.replace("</thead>", "")
    report = _audit((_replace(subject, broken),), tmp_path)
    assert "print" in _rules(report)
    detail = " ".join(finding.detail for finding in report.findings)  # type: ignore[attr-defined]
    assert needle in detail, detail


def test_a_receipt_value_the_page_does_not_need_is_caught(
    subjects: tuple[object, ...], tmp_path: Path
) -> None:
    """A-036 / F-027: a value outside the presentation allowlist is a finding.

    The expected hash of a result is in the receipt and is not on the
    allowlist; a page that shows it has copied something it did not need. So
    has a page carrying any text that is neither catalog nor allowlisted.
    """

    document = gate.reference_document()
    expected = document["payload"]["results"][0]["expected_sha256"]
    assert expected not in subjects[0].presentable  # type: ignore[attr-defined]
    # The third is a catalog sentence whose placeholder holds free text: until
    # 2026-09-04 ``Case {case_id}`` matched any run that began "Case ", so a
    # name behind it was never a finding.
    for injected in (
        expected,
        "CSYN-FIXTURE-VALUE-THE-PAGE-DOES-NOT-NEED",
        "Case CSYN-FIXTURE-LEGAL-NAME",
    ):
        subject = subjects[0]
        leaked = subject.html.replace(  # type: ignore[attr-defined]
            "</main>", f"<p>{injected}</p></main>", 1
        )
        report = _audit((_replace(subject, leaked),), tmp_path)
        assert "minimization" in _rules(report), injected
        detail = " ".join(finding.detail for finding in report.findings)  # type: ignore[attr-defined]
        assert injected not in detail, "the finding must not echo the value"


def test_the_presentation_allowlist_is_named_by_pointer() -> None:
    """The allowlist holds what the page needs and nothing the JSON also has."""

    document = gate.reference_document()
    allowed = gate.presentable_values(document)
    payload = document["payload"]
    assert payload["case_id"] in allowed
    assert set(payload["hashes"].values()) <= allowed
    assert set(payload["limitations"]) <= allowed
    assert {item["rule_id"] for item in payload["results"]} <= allowed
    # `rule_version` is not asserted absent: in the reference fixture it is the
    # same string as `runner_version`, which the page does present.
    for item in payload["results"]:
        assert item["expected_sha256"] not in allowed
        assert not set(item["observed_sha256s"]) & allowed
        assert not set(item["evidence_sha256s"]) & allowed


def test_the_expected_hash_is_recomputed_not_read(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A-036: the hash a page must carry comes from the payload, not the field.

    The renderer has its own refusal of a mismatched ``payload_sha256``, so
    this test steps around it: the document's field is forged, and the
    renderer is replaced by one that stamps the forged value on an otherwise
    real page. A gate that read the field would then find page and document
    in agreement and audit the page. A gate that recomputes the hash finds
    that the page carries the wrong one. The earlier form of this test
    asserted only the renderer's exit 2 and passed under either gate.
    """

    document = gate.reference_document()
    payload = document["payload"]
    real = gate.sha256_json(payload)
    forged = "f" * 64
    assert forged != real
    honest_page = gate.render_receipt_page(document, locale="en-US")
    assert honest_page.count(real) == 2  # `data-cs-payload-sha256` and the <dd>
    document["payload_sha256"] = forged
    monkeypatch.setattr(gate, "reference_document", lambda: document)
    monkeypatch.setattr(
        gate,
        "render_receipt_page",
        lambda *args, **kwargs: honest_page.replace(real, forged),
    )
    subjects = gate.build_subjects(("en-US",))
    assert subjects[0].payload_sha256 == real
    assert f'data-cs-payload-sha256="{forged}"' in subjects[0].html
    report = _audit(subjects, tmp_path)
    assert "wrong-subject" in _rules(report)
    assert report.audited == 0  # type: ignore[attr-defined]
    detail = " ".join(f.detail for f in report.findings if f.rule == "wrong-subject")  # type: ignore[attr-defined]
    assert "does not carry the payload hash of the receipt it should render" in detail
    assert gate.main(["--engines", "builtin", "--workdir", str(tmp_path)]) != 0


def test_a_forged_hash_field_still_cannot_reach_the_renderer(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The renderer's own refusal, kept as a separate fact: exit 2, no page."""

    document = gate.reference_document()
    document["payload_sha256"] = "0" * 64
    monkeypatch.setattr(gate, "reference_document", lambda: document)
    assert gate.main(["--engines", "builtin", "--workdir", str(tmp_path)]) == 2


@pytest.mark.parametrize(
    ("value", "zero"),
    [
        ("0", True),
        ("0px", True),
        ("0.0em", True),
        (".0", True),
        ("-0%", True),
        ("00.000rem", True),
        ("", False),
        ("1", False),
        ("0.5", False),
        ("10px", False),
        ("0x", False),
        (None, False),
    ],
)
def test_the_zero_length_predicate_reads_only_zero(
    value: str | None, zero: bool
) -> None:
    """A collapsed box is a zero, spelled any of the ways CSS allows."""

    assert gate._is_zero(value) is zero


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
