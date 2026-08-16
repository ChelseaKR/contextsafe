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

from contextsafe.canonical import canonical_json
from contextsafe.errors import ContextSafeError
from contextsafe.i18n import (
    PSEUDO_LOCALE,
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
    """A gate that reports success having examined nothing is worthless."""

    findings = gate.run_gate(())
    assert [finding.rule for finding in findings] == ["no-catalogs"]


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
