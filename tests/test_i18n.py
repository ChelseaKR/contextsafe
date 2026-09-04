"""The localization gates, and the negative controls that prove they bite.

The rule this file exists to enforce is narrow and non-negotiable: a machine
translation must never render as though a person checked it. Every assertion
below either pins that rule or pins a gate that would catch it being broken,
and each gate has a case where it fails — a gate nobody has watched fail is a
gate nobody should trust.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from contextsafe.canonical import canonical_json
from contextsafe.errors import ContextSafeError
from contextsafe.i18n import (
    PSEUDO_ACCENTABLE,
    PSEUDO_LOCALE,
    PSEUDO_MINIMUM_EXPANSION,
    SOURCE_LOCALE,
    Catalog,
    Message,
    ReviewClaim,
    ReviewStatus,
    Surface,
    TranslationReview,
    available_locales,
    load_catalog,
    pseudolocalize,
    source_catalog,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
GATE_PATH = REPO_ROOT / "tools" / "i18n_gate.py"


def _load_gate() -> ModuleType:
    spec = importlib.util.spec_from_file_location("i18n_gate", GATE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


gate = _load_gate()


def _reviewed_catalog() -> Catalog:
    """A catalog identical to the source one but marked human-reviewed."""

    source = source_catalog()
    return Catalog(
        locale="xx-XX",
        source_locale=SOURCE_LOCALE,
        review=TranslationReview(
            status=ReviewStatus.HUMAN,
            reviewed_by="A named reviewer",
            reviewed_at="2026-01-01",
            note="Fixture catalog used only by tests.",
        ),
        messages={
            key: Message(
                key=key,
                text=message.text,
                review=ReviewStatus.HUMAN,
                locale="xx-XX",
            )
            for key, message in source.messages.items()
        },
    )


def test_the_source_locale_contains_no_translation() -> None:
    """en-US is authored, so nothing in it may claim to be translated."""

    catalog = source_catalog()
    assert catalog.messages
    assert all(
        message.review is ReviewStatus.SOURCE for message in catalog.messages.values()
    )
    assert not catalog.is_machine_translated


def test_the_only_shipped_translation_is_unreviewed_today() -> None:
    """B-042 has not happened, and the catalog must not pretend otherwise."""

    catalog = load_catalog("es-US")
    assert catalog.is_machine_translated
    assert catalog.review.status is ReviewStatus.MACHINE
    assert catalog.review.reviewed_by is None
    assert catalog.review.reviewed_at is None
    assert not catalog.review.human_reviewed


def test_a_surface_claiming_review_refuses_an_unreviewed_string() -> None:
    """The gate, at its smallest: the claim and the string must agree."""

    surface = Surface(
        name="test", catalog=load_catalog("es-US"), claim=ReviewClaim.HUMAN_REVIEWED
    )
    with pytest.raises(ContextSafeError) as excinfo:
        surface.message("page.heading")
    assert excinfo.value.code == "unreviewed_string_on_reviewed_surface"


def test_a_surface_claiming_review_accepts_a_reviewed_string() -> None:
    """The other half: a real review record must not be refused."""

    surface = Surface(
        name="test", catalog=_reviewed_catalog(), claim=ReviewClaim.HUMAN_REVIEWED
    )
    assert surface.text("page.heading")


def test_a_surface_claiming_nothing_still_has_to_disclose() -> None:
    """Not claiming review is not the same as being allowed to stay quiet."""

    surface = Surface(name="test", catalog=load_catalog("es-US"))
    assert surface.must_disclose_machine_translation
    target, original = surface.disclosure()
    assert target.locale == "es-US"
    assert target.review is ReviewStatus.MACHINE
    assert original.locale == SOURCE_LOCALE
    assert original.review is ReviewStatus.SOURCE
    assert target.text != original.text


def test_disclosure_is_refused_when_there_is_nothing_to_disclose() -> None:
    """A notice on a reviewed page is noise that teaches readers to skip it."""

    surface = Surface(name="test", catalog=source_catalog())
    assert not surface.must_disclose_machine_translation
    with pytest.raises(ContextSafeError) as excinfo:
        surface.disclosure()
    assert excinfo.value.code == "disclosure_not_applicable"


def test_an_unknown_key_fails_closed_instead_of_falling_back() -> None:
    """Silent source-locale fallback is how a half-translated page ships."""

    with pytest.raises(ContextSafeError) as excinfo:
        load_catalog("es-US").message("no.such.key")
    assert excinfo.value.code == "unknown_message_key"


def test_an_unknown_locale_fails_closed() -> None:
    """A locale with no catalog is an error, not an empty page."""

    with pytest.raises(ContextSafeError) as excinfo:
        load_catalog("zz-ZZ")
    assert excinfo.value.code == "unknown_locale"


def test_placeholder_mismatch_fails_closed_in_both_directions() -> None:
    """Supplying the wrong values must not silently drop or invent one."""

    message = source_catalog().message("footer.locale")
    with pytest.raises(ContextSafeError) as missing:
        message.format()
    assert missing.value.code == "message_placeholder_mismatch"
    with pytest.raises(ContextSafeError) as extra:
        message.format(locale="en-US", surplus="x")
    assert extra.value.code == "message_placeholder_mismatch"
    assert message.format(locale="en-US").text.endswith("en-US")


def test_formatting_preserves_review_status() -> None:
    """Substituting a value must not launder an unreviewed string."""

    message = load_catalog("es-US").message("footer.locale").format(locale="es-US")
    assert message.review is ReviewStatus.MACHINE
    assert not message.reviewed


def test_pseudolocale_transforms_text_and_preserves_placeholders() -> None:
    """The pseudolocale has to stay substitutable, or it tests only itself."""

    rendered = pseudolocalize("Interface locale: {locale}")
    assert "{locale}" in rendered
    assert "Interface locale" not in rendered
    assert rendered.startswith("⟦") and rendered.endswith("⟧")
    assert len(rendered) > len("Interface locale: {locale}")
    catalog = load_catalog(PSEUDO_LOCALE)
    assert catalog.keys() == source_catalog().keys()
    assert catalog.is_machine_translated


_PSEUDO_SOURCE_TEXT = st.text(
    alphabet=st.characters(
        codec="ascii", categories=("L", "N", "P", "Zs"), exclude_characters="{}"
    ),
    min_size=1,
    max_size=200,
).filter(str.strip)


_ACCENTED = {char: pseudolocalize(char)[1] for char in PSEUDO_ACCENTABLE}
"""Each accentable letter and the form the transform gives it."""


def _one_diacritic_per_message(text: str) -> str:
    """Pseudolocalize, then put back every accented letter after the first.

    The transform the earlier "some diacritic somewhere" rule could not tell
    from a real one: it expands, keeps placeholders, and leaves the sentence
    legible English from the second letter on.
    """

    plain = {accented: char for char, accented in _ACCENTED.items()}
    kept = False
    out: list[str] = []
    for char in pseudolocalize(text):
        if char in plain and kept:
            out.append(plain[char])
        else:
            kept = kept or char in plain
            out.append(char)
    return "".join(out)


@given(text=_PSEUDO_SOURCE_TEXT, placeholder=st.sampled_from(["", " {count}"]))
@settings(max_examples=200)
def test_pseudolocalization_expands_accents_and_keeps_placeholders(
    text: str, placeholder: str
) -> None:
    """B-041, as a property: the floor holds for any source string.

    At least ``PSEUDO_MINIMUM_EXPANSION`` growth measured on the body alone,
    without the two brackets the gate does count, so this is the stricter of
    the two measures; every accentable letter outside the placeholder
    accented, not merely some diacritic somewhere; and the placeholder set
    unchanged.
    """

    source = text + placeholder
    rendered = pseudolocalize(source)
    assert rendered.startswith("⟦") and rendered.endswith("⟧")
    body = rendered[1:-1]
    assert len(body) - len(source) >= PSEUDO_MINIMUM_EXPANSION * len(source)
    literals = body.replace("{count}", "")
    assert not PSEUDO_ACCENTABLE & set(literals)
    for char in PSEUDO_ACCENTABLE & set(text):
        assert literals.count(_ACCENTED[char]) >= text.count(char)
    assert ("{count}" in rendered) == bool(placeholder)
    assert rendered.count("{") == source.count("{")


def test_the_shipped_pseudolocale_holds_its_floor() -> None:
    """Every generated message, measured, not just one example."""

    assert PSEUDO_MINIMUM_EXPANSION >= 0.35
    assert list(gate.check_pseudolocale(load_catalog(PSEUDO_LOCALE))) == []


def _weakened_pseudolocale(transform: Any) -> Catalog:
    """A pseudolocale built with a transform that has lost a property."""

    source = source_catalog()
    return Catalog(
        locale=PSEUDO_LOCALE,
        source_locale=SOURCE_LOCALE,
        review=load_catalog(PSEUDO_LOCALE).review,
        messages={
            key: Message(
                key=key,
                text=transform(message.text),
                review=ReviewStatus.MACHINE,
                locale=PSEUDO_LOCALE,
            )
            for key, message in source.messages.items()
        },
    )


@pytest.mark.parametrize(
    ("transform", "needle"),
    [
        (
            lambda text: "⟦" + text.translate(str.maketrans("aeiou", "áéíóú")) + "⟧",
            "below",
        ),
        (lambda text: "⟦" + text + "‧" * len(text) + "⟧", "accentable letter"),
        (_one_diacritic_per_message, "accentable letter"),
        (
            lambda text: (
                "⟦"
                + text.translate({ord(c): None for c in PSEUDO_ACCENTABLE})
                + "‧" * (2 * len(text))
                + "⟧"
            ),
            "no diacritic",
        ),
        (lambda text: pseudolocalize(text).replace("{", "{x_"), "placeholders"),
    ],
    ids=["expansion", "diacritics", "partial-diacritics", "no-letters", "placeholders"],
)
def test_the_gate_catches_a_pseudolocale_that_lost_a_property(
    transform: Any, needle: str
) -> None:
    """Negative controls for ``pseudolocale-fidelity``, at least one per property.

    ``partial-diacritics`` is the one the first form of the rule missed: a
    transform that accents one letter per message and leaves the rest plain
    satisfied "some diacritic somewhere" with zero findings.
    """

    findings = list(gate.check_pseudolocale(_weakened_pseudolocale(transform)))
    assert findings
    assert {finding.rule for finding in findings} == {"pseudolocale-fidelity"}
    assert any(needle in finding.detail for finding in findings)


def test_the_gate_catches_a_pseudolocale_missing_a_key() -> None:
    """A key the pseudolocale lacks is a string the hardcoded check cannot see."""

    catalog = _weakened_pseudolocale(pseudolocalize)
    thinned = Catalog(
        locale=catalog.locale,
        source_locale=catalog.source_locale,
        review=catalog.review,
        messages={k: v for k, v in catalog.messages.items() if k != "page.title"},
    )
    findings = list(gate.check_pseudolocale(thinned))
    assert [finding.detail for finding in findings] == ["missing key page.title"]


def test_available_locales_lists_what_can_be_rendered() -> None:
    """``--lang`` offers exactly the locales that exist."""

    locales = available_locales()
    assert SOURCE_LOCALE in locales
    assert "es-US" in locales
    assert PSEUDO_LOCALE in locales


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        ([], "invalid_catalog"),
        ({"locale": "other"}, "catalog_locale_mismatch"),
        ({"locale": "en-US"}, "invalid_catalog"),
        (
            {
                "locale": "en-US",
                "source_locale": "en-US",
                "translation_review": {"status": "nope", "note": "n"},
                "messages": {},
            },
            "invalid_catalog",
        ),
        (
            {
                "locale": "en-US",
                "source_locale": "en-US",
                "translation_review": {"status": "source", "note": ""},
                "messages": {},
            },
            "invalid_catalog",
        ),
        (
            {
                "locale": "en-US",
                "source_locale": "en-US",
                "translation_review": {"status": "source", "note": "n"},
                "messages": {"a": {"review": "source"}},
            },
            "invalid_catalog",
        ),
    ],
)
def test_a_malformed_catalog_is_rejected(payload: Any, code: str) -> None:
    """Catalogs are contracts; a broken one is a rejection, not a guess."""

    from contextsafe import i18n

    with pytest.raises(ContextSafeError) as excinfo:
        i18n._parse_catalog(payload, locale="en-US")
    assert excinfo.value.code == code


def test_the_machine_artifact_never_varies_by_locale() -> None:
    """Hash-covered output stays in one language, whatever the interface does.

    Localizing a receipt payload would change its bytes and therefore its
    hash, so the split is structural rather than a convention: catalogs reach
    the rendered page and nothing else.
    """

    document = gate.reference_document()
    serialized = canonical_json(document)
    spanish = load_catalog("es-US")
    for message in spanish.messages.values():
        assert message.text not in serialized
    for limitation in document["payload"]["limitations"]:  # type: ignore[index]
        assert source_catalog().message
        assert isinstance(limitation, str)
        assert limitation.isascii()


def test_every_mandated_limitation_has_a_catalog_entry() -> None:
    """A limitation with no entry renders untranslated, so pin the coverage."""

    document = gate.reference_document()
    limitations = document["payload"]["limitations"]  # type: ignore[index]
    source = source_catalog()
    keyed = {
        message.text
        for key, message in source.messages.items()
        if key.startswith("limitation.")
    }
    assert set(limitations) <= keyed


def test_the_gate_is_clean_on_the_shipped_catalogs() -> None:
    """The repository has to pass its own gate."""

    assert gate.run_gate(gate.shipped_catalogs()) == []


def test_the_gate_refuses_to_pass_on_nothing() -> None:
    """A gate that reports success having examined nothing is worthless.

    This was a ``no-catalogs`` finding, which put "nothing was examined" at the
    same exit code as a real parity failure. It is a refusal now: exit 2, the
    contract every other gate here keeps. See ADR 0008.
    """

    with pytest.raises(gate.GateUnavailable):
        gate.run_gate(())


def test_examining_nothing_is_exit_two_and_says_so(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert gate.main(["--locale", "xx-YY"]) == 2
    assert "not a clean result" in capsys.readouterr().err


def test_the_gate_catches_a_missing_key(tmp_path: Path) -> None:
    """Negative control for ``catalog-parity``."""

    catalog = _mutated_catalog(tmp_path, drop="column.rule")
    rules = {finding.rule for finding in gate.check_parity(catalog)}
    assert "catalog-parity" in rules


def test_the_gate_catches_a_changed_placeholder(tmp_path: Path) -> None:
    """Negative control for ``placeholder-parity``."""

    catalog = _mutated_catalog(tmp_path, retext=("footer.locale", "Idioma: {idioma}"))
    rules = {finding.rule for finding in gate.check_parity(catalog)}
    assert "placeholder-parity" in rules


def test_the_gate_catches_an_empty_message(tmp_path: Path) -> None:
    """Negative control for ``message-quality`` at the parse boundary."""

    with pytest.raises(ContextSafeError) as excinfo:
        _mutated_catalog(tmp_path, retext=("footer.locale", "   "))
    assert excinfo.value.code == "invalid_catalog"


def test_the_gate_catches_a_source_entry_claiming_translation() -> None:
    """Negative control for ``message-quality`` in the source locale."""

    source = source_catalog()
    tainted = Catalog(
        locale=SOURCE_LOCALE,
        source_locale=SOURCE_LOCALE,
        review=source.review,
        messages={
            **source.messages,
            "page.title": Message(
                key="page.title",
                text="ContextSafe evaluation receipt",
                review=ReviewStatus.MACHINE,
                locale=SOURCE_LOCALE,
            ),
        },
    )
    rules = {finding.rule for finding in gate.check_message_quality(tainted)}
    assert "message-quality" in rules


def test_the_gate_catches_a_review_record_nobody_signed(tmp_path: Path) -> None:
    """Negative control for ``review-consistency``."""

    catalog = _mutated_catalog(tmp_path, review_status="human")
    findings = list(gate.check_review_consistency(catalog))
    details = " ".join(finding.detail for finding in findings)
    assert findings
    assert "have not been reviewed" in details
    assert "without naming a reviewer" in details


def test_the_gate_catches_a_reviewed_catalog_being_refused() -> None:
    """Negative control for the accepting half of the claiming-surface rule."""

    catalog = Catalog(
        locale="xx-XX",
        source_locale=SOURCE_LOCALE,
        review=TranslationReview(
            status=ReviewStatus.HUMAN,
            reviewed_by="A named reviewer",
            reviewed_at="2026-01-01",
            note="Fixture.",
        ),
        messages={
            key: Message(
                key=key,
                text=message.text,
                review=(
                    ReviewStatus.MACHINE if key == "page.title" else ReviewStatus.HUMAN
                ),
                locale="xx-XX",
            )
            for key, message in source_catalog().messages.items()
        },
    )
    rules = {finding.rule for finding in gate.check_claiming_surface(catalog)}
    assert rules == set()
    findings = list(gate.check_review_consistency(catalog))
    assert findings


def test_the_gate_catches_a_surface_that_stopped_refusing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Negative control for ``unreviewed-on-reviewed-surface``.

    If :class:`Surface` ever stopped enforcing its claim, every other check
    here would still pass, so the gate is pointed at that regression directly.
    """

    monkeypatch.setattr(
        gate.Surface, "message", lambda self, key, **values: self.catalog.message(key)
    )
    findings = list(gate.check_claiming_surface(load_catalog("es-US")))
    assert [finding.rule for finding in findings] == ["unreviewed-on-reviewed-surface"]


