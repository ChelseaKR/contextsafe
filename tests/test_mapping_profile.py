"""The versioned mapping profile and its application (B-026).

What this module pins. A profile is validated whole against the importer
registry's own carrier table, and every prohibited row class rejects with a
code and a location and never a token: a row reaching sex parameter for
clinical use from gender identity or recorded sex or gender (A-020, A-021),
any other cross-concept row, two rows that would collapse two source values
into one target, a duplicate source, a target outside the synthetic grammar,
a review status other than ``not_reviewed``, a carrier the importer does not
read or reads as another concept. Applying a profile binds exactly the
matched tokens, leaves unmatched ones verbatim and says so, never changes an
observation's concept or the number of observations, binds only the value of
a sex parameter for clinical use, and stamps every observation with the
profile's digest and version so the evaluator's input hash covers it. The
reference profiles make import followed by evaluate pass for every rule at
the imported checkpoint, and the command line honours the shared flags.
"""

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from contextsafe.canonical import canonical_json, sha256_json
from contextsafe.cli import EXIT_CONTRACT_ERROR, EXIT_SUCCESS, _conversion_command, main
from contextsafe.errors import ContextSafeError
from contextsafe.evaluator import evaluate
from contextsafe.importers import (
    ImportResult,
    ImportWarningCode,
    apply_profile,
    carrier_table,
    compile_profile,
    import_source,
    load_profile,
)
from contextsafe.importers.canonical_json import convert_scanned
from contextsafe.importers.fhir_r4_json import FHIR_R4_PROFILE, NAME_CARRIER
from contextsafe.importers.mapping import _bind
from contextsafe.jsonio import parse_json_bytes
from contextsafe.mapping_profile import (
    COMPILED_LIMITATIONS,
    MAX_ROWS,
    PRONOUN_SET_PATTERN,
    SYNTHETIC_TOKEN_PATTERN,
    MappingProfile,
    SourceToken,
    SpcuValueBinding,
)
from contextsafe.models import (
    Checkpoint,
    ConceptKind,
    MappingDescriptor,
    OutcomeReason,
    OutcomeStatus,
    Pronouns,
    SyntheticCase,
    ValueStatus,
)
from contextsafe.preflight import ScannedSource
from contextsafe.reference_fixtures import REFERENCE_ROOT
from contextsafe.validation import parse_bundle, parse_case, parse_observations

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = REFERENCE_ROOT
FIXTURES = ROOT / "tests" / "fixtures" / "mapping"
FORMATS: dict[str, tuple[str, str]] = {
    "canonical-json": ("evidence-source.json", "ehr"),
    "fhir-r4-json": ("fhir-patient.json", "ehr"),
    "hl7v2-er7": ("hl7v2-er7-message.hl7", "ehr"),
    "lis-csv": ("lis-export.csv", "lis_return"),
    "lis-json": ("lis-export.json", "lis_return"),
}
"""Each registered format, its reference source, and the checkpoint it is for."""

REJECTIONS: dict[str, tuple[str, str]] = {
    "reject-gi-to-spcu.json": ("prohibited_spcu_mapping", "$.rows[0].target"),
    "reject-rsg-to-spcu.json": ("prohibited_spcu_mapping", "$.rows[0].target"),
    "reject-cross-concept.json": ("concept_type_mismatch", "$.rows[0].target"),
    "reject-collapse.json": (
        "mapping_profile_target_collapses_sources",
        "$.rows[1].target",
    ),
    "reject-duplicate-source.json": (
        "mapping_profile_source_duplicate",
        "$.rows[1].source",
    ),
    "reject-target-not-synthetic.json": (
        "mapping_profile_target_not_synthetic",
        "$.rows[0].target.value.value",
    ),
    "reject-target-system-not-synthetic.json": (
        "mapping_profile_target_not_synthetic",
        "$.rows[0].target.value.code_system",
    ),
    "reject-review-approved.json": (
        "mapping_profile_review_not_available",
        "$.review.status",
    ),
    "reject-review-named.json": (
        "mapping_profile_review_not_available",
        "$.review.reviewed_by",
    ),
    "reject-carrier-unknown.json": (
        "mapping_profile_carrier_unknown",
        "$.rows[0].source.carrier",
    ),
    "reject-carrier-concept-mismatch.json": (
        "mapping_profile_carrier_concept_mismatch",
        "$.rows[0].source.concept",
    ),
    "reject-format-unknown.json": ("mapping_profile_format_unsupported", "$.format"),
    "reject-spcu-binds-context.json": ("unknown_field", "$.rows[0].target.value"),
    "reject-token-free-text.json": ("invalid_format", "$.rows[0].source.token"),
    "reject-unknown-field.json": ("unknown_field", "$"),
    "reject-empty-rows.json": ("invalid_row_count", "$.rows"),
    "reject-wrong-schema.json": ("unsupported_schema", "$.schema_version"),
}
"""Every committed rejection profile, its code, and its location."""

FIXTURE_CONTENT = (
    "CSYN-PRONOUN-THEY-THEM",
    "CSYN-PRONOUN-SHE-HER",
    "CSYN-GENDER-1",
    "CSYN-ASTER",
    "CSYN-REVIEWER",
    "CSYN-NOBODY",
    "woman",
    "they them please",
    "csv-generic",
    "approved",
    "terminology.example.invalid",
)
"""Strings a rejection fixture carries that may never appear in its error."""


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _reference_profile(format_name: str) -> dict[str, Any]:
    return _read(REFERENCE / f"mapping-{format_name}.json")


def _write(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value, separators=(",", ":")), encoding="utf-8")
    return path


def _import_args(
    format_name: str, mapping: Path | None, checkpoint: str | None = None
) -> list[str]:
    source, default_checkpoint = FORMATS[format_name]
    argv = [
        "import",
        "--format",
        format_name,
        "--source",
        str(REFERENCE / source),
        "--case",
        str(REFERENCE / "case.json"),
        "--checkpoint",
        checkpoint or default_checkpoint,
    ]
    if mapping is not None:
        argv += ["--mapping", str(mapping)]
    return argv


