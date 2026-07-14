"""Pack compiler governance, compatibility, and determinism tests."""

import copy
import itertools
import json
import shutil
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from contextsafe.canonical import canonical_json, sha256_json
from contextsafe.cli import main
from contextsafe.errors import ContextSafeError
from contextsafe.jsonio import load_json
from contextsafe.pack import (
    ApprovalRole,
    approval_subject_sha256,
    compile_pack,
    parse_pack,
)
from contextsafe.validation import parse_case, parse_rule_set

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "fixtures" / "reference"
AS_OF = date(2026, 7, 13)

_TEST_REVIEWERS = {
    ApprovalRole.CLINICAL_SAFETY_CHAIR.value: "TEST-CLINICAL-ROLE",
    ApprovalRole.COMMUNITY_CO_CHAIR.value: "TEST-COMMUNITY-ROLE",
    ApprovalRole.TECHNICAL_RELEASE_OWNER.value: "TEST-TECHNICAL-ROLE",
}


def _bind_test_approvals(pack: dict[str, Any]) -> None:
    """Create test-only declarations; these are not governance evidence."""

    pack["approvals"] = []
    subject = approval_subject_sha256(parse_pack(pack))
    pack["approvals"] = [
        {
            "decided_on": "2026-07-10",
            "decision": "approved",
            "review_by": "2026-12-31",
            "reviewer_id": _TEST_REVIEWERS[role.value],
            "role": role.value,
            "subject_sha256": subject,
            "withdrawn_on": None,
        }
        for role in ApprovalRole
    ]


def _valid_pack() -> dict[str, Any]:
    case = parse_case(load_json(REFERENCE / "case.json"))
    rules = parse_rule_set(load_json(REFERENCE / "rules.json"))
    pack: dict[str, Any] = {
        "approvals": [],
        "compatibility": {
            "case_schema": "contextsafe.case/0.1.0",
            "rule_set_schema": "contextsafe.rule-set/0.1.0",
            "runner_contract": "contextsafe.runner/0.1",
        },
        "components": {
            "cases": [
                {
                    "component_id": case.case_id,
                    "mandatory": True,
                    "path": "case.json",
                    "sha256": sha256_json(case.to_dict()),
                }
            ],
            "rule_sets": [
                {
                    "component_id": "RULESET-SYNTHETIC-TEST",
                    "mandatory": True,
                    "path": "rules.json",
                    "sha256": sha256_json(rules.to_dict()),
                }
            ],
        },
        "lifecycle": {
            "review_by": "2026-12-31",
            "status": "active",
            "valid_from": "2026-07-01",
            "withdrawn_on": None,
        },
        "pack_id": "PACK-SYNTHETIC-TEST",
        "schema_version": "contextsafe.pack/1.0.0",
        "sources": [
            {
                "limitations": ["synthetic-reference-only"],
                "retrieved_on": "2026-07-01",
                "review_by": "2026-12-31",
                "reviewed_on": "2026-07-02",
                "sha256": sha256_json(rules.to_dict()),
                "source_id": "SRC-SYNTHETIC-TEST",
                "status": "active",
                "uri": "urn:contextsafe:source:synthetic-reference",
                "version": "0.1.0",
                "withdrawn_on": None,
            }
        ],
        "version": "1.0.0",
    }
    _bind_test_approvals(pack)
    return pack


def _schema(name: str) -> dict[str, Any]:
    return json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))


def _copy_components(destination: Path, *, reverse_rules: bool = False) -> None:
    shutil.copyfile(REFERENCE / "case.json", destination / "case.json")
    rules = json.loads((REFERENCE / "rules.json").read_text(encoding="utf-8"))
    if reverse_rules:
        rules["rules"].reverse()
    (destination / "rules.json").write_text(json.dumps(rules), encoding="utf-8")


def test_pack_and_compilation_conform_to_schemas() -> None:
    pack = _valid_pack()
    pack_validator = Draft202012Validator(_schema("contextsafe-pack-v1.schema.json"))
    compiled_validator = Draft202012Validator(
        _schema("contextsafe-compiled-pack-v1.schema.json")
    )
    pack_validator.validate(pack)

    compiled = compile_pack(pack, root=REFERENCE, as_of=AS_OF).to_dict()

    compiled_validator.validate(compiled)
    assert compiled["declared_controls_status"] == "pass"
    assert compiled["valid_for_signing"] is True
    assert compiled["signature_status"] == "not_verified"
    assert compiled["executable"] is False
    assert compiled["case_manifest"][0]["synthetic_identifier"]["system"] == (
        "urn:contextsafe:synthetic"
    )


