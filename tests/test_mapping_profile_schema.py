"""Published mapping-profile contracts against the runtime (B-026).

``schemas/contextsafe-mapping-profile-v1.schema.json`` is the shape
``contextsafe import --mapping`` and ``contextsafe mapping validate`` read, and
``schemas/contextsafe-compiled-mapping-profile-v1.schema.json`` is the shape
``mapping validate`` emits. These tests hold each to the runtime the way
``tests/test_receipt_schema.py`` and ``tests/test_lis_export_schema.py`` do:
the reference profiles validate and the runtime reads them; the per-format
carrier enums are the importer registry's own table; the review status the
contract admits is the one the runtime admits; every rejection fixture is
refused by the runtime, and which layer refuses it is recorded; the compiled
document validates and its constants cannot be relabelled; and every required
field the contracts declare is exercised.
"""

import json
import re
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from contextsafe.errors import ContextSafeError
from contextsafe.importers import carrier_table, compile_profile, load_profile
from contextsafe.mapping_profile import (
    COMPILED_LIMITATIONS,
    COMPILED_MAPPING_PROFILE_SCHEMA_VERSION,
    FIXTURE_SYSTEM_PATTERN,
    MAPPING_PROFILE_SCHEMA_VERSION,
    MAX_ROWS,
    PRONOUN_SET_PATTERN,
    REVIEW_STATUS_NOT_REVIEWED,
    RSG_CONTEXTS,
    RSG_SOURCES,
    SOURCE_TOKEN_PATTERN,
    SYNTHETIC_TOKEN_PATTERN,
)
from contextsafe.models import ConceptKind
from contextsafe.reference_fixtures import REFERENCE_FILES, REFERENCE_ROOT

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "schemas"
PROFILE_SCHEMA = SCHEMAS / "contextsafe-mapping-profile-v1.schema.json"
COMPILED_SCHEMA = SCHEMAS / "contextsafe-compiled-mapping-profile-v1.schema.json"
FIXTURES = ROOT / "tests" / "fixtures" / "mapping"
REFERENCE_PROFILES = sorted(
    name for name in REFERENCE_FILES if name.startswith("mapping-")
)

SCHEMA_CATCHES = {
    "reject-gi-to-spcu.json",
    "reject-rsg-to-spcu.json",
    "reject-cross-concept.json",
    "reject-target-not-synthetic.json",
    "reject-target-system-not-synthetic.json",
    "reject-review-approved.json",
    "reject-review-named.json",
    "reject-carrier-unknown.json",
    "reject-format-unknown.json",
    "reject-spcu-binds-context.json",
    "reject-token-free-text.json",
    "reject-unknown-field.json",
    "reject-empty-rows.json",
    "reject-wrong-schema.json",
}
"""Rejecting fixtures the schema alone refuses.

The rest (``reject-collapse.json``, ``reject-duplicate-source.json``, and
``reject-carrier-concept-mismatch.json``) validate structurally and are
refused by the runtime only: cross-row constraints and the carrier-to-concept
table are semantic constraints the contract lists and cannot express.
"""