def _rejection(value: object) -> ContextSafeError:
    with pytest.raises(ContextSafeError) as raised:
        load_profile(value)
    return raised.value


@pytest.fixture
def case() -> SyntheticCase:
    return parse_case(_read(REFERENCE / "case.json"))


@pytest.fixture
def rules_json() -> dict[str, Any]:
    return _read(REFERENCE / "rules.json")


@pytest.fixture
def case_json() -> dict[str, Any]:
    return _read(REFERENCE / "case.json")


# --- the profile document ----------------------------------------------------


@pytest.mark.parametrize("format_name", sorted(FORMATS))
def test_every_reference_profile_validates_and_names_its_format(
    format_name: str,
) -> None:
    profile = load_profile(_reference_profile(format_name))
    assert profile.format == format_name
    assert profile.reviewed is False
    assert profile.version == "0.1.0"
    assert len(profile.rows) >= 1
    compiled = compile_profile(_reference_profile(format_name)).to_dict()
    assert compiled["profile_sha256"] == profile.sha256()
    assert compiled["review_status"] == "not_reviewed"
    assert compiled["signature_status"] == "not_verified"
    assert compiled["executable"] is False
    assert compiled["limitations"] == list(COMPILED_LIMITATIONS)
    assert compiled["row_count"] == len(profile.rows)


def test_the_canonical_form_is_independent_of_row_order() -> None:
    document = _reference_profile("hl7v2-er7")
    reordered = copy.deepcopy(document)
    reordered["rows"].reverse()
    assert load_profile(document).sha256() == load_profile(reordered).sha256()
    assert load_profile(document).to_dict() == load_profile(reordered).to_dict()


def test_the_digest_is_the_digest_of_the_canonical_form() -> None:
    profile = load_profile(_reference_profile("fhir-r4-json"))
    assert profile.sha256() == sha256_json(profile.to_dict())
    assert profile.to_dict()["review"] == {
        "reviewed_at": None,
        "reviewed_by": None,
        "status": "not_reviewed",
    }


@pytest.mark.parametrize("name", sorted(REJECTIONS))
def test_every_rejection_fixture_is_refused_by_code_and_location_only(
    name: str,
) -> None:
    """Each prohibited row class has a committed fixture and a pinned rejection."""

    code, path = REJECTIONS[name]
    error = _rejection(_read(FIXTURES / name))
    assert (error.code, error.path) == (code, path), name
    for literal in FIXTURE_CONTENT:
        assert literal not in error.message
        assert literal not in error.path


def test_every_committed_rejection_fixture_is_pinned() -> None:
    assert sorted(path.name for path in FIXTURES.glob("*.json")) == sorted(REJECTIONS)


def test_the_spcu_prohibition_is_checked_before_the_general_rule() -> None:
    """A GI-to-SPCU row is refused by name, whatever else is wrong with it."""

    document = _read(FIXTURES / "reject-gi-to-spcu.json")
    document["rows"][0]["target"]["value"] = {"value": "not synthetic at all"}
    assert _rejection(document).code == "prohibited_spcu_mapping"


def _row_run(row: dict[str, Any], count: int) -> list[dict[str, Any]]:
    """``count`` rows that differ only in their source token and target value."""

    return [
        {
            **row,
            "source": {**row["source"], "token": f"CSYN-P{index:04d}"},
            "target": {
                "concept": "pronouns",
                "value": {"status": "specified", "value": f"CSYN-T{index:04d}"},
            },
        }
        for index in range(count)
    ]


def test_a_row_set_over_the_bound_is_refused() -> None:
    document = _reference_profile("canonical-json")
    document["rows"] = _row_run(document["rows"][0], MAX_ROWS + 1)
    assert _rejection(document).code == "invalid_row_count"


def test_a_row_set_at_the_bound_is_accepted() -> None:
    """The accepting side of the same bound: exactly MAX_ROWS parses.

    Without this, an off-by-one that made the bound exclusive would pass the
    whole suite: the over-bound case above still fails, and nothing else
    stands at the boundary from this side.
    """

    document = _reference_profile("canonical-json")
    document["rows"] = _row_run(document["rows"][0], MAX_ROWS)
    profile = load_profile(document)
    assert len(profile.rows) == MAX_ROWS


def test_a_carrier_the_importer_never_emits_is_not_in_the_table() -> None:
    """A canonical-json row cannot name the field code that never converts.

    The importer refuses a ``sex_parameter_for_clinical_use`` record (the
    envelope carries no supporting-observation link), so it emits no token
    under that carrier and the table does not advertise one. The row is
    refused where a carrier the format does not read is refused.
    """

    document = _reference_profile("canonical-json")
    document["rows"] = [
        {
            "source": {
                "concept": "sex_parameter_for_clinical_use",
                "carrier": "sex_parameter_for_clinical_use",
                "token": "CSYN-CONTEXT-1",
            },
            "target": {
                "concept": "sex_parameter_for_clinical_use",
                "value": {"value": "fixture-context-1"},
            },
        }
    ]
    error = _rejection(document)
    assert error.code == "mapping_profile_carrier_unknown"
    assert error.path == "$.rows[0].source.carrier"


def test_a_doubly_invalid_row_reports_the_prohibition_and_not_the_carrier() -> None:
    """The prohibition is refused ahead of the source checks, not after them.

    This row is wrong twice: ``PID-8`` is never read as gender identity, and
    its target is sex parameter for clinical use from a gender-identity
    source. ``_source`` runs before ``_target``, so until the prohibition
    moved ahead of both this reported ``carrier_concept_mismatch`` -- true,
    and not the sentence a reader who tried the prohibition needed.
    """

    document = _reference_profile("hl7v2-er7")
    document["rows"] = [
        {
            "source": {
                "concept": "gender_identity",
                "carrier": "PID-8",
                "token": "X",
            },
            "target": {
                "concept": "sex_parameter_for_clinical_use",
                "value": {"value": "fixture-context-1"},
            },
        }
    ]
    error = _rejection(document)
    assert (error.code, error.path) == ("prohibited_spcu_mapping", "$.rows[0].target")


