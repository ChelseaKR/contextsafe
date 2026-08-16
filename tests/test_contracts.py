"""Contract and fail-closed boundary tests for synthetic schemas."""

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from contextsafe.errors import ContextSafeError
from contextsafe.models import (
    GenderIdentity,
    NameToUse,
    Pronouns,
    RecordedSexOrGender,
    SexParameterForClinicalUse,
)
from contextsafe.validation import (
    parse_bundle,
    parse_case,
    parse_observations,
    parse_rule_set,
)

ROOT = Path(__file__).resolve().parents[1]


def _assert_code(code: str, call: Any, value: object) -> None:
    with pytest.raises(ContextSafeError) as caught:
        call(value)
    assert caught.value.code == code
    assert "fixture-gender-1" not in str(caught.value)


SCHEMA_ID_PREFIX = "https://contextsafe.invalid/schemas/"


def test_every_published_schema_is_a_valid_draft_2020_12_contract() -> None:
    """Every file in `schemas/` is a self-consistent published contract."""

    published = sorted((ROOT / "schemas").glob("*.schema.json"))
    assert published
    for path in published:
        schema = json.loads(path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["$id"].endswith(f"/schemas/{path.name}")
        assert schema["title"].startswith("ContextSafe ")


def test_every_schema_id_is_under_the_reserved_domain() -> None:
    """`$id` must be an identifier nobody can take over.

    Five of these schemas once claimed `$id` under `contextsafe.dev`, a domain
    nobody had registered. On a public repository that is a squattable contract
    identity: anyone may buy the name and serve documents at the URIs this
    project publishes as canonical. `.invalid` is reserved by RFC 2606 and can
    never be delegated, so the identifiers stay unique and stable without
    depending on anyone owning anything. See `schemas/README.md`.
    """

    published = sorted((ROOT / "schemas").glob("*.schema.json"))
    assert published
    for path in published:
        schema = json.loads(path.read_text(encoding="utf-8"))
        assert schema["$id"] == f"{SCHEMA_ID_PREFIX}{path.name}", (
            f"{path.name} claims an identity outside the reserved domain"
        )


def test_published_schemas_accept_reference_fixtures(
    case_json: dict[str, Any], observations_json: dict[str, Any]
) -> None:
    pairs = (
        ("contextsafe-case-v0.1.schema.json", case_json),
        ("contextsafe-observation-set-v0.1.schema.json", observations_json),
    )
    for schema_name, instance in pairs:
        schema = json.loads(
            (ROOT / "schemas" / schema_name).read_text(encoding="utf-8")
        )
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(instance)


def test_published_schemas_enforce_runtime_spcu_token_bounds(
    case_json: dict[str, Any], observations_json: dict[str, Any]
) -> None:
    overlong_context = "ORDER-CSYN-" + "A" * 100
    case_json["concepts"]["sex_parameter_for_clinical_use"][0]["context_id"] = (
        overlong_context
    )
    observations_json["observations"][2]["value"]["context_id"] = overlong_context

    for schema_name, instance in (
        ("contextsafe-case-v0.1.schema.json", case_json),
        ("contextsafe-observation-set-v0.1.schema.json", observations_json),
    ):
        schema = json.loads(
            (ROOT / "schemas" / schema_name).read_text(encoding="utf-8")
        )
        assert not Draft202012Validator(schema).is_valid(instance)
    _assert_code("invalid_format", parse_case, case_json)
    _assert_code("invalid_format", parse_observations, observations_json)


def test_published_schemas_and_runtime_reject_non_scalar_unicode(
    case_json: dict[str, Any], observations_json: dict[str, Any]
) -> None:
    non_scalar = json.loads('"\\ud800"')
    case_json["concepts"]["pronouns"]["value"] = non_scalar
    observations_json["observations"][4]["value"]["value"] = non_scalar

    for schema_name, instance in (
        ("contextsafe-case-v0.1.schema.json", case_json),
        ("contextsafe-observation-set-v0.1.schema.json", observations_json),
    ):
        schema = json.loads(
            (ROOT / "schemas" / schema_name).read_text(encoding="utf-8")
        )
        assert not Draft202012Validator(schema).is_valid(instance)
    _assert_code("invalid_unicode", parse_case, case_json)
    _assert_code("invalid_unicode", parse_observations, observations_json)


def test_errors_never_echo_unknown_or_ancestor_keys(
    case_json: dict[str, Any],
) -> None:
    private_key = "person@example.invalid"
    case_json[private_key] = True
    with pytest.raises(ContextSafeError) as caught:
        parse_case(case_json)
    assert caught.value.code == "unknown_field"
    assert caught.value.path == "$"
    assert private_key not in str(caught.value)

    case_json.pop(private_key)
    case_json[private_key] = {"email": "private-value"}
    with pytest.raises(ContextSafeError) as caught:
        parse_case(case_json)
    assert caught.value.code == "prohibited_field"
    assert caught.value.path == "$"
    assert private_key not in str(caught.value)


def test_models_keep_all_five_concepts_as_distinct_types(
    case_json: dict[str, Any],
    observations_json: dict[str, Any],
    rules_json: dict[str, Any],
) -> None:
    bundle = parse_bundle(case_json, observations_json, rules_json)
    assert isinstance(bundle.case.gender_identity, GenderIdentity)
    assert isinstance(bundle.case.recorded_sex_or_gender[0], RecordedSexOrGender)
    assert isinstance(
        bundle.case.sex_parameter_for_clinical_use[0], SexParameterForClinicalUse
    )
    assert isinstance(bundle.case.name_to_use, NameToUse)
    assert isinstance(bundle.case.pronouns, Pronouns)
    assert len({type(item.value) for item in bundle.observations}) == 5


@pytest.mark.parametrize("source", ["gender_identity", "recorded_sex_or_gender"])
def test_gi_and_rsg_can_never_map_into_spcu(
    source: str, observations_json: dict[str, Any]
) -> None:
    spcu = observations_json["observations"][2]
    spcu["mapping"]["source_concept"] = source
    _assert_code("prohibited_spcu_mapping", parse_observations, observations_json)


def test_other_cross_concept_assignment_is_rejected(
    observations_json: dict[str, Any],
) -> None:
    mapping = observations_json["observations"][0]["mapping"]
    mapping["source_concept"] = "pronouns"
    _assert_code("concept_type_mismatch", parse_observations, observations_json)


def test_mapping_target_must_match_observation_concept(
    observations_json: dict[str, Any],
) -> None:
    mapping = observations_json["observations"][0]["mapping"]
    mapping["source_concept"] = "pronouns"
    mapping["target_concept"] = "pronouns"
    _assert_code("observation_target_mismatch", parse_observations, observations_json)


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (lambda value: value.update({"narrative": "prohibited"}), "prohibited_field"),
        (lambda value: value.update({"unexpected": True}), "unknown_field"),
        (lambda value: value.pop("case_id"), "missing_field"),
        (
            lambda value: value.update({"schema_version": "future"}),
            "unsupported_schema",
        ),
        (lambda value: value.update({"case_id": "unsafe"}), "invalid_format"),
        (
            lambda value: value["synthetic_identifier"].update(
                {"value": "CSYN-CTP-OTHER"}
            ),
            "invalid_synthetic_identifier",
        ),
        (
            lambda value: value.update({"prohibited_inferences": []}),
            "missing_safety_guard",
        ),
        (
            lambda value: value["concepts"]["name_to_use"].update(
                {"value": "Real Person"}
            ),
            "non_synthetic_name",
        ),
        (
            lambda value: value["concepts"]["name_to_use"].update({"use": "official"}),
            "invalid_name_use",
        ),
        (
            lambda value: value["concepts"]["pronouns"].update(
                {"status": "declined", "value": "they/them"}
            ),
            "invalid_presence_semantics",
        ),
        (
            lambda value: value["concepts"]["recorded_sex_or_gender"][0].update(
                {"value": "unsupported"}
            ),
            "invalid_rsg_value",
        ),
        (
            lambda value: value["concepts"]["sex_parameter_for_clinical_use"][0].update(
                {"context_id": "ORDER-REAL-1"}
            ),
            "non_synthetic_context",
        ),
        (
            lambda value: value["concepts"]["sex_parameter_for_clinical_use"][0].update(
                {"supporting_observation_ids": []}
            ),
            "invalid_support",
        ),
    ],
)
def test_case_rejects_malformed_or_prohibited_content(
    mutation: Any, code: str, case_json: dict[str, Any]
) -> None:
    mutation(case_json)
    _assert_code(code, parse_case, case_json)


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (
            lambda value: value.update({"schema_version": "future"}),
            "unsupported_schema",
        ),
        (lambda value: value.update({"observations": "not-an-array"}), "invalid_type"),
        (
            lambda value: value["observations"][0].update({"schema_version": "future"}),
            "unsupported_schema",
        ),
        (
            lambda value: value["observations"][0].update({"observation_id": "unsafe"}),
            "invalid_format",
        ),
        (
            lambda value: value["observations"][0]["evidence"].update(
                {"source_sha256": "bad"}
            ),
            "invalid_format",
        ),
        (
            lambda value: value["observations"][0]["evidence"].update(
                {"source_pointer": "unsafe path"}
            ),
            "invalid_format",
        ),
        (
            lambda value: value["observations"].append(value["observations"][0]),
            "duplicate_observation_id",
        ),
        (
            lambda value: value["observations"][0].update({"concept": "unsupported"}),
            "invalid_enum",
        ),
    ],
)
def test_observation_set_rejects_malformed_content(
    mutation: Any, code: str, observations_json: dict[str, Any]
) -> None:
    mutation(observations_json)
    _assert_code(code, parse_observations, observations_json)


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (
            lambda value: value.update({"schema_version": "future"}),
            "unsupported_schema",
        ),
        (lambda value: value.update({"rules": []}), "empty_rule_set"),
        (lambda value: value["rules"].append(value["rules"][0]), "duplicate_rule_id"),
        (
            lambda value: value["rules"][0].update({"required": "yes"}),
            "invalid_type",
        ),
        (
            lambda value: value["rules"][0].update({"version": "latest"}),
            "invalid_format",
        ),
    ],
)
def test_rule_set_rejects_malformed_content(
    mutation: Any, code: str, rules_json: dict[str, Any]
) -> None:
    mutation(rules_json)
    _assert_code(code, parse_rule_set, rules_json)


def test_bundle_rejects_cross_document_case_mismatch(
    case_json: dict[str, Any],
    observations_json: dict[str, Any],
    rules_json: dict[str, Any],
) -> None:
    observations_json["observations"][0]["case_id"] = "CTP-X99"
    with pytest.raises(ContextSafeError, match="case_mismatch"):
        parse_bundle(case_json, observations_json, rules_json)
    observations_json["observations"][0]["case_id"] = "CTP-I01"
    rules_json["rules"][0]["case_id"] = "CTP-X99"
    with pytest.raises(ContextSafeError, match="case_mismatch"):
        parse_bundle(case_json, observations_json, rules_json)


def test_bundle_rejects_rule_expectation_detached_from_case_manifest(
    case_json: dict[str, Any],
    observations_json: dict[str, Any],
    rules_json: dict[str, Any],
) -> None:
    rules_json["rules"][-1]["expected"]["value"] = "she/her"

    with pytest.raises(ContextSafeError, match="rule_expectation_mismatch"):
        parse_bundle(case_json, observations_json, rules_json)
