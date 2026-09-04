#!/usr/bin/env python3
"""Accessibility gate for the rendered receipt page (B-043).

The design constraint here is not "run an accessibility checker". It is
**never report a pass you did not earn**, because the failure mode this gate
exists to avoid is the one that keeps happening: a checker pointed at a 404
page reporting "5 passed, 0 violations, exit 0", or a page list that was empty
and exited 0 because there was nothing to disagree with. An error page has no
accessibility violations. Neither does a blank one.

So this gate is built around three assertions it makes about itself.

**It renders its own subjects from ground truth.** The pages are rendered here,
in process, from the bundled synthetic reference fixture, and the expected
payload hash, case id, and mandated-limitation wording come from the *receipt
document* rather than from the page. A page that does not carry the hash of the
receipt it was supposed to render is the wrong subject, and the gate says so
instead of auditing it.

**It counts.** Declared pages, audited pages, and per-check examined counts are
all in the report, and a check that examined nothing is a finding
(``check-examined-nothing``) rather than a silent pass. So is an empty page set
(``no-pages``).

**It never converts "could not determine" into "fine".** axe-core runs in a DOM
with no layout engine, so it cannot evaluate colour contrast; those results
arrive as ``undetermined``, are listed by name, and the contrast rule is
computed here from the stylesheet instead.

Checks
------

``html-validity``
    Well-formedness, one ``<h1>``, one ``<main>``, ``lang`` on ``<html>``,
    ``<title>``, a charset, no duplicate ids, no skipped heading level, tables
    with captions and scoped headers, every ``aria-labelledby`` and in-page
    ``href`` resolving to an id that exists, no script, no external resource.

``contrast``
    WCAG 2.2 contrast for every foreground/background pair declared in the
    stylesheet, in the screen rules and again in the print rules. A rule that
    sets ``color`` without setting ``background-color`` in the same block is a
    finding: not because that is invalid CSS, but because it makes the pair
    unknowable, and an unknowable pair is how a contrast check quietly examines
    nothing.

``color-only``
    Every element carrying a status or boolean marker must also carry a text
    label from the published catalog and a non-colour symbol. Removing all
    colour from the page must lose no information.

``print``
    A ``@media print`` block must exist, must hide nothing but the skip link,
    and must not leave text on a background it cannot be read against. A rule
    that hides by any of the techniques ``HIDING_TECHNIQUES`` names
    (``display: none``, ``visibility: hidden``, zero opacity, zero font size,
    a clip, a collapsed box with its overflow hidden, or a box positioned off
    the page) is a finding unless every selector it applies to is in
    ``PRINT_MAY_HIDE``: the check does not know which selectors cover a
    mandated disclosure, so it does not try to. It must also keep the
    page readable across page breaks (B-038): every table has a ``<thead>``
    and the print rules declare it a repeating header group; a result row, a
    limitation, the translation notice, and a source-locale original are each
    kept on one page; and a heading or caption is kept with what follows it,
    so no finding is orphaned from its reason and no table body from its
    headers.

``minimization``
    Every run of reader-visible text is either a message from the page's
    catalog or the source catalog, or one of the values the page is allowed
    to present from the receipt: case id, the four hashes, the mandated
    limitations, rule ids, the outcome counts, runner and contract versions,
    and the caller-declared time. A catalog message with a placeholder counts
    only when the placeholder holds one of those values or a locale tag, so a
    message is never a wildcard prefix that free text can hide behind.
    Anything else is a value the page did not need to substantiate an outcome
    (A-036, F-027). The expected hash the gate compares the page against is
    recomputed from the payload, never read from the document's own
    ``payload_sha256`` field.

``axe``
    axe-core in a headless DOM. Violations fail. Undetermined rules are
    reported by name and never counted as passes. A page for which axe executed
    no rules at all fails as ``engine-examined-nothing``.

Engines are requested explicitly and a requested engine that cannot run is a
failure, never a skip: ``--engines builtin,axe`` fails with
``engine-unavailable`` if the node harness is not installed. Requesting no
engine at all is ``no-engines`` for the same reason ``no-pages`` exists: a run
that examined nothing has not earned the word "clean", and ``--engines ''``
reaching exit 0 would be this gate committing the defect it was written to
catch.

pa11y is not available here. Its engine, HTML_CodeSniffer, loads its rulesets by
injecting script tags and does not complete in a headless DOM without a browser;
it is not wired in rather than wired in and quietly skipped. The rules it would
add over axe — contrast, colour-only encoding, print — are the ones computed
above.

Exit 0 when clean, 1 when anything is found, 2 on a usage error.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:  # pragma: no cover - import shim
    sys.path.insert(0, str(REPO_ROOT / "src"))

from contextsafe.canonical import JsonValue, sha256_json  # noqa: E402
from contextsafe.errors import ContextSafeError  # noqa: E402
from contextsafe.evaluator import evaluate  # noqa: E402
from contextsafe.html_receipt import PAGE_KIND, render_receipt_page  # noqa: E402
from contextsafe.i18n import SOURCE_LOCALE, load_catalog, source_catalog  # noqa: E402
from contextsafe.receipt import build_receipt_document  # noqa: E402
from contextsafe.reference_fixtures import REFERENCE_ROOT  # noqa: E402
from contextsafe.validation import parse_bundle  # noqa: E402

# The locales audited when `--locale` is not given. Unlike `tools/i18n_gate.py`,
# which discovers catalogs from the directory, this list is written down: adding
# a catalog must be a decision to audit it, not a side effect. `make claims`
# fails when it stops matching the catalogs that ship, so a locale cannot reach
# a reader without an accessibility run behind it.
DEFAULT_LOCALES: tuple[str, ...] = ("en-US", "es-US")

REFERENCE = REFERENCE_ROOT
HARNESS = REPO_ROOT / "tools" / "a11y" / "run.mjs"
HARNESS_MODULES = REPO_ROOT / "tools" / "a11y" / "node_modules"

MINIMUM_CONTRAST = 4.5
"""WCAG 2.2 AA for body text. Applied to every pair, including large text."""

BUILTIN_CHECKS = ("html-validity", "contrast", "color-only", "print", "minimization")

PRINT_KEEP_TOGETHER = ("tr", "li", ".notice", ".source-text")
"""Selectors whose print rule must declare ``break-inside: avoid``.

