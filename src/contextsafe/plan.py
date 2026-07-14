"""Fail-closed, offline engagement and execution-plan validation."""

import re
from dataclasses import dataclass
from datetime import date

from contextsafe.canonical import JsonValue, as_json_value, sha256_json
from contextsafe.contract_validation import (
    ID_PATTERN,
    SAFE_TOKEN_PATTERN,
    SHA256_PATTERN,
    array_value,
    boolean_value,
    bounded_string,
    contract_error,
    date_value,
    exact_keys,
    host_value,
    object_value,
    unique_strings,
)
from contextsafe.models import Checkpoint
from contextsafe.pack import PackCompilation, validate_compiled_pack

ENGAGEMENT_SCHEMA_VERSION = "contextsafe.engagement/1.0.0"
PLAN_SCHEMA_VERSION = "contextsafe.plan/1.0.0"
COMPILED_PLAN_SCHEMA_VERSION = "contextsafe.compiled-plan/1.0.0"
SYNTHETIC_IDENTIFIER_SYSTEM = "urn:contextsafe:synthetic"
SYNTHETIC_VALUE_PREFIX = "CSYN-"

_ENVIRONMENT_CLASSIFICATIONS = frozenset({"sandbox", "staging", "test"})
_CASE_TOKEN_PATTERN = re.compile(r"^CSYN-CTP-[A-Z0-9]{3,16}$")
_CHECKPOINTS = frozenset(Checkpoint)
_OWNER_FIELDS = frozenset(
    {
        "technical_owner_id",
        "clinical_owner_id",
        "privacy_owner_id",
        "cleanup_owner_id",
    }
)


@dataclass(frozen=True, slots=True)
class EnvironmentContract:
    """Explicit non-production environment attestation."""

    classification: str
    name: str
    non_production_attested: bool
    production_access_prohibited: bool

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "classification": self.classification,
            "name": self.name,
            "non_production_attested": self.non_production_attested,
            "production_access_prohibited": self.production_access_prohibited,
        }


@dataclass(frozen=True, slots=True)
class SyntheticNamespace:
    """The only identifier namespace usable by the bounded V1 plan."""

    system: str
    value_prefix: str

    def to_dict(self) -> dict[str, JsonValue]:
        return {"system": self.system, "value_prefix": self.value_prefix}


@dataclass(frozen=True, slots=True)
class PlanOwners:
    """Opaque role IDs required for execution and cleanup accountability."""

    technical_owner_id: str
    clinical_owner_id: str
    privacy_owner_id: str
    cleanup_owner_id: str

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "cleanup_owner_id": self.cleanup_owner_id,
            "clinical_owner_id": self.clinical_owner_id,
            "privacy_owner_id": self.privacy_owner_id,
            "technical_owner_id": self.technical_owner_id,
        }


@dataclass(frozen=True, slots=True)
class CleanupContract:
    """Owner, systems, and deadline for post-run synthetic-data cleanup."""

    owner_id: str
    system_ids: tuple[str, ...]
    due_on: date

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "due_on": self.due_on.isoformat(),
            "owner_id": self.owner_id,
            "system_ids": as_json_value(sorted(self.system_ids)),
        }