def test_committed_reference_pack_is_explicitly_draft_and_blocked() -> None:
    draft = load_json(REFERENCE / "pack-draft.json")
    Draft202012Validator(_schema("contextsafe-pack-v1.schema.json")).validate(draft)

    with pytest.raises(ContextSafeError) as raised:
        compile_pack(draft, root=REFERENCE, as_of=AS_OF)

    assert raised.value.code == "pack_not_active"


def test_pack_compilation_is_invariant_to_permuted_approval_and_rule_order(
    tmp_path: Path,
) -> None:
    pack = _valid_pack()
    baseline = canonical_json(compile_pack(pack, root=REFERENCE, as_of=AS_OF).to_dict())
    _copy_components(tmp_path, reverse_rules=True)

    for approvals in itertools.permutations(pack["approvals"]):
        candidate = copy.deepcopy(pack)
        candidate["approvals"] = list(approvals)
        actual = canonical_json(
            compile_pack(candidate, root=tmp_path, as_of=AS_OF).to_dict()
        )
        assert actual == baseline


@pytest.mark.parametrize(
    ("section", "field", "value", "expected_code"),
    [
        ("lifecycle", "status", "draft", "pack_not_active"),
        ("lifecycle", "review_by", "2026-07-12", "pack_expired"),
        ("sources", "status", "draft", "source_not_active"),
        ("sources", "review_by", "2026-07-12", "source_review_expired"),
        (
            "compatibility",
            "runner_contract",
            "contextsafe.runner/9.9",
            "incompatible_pack",
        ),
    ],
)
def test_pack_rejects_inactive_expired_or_incompatible_content(
    section: str, field: str, value: str, expected_code: str
) -> None:
    pack = _valid_pack()
    target = pack[section]
    if section == "sources":
        target = target[0]
    target[field] = value

    with pytest.raises(ContextSafeError) as raised:
        compile_pack(pack, root=REFERENCE, as_of=AS_OF)

    assert raised.value.code == expected_code


def test_pack_rejects_withdrawn_pack_source_and_approval() -> None:
    pack = _valid_pack()
    pack["lifecycle"].update({"status": "withdrawn", "withdrawn_on": "2026-07-11"})
    with pytest.raises(ContextSafeError, match="withdrawn pack") as raised:
        compile_pack(pack, root=REFERENCE, as_of=AS_OF)
    assert raised.value.code == "pack_withdrawn"

    pack = _valid_pack()
    pack["sources"][0].update({"status": "withdrawn", "withdrawn_on": "2026-07-11"})
    with pytest.raises(ContextSafeError) as raised:
        compile_pack(pack, root=REFERENCE, as_of=AS_OF)
    assert raised.value.code == "source_withdrawn"

    pack = _valid_pack()
    pack["approvals"][0]["withdrawn_on"] = "2026-07-11"
    with pytest.raises(ContextSafeError) as raised:
        compile_pack(pack, root=REFERENCE, as_of=AS_OF)
    assert raised.value.code == "approval_withdrawn"


@pytest.mark.parametrize(
    "mutation,expected_code",
    [
        ("missing", "missing_approval"),
        ("rejected", "approval_not_granted"),
        ("stale", "approval_subject_mismatch"),
        ("expired", "approval_expired"),
    ],
)
def test_pack_rejects_incomplete_or_invalid_approval_declarations(
    mutation: str, expected_code: str
) -> None:
    pack = _valid_pack()
    if mutation == "missing":
        pack["approvals"].pop()
    elif mutation == "rejected":
        pack["approvals"][0]["decision"] = "rejected"
    elif mutation == "stale":
        pack["approvals"][0]["subject_sha256"] = "0" * 64
    else:
        pack["approvals"][0]["review_by"] = "2026-07-12"

    with pytest.raises(ContextSafeError) as raised:
        compile_pack(pack, root=REFERENCE, as_of=AS_OF)

    assert raised.value.code == expected_code


def test_pack_rejects_component_hash_tampering() -> None:
    pack = _valid_pack()
    pack["components"]["cases"][0]["sha256"] = "0" * 64

    with pytest.raises(ContextSafeError) as raised:
        compile_pack(pack, root=REFERENCE, as_of=AS_OF)

    assert raised.value.code == "component_hash_mismatch"