def _schema(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _validator(path: Path) -> Draft202012Validator:
    Draft202012Validator.check_schema(_schema(path))
    return Draft202012Validator(_schema(path))


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _runtime_accepts(document: object) -> bool:
    try:
        load_profile(document)
    except ContextSafeError:
        return False
    return True


@pytest.mark.parametrize("name", REFERENCE_PROFILES)
def test_every_reference_profile_validates_and_the_runtime_reads_it(
    name: str,
) -> None:
    document = _read(REFERENCE_ROOT / name)
    _validator(PROFILE_SCHEMA).validate(document)
    assert _runtime_accepts(document)
    compiled = compile_profile(document).to_dict()
    _validator(COMPILED_SCHEMA).validate(compiled)
    _validator(PROFILE_SCHEMA).validate(compiled["profile"])


def test_there_is_one_reference_profile_per_registered_format() -> None:
    expected = sorted(f"mapping-{format_name}.json" for format_name in carrier_table())
    assert expected == REFERENCE_PROFILES


def test_contract_constants_are_the_runtime_constants() -> None:
    schema = _schema(PROFILE_SCHEMA)
    compiled = _schema(COMPILED_SCHEMA)
    assert schema["properties"]["schema_version"] == {
        "const": MAPPING_PROFILE_SCHEMA_VERSION
    }
    assert compiled["properties"]["schema_version"] == {
        "const": COMPILED_MAPPING_PROFILE_SCHEMA_VERSION
    }
    assert schema["properties"]["review"]["properties"]["status"] == {
        "const": REVIEW_STATUS_NOT_REVIEWED
    }
    assert schema["properties"]["rows"]["maxItems"] == MAX_ROWS
    assert schema["properties"]["rows"]["minItems"] == 1
    assert set(schema["properties"]["format"]["enum"]) == set(carrier_table())
    assert set(compiled["properties"]["format"]["enum"]) == set(carrier_table())
    assert compiled["properties"]["review_status"] == {
        "const": REVIEW_STATUS_NOT_REVIEWED
    }
    assert compiled["properties"]["signature_status"] == {"const": "not_verified"}
    assert compiled["properties"]["executable"] == {"const": False}
    assert (
        tuple(
            item["const"]
            for item in compiled["properties"]["limitations"]["prefixItems"]
        )
        == COMPILED_LIMITATIONS
    )
    defs = schema["$defs"]
    assert defs["sourceToken"]["pattern"] == SOURCE_TOKEN_PATTERN.pattern
    assert defs["syntheticToken"]["pattern"] == SYNTHETIC_TOKEN_PATTERN.pattern.replace(
        "(?:", "("
    )
    assert defs["fixtureSystem"]["pattern"] == FIXTURE_SYSTEM_PATTERN.pattern
    assert defs["pronounSet"]["pattern"] == PRONOUN_SET_PATTERN.pattern.replace(
        "(?:", "("
    )
    rsg = defs["recordedSexOrGenderTarget"]["properties"]
    assert set(rsg["context"]["oneOf"][0]["enum"]) == RSG_CONTEXTS
    assert set(rsg["source"]["oneOf"][0]["enum"]) == RSG_SOURCES
    assert set(defs["concept"]["enum"]) == {item.value for item in ConceptKind}
    assert set(defs["spcuValueTarget"]["properties"]) == {"value"}
    description = schema["description"]
    assert "Reference-only and ungoverned" in description
    assert "not_reviewed" in description
    assert "A-020" in description and "A-021" in description
    assert "mapping sign" in description


def test_the_per_format_carrier_enums_are_the_importer_registry() -> None:
    """The schema's if/then blocks and the runtime table name the same carriers."""

    schema = _schema(PROFILE_SCHEMA)
    published: dict[str, set[str]] = {}
    for clause in schema["allOf"]:
        formats = clause["if"]["properties"]["format"]
        names = [formats["const"]] if "const" in formats else formats["enum"]
        carriers = clause["then"]["properties"]["rows"]["items"]["properties"][
            "source"
        ]["properties"]["carrier"]["enum"]
        for name in names:
            published[name] = set(carriers)
    assert published == {name: set(table) for name, table in carrier_table().items()}


@pytest.mark.parametrize(
    "name", sorted(path.name for path in FIXTURES.glob("reject-*.json"))
)
def test_every_rejecting_fixture_is_refused_and_its_layer_is_recorded(
    name: str,
) -> None:
    document = _read(FIXTURES / name)
    assert not _runtime_accepts(document)
    structural = _validator(PROFILE_SCHEMA).is_valid(document)
    assert structural == (name not in SCHEMA_CATCHES), name


def test_the_schema_alone_does_not_establish_the_runtime_semantics() -> None:
    """A document the schema accepts can still collapse two sources."""

    document = _read(FIXTURES / "reject-collapse.json")
    _validator(PROFILE_SCHEMA).validate(document)
    assert not _runtime_accepts(document)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("signature_status", "verified"),
        ("signature_status", "not_signed"),
        ("executable", True),
        ("review_status", "approved"),
        ("valid_for_signing", False),
    ],
)
def test_compiled_constants_cannot_be_relabelled(field: str, value: object) -> None:
    compiled = compile_profile(_read(REFERENCE_ROOT / "mapping-lis-csv.json")).to_dict()
    compiled[field] = value
    assert not _validator(COMPILED_SCHEMA).is_valid(compiled)


