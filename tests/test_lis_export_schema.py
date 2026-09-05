"""Published LIS export contract against the runtime profile (B-025).

``schemas/contextsafe-lis-export-v0.1.schema.json`` is the JSON shape
``contextsafe import --format lis-json`` reads. It is an input contract, so
the agreement to keep is the other way round from the receipt's: everything
the schema admits, the runtime must be willing to read, and everything the
runtime's column allowlist and cell grammars say must be what the schema
says. These tests hold the two together the way ``tests/test_receipt_schema.py``
holds the receipt contract to the runner, and they record which rejections
are structural (the schema catches them) and which are semantic (only the
runtime does), so a consumer validating against the schema alone knows what
it has not established.
"""

import json
import re
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from jsonschema import Draft202012Validator, ValidationError

from contextsafe.errors import ContextSafeError
from contextsafe.importers.lis import (
    LIS_CSV_FORMAT,
    LIS_EXPORT_SCHEMA_VERSION,
    LIS_PROFILE,
    RESULT_TOKEN_PATTERN,
    SYNTHETIC_IDENTIFIER_PATTERN,
    SYNTHETIC_TOKEN_PATTERN,
    convert_table,
    parse_lis_json,
)
from contextsafe.models import Checkpoint
from contextsafe.reference_fixtures import REFERENCE_ROOT
from contextsafe.validation import parse_case

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "contextsafe-lis-export-v0.1.schema.json"
FIXTURES = ROOT / "tests" / "fixtures" / "lis"
_CASE = parse_case(
    json.loads((REFERENCE_ROOT / "case.json").read_text(encoding="utf-8"))
)

RSG_VALUES = ("F", "M", "X", "unknown")
"""The recorded-sex-or-gender vocabulary, restated independently of the runtime.

``contextsafe.validation`` holds the authoritative set. It is restated here
rather than imported so that a widening on either side is a visible test
failure rather than a tautology.
"""

SCHEMA_CATCHES = {
    "reject-wrong-schema.json",
    "reject-top-level-unknown.json",
    "reject-rows-not-array.json",
    "reject-empty-rows.json",
    "reject-too-many-rows.json",
    "reject-row-not-object.json",
    "reject-unknown-key.json",
    "reject-unknown-key-non-string.json",
    "reject-prohibited-key.json",
    "reject-missing-patient-id.json",
    "reject-later-row-unknown-key.json",
    "reject-non-string-cell.json",
    "reject-null-identity.json",
    "reject-formula-cell.json",
    "reject-non-synthetic-patient-id.json",
    "reject-empty-identity-cell.json",
    "reject-unsupported-sex.json",
    "reject-non-synthetic-order.json",
    "reject-free-text-result.json",
    "reject-direct-identifier.json",
}
"""Rejecting fixtures the schema alone refuses.

The rest (``reject-no-identity-key.json``, ``reject-inconsistent-key-set.json``,
``reject-canary.json``, and ``reject-other-case.json``) validate
structurally and are refused by the runtime only: a semantic constraint the
contract lists and cannot express. ``reject-direct-identifier.json`` is
caught by the result-cell grammar, which admits no ``@``; the boundary
detector that refuses it at runtime is the reason it is listed as a
fixture, and the grammar catching it too is incidental.
"""


def _schema() -> dict[str, Any]:
    value = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _validator() -> Draft202012Validator:
    Draft202012Validator.check_schema(_schema())
    return Draft202012Validator(_schema())


def _runtime_accepts(document: object) -> bool:
    try:
        convert_table(
            parse_lis_json(document),
            format_name=LIS_CSV_FORMAT,
            case=_CASE,
            checkpoint=Checkpoint.LIS_RETURN,
            source_sha256="0" * 64,
            source_byte_count=0,
        )
    except ContextSafeError:
        return False
    return True


def test_reference_export_validates_and_converts() -> None:
    document = json.loads(
        (REFERENCE_ROOT / "lis-export.json").read_text(encoding="utf-8")
    )
    _validator().validate(document)
    assert _runtime_accepts(document)


