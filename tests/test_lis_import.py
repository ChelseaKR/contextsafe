"""The LIS export identity importers, ``lis-csv`` and ``lis-json`` (B-025).

What these tests pin. The conversion reads only the identity columns of a
laboratory result export and emits name-to-use, pronoun, and recorded-sex-
or-gender observations at ``lis_return``, one per distinct value per
column, each pointed at the first row that carries it and at the source's
digest. The result columns are recognized, counted, and never observed.
``sex`` becomes recorded sex or gender in the fixed ``laboratory`` context
and nothing else; no path in the module can produce a gender identity or a
sex parameter for clinical use. The conversion is whole or nothing: an
unknown column, a duplicate column, a missing case column, a malformed
record, a formula-leading cell, an empty identity cell, a non-synthetic
identifier anywhere, a cell outside its column's grammar, or a row from
another case rejects the source with a code and a position and produces
nothing, and the rejection never carries a cell. The profile is
reference-only, its type refuses ``profile_reviewed``, and every result
says so.

One fixture per rule sits under ``tests/fixtures/lis/``: the accepting
files show what the reader admits, the rejecting files show what it
refuses, and the table below says which code and which location each one
must produce.
"""

import copy
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

import contextsafe.preflight as preflight_module
from contextsafe.canonical import canonical_json
from contextsafe.cli import EXIT_CONTRACT_ERROR, EXIT_SUCCESS, main
from contextsafe.errors import ContextSafeError
from contextsafe.evaluator import evaluate
from contextsafe.importers import (
    REGISTRY,
    ImportErrorCode,
    ImportWarningCode,
    available_formats,
    import_source,
)
from contextsafe.importers.lis import (
    _IDENTITY_CONCEPTS,
    FORMULA_PREFIXES,
    LABORATORY_CONTEXT,
    LIS_CSV_FORMAT,
    LIS_EXPORT_SCHEMA_VERSION,
    LIS_JSON_FORMAT,
    LIS_PROFILE,
    LisProfile,
    LisTable,
    convert_table,
    parse_lis_csv,
    parse_lis_json,
)
from contextsafe.importers.lis_csv import CsvBounds, parse_csv
from contextsafe.models import Checkpoint, ConceptKind, SyntheticCase
from contextsafe.preflight import MAX_EVIDENCE_BYTES
from contextsafe.reference_fixtures import REFERENCE_ROOT
from contextsafe.validation import parse_bundle, parse_case

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = REFERENCE_ROOT
FIXTURES = ROOT / "tests" / "fixtures" / "lis"
FORMATS = (LIS_CSV_FORMAT, LIS_JSON_FORMAT)
_CASE_JSON = json.loads((REFERENCE / "case.json").read_text(encoding="utf-8"))
_CASE = parse_case(_CASE_JSON)


def _format_for(name: str) -> str:
    return LIS_CSV_FORMAT if name.endswith(".csv") else LIS_JSON_FORMAT


def _convert(name: str, case: SyntheticCase = _CASE) -> Any:
    return import_source(
        _format_for(name), FIXTURES / name, case=case, checkpoint=Checkpoint.LIS_RETURN
    )


def _reject(name: str) -> ContextSafeError:
    with pytest.raises(ContextSafeError) as raised:
        _convert(name)
    return raised.value


def _import_args(
    name: str, case_path: Path, checkpoint: str = "lis_return"
) -> list[str]:
    return [
        "import",
        "--format",
        _format_for(name),
        "--source",
        str(FIXTURES / name),
        "--case",
        str(case_path),
        "--checkpoint",
        checkpoint,
    ]


def _rule(concept: str, expected: dict[str, Any], index: int) -> dict[str, Any]:
    return {
        "rule_id": f"A-I{index:02d}",
        "version": "0.1.0",
        "case_id": _CASE.case_id,
        "checkpoint": Checkpoint.LIS_RETURN.value,
        "concept": concept,
        "expected": expected,
        "required": True,
    }


_LIS_RULES: dict[str, Any] = {
    "schema_version": "contextsafe.rule-set/0.1.0",
    "rules": [
        _rule("name_to_use", _CASE.name_to_use.to_dict(), 1),
        _rule("pronouns", _CASE.pronouns.to_dict(), 2),
        _rule("recorded_sex_or_gender", _CASE.recorded_sex_or_gender[0].to_dict(), 3),
    ],
}
"""Three lis_return rules expecting exactly what the case manifest declares."""


# --- the reference round trip -------------------------------------------------


@pytest.mark.parametrize("name", ["lis-export.csv", "lis-export.json"])
def test_reference_export_reads_into_three_identity_observations(name: str) -> None:
    source = REFERENCE / name
    raw = source.read_bytes()
    result = import_source(
        _format_for(name), source, case=_CASE, checkpoint=Checkpoint.LIS_RETURN
    )

    assert result.format_name == _format_for(name)
    assert result.mapping_version == LIS_PROFILE.version == "0.1.0"
    assert result.record_count == len(result.observations) == 3
    assert result.source_sha256 == hashlib.sha256(raw).hexdigest()
    assert result.source_byte_count == len(raw)
    assert result.profile_reviewed is False
    assert result.unobserved_cell_count == 2 * len(LIS_PROFILE.result_columns)
    assert result.warnings == (
        ImportWarningCode.MAPPING_PROFILE_NOT_BOUND,
        ImportWarningCode.RESULT_COLUMNS_NOT_OBSERVED,
    )
    by_concept = {item.concept: item for item in result.observations}
    assert set(by_concept) == {
        ConceptKind.NAME_TO_USE,
        ConceptKind.PRONOUNS,
        ConceptKind.RECORDED_SEX_OR_GENDER,
    }
    assert by_concept[ConceptKind.NAME_TO_USE].value.to_dict() == {
        "status": "specified",
        "use": "usual",
        "value": "CSYN-ASTER",
    }
    assert by_concept[ConceptKind.PRONOUNS].value.to_dict() == {
        "status": "specified",
        "value": "CSYN-PRONOUN-THEY-THEM",
    }
    assert by_concept[ConceptKind.RECORDED_SEX_OR_GENDER].value.to_dict() == {
        "context": LABORATORY_CONTEXT,
        "source": "urn:contextsafe:unbound-source",
        "value": "X",
    }
    columns = {concept: column for column, concept in _IDENTITY_CONCEPTS.items()}
    for item in result.observations:
        assert item.checkpoint is Checkpoint.LIS_RETURN
        assert item.case_id == "CTP-I01"
        assert item.evidence.source_sha256 == result.source_sha256
        assert item.evidence.source_pointer == f"$.rows[0].{columns[item.concept]}"
        assert (
            item.mapping.source_concept is item.mapping.target_concept is item.concept
        )
        assert item.mapping.mapping_version == LIS_PROFILE.version
    assert [item.observation_id for item in result.observations] == [
        "OBS-CTP-I01-L0000-NTU",
        "OBS-CTP-I01-L0000-PRN",
        "OBS-CTP-I01-L0000-RSG",
    ]
    report = result.to_dict()
    assert report["persisted"] is False
    assert report["profile_reviewed"] is False
    assert report["unobserved_cell_count"] == 14