A result row is a finding and its reason; a list item is a limitation and,
when the translation is unreviewed, its source-locale original; the notice is
the disclosure that the translation is unreviewed. Splitting any of them
across a page break orphans a finding from the sentence that explains it.
"""

PRINT_KEEP_WITH_NEXT = ("h1", "h2", "h3", "caption")
"""Selectors whose print rule must declare ``break-after: avoid``."""

PRINT_REPEATED_HEADER = ("thead", "display", "table-header-group")
"""The declaration that makes a table's headers repeat on every printed page."""

PRINT_MAY_HIDE = (".skip-link",)
"""The only selectors a print rule may hide.

An allowlist, not a list of protected selectors. The earlier form named five
selectors the disclosures live under and let ``li { display: none; }`` walk
past, which hides every limitation on the page; a check that has to know
which selectors cover a disclosure is a check that is wrong the day the
markup changes. Anything hidden that is not the skip link is a finding.
"""

_ZERO = re.compile(r"^-?(?:0+\.?0*|\.0+)(?:px|pt|em|rem|%|vh|vw|cm|mm|in)?$")
_OFF_PAGE = re.compile(r"^-\d*\.?\d+(?:px|pt|em|rem|%|vh|vw|cm|mm|in)$")


def _is_zero(value: str | None) -> bool:
    return value is not None and _ZERO.fullmatch(value.strip()) is not None


def _collapsed(declarations: Mapping[str, str]) -> bool:
    """A box with no height or width and its overflow cut off shows nothing."""

    return declarations.get("overflow") == "hidden" and any(
        _is_zero(declarations.get(name))
        for name in ("height", "max-height", "width", "max-width")
    )


def _off_page(declarations: Mapping[str, str]) -> bool:
    """A box taken out of flow and pushed past an edge is printed nowhere."""

    return declarations.get("position") in ("absolute", "fixed") and any(
        _OFF_PAGE.fullmatch(declarations.get(edge, "").strip()) is not None
        and float(re.sub(r"[a-z%]+$", "", declarations[edge].strip())) <= -100
        for edge in ("left", "top", "right", "bottom")
    )


HIDING_TECHNIQUES: tuple[tuple[str, Callable[[Mapping[str, str]], bool]], ...] = (
    ("display", lambda d: d.get("display") == "none"),
    ("visibility", lambda d: d.get("visibility") == "hidden"),
    ("opacity", lambda d: _is_zero(d.get("opacity"))),
    ("font-size", lambda d: _is_zero(d.get("font-size"))),
    ("clip", lambda d: "clip" in d or "clip-path" in d),
    ("overflow", _collapsed),
    ("position", _off_page),
)
"""Every way a print rule can make an element disappear, each named.

A check that knew only ``display`` and ``visibility`` was a check that a
``.notice { opacity: 0 }`` walked straight past; the print stylesheet has no
legitimate reason to use any of these on anything but the skip link, so each
is a finding rather than a judgement call. ``clip`` and ``clip-path`` are refused
whatever their value: a clip that shows the whole element is a clip nobody
needed to write.
"""

_IGNORED_RUNS = frozenset({"✔", "✖", "▣", "—", "?"})
"""Status symbols. ``color-only`` checks that each sits beside its word."""

ENGINES = ("builtin", "axe")

UNDETERMINED_COVERAGE = {
    "color-contrast": "contrast",
    "landmark-one-main": "html-validity",
    "page-has-heading-one": "html-validity",
}
"""Rules axe cannot decide without layout, and the check that decides them.

A headless DOM has no rendering, so axe returns these as ``incomplete`` rather
than as passes. Treating "could not determine" as "fine" is how an audit ends
up reporting a clean page it never looked at, so every undetermined rule must
map to a check here that does decide it. An undetermined rule with no entry is
itself a finding: it means the gate stopped covering something and nobody
noticed.
"""

_VOID = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
)
_HEADINGS = ("h1", "h2", "h3", "h4", "h5", "h6")


@dataclass(frozen=True, slots=True)
class Finding:
    """One gate failure, reported by rule, subject, and detail."""

    rule: str
    subject: str
    detail: str

    def __str__(self) -> str:
        """Return the one-line report form."""

        return f"  {self.rule}: {self.subject}: {self.detail}"


