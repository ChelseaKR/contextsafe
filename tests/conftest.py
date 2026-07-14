"""Shared copies of the bundled synthetic reference inputs."""

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

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

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "fixtures" / "reference"


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
            "system_version": "fixture-1.0",
        }
    )