@dataclass(frozen=True, slots=True)
class EngagementContract:
    """Partner-approved boundary that a plan must match exactly."""

    schema_version: str
    engagement_id: str
    partner_profile_id: str
    environment: EnvironmentContract
    allowed_hosts: tuple[str, ...]
    synthetic_namespace: SyntheticNamespace
    owners: PlanOwners
    cleanup: CleanupContract
    valid_from: date
    review_by: date

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "allowed_hosts": as_json_value(sorted(self.allowed_hosts)),
            "cleanup": self.cleanup.to_dict(),
            "engagement_id": self.engagement_id,
            "environment": self.environment.to_dict(),
            "owners": self.owners.to_dict(),
            "partner_profile_id": self.partner_profile_id,
            "review_by": self.review_by.isoformat(),
            "schema_version": self.schema_version,
            "synthetic_namespace": self.synthetic_namespace.to_dict(),
            "valid_from": self.valid_from.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class ExecutionPlan:
    """Unsigned execution intent pinned to one engagement and compiled pack."""

    schema_version: str
    plan_id: str
    engagement_id: str
    engagement_sha256: str
    compiled_pack_sha256: str
    environment: EnvironmentContract
    target_hosts: tuple[str, ...]
    synthetic_namespace: SyntheticNamespace
    owners: PlanOwners
    cleanup: CleanupContract
    checkpoints: tuple[Checkpoint, ...]
    case_tokens: tuple[str, ...]
    valid_from: date
    valid_until: date

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "case_tokens": as_json_value(sorted(self.case_tokens)),
            "checkpoints": as_json_value(
                sorted(item.value for item in self.checkpoints)
            ),
            "cleanup": self.cleanup.to_dict(),
            "engagement_id": self.engagement_id,
            "engagement_sha256": self.engagement_sha256,
            "environment": self.environment.to_dict(),
            "owners": self.owners.to_dict(),
            "compiled_pack_sha256": self.compiled_pack_sha256,
            "plan_id": self.plan_id,
            "schema_version": self.schema_version,
            "synthetic_namespace": self.synthetic_namespace.to_dict(),
            "target_hosts": as_json_value(sorted(self.target_hosts)),
            "valid_from": self.valid_from.isoformat(),
            "valid_until": self.valid_until.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class PlanCompilation:
    """Canonical unsigned plan artifact eligible for a future signing step."""

    as_of: date
    plan: ExecutionPlan
    plan_sha256: str

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "as_of": self.as_of.isoformat(),
            "case_tokens": as_json_value(sorted(self.plan.case_tokens)),
            "checkpoints": as_json_value(
                sorted(item.value for item in self.plan.checkpoints)
            ),
            "cleanup": self.plan.cleanup.to_dict(),
            "declared_controls_status": "pass",
            "engagement_id": self.plan.engagement_id,
            "engagement_sha256": self.plan.engagement_sha256,
            "environment": self.plan.environment.to_dict(),
            "executable": False,
            "limitations": [
                "plan-is-unsigned",
                "network-execution-is-out-of-scope",
                "cryptographic-authorization-requires-b-035",
            ],
            "network_actions_performed": False,
            "owners": self.plan.owners.to_dict(),
            "compiled_pack_sha256": self.plan.compiled_pack_sha256,
            "plan_id": self.plan.plan_id,
            "plan_sha256": self.plan_sha256,
            "schema_version": COMPILED_PLAN_SCHEMA_VERSION,
            "signature_status": "not_verified",
            "synthetic_namespace": self.plan.synthetic_namespace.to_dict(),
            "target_hosts": as_json_value(sorted(self.plan.target_hosts)),
            "valid_for_signing": True,
            "valid_from": self.plan.valid_from.isoformat(),
            "valid_until": self.plan.valid_until.isoformat(),
        }


def _parse_environment(value: object, path: str) -> EnvironmentContract:
    data = object_value(value, path)
    exact_keys(
        data,
        frozenset(
            {
                "classification",
                "name",
                "non_production_attested",
                "production_access_prohibited",
            }
        ),
        path,
    )
    classification = bounded_string(data["classification"], f"{path}.classification")
    if classification == "production":
        raise contract_error(
            "production_environment",
            f"{path}.classification",
            "production environments are prohibited",
        )
    if classification not in _ENVIRONMENT_CLASSIFICATIONS:
        raise contract_error(
            "unsupported_environment",
            f"{path}.classification",
            "environment classification is unsupported",
        )
    attested = boolean_value(
        data["non_production_attested"], f"{path}.non_production_attested"
    )
    prohibited = boolean_value(
        data["production_access_prohibited"],
        f"{path}.production_access_prohibited",
    )
    if not attested or not prohibited:
        raise contract_error(
            "non_production_attestation_missing",
            path,
            "both non-production controls must be true",
        )
    return EnvironmentContract(
        classification=classification,
        name=bounded_string(data["name"], f"{path}.name", pattern=SAFE_TOKEN_PATTERN),
        non_production_attested=attested,
        production_access_prohibited=prohibited,
    )


def _parse_namespace(value: object, path: str) -> SyntheticNamespace:
    data = object_value(value, path)
    exact_keys(data, frozenset({"system", "value_prefix"}), path)
    namespace = SyntheticNamespace(
        system=bounded_string(data["system"], f"{path}.system"),
        value_prefix=bounded_string(data["value_prefix"], f"{path}.value_prefix"),
    )
    if (
        namespace.system != SYNTHETIC_IDENTIFIER_SYSTEM
        or namespace.value_prefix != SYNTHETIC_VALUE_PREFIX
    ):
        raise contract_error(
            "namespace_mismatch",
            path,
            "the fixed ContextSafe synthetic namespace is required",
        )
    return namespace


