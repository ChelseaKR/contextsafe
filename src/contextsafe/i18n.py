"""Message catalogs, and the rule that an unreviewed translation says so.

Three ideas hold this module together.

**A message is not a string.** :func:`Catalog.message` returns a
:class:`Message` carrying the text *and* the review status of that text.
Nothing in this package can obtain display text without also obtaining the
provenance of that text, so "we forgot to check whether this was reviewed" is
not a reachable state.

**A surface declares what it claims.** A :class:`Surface` is a place text is
shown, and it carries a :class:`ReviewClaim`. Rendering an unreviewed message
through a surface that claims human review raises
``unreviewed_string_on_reviewed_surface``. B-042 — professional translation and
independent community review — has not happened, so today every non-source
locale is :attr:`ReviewStatus.MACHINE` and no surface may claim review.

**Machine translation is disclosed, not implied.** For a product whose users
are people for whom a mistranslation is a safety problem, an unreviewed
translation that renders like a reviewed one is a defect, not a placeholder.
:meth:`Surface.disclosure` gives a surface the disclosure it must show, and
:meth:`Catalog.is_machine_translated` is what a caller checks to know it must
show it. Mandated safety disclosures additionally render alongside their
source-locale original — see ``html_receipt`` — because a machine translation
of "not an approved clinical oracle" is exactly the sentence a reader must not
have to trust an unreviewed rendering of.

Nothing here touches the deterministic artifacts. Receipt payloads, ``--output``
files, and the stderr error object are hash-covered machine contracts in one
fixed language; ``test_i18n.py`` pins that they do not vary by locale.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from string import Formatter

from contextsafe.errors import ContextSafeError

LOCALES_ROOT = Path(__file__).parent / "locales"

SOURCE_LOCALE = "en-US"
"""The locale the product is authored in. Nothing here is a translation."""

PSEUDO_LOCALE = "qps-ploc"
"""A generated locale used only by gates, never shipped to a reader.

Every source message is accented, bracketed, and padded. Any run of visible
text in a pseudolocalized render that is still readable English is a string
somebody hardcoded instead of externalizing, which is the whole point.
"""

_PSEUDO_PREFIX = "⟦"
_PSEUDO_SUFFIX = "⟧"
_PSEUDO_PAD = "‧"
_PSEUDO_EXPANSION = 0.3

_PSEUDO_MAP = str.maketrans(
    "aeiounpcsyAEIOUNPCSY",
    "áéíóúñþçšýÁÉÍÓÚÑÞÇŠÝ",
)


class ReviewStatus(StrEnum):
    """Where a particular string's wording came from."""

    SOURCE = "source"
    """Authored in the source locale. No translation step happened."""

    MACHINE = "machine"
    """Machine translated. No qualified human has reviewed this wording."""

    HUMAN = "human"
    """Reviewed by a qualified human translator and community reviewer."""


class ReviewClaim(StrEnum):
    """What a surface asserts about the text it displays."""

    NONE = "none"
    """Claims nothing. Must disclose when what it shows is unreviewed."""

    HUMAN_REVIEWED = "human_reviewed"
    """Asserts every string shown has passed human translation review."""


@dataclass(frozen=True, slots=True)
class Message:
    """Display text bound to the provenance of its wording."""

    key: str
    text: str
    review: ReviewStatus
    locale: str

    @property
    def reviewed(self) -> bool:
        """Whether this wording may be presented as human-checked."""

        return self.review in (ReviewStatus.SOURCE, ReviewStatus.HUMAN)

    def format(self, **values: object) -> Message:
        """Substitute placeholders, keeping key, review status, and locale."""

        expected = _placeholders(self.text)
        supplied = frozenset(values)
        if expected != supplied:
            raise ContextSafeError(
                "message_placeholder_mismatch",
                f"$.messages.{self.key}",
                "message placeholders do not match the values supplied",
            )
        return Message(
            key=self.key,
            text=self.text.format(**values),
            review=self.review,
            locale=self.locale,
        )