@pytest.mark.parametrize(
    ("carrier", "token"),
    [("not-a-carrier", "X"), ("PID-8", "not a token at all")],
)
def test_the_prohibition_outranks_every_other_defect_in_the_same_row(
    carrier: str, token: str
) -> None:
    """Whatever else is wrong with the row, the prohibition is what it says."""

    document = _reference_profile("hl7v2-er7")
    document["rows"] = [
        {
            "source": {
                "concept": "recorded_sex_or_gender",
                "carrier": carrier,
                "token": token,
            },
            "target": {
                "concept": "sex_parameter_for_clinical_use",
                "value": {"value": "fixture-context-1"},
            },
        }
    ]
    assert _rejection(document).code == "prohibited_spcu_mapping"


def test_a_row_half_that_declares_no_concept_is_still_refused_structurally() -> None:
    """The early read decides nothing when it cannot read both concepts."""

    document = _reference_profile("hl7v2-er7")
    document["rows"] = [
        {
            "source": "not an object",
            "target": {
                "concept": "sex_parameter_for_clinical_use",
                "value": {"value": "fixture-context-1"},
            },
        }
    ]
    error = _rejection(document)
    assert (error.code, error.path) == ("invalid_type", "$.rows[0].source")


def test_a_token_that_trips_a_boundary_detector_is_refused_without_echo() -> None:
    document = _reference_profile("canonical-json")
    document["rows"][0]["source"].update({"token": "CSYN-9876543210"})
    error = _rejection(document)
    assert error.code == "direct_identifier_detected"
    assert error.path == "$.rows[0].source.token"
    assert "9876543210" not in error.message


@pytest.mark.parametrize(
    ("concept", "value", "field"),
    [
        (
            "recorded_sex_or_gender",
            {"value": "X", "context": "passport-office", "source": "synthetic-fixture"},
            "context",
        ),
        (
            "recorded_sex_or_gender",
            {"value": "X", "context": "government-id", "source": "registrar"},
            "source",
        ),
        ("pronouns", {"status": "specified", "value": "They/Them"}, "value"),
        ("pronouns", {"status": "specified", "value": "ze/hir/1"}, "value"),
        (
            "name_to_use",
            {"status": "specified", "value": "CSYN-Jordan Rivera", "use": "usual"},
            "value",
        ),
    ],
)
def test_targets_outside_the_synthetic_grammar_are_refused_by_field(
    concept: str, value: dict[str, Any], field: str
) -> None:
    carrier = {
        "recorded_sex_or_gender": "PID-8",
        "pronouns": "GSP-5",
        "name_to_use": "PID-5",
    }[concept]
    document = _reference_profile("hl7v2-er7")
    document["rows"] = [
        {
            "source": {"concept": concept, "carrier": carrier, "token": "X"},
            "target": {"concept": concept, "value": value},
        }
    ]
    error = _rejection(document)
    assert error.code == "mapping_profile_target_not_synthetic"
    assert error.path == f"$.rows[0].target.value.{field}"


@pytest.mark.parametrize(
    ("concept", "value"),
    [
        ("pronouns", {"status": "declined", "value": None}),
        ("pronouns", {"status": "specified", "value": "xe/xem/xyr"}),
        ("pronouns", {"status": "specified", "value": "CSYN-PRONOUN-SET-A"}),
        (
            "gender_identity",
            {"status": "unknown", "value": None, "code_system": "urn:contextsafe:x"},
        ),
        ("name_to_use", {"status": "absent", "value": None, "use": "usual"}),
        (
            "recorded_sex_or_gender",
            {
                "value": "unknown",
                "context": "CSYN-CTX",
                "source": "urn:contextsafe:lis",
            },
        ),
    ],
)
def test_presence_states_and_synthetic_shapes_are_admitted_as_targets(
    concept: str, value: dict[str, Any]
) -> None:
    carrier = {
        "pronouns": "GSP-5",
        "gender_identity": "GSP-5",
        "name_to_use": "PID-5",
        "recorded_sex_or_gender": "PID-8",
    }[concept]
    document = _reference_profile("hl7v2-er7")
    document["rows"] = [
        {
            "source": {"concept": concept, "carrier": carrier, "token": "declined"},
            "target": {"concept": concept, "value": value},
        }
    ]
    assert len(load_profile(document).rows) == 1


def test_the_profile_type_refuses_to_be_reviewed() -> None:
    profile = load_profile(_reference_profile("canonical-json"))
    with pytest.raises(ContextSafeError) as raised:
        MappingProfile(
            schema_version=profile.schema_version,
            profile_id=profile.profile_id,
            format=profile.format,
            version=profile.version,
            rows=profile.rows,
            reviewed=True,
        )
    assert raised.value.code == "mapping_profile_review_not_available"


def test_the_carrier_table_is_the_registry_and_pid8_is_only_rsg() -> None:
    table = carrier_table()
    assert set(table) == set(FORMATS)
    assert table["hl7v2-er7"]["PID-8"] == frozenset(
        {ConceptKind.RECORDED_SEX_OR_GENDER}
    )
    assert table["lis-csv"]["sex"] == frozenset({ConceptKind.RECORDED_SEX_OR_GENDER})
    assert table["fhir-r4-json"][NAME_CARRIER] == frozenset({ConceptKind.NAME_TO_USE})
    assert FHIR_R4_PROFILE.sex_parameter_url not in table["fhir-r4-json"]
    assert "sex_parameter_for_clinical_use" not in table["canonical-json"]
    for carriers in table.values():
        for admitted in carriers.values():
            assert admitted


# --- applying a profile -------------------------------------------------------