def _parse_owners(value: object, path: str) -> PlanOwners:
    data = object_value(value, path)
    missing = _OWNER_FIELDS - data.keys()
    if missing:
        raise contract_error(
            "missing_owner", path, "every required owner role must be assigned"
        )
    exact_keys(data, _OWNER_FIELDS, path)
    return PlanOwners(
        technical_owner_id=bounded_string(
            data["technical_owner_id"],
            f"{path}.technical_owner_id",
            pattern=SAFE_TOKEN_PATTERN,
        ),
        clinical_owner_id=bounded_string(
            data["clinical_owner_id"],
            f"{path}.clinical_owner_id",
            pattern=SAFE_TOKEN_PATTERN,
        ),
        privacy_owner_id=bounded_string(
            data["privacy_owner_id"],
            f"{path}.privacy_owner_id",
            pattern=SAFE_TOKEN_PATTERN,
        ),
        cleanup_owner_id=bounded_string(
            data["cleanup_owner_id"],
            f"{path}.cleanup_owner_id",
            pattern=SAFE_TOKEN_PATTERN,
        ),
    )


def _parse_cleanup(value: object, path: str) -> CleanupContract:
    data = object_value(value, path)
    exact_keys(data, frozenset({"owner_id", "system_ids", "due_on"}), path)
    raw_systems = array_value(data["system_ids"], f"{path}.system_ids")
    if not raw_systems or len(raw_systems) > 20:
        raise contract_error(
            "invalid_cleanup_scope",
            f"{path}.system_ids",
            "cleanup systems are outside the supported bound",
        )
    systems = tuple(
        bounded_string(item, f"{path}.system_ids[{index}]", pattern=ID_PATTERN)
        for index, item in enumerate(raw_systems)
    )
    unique_strings(systems, f"{path}.system_ids", code="duplicate_cleanup_system")
    return CleanupContract(
        owner_id=bounded_string(
            data["owner_id"], f"{path}.owner_id", pattern=SAFE_TOKEN_PATTERN
        ),
        system_ids=systems,
        due_on=date_value(data["due_on"], f"{path}.due_on"),
    )


def parse_engagement(value: object) -> EngagementContract:
    """Parse a non-production engagement allowlist and ownership contract."""

    data = object_value(value, "$")
    exact_keys(
        data,
        frozenset(
            {
                "schema_version",
                "engagement_id",
                "partner_profile_id",
                "environment",
                "allowed_hosts",
                "synthetic_namespace",
                "owners",
                "cleanup",
                "valid_from",
                "review_by",
            }
        ),
        "$",
    )
    schema_version = bounded_string(data["schema_version"], "$.schema_version")
    if schema_version != ENGAGEMENT_SCHEMA_VERSION:
        raise contract_error(
            "unsupported_schema",
            "$.schema_version",
            "engagement schema is unsupported",
        )
    raw_hosts = array_value(data["allowed_hosts"], "$.allowed_hosts")
    if not raw_hosts or len(raw_hosts) > 50:
        raise contract_error(
            "invalid_host_count",
            "$.allowed_hosts",
            "allowed-host count is outside the supported bound",
        )
    hosts = tuple(
        host_value(item, f"$.allowed_hosts[{index}]")
        for index, item in enumerate(raw_hosts)
    )
    unique_strings(hosts, "$.allowed_hosts", code="duplicate_allowed_host")
    owners = _parse_owners(data["owners"], "$.owners")
    cleanup = _parse_cleanup(data["cleanup"], "$.cleanup")
    valid_from = date_value(data["valid_from"], "$.valid_from")
    review_by = date_value(data["review_by"], "$.review_by")
    if valid_from > review_by:
        raise contract_error(
            "invalid_validity", "$", "engagement validity interval is inverted"
        )
    if cleanup.owner_id != owners.cleanup_owner_id:
        raise contract_error(
            "cleanup_owner_mismatch",
            "$.cleanup.owner_id",
            "cleanup owner must match the assigned role",
        )
    if not valid_from <= cleanup.due_on <= review_by:
        raise contract_error(
            "cleanup_deadline_out_of_bounds",
            "$.cleanup.due_on",
            "cleanup deadline must remain inside engagement validity",
        )
    return EngagementContract(
        schema_version=schema_version,
        engagement_id=bounded_string(
            data["engagement_id"], "$.engagement_id", pattern=ID_PATTERN
        ),
        partner_profile_id=bounded_string(
            data["partner_profile_id"], "$.partner_profile_id", pattern=ID_PATTERN
        ),
        environment=_parse_environment(data["environment"], "$.environment"),
        allowed_hosts=hosts,
        synthetic_namespace=_parse_namespace(
            data["synthetic_namespace"], "$.synthetic_namespace"
        ),
        owners=owners,
        cleanup=cleanup,
        valid_from=valid_from,
        review_by=review_by,
    )