def _placeholders(text: str) -> frozenset[str]:
    """Return the named ``{placeholder}`` fields in ``text``."""

    return frozenset(
        name for _, name, _, _ in Formatter().parse(text) if name is not None
    )


@dataclass(frozen=True, slots=True)
class TranslationReview:
    """The catalog-level record of who checked this locale, and when."""

    status: ReviewStatus
    reviewed_by: str | None
    reviewed_at: str | None
    note: str

    @property
    def human_reviewed(self) -> bool:
        """Whether a qualified human signed off on this whole catalog."""

        return self.status is ReviewStatus.HUMAN


@dataclass(frozen=True, slots=True)
class Catalog:
    """One locale's messages plus the review record for that locale."""

    locale: str
    source_locale: str
    review: TranslationReview
    messages: Mapping[str, Message]

    def message(self, key: str) -> Message:
        """Return the message for ``key``, failing closed if it is absent.

        A missing key is a defect, not something to paper over with the key
        name or with source-locale fallback: silent fallback is how a half
        translated interface ships looking finished.
        """

        found = self.messages.get(key)
        if found is None:
            raise ContextSafeError(
                "unknown_message_key",
                f"$.messages.{key}",
                "message key is not present in the catalog",
            )
        return found

    @property
    def is_machine_translated(self) -> bool:
        """Whether any string in this catalog is an unreviewed translation."""

        return any(
            message.review is ReviewStatus.MACHINE for message in self.messages.values()
        )

    def keys(self) -> frozenset[str]:
        """Return every message key in this catalog."""

        return frozenset(self.messages)


@dataclass(frozen=True, slots=True)
class Surface:
    """A place text is shown, and what that place claims about the text."""

    name: str
    catalog: Catalog
    claim: ReviewClaim = ReviewClaim.NONE

    def message(self, key: str, **values: object) -> Message:
        """Return the message for ``key``, enforcing this surface's claim."""

        message = self.catalog.message(key)
        if values:
            message = message.format(**values)
        if self.claim is ReviewClaim.HUMAN_REVIEWED and not message.reviewed:
            raise ContextSafeError(
                "unreviewed_string_on_reviewed_surface",
                f"$.surfaces.{self.name}.{key}",
                (
                    "surface claims human-reviewed translation but the string "
                    "has not been reviewed"
                ),
            )
        return message

    def text(self, key: str, **values: object) -> str:
        """Return display text for ``key`` after the claim check passes."""

        return self.message(key, **values).text

    @property
    def must_disclose_machine_translation(self) -> bool:
        """Whether this surface has to tell the reader the text is unreviewed."""

        return self.catalog.is_machine_translated

    def disclosure(self) -> tuple[Message, Message]:
        """Return the unreviewed-translation notice, in target and source text.

        Two messages, deliberately. A reader who cannot rely on the target
        wording is exactly the reader the notice is for, so the notice is also
        given in the source locale.
        """

        if not self.must_disclose_machine_translation:
            raise ContextSafeError(
                "disclosure_not_applicable",
                f"$.surfaces.{self.name}",
                "catalog carries no machine-translated string to disclose",
            )
        return (
            self.catalog.message("translation.unreviewed.body"),
            source_catalog().message("translation.unreviewed.body"),
        )