def test_csv_and_json_reference_exports_agree_on_everything_but_the_source_digest() -> (
    None
):
    """The same table in two formats is the same observation set, modulo digest."""

    csv_result = _convert_reference("lis-export.csv")
    json_result = _convert_reference("lis-export.json")
    strip = lambda item: {  # noqa: E731
        key: value for key, value in item.to_dict().items() if key != "evidence"
    }
    assert [strip(item) for item in csv_result.observations] == [
        strip(item) for item in json_result.observations
    ]
    assert csv_result.source_sha256 != json_result.source_sha256
    assert csv_result.unobserved_cell_count == json_result.unobserved_cell_count


def _convert_reference(name: str) -> Any:
    return import_source(
        _format_for(name),
        REFERENCE / name,
        case=_CASE,
        checkpoint=Checkpoint.LIS_RETURN,
    )


def test_imported_set_evaluates_a_surviving_name_as_pass_and_unbound_tokens_as_fail(
    rules_json: dict[str, Any],
) -> None:
    """A-031 in the small: the name the LIS returned is the name the case holds.

    The name token is the same string on both sides, so that rule passes
    on its own merits. The pronoun token and the laboratory-context sex
    value are not what the case manifest declares, and no profile has said
    they are, so those report ``semantic_mismatch`` and not pass. Against
    the shipped reference rules, which name no ``lis_return`` checkpoint,
    everything stays ``missing_evidence``.
    """

    result = _convert_reference("lis-export.csv")
    bundle = parse_bundle(_CASE_JSON, result.observation_set(), _LIS_RULES)
    by_rule = {item.rule_id: item for item in evaluate(bundle)}
    assert by_rule["A-I01"].status.value == "pass"
    assert by_rule["A-I01"].evidence_sha256s == (result.source_sha256,)
    assert by_rule["A-I02"].reason.value == "semantic_mismatch"
    assert by_rule["A-I03"].reason.value == "semantic_mismatch"

    reference = parse_bundle(_CASE_JSON, result.observation_set(), rules_json)
    assert {item.reason.value for item in evaluate(reference)} == {"missing_evidence"}


# --- accepting fixtures: what the reader admits --------------------------------


@pytest.mark.parametrize(
    ("name", "values", "unobserved"),
    [
        (
            "accept-identity-only.csv",
            [
                ("name_to_use", "CSYN-ASTER", 0),
                ("pronouns", "CSYN-PRONOUN-THEY-THEM", 0),
                ("sex", "X", 0),
            ],
            0,
        ),
        (
            "accept-crlf.csv",
            [
                ("name_to_use", "CSYN-ASTER", 0),
                ("pronouns", "CSYN-PRONOUN-THEY-THEM", 0),
                ("sex", "X", 0),
            ],
            7,
        ),
        (
            "accept-no-final-terminator.csv",
            [
                ("name_to_use", "CSYN-ASTER", 0),
                ("pronouns", "CSYN-PRONOUN-THEY-THEM", 0),
                ("sex", "X", 0),
            ],
            7,
        ),
        (
            "accept-quoted-cells.csv",
            [
                ("name_to_use", "CSYN-ASTER", 0),
                ("pronouns", "CSYN-PRONOUN-THEY-THEM", 0),
            ],
            0,
        ),
        (
            "accept-presence-states.csv",
            [("name_to_use", None, 0), ("pronouns", None, 0), ("sex", "unknown", 0)],
            0,
        ),
        (
            "accept-conflicting-rows.csv",
            [
                ("name_to_use", "CSYN-ASTER", 0),
                ("name_to_use", "CSYN-OTHER", 1),
                ("pronouns", "CSYN-PRONOUN-THEY-THEM", 0),
            ],
            0,
        ),
        ("accept-empty-result-cells.csv", [("name_to_use", "CSYN-ASTER", 0)], 4),
        (
            "accept-identity-only.json",
            [
                ("name_to_use", "CSYN-ASTER", 0),
                ("pronouns", "CSYN-PRONOUN-THEY-THEM", 0),
                ("sex", "X", 0),
            ],
            0,
        ),
        ("accept-conflicting-rows.json", [("sex", "X", 0), ("sex", "F", 1)], 0),
    ],
)
def test_accepting_fixtures_produce_one_observation_per_distinct_value(
    name: str, values: list[tuple[str, str | None, int]], unobserved: int
) -> None:
    result = _convert(name)
    assert [
        (
            item.evidence.source_pointer.rsplit(".", 1)[1],
            item.value.to_dict()["value"],
            int(item.evidence.source_pointer.split("[")[1].split("]")[0]),
        )
        for item in result.observations
    ] == values
    assert result.record_count == len(values)
    assert result.unobserved_cell_count == unobserved
    assert (ImportWarningCode.RESULT_COLUMNS_NOT_OBSERVED in result.warnings) == (
        unobserved > 0
    )
    assert ImportWarningCode.MAPPING_PROFILE_NOT_BOUND in result.warnings
    assert result.profile_reviewed is False


def test_presence_states_carry_no_value_and_are_not_invented() -> None:
    result = _convert("accept-presence-states.csv")
    assert [item.value.to_dict()["status"] for item in result.observations[:2]] == [
        "declined",
        "unknown",
    ]
    assert all(
        item.value.to_dict()["value"] is None for item in result.observations[:2]
    )
    # ``unknown`` in the sex column is an RSG value, not a presence state.
    assert result.observations[2].value.to_dict() == {
        "context": LABORATORY_CONTEXT,
        "source": "urn:contextsafe:unbound-source",
        "value": "unknown",
    }