@pytest.mark.parametrize("format_name", sorted(FORMATS))
def test_applying_the_reference_profile_binds_every_token_and_stamps_the_digest(
    format_name: str, case: SyntheticCase
) -> None:
    source, checkpoint = FORMATS[format_name]
    profile = load_profile(_reference_profile(format_name))
    verbatim = import_source(
        format_name, REFERENCE / source, case=case, checkpoint=Checkpoint(checkpoint)
    )
    bound = import_source(
        format_name,
        REFERENCE / source,
        case=case,
        checkpoint=Checkpoint(checkpoint),
        profile=profile,
    )
    assert len(bound.observations) == len(verbatim.observations)
    assert [item.concept for item in bound.observations] == [
        item.concept for item in verbatim.observations
    ]
    assert [item.observation_id for item in bound.observations] == [
        item.observation_id for item in verbatim.observations
    ]
    assert bound.source_tokens == verbatim.source_tokens
    assert ImportWarningCode.MAPPING_PROFILE_NOT_BOUND in verbatim.warnings
    assert ImportWarningCode.MAPPING_PROFILE_NOT_BOUND not in bound.warnings
    assert ImportWarningCode.MAPPING_PROFILE_ROW_UNMATCHED not in bound.warnings
    assert bound.profile_reviewed is False
    assert bound.profile_sha256 == profile.sha256()
    assert bound.profile_version == profile.version
    assert verbatim.profile_sha256 is None
    for item in bound.observations:
        assert item.mapping.profile_sha256 == profile.sha256()
        assert item.mapping.profile_version == profile.version
        assert item.mapping.source_concept is item.concept
        assert item.mapping.target_concept is item.concept
    for item in verbatim.observations:
        assert item.mapping.profile_sha256 is None
        assert "profile_sha256" not in item.mapping.to_dict()
    assert bound.to_dict()["profile_sha256"] == profile.sha256()


@pytest.mark.parametrize(
    ("format_name", "checkpoint", "expected"),
    [
        ("canonical-json", "ehr", {"A-I05"}),
        ("fhir-r4-json", "ehr", {"A-I01", "A-I04", "A-I05"}),
        ("fhir-r4-json", "registration", {"A-I02"}),
        ("hl7v2-er7", "ehr", {"A-I01", "A-I04", "A-I05"}),
        ("hl7v2-er7", "registration", {"A-I02"}),
        ("hl7v2-er7", "interface", {"A-I03"}),
        ("lis-csv", "lis_return", set()),
        ("lis-json", "lis_return", set()),
    ],
)
def test_import_with_the_reference_profile_then_evaluate_passes_at_the_checkpoint(
    format_name: str,
    checkpoint: str,
    expected: set[str],
    case_json: dict[str, Any],
    rules_json: dict[str, Any],
    case: SyntheticCase,
) -> None:
    """Every rule at the imported checkpoint passes; every other is missing.

    No rule reports ``semantic_mismatch`` once the profile has bound the
    tokens, and no rule at another checkpoint is answered by evidence that
    was not imported for it. The reference rule set has no rule at
    ``lis_return``, so both LIS imports evaluate to missing evidence only.
    """

    source, _default = FORMATS[format_name]
    result = import_source(
        format_name,
        REFERENCE / source,
        case=case,
        checkpoint=Checkpoint(checkpoint),
        profile=load_profile(_reference_profile(format_name)),
    )
    bundle = parse_bundle(case_json, result.observation_set(), rules_json)
    outcomes = {item.rule_id: item for item in evaluate(bundle)}
    passed = {
        rule_id
        for rule_id, item in outcomes.items()
        if item.status is OutcomeStatus.PASSED
    }
    assert passed == expected
    for rule_id, item in outcomes.items():
        if rule_id not in expected:
            assert item.status is OutcomeStatus.INDETERMINATE
            assert item.reason is OutcomeReason.MISSING_EVIDENCE
    assert all(
        item.reason is not OutcomeReason.SEMANTIC_MISMATCH for item in outcomes.values()
    )


def test_without_a_profile_the_same_import_reports_the_mismatch(
    case_json: dict[str, Any], rules_json: dict[str, Any], case: SyntheticCase
) -> None:
    """The control: the profile is what turns the mismatch into a pass."""

    result = import_source(
        "fhir-r4-json",
        REFERENCE / "fhir-patient.json",
        case=case,
        checkpoint=Checkpoint.EHR,
    )
    bundle = parse_bundle(case_json, result.observation_set(), rules_json)
    outcomes = {item.rule_id: item for item in evaluate(bundle)}
    assert outcomes["A-I01"].reason is OutcomeReason.SEMANTIC_MISMATCH
    assert outcomes["A-I05"].reason is OutcomeReason.SEMANTIC_MISMATCH


def test_an_unmatched_token_stays_verbatim_and_the_result_says_so(
    case: SyntheticCase,
) -> None:
    document = _reference_profile("fhir-r4-json")
    document["rows"] = [
        row for row in document["rows"] if row["source"]["concept"] != "pronouns"
    ]
    result = import_source(
        "fhir-r4-json",
        REFERENCE / "fhir-patient.json",
        case=case,
        checkpoint=Checkpoint.EHR,
        profile=load_profile(document),
    )
    assert ImportWarningCode.MAPPING_PROFILE_ROW_UNMATCHED in result.warnings
    pronouns = [
        item for item in result.observations if item.concept is ConceptKind.PRONOUNS
    ]
    assert len(pronouns) == 1
    assert pronouns[0].value == Pronouns(
        status=ValueStatus.SPECIFIED, value="CSYN-PRONOUN-THEY-THEM"
    )
    assert pronouns[0].mapping.profile_sha256 is not None


def test_an_spcu_row_binds_the_value_and_never_the_order_context(
    case: SyntheticCase,
) -> None:
    document = _reference_profile("hl7v2-er7")
    for row in document["rows"]:
        if row["source"]["concept"] == "sex_parameter_for_clinical_use":
            row["target"]["value"] = {"value": "fixture-context-2"}
    result = import_source(
        "hl7v2-er7",
        REFERENCE / "hl7v2-er7-message.hl7",
        case=case,
        checkpoint=Checkpoint.INTERFACE,
        profile=load_profile(document),
    )
    spcu = [
        item
        for item in result.observations
        if item.concept is ConceptKind.SEX_PARAMETER_FOR_CLINICAL_USE
    ]
    assert len(spcu) == 1
    assert spcu[0].value.to_dict() == {
        "context_id": "ORDER-CSYN-I01-A",
        "supporting_observation_ids": ["SUP-CSYN-I01-A"],
        "value": "fixture-context-2",
    }