def test_pack_rejects_component_symlink_escape(tmp_path: Path) -> None:
    pack = _valid_pack()
    (tmp_path / "case.json").symlink_to(REFERENCE / "case.json")
    (tmp_path / "rules.json").symlink_to(REFERENCE / "rules.json")

    with pytest.raises(ContextSafeError) as raised:
        compile_pack(pack, root=tmp_path, as_of=AS_OF)

    assert raised.value.code == "component_path_escape"


def test_pack_rejects_rules_for_a_case_outside_the_pack(tmp_path: Path) -> None:
    pack = _valid_pack()
    _copy_components(tmp_path)
    rules = json.loads((tmp_path / "rules.json").read_text(encoding="utf-8"))
    for rule in rules["rules"]:
        rule["case_id"] = "CTP-Z99"
    (tmp_path / "rules.json").write_text(json.dumps(rules), encoding="utf-8")
    parsed_rules = parse_rule_set(load_json(tmp_path / "rules.json"))
    pack["components"]["rule_sets"][0]["sha256"] = sha256_json(parsed_rules.to_dict())
    _bind_test_approvals(pack)

    with pytest.raises(ContextSafeError) as raised:
        compile_pack(pack, root=tmp_path, as_of=AS_OF)

    assert raised.value.code == "rule_case_missing"


def test_pack_cli_emits_unsigned_compilation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _copy_components(tmp_path)
    pack_path = tmp_path / "pack.json"
    pack_path.write_text(json.dumps(_valid_pack()), encoding="utf-8")

    exit_code = main(
        ["pack", "validate", "--pack", str(pack_path), "--as-of", "2026-07-13"]
    )

    captured = capsys.readouterr()
    output = json.loads(captured.out)
    assert exit_code == 0
    assert captured.err == ""
    assert output["valid_for_signing"] is True
    assert output["signature_status"] == "not_verified"
    assert output["executable"] is False


def test_pack_cli_fails_closed_on_missing_approval(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _copy_components(tmp_path)
    pack = _valid_pack()
    pack["approvals"].pop()
    pack_path = tmp_path / "pack.json"
    pack_path.write_text(json.dumps(pack), encoding="utf-8")

    exit_code = main(
        ["pack", "validate", "--pack", str(pack_path), "--as-of", "2026-07-13"]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert json.loads(captured.err)["error"]["code"] == "missing_approval"


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("unsupported_schema", "unsupported_schema"),
        ("empty_cases", "invalid_component_count"),
        ("no_mandatory_case", "missing_mandatory_component"),
        ("duplicate_component_id", "duplicate_component_id"),
        ("duplicate_component_path", "duplicate_component_path"),
        ("empty_sources", "invalid_source_count"),
        ("duplicate_source_id", "duplicate_source_id"),
        ("too_many_approvals", "invalid_approval_count"),
        ("duplicate_approval_role", "duplicate_approval_role"),
    ],
)
def test_pack_parser_rejects_invalid_collection_contracts(
    mutation: str, expected_code: str
) -> None:
    pack = _valid_pack()
    if mutation == "unsupported_schema":
        pack["schema_version"] = "contextsafe.pack/2.0.0"
    elif mutation == "empty_cases":
        pack["components"]["cases"] = []
    elif mutation == "no_mandatory_case":
        pack["components"]["cases"][0]["mandatory"] = False
    elif mutation == "duplicate_component_id":
        pack["components"]["cases"].append(
            copy.deepcopy(pack["components"]["cases"][0])
        )
        pack["components"]["cases"][1]["path"] = "other-case.json"
    elif mutation == "duplicate_component_path":
        duplicate = copy.deepcopy(pack["components"]["cases"][0])
        duplicate["component_id"] = "CTP-Z99"
        pack["components"]["cases"].append(duplicate)
    elif mutation == "empty_sources":
        pack["sources"] = []
    elif mutation == "duplicate_source_id":
        pack["sources"].append(copy.deepcopy(pack["sources"][0]))
    elif mutation == "too_many_approvals":
        pack["approvals"].append(copy.deepcopy(pack["approvals"][0]))
    elif mutation == "duplicate_approval_role":
        pack["approvals"][2]["role"] = pack["approvals"][0]["role"]

    with pytest.raises(ContextSafeError) as raised:
        parse_pack(pack)

    assert raised.value.code == expected_code


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("inverted_lifecycle", "invalid_validity"),
        ("lifecycle_date_without_state", "invalid_withdrawal"),
        ("withdrawal_before_validity", "invalid_withdrawal"),
        ("source_date_without_state", "invalid_withdrawal"),
        ("source_review_before_retrieval", "invalid_source_dates"),
        ("source_review_interval_inverted", "invalid_source_dates"),
    ],
)
def test_pack_parser_rejects_invalid_lifecycle_and_source_dates(
    mutation: str, expected_code: str
) -> None:
    pack = _valid_pack()
    if mutation == "inverted_lifecycle":
        pack["lifecycle"]["valid_from"] = "2027-01-01"
    elif mutation == "lifecycle_date_without_state":
        pack["lifecycle"]["withdrawn_on"] = "2026-07-11"
    elif mutation == "withdrawal_before_validity":
        pack["lifecycle"].update({"status": "withdrawn", "withdrawn_on": "2026-06-30"})
    elif mutation == "source_date_without_state":
        pack["sources"][0]["withdrawn_on"] = "2026-07-11"
    elif mutation == "source_review_before_retrieval":
        pack["sources"][0]["reviewed_on"] = "2026-06-30"
    elif mutation == "source_review_interval_inverted":
        pack["sources"][0]["review_by"] = "2026-07-01"

    with pytest.raises(ContextSafeError) as raised:
        parse_pack(pack)

    assert raised.value.code == expected_code


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("invalid_pending_fields", "invalid_pending_approval"),
        ("incomplete_approval", "incomplete_approval"),
        ("inverted_approval", "invalid_approval_dates"),
        ("approval_withdrawn_before_decision", "invalid_withdrawal"),
    ],
)
def test_pack_parser_rejects_invalid_approval_state(
    mutation: str, expected_code: str
) -> None:
    pack = _valid_pack()
    if mutation == "invalid_pending_fields":
        pack["approvals"][0]["decision"] = "pending"
    elif mutation == "incomplete_approval":
        pack["approvals"][0]["reviewer_id"] = None
    elif mutation == "inverted_approval":
        pack["approvals"][0]["review_by"] = "2026-07-01"
    else:
        pack["approvals"][0]["withdrawn_on"] = "2026-07-01"

    with pytest.raises(ContextSafeError) as raised:
        parse_pack(pack)

    assert raised.value.code == expected_code


