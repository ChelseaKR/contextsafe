"""Engagement and plan contract tests for the non-production guard."""

import copy
import itertools
import json
import shutil
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import Draft202012Validator

from contextsafe.canonical import canonical_json
from contextsafe.cli import main
from contextsafe.errors import ContextSafeError
from contextsafe.jsonio import load_json
from contextsafe.pack import (
    ApprovalRole,
    PackCompilation,
    approval_subject_sha256,
    compile_pack,
    parse_pack,
)
from contextsafe.plan import (
    engagement_sha256,
    parse_engagement,
    parse_plan,
    validate_plan,
)

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "fixtures" / "reference"
AS_OF = date(2026, 7, 13)


def _test_pack_value() -> dict[str, Any]:
    """Activate the draft only in memory with visibly test-only declarations."""

    pack = cast(dict[str, Any], copy.deepcopy(load_json(REFERENCE / "pack-draft.json")))
    pack["lifecycle"].update({"status": "active", "valid_from": "2026-07-01"})
    pack["sources"][0].update(
        {
            "status": "active",
            "reviewed_on": "2026-07-13",
            "review_by": "2026-12-31",
        }
    )
    subject = approval_subject_sha256(parse_pack(pack))
    pack["approvals"] = [
        {
            "decided_on": "2026-07-10",
            "decision": "approved",
            "review_by": "2026-12-31",
            "reviewer_id": f"TEST-{role.value.upper().replace('_', '-')}",
            "role": role.value,
            "subject_sha256": subject,
            "withdrawn_on": None,
        }
        for role in ApprovalRole
    ]
    return pack


def _compiled_pack(*, as_of: date = AS_OF) -> PackCompilation:
    return compile_pack(_test_pack_value(), root=REFERENCE, as_of=as_of)


def _engagement() -> dict[str, Any]:
    return {
        "allowed_hosts": [
            "staging.contextsafe.invalid",
            "lis.contextsafe.invalid",
        ],
        "cleanup": {
            "due_on": "2026-08-01",
            "owner_id": "TEST-CLEANUP-OWNER",
            "system_ids": ["SYS-STAGING-EHR", "SYS-STAGING-LIS"],
        },
        "engagement_id": "ENG-SYNTHETIC-TEST",
        "environment": {
            "classification": "staging",
            "name": "SYNTHETIC-STAGING-A",
            "non_production_attested": True,
            "production_access_prohibited": True,
        },
        "owners": {
            "cleanup_owner_id": "TEST-CLEANUP-OWNER",
            "clinical_owner_id": "TEST-CLINICAL-OWNER",
            "privacy_owner_id": "TEST-PRIVACY-OWNER",
            "technical_owner_id": "TEST-TECHNICAL-OWNER",
        },
        "partner_profile_id": "PROFILE-SYNTHETIC-TEST",
        "review_by": "2026-12-31",
        "schema_version": "contextsafe.engagement/1.0.0",
        "synthetic_namespace": {
            "system": "urn:contextsafe:synthetic",
            "value_prefix": "CSYN-",
        },
        "valid_from": "2026-07-01",
    }


def _plan(engagement: dict[str, Any], pack: PackCompilation) -> dict[str, Any]:
    parsed_engagement = parse_engagement(engagement)
    return {
        "case_tokens": [
            cast(dict[str, Any], item["synthetic_identifier"])["value"]
            for item in pack.case_manifest
        ],
        "checkpoints": ["registration", "ehr", "interface", "lis_return"],
        "cleanup": copy.deepcopy(engagement["cleanup"]),
        "engagement_id": engagement["engagement_id"],
        "engagement_sha256": engagement_sha256(parsed_engagement),
        "environment": copy.deepcopy(engagement["environment"]),
        "owners": copy.deepcopy(engagement["owners"]),
        "compiled_pack_sha256": pack.compiled_pack_sha256,
        "plan_id": "PLAN-SYNTHETIC-TEST",
        "schema_version": "contextsafe.plan/1.0.0",
        "synthetic_namespace": copy.deepcopy(engagement["synthetic_namespace"]),
        "target_hosts": copy.deepcopy(engagement["allowed_hosts"]),
        "valid_from": "2026-07-13",
        "valid_until": "2026-08-01",
    }