def test_a_profile_for_another_format_is_refused_before_anything_is_bound(
    case: SyntheticCase,
) -> None:
    with pytest.raises(ContextSafeError) as raised:
        import_source(
            "fhir-r4-json",
            REFERENCE / "fhir-patient.json",
            case=case,
            checkpoint=Checkpoint.EHR,
            profile=load_profile(_reference_profile("hl7v2-er7")),
        )
    assert raised.value.code == "mapping_profile_format_mismatch"
    assert raised.value.path == "$.format"


def test_a_result_without_source_tokens_cannot_have_a_profile_applied(
    case: SyntheticCase,
) -> None:
    result = import_source(
        "canonical-json",
        REFERENCE / "evidence-source.json",
        case=case,
        checkpoint=Checkpoint.EHR,
    )
    stripped = ImportResult(
        format_name=result.format_name,
        mapping_version=result.mapping_version,
        source_sha256=result.source_sha256,
        source_byte_count=result.source_byte_count,
        record_count=result.record_count,
        observations=result.observations,
        warnings=result.warnings,
    )
    with pytest.raises(ContextSafeError) as raised:
        apply_profile(stripped, load_profile(_reference_profile("canonical-json")))
    assert raised.value.code == "mapping_profile_not_applicable"


def test_a_token_whose_concept_is_not_its_observations_is_refused(
    case: SyntheticCase,
) -> None:
    result = import_source(
        "canonical-json",
        REFERENCE / "evidence-source.json",
        case=case,
        checkpoint=Checkpoint.EHR,
    )
    crossed = ImportResult(
        format_name=result.format_name,
        mapping_version=result.mapping_version,
        source_sha256=result.source_sha256,
        source_byte_count=result.source_byte_count,
        record_count=result.record_count,
        observations=result.observations,
        warnings=result.warnings,
        source_tokens=(SourceToken(ConceptKind.GENDER_IDENTITY, "pronouns", "CSYN-X"),),
    )
    with pytest.raises(ContextSafeError) as raised:
        apply_profile(crossed, load_profile(_reference_profile("canonical-json")))
    assert raised.value.code == "mapping_profile_not_applicable"


def test_a_value_binding_cannot_land_on_a_value_that_is_not_a_sex_parameter() -> None:
    with pytest.raises(ContextSafeError) as raised:
        _bind(
            Pronouns(status=ValueStatus.SPECIFIED, value="they/them"),
            SpcuValueBinding(value="fixture-context-1"),
        )
    assert raised.value.code == "mapping_profile_not_applicable"


def test_two_bound_carriers_of_one_concept_stay_two_and_evaluate_ambiguous(
    tmp_path: Path,
    case: SyntheticCase,
    case_json: dict[str, Any],
    rules_json: dict[str, Any],
) -> None:
    """Ambiguity retention: a profile never lets two source values become one."""

    patient = _read(REFERENCE / "fhir-patient.json")
    gender = copy.deepcopy(patient["extension"][0])
    gender["extension"][0]["valueCodeableConcept"]["coding"][0]["code"] = (
        "CSYN-GENDER-2"
    )
    patient["extension"].append(gender)
    source = _write(tmp_path / "patient.json", patient)
    document = _reference_profile("fhir-r4-json")
    document["rows"].append(
        {
            "source": {
                "concept": "gender_identity",
                "carrier": FHIR_R4_PROFILE.gender_identity_url,
                "token": "CSYN-GENDER-2",
            },
            "target": {
                "concept": "gender_identity",
                "value": {
                    "status": "specified",
                    "value": "fixture-gender-2",
                    "code_system": "urn:contextsafe:fixture",
                },
            },
        }
    )
    result = import_source(
        "fhir-r4-json",
        source,
        case=case,
        checkpoint=Checkpoint.EHR,
        profile=load_profile(document),
    )
    genders = [
        item
        for item in result.observations
        if item.concept is ConceptKind.GENDER_IDENTITY
    ]
    assert len(genders) == 2
    bundle = parse_bundle(case_json, result.observation_set(), rules_json)
    outcomes = {item.rule_id: item for item in evaluate(bundle)}
    assert outcomes["A-I01"].status is OutcomeStatus.INDETERMINATE
    assert outcomes["A-I01"].reason is OutcomeReason.AMBIGUOUS_EVIDENCE


def test_the_same_token_twice_is_still_two_observations_after_binding(
    tmp_path: Path, case: SyntheticCase
) -> None:
    patient = _read(REFERENCE / "fhir-patient.json")
    patient["extension"].append(copy.deepcopy(patient["extension"][0]))
    source = _write(tmp_path / "patient.json", patient)
    result = import_source(
        "fhir-r4-json",
        source,
        case=case,
        checkpoint=Checkpoint.EHR,
        profile=load_profile(_reference_profile("fhir-r4-json")),
    )
    genders = [
        item.value.to_dict()
        for item in result.observations
        if item.concept is ConceptKind.GENDER_IDENTITY
    ]
    assert len(genders) == 2
    assert genders[0] == genders[1]


# --- the binding on the observation contract ---------------------------------