def test_the_gate_reports_a_locale_that_cannot_render(tmp_path: Path) -> None:
    """A locale that fails to render is a finding, not a traceback."""

    catalog = _mutated_catalog(tmp_path, drop="column.rule")
    findings = list(gate.check_disclosure(catalog, gate.reference_document()))
    assert [finding.rule for finding in findings] == ["render-failed"]


def _mutated_catalog(
    tmp_path: Path,
    *,
    drop: str | None = None,
    retext: tuple[str, str] | None = None,
    review_status: str | None = None,
) -> Catalog:
    """Write a mutated copy of the Spanish catalog and load it."""

    from contextsafe import i18n

    raw = json.loads((i18n.LOCALES_ROOT / "es-US.json").read_text(encoding="utf-8"))
    if drop is not None:
        del raw["messages"][drop]
    if retext is not None:
        raw["messages"][retext[0]]["text"] = retext[1]
    if review_status is not None:
        raw["translation_review"]["status"] = review_status
    return i18n._parse_catalog(raw, locale="es-US")


def test_the_gate_cli_reports_clean_and_dirty(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The command-line entry point has to agree with the library."""

    assert gate.main([]) == 0
    assert "clean over 2 catalog(s)" in capsys.readouterr().out
    monkeypatch.setattr(
        gate, "run_gate", lambda catalogs: [gate.Finding("r", "l", "d")]
    )
    assert gate.main(["--locale", "es-US"]) == 1
    assert "1 finding(s)" in capsys.readouterr().out


def _rendering(monkeypatch: pytest.MonkeyPatch, edit: Any) -> None:
    """Point the gate at a renderer whose output ``edit`` has changed."""

    real = gate.render_receipt_page
    monkeypatch.setattr(
        gate, "render_receipt_page", lambda *a, **k: edit(real(*a, **k))
    )


@pytest.mark.parametrize(
    "injected",
    [
        "<p>Rendered by hand</p>",
        "<p>Skip to the receipt</p>",
        '<p lang="es-US">Skip to the receipt</p>',
    ],
    ids=["free-text", "unmarked-catalog-copy", "wrongly-marked-catalog-copy"],
)
def test_the_gate_catches_a_hardcoded_string(
    monkeypatch: pytest.MonkeyPatch, injected: str
) -> None:
    """Negative control for ``hardcoded-string``.

    A literal nobody externalized, and a literal copy of a catalog sentence
    that is not marked as a source-locale original: the second is the one
    a pattern-only check would have waved through.
    """

    _rendering(monkeypatch, lambda page: page.replace("</main>", injected + "</main>"))
    findings = list(gate.check_hardcoded_strings(gate.reference_document()))
    assert [finding.rule for finding in findings] == ["hardcoded-string"]


def test_a_marked_source_original_is_not_a_hardcoded_string(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The accepting half: an original marked as such is how the page works."""

    _rendering(
        monkeypatch,
        lambda page: page.replace(
            "</main>", '<p lang="en-US">Skip to the receipt</p></main>'
        ),
    )
    assert list(gate.check_hardcoded_strings(gate.reference_document())) == []


def test_the_gate_catches_an_undisclosed_machine_translation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Negative control for ``undisclosed-machine-translation``, both ways."""

    document = gate.reference_document()
    _rendering(
        monkeypatch,
        lambda page: page.replace('data-cs-notice="machine-translation"', ""),
    )
    findings = list(gate.check_disclosure(load_catalog("es-US"), document))
    assert [finding.rule for finding in findings] == ["undisclosed-machine-translation"]
    assert "without the notice" in findings[0].detail

    monkeypatch.undo()
    _rendering(
        monkeypatch,
        lambda page: page.replace(
            "<main", '<aside data-cs-notice="machine-translation"></aside><main'
        ),
    )
    findings = list(gate.check_disclosure(_reviewed_catalog(), document))
    assert [finding.rule for finding in findings] == ["undisclosed-machine-translation"]
    assert "reviewed catalog" in findings[0].detail


def test_visible_text_carries_the_language_in_force() -> None:
    """The lang a run is judged under is inherited, the way a browser does it."""

    runs = gate.visible_text(
        '</stray><html lang="qps-ploc"><head><title>t</title><style>x</style>'
        '</head><body><p>a<span lang="en-US">b<br></br>c</span></span>d</p>'
        '<p lang="es-US">e</p></body></html>'
    )
    assert [(run.text, run.lang) for run in runs] == [
        ("a", "qps-ploc"),
        ("b", "en-US"),
        ("c", "en-US"),
        ("d", "qps-ploc"),
        ("e", "es-US"),
    ]


def test_a_stray_end_tag_moves_no_language() -> None:
    """An end tag that closes nothing must not shift what follows into en-US.

    The first form popped whatever was on top of the stack on any end tag,
    so ``</stray>`` inside an ``en-US`` span put the rest of the span under
    the page language, and an end tag that closed the page's ``<p>`` early
    put the rest of the page under the accepting source-locale bucket. Pop by
    name: a stray tag closes nothing, and an end tag closes what it names
    along with anything left open inside it.
    """

    runs = gate.visible_text(
        '<html lang="qps-ploc"><body><p><span lang="en-US">b</stray>c</span>d</p>'
        '<p lang="es-US"><span lang="en-US">e</p>f'
        "<style>g</stray>h</style>i</body></html>"
    )
    assert [(run.text, run.lang) for run in runs] == [
        ("b", "en-US"),
        ("c", "en-US"),
        ("d", "qps-ploc"),
        ("e", "en-US"),
        ("f", "qps-ploc"),
        ("i", "qps-ploc"),
    ]
    parser = gate._VisibleText()
    parser.feed("<p>a</b>b</p></p>")
    assert parser.stray == ["b", "p"]
    assert [run.text for run in parser.runs] == ["a", "b"]


def test_the_expansion_floor_is_measured_without_the_brackets() -> None:
    """A transform that only brackets a label is short of the floor on it.

    Counted, the two brackets were a 50 percent expansion of ``Pass`` and a
    100 percent expansion of ``No``, so a pseudolocale that stopped padding
    passed the gate on exactly the short column headers and status words
    where expansion matters; the property test measured the body and the
    gate did not. Every message of five characters or fewer must now be
    named by the gate under that transform.
    """

    accented = str.maketrans("aeiou", "áéíóú")
    findings = list(
        gate.check_pseudolocale(
            _weakened_pseudolocale(lambda text: "⟦" + text.translate(accented) + "⟧")
        )
    )
    named = {
        finding.detail.partition(":")[0]
        for finding in findings
        if "below" in finding.detail
    }
    short = {
        key
        for key, message in source_catalog().messages.items()
        if len(message.text) <= 5
    }
    assert short, "the source catalog has no short label to measure"
    assert short <= named, sorted(short - named)


def test_a_placeholder_permitted_no_value_matches_nothing() -> None:
    """The empty allowlist is a placeholder no run may have filled."""

    from contextsafe import i18n

    catalog = source_catalog()
    key, message = next(
        (key, message)
        for key, message in sorted(catalog.messages.items())
        if "{" in message.text
    )
    filled = message.text.format_map(_AnyValue())
    assert catalog.accounts_for(filled)
    assert catalog.accounts_for(filled, {"CSYN-FIXTURE-VALUE"})
    assert not catalog.accounts_for(filled, set())
    assert not catalog.accounts_for(filled, {"CSYN-OTHER"})
    assert i18n._message_pattern(message.text, ()).fullmatch(filled) is None, key


class _AnyValue(dict[str, str]):
    """Format map that fills every placeholder with one synthetic token."""

    def __missing__(self, key: str) -> str:
        return "CSYN-FIXTURE-VALUE"


def test_pseudolocalization_keeps_a_conversion_and_a_format_spec() -> None:
    """``{count!r:>4}`` survives the transform with both halves intact."""

    rendered = pseudolocalize("n {count!r:>4} m")
    assert "{count!r:>4}" in rendered
    assert rendered.count("{") == 1


def test_a_review_status_that_is_not_text_is_rejected() -> None:
    """A review status is a closed enum member, never a number or a flag."""

    from contextsafe import i18n

    payload = json.loads(
        (REPO_ROOT / "src" / "contextsafe" / "locales" / "en-US.json").read_text(
            encoding="utf-8"
        )
    )
    key = sorted(payload["messages"])[0]
    payload["messages"][key]["review"] = True
    with pytest.raises(ContextSafeError) as excinfo:
        i18n._parse_catalog(payload, locale="en-US")
    assert excinfo.value.code == "invalid_catalog"
    assert excinfo.value.path == f"$.messages.{key}.review"


def test_shipped_catalogs_iterate_source_locale_first() -> None:
    """The source catalog leads, so parity has something to compare against."""

    from contextsafe import i18n

    locales = [catalog.locale for catalog in i18n.iter_shipped_catalogs()]
    assert locales[0] == SOURCE_LOCALE
    assert PSEUDO_LOCALE not in locales
    assert set(locales) == set(available_locales()) - {PSEUDO_LOCALE}