def test_pending_approval_with_null_fields_parses_but_cannot_compile() -> None:
    pack = _valid_pack()
    pack["approvals"][0].update(
        {
            "decision": "pending",
            "reviewer_id": None,
            "decided_on": None,
            "review_by": None,
            "subject_sha256": None,
            "withdrawn_on": None,
        }
    )
    parse_pack(pack)

    with pytest.raises(ContextSafeError) as raised:
        compile_pack(pack, root=REFERENCE, as_of=AS_OF)

    assert raised.value.code == "approval_not_granted"


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("not_yet_valid", "pack_not_yet_valid"),
        ("source_review_missing", "source_review_missing"),
        ("source_retrieval_future", "source_retrieval_in_future"),
        ("source_review_future", "source_review_in_future"),
        ("approval_decision_future", "approval_not_yet_valid"),
        ("case_id_mismatch", "component_id_mismatch"),
        ("rule_hash_mismatch", "component_hash_mismatch"),
    ],
)
def test_pack_compiler_rejects_additional_stale_or_tampered_states(
    mutation: str, expected_code: str
) -> None:
    pack = _valid_pack()
    if mutation == "not_yet_valid":
        pack["lifecycle"]["valid_from"] = "2026-07-14"
    elif mutation == "source_review_missing":
        pack["sources"][0].update({"reviewed_on": None, "review_by": None})
    elif mutation == "source_retrieval_future":
        pack["sources"][0]["retrieved_on"] = "2026-07-14"
        pack["sources"][0]["reviewed_on"] = "2026-07-14"
    elif mutation == "source_review_future":
        pack["sources"][0]["reviewed_on"] = "2026-07-14"
    elif mutation == "approval_decision_future":
        pack["approvals"][0]["decided_on"] = "2026-07-14"
    elif mutation == "case_id_mismatch":
        pack["components"]["cases"][0]["component_id"] = "CTP-Z99"
    else:
        pack["components"]["rule_sets"][0]["sha256"] = "0" * 64

    with pytest.raises(ContextSafeError) as raised:
        compile_pack(pack, root=REFERENCE, as_of=AS_OF)

    assert raised.value.code == expected_code