def test_a_profile_binding_carries_both_fields_or_neither(
    case: SyntheticCase,
) -> None:
    with pytest.raises(ContextSafeError) as raised:
        MappingDescriptor(
            source_concept=ConceptKind.PRONOUNS,
            target_concept=ConceptKind.PRONOUNS,
            mapping_version="0.1.0",
            profile_sha256="0" * 64,
        )
    assert raised.value.code == "mapping_profile_binding_incomplete"
    result = import_source(
        "canonical-json",
        REFERENCE / "evidence-source.json",
        case=case,
        checkpoint=Checkpoint.EHR,
        profile=load_profile(_reference_profile("canonical-json")),
    )
    document = result.observation_set()
    observations = document["observations"]
    assert isinstance(observations, list)
    first = observations[0]
    assert isinstance(first, dict)
    mapping = first["mapping"]
    assert isinstance(mapping, dict)
    del mapping["profile_version"]
    with pytest.raises(ContextSafeError) as raised:
        parse_observations(document)
    assert raised.value.code == "mapping_profile_binding_incomplete"
    assert raised.value.path == "$.observations[0].mapping"


def test_the_import_result_refuses_a_partial_binding_or_token_miscount(
    case: SyntheticCase,
) -> None:
    result = import_source(
        "canonical-json",
        REFERENCE / "evidence-source.json",
        case=case,
        checkpoint=Checkpoint.EHR,
    )
    fields = {
        "format_name": result.format_name,
        "mapping_version": result.mapping_version,
        "source_sha256": result.source_sha256,
        "source_byte_count": result.source_byte_count,
        "record_count": result.record_count,
        "observations": result.observations,
        "warnings": result.warnings,
    }
    with pytest.raises(ContextSafeError, match="mapping_profile_binding_incomplete"):
        ImportResult(**fields, profile_sha256="0" * 64)
    with pytest.raises(ContextSafeError, match="import_count_mismatch"):
        ImportResult(
            **fields, source_tokens=(*result.source_tokens, *result.source_tokens)
        )


# --- the command line ---------------------------------------------------------


@pytest.mark.parametrize("format_name", sorted(FORMATS))
def test_cli_import_with_mapping_writes_a_bound_observation_set(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], format_name: str
) -> None:
    output = tmp_path / "observations.json"
    argv = _import_args(format_name, REFERENCE / f"mapping-{format_name}.json")
    assert main([*argv, "--output", str(output)]) == EXIT_SUCCESS
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
    document = json.loads(output.read_text(encoding="utf-8"))
    profile = load_profile(_reference_profile(format_name))
    for item in document["observations"]:
        assert item["mapping"]["profile_sha256"] == profile.sha256()
        assert item["mapping"]["profile_version"] == "0.1.0"
    parse_observations(document)


