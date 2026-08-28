"""The boundary detectors, and which of them apply to what kind of value.

Why this module exists
----------------------

The detectors used to live in :mod:`contextsafe.preflight`, which imports
:mod:`contextsafe.evidence`. That made them unreachable from `evidence` without
a cycle, and the only way to reach them from there was a function-local import
of a private name. Both are worse than a leaf module, so the definitions moved
here and `preflight` re-exports :func:`identifier_hits`, which is the documented
extension point and stays exactly where callers already import it from.

Nothing in this module imports anything else from the package. It is a leaf on
purpose, so any layer that accepts a value can reach one definition of what a
direct identifier looks like.

Two audiences, one detector set
-------------------------------

:func:`identifier_hits` is the free-text pass. It runs over caller-owned
evidence, which is arbitrary JSON, and over the redacted support bundle as a
second and redundant check. Its return values are unchanged from when it lived
in `preflight`, because :mod:`contextsafe.diagnostics` and its tests read them.

:func:`provenance_hits` is the bounded-token pass. It runs over the operator-
supplied provenance on an accepted evidence record: ``collector_id``,
``system_id`` and ``system_version``. Those are not free text. They are tokens
whose published grammar in ``schemas/contextsafe-evidence-v1.schema.json``
forbids a bare number, a run of four or more digits, a colon and a slash, so
most of what the free-text detectors look for cannot be written down in them at
all. One detector is excluded there and only there; see
:data:`PROVENANCE_EXEMPT_DETECTORS` for which, why, and what bounds the residual.

A detector firing on a value whose grammar should have made it unwritable is a
defect in the grammar, not a redaction that saved the day. That is the same
relationship :mod:`contextsafe.diagnostics` already has with this module, and
the reason both passes exist rather than either one alone.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

KNOWN_CANARIES: frozenset[str] = frozenset(
    {
        "contextsafephicanary",
        "ctxsafephicanaryalice",
        "realpatientcanary",
    }
)
"""Strings that exist so a leak has something to trip.

No legitimate value contains one, at any layer, in any field. Canary detection
is therefore never exempted anywhere and cannot be expressed as a grammar: a
canary is ordinary letters, so only content inspection finds it.
"""


@dataclass(frozen=True, slots=True)
class Detector:
    """One direct-identifier shape, and a name to reason about it by."""

    name: str
    pattern: re.Pattern[str]


DETECTORS: tuple[Detector, ...] = (
    Detector(
        "email",
        re.compile(
            r"(?i)(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![A-Za-z0-9])"
        ),
    ),
    Detector("ssn", re.compile(r"(?<![0-9])[0-9]{3}-[0-9]{2}-[0-9]{4}(?![0-9])")),
    Detector(
        "telephone",
        re.compile(
            r"(?<![0-9])(?:\+?1[ .-]?)?(?:\([0-9]{3}\)|[0-9]{3})[ .-][0-9]{3}[ .-][0-9]{4}(?![0-9])"
        ),
    ),
    Detector("url", re.compile(r"(?i)(?:https?://|www\.)")),
    Detector(
        "date", re.compile(r"(?<![0-9])(?:19|20)[0-9]{2}-[0-9]{2}-[0-9]{2}(?![0-9])")
    ),
    Detector(
        "record-locator",
        re.compile(
            r"(?i)\b(?:mrn|medical[ _-]?record|account)[ :#_-]+[A-Za-z0-9]{4,}\b"
        ),
    ),
    Detector("long-digit-run", re.compile(r"(?<![A-Za-z0-9])[0-9]{7,}(?![A-Za-z0-9])")),
)
"""The direct-identifier shapes, in the order they have always been in.

:func:`identifier_hits` reports a match as ``direct-identifier:<index>`` into
this tuple, which is the string ``diagnostics`` and its tests already read, so
the order is part of that contract. Reordering it changes what a support bundle
says. The names exist so a policy can refer to a detector without depending on
its position.
"""

PROVENANCE_EXEMPT_DETECTORS: frozenset[str] = frozenset({"record-locator"})
"""Detectors that do not apply to a bounded provenance token.

``record-locator`` matches a locator word (``mrn``, ``medical record``,
``account``) followed by a separator and four or more alphanumerics. In free
text that is how a medical record number is written down. In a system name it
is how a system is named: ``SYS-MEDICAL-RECORD-SYSTEM`` is an ordinary and
entirely honest ``system_id``, and rejecting it would be rejecting a value the
published schema declares valid, which is the defect that closed PR #38.

What bounds the residual is the grammar rather than this detector. A provenance
token may not contain a run of four or more digits and every one of its
separated segments must begin with a letter, so the *number* a record locator
would introduce cannot be written in one of these fields at all: ``MRN-1234567``
and ``MRN-12-3456`` are both rejected by the grammar before any detector runs.
What survives is a locator word next to letters, which identifies nobody.

Every other detector applies, and canary detection is never exempt. This is the
only exemption, it is named rather than positional, and
``tests/test_privacy_canaries.py`` pins both halves: what it lets through and
what the grammar catches instead.
"""


def normalized(value: str) -> str:
    """Return the NFKC form, so a homoglyph cannot walk past a detector."""

    return unicodedata.normalize("NFKC", value)


def _compact(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", normalized(value).casefold())


def canary_hits(value: str) -> tuple[str, ...]:
    """Return the canaries ``value`` contains, ignoring case and punctuation."""

    compact = _compact(value)
    return tuple(
        f"canary:{canary}" for canary in sorted(KNOWN_CANARIES) if canary in compact
    )


def identifier_hits(value: str) -> tuple[str, ...]:
    """Return the names of the boundary detectors ``value`` trips.

    The free-text pass: every canary and every detector. Exposed so that a
    second, independent pass can be run over something this module did not
    produce, which is what the redacted support bundle in ``diagnostics`` does
    with it. Detector coverage is bounded, and ``tests/test_privacy_canaries.py``
    records where.
    """

    text = normalized(value)
    hits = list(canary_hits(value))
    hits.extend(
        f"direct-identifier:{index}"
        for index, detector in enumerate(DETECTORS)
        if detector.pattern.search(text) is not None
    )
    return tuple(hits)


def provenance_hits(value: str) -> tuple[str, ...]:
    """Return the boundary detectors a bounded provenance token trips.

    Every canary, and every detector except those named in
    :data:`PROVENANCE_EXEMPT_DETECTORS`. Reported by detector name rather than
    by index, because a caller of this function is deciding whether to reject a
    named field and a position into a tuple tells it nothing.
    """

    text = normalized(value)
    hits = list(canary_hits(value))
    hits.extend(
        f"direct-identifier:{detector.name}"
        for detector in DETECTORS
        if detector.name not in PROVENANCE_EXEMPT_DETECTORS
        and detector.pattern.search(text) is not None
    )
    return tuple(hits)
