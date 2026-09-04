"""Published rule-set 0.2 contract against the runtime (B-028).

`schemas/contextsafe-rule-set-v0.2.schema.json` is the first published schema
for the rule set: the exact-only 0.1.0 shape predates the published contracts
and has no file. These tests are the schema/runtime agreement gate for the new
shape, modeled on `tests/test_receipt_schema.py`: the packaged predicate rule
set validates, the published enums equal the runtime types, a 0.1.0 rule set
rewritten as 0.2.0 still validates (the default is `exact`), and every
fail-closed refusal the runtime makes at the rule level is also a rejection
under the contract, so the two cannot drift apart silently.
"""

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from contextsafe.errors import ContextSafeError
from contextsafe.models import (
    PREDICATE_RULE_SET_SCHEMA_VERSION,
    Checkpoint,
    ConceptKind,
    RulePredicate,
)
from contextsafe.reference_fixtures import REFERENCE_ROOT
from contextsafe.validation import parse_rule_set

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "contextsafe-rule-set-v0.2.schema.json"


def _schema() -> dict[str, Any]:
    value = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _validator() -> Draft202012Validator:
    return Draft202012Validator(_schema())


@pytest.fixture
def predicate_rules_json() -> dict[str, Any]:
    value = json.loads(
        (REFERENCE_ROOT / "rules-predicates.json").read_text(encoding="utf-8")
    )
    assert isinstance(value, dict)
    return value


def _rule(rules_json: dict[str, Any], rule_id: str) -> dict[str, Any]:
    rule = next(item for item in rules_json["rules"] if item["rule_id"] == rule_id)
    assert isinstance(rule, dict)
    return rule


def test_published_contract_accepts_the_packaged_predicate_rule_set(
    predicate_rules_json: dict[str, Any],
) -> None:
    schema = _schema()
    Draft202012Validator.check_schema(schema)
    assert schema["$id"].endswith("/schemas/contextsafe-rule-set-v0.2.schema.json")
    _validator().validate(predicate_rules_json)
    parse_rule_set(predicate_rules_json)


def test_contract_version_matches_the_runtime_constant() -> None:
    assert (
        _schema()["properties"]["schema_version"]["const"]
        == PREDICATE_RULE_SET_SCHEMA_VERSION
    )


def test_contract_enums_equal_the_runtime_types() -> None:
    defs = _schema()["$defs"]
    assert set(defs["predicate"]["enum"]) == {item.value for item in RulePredicate}
    assert set(defs["checkpoint"]["enum"]) == {item.value for item in Checkpoint}
    assert set(defs["concept"]["enum"]) == {item.value for item in ConceptKind}


def test_an_exact_only_rule_set_rewritten_as_0_2_0_validates(
    rules_json: dict[str, Any],
) -> None:
    """The default is exact, so the 0.1.0 shape is a subset of 0.2.0."""

    rules_json["schema_version"] = PREDICATE_RULE_SET_SCHEMA_VERSION
    _validator().validate(rules_json)
    parse_rule_set(rules_json)


def test_the_exact_only_version_string_does_not_validate_here(
    rules_json: dict[str, Any],
) -> None:
    """A 0.1.0 document is the runtime's to accept; this contract is 0.2.0."""

    assert not _validator().is_valid(rules_json)


def test_the_canonical_form_of_every_rule_still_validates(
    predicate_rules_json: dict[str, Any],
) -> None:
    """What the runtime hashes is a document the contract accepts."""

    canonical = parse_rule_set(predicate_rules_json).to_dict()
    _validator().validate(canonical)
    assert canonical == predicate_rules_json


@pytest.mark.parametrize(
    ("rule_id", "mutation"),
    [
        ("A-I01", {"predicate": "closest_supported_value"}),
        ("A-I01", {"contextsafe_extension": "unreviewed"}),
        ("A-I02", {"forbidden": [{"status": "absent", "value": None}]}),
        ("A-I02", {"expected_count": 1}),
        ("A-I02", {"preserved_from": "registration"}),
        ("A-I06", {"forbidden": []}),
        ("A-I06", {"forbidden": [{"value": "Q", "context": "c", "source": "s"}]}),
        ("A-I06", {"forbidden": [{"status": "absent", "value": None}]}),
        ("A-I07", {"expected_count": 0}),
        ("A-I07", {"expected_count": 65}),
        ("A-I07", {"expected_count": "1"}),
        ("A-I08", {"preserved_from": "elsewhere"}),
    ],
)
def test_contract_and_runtime_agree_on_a_malformed_rule(
    predicate_rules_json: dict[str, Any], rule_id: str, mutation: dict[str, Any]
) -> None:
    _rule(predicate_rules_json, rule_id).update(mutation)
    assert not _validator().is_valid(predicate_rules_json)
    with pytest.raises(ContextSafeError):
        parse_rule_set(predicate_rules_json)


@pytest.mark.parametrize(
    ("rule_id", "field"),
    [("A-I06", "forbidden"), ("A-I07", "expected_count"), ("A-I08", "preserved_from")],
)
def test_contract_and_runtime_agree_that_a_predicate_field_is_required(
    predicate_rules_json: dict[str, Any], rule_id: str, field: str
) -> None:
    del _rule(predicate_rules_json, rule_id)[field]
    assert not _validator().is_valid(predicate_rules_json)
    with pytest.raises(ContextSafeError):
        parse_rule_set(predicate_rules_json)


@pytest.mark.parametrize(
    ("predicate", "concept"),
    [
        ("present", "recorded_sex_or_gender"),
        ("status_preserved", "sex_parameter_for_clinical_use"),
        ("not_overwritten_by", "pronouns"),
    ],
)
def test_contract_and_runtime_agree_on_a_vacuous_predicate(
    predicate_rules_json: dict[str, Any],
    case_json: dict[str, Any],
    predicate: str,
    concept: str,
) -> None:
    rule = _rule(predicate_rules_json, "A-I01")
    declared = case_json["concepts"][concept]
    rule.update(
        {
            "predicate": predicate,
            "concept": concept,
            "expected": declared[0] if isinstance(declared, list) else declared,
        }
    )
    assert not _validator().is_valid(predicate_rules_json)
    with pytest.raises(ContextSafeError):
        parse_rule_set(predicate_rules_json)


def test_the_contract_records_the_constraints_only_the_runtime_decides() -> None:
    """A checkpoint pair, forbidden uniqueness, and the manifest cross-checks
    are runtime semantics; the schema says so rather than implying it checks
    them."""

    constraints = _schema()["x-contextsafe-semantic-constraints"]
    assert any("preserved_from" in item for item in constraints)
    assert any("unique" in item for item in constraints)
    assert any("case manifest" in item for item in constraints)


def test_a_same_checkpoint_pair_is_runtime_only(
    predicate_rules_json: dict[str, Any],
) -> None:
    """The schema accepts it; the runtime does not. Pinned so the boundary is
    known rather than assumed."""

    _rule(predicate_rules_json, "A-I08")["preserved_from"] = "ehr"
    assert _validator().is_valid(predicate_rules_json)
    with pytest.raises(ContextSafeError) as caught:
        parse_rule_set(predicate_rules_json)
    assert caught.value.code == "invalid_checkpoint_pair"


def test_the_contract_rejects_an_empty_rule_list_and_unknown_top_level_fields(
    predicate_rules_json: dict[str, Any],
) -> None:
    empty = copy.deepcopy(predicate_rules_json)
    empty["rules"] = []
    assert not _validator().is_valid(empty)
    predicate_rules_json["approvals"] = []
    assert not _validator().is_valid(predicate_rules_json)