def _schema(name: str) -> dict[str, Any]:
    return json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))


def _values() -> tuple[dict[str, Any], dict[str, Any], PackCompilation]:
    pack = _compiled_pack()
    engagement = _engagement()
    return engagement, _plan(engagement, pack), pack


def test_engagement_plan_and_compilation_conform_to_schemas() -> None:
    engagement, plan, pack = _values()
    for name, value in (
        ("contextsafe-engagement-v1.schema.json", engagement),
        ("contextsafe-plan-v1.schema.json", plan),
    ):
        schema = _schema(name)
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(value)

    compiled = validate_plan(engagement, plan, pack=pack, as_of=AS_OF).to_dict()
    compiled_schema = _schema("contextsafe-compiled-plan-v1.schema.json")
    Draft202012Validator.check_schema(compiled_schema)
    Draft202012Validator(compiled_schema).validate(compiled)
    assert compiled["declared_controls_status"] == "pass"
    assert compiled["valid_for_signing"] is True
    assert compiled["signature_status"] == "not_verified"
    assert compiled["executable"] is False
    assert compiled["network_actions_performed"] is False


@pytest.mark.parametrize("document", ["engagement", "plan"])
def test_production_environment_is_blocked(document: str) -> None:
    engagement, plan, pack = _values()
    target = engagement if document == "engagement" else plan
    target["environment"]["classification"] = "production"

    with pytest.raises(ContextSafeError) as raised:
        validate_plan(engagement, plan, pack=pack, as_of=AS_OF)

    assert raised.value.code == "production_environment"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("non_production_attested", False),
        ("production_access_prohibited", False),
    ],
)
def test_non_production_attestations_are_required(field: str, value: bool) -> None:
    engagement, plan, pack = _values()
    engagement["environment"][field] = value

    with pytest.raises(ContextSafeError) as raised:
        validate_plan(engagement, plan, pack=pack, as_of=AS_OF)

    assert raised.value.code == "non_production_attestation_missing"


def test_unallowlisted_host_is_blocked() -> None:
    engagement, plan, pack = _values()
    plan["target_hosts"] = ["not-allowlisted.contextsafe.invalid"]

    with pytest.raises(ContextSafeError) as raised:
        validate_plan(engagement, plan, pack=pack, as_of=AS_OF)

    assert raised.value.code == "host_not_allowlisted"


@pytest.mark.parametrize(
    "host",
    [
        "https://staging.contextsafe.invalid",
        "*.contextsafe.invalid",
        "Staging.contextsafe.invalid",
        "127.0.0.1",
        "2130706433",
        "127.1",
        "0177.0.0.1",
        "0x7f.0.0.1",
        "::1",
        "0:0:0:0:0:0:0:1",
        "::ffff:127.0.0.1",
    ],
)
def test_noncanonical_or_ip_hosts_are_blocked(host: str) -> None:
    engagement, plan, pack = _values()
    plan["target_hosts"] = [host]

    with pytest.raises(ContextSafeError):
        validate_plan(engagement, plan, pack=pack, as_of=AS_OF)


@pytest.mark.parametrize("document", ["engagement", "plan"])
def test_missing_owner_is_blocked(document: str) -> None:
    engagement, plan, pack = _values()
    target = engagement if document == "engagement" else plan
    del target["owners"]["privacy_owner_id"]

    with pytest.raises(ContextSafeError) as raised:
        validate_plan(engagement, plan, pack=pack, as_of=AS_OF)

    assert raised.value.code == "missing_owner"