@dataclass(frozen=True, slots=True)
class Subject:
    """A page the gate intends to audit, and how it will recognise it."""

    name: str
    locale: str
    html: str
    payload_sha256: str
    case_id: str
    required_text: tuple[str, ...]
    presentable: frozenset[str] = frozenset()
    """Every receipt value the page may show as a run of text on its own."""


@dataclass(slots=True)
class CheckResult:
    """What one check examined, and what it found."""

    name: str
    examined: int = 0
    findings: list[Finding] = field(default_factory=list)


@dataclass(slots=True)
class Report:
    """The whole run, including the counts that make a pass meaningful."""

    declared: int = 0
    audited: int = 0
    engines_requested: tuple[str, ...] = ()
    engines_executed: list[str] = field(default_factory=list)
    checks: list[CheckResult] = field(default_factory=list)
    undetermined: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        """Return the machine-readable form of this report."""

        return {
            "declared_pages": self.declared,
            "audited_pages": self.audited,
            "engines_requested": list(self.engines_requested),
            "engines_executed": self.engines_executed,
            "checks": [
                {
                    "name": check.name,
                    "examined": check.examined,
                    "findings": len(check.findings),
                }
                for check in self.checks
            ],
            "undetermined_rules": sorted(set(self.undetermined)),
            "findings": [
                {"rule": item.rule, "subject": item.subject, "detail": item.detail}
                for item in self.findings
            ],
        }