@pytest.mark.parametrize(
    "limitations",
    [
        [],
        list(COMPILED_LIMITATIONS[:2]),
        [*COMPILED_LIMITATIONS, "reviewed-by-the-vendor"],
        [COMPILED_LIMITATIONS[1], COMPILED_LIMITATIONS[0], COMPILED_LIMITATIONS[2]],
    ],
)
def test_compiled_limitations_are_pinned_in_order(limitations: list[str]) -> None:
    compiled = compile_profile(_read(REFERENCE_ROOT / "mapping-lis-csv.json")).to_dict()
    compiled["limitations"] = limitations
    assert not _validator(COMPILED_SCHEMA).is_valid(compiled)


def _required_field_cases(path: Path) -> list[tuple[tuple[str | int, ...], str]]:
    schema = _schema(path)
    defs = schema.get("$defs", {})
    cases: list[tuple[tuple[str | int, ...], str]] = []

    def resolve(node: dict[str, Any]) -> dict[str, Any]:
        while "$ref" in node:
            resolved = defs[node["$ref"].removeprefix("#/$defs/")]
            assert isinstance(resolved, dict)
            node = resolved
        return node

    def walk(node: dict[str, Any], location: tuple[str | int, ...]) -> None:
        node = resolve(node)
        for key in node.get("required", []):
            cases.append((location, key))
        for key, subschema in node.get("properties", {}).items():
            walk(subschema, (*location, key))
        items = node.get("items")
        if isinstance(items, dict):
            walk(items, (*location, 0))

    walk(schema, ())
    return cases


PROFILE_REQUIRED = _required_field_cases(PROFILE_SCHEMA)
COMPILED_REQUIRED = _required_field_cases(COMPILED_SCHEMA)


def _at(document: dict[str, Any], location: tuple[str | int, ...]) -> Any:
    target: Any = document
    for key in location:
        target = target[key]
    return target


@pytest.mark.parametrize(
    ("location", "key"),
    [case for case in PROFILE_REQUIRED if "value" not in case[0]],
    ids=[
        "-".join(str(part) for part in (*loc, key))
        for loc, key in PROFILE_REQUIRED
        if "value" not in loc
    ],
)
def test_missing_required_profile_fields_fail_both_layers(
    location: tuple[str | int, ...], key: str
) -> None:
    document = _read(REFERENCE_ROOT / "mapping-hl7v2-er7.json")
    del _at(document, location)[key]
    assert not _validator(PROFILE_SCHEMA).is_valid(document)
    assert not _runtime_accepts(document)


@pytest.mark.parametrize(
    ("location", "key"),
    COMPILED_REQUIRED,
    ids=["-".join(str(part) for part in (*loc, key)) for loc, key in COMPILED_REQUIRED],
)
def test_missing_required_compiled_fields_fail_closed(
    location: tuple[str | int, ...], key: str
) -> None:
    compiled = compile_profile(
        _read(REFERENCE_ROOT / "mapping-hl7v2-er7.json")
    ).to_dict()
    del _at(compiled, location)[key]
    assert not _validator(COMPILED_SCHEMA).is_valid(compiled)


@pytest.mark.parametrize(
    "path", [(), ("review",), ("rows", 0), ("rows", 0, "source"), ("rows", 0, "target")]
)
def test_unknown_fields_fail_closed_at_every_level(path: tuple[str | int, ...]) -> None:
    document = _read(REFERENCE_ROOT / "mapping-hl7v2-er7.json")
    _at(document, path)["contextsafe_extension"] = "unreviewed"
    assert not _validator(PROFILE_SCHEMA).is_valid(document)
    assert not _runtime_accepts(document)


@pytest.mark.parametrize("path", [PROFILE_SCHEMA, COMPILED_SCHEMA])
def test_every_published_pattern_is_ecma_262_safe(path: Path) -> None:
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

    walk(_schema(path))
    assert patterns
    for pattern in patterns:
        assert "(?i" not in pattern and "(?P" not in pattern and "(?:" not in pattern
        re.compile(pattern)
