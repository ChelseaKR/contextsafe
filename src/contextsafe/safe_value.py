"""Values a support bundle is allowed to contain, and nothing else.

A support bundle produced by this tool could carry exactly the data the product
exists to protect: a patient's name in an export path, a medical record number
in an exception message, a case token somebody built out of a real identifier.
The usual defence is a redactor — assemble the bundle, then run patterns over it
and blank what matches. That defence fails the way every denylist fails. It
misses ``MRN: 1 2 3 4 5 6 7``. It misses a first name whose ``a`` is the
Cyrillic homoglyph rather than the Latin letter. It misses a name in a
directory component when it was only looking at filenames. And each miss ships
something a filter said was clean.

So there is no filter here. There is a type.

Everything in a bundle is a :class:`SafeValue`, and a ``SafeValue`` can only be
built by one of the constructors below. Every constructor is total: it either
returns a value that carries no free text, or it raises. There is deliberately
no ``raw()`` and no escape hatch, so a caller holding a string with a patient
name in it has nowhere to put it:

* :func:`count` and :func:`byte_count` take a non-negative integer.
* :func:`flag` takes a boolean.
* :func:`enum_value` takes a string that must already be a member of a closed
  set the caller declares in the same call.
* :func:`digest` takes any text and returns its SHA-256. The text does not
  survive. Two bundles can still be compared, and a value can still be matched
  against a known one, without either being disclosed.
* :func:`version` takes a dotted numeric version. It starts with a digit, so a
  hyphenated name cannot pass as one.
* :func:`path_shape` takes a path and returns its depth, its extension if the
  extension is on a published list, and the SHA-256 of its final component. No
  directory name and no filename survives.

The serializer in :func:`to_json` walks the structure and raises on anything
that is not a ``SafeValue``, so "somebody added a plain string to the bundle
next year" is a test failure rather than a disclosure.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePath

from contextsafe.canonical import JsonValue
from contextsafe.errors import ContextSafeError

MAX_ENUM_LENGTH = 64
VERSION_PATTERN = re.compile(r"^[0-9]+(?:\.[0-9]+){0,3}(?:[-+][A-Za-z0-9.]{1,16})?$")
"""A version starts with a digit.

Deliberately narrower than a general identifier. A pattern that merely forbade
spaces would happily accept ``exports-Jordan-Rivera-1987`` as a version string,
which the free-text property test in ``tests/test_diagnostics.py`` found by
handing every constructor a hostile name. A version is a number, not a word.
"""
PUBLISHED_SUFFIXES = frozenset({".json", ".sqlite", ".part", ".html", ".txt", ".log"})
"""Extensions a bundle may name. Anything else is reported as ``other``."""


class SafeKind(StrEnum):
    """What a bundle field is, which is also the proof of what it is not."""

    COUNT = "count"
    BYTE_COUNT = "byte_count"
    FLAG = "flag"
    ENUM = "enum"
    DIGEST = "digest"
    VERSION = "version"
    PATH_SHAPE = "path_shape"


@dataclass(frozen=True, slots=True)
class SafeValue:
    """A value that has already been proved not to carry free text."""

    kind: SafeKind
    value: JsonValue

    def to_json(self) -> JsonValue:
        """Return the serialized form, which records its own kind."""

        return {"kind": self.kind.value, "value": self.value}


def _reject(pointer: str, message: str) -> ContextSafeError:
    return ContextSafeError("unsafe_bundle_value", pointer, message)


def count(value: int, *, pointer: str = "$") -> SafeValue:
    """Return a non-negative count."""

    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise _reject(pointer, "a count must be a non-negative integer")
    return SafeValue(SafeKind.COUNT, value)


def byte_count(value: int, *, pointer: str = "$") -> SafeValue:
    """Return a non-negative size in bytes."""

    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise _reject(pointer, "a byte count must be a non-negative integer")
    return SafeValue(SafeKind.BYTE_COUNT, value)


def flag(value: bool, *, pointer: str = "$") -> SafeValue:
    """Return a boolean."""

    if not isinstance(value, bool):
        raise _reject(pointer, "a flag must be a boolean")
    return SafeValue(SafeKind.FLAG, value)


def enum_value(
    value: str, allowed: frozenset[str] | Sequence[str], *, pointer: str = "$"
) -> SafeValue:
    """Return a string that is already a member of a closed published set.

    The closed set is passed in at the call site rather than checked later, so
    the question "could an arbitrary string reach the bundle here?" is answered
    by reading one line.
    """

    permitted = frozenset(allowed)
    if not permitted:
        raise _reject(pointer, "an enum needs a non-empty set of permitted values")
    if value not in permitted:
        raise _reject(pointer, "value is not a member of the published set")
    if len(value) > MAX_ENUM_LENGTH:
        raise _reject(pointer, "enum value is longer than the published limit")
    return SafeValue(SafeKind.ENUM, value)


def digest(value: str, *, pointer: str = "$") -> SafeValue:
    """Return the SHA-256 of ``value``. The text itself does not survive."""

    if not isinstance(value, str):
        raise _reject(pointer, "a digest is taken over text")
    return SafeValue(SafeKind.DIGEST, hashlib.sha256(value.encode("utf-8")).hexdigest())


def version(value: str, *, pointer: str = "$") -> SafeValue:
    """Return a version string, validated against a narrow pattern."""

    if not isinstance(value, str) or VERSION_PATTERN.fullmatch(value) is None:
        raise _reject(pointer, "a version must match the published version pattern")
    return SafeValue(SafeKind.VERSION, value)


def path_shape(value: PurePath | str, *, pointer: str = "$") -> SafeValue:
    """Return the shape of a path: depth, published extension, name digest.

    No directory component and no filename survives. A patient name in the
    middle of an export path is as invisible here as one in the filename,
    which is the difference between this and a redactor that was only ever
    pointed at basenames.
    """

    path = PurePath(value)
    suffix = path.suffix if path.suffix in PUBLISHED_SUFFIXES else "other"
    return SafeValue(
        SafeKind.PATH_SHAPE,
        {
            "depth": len([part for part in path.parts if part not in ("/", "")]),
            "suffix": suffix,
            "name_sha256": hashlib.sha256(path.name.encode("utf-8")).hexdigest(),
        },
    )


Section = Mapping[str, "SafeValue | Section | Sequence[SafeValue | Section]"]


def to_json(section: Section, *, pointer: str = "$") -> dict[str, JsonValue]:
    """Serialize a section, raising on anything that is not a ``SafeValue``."""

    result: dict[str, JsonValue] = {}
    for key in sorted(section):
        result[key] = _node_to_json(section[key], f"{pointer}.{key}")
    return result


def _node_to_json(node: object, pointer: str) -> JsonValue:
    if isinstance(node, SafeValue):
        return node.to_json()
    if isinstance(node, Mapping):
        return to_json(node, pointer=pointer)
    if isinstance(node, list | tuple):
        return [
            _node_to_json(item, f"{pointer}[{index}]")
            for index, item in enumerate(node)
        ]
    raise _reject(
        pointer,
        "only SafeValue, mappings of them, and sequences of them may be "
        "serialized into a bundle",
    )