class _Document(HTMLParser):
    """A minimal structural model of the page, built without a browser."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.elements: list[tuple[str, dict[str, str]]] = []
        self.ids: list[str] = []
        self.headings: list[str] = []
        self.mismatched: list[str] = []
        self.text_by_element: list[tuple[str, dict[str, str], str]] = []
        self.raw_by_element: list[tuple[str, dict[str, str], str]] = []
        self._open: list[tuple[str, dict[str, str], int]] = []
        self._raw = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Record an element and push it if it can contain content."""

        attributes = {name: (value or "") for name, value in attrs}
        self.elements.append((tag, attributes))
        if "id" in attributes:
            self.ids.append(attributes["id"])
        if tag in _HEADINGS:
            self.headings.append(tag)
        if tag not in _VOID:
            self.stack.append(tag)
            self._open.append((tag, attributes, len(self._raw)))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Treat a self-closed tag as a void element."""

        self.handle_starttag(tag, attrs)
        if tag not in _VOID and self.stack and self.stack[-1] == tag:
            self.stack.pop()
            self._open.pop()

    def handle_endtag(self, tag: str) -> None:
        """Pop the element, recording any tag that does not match."""

        if not self.stack or self.stack[-1] != tag:
            self.mismatched.append(tag)
            return
        self.stack.pop()
        name, attributes, start = self._open.pop()
        raw = self._raw[start:]
        self.raw_by_element.append((name, attributes, raw))
        self.text_by_element.append(
            (name, attributes, re.sub(r"<[^>]*>", " ", raw).strip())
        )

    def handle_data(self, data: str) -> None:
        """Accumulate character data into the raw buffer."""

        self._raw += data

    def unknown_decl(self, data: str) -> None:  # pragma: no cover - defensive
        """Ignore unknown declarations rather than failing the parse."""

    def feed(self, data: str) -> None:
        """Parse ``data``, keeping raw offsets aligned with the input."""

        for chunk in re.split(r"(<[^>]*>)", data):
            if chunk.startswith("<"):
                self._raw += chunk
                super().feed(chunk)
            else:
                super().feed(chunk)


def parse_document(html: str) -> _Document:
    """Return the structural model of ``html``."""

    document = _Document()
    document.feed(html)
    document.close()
    return document


class _VisibleRuns(HTMLParser):
    """Collect every run of text a reader would see on the page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.runs: list[str] = []
        self._suppress = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Start suppressing inside an element a reader never sees."""

        if tag in ("head", "script", "style", "title"):
            self._suppress += 1

    def handle_endtag(self, tag: str) -> None:
        """Stop suppressing at the close of that element."""

        if tag in ("head", "script", "style", "title") and self._suppress:
            self._suppress -= 1

    def handle_data(self, data: str) -> None:
        """Record one non-blank run."""

        text = data.strip()
        if text and not self._suppress:
            self.runs.append(text)


def visible_runs(html: str) -> list[str]:
    """Return every run of reader-visible text on ``html``, in page order."""

    parser = _VisibleRuns()
    parser.feed(html)
    parser.close()
    return parser.runs


def _luminance(hex_colour: str) -> float:
    value = hex_colour.lstrip("#")
    if len(value) == 3:
        value = "".join(char * 2 for char in value)
    channels = [int(value[index : index + 2], 16) / 255 for index in (0, 2, 4)]
    linear = [
        channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
        for channel in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast_ratio(foreground: str, background: str) -> float:
    """Return the WCAG 2.2 contrast ratio between two hex colours."""

    lighter, darker = sorted(
        (_luminance(foreground), _luminance(background)), reverse=True
    )
    return (lighter + 0.05) / (darker + 0.05)


def _stylesheet(html: str) -> str:
    match = re.search(r"<style>(.*?)</style>", html, flags=re.S)
    return match.group(1) if match else ""


def _split_media(style: str) -> tuple[str, str]:
    """Return the screen rules and the print rules separately."""

    match = re.search(r"@media print \{(.*?)\n\}", style, flags=re.S)
    if match is None:
        return style, ""
    return style[: match.start()] + style[match.end() :], match.group(1)


def _rules(css: str) -> Iterator[tuple[str, dict[str, str]]]:
    for selector, block in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        declarations = {}
        for declaration in block.split(";"):
            if ":" not in declaration:
                continue
            name, _, value = declaration.partition(":")
            declarations[name.strip()] = value.strip()
        yield selector.strip(), declarations


def check_contrast(subject: Subject) -> CheckResult:
    """Compute the contrast of every declared foreground/background pair."""

    result = CheckResult("contrast")
    screen, printed = _split_media(_stylesheet(subject.html))
    for scope, css in (("screen", screen), ("print", printed)):
        for selector, declarations in _rules(css):
            foreground = declarations.get("color")
            background = declarations.get("background-color")
            if foreground is None:
                continue
            if background is None:
                result.findings.append(
                    Finding(
                        "contrast",
                        subject.name,
                        f"{scope} rule {selector!r} sets color with no "
                        "background-color in the same block, so the pair "
                        "cannot be checked",
                    )
                )
                continue
            result.examined += 1
            ratio = contrast_ratio(foreground, background)
            if ratio < MINIMUM_CONTRAST:
                result.findings.append(
                    Finding(
                        "contrast",
                        subject.name,
                        f"{scope} rule {selector!r}: {foreground} on "
                        f"{background} is {ratio:.2f}:1, below "
                        f"{MINIMUM_CONTRAST}:1",
                    )
                )
    return result


def check_color_only(subject: Subject) -> CheckResult:
    """Every status must survive the page being printed without colour."""

    result = CheckResult("color-only")
    document = parse_document(subject.html)
    catalog = load_catalog(subject.locale)
    labels = {
        message.text
        for key, message in catalog.messages.items()
        if key.startswith(("status.", "value."))
    }
    for tag, attributes, raw in document.raw_by_element:
        marker = attributes.get("data-cs-status") or attributes.get("data-cs-boolean")
        if marker is None or tag not in ("td", "th", "dd"):
            continue
        result.examined += 1
        text = re.sub(r"<[^>]*>", " ", raw)
        if 'class="status-symbol"' not in raw:
            result.findings.append(
                Finding(
                    "color-only",
                    subject.name,
                    f"{tag} marked {marker!r} carries no non-colour symbol",
                )
            )
        if not any(label and label in text for label in labels):
            result.findings.append(
                Finding(
                    "color-only",
                    subject.name,
                    f"{tag} marked {marker!r} carries no published text label",
                )
            )
    return result


def _print_declarations(printed: str) -> dict[str, dict[str, str]]:
    """Return the print declarations in force for each simple selector.

    A rule written ``section, table, tr { ... }`` counts for each of the three,
    which is how the stylesheet writes them and how a browser reads them.
    """

    declared: dict[str, dict[str, str]] = {}
    for selector, declarations in _rules(printed):
        for part in selector.split(","):
            declared.setdefault(part.strip(), {}).update(declarations)
    return declared


def _hiding_findings(subject: Subject, printed: str) -> Iterator[Finding]:
    """A rule that hides is a finding unless it hides only the skip link.

    Judged per selector list: ``.skip-link, .notice { display: none; }`` hides
    the notice, so the whole rule is a finding, not the allowlisted half.
    """

    for selector, declarations in _rules(printed):
        if {part.strip() for part in selector.split(",")} <= set(PRINT_MAY_HIDE):
            continue
        for technique, hides in HIDING_TECHNIQUES:
            if hides(declarations):
                yield Finding(
                    "print",
                    subject.name,
                    f"print rule {selector!r} hides content the page must "
                    f"keep when printed (by {technique})",
                )


def _page_break_findings(
    subject: Subject, declared: Mapping[str, Mapping[str, str]]
) -> Iterator[Finding]:
    """Headers repeat, and nothing that belongs together is split (B-038)."""

    header, prop, value = PRINT_REPEATED_HEADER
    if declared.get(header, {}).get(prop) != value:
        yield Finding(
            "print",
            subject.name,
            f"print rules do not declare {header!r} as {value!r}, so table "
            "headers would not repeat on every printed page",
        )
    for selector in PRINT_KEEP_TOGETHER:
        if declared.get(selector, {}).get("break-inside") != "avoid":
            yield Finding(
                "print",
                subject.name,
                f"print rules do not keep {selector!r} on one page, so a "
                "finding could be orphaned from its reason or a limitation "
                "from its original",
            )
    for selector in PRINT_KEEP_WITH_NEXT:
        if declared.get(selector, {}).get("break-after") != "avoid":
            yield Finding(
                "print",
                subject.name,
                f"print rules do not keep {selector!r} with what follows it",
            )


def _table_header_findings(subject: Subject) -> Iterator[Finding]:
    for tag, _, raw in parse_document(subject.html).raw_by_element:
        if tag == "table" and "<thead" not in raw:
            yield Finding(
                "print",
                subject.name,
                "a table has no <thead>, so its headers cannot repeat in print",
            )


def check_print(subject: Subject) -> CheckResult:
    """The page has to print, disclosures included, across page breaks."""

    result = CheckResult("print")
    _, printed = _split_media(_stylesheet(subject.html))
    if not printed.strip():
        result.findings.append(
            Finding("print", subject.name, "the page has no @media print rules")
        )
        return result
    declared = _print_declarations(printed)
    result.examined += len(list(_rules(printed)))
    result.examined += 1 + len(PRINT_KEEP_TOGETHER) + len(PRINT_KEEP_WITH_NEXT)
    result.examined += subject.html.count("<table")
    result.findings.extend(_hiding_findings(subject, printed))
    result.findings.extend(_page_break_findings(subject, declared))
    result.findings.extend(_table_header_findings(subject))
    return result


def check_minimization(subject: Subject) -> CheckResult:
    """Nothing on the page but catalog text and the values it may present."""

    result = CheckResult("minimization")
    catalogs = (load_catalog(subject.locale), source_catalog())
    # A placeholder may hold only a value the page may present or the locale
    # tags the footer and the source-original label name. Without this, every
    # message with a placeholder is a prefix any free text can follow.
    fillers = subject.presentable | {subject.locale, SOURCE_LOCALE}
    for index, run in enumerate(visible_runs(subject.html)):
        result.examined += 1
        if run in subject.presentable or run in _IGNORED_RUNS:
            continue
        if any(catalog.accounts_for(run, fillers) for catalog in catalogs):
            continue
        # The run is named by position and size, never quoted: on a real
        # receipt the thing this check catches is exactly the value that must
        # not be copied into a report.
        result.findings.append(
            Finding(
                "minimization",
                subject.name,
                f"visible text run {index} ({len(run)} characters) is neither "
                "catalog text nor a value the page may present",
            )
        )
    return result


def _validity_findings(subject: Subject, document: _Document) -> Iterator[Finding]:
    html_attrs = next(
        (attrs for tag, attrs in document.elements if tag == "html"), None
    )
    if html_attrs is None or not html_attrs.get("lang"):
        yield Finding("html-validity", subject.name, "<html> has no lang attribute")
    if document.mismatched:
        yield Finding(
            "html-validity",
            subject.name,
            f"unbalanced tags: {sorted(set(document.mismatched))}",
        )
    if document.stack:
        yield Finding("html-validity", subject.name, f"unclosed tags: {document.stack}")
    duplicates = sorted({i for i in document.ids if document.ids.count(i) > 1})
    if duplicates:
        yield Finding("html-validity", subject.name, f"duplicate ids: {duplicates}")
    yield from _landmark_findings(subject, document)
    yield from _heading_findings(subject, document)
    yield from _reference_findings(subject, document)
    yield from _resource_findings(subject, document)


def _landmark_findings(subject: Subject, document: _Document) -> Iterator[Finding]:
    tags = [tag for tag, _ in document.elements]
    for tag, expected in (("h1", 1), ("main", 1), ("title", 1)):
        if tags.count(tag) != expected:
            yield Finding(
                "html-validity",
                subject.name,
                f"expected exactly {expected} <{tag}>, found {tags.count(tag)}",
            )
    if not any(
        tag == "meta" and "charset" in attrs for tag, attrs in document.elements
    ):
        yield Finding("html-validity", subject.name, "no character encoding declared")
    for tag, attrs, _ in document.raw_by_element:
        if tag == "table" and "<caption" not in _raw_of(document, tag, attrs):
            yield Finding("html-validity", subject.name, "a table has no <caption>")
    for tag, attrs in document.elements:
        if tag == "th" and not attrs.get("scope"):
            yield Finding("html-validity", subject.name, "a <th> has no scope")
        if tag == "img" and "alt" not in attrs:
            yield Finding("html-validity", subject.name, "an <img> has no alt")


def _raw_of(document: _Document, tag: str, attrs: dict[str, str]) -> str:
    for name, attributes, raw in document.raw_by_element:
        if name == tag and attributes == attrs:
            return raw
    return ""


def _heading_findings(subject: Subject, document: _Document) -> Iterator[Finding]:
    previous = 0
    for heading in document.headings:
        level = int(heading[1])
        if previous and level > previous + 1:
            yield Finding(
                "html-validity",
                subject.name,
                f"heading level jumps from h{previous} to h{level}",
            )
        previous = level


def _reference_findings(subject: Subject, document: _Document) -> Iterator[Finding]:
    known = set(document.ids)
    for tag, attrs in document.elements:
        target = attrs.get("aria-labelledby")
        if target and target not in known:
            yield Finding(
                "html-validity",
                subject.name,
                f"<{tag} aria-labelledby={target!r}> points at no element",
            )
        href = attrs.get("href", "")
        if href.startswith("#") and href[1:] not in known:
            yield Finding(
                "html-validity",
                subject.name,
                f"in-page link {href!r} points at no element",
            )


def _resource_findings(subject: Subject, document: _Document) -> Iterator[Finding]:
    lowered = subject.html.lower()
    for forbidden in ("<script", "<iframe", "<object", "<embed"):
        if forbidden in lowered:
            yield Finding("html-validity", subject.name, f"page contains {forbidden}>")
    if re.search(r"\son[a-z]+\s*=", lowered):
        yield Finding(
            "html-validity", subject.name, "page contains an inline event handler"
        )
    for scheme in ("http://", "https://", "//cdn", "url("):
        if scheme in lowered:
            yield Finding(
                "html-validity",
                subject.name,
                f"page references an external resource ({scheme})",
            )


def check_html_validity(subject: Subject) -> CheckResult:
    """Structural validity, the parts a headless DOM cannot judge for us."""

    result = CheckResult("html-validity")
    document = parse_document(subject.html)
    result.examined = len(document.elements)
    result.findings.extend(_validity_findings(subject, document))
    return result


def assert_subject(subject: Subject) -> list[Finding]:
    """Prove this page is the page we meant to audit, before auditing it.

    Everything compared here comes from the receipt document rather than from
    the page, so an error page, a truncated file, or a page rendered from some
    other receipt cannot satisfy it by being internally consistent.
    """

    findings: list[Finding] = []
    html = subject.html
    if not html.strip():
        findings.append(Finding("wrong-subject", subject.name, "page is empty"))
        return findings
    if not html.startswith("<!DOCTYPE html>"):
        findings.append(
            Finding("wrong-subject", subject.name, "page has no HTML doctype")
        )
    expected = (
        (f'data-cs-page="{PAGE_KIND}"', "is not a receipt page"),
        (
            f'data-cs-payload-sha256="{subject.payload_sha256}"',
            "does not carry the payload hash of the receipt it should render",
        ),
        (f'data-cs-case-id="{subject.case_id}"', "does not carry the expected case id"),
        (f'lang="{subject.locale}"', "is not in the locale it was rendered for"),
        ("<h1 ", "has no level-one heading"),
        ("<main ", "has no main landmark"),
    )
    for needle, complaint in expected:
        if needle not in html:
            findings.append(Finding("wrong-subject", subject.name, f"page {complaint}"))
    for required in subject.required_text:
        if required not in html:
            findings.append(
                Finding(
                    "wrong-subject",
                    subject.name,
                    f"page is missing required content: {required[:60]!r}",
                )
            )
    return findings


def reference_document() -> dict[str, JsonValue]:
    """Build the bundled reference receipt document, in process."""

    def read(name: str) -> object:
        return json.loads((REFERENCE / name).read_text(encoding="utf-8"))

    # `parse_bundle` takes three `object` parameters and validates them itself,
    # so the three `type: ignore[arg-type]` comments that used to sit here
    # suppressed nothing. A suppression that suppresses nothing is a claim about
    # a problem that is not there, which is why `--strict` reports it.
    bundle = parse_bundle(
        read("case.json"), read("observations.json"), read("rules.json")
    )
    return build_receipt_document(bundle, evaluate(bundle))


def presentable_values(document: Mapping[str, JsonValue]) -> frozenset[str]:
    """Return the receipt values the page may show as a run of text.

    Named by pointer rather than by walking the document, so a value the
    receipt carries and the page does not need — an expected or observed hash,
    a rule version, or a field a later contract adds — is not on the list by
    accident. This is the A-036 allowlist.
    """

    payload = document["payload"]
    envelope = document["envelope"]
    if not isinstance(payload, dict) or not isinstance(envelope, dict):
        raise TypeError("receipt payload and envelope must be objects")
    hashes, summary = payload["hashes"], payload["summary"]
    limitations, results = payload["limitations"], payload["results"]
    if not isinstance(hashes, dict) or not isinstance(summary, dict):
        raise TypeError("receipt hashes and summary must be objects")
    if not isinstance(limitations, list) or not isinstance(results, list):
        raise TypeError("receipt limitations and results must be arrays")
    values: list[object] = [
        payload["case_id"],
        payload["runner_version"],
        document["schema_version"],
        sha256_json(payload),
        envelope["claimed_generated_at"],
        *hashes.values(),
        *summary.values(),
        *limitations,
        *(item["rule_id"] for item in results if isinstance(item, dict)),
    ]
    return frozenset(str(value) for value in values if value is not None)


def build_subjects(locales: Sequence[str]) -> tuple[Subject, ...]:
    """Render one page per locale from the bundled reference fixture.

    The hash each page must carry is recomputed from the payload here rather
    than copied from the document's own ``payload_sha256`` field, so a page
    rendered from a document whose field was edited cannot satisfy the gate by
    agreeing with the field.
    """

    document = reference_document()
    payload = document["payload"]
    if not isinstance(payload, dict):  # pragma: no cover - build_receipt_document
        raise TypeError("receipt payload is not an object")
    limitations = payload["limitations"]
    if not isinstance(limitations, list):  # pragma: no cover - schema-pinned
        raise TypeError("receipt limitations are not a list")
    case_id = str(payload["case_id"])
    presentable = presentable_values(document)
    return tuple(
        Subject(
            name=f"receipt.{locale}.html",
            locale=locale,
            html=render_receipt_page(document, locale=locale),
            payload_sha256=sha256_json(payload),
            case_id=case_id,
            required_text=tuple(str(item) for item in limitations),
            presentable=presentable,
        )
        for locale in locales
    )


def run_axe(
    subjects: Sequence[Subject], workdir: Path
) -> tuple[list[Finding], list[str], bool]:
    """Run the axe harness, treating an unavailable engine as a failure."""

    findings: list[Finding] = []
    undetermined: list[str] = []
    node = shutil.which("node")
    if not HARNESS_MODULES.is_dir() or node is None:
        findings.append(
            Finding(
                "engine-unavailable",
                "axe",
                "node or tools/a11y/node_modules is missing; run "
                "`make a11y-install`. A requested engine that cannot run is a "
                "failure, not a skip",
            )
        )
        return findings, undetermined, False
    paths: list[str] = []
    for subject in subjects:
        target = workdir / subject.name
        target.write_text(subject.html, encoding="utf-8")
        paths.append(str(target))
    completed = subprocess.run(  # noqa: S603 - resolved argv, no shell
        [node, str(HARNESS), *paths],
        capture_output=True,
        text=True,
        cwd=HARNESS.parent,
        check=False,
    )
    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError:
        payload = {}
    if not payload.get("ok"):
        findings.append(
            Finding(
                "engine-unavailable",
                "axe",
                f"harness did not run: {payload.get('error') or completed.stderr.strip()[:200]}",
            )
        )
        return findings, undetermined, False
    # `ok` is the harness saying it started, not evidence it examined anything.
    # A harness that answered `{"ok": true}` with no pages produced no finding
    # and no refusal, so the gate reported a clean axe run over zero pages.
    # Every subject handed over must come back.
    returned = {Path(str(page["page"])).name for page in payload.get("pages", [])}
    for subject in subjects:
        if subject.name not in returned:
            findings.append(
                Finding(
                    "engine-examined-nothing",
                    subject.name,
                    "the harness reported success and returned no result for this "
                    "page, so nothing was examined and nothing is proved",
                )
            )
    for page in payload.get("pages", []):
        name = Path(str(page["page"])).name
        if int(page.get("executedRules", 0)) == 0:
            findings.append(
                Finding(
                    "engine-examined-nothing",
                    name,
                    "axe executed no rules against this page, so its "
                    "zero-violation result means nothing",
                )
            )
        undetermined.extend(str(rule) for rule in page.get("undetermined", []))
        for violation in page.get("violations", []):
            findings.append(
                Finding(
                    "axe",
                    name,
                    f"{violation['id']} ({violation.get('impact')}) on "
                    f"{violation.get('nodes')} node(s): {violation.get('help')}",
                )
            )
    return findings, undetermined, True


_CHECKS = {
    "html-validity": check_html_validity,
    "contrast": check_contrast,
    "color-only": check_color_only,
    "print": check_print,
    "minimization": check_minimization,
}


def audit(
    subjects: Sequence[Subject], *, engines: Sequence[str], workdir: Path
) -> Report:
    """Audit ``subjects`` and return a report that counts what it examined."""

    report = Report(declared=len(subjects), engines_requested=tuple(engines))
    if not engines:
        report.findings.append(
            Finding(
                "no-engines",
                "-",
                "no engine was requested, so no check ran; a page nothing "
                "examined is not a page that passed",
            )
        )
    if not subjects:
        report.findings.append(
            Finding(
                "no-pages",
                "-",
                "no page was declared, so nothing was audited and nothing is proved",
            )
        )
        return report
    for engine in engines:
        if engine not in ENGINES:
            report.findings.append(
                Finding("engine-unknown", engine, f"known engines are {list(ENGINES)}")
            )
    audited = _accept_subjects(subjects, report)
    _run_engines(audited, engines=engines, workdir=workdir, report=report)
    report.findings.extend(_coverage_findings(report, engines))
    report.findings.extend(_undetermined_findings(report))
    return report


def _accept_subjects(subjects: Sequence[Subject], report: Report) -> list[Subject]:
    """Return only the pages that proved they are the pages we meant."""

    audited: list[Subject] = []
    for subject in subjects:
        mismatches = assert_subject(subject)
        if mismatches:
            report.findings.extend(mismatches)
            continue
        audited.append(subject)
    report.audited = len(audited)
    return audited


def _run_engines(
    audited: Sequence[Subject],
    *,
    engines: Sequence[str],
    workdir: Path,
    report: Report,
) -> None:
    """Run each requested engine and fold its results into ``report``."""

    if "builtin" in engines:
        report.engines_executed.append("builtin")
        report.checks.extend(_run_builtin(audited))
        for check in report.checks:
            report.findings.extend(check.findings)
    if "axe" in engines:
        findings, undetermined, ran = run_axe(audited, workdir)
        if ran:
            report.engines_executed.append("axe")
        report.findings.extend(findings)
        report.undetermined.extend(undetermined)


def _coverage_findings(report: Report, engines: Sequence[str]) -> Iterator[Finding]:
    """Fail on a page that was not audited or an engine that did not run."""

    if report.audited != report.declared:
        yield Finding(
            "coverage",
            "-",
            f"declared {report.declared} page(s) but audited "
            f"{report.audited}; an unaudited page is not a passing page",
        )
    for engine in engines:
        if engine in ENGINES and engine not in report.engines_executed:
            yield Finding("engine-not-executed", engine, "requested but did not run")


def _undetermined_findings(report: Report) -> Iterator[Finding]:
    """Fail on any rule axe could not decide and nothing else decides either."""

    executed = {check.name for check in report.checks if check.examined > 0}
    for rule in sorted(set(report.undetermined)):
        covering = UNDETERMINED_COVERAGE.get(rule)
        if covering is None:
            yield Finding(
                "undetermined-uncovered",
                rule,
                "axe could not determine this rule and no check here decides "
                "it, so nothing has actually been verified about it",
            )
        elif covering not in executed:
            yield Finding(
                "undetermined-uncovered",
                rule,
                f"axe could not determine this rule and its covering check "
                f"{covering!r} examined nothing",
            )


def _run_builtin(subjects: Iterable[Subject]) -> list[CheckResult]:
    totals = {name: CheckResult(name) for name in BUILTIN_CHECKS}
    for subject in subjects:
        for name, check in _CHECKS.items():
            outcome = check(subject)
            totals[name].examined += outcome.examined
            totals[name].findings.extend(outcome.findings)
    for name, result in totals.items():
        if result.examined == 0:
            result.findings.append(
                Finding(
                    "check-examined-nothing",
                    name,
                    "the check examined nothing, so its clean result is not a pass",
                )
            )
    return list(totals.values())


# Findings that mean "this gate did not examine what it claims to", as opposed
# to "this page has an accessibility defect". They exit 2 rather than 1, so a
# missing node harness is never mistaken for a contrast failure and a passing
# CI job can never be a job whose engine was absent. See ADR 0008.
#
# Four ids were missing here until 2026-08-31, and every one of them was a way
# for the gate to say "I could not look" at exit 1: `--engines ''` (no engine
# requested), `--engines bogus` (an engine that does not exist), a page declared
# and not audited, and a rule axe returned as undetermined that no check here
# decides. All four are the same sentence as an absent node harness.
UNAVAILABLE_RULES: frozenset[str] = frozenset(
    {
        "check-examined-nothing",
        "coverage",
        "engine-examined-nothing",
        "engine-not-executed",
        "engine-unavailable",
        "engine-unknown",
        "no-engines",
        "no-pages",
        "undetermined-uncovered",
    }
)

# Findings that mean "this page has a defect", which is exit 1. Declared rather
# than left as "everything else", so that a rule added later belongs to one list
# or the other by decision: `tests/test_gate_exit_contract.py` reads every rule
# id this module constructs and fails when one is in neither.
DEFECT_RULES: frozenset[str] = frozenset(
    {
        "axe",
        "color-only",
        "contrast",
        "html-validity",
        "minimization",
        "print",
        "wrong-subject",
    }
)


def exit_code(findings: Sequence[Finding]) -> int:
    """Return the gate's exit code for a finding set.

    A run that could not examine everything it was asked to is exit 2 even when
    it also has real findings, because those findings are over an incomplete
    engine set and the reader cannot tell what is missing from them.
    """

    if any(finding.rule in UNAVAILABLE_RULES for finding in findings):
        return 2
    return 1 if findings else 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the gate: 0 clean, 1 with findings, 2 when it examined nothing."""

    parser = argparse.ArgumentParser(description="Accessibility gate (B-043).")
    parser.add_argument(
        "--engines",
        default="builtin",
        help="comma-separated engines to require; a requested engine that "
        "cannot run is a failure, never a skip",
    )
    parser.add_argument(
        "--locale", action="append", help="restrict to one locale; repeatable"
    )
    parser.add_argument("--json", type=Path, help="write the full report here")
    parser.add_argument(
        "--workdir",
        type=Path,
        default=REPO_ROOT / ".a11y",
        help="where rendered pages are written for external engines",
    )
    args = parser.parse_args(argv)
    engines = tuple(part for part in args.engines.split(",") if part)
    locales = tuple(args.locale) if args.locale else DEFAULT_LOCALES
    try:
        args.workdir.mkdir(parents=True, exist_ok=True)
        subjects = build_subjects(locales)
    except (ContextSafeError, OSError) as exc:
        # A locale with no published catalog used to reach the reader as an
        # unhandled traceback at exit 1 -- "examined and found something" for a
        # gate that rendered no page at all. `tools/i18n_gate.py` answers the
        # same input class with exit 2, and two gates in one repository must not
        # answer it differently. See ADR 0008.
        print(f"a11y-gate: {exc}", file=sys.stderr)
        print(
            "a11y-gate: no page could be built, so this is a failure to run the "
            "gate, not a clean result.",
            file=sys.stderr,
        )
        return 2
    report = audit(subjects, engines=engines, workdir=args.workdir)
    if args.json:
        args.json.write_text(
            json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(
        f"a11y-gate: {report.audited}/{report.declared} page(s) audited; "
        f"engines executed: {', '.join(report.engines_executed) or 'none'}"
    )
    for check in report.checks:
        print(f"  {check.name}: examined {check.examined}")
    if report.undetermined:
        print(
            "  undetermined by axe (never counted as a pass): "
            + ", ".join(sorted(set(report.undetermined)))
        )
    code = exit_code(report.findings)
    if report.findings:
        print(f"a11y-gate: {len(report.findings)} finding(s)")
        for finding in report.findings:
            print(finding)
        if code == 2:
            print(
                "a11y-gate: at least one finding is a failure to run a check, "
                "not an accessibility defect, so this is not a clean result.",
                file=sys.stderr,
            )
        return code
    print("a11y-gate: clean")
    return 0


if __name__ == "__main__":  # pragma: no cover - module entry point
    raise SystemExit(main())
