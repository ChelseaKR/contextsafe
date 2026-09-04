"""Shared copies of the bundled synthetic reference inputs."""

import copy
import json
from collections.abc import Callable
from datetime import date
from typing import Any

import pytest

from contextsafe.evaluator import evaluate
from contextsafe.evidence import (
    CANONICAL_JSON_MEDIA_TYPE,
    CANONICAL_JSON_SOURCE_TYPE,
    EvidenceMetadata,
    EvidenceScope,
    build_evidence_scope,
    parse_evidence_metadata,
)
from contextsafe.models import Checkpoint
from contextsafe.plan import (
    CleanupContract,
    EnvironmentContract,
    ExecutionPlan,
    PlanOwners,
    SyntheticNamespace,
)
from contextsafe.receipt import build_receipt_document
from contextsafe.reference_fixtures import REFERENCE_ROOT
from contextsafe.validation import parse_bundle

REFERENCE = REFERENCE_ROOT

FINDING_OUTCOME: dict[str, str] = {
    "rule_id": "A-I05",
    "case_id": "CTP-I01",
    "checkpoint": "ehr",
    "concept": "pronouns",
}
"""The one outcome ``finding_receipt`` records as ``fail``."""

CHAIR_SIGNER: dict[str, str] = {
    "role": "contextsafe_clinical_safety_chair",
    "organization_id": "ORG-CONTEXTSAFE-TEST",
    "signature_status": "not_verified",
}
CUSTOMER_SIGNER: dict[str, str] = {
    "role": "customer_clinical_owner",
    "organization_id": "ORG-CUSTOMER-TEST",
    "signature_status": "not_verified",
}
"""Visibly test-only declared signers. Neither is a signature of anything."""

_EVENT_DEFAULTS: dict[str, dict[str, Any]] = {
    "confirmed": {
        "severity": "cs2_high",
        "owner": None,
        "rationale_code": "evidence_verified_against_source",
        "signers": [CHAIR_SIGNER],
    },
    "rejected": {
        "severity": None,
        "owner": None,
        "rationale_code": "evidence_not_reproducible",
        "signers": [CHAIR_SIGNER],
    },
    "severity_changed": {
        "severity": "cs3_moderate",
        "owner": None,
        "rationale_code": "severity_rubric_applied",
        "signers": [CHAIR_SIGNER],
    },
    "owner_assigned": {
        "severity": None,
        "owner": {"role": "customer_technical_owner", "token_sha256": "a" * 64},
        "rationale_code": "ownership_assigned_by_plan_role",
        "signers": [CUSTOMER_SIGNER],
    },
    "remediated": {
        "severity": None,
        "owner": None,
        "rationale_code": "remediation_verified_by_rerun",
        "signers": [CHAIR_SIGNER],
    },
    "accepted_residual_risk": {
        "severity": "cs2_high",
        "owner": None,
        "rationale_code": "residual_risk_bounded_by_disposition",
        "signers": [CUSTOMER_SIGNER, CHAIR_SIGNER],
    },
    "withdrawn": {
        "severity": None,
        "owner": None,
        "rationale_code": "entered_in_error",
        "signers": [CHAIR_SIGNER],
    },
}
"""A shape-valid event for every published decision."""


