"""Deterministic, unsigned pack compiler with fail-closed declared controls."""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path, PurePosixPath
from re import Pattern

from contextsafe.canonical import JsonValue, as_json_value, sha256_json
from contextsafe.contract_validation import (
    ID_PATTERN,
    SAFE_TOKEN_PATTERN,
    SEMVER_PATTERN,
    SHA256_PATTERN,
    SLUG_PATTERN,
    array_value,
    boolean_value,
    bounded_string,
    contract_error,
    date_value,
    enum_string,
    exact_keys,
    nullable_date_value,
    object_value,
    relative_path_value,
    unique_strings,
)
from contextsafe.jsonio import load_json
from contextsafe.models import CASE_SCHEMA_VERSION, RULE_SET_SCHEMA_VERSION
from contextsafe.validation import parse_case, parse_rule_set

PACK_SCHEMA_VERSION = "contextsafe.pack/1.0.0"
COMPILED_PACK_SCHEMA_VERSION = "contextsafe.compiled-pack/1.0.0"
RUNNER_CONTRACT_VERSION = "contextsafe.runner/0.1"


class LifecycleStatus(StrEnum):
    """Lifecycle states for a pack or provenance source."""

    DRAFT = "draft"
    ACTIVE = "active"
    WITHDRAWN = "withdrawn"


