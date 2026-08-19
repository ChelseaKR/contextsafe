#!/usr/bin/env python3
"""Localization gate: catalogs stay in parity, and no unreviewed string lies.

Six rules, each of which exists because the alternative is a defect somebody
would only find in front of a reader.

``catalog-parity``
    A shipped locale is missing a key the source locale has, or carries one it
    does not. A missing key means a reader hits a fail-closed error mid-page;
    an extra key means dead weight that a translator was paid to produce.

``placeholder-parity``
    A translated string's ``{placeholder}`` set differs from the source's. This
    is the classic localization crash: the substitution raises, or worse,
    quietly drops the value the sentence was about.

``message-quality``
    An empty message, or a source-locale entry marked as a translation. The
    source locale is authored, not translated; if an entry there claims to be
    machine translated, the review status of the whole catalog stops meaning
    anything.

``review-consistency``
    A catalog claims ``human`` review while containing an unreviewed string, or
    claims ``human`` without naming a reviewer and a date. A review record that
    nobody signed is worse than no record: it is a false one.

``unreviewed-on-reviewed-surface``
    A surface declaring ``human_reviewed`` accepts a string that has not been
    reviewed. This is the one a sibling repository shipped today in a different
    shape — a placeholder verifier rendering as human verification on every
    source line — and it is the reason this gate exists at all. Every shipped
    locale is pulled through a claiming surface; a machine-translated locale
    must be refused, and a human-reviewed one must be accepted.

``undisclosed-machine-translation``
    A rendered page whose catalog is machine translated does not carry the
    unreviewed-translation notice, or a reviewed one carries it anyway. Both
    directions matter: a notice that appears when it should not is noise that
    teaches readers to ignore it.

``hardcoded-string``
    A run of visible text on the rendered page that no catalog message
    accounts for and that does not come from the receipt document. Found by
    rendering the pseudolocale, where every externalized string is accented and
    bracketed, so anything still legible was never externalized.

Exit 0 when clean, 1 when anything is found, 2 on a usage error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from string import Formatter

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:  # pragma: no cover - import shim
    sys.path.insert(0, str(REPO_ROOT / "src"))

from contextsafe.errors import ContextSafeError  # noqa: E402
from contextsafe.evaluator import evaluate  # noqa: E402
from contextsafe.html_receipt import render_receipt_page  # noqa: E402
from contextsafe.i18n import (  # noqa: E402
    PSEUDO_LOCALE,
    SOURCE_LOCALE,
    Catalog,
    ReviewClaim,
    ReviewStatus,
    Surface,
    load_catalog,
    source_catalog,
)
from contextsafe.receipt import build_receipt_document  # noqa: E402
from contextsafe.validation import parse_bundle  # noqa: E402

REFERENCE = REPO_ROOT / "fixtures" / "reference"

_IGNORED_TEXT = frozenset({"✔", "✖", "▣", "—", "?"})


@dataclass(frozen=True, slots=True)
class Finding:
    """One gate failure, reported by rule, locale, and detail."""

    rule: str
    locale: str
    detail: str

    def __str__(self) -> str:
        """Return the one-line report form."""

        return f"  {self.rule}: {self.locale}: {self.detail}"


class _VisibleText(HTMLParser):
    """Collect text a reader would see, skipping head, style, and script."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.runs: list[str] = []
        self._suppress = 0

    def handle_starttag(self, tag: str, attrs: object) -> None:
        """Start suppressing text inside non-rendered elements."""

        if tag in ("style", "script", "head", "title"):
            self._suppress += 1

    def handle_endtag(self, tag: str) -> None:
        """Stop suppressing at the close of a non-rendered element."""

        if tag in ("style", "script", "head", "title") and self._suppress:
            self._suppress -= 1

    def handle_data(self, data: str) -> None:
        """Record one run of visible text."""

        if self._suppress:
            return
        text = data.strip()
        if text:
            self.runs.append(text)


def visible_text(html: str) -> list[str]:
    """Return every run of reader-visible text on ``html``."""

    parser = _VisibleText()
    parser.feed(html)
    parser.close()
    return parser.runs