def test_schema_columns_bounds_and_grammars_are_the_runtime_profile() -> None:
    schema = _schema()
    rows = schema["properties"]["rows"]
    row = rows["items"]
    assert schema["properties"]["schema_version"] == {
        "const": LIS_EXPORT_SCHEMA_VERSION
    }
    assert set(schema["properties"]) == {"schema_version", "rows"}
    assert schema["additionalProperties"] is False
    assert row["additionalProperties"] is False
    assert tuple(row["properties"]) == LIS_PROFILE.columns
    assert row["required"] == [LIS_PROFILE.case_column]
    assert rows["minItems"] == 1
    assert rows["maxItems"] == LIS_PROFILE.max_rows
    assert row["properties"]["sex"] == {"enum": list(RSG_VALUES)}
    defs = schema["$defs"]
    presence = defs["presenceOrSyntheticToken"]["oneOf"]
    assert presence[0] == {"enum": ["declined", "unknown", "absent"]}
    assert presence[1]["pattern"] == SYNTHETIC_TOKEN_PATTERN.pattern
    assert defs["resultCell"]["pattern"] == (
        "^(?:" + RESULT_TOKEN_PATTERN.pattern[1:-1] + ")?$"
    )
    assert defs["syntheticIdentifierCell"]["pattern"] == (
        "^(?:" + SYNTHETIC_IDENTIFIER_PATTERN.pattern[1:-1] + ")?$"
    )
    for column in LIS_PROFILE.identity_columns:
        if column != "sex":
            assert row["properties"][column] == {
                "$ref": "#/$defs/presenceOrSyntheticToken"
            }
    for column in LIS_PROFILE.result_columns:
        expected = (
            "#/$defs/syntheticIdentifierCell"
            if column in LIS_PROFILE.identifier_columns
            else "#/$defs/resultCell"
        )
        assert row["properties"][column] == {"$ref": expected}
    description = schema["description"]
    assert "Reference-only and ungoverned" in description
    assert "profile_reviewed is false" in description
    assert "produce no observation" in description
    assert "never as gender_identity or sex_parameter_for_clinical_use" in " ".join(
        schema["x-contextsafe-semantic-constraints"]
    )


@pytest.mark.parametrize(
    "name", sorted(path.name for path in FIXTURES.glob("accept-*.json"))
)
def test_every_accepting_json_fixture_validates_and_converts(name: str) -> None:
    document = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    _validator().validate(document)
    assert _runtime_accepts(document)


@pytest.mark.parametrize(
    "name", sorted(path.name for path in FIXTURES.glob("reject-*.json"))
)
def test_every_rejecting_json_fixture_is_refused_and_its_layer_is_recorded(
    name: str,
) -> None:
    """The runtime refuses every one; the schema refuses exactly the listed ones."""

    document = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    assert not _runtime_accepts(document)
    structural = _validator().is_valid(document)
    assert structural == (name not in SCHEMA_CATCHES), name


def test_schema_alone_does_not_establish_the_runtime_semantics() -> None:
    """A document the schema accepts can still be from another case."""

    document = {
        "schema_version": LIS_EXPORT_SCHEMA_VERSION,
        "rows": [{"patient_id": "CSYN-CTP-Z99", "name_to_use": "CSYN-ASTER"}],
    }
    _validator().validate(document)
    assert not _runtime_accepts(document)


_TOKEN_SUFFIX = st.text(alphabet="ABCDEFGH0123456789", min_size=1, max_size=6)
_PRESENCE_OR_TOKEN = st.one_of(
    st.sampled_from(("declined", "unknown", "absent")),
    _TOKEN_SUFFIX.map(lambda s: f"CSYN-VAL-{s}"),
)
_RESULT = st.one_of(
    st.just(""),
    st.sampled_from(
        ("4.1", "fixture-unit-alpha/beta", "fixture-range-1", "fixture-flag-1")
    ),
)
_IDENTIFIER = st.one_of(st.just(""), _TOKEN_SUFFIX.map(lambda s: f"CSYN-{s}"))
_CELLS = {
    "name_to_use": _PRESENCE_OR_TOKEN,
    "pronouns": _PRESENCE_OR_TOKEN,
    "sex": st.sampled_from(RSG_VALUES),
    "order": _IDENTIFIER,
    "specimen": _IDENTIFIER,
}


@st.composite
def _documents(draw: st.DrawFn) -> dict[str, Any]:
    identity = draw(
        st.lists(
            st.sampled_from(LIS_PROFILE.identity_columns),
            min_size=1,
            max_size=3,
            unique=True,
        )
    )
    result = draw(
        st.lists(st.sampled_from(LIS_PROFILE.result_columns), max_size=7, unique=True)
    )
    columns = [*identity, *result]
    count = draw(st.integers(min_value=1, max_value=4))
    return {
        "schema_version": LIS_EXPORT_SCHEMA_VERSION,
        "rows": [
            {
                "patient_id": "CSYN-CTP-I01",
                **{column: draw(_CELLS.get(column, _RESULT)) for column in columns},
            }
            for _ in range(count)
        ],
    }


@settings(max_examples=150, deadline=None)
@given(document=_documents())
def test_what_the_schema_admits_the_runtime_reads(document: dict[str, Any]) -> None:
    _validator().validate(document)
    assert _runtime_accepts(document)


@settings(max_examples=150, deadline=None)
@given(
    document=_documents(),
    key=st.text(min_size=1, max_size=16).filter(lambda s: s not in LIS_PROFILE.columns),
)
def test_any_key_outside_the_allowlist_is_refused_by_both(
    document: dict[str, Any], key: str
) -> None:
    document["rows"][0][key] = "CSYN-X"
    with pytest.raises(ValidationError):
        _validator().validate(document)
    assert not _runtime_accepts(document)


def test_every_published_pattern_is_ecma_262_safe() -> None:
    """No inline flag and no Python-only construct in a published ``pattern``."""

    patterns: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if isinstance(node.get("pattern"), str):
                patterns.append(node["pattern"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(_schema())
    assert patterns
    for pattern in patterns:
        assert "(?i" not in pattern and "(?P" not in pattern
        re.compile(pattern)