def engagement_sha256(engagement: EngagementContract) -> str:
    """Hash the canonical engagement contract for plan pinning."""

    return sha256_json(engagement.to_dict())


def parse_plan(value: object) -> ExecutionPlan:
    """Parse an unsigned plan without performing cross-document validation."""

    data = object_value(value, "$")
    exact_keys(
        data,
        frozenset(
            {
                "schema_version",
                "plan_id",
                "engagement_id",
                "engagement_sha256",
                "compiled_pack_sha256",
                "environment",
                "target_hosts",
                "synthetic_namespace",
                "owners",
                "cleanup",
                "checkpoints",
                "case_tokens",
                "valid_from",
                "valid_until",
            }
        ),
        "$",
    )
    schema_version = bounded_string(data["schema_version"], "$.schema_version")
    if schema_version != PLAN_SCHEMA_VERSION:
        raise contract_error(
            "unsupported_schema", "$.schema_version", "plan schema is unsupported"
        )
    raw_hosts = array_value(data["target_hosts"], "$.target_hosts")
    if not raw_hosts or len(raw_hosts) > 50:
        raise contract_error(
            "invalid_host_count",
            "$.target_hosts",
            "target-host count is outside the supported bound",
        )
    target_hosts = tuple(
        host_value(item, f"$.target_hosts[{index}]")
        for index, item in enumerate(raw_hosts)
    )
    unique_strings(target_hosts, "$.target_hosts", code="duplicate_target_host")
    raw_checkpoints = array_value(data["checkpoints"], "$.checkpoints")
    checkpoints: tuple[Checkpoint, ...] = tuple()
    try:
        checkpoints = tuple(
            Checkpoint(bounded_string(item, f"$.checkpoints[{index}]"))
            for index, item in enumerate(raw_checkpoints)
        )
    except ValueError as exc:
        raise contract_error(
            "unsupported_checkpoint",
            "$.checkpoints",
            "checkpoint is unsupported",
        ) from exc
    unique_strings(
        tuple(item.value for item in checkpoints),
        "$.checkpoints",
        code="duplicate_checkpoint",
    )
    if frozenset(checkpoints) != _CHECKPOINTS:
        raise contract_error(
            "checkpoint_scope_incomplete",
            "$.checkpoints",
            "the bounded V1 path requires all four checkpoints",
        )
    raw_tokens = array_value(data["case_tokens"], "$.case_tokens")
    if not raw_tokens or len(raw_tokens) > 50:
        raise contract_error(
            "invalid_case_scope",
            "$.case_tokens",
            "case-token count is outside the supported bound",
        )
    case_tokens = tuple(
        bounded_string(item, f"$.case_tokens[{index}]", pattern=_CASE_TOKEN_PATTERN)
        for index, item in enumerate(raw_tokens)
    )
    unique_strings(case_tokens, "$.case_tokens", code="duplicate_case_token")
    valid_from = date_value(data["valid_from"], "$.valid_from")
    valid_until = date_value(data["valid_until"], "$.valid_until")
    if valid_from > valid_until:
        raise contract_error(
            "invalid_validity", "$", "plan validity interval is inverted"
        )
    return ExecutionPlan(
        schema_version=schema_version,
        plan_id=bounded_string(data["plan_id"], "$.plan_id", pattern=ID_PATTERN),
        engagement_id=bounded_string(
            data["engagement_id"], "$.engagement_id", pattern=ID_PATTERN
        ),
        engagement_sha256=bounded_string(
            data["engagement_sha256"],
            "$.engagement_sha256",
            pattern=SHA256_PATTERN,
        ),
        compiled_pack_sha256=bounded_string(
            data["compiled_pack_sha256"],
            "$.compiled_pack_sha256",
            pattern=SHA256_PATTERN,
        ),
        environment=_parse_environment(data["environment"], "$.environment"),
        target_hosts=target_hosts,
        synthetic_namespace=_parse_namespace(
            data["synthetic_namespace"], "$.synthetic_namespace"
        ),
        owners=_parse_owners(data["owners"], "$.owners"),
        cleanup=_parse_cleanup(data["cleanup"], "$.cleanup"),
        checkpoints=checkpoints,
        case_tokens=case_tokens,
        valid_from=valid_from,
        valid_until=valid_until,
    )


