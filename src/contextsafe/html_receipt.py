"""Script-free, deterministic HTML rendering of a receipt document (B-034).

The receipt document is the machine artifact: canonical JSON, hash-covered,
one fixed language. This module is the human artifact rendered from it, and it
is deliberately the *only* place in the package where wording varies by locale.

Constraints this renderer holds, each of which has a gate behind it:

* **No script and no network.** No ``<script>``, no event-handler attribute,
  no external stylesheet, font, or image. The page opens from a file:// URL on
  a machine with no network, which is the environment this tool runs in.
* **Deterministic.** The same receipt document and locale always produce the
  same bytes. Nothing here reads a clock, an environment variable, a locale
  database, or the filesystem.
* **Nothing added, nothing removed.** Every hash, status, and mandated
  limitation in the payload appears on the page. The renderer never computes a
  judgement of its own; ``data-cs-payload-sha256`` on ``<main>`` ties the page
  to the exact payload it was rendered from, so a gate can prove it audited
  this receipt rather than some other page.
* **Never colour alone.** Every status carries its word and a distinct symbol.
  Removing every colour from this page loses no information, which is what
  makes it survive black-and-white print, forced-colours mode, and the several
  kinds of colour vision the status palette would otherwise exclude.
* **An unreviewed translation says so.** See ``i18n``: when the chosen locale
  is machine translated, the page carries a notice in both the target and the
  source locale, and every mandated safety disclosure renders next to its
  source-locale original.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from html import escape

from contextsafe.canonical import JsonValue
from contextsafe.errors import ContextSafeError
from contextsafe.i18n import (
    SOURCE_LOCALE,
    Catalog,
    Message,
    ReviewStatus,
    Surface,
    load_catalog,
    source_catalog,
)

PAGE_KIND = "receipt"
"""Value of ``data-cs-page``. A gate asserts on it before auditing anything."""

_STATUS_SYMBOLS = {
    "pass": "✔",
    "fail": "✖",
    "indeterminate": "?",
    "blocked": "▣",
    "not_applicable": "—",
}

_BOOLEAN_SYMBOLS = {True: "✔", False: "✖"}

_HASH_ORDER = ("input_sha256", "result_sha256", "rule_set_sha256")

_STYLE = """
:root { color-scheme: light; }
html { background-color: #ffffff; color: #1a1a1a; }
body {
  background-color: #ffffff;
  color: #1a1a1a;
  font-family: Georgia, "Times New Roman", serif;
  line-height: 1.5;
  margin: 0 auto;
  max-width: 46rem;
  padding: 1.5rem;
}
a { background-color: #ffffff; color: #0b3d91; }
a:focus { background-color: #ffec99; color: #1a1a1a; outline: 3px solid #1a1a1a; }
.skip-link {
  background-color: #ffffff;
  color: #0b3d91;
  display: inline-block;
  padding: 0.25rem 0;
}
h1, h2, h3 { background-color: #ffffff; color: #1a1a1a; line-height: 1.25; }
h1 { font-size: 1.75rem; }
h2 { border-bottom: 2px solid #1a1a1a; font-size: 1.3rem; padding-bottom: 0.2rem; }
h3 { font-size: 1.05rem; }
p, li, dd, dt, caption, th, td { background-color: #ffffff; color: #1a1a1a; }
.subheading { background-color: #ffffff; color: #3d3d3d; font-size: 1.05rem; }
.notice {
  background-color: #fff8e1;
  border: 3px solid #6b4a00;
  color: #3d2a00;
  padding: 0.75rem 1rem;
}
.notice h2 { background-color: #fff8e1; border-bottom: none; color: #3d2a00; }
.notice p { background-color: #fff8e1; color: #3d2a00; }
.source-text {
  background-color: #f4f4f4;
  border-left: 4px solid #4a4a4a;
  color: #1a1a1a;
  padding: 0.4rem 0.75rem;
}
.source-label {
  background-color: #f4f4f4;
  color: #3d3d3d;
  display: block;
  font-size: 0.85rem;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
table { border-collapse: collapse; width: 100%; }
caption {
  background-color: #ffffff;
  caption-side: top;
  color: #3d3d3d;
  padding-bottom: 0.4rem;
  text-align: left;
}
th, td { border: 1px solid #767676; padding: 0.4rem 0.5rem; text-align: left; }
th { background-color: #efefef; color: #1a1a1a; }
.status { background-color: #ffffff; color: #1a1a1a; white-space: nowrap; }
.status-symbol {
  background-color: #ffffff;
  border: 2px solid #1a1a1a;
  color: #1a1a1a;
  display: inline-block;
  font-family: monospace;
  margin-right: 0.4rem;
  min-width: 1.4em;
  text-align: center;
}
.hash { background-color: #ffffff; color: #1a1a1a; font-family: monospace; overflow-wrap: anywhere; }
dt { background-color: #ffffff; color: #3d3d3d; font-weight: bold; }
dd { background-color: #ffffff; color: #1a1a1a; margin: 0 0 0.6rem 0; }
footer { background-color: #ffffff; border-top: 1px solid #767676; color: #3d3d3d; margin-top: 2rem; padding-top: 0.75rem; }
footer p { background-color: #ffffff; color: #3d3d3d; }
@media print {
  body { background-color: #ffffff; color: #000000; max-width: none; padding: 0; }
  .skip-link { display: none; }
  .notice { background-color: #ffffff; border: 3px solid #000000; color: #000000; }
  .notice h2, .notice p { background-color: #ffffff; color: #000000; }
  .source-text, .source-label { background-color: #ffffff; color: #000000; }
  th { background-color: #ffffff; color: #000000; }
  section, table, tr { break-inside: avoid; }
}
"""


@dataclass(frozen=True, slots=True)
class _Row:
    """One rendered rule outcome, already resolved to display text."""

    rule_id: str
    checkpoint: str
    concept: str
    status_key: str
    status_text: str
    reason: str


def _mapping(value: JsonValue | None, pointer: str) -> Mapping[str, JsonValue]:
    if not isinstance(value, dict):
        raise ContextSafeError(
            "invalid_receipt_document", pointer, "expected a JSON object"
        )
    return value


def _text(value: JsonValue | None, pointer: str) -> str:
    if not isinstance(value, str):
        raise ContextSafeError(
            "invalid_receipt_document", pointer, "expected a JSON string"
        )
    return value


def _sequence(value: JsonValue | None, pointer: str) -> Sequence[JsonValue]:
    if not isinstance(value, list):
        raise ContextSafeError(
            "invalid_receipt_document", pointer, "expected a JSON array"
        )
    return value


def _attr(name: str, value: str) -> str:
    return f'{name}="{escape(value, quote=True)}"'


def _marked(message: Message) -> str:
    """Return the ``lang``/``data-cs-review`` attributes a string must carry.

    Marking is per string rather than per page on purpose: a page can mix
    reviewed and unreviewed wording, and a reader who is deciding how much to
    trust one sentence should not have to reason about the whole document.
    """

    return f"{_attr('lang', message.locale)} {_attr('data-cs-review', message.review)}"


def _paragraph(message: Message, *, css_class: str | None = None) -> str:
    classes = f" {_attr('class', css_class)}" if css_class else ""
    return f"<p {_marked(message)}{classes}>{escape(message.text)}</p>"


def _source_original(surface: Surface, key: str, **values: object) -> str:
    """Return the source-locale original of ``key``, labelled as the original."""

    original = source_catalog().message(key)
    if values:
        original = original.format(**values)
    label = surface.message("translation.source_label", locale=SOURCE_LOCALE)
    return (
        f'<div class="source-text">'
        f'<span {_marked(label)} class="source-label">{escape(label.text)}</span>'
        f"{_paragraph(original)}"
        f"</div>"
    )


def _safety_text(surface: Surface, key: str, **values: object) -> str:
    """Render a safety-critical string, with its original when unreviewed.

    This is the rule that matters most in this file. A machine translation of
    "not an approved clinical oracle" is exactly the sentence a reader must not
    be left alone with, so when the wording is unreviewed the source-locale
    original renders directly beneath it rather than being available somewhere
    else.
    """

    message = surface.message(key, **values)
    rendered = _paragraph(message)
    if message.reviewed:
        return rendered
    return rendered + _source_original(surface, key, **values)


def _notice(surface: Surface) -> str:
    """Return the unreviewed-translation notice, or nothing if none is due."""

    if not surface.must_disclose_machine_translation:
        return ""
    heading = surface.message("translation.unreviewed.heading")
    target, original = surface.disclosure()
    # No explicit role: `role="note"` would override the implicit
    # `complementary` landmark of `<aside>`, which puts the notice outside every
    # landmark on the page and makes it skippable by exactly the readers it is
    # addressed to. axe's `region` rule caught that; the name comes from the
    # heading instead.
    return (
        '<aside class="notice" aria-labelledby="translation-notice" '
        'data-cs-notice="machine-translation">'
        f'<h2 id="translation-notice" {_marked(heading)}>'
        f"{escape(heading.text)}</h2>"
        f"{_paragraph(target)}"
        f"{_paragraph(original)}"
        "</aside>"
    )


def _limitation_keys() -> Mapping[str, str]:
    """Map each source-locale limitation sentence to its message key.

    Keyed by the sentence itself, so a reworded mandated limitation cannot
    keep a stale translation: the lookup simply misses and the page falls back
    to the receipt's own wording with an explicit "no translation published"
    note. Silence would be the dangerous behaviour here.
    """

    source = source_catalog()
    return {
        message.text: key
        for key, message in source.messages.items()
        if key.startswith("limitation.")
    }


def _limitations(surface: Surface, limitations: Sequence[JsonValue]) -> str:
    keys = _limitation_keys()
    items: list[str] = []
    for index, raw in enumerate(limitations):
        sentence = _text(raw, f"$.payload.limitations[{index}]")
        key = keys.get(sentence)
        if key is None:
            items.append(f"<li>{_untranslated(surface, sentence)}</li>")
            continue
        items.append(f"<li>{_safety_text(surface, key)}</li>")
    return "".join(items)


def _untranslated(surface: Surface, sentence: str) -> str:
    """Render receipt wording no catalog covers, and say that plainly."""

    note = surface.message("translation.unavailable", locale=SOURCE_LOCALE)
    source_message = Message(
        key="limitation.untranslated",
        text=sentence,
        review=ReviewStatus.SOURCE,
        locale=SOURCE_LOCALE,
    )
    return _paragraph(source_message) + _paragraph(note, css_class="source-label")


def _scope(surface: Surface, scope: Mapping[str, JsonValue]) -> str:
    rows: list[str] = []
    for name in sorted(scope):
        raw = scope[name]
        if not isinstance(raw, bool):
            raise ContextSafeError(
                "invalid_receipt_document",
                f"$.payload.scope.{name}",
                "scope values must be booleans",
            )
        label = surface.message(f"scope.{name}.label")
        state = surface.message("value.yes" if raw else "value.no")
        symbol = _BOOLEAN_SYMBOLS[raw]
        rows.append(
            f"<dt {_marked(label)}>{escape(label.text)}</dt>"
            f'<dd class="status" {_attr("data-cs-boolean", "true" if raw else "false")}>'
            f'<span class="status-symbol" aria-hidden="true">{escape(symbol)}</span>'
            f"<span {_marked(state)}>{escape(state.text)}</span></dd>"
        )
    return "".join(rows)


def _status_cell(surface: Surface, status: str) -> tuple[str, str]:
    symbol = _STATUS_SYMBOLS.get(status)
    if symbol is None:
        raise ContextSafeError(
            "invalid_receipt_document",
            "$.payload.results[].status",
            "status is not a published outcome status",
        )
    message = surface.message(f"status.{status}")
    return symbol, message.text


def _rows(surface: Surface, results: Sequence[JsonValue]) -> tuple[_Row, ...]:
    rows: list[_Row] = []
    for index, raw in enumerate(results):
        result = _mapping(raw, f"$.payload.results[{index}]")
        status = _text(result.get("status"), f"$.payload.results[{index}].status")
        _, status_text = _status_cell(surface, status)
        rows.append(
            _Row(
                rule_id=_text(
                    result.get("rule_id"), f"$.payload.results[{index}].rule_id"
                ),
                checkpoint=surface.text(
                    "checkpoint."
                    + _text(
                        result.get("checkpoint"),
                        f"$.payload.results[{index}].checkpoint",
                    )
                ),
                concept=surface.text(
                    "concept."
                    + _text(
                        result.get("concept"), f"$.payload.results[{index}].concept"
                    )
                ),
                status_key=status,
                status_text=status_text,
                reason=surface.text(
                    "reason."
                    + _text(result.get("reason"), f"$.payload.results[{index}].reason")
                ),
            )
        )
    return tuple(rows)


def _results_table(surface: Surface, rows: Iterable[_Row]) -> str:
    caption = surface.message("table.results.caption")
    headers = "".join(
        f'<th scope="col" {_marked(surface.message(key))}>'
        f"{escape(surface.text(key))}</th>"
        for key in (
            "column.rule",
            "column.checkpoint",
            "column.concept",
            "column.status",
            "column.reason",
        )
    )
    body = "".join(
        f'<tr><th scope="row" class="hash">{escape(row.rule_id)}</th>'
        f"<td>{escape(row.checkpoint)}</td>"
        f"<td>{escape(row.concept)}</td>"
        f'<td class="status" {_attr("data-cs-status", row.status_key)}>'
        f'<span class="status-symbol" aria-hidden="true">'
        f"{escape(_STATUS_SYMBOLS[row.status_key])}</span>"
        f"<span {_marked(surface.message(f'status.{row.status_key}'))}>"
        f"{escape(row.status_text)}</span></td>"
        f"<td>{escape(row.reason)}</td></tr>"
        for row in rows
    )
    return (
        f"<table><caption {_marked(caption)}>{escape(caption.text)}</caption>"
        f"<thead><tr>{headers}</tr></thead><tbody>{body}</tbody></table>"
    )


def _summary_table(surface: Surface, summary: Mapping[str, JsonValue]) -> str:
    caption = surface.message("table.summary.caption")
    status_header = surface.message("column.status")
    count_header = surface.message("column.count")
    rows: list[str] = []
    for status in sorted(summary):
        count = summary[status]
        if not isinstance(count, int) or isinstance(count, bool):
            raise ContextSafeError(
                "invalid_receipt_document",
                f"$.payload.summary.{status}",
                "summary counts must be integers",
            )
        symbol, label = _status_cell(surface, status)
        rows.append(
            f'<tr><th scope="row" class="status" {_attr("data-cs-status", status)}>'
            f'<span class="status-symbol" aria-hidden="true">{escape(symbol)}</span>'
            f"<span {_marked(surface.message(f'status.{status}'))}>"
            f"{escape(label)}</span></th>"
            f"<td>{count}</td></tr>"
        )
    return (
        f"<table><caption {_marked(caption)}>{escape(caption.text)}</caption>"
        f"<thead><tr>"
        f'<th scope="col" {_marked(status_header)}>{escape(status_header.text)}</th>'
        f'<th scope="col" {_marked(count_header)}>{escape(count_header.text)}</th>'
        f"</tr></thead><tbody>{''.join(rows)}</tbody></table>"
    )


def _hashes(
    surface: Surface, hashes: Mapping[str, JsonValue], payload_sha256: str
) -> str:
    items: list[str] = []
    for name in _HASH_ORDER:
        label = surface.message(f"hash.{name}")
        value = _text(hashes.get(name), f"$.payload.hashes.{name}")
        items.append(
            f"<dt {_marked(label)}>{escape(label.text)}</dt>"
            f'<dd class="hash">{escape(value)}</dd>'
        )
    payload_label = surface.message("hash.payload_sha256")
    items.append(
        f"<dt {_marked(payload_label)}>{escape(payload_label.text)}</dt>"
        f'<dd class="hash">{escape(payload_sha256)}</dd>'
    )
    return "".join(items)


def _envelope(surface: Surface, envelope: Mapping[str, JsonValue]) -> str:
    claimed = envelope.get("claimed_generated_at")
    claimed_label = surface.message("envelope.claimed_generated_at.label")
    signature_label = surface.message("envelope.signature_status.label")
    signature_value = surface.message("envelope.signature_status.not_signed")
    time_label = surface.message("envelope.trusted_time.label")
    time_value = surface.message("envelope.trusted_time.false")
    if (
        envelope.get("signature_status") != "not_signed"
        or envelope.get("trusted_time") is not False
    ):
        raise ContextSafeError(
            "invalid_receipt_document",
            "$.envelope",
            "this iteration renders unsigned, untrusted-time envelopes only",
        )
    if claimed is None:
        claimed_message = surface.message("envelope.claimed_generated_at.absent")
        claimed_html = (
            f"<span {_marked(claimed_message)}>{escape(claimed_message.text)}</span>"
        )
    else:
        claimed_html = f'<span class="hash">{escape(_text(claimed, "$.envelope.claimed_generated_at"))}</span>'
    return (
        f"<dt {_marked(signature_label)}>{escape(signature_label.text)}</dt>"
        f"<dd {_marked(signature_value)}>{escape(signature_value.text)}</dd>"
        f"<dt {_marked(time_label)}>{escape(time_label.text)}</dt>"
        f"<dd {_marked(time_value)}>{escape(time_value.text)}</dd>"
        f"<dt {_marked(claimed_label)}>{escape(claimed_label.text)}</dt>"
        f"<dd>{claimed_html}</dd>"
    )


def _section(surface: Surface, heading_key: str, ident: str, body: str) -> str:
    heading = surface.message(heading_key)
    return (
        f'<section aria-labelledby="{ident}">'
        f'<h2 id="{ident}" {_marked(heading)}>{escape(heading.text)}</h2>'
        f"{body}</section>"
    )


def render_receipt_page(
    document: Mapping[str, JsonValue],
    *,
    locale: str = SOURCE_LOCALE,
    catalog: Catalog | None = None,
) -> str:
    """Render a receipt document as one self-contained HTML page.

    Deterministic in ``document`` and the catalog, and nothing else. A caller
    may pass an in-memory ``catalog`` rather than a locale name so that a gate
    can render exactly the catalog it just inspected: auditing one catalog and
    rendering a different one is the shape of bug this repository keeps
    finding elsewhere.
    """

    if catalog is None:
        catalog = load_catalog(locale)
    elif catalog.locale != locale and locale != SOURCE_LOCALE:
        raise ContextSafeError(
            "catalog_locale_mismatch",
            "$.locale",
            "catalog does not match the locale requested",
        )
    surface = Surface(name="receipt-html", catalog=catalog)
    payload = _mapping(document.get("payload"), "$.payload")
    envelope = _mapping(document.get("envelope"), "$.envelope")
    payload_sha256 = _text(document.get("payload_sha256"), "$.payload_sha256")
    case_id = _text(payload.get("case_id"), "$.payload.case_id")
    body = _body(surface, document, payload, envelope, payload_sha256, case_id)
    title = surface.message("page.title")
    return (
        "<!DOCTYPE html>\n"
        f"<html {_attr('lang', catalog.locale)}>\n"
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{escape(title.text)}</title>\n"
        f"<style>{_STYLE}</style>\n"
        "</head>\n"
        f"{body}\n"
        "</html>\n"
    )


def _body(
    surface: Surface,
    document: Mapping[str, JsonValue],
    payload: Mapping[str, JsonValue],
    envelope: Mapping[str, JsonValue],
    payload_sha256: str,
    case_id: str,
) -> str:
    catalog = surface.catalog
    skip = surface.message("page.skip_to_content")
    heading = surface.message("page.heading")
    subheading = surface.message("page.subheading", case_id=case_id)
    rows = _rows(surface, _sequence(payload.get("results"), "$.payload.results"))
    sections = "".join(
        (
            _section(
                surface,
                "section.scope.heading",
                "scope",
                "<dl>"
                + _scope(surface, _mapping(payload.get("scope"), "$.payload.scope"))
                + "</dl>",
            ),
            _section(
                surface,
                "section.limitations.heading",
                "limitations",
                _paragraph(surface.message("limitations.intro"))
                + "<ol>"
                + _limitations(
                    surface,
                    _sequence(payload.get("limitations"), "$.payload.limitations"),
                )
                + "</ol>",
            ),
            _section(
                surface,
                "section.summary.heading",
                "summary",
                _legend(surface)
                + _summary_table(
                    surface, _mapping(payload.get("summary"), "$.payload.summary")
                ),
            ),
            _section(
                surface,
                "section.results.heading",
                "results",
                _results_table(surface, rows),
            ),
            _section(
                surface,
                "section.hashes.heading",
                "hashes",
                "<dl>"
                + _hashes(
                    surface,
                    _mapping(payload.get("hashes"), "$.payload.hashes"),
                    payload_sha256,
                )
                + "</dl>",
            ),
            _section(
                surface,
                "section.envelope.heading",
                "envelope",
                _safety_text(surface, "envelope.explainer")
                + "<dl>"
                + _envelope(surface, envelope)
                + "</dl>",
            ),
        )
    )
    return (
        f"<body {_attr('data-cs-page', PAGE_KIND)} "
        f"{_attr('data-cs-locale', catalog.locale)} "
        f"{_attr('data-cs-translation-review', catalog.review.status)}>\n"
        f'<a class="skip-link" href="#receipt" {_marked(skip)}>{escape(skip.text)}</a>\n'
        f"<header><h1 {_marked(heading)}>{escape(heading.text)}</h1>"
        f'<p class="subheading" {_marked(subheading)}>{escape(subheading.text)}</p>'
        "</header>\n"
        f"{_notice(surface)}\n"
        f'<main id="receipt" {_attr("data-cs-payload-sha256", payload_sha256)} '
        f"{_attr('data-cs-case-id', case_id)}>\n{sections}\n</main>\n"
        f"{_footer(surface, document, payload)}\n"
        "</body>"
    )


def _legend(surface: Surface) -> str:
    heading = surface.message("status.legend.heading")
    return f"<h3 {_marked(heading)}>{escape(heading.text)}</h3>" + _paragraph(
        surface.message("status.legend.body")
    )


def _footer(
    surface: Surface,
    document: Mapping[str, JsonValue],
    payload: Mapping[str, JsonValue],
) -> str:
    runner = surface.message(
        "footer.runner",
        version=_text(payload.get("runner_version"), "$.payload.runner_version"),
    )
    schema = surface.message(
        "footer.schema",
        schema_version=_text(document.get("schema_version"), "$.schema_version"),
    )
    locale_note = surface.message("footer.locale", locale=surface.catalog.locale)
    return (
        "<footer>"
        + _paragraph(runner)
        + _paragraph(schema)
        + _paragraph(locale_note)
        + _paragraph(surface.message("footer.determinism"))
        + "</footer>"
    )


def catalog_for(locale: str) -> Catalog:
    """Return the catalog a caller would render ``locale`` with."""

    return load_catalog(locale)