def test_namespace_mismatch_is_blocked() -> None:
    engagement, plan, pack = _values()
    plan["synthetic_namespace"]["value_prefix"] = "CSYN-WRONG-"

    with pytest.raises(ContextSafeError) as raised:
        validate_plan(engagement, plan, pack=pack, as_of=AS_OF)

    assert raised.value.code == "namespace_mismatch"


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("environment", "environment_mismatch"),
        ("owner", "owner_mismatch"),
        ("cleanup", "cleanup_mismatch"),
        ("engagement_hash", "engagement_hash_mismatch"),
        ("pack_hash", "compiled_pack_pin_mismatch"),
        ("case_scope", "case_scope_mismatch"),
    ],
)
def test_cross_document_pins_and_scope_fail_closed(
    mutation: str, expected_code: str
) -> None:
    engagement, plan, pack = _values()
    if mutation == "environment":
        plan["environment"]["name"] = "SYNTHETIC-STAGING-B"
    elif mutation == "owner":
        plan["owners"]["technical_owner_id"] = "TEST-OTHER-OWNER"
    elif mutation == "cleanup":
        plan["cleanup"]["due_on"] = "2026-08-02"
    elif mutation == "engagement_hash":
        plan["engagement_sha256"] = "0" * 64
    elif mutation == "pack_hash":
        plan["compiled_pack_sha256"] = "0" * 64
    else:
        plan["case_tokens"] = ["CSYN-CTP-Z99"]

    with pytest.raises(ContextSafeError) as raised:
        validate_plan(engagement, plan, pack=pack, as_of=AS_OF)

    assert raised.value.code == expected_code


def test_checkpoint_and_validity_scope_fail_closed() -> None:
    engagement, plan, pack = _values()
    plan["checkpoints"].pop()
    with pytest.raises(ContextSafeError) as raised:
        validate_plan(engagement, plan, pack=pack, as_of=AS_OF)
    assert raised.value.code == "checkpoint_scope_incomplete"

    engagement, plan, pack = _values()
    plan["valid_until"] = "2027-01-01"
    with pytest.raises(ContextSafeError) as raised:
        validate_plan(engagement, plan, pack=pack, as_of=AS_OF)
    assert raised.value.code == "plan_outside_engagement"

    engagement, plan, _ = _values()
    stale_pack = _compiled_pack(as_of=date(2026, 7, 14))
    with pytest.raises(ContextSafeError) as raised:
        validate_plan(engagement, plan, pack=stale_pack, as_of=AS_OF)
    assert raised.value.code == "pack_date_mismatch"


def test_plan_compilation_is_order_invariant() -> None:
    engagement, plan, pack = _values()
    baseline = canonical_json(
        validate_plan(engagement, plan, pack=pack, as_of=AS_OF).to_dict()
    )

    for checkpoint_order in itertools.permutations(plan["checkpoints"]):
        candidate_engagement = copy.deepcopy(engagement)
        candidate_engagement["allowed_hosts"].reverse()
        candidate_engagement["cleanup"]["system_ids"].reverse()
        candidate_plan = copy.deepcopy(plan)
        candidate_plan["target_hosts"].reverse()
        candidate_plan["cleanup"]["system_ids"].reverse()
        candidate_plan["checkpoints"] = list(checkpoint_order)
        actual = canonical_json(
            validate_plan(
                candidate_engagement,
                candidate_plan,
                pack=pack,
                as_of=AS_OF,
            ).to_dict()
        )
        assert actual == baseline