def _placeholders(text: str) -> frozenset[str]:
    return frozenset(
        name for _, name, _, _ in Formatter().parse(text) if name is not None
    )


def reference_document() -> dict[str, object]:
    """Build the bundled reference receipt document, in process."""

    def read(name: str) -> object:
        return json.loads((REFERENCE / name).read_text(encoding="utf-8"))

    bundle = parse_bundle(
        read("case.json"),  # type: ignore[arg-type]
        read("observations.json"),  # type: ignore[arg-type]
        read("rules.json"),  # type: ignore[arg-type]
    )
    return build_receipt_document(bundle, evaluate(bundle))


def _document_strings(value: object) -> Iterator[str]:
    if isinstance(value, dict):
        for item in value.values():
            yield from _document_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _document_strings(item)
    elif isinstance(value, bool):
        return
    elif isinstance(value, str | int):
        yield str(value)


def _message_patterns(catalog: Catalog) -> tuple[re.Pattern[str], ...]:
    patterns: list[re.Pattern[str]] = []
    for message in catalog.messages.values():
        parts = [
            re.escape(literal) + ("(?s:.+?)" if field is not None else "")
            for literal, field, _, _ in Formatter().parse(message.text)
        ]
        patterns.append(re.compile("".join(parts)))
    return tuple(patterns)


def check_parity(catalog: Catalog) -> Iterator[Finding]:
    """Compare one catalog's keys and placeholders with the source locale."""

    source = source_catalog()
    if catalog.locale == source.locale:
        return
    for key in sorted(source.keys() - catalog.keys()):
        yield Finding("catalog-parity", catalog.locale, f"missing key {key}")
    for key in sorted(catalog.keys() - source.keys()):
        yield Finding("catalog-parity", catalog.locale, f"unknown key {key}")
    for key in sorted(source.keys() & catalog.keys()):
        expected = _placeholders(source.message(key).text)
        actual = _placeholders(catalog.message(key).text)
        if expected != actual:
            yield Finding(
                "placeholder-parity",
                catalog.locale,
                f"{key}: expected {sorted(expected)}, found {sorted(actual)}",
            )


def check_message_quality(catalog: Catalog) -> Iterator[Finding]:
    """Reject empty text, and translation markings in the source locale."""

    for key in sorted(catalog.keys()):
        message = catalog.message(key)
        if not message.text.strip():
            yield Finding("message-quality", catalog.locale, f"{key}: empty text")
        if (
            catalog.locale == SOURCE_LOCALE
            and message.review is not ReviewStatus.SOURCE
        ):
            yield Finding(
                "message-quality",
                catalog.locale,
                f"{key}: source-locale entry marked {message.review}",
            )


def check_review_consistency(catalog: Catalog) -> Iterator[Finding]:
    """A catalog may not claim more review than its strings have had."""

    if catalog.review.human_reviewed:
        unreviewed = sorted(
            key
            for key, message in catalog.messages.items()
            if message.review is not ReviewStatus.HUMAN
        )
        if unreviewed:
            yield Finding(
                "review-consistency",
                catalog.locale,
                f"catalog claims human review but {len(unreviewed)} strings have not"
                f" been reviewed, starting at {unreviewed[0]}",
            )
        if not catalog.review.reviewed_by or not catalog.review.reviewed_at:
            yield Finding(
                "review-consistency",
                catalog.locale,
                "catalog claims human review without naming a reviewer and a date",
            )


def check_claiming_surface(catalog: Catalog) -> Iterator[Finding]:
    """Pull every string through a surface that claims human review."""

    surface = Surface(
        name="i18n-gate", catalog=catalog, claim=ReviewClaim.HUMAN_REVIEWED
    )
    refused: list[str] = []
    for key in sorted(catalog.keys()):
        try:
            surface.message(key)
        except ContextSafeError as exc:
            if exc.code != "unreviewed_string_on_reviewed_surface":
                raise
            refused.append(key)
    expected_refusal = catalog.is_machine_translated
    if expected_refusal and not refused:
        yield Finding(
            "unreviewed-on-reviewed-surface",
            catalog.locale,
            "catalog carries machine-translated strings that a surface claiming"
            " human review accepted",
        )
    if not expected_refusal and refused:
        yield Finding(
            "unreviewed-on-reviewed-surface",
            catalog.locale,
            f"a reviewed catalog was refused at {refused[0]}",
        )


