"""The secret scan's allowlist, pinned in both directions.

An allowlist is a hole in a gate. `.gitleaks.toml` carries three entries, each
a verified false positive, and the danger is not that they are wrong today but
that one of them is wider than it reads and covers a real credential tomorrow.

These tests need no gitleaks: they read the published regexes and check what
they do and do not match. That is the property that matters, and checking it
this way means it is checked on every run of `make verify` rather than only
where the scanner happens to be installed.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

CONFIG = Path(__file__).resolve().parents[1] / ".gitleaks.toml"


def _allowlist_regexes() -> tuple[re.Pattern[str], ...]:
    with CONFIG.open("rb") as handle:
        config = tomllib.load(handle)
    return tuple(re.compile(item) for item in config["allowlist"]["regexes"])


def test_the_config_extends_the_default_ruleset() -> None:
    """An allowlist over a replaced ruleset would be a different gate."""

    with CONFIG.open("rb") as handle:
        config = tomllib.load(handle)
    assert config["extend"]["useDefault"] is True
    assert "rules" not in config, "this file allows exceptions; it defines no rules"


def test_every_entry_carries_its_reason() -> None:
    """The exemption set is readable in one place, with why beside each entry."""

    text = CONFIG.read_text(encoding="utf-8")
    assert text.count("#") >= len(_allowlist_regexes())
    assert "verified by hand" in text


@pytest.mark.parametrize(
    "value",
    [
        "CSYN-9876543210",
        "CSYN-CTP-I01",
        "CSYN-ASTER",
        "fixture-gender-1",
        "max_length=96",
        "max_length=1",
    ],
)
def test_the_shapes_it_exists_for_are_allowed(value: str) -> None:
    """Each is a value this repository publishes by construction."""

    assert any(item.fullmatch(value) for item in _allowlist_regexes()), value


# Credential shapes, kept as (prefix, separator, tail) and joined at run time.
# Written whole they would be real findings for the very scanner under test --
# they were, on the first run of this file -- and a literal is folded into the
# .pyc as well, so splitting has to survive compilation: ``str.join`` is a call,
# and a call is not constant-folded.
_CREDENTIAL_PARTS = (
    ("ghp", "_", "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"),
    ("xoxb", "-", "2074528374652-2074528374653-Xy7Kq2mNvB4pLr8sTf3wZa1c"),
    ("sk", "_", "live_4eC39HqLyjWDarjtT1zdp7dc"),
    ("AKIAIOSFODNN7", "", "EXAMPLE"),
    ("postgres://user:hunter2@db.contextsafe.invalid", ":", "5432/app"),
    ("-----BEGIN RSA PRIVATE", " ", "KEY-----"),
)


def _credential_shapes() -> tuple[str, ...]:
    return tuple("".join(parts) for parts in _CREDENTIAL_PARTS)


@pytest.mark.parametrize("index", range(len(_CREDENTIAL_PARTS)))
def test_no_credential_shape_is_allowed(index: int) -> None:
    """The boundary, stated as a test rather than as a claim in a comment."""

    secret = _credential_shapes()[index]
    assert not any(item.fullmatch(secret) for item in _allowlist_regexes()), secret


@pytest.mark.parametrize("index", range(len(_CREDENTIAL_PARTS)))
def test_a_credential_beside_an_allowed_token_is_not_allowed(index: int) -> None:
    """The anchoring cases.

    An allowlist written without ``^``/``$`` would swallow a real credential
    that merely sat next to an allowed token.
    """

    secret = _credential_shapes()[index]
    for neighbour in (f"CSYN-ASTER {secret}", f"max_length=96; {secret}"):
        assert not any(item.fullmatch(neighbour) for item in _allowlist_regexes()), (
            neighbour
        )


def test_a_token_with_anything_appended_is_not_allowed() -> None:
    """``prefixCSYN-ASTER`` and ``CSYN-ASTER extra`` are both outside."""

    for value in ("prefixCSYN-ASTER", "CSYN-ASTER extra", "max_length=96 more"):
        assert not any(item.fullmatch(value) for item in _allowlist_regexes()), value


def test_the_synthetic_entries_are_the_published_grammar() -> None:
    """The allowlist admits the namespace the code defines, not a wider one."""

    from contextsafe.mapping_profile import SYNTHETIC_TOKEN_PATTERN

    published = SYNTHETIC_TOKEN_PATTERN.pattern
    allowed = {item.pattern for item in _allowlist_regexes()}
    for half in ("CSYN-[A-Z0-9][A-Z0-9_.:-]{0,95}", "fixture-[a-z0-9][a-z0-9-]{0,63}"):
        assert half in published
        assert f"^{half}$" in allowed