def _read_json(name: str) -> dict[str, Any]:
    value = json.loads((REFERENCE / name).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


@pytest.fixture
def case_json() -> dict[str, Any]:
    """Return a fresh canonical case object."""

    return _read_json("case.json")


@pytest.fixture
def observations_json() -> dict[str, Any]:
    """Return a fresh canonical observation-set object."""

    return _read_json("observations.json")


@pytest.fixture
def rules_json() -> dict[str, Any]:
    """Return a fresh rule-set object."""

    return _read_json("rules.json")


@pytest.fixture
def evidence_source_json() -> dict[str, Any]:
    """Return a fresh code-only boundary envelope."""

    return _read_json("evidence-source.json")


@pytest.fixture
def execution_plan() -> ExecutionPlan:
    """Return a parsed-shape, visibly synthetic unsigned execution plan."""

    environment = EnvironmentContract(
        classification="staging",
        name="SYNTHETIC-STAGING-A",
        non_production_attested=True,
        production_access_prohibited=True,
    )
    owners = PlanOwners(
        technical_owner_id="TEST-TECHNICAL-OWNER",
        clinical_owner_id="TEST-CLINICAL-OWNER",
        privacy_owner_id="TEST-PRIVACY-OWNER",
        cleanup_owner_id="TEST-CLEANUP-OWNER",
    )
    cleanup = CleanupContract(
        owner_id=owners.cleanup_owner_id,
        system_ids=("SYS-STAGING-EHR",),
        due_on=date(2026, 8, 1),
    )
    return ExecutionPlan(
        schema_version="contextsafe.plan/1.0.0",
        plan_id="PLAN-SYNTHETIC-TEST",
        engagement_id="ENG-SYNTHETIC-TEST",
        engagement_sha256="1" * 64,
        compiled_pack_sha256="2" * 64,
        environment=environment,
        target_hosts=("staging.contextsafe.invalid",),
        synthetic_namespace=SyntheticNamespace(
            system="urn:contextsafe:synthetic", value_prefix="CSYN-"
        ),
        owners=owners,
        cleanup=cleanup,
        checkpoints=tuple(Checkpoint),
        case_tokens=("CSYN-CTP-I01",),
        valid_from=date(2026, 7, 13),
        valid_until=date(2026, 8, 1),
    )


@pytest.fixture
def evidence_scope(execution_plan: ExecutionPlan) -> EvidenceScope:
    """Bind the reference source to its synthetic EHR checkpoint."""

    return build_evidence_scope(
        execution_plan,
        case_token=execution_plan.case_tokens[0],
        checkpoint="ehr",
        source_type=CANONICAL_JSON_SOURCE_TYPE,
        media_type=CANONICAL_JSON_MEDIA_TYPE,
    )


@pytest.fixture
def evidence_metadata() -> EvidenceMetadata:
    """Return deterministic, opaque provenance for store tests."""

    return parse_evidence_metadata(
        {
            "captured_at": "2026-07-13T12:00:00Z",
            "collector_id": "TEST-COLLECTOR",
            "system_id": "SYS-STAGING-EHR",
            "system_version": "1.0.0",
        }
    )


@pytest.fixture
def finding_receipt(
    case_json: dict[str, Any],
    observations_json: dict[str, Any],
    rules_json: dict[str, Any],
) -> dict[str, Any]:
    """A receipt document with exactly one ``fail`` outcome, ``FINDING_OUTCOME``.

    The pronoun observation is contradicted so that a finding exists to review;
    the other four outcomes pass and are therefore not reviewable.
    """

    observations_json["observations"][4]["value"]["value"] = "ze/hir"
    bundle = parse_bundle(case_json, observations_json, rules_json)
    return build_receipt_document(bundle, evaluate(bundle))


@pytest.fixture
def review_event(
    finding_receipt: dict[str, Any],
) -> Callable[..., dict[str, Any]]:
    """Build a shape-valid review event for a decision, bound to that receipt."""

    def build(decision: str, **overrides: Any) -> dict[str, Any]:
        event: dict[str, Any] = {
            "schema_version": "contextsafe.review-event/1.0.0",
            "outcome": dict(FINDING_OUTCOME),
            "receipt": {
                "payload_sha256": finding_receipt["payload_sha256"],
                "rule_set_sha256": finding_receipt["payload"]["hashes"][
                    "rule_set_sha256"
                ],
            },
            "decision": decision,
            "external_reference": None,
            "signature_status": "not_verified",
            **copy.deepcopy(_EVENT_DEFAULTS[decision]),
        }
        event.update(overrides)
        return event

    return build