def _parse_catalog(raw: object, *, locale: str) -> Catalog:
    """Build a :class:`Catalog` from parsed catalog JSON, failing closed."""

    if not isinstance(raw, dict):
        raise ContextSafeError("invalid_catalog", "$", "catalog must be a JSON object")
    declared = raw.get("locale")
    if declared != locale:
        raise ContextSafeError(
            "catalog_locale_mismatch",
            "$.locale",
            "catalog locale does not match the file it was loaded from",
        )
    review_raw = raw.get("translation_review")
    messages_raw = raw.get("messages")
    if not isinstance(review_raw, dict) or not isinstance(messages_raw, dict):
        raise ContextSafeError(
            "invalid_catalog",
            "$",
            "catalog needs a translation_review object and a messages object",
        )
    review = TranslationReview(
        status=_review_status(review_raw.get("status"), "$.translation_review.status"),
        reviewed_by=_optional_text(review_raw.get("reviewed_by")),
        reviewed_at=_optional_text(review_raw.get("reviewed_at")),
        note=_required_text(review_raw.get("note"), "$.translation_review.note"),
    )
    messages = {
        key: Message(
            key=key,
            text=_required_text(
                entry.get("text") if isinstance(entry, dict) else None,
                f"$.messages.{key}.text",
            ),
            review=_review_status(
                entry.get("review") if isinstance(entry, dict) else None,
                f"$.messages.{key}.review",
            ),
            locale=locale,
        )
        for key, entry in sorted(messages_raw.items())
    }
    source_locale = _required_text(raw.get("source_locale"), "$.source_locale")
    return Catalog(
        locale=locale,
        source_locale=source_locale,
        review=review,
        messages=messages,
    )


def _review_status(value: object, pointer: str) -> ReviewStatus:
    if not isinstance(value, str):
        raise ContextSafeError("invalid_catalog", pointer, "review status must be text")
    try:
        return ReviewStatus(value)
    except ValueError as exc:
        raise ContextSafeError(
            "invalid_catalog", pointer, "review status is not a published value"
        ) from exc


def _required_text(value: object, pointer: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContextSafeError(
            "invalid_catalog", pointer, "value must be non-empty text"
        )
    return value


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _read_catalog(locale: str) -> Catalog:
    path = LOCALES_ROOT / f"{locale}.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ContextSafeError(
            "unknown_locale",
            "$.locale",
            "no message catalog is published for this locale",
        ) from exc
    return _parse_catalog(raw, locale=locale)


def available_locales() -> tuple[str, ...]:
    """Return every shipped locale, plus the generated pseudolocale."""

    shipped = sorted(path.stem for path in LOCALES_ROOT.glob("*.json"))
    return (*shipped, PSEUDO_LOCALE)


def source_catalog() -> Catalog:
    """Return the source-locale catalog."""

    return load_catalog(SOURCE_LOCALE)


def pseudolocalize(text: str) -> str:
    """Return an accented, bracketed, padded form of ``text``.

    Placeholders survive untouched: a gate that mangled ``{count}`` would be
    testing its own transform rather than the interface.
    """

    parts: list[str] = []
    for literal, field, spec, conversion in Formatter().parse(text):
        parts.append(literal.translate(_PSEUDO_MAP))
        if field is None:
            continue
        rendered = field
        if conversion:
            rendered = f"{rendered}!{conversion}"
        if spec:
            rendered = f"{rendered}:{spec}"
        parts.append("{" + rendered + "}")
    body = "".join(parts)
    padding = _PSEUDO_PAD * max(1, round(len(body) * _PSEUDO_EXPANSION))
    return f"{_PSEUDO_PREFIX}{body}{padding}{_PSEUDO_SUFFIX}"


def _pseudo_catalog() -> Catalog:
    source = source_catalog()
    return Catalog(
        locale=PSEUDO_LOCALE,
        source_locale=source.locale,
        review=TranslationReview(
            status=ReviewStatus.MACHINE,
            reviewed_by=None,
            reviewed_at=None,
            note=("Generated pseudolocale for gates only. Never shipped to a reader."),
        ),
        messages={
            key: Message(
                key=key,
                text=pseudolocalize(message.text),
                review=ReviewStatus.MACHINE,
                locale=PSEUDO_LOCALE,
            )
            for key, message in source.messages.items()
        },
    )


def load_catalog(locale: str) -> Catalog:
    """Return the catalog for ``locale``, failing closed on an unknown one."""

    if locale == PSEUDO_LOCALE:
        return _pseudo_catalog()
    return _read_catalog(locale)


def iter_shipped_catalogs() -> Iterator[Catalog]:
    """Yield every catalog that ships in the package, source locale first."""

    for path in sorted(
        LOCALES_ROOT.glob("*.json"), key=lambda p: p.stem != SOURCE_LOCALE
    ):
        yield load_catalog(path.stem)