def test_cli_import_without_mapping_is_unchanged(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(_import_args("canonical-json", None)) == EXIT_SUCCESS
    document = json.loads(capsys.readouterr().out)
    for item in document["observations"]:
        assert "profile_sha256" not in item["mapping"]
        assert item["value"]["value"] == "CSYN-PRONOUN-THEY-THEM"


def test_cli_import_rejects_a_bad_profile_before_reading_the_source(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = _import_args("canonical-json", FIXTURES / "reject-gi-to-spcu.json")
    assert main([*argv, "--output", str(tmp_path / "out.json")]) == EXIT_CONTRACT_ERROR
    captured = capsys.readouterr()
    assert captured.out == ""
    error = json.loads(captured.err)["error"]
    assert error["code"] == "prohibited_spcu_mapping"
    assert error["path"] == "$.rows[0].target"
    assert not (tmp_path / "out.json").exists()


def test_cli_import_rejects_a_profile_for_another_format(
    capsys: pytest.CaptureFixture[str],
) -> None:
    argv = _import_args("lis-csv", REFERENCE / "mapping-lis-json.json")
    assert main(argv) == EXIT_CONTRACT_ERROR
    error = json.loads(capsys.readouterr().err)["error"]
    assert error["code"] == "mapping_profile_format_mismatch"


def test_cli_mapping_validate_emits_the_compiled_profile(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    profile_path = REFERENCE / "mapping-fhir-r4-json.json"
    assert main(["mapping", "validate", "--profile", str(profile_path)]) == (
        EXIT_SUCCESS
    )
    printed = capsys.readouterr().out
    output = tmp_path / "compiled.json"
    assert (
        main(
            [
                "mapping",
                "validate",
                "--quiet",
                "--profile",
                str(profile_path),
                "--output",
                str(output),
            ]
        )
        == EXIT_SUCCESS
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
    assert output.read_text(encoding="utf-8") == printed
    compiled = json.loads(printed)
    assert compiled == compile_profile(_read(profile_path)).to_dict()
    assert printed == f"{canonical_json(compiled)}\n"


@pytest.mark.parametrize("name", sorted(REJECTIONS))
def test_cli_mapping_validate_rejects_with_one_error_object(
    capsys: pytest.CaptureFixture[str], name: str
) -> None:
    code, path = REJECTIONS[name]
    assert (
        main(["mapping", "validate", "--no-color", "--profile", str(FIXTURES / name)])
        == EXIT_CONTRACT_ERROR
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "\x1b" not in captured.err
    error = json.loads(captured.err)["error"]
    assert (error["code"], error["path"]) == (code, path)
    for literal in FIXTURE_CONTENT:
        assert literal not in captured.err


def test_cli_mapping_validate_logs_a_closed_record(tmp_path: Path) -> None:
    log_dir = tmp_path / "log"
    assert (
        main(
            [
                "mapping",
                "validate",
                "--quiet",
                "--log-dir",
                str(log_dir),
                "--profile",
                str(REFERENCE / "mapping-lis-csv.json"),
            ]
        )
        == EXIT_SUCCESS
    )
    record = json.loads(
        (log_dir / "contextsafe-events.jsonl").read_text(encoding="utf-8")
    )
    assert record["command"] == "mapping"
    assert record["outcome"] == "accepted"
    assert record["warnings"] == []
    assert set(record) == {
        "command",
        "error_code",
        "outcome",
        "schema_version",
        "sequence",
        "warnings",
    }


def _logged_warnings(log_dir: Path) -> list[str]:
    text = (log_dir / "contextsafe-events.jsonl").read_text(encoding="utf-8")
    records = [json.loads(line) for line in text.splitlines()]
    assert len(records) == 1
    warnings = records[0]["warnings"]
    assert isinstance(warnings, list)
    return [str(item) for item in warnings]


def test_cli_import_logs_the_warnings_the_conversion_carried(tmp_path: Path) -> None:
    """Without a profile, the log says the values are unbound tokens."""

    log_dir = tmp_path / "log"
    argv = _import_args("canonical-json", None)
    assert main([*argv, "--quiet", "--log-dir", str(log_dir)]) == EXIT_SUCCESS
    assert _logged_warnings(log_dir) == [
        "mapping_profile_not_bound",
        "plan_binding_not_checked",
    ]


def test_cli_import_logs_a_profile_that_binds_nothing(tmp_path: Path) -> None:
    """The unmatched-row warning reaches an operator, not just a test.

    A profile whose rows bind no token used to leave the command at exit 0
    with no signal at the point where the profile could still be fixed: the
    CLI writes the observation set, and the result's warnings had no reader.
    They are in the ``--log-dir`` record now, which is the surface that
    already carries closed codes.
    """

    document = _reference_profile("canonical-json")
    document["rows"][0]["source"].update({"token": "CSYN-PRONOUN-NOBODY"})
    profile = _write(tmp_path / "profile.json", document)
    log_dir = tmp_path / "log"
    argv = _import_args("canonical-json", profile)
    assert main([*argv, "--quiet", "--log-dir", str(log_dir)]) == EXIT_SUCCESS
    warnings = _logged_warnings(log_dir)
    assert "mapping_profile_row_unmatched" in warnings
    assert "mapping_profile_not_bound" not in warnings
    for literal in FIXTURE_CONTENT:
        assert literal not in json.dumps(warnings)


def test_cli_import_with_a_profile_that_binds_everything_logs_no_unmatched_row(
    tmp_path: Path,
) -> None:
    """The control: the same command, the reference profile, no warning."""

    log_dir = tmp_path / "log"
    argv = _import_args("canonical-json", REFERENCE / "mapping-canonical-json.json")
    assert main([*argv, "--quiet", "--log-dir", str(log_dir)]) == EXIT_SUCCESS
    assert _logged_warnings(log_dir) == ["plan_binding_not_checked"]


def test_cli_import_that_is_refused_logs_no_warnings(tmp_path: Path) -> None:
    """A rejected command produced no conversion, so it carries no warning."""

    log_dir = tmp_path / "log"
    argv = _import_args("canonical-json", FIXTURES / "reject-gi-to-spcu.json")
    assert main([*argv, "--quiet", "--log-dir", str(log_dir)]) == EXIT_CONTRACT_ERROR
    text = (log_dir / "contextsafe-events.jsonl").read_text(encoding="utf-8")
    record = json.loads(text)
    assert record["outcome"] == "rejected"
    assert record["error_code"] == "prohibited_spcu_mapping"
    assert record["warnings"] == []


def test_an_unknown_mapping_command_is_refused() -> None:
    args = argparse.Namespace(command="mapping", mapping_command="sign")
    with pytest.raises(ContextSafeError) as raised:
        _conversion_command(args)
    assert raised.value.code == "unsupported_command"


# --- property suites ----------------------------------------------------------

_TOKEN = st.text(alphabet="ABCDEFGHJKMNP", min_size=1, max_size=8).map(
    lambda suffix: f"CSYN-{suffix}"
)
"""Letters only after the prefix: a digit run is what the boundary detectors
refuse, and that refusal is pinned by its own test rather than drawn here."""
_ERROR_FIXED = {
    "code": "prohibited_spcu_mapping",
    "message": "GI and RSG can never be mapped into SPCU",
    "path": "$.rows[0].target",
}


@settings(max_examples=100, deadline=None)
@given(
    concept=st.sampled_from(["gender_identity", "recorded_sex_or_gender"]),
    code=_TOKEN,
    target=st.one_of(_TOKEN, st.just("fixture-context-1"), st.text(max_size=12)),
)
@example(concept="recorded_sex_or_gender", code="CSYN-X", target="")
def test_no_row_reaches_spcu_from_gi_or_rsg_whatever_the_tokens(
    concept: str, code: str, target: object
) -> None:
    """A-020 and A-021, over arbitrary tokens: the whole error is one fixed object."""

    document = _reference_profile("hl7v2-er7")
    document["rows"] = [
        {
            "source": {"concept": concept, "carrier": "GSP-5", "token": code},
            "target": {
                "concept": "sex_parameter_for_clinical_use",
                "value": {"value": target},
            },
        }
    ]
    error = _rejection(document)
    assert error.to_dict() == _ERROR_FIXED


_ANY_TEXT = st.text(min_size=1, max_size=24)
"""Nothing is filtered out of the pronoun-target strategy.

It used to filter away both the synthetic prefixes and any lowercase
slash-joined alphabetic string, which is exactly the class the shape's own
claim was about, so the property could not have caught ``jordan/rivera``
being admitted. The strategy draws it now and the test classifies each draw
against the two published grammars instead.
"""
_TARGET_REJECTIONS = (
    {
        "code": "mapping_profile_target_not_synthetic",
        "message": (
            "a target value must be in the synthetic namespace; a profile is "
            "not a route by which a real value reaches an observation"
        ),
        "path": "$.rows[0].target.value.value",
    },
    {
        "code": "direct_identifier_detected",
        "message": "a direct-identifier pattern was detected",
        "path": "$.rows[0].target.value.value",
    },
    {
        "code": "invalid_unicode",
        "message": "string must contain only Unicode scalar values",
        "path": "$.rows[0].target.value.value",
    },
)
"""The only error objects a pronoun target outside the grammar may raise.

Compared whole, the way the importer suites do, rather than by testing that
the drawn value is absent from the message: a one-letter draw is a substring
of any sentence, and the structural comparison is what proves the value is
not there.
"""


def _pronoun_target_admitted(value: str) -> bool:
    """What the two published grammars admit as a pronouns target value."""

    return bool(
        SYNTHETIC_TOKEN_PATTERN.fullmatch(value) or PRONOUN_SET_PATTERN.fullmatch(value)
    )


@settings(max_examples=200, deadline=None)
@given(value=_ANY_TEXT)
@example(value="Jordan")
@example(value="they/them/theirs/them")
@example(value="a")
@example(value="they/them")
@example(value="jordan/rivera")
@example(value="CSYN-PRONOUN-THEY-THEM")
def test_a_pronoun_target_is_admitted_exactly_when_the_published_shape_admits_it(
    value: str,
) -> None:
    """Both directions of the same grammar, over arbitrary draws.

    Outside the two shapes the rejection is one of three fixed error objects,
    compared whole so the drawn value is proved absent. Inside them the value
    arrives, ``jordan/rivera`` included: the shape admits two lowercase words
    joined by a slash and cannot tell one from a pronoun set, which is what
    ``PRONOUN_SET_PATTERN`` now says rather than the reverse.
    """

    document = _reference_profile("canonical-json")
    document["rows"][0]["target"]["value"] = {"status": "specified", "value": value}
    if not _pronoun_target_admitted(value):
        assert _rejection(document).to_dict() in _TARGET_REJECTIONS
        return
    profile = load_profile(document)
    assert profile.rows[0].target.to_dict()["value"] == value


def test_the_pronoun_shape_admits_a_lowercase_slash_joined_name() -> None:
    """The claim the shape carries is the one this pins, not a wider one.

    ``jordan/rivera`` is admitted. Refusing it would need a published list of
    pronouns to compare against, and publishing one is a community judgment
    no reviewer here has made, so the documented guarantee is the shape --
    no capital, digit, space, or other punctuation -- and not "no name can
    be written in it". The boundary scan does not catch it either: it is not
    a direct identifier, a canary, or free text by any detector's rule.
    """

    document = _reference_profile("canonical-json")
    document["rows"][0]["target"]["value"] = {
        "status": "specified",
        "value": "jordan/rivera",
    }
    profile = load_profile(document)
    assert profile.rows[0].target.to_dict() == {
        "status": "specified",
        "value": "jordan/rivera",
    }


def _scanned_pronoun_records(tokens: list[str]) -> ScannedSource:
    """The reference envelope with one pronouns record per token, in memory."""

    envelope = _read(REFERENCE / "evidence-source.json")
    envelope["records"] = [
        {
            "field_code": "pronouns",
            "value_code": token,
            "context_code": None,
            "source_pointer": f"$.records[{index}]",
        }
        for index, token in enumerate(tokens)
    ]
    raw = canonical_json(json.loads(json.dumps(envelope))).encode("utf-8")
    return ScannedSource(
        raw_sha256=hashlib.sha256(raw).hexdigest(),
        raw_byte_count=len(raw),
        value=parse_json_bytes(raw),
    )


_CASE = parse_case(_read(REFERENCE / "case.json"))
"""Parsed once at import: Hypothesis must not share a function-scoped fixture."""


@settings(max_examples=60, deadline=None)
@given(
    tokens=st.lists(_TOKEN, min_size=1, max_size=5, unique=True),
    bound=st.data(),
)
def test_applying_a_profile_binds_exactly_the_matched_tokens_deterministically(
    tokens: list[str], bound: st.DataObject
) -> None:
    """Concepts and counts never change; only matched values do; bytes repeat."""

    chosen = bound.draw(st.lists(st.sampled_from(tokens), unique=True))
    document = _reference_profile("canonical-json")
    document["rows"] = [
        {
            "source": {"concept": "pronouns", "carrier": "pronouns", "token": token},
            "target": {
                "concept": "pronouns",
                "value": {"status": "specified", "value": f"CSYN-BOUND-{index}"},
            },
        }
        for index, token in enumerate(chosen)
    ]
    scanned = _scanned_pronoun_records(tokens)
    plain = convert_scanned(scanned, case=_CASE, checkpoint=Checkpoint.EHR)
    if not chosen:
        first = second = plain
    else:
        profile = load_profile(document)
        first = apply_profile(plain, profile)
        second = apply_profile(
            convert_scanned(scanned, case=_CASE, checkpoint=Checkpoint.EHR), profile
        )
    assert canonical_json(first.observation_set()) == canonical_json(
        second.observation_set()
    )
    assert len(first.observations) == len(tokens)
    assert all(item.concept is ConceptKind.PRONOUNS for item in first.observations)
    for token, plain_item, item in zip(
        tokens, plain.observations, first.observations, strict=True
    ):
        value = item.value.to_dict()["value"]
        if token in chosen:
            assert value == f"CSYN-BOUND-{chosen.index(token)}"
        else:
            assert value == token
            assert item.value == plain_item.value
    if chosen:
        unmatched = set(tokens) - set(chosen)
        assert (
            ImportWarningCode.MAPPING_PROFILE_ROW_UNMATCHED in first.warnings
        ) == bool(unmatched)


@pytest.mark.parametrize(
    ("concept", "carrier", "value"),
    [
        (
            "name_to_use",
            "PID-5",
            {"status": "specified", "value": "CSYN-9876543210", "use": "usual"},
        ),
        (
            "pronouns",
            "GSP-5",
            {"status": "specified", "value": "CSYN-555-01-0199"},
        ),
    ],
)
def test_a_target_shaped_like_an_identifier_is_refused_by_the_boundary_scan(
    concept: str, carrier: str, value: dict[str, Any]
) -> None:
    """A target goes through the scan the source token already goes through.

    Each of these satisfies the synthetic grammar, so the grammar alone would
    admit it. The asymmetry this closes was real: the same string was refused
    as a source token and accepted as a target.
    """

    document = _reference_profile("hl7v2-er7")
    document["rows"] = [
        {
            "source": {"concept": concept, "carrier": carrier, "token": "X"},
            "target": {"concept": concept, "value": value},
        }
    ]
    error = _rejection(document)
    assert error.code == "direct_identifier_detected"
    assert error.path == "$.rows[0].target.value.value"
    assert value["value"] not in str(error)
    assert value["value"] not in canonical_json(error.to_dict())