def test_plan_cli_validates_without_network_execution(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    shutil.copyfile(REFERENCE / "case.json", tmp_path / "case.json")
    shutil.copyfile(REFERENCE / "rules.json", tmp_path / "rules.json")
    pack_value = _test_pack_value()
    pack = compile_pack(pack_value, root=tmp_path, as_of=AS_OF)
    engagement = _engagement()
    plan = _plan(engagement, pack)
    paths = {
        "pack": tmp_path / "pack.json",
        "engagement": tmp_path / "engagement.json",
        "plan": tmp_path / "plan.json",
    }
    paths["pack"].write_text(json.dumps(pack_value), encoding="utf-8")
    paths["engagement"].write_text(json.dumps(engagement), encoding="utf-8")
    paths["plan"].write_text(json.dumps(plan), encoding="utf-8")

    exit_code = main(
        [
            "plan",
            "validate",
            "--engagement",
            str(paths["engagement"]),
            "--plan",
            str(paths["plan"]),
            "--pack",
            str(paths["pack"]),
            "--as-of",
            "2026-07-13",
        ]
    )

    captured = capsys.readouterr()
    output = json.loads(captured.out)
    assert exit_code == 0
    assert captured.err == ""
    assert output["network_actions_performed"] is False
    assert output["executable"] is False


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("unsupported_schema", "unsupported_schema"),
        ("empty_hosts", "invalid_host_count"),
        ("duplicate_host", "duplicate_allowed_host"),
        ("unsupported_environment", "unsupported_environment"),
        ("empty_cleanup", "invalid_cleanup_scope"),
        ("duplicate_cleanup_system", "duplicate_cleanup_system"),
        ("inverted_validity", "invalid_validity"),
        ("cleanup_owner", "cleanup_owner_mismatch"),
        ("cleanup_deadline", "cleanup_deadline_out_of_bounds"),
    ],
)
def test_engagement_parser_rejects_invalid_contracts(
    mutation: str, expected_code: str
) -> None:
    engagement = _engagement()
    if mutation == "unsupported_schema":
        engagement["schema_version"] = "contextsafe.engagement/2.0.0"
    elif mutation == "empty_hosts":
        engagement["allowed_hosts"] = []
    elif mutation == "duplicate_host":
        engagement["allowed_hosts"].append(engagement["allowed_hosts"][0])
    elif mutation == "unsupported_environment":
        engagement["environment"]["classification"] = "development"
    elif mutation == "empty_cleanup":
        engagement["cleanup"]["system_ids"] = []
    elif mutation == "duplicate_cleanup_system":
        engagement["cleanup"]["system_ids"].append(
            engagement["cleanup"]["system_ids"][0]
        )
    elif mutation == "inverted_validity":
        engagement["valid_from"] = "2027-01-01"
    elif mutation == "cleanup_owner":
        engagement["cleanup"]["owner_id"] = "TEST-OTHER-OWNER"
    else:
        engagement["cleanup"]["due_on"] = "2027-01-01"

    with pytest.raises(ContextSafeError) as raised:
        parse_engagement(engagement)

    assert raised.value.code == expected_code


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("unsupported_schema", "unsupported_schema"),
        ("empty_hosts", "invalid_host_count"),
        ("duplicate_host", "duplicate_target_host"),
        ("unsupported_checkpoint", "unsupported_checkpoint"),
        ("duplicate_checkpoint", "duplicate_checkpoint"),
        ("empty_cases", "invalid_case_scope"),
        ("duplicate_case", "duplicate_case_token"),
        ("inverted_validity", "invalid_validity"),
    ],
)
def test_plan_parser_rejects_invalid_contracts(
    mutation: str, expected_code: str
) -> None:
    engagement, plan, _ = _values()
    del engagement
    if mutation == "unsupported_schema":
        plan["schema_version"] = "contextsafe.plan/2.0.0"
    elif mutation == "empty_hosts":
        plan["target_hosts"] = []
    elif mutation == "duplicate_host":
        plan["target_hosts"].append(plan["target_hosts"][0])
    elif mutation == "unsupported_checkpoint":
        plan["checkpoints"][0] = "unsupported"
    elif mutation == "duplicate_checkpoint":
        plan["checkpoints"][0] = plan["checkpoints"][1]
    elif mutation == "empty_cases":
        plan["case_tokens"] = []
    elif mutation == "duplicate_case":
        plan["case_tokens"].append(plan["case_tokens"][0])
    else:
        plan["valid_from"] = "2026-08-02"

    with pytest.raises(ContextSafeError) as raised:
        parse_plan(plan)

    assert raised.value.code == expected_code


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("engagement_expired", "engagement_not_current"),
        ("plan_not_started", "plan_not_current"),
        ("engagement_id", "engagement_id_mismatch"),
        ("namespace_system", "namespace_mismatch"),
    ],
)
def test_plan_rejects_additional_date_pin_and_namespace_drift(
    mutation: str, expected_code: str
) -> None:
    engagement, plan, pack = _values()
    if mutation == "engagement_expired":
        engagement["review_by"] = "2026-07-12"
        engagement["cleanup"]["due_on"] = "2026-07-12"
    elif mutation == "plan_not_started":
        plan["valid_from"] = "2026-07-14"
    elif mutation == "engagement_id":
        plan["engagement_id"] = "ENG-OTHER-TEST"
    else:
        plan["synthetic_namespace"]["system"] = "urn:contextsafe:wrong"

    with pytest.raises(ContextSafeError) as raised:
        validate_plan(engagement, plan, pack=pack, as_of=AS_OF)

    assert raised.value.code == expected_code