@pytest.mark.parametrize(
    "name", ["accept-conflicting-rows.csv", "accept-conflicting-rows.json"]
)
def test_rows_that_disagree_evaluate_as_ambiguous_never_pass(name: str) -> None:
    """Two distinct values for one concept are both carried and neither is chosen."""

    result = _convert(name)
    bundle = parse_bundle(_CASE_JSON, result.observation_set(), _LIS_RULES)
    outcomes = {item.concept: item for item in evaluate(bundle)}
    concept = (
        ConceptKind.NAME_TO_USE
        if name.endswith(".csv")
        else ConceptKind.RECORDED_SEX_OR_GENDER
    )
    assert outcomes[concept].status.value == "indeterminate"
    assert outcomes[concept].reason.value == "ambiguous_evidence"
    assert len(outcomes[concept].observed_sha256s) == 2
    assert not any(item.status.value == "pass" for item in outcomes.values())


def test_identical_rows_collapse_to_one_observation_pointed_at_the_first() -> None:
    """A result export repeats the identity per result; that is not ambiguity."""

    result = _convert_reference("lis-export.csv")
    assert result.record_count == 3
    assert all(
        item.evidence.source_pointer.startswith("$.rows[0].")
        for item in result.observations
    )


# --- rejecting fixtures: whole source, code and position, never content --------

_CSV_REJECTIONS: list[tuple[str, str, str]] = [
    ("reject-empty.csv", ImportErrorCode.SOURCE_MALFORMED.value, "$"),
    ("reject-header-only.csv", ImportErrorCode.BOUND_EXCEEDED.value, "$.rows"),
    ("reject-bare-cr.csv", ImportErrorCode.SOURCE_MALFORMED.value, "$"),
    (
        "reject-embedded-newline.csv",
        ImportErrorCode.SOURCE_MALFORMED.value,
        "$.records[1][1]",
    ),
    (
        "reject-bare-quote.csv",
        ImportErrorCode.SOURCE_MALFORMED.value,
        "$.records[1][1]",
    ),
    (
        "reject-text-after-quote.csv",
        ImportErrorCode.SOURCE_MALFORMED.value,
        "$.records[1][1]",
    ),
    ("reject-ragged-row.csv", ImportErrorCode.SOURCE_MALFORMED.value, "$.records[1]"),
    ("reject-blank-line.csv", ImportErrorCode.SOURCE_MALFORMED.value, "$.records[2]"),
    (
        "reject-cell-too-long.csv",
        ImportErrorCode.BOUND_EXCEEDED.value,
        "$.records[1][1]",
    ),
    ("reject-too-wide.csv", ImportErrorCode.BOUND_EXCEEDED.value, "$.records[0][11]"),
    ("reject-bom.csv", ImportErrorCode.COLUMN_UNKNOWN.value, "$.header[0]"),
    ("reject-unknown-column.csv", ImportErrorCode.COLUMN_UNKNOWN.value, "$.header[2]"),
    ("reject-spcu-column.csv", ImportErrorCode.COLUMN_UNKNOWN.value, "$.header[2]"),
    (
        "reject-case-mismatched-header.csv",
        ImportErrorCode.COLUMN_UNKNOWN.value,
        "$.header[0]",
    ),
    ("reject-duplicate-column.csv", ImportErrorCode.COLUMN_DUPLICATE.value, "$.header"),
    ("reject-missing-patient-id.csv", ImportErrorCode.COLUMN_MISSING.value, "$.header"),
    ("reject-no-identity-column.csv", ImportErrorCode.COLUMN_MISSING.value, "$.header"),
    (
        "reject-formula-equals.csv",
        ImportErrorCode.FORMULA_CELL.value,
        "$.rows[0].name_to_use",
    ),
    ("reject-formula-plus.csv", ImportErrorCode.FORMULA_CELL.value, "$.rows[0].value"),
    ("reject-formula-minus.csv", ImportErrorCode.FORMULA_CELL.value, "$.rows[0].value"),
    ("reject-formula-at.csv", ImportErrorCode.FORMULA_CELL.value, "$.rows[0].analyte"),
    ("reject-boundary-whitespace.csv", "unapproved_free_text", "$.rows[0].name_to_use"),
    ("reject-control-character.csv", "prohibited_unicode", "$.rows[0].name_to_use"),
    ("reject-canary.csv", "phi_canary_detected", "$.rows[0].analyte"),
    ("reject-direct-identifier.csv", "direct_identifier_detected", "$.rows[0].analyte"),
    (
        "reject-record-locator-patient-id.csv",
        "direct_identifier_detected",
        "$.rows[0].patient_id",
    ),
    (
        "reject-non-synthetic-patient-id.csv",
        ImportErrorCode.IDENTIFIER_NOT_SYNTHETIC.value,
        "$.rows[0].patient_id",
    ),
    (
        "reject-empty-patient-id.csv",
        ImportErrorCode.IDENTIFIER_NOT_SYNTHETIC.value,
        "$.rows[0].patient_id",
    ),
    (
        "reject-other-case.csv",
        ImportErrorCode.CASE_MISMATCH.value,
        "$.rows[0].patient_id",
    ),
    (
        "reject-mixed-case-in-row.csv",
        ImportErrorCode.CASE_MISMATCH.value,
        "$.rows[1].patient_id",
    ),
    (
        "reject-non-synthetic-name.csv",
        ImportErrorCode.CONCEPT_NOT_CONVERTIBLE.value,
        "$.rows[0].name_to_use",
    ),
    (
        "reject-sex-code-as-name.csv",
        ImportErrorCode.CONCEPT_NOT_CONVERTIBLE.value,
        "$.rows[0].name_to_use",
    ),
    (
        "reject-empty-identity-cell.csv",
        ImportErrorCode.VALUE_MISSING.value,
        "$.rows[0].pronouns",
    ),
    ("reject-empty-sex.csv", ImportErrorCode.VALUE_MISSING.value, "$.rows[0].sex"),
    (
        "reject-specified-without-value.csv",
        ImportErrorCode.VALUE_AMBIGUOUS.value,
        "$.rows[0].pronouns",
    ),
    (
        "reject-unsupported-sex.csv",
        "invalid_rsg_value",
        "$.observations[0].value.value",
    ),
    ("reject-lowercase-sex.csv", "invalid_rsg_value", "$.observations[0].value.value"),
    (
        "reject-non-synthetic-order.csv",
        ImportErrorCode.IDENTIFIER_NOT_SYNTHETIC.value,
        "$.rows[0].order",
    ),
    (
        "reject-non-synthetic-specimen.csv",
        ImportErrorCode.IDENTIFIER_NOT_SYNTHETIC.value,
        "$.rows[0].specimen",
    ),
    (
        "reject-free-text-result.csv",
        ImportErrorCode.CELL_FREE_TEXT.value,
        "$.rows[0].flag",
    ),
]