class ApprovalDecision(StrEnum):
    """Declared human decision; never a cryptographic signature."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ApprovalRole(StrEnum):
    """Roles required before an unsigned pack is eligible for signing."""

    CLINICAL_SAFETY_CHAIR = "clinical_safety_chair"
    COMMUNITY_CO_CHAIR = "community_co_chair"
    TECHNICAL_RELEASE_OWNER = "technical_release_owner"


REQUIRED_APPROVAL_ROLES = frozenset(ApprovalRole)
_LIFECYCLE_VALUES = frozenset(item.value for item in LifecycleStatus)
_DECISION_VALUES = frozenset(item.value for item in ApprovalDecision)
_ROLE_VALUES = frozenset(item.value for item in ApprovalRole)


@dataclass(frozen=True, slots=True)
class PackCompatibility:
    """Exact component and runner contracts supported by this compiler."""

    runner_contract: str
    case_schema: str
    rule_set_schema: str

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "case_schema": self.case_schema,
            "rule_set_schema": self.rule_set_schema,
            "runner_contract": self.runner_contract,
        }


@dataclass(frozen=True, slots=True)
class Lifecycle:
    """Bounded validity and withdrawal state."""

    status: LifecycleStatus
    valid_from: date
    review_by: date
    withdrawn_on: date | None

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "review_by": self.review_by.isoformat(),
            "status": self.status.value,
            "valid_from": self.valid_from.isoformat(),
            "withdrawn_on": (
                None if self.withdrawn_on is None else self.withdrawn_on.isoformat()
            ),
        }


@dataclass(frozen=True, slots=True)
class ComponentReference:
    """One content-addressed case or rule-set document."""

    component_id: str
    path: str
    sha256: str
    mandatory: bool

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "component_id": self.component_id,
            "mandatory": self.mandatory,
            "path": self.path,
            "sha256": self.sha256,
        }


@dataclass(frozen=True, slots=True)
class SourceRecord:
    """Content-addressed provenance metadata without copied source text."""

    source_id: str
    version: str
    uri: str
    sha256: str
    status: LifecycleStatus
    retrieved_on: date
    reviewed_on: date | None
    review_by: date | None
    withdrawn_on: date | None
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "limitations": as_json_value(sorted(self.limitations)),
            "retrieved_on": self.retrieved_on.isoformat(),
            "review_by": None if self.review_by is None else self.review_by.isoformat(),
            "reviewed_on": (
                None if self.reviewed_on is None else self.reviewed_on.isoformat()
            ),
            "sha256": self.sha256,
            "source_id": self.source_id,
            "status": self.status.value,
            "uri": self.uri,
            "version": self.version,
            "withdrawn_on": (
                None if self.withdrawn_on is None else self.withdrawn_on.isoformat()
            ),
        }


@dataclass(frozen=True, slots=True)
class ApprovalDeclaration:
    """A content-bound human-decision declaration, not proof of identity."""

    role: ApprovalRole
    decision: ApprovalDecision
    reviewer_id: str | None
    decided_on: date | None
    review_by: date | None
    subject_sha256: str | None
    withdrawn_on: date | None

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "decided_on": (
                None if self.decided_on is None else self.decided_on.isoformat()
            ),
            "decision": self.decision.value,
            "review_by": None if self.review_by is None else self.review_by.isoformat(),
            "reviewer_id": self.reviewer_id,
            "role": self.role.value,
            "subject_sha256": self.subject_sha256,
            "withdrawn_on": (
                None if self.withdrawn_on is None else self.withdrawn_on.isoformat()
            ),
        }


@dataclass(frozen=True, slots=True)
class Pack:
    """Parsed pack envelope over existing typed case and rule-set contracts."""

    schema_version: str
    pack_id: str
    version: str
    compatibility: PackCompatibility
    lifecycle: Lifecycle
    cases: tuple[ComponentReference, ...]
    rule_sets: tuple[ComponentReference, ...]
    sources: tuple[SourceRecord, ...]
    approvals: tuple[ApprovalDeclaration, ...]

    def approval_payload(self) -> dict[str, JsonValue]:
        """Return all content governed by approval declarations."""

        return {
            "compatibility": self.compatibility.to_dict(),
            "components": {
                "cases": [
                    item.to_dict()
                    for item in sorted(self.cases, key=lambda item: item.component_id)
                ],
                "rule_sets": [
                    item.to_dict()
                    for item in sorted(
                        self.rule_sets, key=lambda item: item.component_id
                    )
                ],
            },
            "lifecycle": self.lifecycle.to_dict(),
            "pack_id": self.pack_id,
            "schema_version": self.schema_version,
            "sources": [
                item.to_dict()
                for item in sorted(self.sources, key=lambda item: item.source_id)
            ],
            "version": self.version,
        }

    def to_dict(self) -> dict[str, JsonValue]:
        value = self.approval_payload()
        value["approvals"] = [
            item.to_dict()
            for item in sorted(self.approvals, key=lambda item: item.role.value)
        ]
        return value


@dataclass(frozen=True, slots=True)
class PackCompilation:
    """Canonical unsigned pack artifact eligible for a future signing step."""

    as_of: date
    pack_id: str
    pack_version: str
    pack_sha256: str
    approval_subject_sha256: str
    case_manifest: tuple[dict[str, JsonValue], ...]
    rule_set_manifest: tuple[dict[str, JsonValue], ...]
    source_manifest: tuple[dict[str, JsonValue], ...]
    approval_manifest: tuple[dict[str, JsonValue], ...]

    def to_dict(self) -> dict[str, JsonValue]:
        """Return an explicitly unsigned and non-executable artifact."""

        return {
            "approval_manifest": list(self.approval_manifest),
            "approval_subject_sha256": self.approval_subject_sha256,
            "as_of": self.as_of.isoformat(),
            "case_manifest": list(self.case_manifest),
            "declared_controls_status": "pass",
            "executable": False,
            "limitations": [
                "approval-declarations-are-not-signatures",
                "cryptographic-authorization-requires-b-035",
            ],
            "pack_id": self.pack_id,
            "pack_sha256": self.pack_sha256,
            "pack_version": self.pack_version,
            "rule_set_manifest": list(self.rule_set_manifest),
            "schema_version": COMPILED_PACK_SCHEMA_VERSION,
            "signature_status": "not_verified",
            "source_manifest": list(self.source_manifest),
            "valid_for_signing": True,
        }


def _nullable_string(
    value: object, path: str, *, pattern: Pattern[str] | None = None
) -> str | None:
    if value is None:
        return None
    return bounded_string(value, path, pattern=pattern)


def _parse_compatibility(value: object) -> PackCompatibility:
    path = "$.compatibility"
    data = object_value(value, path)
    exact_keys(
        data,
        frozenset({"runner_contract", "case_schema", "rule_set_schema"}),
        path,
    )
    compatibility = PackCompatibility(
        runner_contract=bounded_string(
            data["runner_contract"], f"{path}.runner_contract"
        ),
        case_schema=bounded_string(data["case_schema"], f"{path}.case_schema"),
        rule_set_schema=bounded_string(
            data["rule_set_schema"], f"{path}.rule_set_schema"
        ),
    )
    expected = PackCompatibility(
        runner_contract=RUNNER_CONTRACT_VERSION,
        case_schema=CASE_SCHEMA_VERSION,
        rule_set_schema=RULE_SET_SCHEMA_VERSION,
    )
    if compatibility != expected:
        raise contract_error(
            "incompatible_pack",
            path,
            "pack contracts are not supported by this compiler",
        )
    return compatibility


def _parse_lifecycle(value: object) -> Lifecycle:
    path = "$.lifecycle"
    data = object_value(value, path)
    exact_keys(
        data,
        frozenset({"status", "valid_from", "review_by", "withdrawn_on"}),
        path,
    )
    lifecycle = Lifecycle(
        status=LifecycleStatus(
            enum_string(data["status"], f"{path}.status", _LIFECYCLE_VALUES)
        ),
        valid_from=date_value(data["valid_from"], f"{path}.valid_from"),
        review_by=date_value(data["review_by"], f"{path}.review_by"),
        withdrawn_on=nullable_date_value(data["withdrawn_on"], f"{path}.withdrawn_on"),
    )
    if lifecycle.valid_from > lifecycle.review_by:
        raise contract_error("invalid_validity", path, "validity interval is inverted")
    if (lifecycle.status is LifecycleStatus.WITHDRAWN) != (
        lifecycle.withdrawn_on is not None
    ):
        raise contract_error(
            "invalid_withdrawal", path, "withdrawal state and date must agree"
        )
    if (
        lifecycle.withdrawn_on is not None
        and lifecycle.withdrawn_on < lifecycle.valid_from
    ):
        raise contract_error(
            "invalid_withdrawal", path, "withdrawal cannot precede validity"
        )
    return lifecycle


def _parse_component(value: object, path: str) -> ComponentReference:
    data = object_value(value, path)
    exact_keys(data, frozenset({"component_id", "path", "sha256", "mandatory"}), path)
    return ComponentReference(
        component_id=bounded_string(
            data["component_id"], f"{path}.component_id", pattern=ID_PATTERN
        ),
        path=relative_path_value(data["path"], f"{path}.path"),
        sha256=bounded_string(data["sha256"], f"{path}.sha256", pattern=SHA256_PATTERN),
        mandatory=boolean_value(data["mandatory"], f"{path}.mandatory"),
    )


def _parse_components(
    value: object,
) -> tuple[tuple[ComponentReference, ...], tuple[ComponentReference, ...]]:
    path = "$.components"
    data = object_value(value, path)
    exact_keys(data, frozenset({"cases", "rule_sets"}), path)

    def parse_group(key: str, limit: int) -> tuple[ComponentReference, ...]:
        group_path = f"{path}.{key}"
        raw = array_value(data[key], group_path)
        if not raw or len(raw) > limit:
            raise contract_error(
                "invalid_component_count",
                group_path,
                "component count is outside the supported bound",
            )
        parsed = tuple(
            _parse_component(item, f"{group_path}[{index}]")
            for index, item in enumerate(raw)
        )
        unique_strings(
            tuple(item.component_id for item in parsed),
            group_path,
            code="duplicate_component_id",
        )
        return parsed

    cases = parse_group("cases", 50)
    rule_sets = parse_group("rule_sets", 50)
    all_paths = tuple(item.path for item in (*cases, *rule_sets))
    unique_strings(all_paths, path, code="duplicate_component_path")
    if not any(item.mandatory for item in cases) or not any(
        item.mandatory for item in rule_sets
    ):
        raise contract_error(
            "missing_mandatory_component",
            path,
            "a mandatory case and rule set are required",
        )
    return cases, rule_sets


def _parse_source(value: object, path: str) -> SourceRecord:
    data = object_value(value, path)
    exact_keys(
        data,
        frozenset(
            {
                "source_id",
                "version",
                "uri",
                "sha256",
                "status",
                "retrieved_on",
                "reviewed_on",
                "review_by",
                "withdrawn_on",
                "limitations",
            }
        ),
        path,
    )
    limitation_values = tuple(
        bounded_string(item, f"{path}.limitations[{index}]", pattern=SLUG_PATTERN)
        for index, item in enumerate(
            array_value(data["limitations"], f"{path}.limitations")
        )
    )
    unique_strings(
        limitation_values, f"{path}.limitations", code="duplicate_limitation"
    )
    source = SourceRecord(
        source_id=bounded_string(
            data["source_id"], f"{path}.source_id", pattern=ID_PATTERN
        ),
        version=bounded_string(
            data["version"], f"{path}.version", pattern=SEMVER_PATTERN
        ),
        uri=bounded_string(data["uri"], f"{path}.uri", pattern=SAFE_TOKEN_PATTERN),
        sha256=bounded_string(data["sha256"], f"{path}.sha256", pattern=SHA256_PATTERN),
        status=LifecycleStatus(
            enum_string(data["status"], f"{path}.status", _LIFECYCLE_VALUES)
        ),
        retrieved_on=date_value(data["retrieved_on"], f"{path}.retrieved_on"),
        reviewed_on=nullable_date_value(data["reviewed_on"], f"{path}.reviewed_on"),
        review_by=nullable_date_value(data["review_by"], f"{path}.review_by"),
        withdrawn_on=nullable_date_value(data["withdrawn_on"], f"{path}.withdrawn_on"),
        limitations=limitation_values,
    )
    if (source.status is LifecycleStatus.WITHDRAWN) != (
        source.withdrawn_on is not None
    ):
        raise contract_error(
            "invalid_withdrawal", path, "withdrawal state and date must agree"
        )
    if source.reviewed_on is not None and source.reviewed_on < source.retrieved_on:
        raise contract_error(
            "invalid_source_dates", path, "review cannot precede retrieval"
        )
    if (
        source.reviewed_on is not None
        and source.review_by is not None
        and source.reviewed_on > source.review_by
    ):
        raise contract_error(
            "invalid_source_dates", path, "source review interval is inverted"
        )
    return source


def _parse_approval(value: object, path: str) -> ApprovalDeclaration:
    data = object_value(value, path)
    exact_keys(
        data,
        frozenset(
            {
                "role",
                "decision",
                "reviewer_id",
                "decided_on",
                "review_by",
                "subject_sha256",
                "withdrawn_on",
            }
        ),
        path,
    )
    approval = ApprovalDeclaration(
        role=ApprovalRole(enum_string(data["role"], f"{path}.role", _ROLE_VALUES)),
        decision=ApprovalDecision(
            enum_string(data["decision"], f"{path}.decision", _DECISION_VALUES)
        ),
        reviewer_id=_nullable_string(
            data["reviewer_id"], f"{path}.reviewer_id", pattern=SAFE_TOKEN_PATTERN
        ),
        decided_on=nullable_date_value(data["decided_on"], f"{path}.decided_on"),
        review_by=nullable_date_value(data["review_by"], f"{path}.review_by"),
        subject_sha256=_nullable_string(
            data["subject_sha256"], f"{path}.subject_sha256", pattern=SHA256_PATTERN
        ),
        withdrawn_on=nullable_date_value(data["withdrawn_on"], f"{path}.withdrawn_on"),
    )
    bound_fields = (
        approval.reviewer_id,
        approval.decided_on,
        approval.review_by,
        approval.subject_sha256,
    )
    if approval.decision is ApprovalDecision.PENDING:
        if any(item is not None for item in (*bound_fields, approval.withdrawn_on)):
            raise contract_error(
                "invalid_pending_approval",
                path,
                "pending approval fields must remain null",
            )
    elif any(item is None for item in bound_fields):
        raise contract_error(
            "incomplete_approval", path, "decided approval fields are required"
        )
    if (
        approval.decided_on is not None
        and approval.review_by is not None
        and approval.decided_on > approval.review_by
    ):
        raise contract_error(
            "invalid_approval_dates", path, "approval interval is inverted"
        )
    if (
        approval.withdrawn_on is not None
        and approval.decided_on is not None
        and approval.withdrawn_on < approval.decided_on
    ):
        raise contract_error(
            "invalid_withdrawal", path, "withdrawal cannot precede decision"
        )
    return approval


def parse_pack(value: object) -> Pack:
    """Parse the pack envelope without treating declarations as authorization."""

    data = object_value(value, "$")
    exact_keys(
        data,
        frozenset(
            {
                "schema_version",
                "pack_id",
                "version",
                "compatibility",
                "lifecycle",
                "components",
                "sources",
                "approvals",
            }
        ),
        "$",
    )
    schema_version = bounded_string(data["schema_version"], "$.schema_version")
    if schema_version != PACK_SCHEMA_VERSION:
        raise contract_error(
            "unsupported_schema", "$.schema_version", "pack schema is unsupported"
        )
    cases, rule_sets = _parse_components(data["components"])
    raw_sources = array_value(data["sources"], "$.sources")
    if not raw_sources or len(raw_sources) > 100:
        raise contract_error(
            "invalid_source_count",
            "$.sources",
            "source count is outside the supported bound",
        )
    sources = tuple(
        _parse_source(item, f"$.sources[{index}]")
        for index, item in enumerate(raw_sources)
    )
    unique_strings(
        tuple(item.source_id for item in sources),
        "$.sources",
        code="duplicate_source_id",
    )
    raw_approvals = array_value(data["approvals"], "$.approvals")
    if len(raw_approvals) > len(REQUIRED_APPROVAL_ROLES):
        raise contract_error(
            "invalid_approval_count", "$.approvals", "too many approval declarations"
        )
    approvals = tuple(
        _parse_approval(item, f"$.approvals[{index}]")
        for index, item in enumerate(raw_approvals)
    )
    unique_strings(
        tuple(item.role.value for item in approvals),
        "$.approvals",
        code="duplicate_approval_role",
    )
    return Pack(
        schema_version=schema_version,
        pack_id=bounded_string(data["pack_id"], "$.pack_id", pattern=ID_PATTERN),
        version=bounded_string(data["version"], "$.version", pattern=SEMVER_PATTERN),
        compatibility=_parse_compatibility(data["compatibility"]),
        lifecycle=_parse_lifecycle(data["lifecycle"]),
        cases=cases,
        rule_sets=rule_sets,
        sources=sources,
        approvals=approvals,
    )


def approval_subject_sha256(pack: Pack) -> str:
    """Hash the canonical pack content covered by every declaration."""

    return sha256_json(pack.approval_payload())


def _resolve_component(root: Path, relative_path: str) -> Path:
    base = root.resolve()
    path = base.joinpath(*PurePosixPath(relative_path).parts).resolve()
    if path == base or not path.is_relative_to(base):
        raise contract_error(
            "component_path_escape",
            "$.components",
            "component path must remain inside the pack directory",
        )
    return path


def _validate_lifecycle(pack: Pack, as_of: date) -> None:
    if pack.lifecycle.status is LifecycleStatus.DRAFT:
        raise contract_error(
            "pack_not_active", "$.lifecycle.status", "draft pack cannot be compiled"
        )
    if pack.lifecycle.status is LifecycleStatus.WITHDRAWN:
        raise contract_error(
            "pack_withdrawn", "$.lifecycle.status", "withdrawn pack cannot be compiled"
        )
    if as_of < pack.lifecycle.valid_from:
        raise contract_error(
            "pack_not_yet_valid", "$.lifecycle.valid_from", "pack is not yet valid"
        )
    if as_of > pack.lifecycle.review_by:
        raise contract_error(
            "pack_expired", "$.lifecycle.review_by", "pack review date has passed"
        )


def _validate_sources(pack: Pack, as_of: date) -> None:
    for index, source in enumerate(pack.sources):
        path = f"$.sources[{index}]"
        if source.status is LifecycleStatus.DRAFT:
            raise contract_error(
                "source_not_active", f"{path}.status", "draft source blocks compilation"
            )
        if source.status is LifecycleStatus.WITHDRAWN:
            raise contract_error(
                "source_withdrawn",
                f"{path}.status",
                "withdrawn source blocks compilation",
            )
        if source.reviewed_on is None or source.review_by is None:
            raise contract_error(
                "source_review_missing",
                path,
                "current review metadata is required",
            )
        if source.retrieved_on > as_of:
            raise contract_error(
                "source_retrieval_in_future",
                f"{path}.retrieved_on",
                "source retrieval cannot be in the future",
            )
        if source.reviewed_on > as_of:
            raise contract_error(
                "source_review_in_future",
                f"{path}.reviewed_on",
                "source review cannot be in the future",
            )
        if source.review_by < as_of:
            raise contract_error(
                "source_review_expired",
                f"{path}.review_by",
                "source review date has passed",
            )


def _validate_approvals(pack: Pack, as_of: date) -> None:
    by_role = {item.role: item for item in pack.approvals}
    missing = sorted(
        REQUIRED_APPROVAL_ROLES - by_role.keys(), key=lambda item: item.value
    )
    if missing:
        raise contract_error(
            "missing_approval",
            "$.approvals",
            "a required approval role is missing",
        )
    expected_subject = approval_subject_sha256(pack)
    for role in sorted(REQUIRED_APPROVAL_ROLES, key=lambda item: item.value):
        approval = by_role[role]
        if approval.decision is not ApprovalDecision.APPROVED:
            raise contract_error(
                "approval_not_granted",
                "$.approvals",
                "every required role must declare approval",
            )
        if approval.subject_sha256 != expected_subject:
            raise contract_error(
                "approval_subject_mismatch",
                "$.approvals",
                "approval does not bind the current pack content",
            )
        if approval.withdrawn_on is not None:
            raise contract_error(
                "approval_withdrawn",
                "$.approvals",
                "withdrawn approval blocks compilation",
            )
        if approval.decided_on is None or approval.decided_on > as_of:
            raise contract_error(
                "approval_not_yet_valid",
                "$.approvals",
                "approval is not valid on the requested date",
            )
        if approval.review_by is None or approval.review_by < as_of:
            raise contract_error(
                "approval_expired",
                "$.approvals",
                "approval review date has passed",
            )


def _load_components(
    pack: Pack, root: Path
) -> tuple[tuple[dict[str, JsonValue], ...], tuple[dict[str, JsonValue], ...]]:
    case_manifest: list[dict[str, JsonValue]] = []
    case_ids: set[str] = set()
    for reference in sorted(pack.cases, key=lambda item: item.component_id):
        value = load_json(_resolve_component(root, reference.path))
        case = parse_case(value)
        canonical_hash = sha256_json(case.to_dict())
        if canonical_hash != reference.sha256:
            raise contract_error(
                "component_hash_mismatch",
                "$.components.cases",
                "case content hash does not match the pack",
            )
        if case.case_id != reference.component_id:
            raise contract_error(
                "component_id_mismatch",
                "$.components.cases",
                "case ID does not match its component reference",
            )
        case_ids.add(case.case_id)
        case_manifest.append(
            {
                "case_id": case.case_id,
                "mandatory": reference.mandatory,
                "path": reference.path,
                "schema_version": case.schema_version,
                "sha256": canonical_hash,
                "synthetic_identifier": case.synthetic_identifier.to_dict(),
            }
        )
    rule_manifest: list[dict[str, JsonValue]] = []
    for reference in sorted(pack.rule_sets, key=lambda item: item.component_id):
        value = load_json(_resolve_component(root, reference.path))
        rule_set = parse_rule_set(value)
        canonical_hash = sha256_json(rule_set.to_dict())
        if canonical_hash != reference.sha256:
            raise contract_error(
                "component_hash_mismatch",
                "$.components.rule_sets",
                "rule-set content hash does not match the pack",
            )
        if any(rule.case_id not in case_ids for rule in rule_set.rules):
            raise contract_error(
                "rule_case_missing",
                "$.components.rule_sets",
                "rule references a case outside this pack",
            )
        rule_manifest.append(
            {
                "mandatory": reference.mandatory,
                "path": reference.path,
                "rule_ids": as_json_value(
                    sorted(rule.rule_id for rule in rule_set.rules)
                ),
                "rule_set_id": reference.component_id,
                "schema_version": rule_set.schema_version,
                "sha256": canonical_hash,
            }
        )
    return tuple(case_manifest), tuple(rule_manifest)


def compile_pack(value: object, *, root: Path, as_of: date) -> PackCompilation:
    """Compile one governed envelope into a deterministic unsigned manifest.

    This function validates declared approvals but does not authenticate reviewer
    identity. Its result is intentionally marked non-executable until B-035 adds
    detached signature verification.
    """

    pack = parse_pack(value)
    _validate_lifecycle(pack, as_of)
    _validate_sources(pack, as_of)
    case_manifest, rule_set_manifest = _load_components(pack, root)
    _validate_approvals(pack, as_of)
    return PackCompilation(
        as_of=as_of,
        pack_id=pack.pack_id,
        pack_version=pack.version,
        pack_sha256=sha256_json(pack.to_dict()),
        approval_subject_sha256=approval_subject_sha256(pack),
        case_manifest=case_manifest,
        rule_set_manifest=rule_set_manifest,
        source_manifest=tuple(
            item.to_dict()
            for item in sorted(pack.sources, key=lambda item: item.source_id)
        ),
        approval_manifest=tuple(
            {
                "decided_on": (
                    None if item.decided_on is None else item.decided_on.isoformat()
                ),
                "review_by": (
                    None if item.review_by is None else item.review_by.isoformat()
                ),
                "reviewer_id": item.reviewer_id,
                "role": item.role.value,
                "subject_sha256": item.subject_sha256,
            }
            for item in sorted(pack.approvals, key=lambda item: item.role.value)
        ),
    )
