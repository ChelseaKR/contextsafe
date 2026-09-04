#!/usr/bin/env python3
"""Localization gate: catalogs stay in parity, and no unreviewed string lies.

Eight rules, each of which exists because the alternative is a defect somebody
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
    bracketed, so anything still legible was never externalized. Source-locale
    wording is legitimate on that page only where the renderer marks it as a
    source-locale original (``lang`` equal to the source locale): a run of
    English under any other ``lang`` is hardcoded even when it happens to
    repeat a catalog sentence.

``pseudolocale-fidelity``
    The generated pseudolocale is what the rule above sees through, so it is
    measured rather than trusted: every message must grow by at least
    ``PSEUDO_MINIMUM_EXPANSION`` over its source, must leave no letter the
    transform accents unaccented outside a placeholder, and must keep the
    source's ``{placeholder}`` set exactly. A pseudolocale that stopped
    expanding would hide every layout defect it exists to expose, and one
    that mangled a placeholder would be testing its own transform.

Exit 0 when clean, 1 when anything is found, 2 on a usage error.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from string import Formatter

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:  # pragma: no cover - import shim
    sys.path.insert(0, str(REPO_ROOT / "src"))

from contextsafe.canonical import JsonValue  # noqa: E402
from contextsafe.errors import ContextSafeError  # noqa: E402
from contextsafe.evaluator import evaluate  # noqa: E402
from contextsafe.html_receipt import render_receipt_page  # noqa: E402
from contextsafe.i18n import (  # noqa: E402
    PSEUDO_ACCENTABLE,
    PSEUDO_ACCENTED,
    PSEUDO_LOCALE,
    PSEUDO_MINIMUM_EXPANSION,
    SOURCE_LOCALE,
    Catalog,
    ReviewClaim,
    ReviewStatus,
    Surface,
    load_catalog,
    source_catalog,
)
from contextsafe.receipt import build_receipt_document  # noqa: E402
from contextsafe.reference_fixtures import REFERENCE_ROOT  # noqa: E402
from contextsafe.validation import parse_bundle  # noqa: E402

REFERENCE = REFERENCE_ROOT

_IGNORED_TEXT = frozenset({"✔", "✖", "▣", "—", "?"})

_VOID_TAGS = frozenset({"br", "col", "hr", "img", "input", "link", "meta", "wbr"})


@dataclass(frozen=True, slots=True)
class Finding:
    """One gate failure, reported by rule, locale, and detail."""

    rule: str
    locale: str
    detail: str

    def __str__(self) -> str:
        """Return the one-line report form."""

        return f"  {self.rule}: {self.locale}: {self.detail}"


@dataclass(frozen=True, slots=True)
class VisibleRun:
    """One run of reader-visible text and the language it is marked as."""

    text: str
    lang: str | None


class _VisibleText(HTMLParser):
    """Collect text a reader would see, with the ``lang`` in force for each run.

    Head, style, script, and title are skipped. ``lang`` is inherited the way
    a browser inherits it, so a run's language is that of the nearest marked
    ancestor, or none if the page never marked one.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.runs: list[VisibleRun] = []
        self._suppress = 0
        self._langs: list[str | None] = [None]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Push the language in force and start suppressing unrendered text."""

        if tag in _VOID_TAGS:
            return
        lang = dict(attrs).get("lang")
        self._langs.append(lang if lang else self._langs[-1])
        if tag in ("style", "script", "head", "title"):
            self._suppress += 1

    def handle_endtag(self, tag: str) -> None:
        """Pop the language and stop suppressing at the close of the element."""

        if tag in _VOID_TAGS:
            return
        if len(self._langs) > 1:
            self._langs.pop()
        if tag in ("style", "script", "head", "title") and self._suppress:
            self._suppress -= 1

    def handle_data(self, data: str) -> None:
        """Record one run of visible text."""

        if self._suppress:
            return
        text = data.strip()
        if text:
            self.runs.append(VisibleRun(text=text, lang=self._langs[-1]))


def visible_text(html: str) -> list[VisibleRun]:
    """Return every run of reader-visible text on ``html`` with its language."""

    parser = _VisibleText()
    parser.feed(html)
    parser.close()
    return parser.runs


def _placeholders(text: str) -> frozenset[str]:
    return frozenset(
        name for _, name, _, _ in Formatter().parse(text) if name is not None
    )


def _literals(text: str) -> str:
    """Return ``text`` with every ``{placeholder}`` removed."""

    return "".join(literal for literal, _, _, _ in Formatter().parse(text))


def _diacritic_findings(
    locale: str, key: str, original: str, generated: str
) -> Iterator[Finding]:
    """Every accentable letter outside a placeholder must have been accented.

    "Some diacritic somewhere" was the earlier rule, and a transform that
    accented one letter per message satisfied it while leaving the rest of the
    sentence legible English. Legible English on the pseudolocalized page is
    exactly what ``hardcoded-string`` reads as a defect, so the pseudolocale
    may not produce any.
    """

    plain = sorted(PSEUDO_ACCENTABLE & set(_literals(generated)))
    if plain:
        yield Finding(
            "pseudolocale-fidelity",
            locale,
            f"{key}: leaves {len(plain)} accentable letter(s) plain, so it is "
            "legible where it should carry a diacritic",
        )
    elif PSEUDO_ACCENTABLE & set(_literals(original)) and not (
        PSEUDO_ACCENTED & set(generated)
    ):
        yield Finding("pseudolocale-fidelity", locale, f"{key}: carries no diacritic")


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
    locale: str, document: Mapping[str, object], catalog: Catalog | None = None
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
    catalog: Catalog, document: Mapping[str, object]
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


def check_hardcoded_strings(document: Mapping[str, object]) -> Iterator[Finding]:
    """Find visible text on the page that no catalog message accounts for.

    A run marked as the source locale may be a source-locale message, because
    that is how the renderer shows the original beside an unreviewed
    translation. Under any other ``lang`` only a pseudolocalized message will
    do: English there was never externalized, even English that repeats a
    catalog sentence word for word.
    """

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
    source = source_catalog()
    for index, run in enumerate(visible_text(page)):
        if run.text in allowed:
            continue
        accounting = source if run.lang == SOURCE_LOCALE else catalog
        if accounting.accounts_for(run.text):
            continue
        # Named by position, size, and the language it was judged under,
        # never quoted: the run this rule catches on a real page is exactly
        # the text that must not be copied into a report.
        yield Finding(
            "hardcoded-string",
            catalog.locale,
            f"visible text run {index} ({len(run.text)} characters) under "
            f"lang={run.lang!r} is accounted for by no message",
        )


def check_pseudolocale(catalog: Catalog) -> Iterator[Finding]:
    """Measure the pseudolocale against the floor it is supposed to hold.

    Three properties, each with a way to fail: expansion below
    ``PSEUDO_MINIMUM_EXPANSION``, an accentable letter left plain anywhere
    outside a placeholder, and a placeholder set that differs from the
    source. The catalog is a parameter so a negative control can hand in a
    weakened one. An empty source message is ``message-quality``'s finding,
    so it is skipped here rather than divided by.
    """

    source = source_catalog()
    for key in sorted(source.keys() - catalog.keys()):
        yield Finding("pseudolocale-fidelity", catalog.locale, f"missing key {key}")
    for key in sorted(source.keys() & catalog.keys()):
        original = source.message(key).text
        generated = catalog.message(key).text
        if not original:
            continue
        growth = (len(generated) - len(original)) / len(original)
        if growth < PSEUDO_MINIMUM_EXPANSION:
            yield Finding(
                "pseudolocale-fidelity",
                catalog.locale,
                f"{key}: expanded {growth:.0%}, below {PSEUDO_MINIMUM_EXPANSION:.0%}",
            )
        yield from _diacritic_findings(catalog.locale, key, original, generated)
        if _placeholders(original) != _placeholders(generated):
            yield Finding(
                "pseudolocale-fidelity",
                catalog.locale,
                f"{key}: placeholders {sorted(_placeholders(generated))} differ "
                f"from {sorted(_placeholders(original))}",
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
        raise GateUnavailable("no catalog was examined, so nothing was proved")
    findings.extend(check_pseudolocale(load_catalog(PSEUDO_LOCALE)))
    findings.extend(check_hardcoded_strings(document))
    return findings


def shipped_catalogs() -> tuple[Catalog, ...]:
    """Return every catalog that ships in the package."""

    locales = sorted(
        path.stem
        for path in (REPO_ROOT / "src" / "contextsafe" / "locales").glob("*.json")
    )
    return tuple(load_catalog(locale) for locale in locales)


class GateUnavailable(Exception):
    """The gate examined nothing, which is never a clean result.

    Exit 2, not exit 1. This gate used to report "no catalog was examined" as a
    finding, which put it at the same exit code as a real parity failure and
    lost the distinction the rest of the gates in this repository keep. See
    ADR 0008.
    """


def main(argv: Sequence[str] | None = None) -> int:
    """Run the gate: 0 clean, 1 with findings, 2 when it examined nothing."""

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
    try:
        catalogs = (
            tuple(load_catalog(locale) for locale in args.locale)
            if args.locale
            else shipped_catalogs()
        )
        findings = run_gate(catalogs)
    except (GateUnavailable, ContextSafeError, OSError, json.JSONDecodeError) as exc:
        print(f"i18n-gate: {exc}.", file=sys.stderr)
        print(
            "i18n-gate: this is a failure to run the gate, not a clean result.",
            file=sys.stderr,
        )
        return 2
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