_JSON_REJECTIONS: list[tuple[str, str, str]] = [
    ("reject-wrong-schema.json", "unsupported_schema", "$.schema_version"),
    ("reject-top-level-unknown.json", "unknown_field", "$"),
    ("reject-rows-not-array.json", "invalid_type", "$.rows"),
    ("reject-empty-rows.json", ImportErrorCode.BOUND_EXCEEDED.value, "$.rows"),
    ("reject-too-many-rows.json", ImportErrorCode.BOUND_EXCEEDED.value, "$.rows"),
    ("reject-row-not-object.json", "invalid_type", "$.rows[0]"),
    ("reject-unknown-key.json", ImportErrorCode.COLUMN_UNKNOWN.value, "$.rows[0]"),
    (
        "reject-unknown-key-non-string.json",
        ImportErrorCode.COLUMN_UNKNOWN.value,
        "$.rows[0]",
    ),
    ("reject-prohibited-key.json", "prohibited_field", "$.rows[0]"),
    (
        "reject-missing-patient-id.json",
        ImportErrorCode.COLUMN_MISSING.value,
        "$.rows[0]",
    ),
    ("reject-no-identity-key.json", ImportErrorCode.COLUMN_MISSING.value, "$.rows[0]"),
    (
        "reject-inconsistent-key-set.json",
        ImportErrorCode.COLUMN_MISSING.value,
        "$.rows[1]",
    ),
    (
        "reject-later-row-unknown-key.json",
        ImportErrorCode.COLUMN_MISSING.value,
        "$.rows[1]",
    ),
    (
        "reject-non-string-cell.json",
        ImportErrorCode.SOURCE_MALFORMED.value,
        "$.rows[0].value",
    ),
    (
        "reject-null-identity.json",
        ImportErrorCode.SOURCE_MALFORMED.value,
        "$.rows[0].name_to_use",
    ),
    ("reject-formula-cell.json", ImportErrorCode.FORMULA_CELL.value, "$.rows[0].value"),
    ("reject-canary.json", "phi_canary_detected", "$.rows[0].analyte"),
    ("reject-direct-identifier.json", "direct_identifier_detected", "$.rows[0].unit"),
    (
        "reject-non-synthetic-patient-id.json",
        ImportErrorCode.IDENTIFIER_NOT_SYNTHETIC.value,
        "$.rows[0].patient_id",
    ),
    (
        "reject-other-case.json",
        ImportErrorCode.CASE_MISMATCH.value,
        "$.rows[0].patient_id",
    ),
    (
        "reject-empty-identity-cell.json",
        ImportErrorCode.VALUE_MISSING.value,
        "$.rows[0].pronouns",
    ),
    (
        "reject-unsupported-sex.json",
        "invalid_rsg_value",
        "$.observations[0].value.value",
    ),
    (
        "reject-non-synthetic-order.json",
        ImportErrorCode.IDENTIFIER_NOT_SYNTHETIC.value,
        "$.rows[0].order",
    ),
    (
        "reject-free-text-result.json",
        ImportErrorCode.CELL_FREE_TEXT.value,
        "$.rows[0].range",
    ),
]

_REJECTIONS = _CSV_REJECTIONS + _JSON_REJECTIONS

_SUSPECT_FRAGMENTS = (
    "ASTER",
    "Aster",
    "OTHER",
    "ALICE",
    "example.invalid",
    "4471",
    "12345",
    "Z99",
    "female",
    "nonbinary",
    "gender",
    "spcu",
    "legal",
    "exported",
    "MRN",
    "call the lab",
    "see note",
    "2026",
    "SUM",
)
"""Cell and key text the rejecting fixtures carry; none may reach an error."""


@pytest.mark.parametrize(("name", "code", "path"), _REJECTIONS)
def test_rejecting_fixtures_fail_whole_with_a_code_and_a_position(
    name: str, code: str, path: str
) -> None:
    error = _reject(name)
    assert error.code == code
    assert error.path == path
    rendered = json.dumps(error.to_dict())
    assert not any(fragment in rendered for fragment in _SUSPECT_FRAGMENTS)


def test_every_fixture_is_named_by_exactly_one_table_row() -> None:
    """The fixture directory and the tables above are the same set."""

    accepted = {
        "accept-identity-only.csv",
        "accept-crlf.csv",
        "accept-no-final-terminator.csv",
        "accept-quoted-cells.csv",
        "accept-presence-states.csv",
        "accept-conflicting-rows.csv",
        "accept-empty-result-cells.csv",
        "accept-identity-only.json",
        "accept-conflicting-rows.json",
    }
    rejected = {name for name, _code, _path in _REJECTIONS}
    assert len(rejected) == len(_REJECTIONS)
    assert accepted.isdisjoint(rejected)
    assert {path.name for path in FIXTURES.iterdir()} == accepted | rejected


def test_a_header_is_held_to_the_allowlist_before_any_cell_is_read() -> None:
    """An unknown column and a canary in a cell: the column wins, by position."""

    text = "patient_id,name_to_use,legal_name\nCSYN-CTP-I01,CTXSAFE-PHI-CANARY-ALICE,CSYN-LEGAL\n"
    with pytest.raises(ContextSafeError) as raised:
        parse_lis_csv(text)
    assert raised.value.to_dict() == {
        "code": ImportErrorCode.COLUMN_UNKNOWN.value,
        "message": "column is outside the profile allowlist",
        "path": "$.header[2]",
    }