def _render(
    locale: str, document: dict[str, object], catalog: Catalog | None = None
) -> tuple[str | None, Finding | None]:
    """Render a page, turning a fail-closed rejection into a finding.

    A locale that cannot render at all is a worse failure than any single rule
    here, and it must not arrive as a traceback that hides the findings already
    collected.
    """

    try:
        page = render_receipt_page(document, locale=locale, catalog=catalog)  # type: ignore[arg-type]
        return page, None
    except ContextSafeError as exc:
        return None, Finding("render-failed", locale, f"{exc.code} at {exc.path}")


def check_disclosure(
    catalog: Catalog, document: dict[str, object]
) -> Iterator[Finding]:
    """The page must disclose an unreviewed translation, and only then."""

    page, failure = _render(catalog.locale, document, catalog)
    if page is None:
        yield (
            failure
            if failure is not None
            else Finding("render-failed", catalog.locale, "page did not render")
        )
        return
    discloses = 'data-cs-notice="machine-translation"' in page
    if catalog.is_machine_translated and not discloses:
        yield Finding(
            "undisclosed-machine-translation",
            catalog.locale,
            "page renders machine-translated strings without the notice",
        )
    if not catalog.is_machine_translated and discloses:
        yield Finding(
            "undisclosed-machine-translation",
            catalog.locale,
            "page shows the unreviewed-translation notice for a reviewed catalog",
        )


def check_hardcoded_strings(document: dict[str, object]) -> Iterator[Finding]:
    """Find visible text on the page that no catalog message accounts for."""

    catalog = load_catalog(PSEUDO_LOCALE)
    page, failure = _render(PSEUDO_LOCALE, document)
    if page is None:
        yield (
            failure
            if failure is not None
            else Finding("render-failed", PSEUDO_LOCALE, "page did not render")
        )
        return
    allowed = frozenset(_document_strings(document)) | _IGNORED_TEXT
    patterns = _message_patterns(catalog) + _message_patterns(source_catalog())
    for run in visible_text(page):
        if run in allowed:
            continue
        if any(pattern.fullmatch(run) for pattern in patterns):
            continue
        yield Finding(
            "hardcoded-string",
            catalog.locale,
            f"visible text no message accounts for: {run!r}",
        )


def run_gate(catalogs: Iterable[Catalog]) -> list[Finding]:
    """Run every rule over ``catalogs`` and return the findings in order."""

    document = reference_document()
    findings: list[Finding] = []
    seen = 0
    for catalog in catalogs:
        seen += 1
        findings.extend(check_parity(catalog))
        findings.extend(check_message_quality(catalog))
        findings.extend(check_review_consistency(catalog))
        findings.extend(check_claiming_surface(catalog))
        findings.extend(check_disclosure(catalog, document))
    if seen == 0:
        findings.append(
            Finding(
                "no-catalogs", "-", "no catalog was examined, so nothing was proved"
            )
        )
        return findings
    findings.extend(check_hardcoded_strings(document))
    return findings


def shipped_catalogs() -> tuple[Catalog, ...]:
    """Return every catalog that ships in the package."""

    locales = sorted(
        path.stem
        for path in (REPO_ROOT / "src" / "contextsafe" / "locales").glob("*.json")
    )
    return tuple(load_catalog(locale) for locale in locales)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the gate and return 0 clean, 1 with findings, 2 on usage error."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--locale",
        action="append",
        help="restrict the gate to one locale; repeatable",
    )
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:  # pragma: no cover - argparse exits directly
        return 2 if exc.code else 0
    catalogs = (
        tuple(load_catalog(locale) for locale in args.locale)
        if args.locale
        else shipped_catalogs()
    )
    findings = run_gate(catalogs)
    if findings:
        print(f"i18n-gate: {len(findings)} finding(s)")
        for finding in findings:
            print(finding)
        return 1
    print(
        f"i18n-gate: clean over {len(catalogs)} catalog(s): "
        f"{', '.join(catalog.locale for catalog in catalogs)}"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - module entry point
    raise SystemExit(main())