def _pack_case_tokens(compilation: PackCompilation) -> tuple[str, ...]:
    tokens: list[str] = []
    for index, item in enumerate(compilation.case_manifest):
        identifier = object_value(
            item["synthetic_identifier"],
            f"$.pack.case_manifest[{index}].synthetic_identifier",
        )
        token = bounded_string(
            identifier.get("value"),
            f"$.pack.case_manifest[{index}].synthetic_identifier.value",
            pattern=_CASE_TOKEN_PATTERN,
        )
        tokens.append(token)
    return tuple(tokens)


def _validate_dates(
    engagement: EngagementContract,
    plan: ExecutionPlan,
    pack: PackCompilation,
    as_of: date,
) -> None:
    if pack.as_of != as_of:
        raise contract_error(
            "pack_date_mismatch",
            "$.pack",
            "pack and plan must be validated for the same date",
        )
    if not engagement.valid_from <= as_of <= engagement.review_by:
        raise contract_error(
            "engagement_not_current",
            "$.engagement",
            "engagement is not current on the requested date",
        )
    if not (
        engagement.valid_from
        <= plan.valid_from
        <= plan.valid_until
        <= engagement.review_by
    ):
        raise contract_error(
            "plan_outside_engagement",
            "$",
            "plan validity must remain inside engagement validity",
        )
    if not plan.valid_from <= as_of <= plan.valid_until:
        raise contract_error(
            "plan_not_current", "$", "plan is not current on the requested date"
        )
    cleanup_deadlines = (engagement.cleanup.due_on, plan.cleanup.due_on)
    if any(deadline < as_of for deadline in cleanup_deadlines):
        raise contract_error(
            "cleanup_deadline_expired",
            "$.cleanup.due_on",
            "cleanup deadline has already passed",
        )
    if any(deadline < plan.valid_until for deadline in cleanup_deadlines):
        raise contract_error(
            "cleanup_deadline_before_plan_end",
            "$.cleanup.due_on",
            "cleanup deadline must cover the complete plan validity interval",
        )


def _validate_pins(
    engagement: EngagementContract,
    plan: ExecutionPlan,
    pack: PackCompilation,
) -> None:
    if plan.engagement_id != engagement.engagement_id:
        raise contract_error(
            "engagement_id_mismatch",
            "$.engagement_id",
            "plan references a different engagement",
        )
    if plan.engagement_sha256 != engagement_sha256(engagement):
        raise contract_error(
            "engagement_hash_mismatch",
            "$.engagement_sha256",
            "plan does not bind the current engagement",
        )
    if plan.compiled_pack_sha256 != pack.compiled_pack_sha256:
        raise contract_error(
            "compiled_pack_pin_mismatch",
            "$.compiled_pack_sha256",
            "plan does not bind the compiled pack",
        )


def _validate_scope(
    engagement: EngagementContract,
    plan: ExecutionPlan,
    pack: PackCompilation,
) -> None:
    if plan.environment != engagement.environment:
        raise contract_error(
            "environment_mismatch",
            "$.environment",
            "plan environment differs from the engagement",
        )
    if not set(plan.target_hosts).issubset(engagement.allowed_hosts):
        raise contract_error(
            "host_not_allowlisted",
            "$.target_hosts",
            "every target host must be explicitly allowlisted",
        )
    if plan.owners != engagement.owners:
        raise contract_error(
            "owner_mismatch",
            "$.owners",
            "plan owners differ from the engagement",
        )
    if plan.cleanup != engagement.cleanup:
        raise contract_error(
            "cleanup_mismatch",
            "$.cleanup",
            "plan cleanup contract differs from the engagement",
        )
    if set(plan.case_tokens) != set(_pack_case_tokens(pack)):
        raise contract_error(
            "case_scope_mismatch",
            "$.case_tokens",
            "plan case scope must match the compiled pack",
        )


def validate_plan(
    engagement_value: object,
    plan_value: object,
    *,
    pack: PackCompilation,
    as_of: date,
) -> PlanCompilation:
    """Validate and compile a plan without connecting to any declared host."""

    validate_compiled_pack(pack)
    engagement = parse_engagement(engagement_value)
    plan = parse_plan(plan_value)
    _validate_dates(engagement, plan, pack, as_of)
    _validate_pins(engagement, plan, pack)
    _validate_scope(engagement, plan, pack)
    return PlanCompilation(
        as_of=as_of,
        plan=plan,
        plan_sha256=sha256_json(plan.to_dict()),
    )