def test_json_unknown_key_is_refused_before_its_non_string_cell_is_typed() -> None:
    """The order the review asked for: allowlist first, cell type second.

    A key outside the profile with a non-string value must be reported as
    an unknown column at the row, never as a malformed cell at a path that
    would have to name the key.
    """

    error = _reject("reject-unknown-key-non-string.json")
    assert error.to_dict() == {
        "code": ImportErrorCode.COLUMN_UNKNOWN.value,
        "message": "column is outside the profile allowlist",
        "path": "$.rows[0]",
    }


# --- the concept boundary ------------------------------------------------------


def test_sex_maps_only_to_recorded_sex_or_gender_and_nothing_reaches_gi_or_spcu() -> (
    None
):
    assert _IDENTITY_CONCEPTS["sex"] is ConceptKind.RECORDED_SEX_OR_GENDER
    assert set(_IDENTITY_CONCEPTS.values()) == {
        ConceptKind.NAME_TO_USE,
        ConceptKind.PRONOUNS,
        ConceptKind.RECORDED_SEX_OR_GENDER,
    }
    assert ConceptKind.GENDER_IDENTITY not in _IDENTITY_CONCEPTS.values()
    assert ConceptKind.SEX_PARAMETER_FOR_CLINICAL_USE not in _IDENTITY_CONCEPTS.values()
    for concept in (
        ConceptKind.GENDER_IDENTITY,
        ConceptKind.SEX_PARAMETER_FOR_CLINICAL_USE,
    ):
        assert concept.value not in LIS_PROFILE.columns
    for name in ("lis-export.csv", "lis-export.json"):
        result = _convert_reference(name)
        assert all(
            item.concept is not ConceptKind.GENDER_IDENTITY
            and item.concept is not ConceptKind.SEX_PARAMETER_FOR_CLINICAL_USE
            for item in result.observations
        )
        rsg = [
            item
            for item in result.observations
            if item.concept is ConceptKind.RECORDED_SEX_OR_GENDER
        ]
        assert [item.value.to_dict()["context"] for item in rsg] == [LABORATORY_CONTEXT]


def test_the_case_document_is_a_cross_check_and_never_a_source_of_values() -> None:
    """A different case document with the same identifier changes nothing observed."""

    other = copy.deepcopy(_CASE_JSON)
    other["concepts"]["name_to_use"]["value"] = "CSYN-SOMEONE-ELSE"
    result = _convert("accept-identity-only.csv", parse_case(other))
    assert result.observations[0].value.to_dict()["value"] == "CSYN-ASTER"


def test_the_profile_refuses_to_be_reviewed_and_result_columns_stay_unobserved() -> (
    None
):
    assert LIS_PROFILE.profile_reviewed is False
    with pytest.raises(ContextSafeError) as raised:
        LisProfile(
            version=LIS_PROFILE.version,
            case_column=LIS_PROFILE.case_column,
            identity_columns=LIS_PROFILE.identity_columns,
            result_columns=LIS_PROFILE.result_columns,
            identifier_columns=LIS_PROFILE.identifier_columns,
            max_rows=LIS_PROFILE.max_rows,
            max_cell_length=LIS_PROFILE.max_cell_length,
            profile_reviewed=True,
        )
    assert raised.value.code == "profile_review_not_available"
    with pytest.raises(ContextSafeError) as raised:
        LisProfile(
            version="0.1.0",
            case_column="patient_id",
            identity_columns=("sex",),
            result_columns=("analyte",),
            identifier_columns=("order",),
            max_rows=1,
            max_cell_length=1,
        )
    assert raised.value.code == "profile_columns_inconsistent"
    assert set(LIS_PROFILE.identifier_columns) <= set(LIS_PROFILE.result_columns)
    assert set(LIS_PROFILE.result_columns).isdisjoint(_IDENTITY_CONCEPTS)
    assert len(LIS_PROFILE.columns) == len(set(LIS_PROFILE.columns)) == 11
    with pytest.raises((AttributeError, TypeError)):
        LIS_PROFILE.profile_reviewed = True  # type: ignore[misc]


@pytest.mark.parametrize(
    "checkpoint", [item for item in Checkpoint if item is not Checkpoint.LIS_RETURN]
)
@pytest.mark.parametrize("name", ["lis-export.csv", "lis-export.json"])
def test_any_checkpoint_but_lis_return_rejects_before_the_source_is_opened(
    checkpoint: Checkpoint, name: str, tmp_path: Path
) -> None:
    absent = tmp_path / name
    with pytest.raises(ContextSafeError) as raised:
        import_source(_format_for(name), absent, case=_CASE, checkpoint=checkpoint)
    assert raised.value.code == ImportErrorCode.CHECKPOINT_MISMATCH.value
    assert raised.value.path == "$.checkpoint"
    with pytest.raises(ContextSafeError) as raised:
        convert_table(
            LisTable(columns=("patient_id", "sex"), rows=(("CSYN-CTP-I01", "X"),)),
            format_name=LIS_CSV_FORMAT,
            case=_CASE,
            checkpoint=checkpoint,
            source_sha256="0" * 64,
            source_byte_count=0,
        )
    assert raised.value.code == ImportErrorCode.CHECKPOINT_MISMATCH.value


# --- the read path -------------------------------------------------------------


@pytest.mark.parametrize("name", ["lis-export.csv", "lis-export.json"])
def test_oversized_symlinked_and_unsupported_platform_sources_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    large = tmp_path / f"large{Path(name).suffix}"
    large.write_bytes(b" " * (MAX_EVIDENCE_BYTES + 1))
    with pytest.raises(ContextSafeError) as raised:
        import_source(
            _format_for(name), large, case=_CASE, checkpoint=Checkpoint.LIS_RETURN
        )
    assert raised.value.code == "input_too_large"

    link = tmp_path / f"link{Path(name).suffix}"
    link.symlink_to(REFERENCE / name)
    with pytest.raises(ContextSafeError) as raised:
        import_source(
            _format_for(name), link, case=_CASE, checkpoint=Checkpoint.LIS_RETURN
        )
    assert raised.value.code == "input_path_unsafe"

    directory = tmp_path / "directory"
    directory.mkdir()
    with pytest.raises(ContextSafeError) as raised:
        import_source(
            _format_for(name), directory, case=_CASE, checkpoint=Checkpoint.LIS_RETURN
        )
    assert raised.value.code in {"input_path_unsafe", "input_io_error"}

    monkeypatch.setattr(preflight_module, "_NOFOLLOW", 0)
    with pytest.raises(ContextSafeError) as raised:
        import_source(
            _format_for(name),
            REFERENCE / name,
            case=_CASE,
            checkpoint=Checkpoint.LIS_RETURN,
        )
    assert raised.value.code == "input_path_unsupported"