def test_plan_rejects_expired_cleanup_deadline_independently() -> None:
    pack = _compiled_pack()
    engagement = _engagement()
    engagement["cleanup"]["due_on"] = "2026-07-12"
    plan = _plan(engagement, pack)

    with pytest.raises(ContextSafeError) as raised:
        validate_plan(engagement, plan, pack=pack, as_of=AS_OF)

    assert raised.value.code == "cleanup_deadline_expired"


def test_plan_rejects_cleanup_deadline_before_plan_end() -> None:
    pack = _compiled_pack()
    engagement = _engagement()
    engagement["cleanup"]["due_on"] = "2026-07-20"
    plan = _plan(engagement, pack)

    with pytest.raises(ContextSafeError) as raised:
        validate_plan(engagement, plan, pack=pack, as_of=AS_OF)

    assert raised.value.code == "cleanup_deadline_before_plan_end"


def test_plan_pins_exact_compiled_pack_payload() -> None:
    engagement, plan, pack = _values()
    changed_sources = copy.deepcopy(pack.source_manifest)
    changed_sources[0]["limitations"] = ["changed-but-valid"]
    changed_pack = replace(pack, source_manifest=changed_sources)

    with pytest.raises(ContextSafeError) as raised:
        validate_plan(engagement, plan, pack=changed_pack, as_of=AS_OF)

    assert raised.value.code == "compiled_pack_pin_mismatch"


def test_plan_rejects_compiled_pack_mutated_after_hashing() -> None:
    engagement, plan, pack = _values()
    pack.case_manifest[0]["synthetic_identifier"]["value"] = "CSYN-CTP-Z99"

    with pytest.raises(ContextSafeError) as raised:
        validate_plan(engagement, plan, pack=pack, as_of=AS_OF)

    assert raised.value.code == "compiled_pack_hash_mismatch"


@pytest.mark.parametrize(
    "host",
    [
        "127.0.0.1",
        "2130706433",
        "127.1",
        "0177.0.0.1",
        "0x7f.0.0.1",
        "::1",
        "0:0:0:0:0:0:0:1",
        "::ffff:127.0.0.1",
    ],
)
def test_plan_contract_schemas_reject_all_ip_literal_forms(host: str) -> None:
    engagement, plan, pack = _values()
    compiled = validate_plan(engagement, plan, pack=pack, as_of=AS_OF).to_dict()
    engagement["allowed_hosts"] = [host]
    plan["target_hosts"] = [host]
    compiled["target_hosts"] = [host]

    for schema_name, value in (
        ("contextsafe-engagement-v1.schema.json", engagement),
        ("contextsafe-plan-v1.schema.json", plan),
        ("contextsafe-compiled-plan-v1.schema.json", compiled),
    ):
        assert not Draft202012Validator(_schema(schema_name)).is_valid(value)