def test_a_json_cell_over_the_length_bound_rejects_by_row_and_column() -> None:
    """The CSV grammar bounds a field first; a JSON cell reaches the profile's bound."""

    document = {
        "schema_version": LIS_EXPORT_SCHEMA_VERSION,
        "rows": [
            {
                "patient_id": "CSYN-CTP-I01",
                "name_to_use": "CSYN-" + "A" * LIS_PROFILE.max_cell_length,
            }
        ],
    }
    with pytest.raises(ContextSafeError) as raised:
        _convert_any(parse_lis_json(document))
    assert raised.value.to_dict() == {
        "code": ImportErrorCode.BOUND_EXCEEDED.value,
        "message": "cell length exceeds the bound",
        "path": "$.rows[0].name_to_use",
    }


def test_bytes_that_are_not_utf8_reject_before_any_record_is_read(
    tmp_path: Path,
) -> None:
    """Built here rather than shipped: a file no gate can read is not a fixture.

    The repository's hygiene and publication gates refuse to vouch for a
    tracked file they cannot decode, and they are right to, so the one
    input this reader refuses for its encoding is written at test time.
    """

    source = tmp_path / "latin1.csv"
    source.write_bytes(b"patient_id,name_to_use\nCSYN-CTP-I01,CSYN-AS\xffTER\n")
    with pytest.raises(ContextSafeError) as raised:
        import_source(
            LIS_CSV_FORMAT, source, case=_CASE, checkpoint=Checkpoint.LIS_RETURN
        )
    assert raised.value.to_dict() == {
        "code": "invalid_utf8",
        "message": "input must be UTF-8",
        "path": "$",
    }


def test_read_source_closes_its_descriptor_on_success_and_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_open = os.open
    opened: list[int] = []

    def recording_open(*args: Any, **kwargs: Any) -> int:
        descriptor = original_open(*args, **kwargs)
        opened.append(descriptor)
        return descriptor

    monkeypatch.setattr(preflight_module.os, "open", recording_open)
    source = REFERENCE / "lis-export.csv"
    raw = preflight_module.read_source(source)
    assert raw.raw == source.read_bytes()
    assert raw.raw_sha256 == hashlib.sha256(raw.raw).hexdigest()

    fifo = tmp_path / "fifo"
    os.mkfifo(fifo)
    with pytest.raises(ContextSafeError) as raised:
        preflight_module.read_source(fifo)
    assert raised.value.code == "input_path_unsafe"
    assert len(opened) == 2
    for descriptor in opened:
        with pytest.raises(OSError):
            os.fstat(descriptor)


# --- the command line ---------------------------------------------------------


@pytest.mark.parametrize("name", ["lis-export.csv", "lis-export.json"])
def test_cli_import_is_read_only_honours_output_quiet_and_log_dir(
    tmp_path: Path,
    name: str,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    source = tmp_path / name
    source.write_bytes((REFERENCE / name).read_bytes())
    case_path = tmp_path / "case.json"
    case_path.write_bytes((REFERENCE / "case.json").read_bytes())
    before = source.read_bytes()
    argv = [
        "import",
        "--format",
        _format_for(name),
        "--source",
        str(source),
        "--case",
        str(case_path),
        "--checkpoint",
        "lis_return",
    ]

    assert main([*argv, "--no-color"]) == EXIT_SUCCESS
    captured = capsys.readouterr()
    assert captured.err == ""
    assert "\x1b" not in captured.out
    document = json.loads(captured.out)
    assert document["schema_version"] == "contextsafe.observation-set/0.1.0"
    assert [item["concept"] for item in document["observations"]] == [
        "name_to_use",
        "pronouns",
        "recorded_sex_or_gender",
    ]
    assert {item.name for item in tmp_path.iterdir()} == {name, "case.json"}
    assert source.read_bytes() == before

    output = tmp_path / "observations.json"
    log_dir = tmp_path / "log"
    assert (
        main([*argv, "--quiet", "--output", str(output), "--log-dir", str(log_dir)])
        == EXIT_SUCCESS
    )
    quiet = capsys.readouterr()
    assert quiet.out == "" and quiet.err == ""
    assert output.read_bytes() == captured.out.encode("utf-8")
    assert captured.out.endswith("\n") and captured.out.count("\n") == 1
    records = [
        json.loads(line)
        for path in log_dir.iterdir()
        for line in path.read_text(encoding="utf-8").splitlines()
    ]
    assert len(records) == 1
    assert records[0]["command"] == "import"
    assert records[0]["outcome"] == "accepted"
    assert "CSYN" not in json.dumps(records)

    assert (
        main(
            [
                "evaluate",
                "--case",
                str(case_path),
                "--observations",
                str(output),
                "--rules",
                str(REFERENCE / "rules.json"),
            ]
        )
        == EXIT_SUCCESS
    )
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["payload"]["summary"]["indeterminate"] == 5
    assert receipt["payload"]["summary"]["pass"] == 0


@pytest.mark.parametrize(
    "name",
    [
        "reject-non-synthetic-name.csv",
        "reject-canary.csv",
        "reject-unknown-key.json",
        "reject-free-text-result.json",
    ],
)
def test_cli_rejection_is_one_json_error_without_source_content(
    tmp_path: Path, name: str, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "observations.json"
    assert (
        main([*_import_args(name, REFERENCE / "case.json"), "--output", str(output)])
        == EXIT_CONTRACT_ERROR
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    error = json.loads(captured.err)["error"]
    assert set(error) == {"code", "message", "path"}
    assert not any(fragment in captured.err for fragment in _SUSPECT_FRAGMENTS)
    assert str(tmp_path) not in captured.err
    assert str(FIXTURES) not in captured.err
    assert not output.exists()


def test_cli_wrong_checkpoint_rejects_with_the_import_family(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert (
        main(_import_args("accept-identity-only.csv", REFERENCE / "case.json", "ehr"))
        == EXIT_CONTRACT_ERROR
    )
    assert json.loads(capsys.readouterr().err)["error"]["code"] == (
        ImportErrorCode.CHECKPOINT_MISMATCH.value
    )


def test_both_formats_are_registered_and_share_one_profile_version() -> None:
    assert set(FORMATS) <= set(available_formats())
    for name in FORMATS:
        assert REGISTRY[name].format_name == name
        assert REGISTRY[name].mapping_version == LIS_PROFILE.version


# --- the CSV grammar -----------------------------------------------------------

_BOUNDS = CsvBounds(max_records=4, max_fields=3, max_field_length=8)


@pytest.mark.parametrize(
    ("text", "records"),
    [
        ("a,b\n1,2\n", (("a", "b"), ("1", "2"))),
        ("a,b\r\n1,2", (("a", "b"), ("1", "2"))),
        ('a,b\n"1,1","2""2"\n', (("a", "b"), ("1,1", '2"2'))),
        ("a,b\n,\n", (("a", "b"), ("", ""))),
        ('a,b\n"",""\n', (("a", "b"), ("", ""))),
        ("a\n\n", (("a",), ("",))),
    ],
)
def test_csv_subset_accepts_exactly_what_it_says(
    text: str, records: tuple[tuple[str, ...], ...]
) -> None:
    assert parse_csv(text, bounds=_BOUNDS) == records


@pytest.mark.parametrize(
    ("text", "code", "path"),
    [
        ("", ImportErrorCode.SOURCE_MALFORMED.value, "$"),
        ("a,b\r1,2", ImportErrorCode.SOURCE_MALFORMED.value, "$"),
        ('a,b\n"1\n2",3\n', ImportErrorCode.SOURCE_MALFORMED.value, "$.records[1][0]"),
        ('a,b\n1,2"\n', ImportErrorCode.SOURCE_MALFORMED.value, "$.records[1][1]"),
        ('a,b\n"1"2,3\n', ImportErrorCode.SOURCE_MALFORMED.value, "$.records[1][0]"),
        ("a,b\n1\n", ImportErrorCode.SOURCE_MALFORMED.value, "$.records[1]"),
        ("a,b\n1,2,3\n", ImportErrorCode.SOURCE_MALFORMED.value, "$.records[1]"),
        ("a,b,c,d\n", ImportErrorCode.BOUND_EXCEEDED.value, "$.records[0][3]"),
        ("a\n1\n2\n3\n4\n", ImportErrorCode.BOUND_EXCEEDED.value, "$.records"),
        ("a\n123456789\n", ImportErrorCode.BOUND_EXCEEDED.value, "$.records[1][0]"),
    ],
)
def test_csv_subset_refuses_every_leniency_by_position(
    text: str, code: str, path: str
) -> None:
    with pytest.raises(ContextSafeError) as raised:
        parse_csv(text, bounds=_BOUNDS)
    assert raised.value.code == code
    assert raised.value.path == path


_FIELD = st.text(
    alphabet=st.characters(exclude_categories=("Cs",), exclude_characters="\r\n"),
    max_size=8,
)


def _quote(field: str) -> str:
    return '"' + field.replace('"', '""') + '"'


@settings(max_examples=200, deadline=None)
@example(rows=[["", ""], ['"', ',"']])
@given(rows=st.lists(st.lists(_FIELD, min_size=2, max_size=2), min_size=1, max_size=3))
def test_csv_quoting_round_trips_any_line_break_free_text(
    rows: list[list[str]],
) -> None:
    """Quoted, every field survives; the grammar never invents or drops a cell."""

    text = "\n".join(",".join(_quote(field) for field in row) for row in rows) + "\n"
    assert parse_csv(text, bounds=CsvBounds(3, 2, 8)) == tuple(
        tuple(row) for row in rows
    )


# --- properties over the profile -----------------------------------------------

_TOKEN_SUFFIX = st.text(alphabet="ABCDEFGH0123456789", min_size=1, max_size=6)
_PRESENCE_OR_TOKEN = st.one_of(
    st.sampled_from(("declined", "unknown", "absent")),
    _TOKEN_SUFFIX.map(lambda s: f"CSYN-VAL-{s}"),
)
_SEX = st.sampled_from(("F", "M", "X", "unknown"))
_RESULT = st.one_of(
    st.just(""), st.sampled_from(("4.1", "mmol/L", "3.5-5.5", "H", "<0.5"))
)
_IDENTIFIER = st.one_of(st.just(""), _TOKEN_SUFFIX.map(lambda s: f"ORDER-CSYN-{s}"))


@st.composite
def _tables(draw: st.DrawFn) -> LisTable:
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
    columns = tuple(
        column
        for column in LIS_PROFILE.columns
        if column == LIS_PROFILE.case_column or column in identity or column in result
    )
    strategies = {
        "patient_id": st.just("CSYN-CTP-I01"),
        "name_to_use": _PRESENCE_OR_TOKEN,
        "pronouns": _PRESENCE_OR_TOKEN,
        "sex": _SEX,
        "order": _IDENTIFIER,
        "specimen": _IDENTIFIER,
    }
    row_count = draw(st.integers(min_value=1, max_value=5))
    rows = tuple(
        tuple(draw(strategies.get(column, _RESULT)) for column in columns)
        for _ in range(row_count)
    )
    return LisTable(columns=columns, rows=rows)


def _csv_text(table: LisTable) -> str:
    return "\n".join(",".join(row) for row in (table.columns, *table.rows)) + "\n"


def _json_document(table: LisTable) -> dict[str, Any]:
    return {
        "schema_version": LIS_EXPORT_SCHEMA_VERSION,
        "rows": [dict(zip(table.columns, row, strict=True)) for row in table.rows],
    }


def _convert_any(table: LisTable) -> Any:
    return convert_table(
        table,
        format_name=LIS_CSV_FORMAT,
        case=_CASE,
        checkpoint=Checkpoint.LIS_RETURN,
        source_sha256="0" * 64,
        source_byte_count=0,
    )


@settings(max_examples=150, deadline=None)
@given(table=_tables())
def test_both_readers_agree_and_the_conversion_is_deterministic(
    table: LisTable,
) -> None:
    """CSV and JSON of one table read to one table, and convert to one document."""

    assert parse_lis_csv(_csv_text(table)) == table
    assert parse_lis_json(_json_document(table)) == table
    first = _convert_any(table)
    second = _convert_any(copy.deepcopy(table))
    assert canonical_json(first.observation_set()) == canonical_json(
        second.observation_set()
    )
    assert first.to_dict() == second.to_dict()
    distinct = sum(
        len({row[index] for row in table.rows})
        for index, column in enumerate(table.columns)
        if column in LIS_PROFILE.identity_columns
    )
    assert first.record_count == distinct
    assert first.unobserved_cell_count == len(table.rows) * sum(
        column in LIS_PROFILE.result_columns for column in table.columns
    )
    assert all(item.checkpoint is Checkpoint.LIS_RETURN for item in first.observations)
    assert all(
        item.concept
        in {
            ConceptKind.NAME_TO_USE,
            ConceptKind.PRONOUNS,
            ConceptKind.RECORDED_SEX_OR_GENDER,
        }
        for item in first.observations
    )


_COLUMN_UNKNOWN = {
    "code": ImportErrorCode.COLUMN_UNKNOWN.value,
    "message": "column is outside the profile allowlist",
}


@settings(max_examples=150, deadline=None)
@example(
    table=LisTable(("patient_id", "sex"), (("CSYN-CTP-I01", "X"),)),
    position=0,
    column="Sex",
)
@example(
    table=LisTable(("patient_id", "sex"), (("CSYN-CTP-I01", "X"),)),
    position=2,
    column="gender_identity",
)
@example(
    table=LisTable(("patient_id", "sex"), (("CSYN-CTP-I01", "X"),)),
    position=1,
    column=" ",
)
@given(
    table=_tables(),
    position=st.integers(min_value=0, max_value=11),
    column=st.text(min_size=1, max_size=16).filter(
        lambda s: (
            s not in LIS_PROFILE.columns
            and "\n" not in s
            and "\r" not in s
            and "," not in s
            and '"' not in s
        )
    ),
)
def test_any_unknown_column_rejects_the_whole_table_in_both_formats(
    table: LisTable, position: int, column: str
) -> None:
    index = min(position, len(table.columns))
    columns = (*table.columns[:index], column, *table.columns[index:])
    rows = tuple((*row[:index], "CSYN-X", *row[index:]) for row in table.rows)
    with pytest.raises(ContextSafeError) as raised:
        parse_lis_csv(_csv_text(LisTable(columns, rows)))
    # Structural, not substring: the whole error object is fixed text plus a
    # position, so the drawn column name cannot be in it. A table that already
    # carries every profile column overruns the width bound first, which is
    # the earlier of the two refusals and names the position all the same.
    expected = {**_COLUMN_UNKNOWN, "path": f"$.header[{index}]"}
    if len(columns) > len(LIS_PROFILE.columns):
        expected = {
            "code": ImportErrorCode.BOUND_EXCEEDED.value,
            "message": "field count exceeds the bound",
            "path": f"$.records[0][{len(LIS_PROFILE.columns)}]",
        }
    assert raised.value.to_dict() == expected
    with pytest.raises(ContextSafeError) as raised:
        parse_lis_json(_json_document(LisTable(columns, rows)))
    assert raised.value.to_dict() == {**_COLUMN_UNKNOWN, "path": "$.rows[0]"}


_FORMULA_MESSAGE = "a cell may not begin with a character a spreadsheet would execute"
_IDENTIFIER_REJECTIONS = (
    {
        "code": ImportErrorCode.IDENTIFIER_NOT_SYNTHETIC.value,
        "message": "the case identifier must be a synthetic case token",
    },
    {
        "code": ImportErrorCode.CASE_MISMATCH.value,
        "message": "the row's case identifier must match the case document",
    },
    {"code": ImportErrorCode.FORMULA_CELL.value, "message": _FORMULA_MESSAGE},
    {
        "code": "direct_identifier_detected",
        "message": "a direct-identifier pattern was detected",
    },
)
"""Every error object a rejected case identifier may produce (closed).

Fixed sentences at the identifier's own path, so membership proves the
drawn identifier is not in the rejection. A leading hyphen is a formula
prefix and a locator or long digit run trips a boundary detector, both
before the identifier grammar is consulted.
"""


@settings(max_examples=150, deadline=None)
@example(
    table=LisTable(("patient_id", "sex"), (("CSYN-CTP-I01", "X"),)),
    row=0,
    identifier="CSYN-CTP-Z99",
)
@example(
    table=LisTable(("patient_id", "sex"), (("CSYN-CTP-I01", "X"),)),
    row=0,
    identifier="CTP-I01",
)
@example(
    table=LisTable(("patient_id", "sex"), (("CSYN-CTP-I01", "X"),)),
    row=0,
    identifier="",
)
@given(
    table=_tables(),
    row=st.integers(min_value=0, max_value=4),
    identifier=st.text(
        alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-", max_size=20
    ).filter(lambda s: s != "CSYN-CTP-I01"),
)
def test_any_non_synthetic_or_foreign_case_identifier_rejects_the_whole_table(
    table: LisTable, row: int, identifier: str
) -> None:
    index = min(row, len(table.rows) - 1)
    rows = list(table.rows)
    rows[index] = (identifier, *rows[index][1:])
    with pytest.raises(ContextSafeError) as raised:
        _convert_any(LisTable(table.columns, tuple(rows)))
    path = f"$.rows[{index}].patient_id"
    assert raised.value.to_dict() in tuple(
        {**item, "path": path} for item in _IDENTIFIER_REJECTIONS
    )


@settings(max_examples=100, deadline=None)
@given(
    table=_tables(),
    row=st.integers(min_value=0, max_value=4),
    column=st.integers(min_value=0, max_value=10),
    prefix=st.sampled_from(sorted(FORMULA_PREFIXES)),
)
def test_a_formula_prefix_in_any_cell_rejects_the_whole_table(
    table: LisTable, row: int, column: int, prefix: str
) -> None:
    row_index = min(row, len(table.rows) - 1)
    column_index = min(column, len(table.columns) - 1)
    rows = list(table.rows)
    cells = list(rows[row_index])
    cells[column_index] = prefix + cells[column_index]
    rows[row_index] = tuple(cells)
    with pytest.raises(ContextSafeError) as raised:
        _convert_any(LisTable(table.columns, tuple(rows)))
    assert raised.value.to_dict() == {
        "code": ImportErrorCode.FORMULA_CELL.value,
        "message": _FORMULA_MESSAGE,
        "path": f"$.rows[{row_index}].{table.columns[column_index]}",
    }
