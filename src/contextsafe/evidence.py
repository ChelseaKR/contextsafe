"""Deterministic contracts for preflighted evidence and canonical observations."""

import re
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from enum import StrEnum

from contextsafe.canonical import JsonValue, sha256_json
from contextsafe.contract_validation import (
    ID_PATTERN,
    PROVENANCE_LABEL_GRAMMAR,
    PROVENANCE_SYSTEM_GRAMMAR,
    PROVENANCE_VERSION_GRAMMAR,
    SAFE_TOKEN_PATTERN,
    SHA256_PATTERN,
    Grammar,
    array_value,
    boolean_value,
    bounded_string,
    contract_error,
    enum_string,
    exact_keys,
    object_value,
    provenance_string,
    timestamp_value,
    unique_strings,
)
from contextsafe.identifiers import provenance_hits
from contextsafe.models import (
    Checkpoint,
    ConceptKind,
    MappingDescriptor,
    SemanticValue,
)
from contextsafe.plan import (
    SYNTHETIC_IDENTIFIER_SYSTEM,
    SYNTHETIC_VALUE_PREFIX,
    ExecutionPlan,
)
from contextsafe.validation import parse_mapping_descriptor, parse_semantic_value

EVIDENCE_SOURCE_SCHEMA_VERSION = "contextsafe.evidence-source/1.0.0"
EVIDENCE_SCHEMA_VERSION = "contextsafe.evidence/1.0.0"
CANONICAL_OBSERVATION_SCHEMA_VERSION = "contextsafe.observation/1.0.0"
PREFLIGHT_PROFILE_VERSION = "contextsafe.preflight/canonical-json-1.0.0"
CANONICAL_JSON_SOURCE_TYPE = "canonical_json"
CANONICAL_JSON_MEDIA_TYPE = "application/vnd.contextsafe.evidence+json"
INTERNAL_AUTHORIZATION_STATUS = "not_verified_internal_test_only"

_CASE_ID_PATTERN = re.compile(r"^CTP-[A-Z0-9]{3,16}$")
_CASE_TOKEN_PATTERN = re.compile(r"^CSYN-CTP-[A-Z0-9]{3,16}$")
_EVIDENCE_ID_PATTERN = re.compile(r"^EVD-[0-9a-f]{64}$")
_OBSERVATION_ID_PATTERN = re.compile(r"^OBS-[A-Z0-9-]{3,48}$")
_SOURCE_POINTER_PATTERN = re.compile(r"^\$[.\[\]A-Za-z0-9_-]{1,127}$")
_SYNTHETIC_CODE_PATTERN = re.compile(r"^CSYN-[A-Z0-9][A-Z0-9_.:-]{0,95}$")
_CONTEXT_TOKEN_PATTERN = re.compile(
    r"^(?:CSYN|ORDER-CSYN|SUP-CSYN)-[A-Za-z0-9][A-Za-z0-9:/_.-]{0,95}$"
)
_FIELD_CODES = frozenset(
    {
        "abnormal_flag",
        "gender_identity",
        "name_to_use",
        "order",
        "pronouns",
        "recorded_sex_or_gender",
        "reference_range",
        "result",
        "sex_parameter_for_clinical_use",
        "status",
    }
)
_FIXED_VALUE_CODES = frozenset(
    {
        "F",
        "M",
        "X",
        "absent",
        "abnormal",
        "corrected",
        "declined",
        "final",
        "normal",
        "preliminary",
        "specified",
        "unknown",
    }
)
_CANONICAL_PATHS = {
    ConceptKind.GENDER_IDENTITY: "$.concepts.gender_identity",
    ConceptKind.RECORDED_SEX_OR_GENDER: "$.concepts.recorded_sex_or_gender",
    ConceptKind.SEX_PARAMETER_FOR_CLINICAL_USE: (
        "$.concepts.sex_parameter_for_clinical_use"
    ),
    ConceptKind.NAME_TO_USE: "$.concepts.name_to_use",
    ConceptKind.PRONOUNS: "$.concepts.pronouns",
}


class AmbiguityStatus(StrEnum):
    """Whether one or several source candidates remain visible."""

    UNAMBIGUOUS = "unambiguous"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True, slots=True)
class EvidenceScope:
    """One plan-pinned synthetic case/checkpoint boundary."""

    plan_id: str
    case_token: str
    case_id: str
    checkpoint: Checkpoint
    source_type: str
    media_type: str
    valid_from: date
    valid_until: date

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "case_id": self.case_id,
            "case_token": self.case_token,
            "checkpoint": self.checkpoint.value,
            "media_type": self.media_type,
            "plan_id": self.plan_id,
            "source_type": self.source_type,
            "valid_from": self.valid_from.isoformat(),
            "valid_until": self.valid_until.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class BoundaryRecord:
    """One code-only record in the canonical boundary envelope."""

    field_code: str
    value_code: str | None
    context_code: str | None
    source_pointer: str

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "context_code": self.context_code,
            "field_code": self.field_code,
            "source_pointer": self.source_pointer,
            "value_code": self.value_code,
        }


@dataclass(frozen=True, slots=True)
class EvidenceSourceEnvelope:
    """Strict, code-only JSON accepted by the first boundary profile."""

    schema_version: str
    plan_id: str
    case_token: str
    checkpoint: Checkpoint
    source_type: str
    identifier_system: str
    identifier_value: str
    records: tuple[BoundaryRecord, ...]

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "case_token": self.case_token,
            "checkpoint": self.checkpoint.value,
            "plan_id": self.plan_id,
            "records": [record.to_dict() for record in self.records],
            "schema_version": self.schema_version,
            "source_type": self.source_type,
            "synthetic_identifier": {
                "system": self.identifier_system,
                "value": self.identifier_value,
            },
        }


@dataclass(frozen=True, slots=True)
class PreflightResult:
    """Non-sensitive success metadata from a complete first pass."""

    scope: EvidenceScope
    raw_sha256: str
    raw_byte_count: int
    boundary_profile_version: str = PREFLIGHT_PROFILE_VERSION

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "boundary_check_status": "passed",
            "boundary_profile_version": self.boundary_profile_version,
            "limitations": [
                "boundary-check-is-not-proof-of-no-phi",
                "unsigned-plan-cannot-authorize-evidence-import",
            ],
            "persisted": False,
            "raw_byte_count": self.raw_byte_count,
            "raw_sha256": self.raw_sha256,
            "scope": self.scope.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class EvidenceMetadata:
    """Bounded operator-supplied provenance for an accepted source."""

    captured_at: datetime
    collector_id: str
    system_id: str
    system_version: str

    def __post_init__(self) -> None:
        _require_canonical_utc(self.captured_at, "$.captured_at")

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "captured_at": self.captured_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "collector_id": self.collector_id,
            "system_id": self.system_id,
            "system_version": self.system_version,
        }


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    """Append-only index record for one accepted raw object."""

    schema_version: str
    evidence_id: str
    plan_id: str
    case_id: str
    case_token: str
    checkpoint: Checkpoint
    source_type: str
    media_type: str
    raw_sha256: str
    raw_byte_count: int
    captured_at: datetime
    collector_id: str
    system_id: str
    system_version: str
    boundary_profile_version: str
    boundary_check_status: str
    authorization_status: str
    usable_for_execution: bool

    def __post_init__(self) -> None:
        _require_canonical_utc(self.captured_at, "$.captured_at")

    def identity_payload(self) -> dict[str, JsonValue]:
        """Return every immutable field except the derived evidence ID."""

        return {
            "authorization_status": self.authorization_status,
            "boundary_check_status": self.boundary_check_status,
            "boundary_profile_version": self.boundary_profile_version,
            "captured_at": self.captured_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "case_id": self.case_id,
            "case_token": self.case_token,
            "checkpoint": self.checkpoint.value,
            "collector_id": self.collector_id,
            "media_type": self.media_type,
            "plan_id": self.plan_id,
            "raw_byte_count": self.raw_byte_count,
            "raw_sha256": self.raw_sha256,
            "schema_version": self.schema_version,
            "source_type": self.source_type,
            "system_id": self.system_id,
            "system_version": self.system_version,
            "usable_for_execution": self.usable_for_execution,
        }

    def to_dict(self) -> dict[str, JsonValue]:
        return {"evidence_id": self.evidence_id, **self.identity_payload()}


@dataclass(frozen=True, slots=True)
class ObservationCandidate:
    """A typed value retained with its exact raw-source pointer."""

    source_pointer: str
    typed_value: SemanticValue

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "source_pointer": self.source_pointer,
            "typed_value": self.typed_value.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class CanonicalObservation:
    """A v1 observation that preserves every ambiguous source candidate."""

    schema_version: str
    observation_id: str
    evidence_id: str
    case_id: str
    checkpoint: Checkpoint
    concept: ConceptKind
    canonical_path: str
    context_token: str | None
    mapping: MappingDescriptor
    ambiguity: AmbiguityStatus
    candidates: tuple[ObservationCandidate, ...]

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "ambiguity": self.ambiguity.value,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "canonical_path": self.canonical_path,
            "case_id": self.case_id,
            "checkpoint": self.checkpoint.value,
            "concept": self.concept.value,
            "context_token": self.context_token,
            "evidence_id": self.evidence_id,
            "mapping": self.mapping.to_dict(),
            "observation_id": self.observation_id,
            "schema_version": self.schema_version,
        }


def build_evidence_scope(
    plan: ExecutionPlan,
    *,
    case_token: object,
    checkpoint: object,
    source_type: object,
    media_type: object,
) -> EvidenceScope:
    """Bind a source to one allowed synthetic plan scope."""

    if (
        not plan.environment.non_production_attested
        or not plan.environment.production_access_prohibited
    ):
        raise contract_error(
            "non_production_attestation_missing",
            "$.environment",
            "both non-production controls must be true",
        )
    if (
        plan.synthetic_namespace.system != SYNTHETIC_IDENTIFIER_SYSTEM
        or plan.synthetic_namespace.value_prefix != SYNTHETIC_VALUE_PREFIX
    ):
        raise contract_error(
            "namespace_mismatch",
            "$.synthetic_namespace",
            "the fixed ContextSafe synthetic namespace is required",
        )
    plan_id = bounded_string(plan.plan_id, "$.plan_id", pattern=ID_PATTERN)
    token = bounded_string(case_token, "$.case_token", pattern=_CASE_TOKEN_PATTERN)
    if token not in plan.case_tokens:
        raise contract_error(
            "case_scope_mismatch",
            "$.case_token",
            "case token is outside the execution plan",
        )
    try:
        parsed_checkpoint = Checkpoint(bounded_string(checkpoint, "$.checkpoint"))
    except ValueError as exc:
        raise contract_error(
            "unsupported_checkpoint", "$.checkpoint", "checkpoint is unsupported"
        ) from exc
    if parsed_checkpoint not in plan.checkpoints:
        raise contract_error(
            "checkpoint_scope_mismatch",
            "$.checkpoint",
            "checkpoint is outside the execution plan",
        )
    parsed_source_type = bounded_string(source_type, "$.source_type")
    if parsed_source_type != CANONICAL_JSON_SOURCE_TYPE:
        raise contract_error(
            "unsupported_source_type", "$.source_type", "source type is unsupported"
        )
    parsed_media_type = bounded_string(media_type, "$.media_type")
    if parsed_media_type != CANONICAL_JSON_MEDIA_TYPE:
        raise contract_error(
            "unsupported_media_type", "$.media_type", "media type is unsupported"
        )
    return EvidenceScope(
        plan_id=plan_id,
        case_token=token,
        case_id=token.removeprefix(SYNTHETIC_VALUE_PREFIX),
        checkpoint=parsed_checkpoint,
        source_type=parsed_source_type,
        media_type=parsed_media_type,
        valid_from=plan.valid_from,
        valid_until=plan.valid_until,
    )


def _require_canonical_utc(value: datetime, path: str) -> None:
    """Reject timestamps that cannot be serialized losslessly as canonical ``Z``."""

    if not isinstance(value, datetime):
        raise contract_error(
            "invalid_timestamp", path, "timestamp must be canonical whole-second UTC"
        )
    try:
        offset = value.utcoffset()
    except (OverflowError, TypeError, ValueError) as exc:
        raise contract_error(
            "invalid_timestamp", path, "timestamp must be canonical whole-second UTC"
        ) from exc
    if value.tzinfo is None or offset != timedelta(0) or value.microsecond != 0:
        raise contract_error(
            "invalid_timestamp", path, "timestamp must be canonical whole-second UTC"
        )


def _nullable_synthetic_code(value: object, path: str) -> str | None:
    if value is None:
        return None
    raw = bounded_string(value, path)
    if raw not in _FIXED_VALUE_CODES and _SYNTHETIC_CODE_PATTERN.fullmatch(raw) is None:
        raise contract_error(
            "unapproved_free_text",
            path,
            "value must be a supported code or synthetic token",
        )
    return raw


def _nullable_context_code(value: object, path: str) -> str | None:
    if value is None:
        return None
    return bounded_string(value, path, pattern=_CONTEXT_TOKEN_PATTERN)


def parse_evidence_envelope(value: object) -> EvidenceSourceEnvelope:
    """Parse the exact field allowlist of the code-only source envelope.

    Structural and self-consistent only: the schema version, the ID and token
    grammars, the record bound, the fixed synthetic identifier system, the
    identifier value equal to the envelope's own case token, and pointer
    uniqueness. It binds the envelope to nothing outside itself. A caller
    holding an execution plan uses :func:`parse_evidence_source`, which adds
    the plan-scope equality check; a caller holding only a case document
    makes its own cross-check against what it holds and says so.
    """

    data = object_value(value, "$")
    exact_keys(
        data,
        frozenset(
            {
                "schema_version",
                "plan_id",
                "case_token",
                "checkpoint",
                "source_type",
                "synthetic_identifier",
                "records",
            }
        ),
        "$",
    )
    schema_version = bounded_string(data["schema_version"], "$.schema_version")
    if schema_version != EVIDENCE_SOURCE_SCHEMA_VERSION:
        raise contract_error(
            "unsupported_schema",
            "$.schema_version",
            "evidence-source schema is unsupported",
        )
    plan_id = bounded_string(data["plan_id"], "$.plan_id", pattern=ID_PATTERN)
    case_token = bounded_string(
        data["case_token"], "$.case_token", pattern=_CASE_TOKEN_PATTERN
    )
    checkpoint = enum_string(
        data["checkpoint"],
        "$.checkpoint",
        frozenset(item.value for item in Checkpoint),
    )
    source_type = bounded_string(data["source_type"], "$.source_type")
    if source_type != CANONICAL_JSON_SOURCE_TYPE:
        raise contract_error(
            "unsupported_source_type", "$.source_type", "source type is unsupported"
        )
    identifier = object_value(data["synthetic_identifier"], "$.synthetic_identifier")
    exact_keys(
        identifier,
        frozenset({"system", "value"}),
        "$.synthetic_identifier",
    )
    identifier_system = bounded_string(
        identifier["system"], "$.synthetic_identifier.system"
    )
    identifier_value = bounded_string(
        identifier["value"],
        "$.synthetic_identifier.value",
        pattern=_CASE_TOKEN_PATTERN,
    )
    if (
        identifier_system != SYNTHETIC_IDENTIFIER_SYSTEM
        or identifier_value != case_token
    ):
        raise contract_error(
            "namespace_mismatch",
            "$.synthetic_identifier",
            "the fixed synthetic identifier must match the envelope case token",
        )
    raw_records = array_value(data["records"], "$.records")
    if not raw_records or len(raw_records) > 2_000:
        raise contract_error(
            "invalid_record_count",
            "$.records",
            "record count is outside the supported bound",
        )
    records: list[BoundaryRecord] = []
    for index, raw_record in enumerate(raw_records):
        path = f"$.records[{index}]"
        record = object_value(raw_record, path)
        exact_keys(
            record,
            frozenset({"field_code", "value_code", "context_code", "source_pointer"}),
            path,
        )
        records.append(
            BoundaryRecord(
                field_code=enum_string(
                    record["field_code"], f"{path}.field_code", _FIELD_CODES
                ),
                value_code=_nullable_synthetic_code(
                    record["value_code"], f"{path}.value_code"
                ),
                context_code=_nullable_context_code(
                    record["context_code"], f"{path}.context_code"
                ),
                source_pointer=bounded_string(
                    record["source_pointer"],
                    f"{path}.source_pointer",
                    pattern=_SOURCE_POINTER_PATTERN,
                ),
            )
        )
    pointers = tuple(record.source_pointer for record in records)
    unique_strings(pointers, "$.records", code="duplicate_source_pointer")
    return EvidenceSourceEnvelope(
        schema_version=schema_version,
        plan_id=plan_id,
        case_token=case_token,
        checkpoint=Checkpoint(checkpoint),
        source_type=source_type,
        identifier_system=identifier_system,
        identifier_value=identifier_value,
        records=tuple(records),
    )


def parse_evidence_source(
    value: object, *, scope: EvidenceScope
) -> EvidenceSourceEnvelope:
    """Parse the source envelope and require it to match one plan scope."""

    envelope = parse_evidence_envelope(value)
    if (
        envelope.plan_id != scope.plan_id
        or envelope.case_token != scope.case_token
        or envelope.checkpoint is not scope.checkpoint
        or envelope.source_type != scope.source_type
    ):
        raise contract_error(
            "evidence_scope_mismatch",
            "$",
            "evidence envelope does not match the requested plan scope",
        )
    return envelope


def _provenance_token(value: object, path: str, grammar: Grammar) -> str:
    """Parse one provenance token, then scan it at the boundary.

    Two layers, and they are not the same layer twice. The grammar is the
    control: it makes a bare number, a date, a telephone number, a social
    security number and a URL scheme unwritable in these fields, so most of what
    the detectors look for cannot be expressed here at all. The scan is what a
    grammar cannot do: a PHI canary is ordinary letters, and only inspecting the
    content finds one.

    A detector that fires on a value the grammar admitted is therefore a defect
    in the grammar rather than a filter that saved the day. That is the same
    relationship ``diagnostics.build_support_bundle`` already has with
    ``identifier_hits``, and ``tests/test_privacy_canaries.py`` pins it in both
    directions.

    ``provenance_hits`` is reached through :mod:`contextsafe.identifiers`, the
    leaf module that defines the detectors, rather than through a function-local
    import of a private name in :mod:`contextsafe.preflight`, which imports this
    module and cannot be imported from it.
    """

    token = provenance_string(value, path, grammar)
    hits = provenance_hits(token)
    if any(hit.startswith("canary:") for hit in hits):
        raise contract_error(
            "phi_canary_detected", path, "a configured PHI canary was detected"
        )
    if hits:
        raise contract_error(
            "direct_identifier_detected",
            path,
            "a direct-identifier pattern was detected",
        )
    return token


def parse_evidence_metadata(value: object) -> EvidenceMetadata:
    """Parse deterministic provenance supplied outside the raw source."""

    data = object_value(value, "$")
    exact_keys(
        data,
        frozenset({"captured_at", "collector_id", "system_id", "system_version"}),
        "$",
    )
    return EvidenceMetadata(
        captured_at=timestamp_value(data["captured_at"], "$.captured_at"),
        collector_id=_provenance_token(
            data["collector_id"], "$.collector_id", PROVENANCE_LABEL_GRAMMAR
        ),
        system_id=_provenance_token(
            data["system_id"], "$.system_id", PROVENANCE_SYSTEM_GRAMMAR
        ),
        system_version=_provenance_token(
            data["system_version"], "$.system_version", PROVENANCE_VERSION_GRAMMAR
        ),
    )


def build_evidence_record(
    preflight: PreflightResult, metadata: EvidenceMetadata
) -> EvidenceRecord:
    """Build a deterministic, explicitly non-executable evidence record."""

    if not (
        preflight.scope.valid_from
        <= metadata.captured_at.date()
        <= preflight.scope.valid_until
    ):
        raise contract_error(
            "capture_outside_plan",
            "$.captured_at",
            "evidence capture date must be inside plan validity",
        )
    provisional = EvidenceRecord(
        schema_version=EVIDENCE_SCHEMA_VERSION,
        evidence_id="",
        plan_id=preflight.scope.plan_id,
        case_id=preflight.scope.case_id,
        case_token=preflight.scope.case_token,
        checkpoint=preflight.scope.checkpoint,
        source_type=preflight.scope.source_type,
        media_type=preflight.scope.media_type,
        raw_sha256=preflight.raw_sha256,
        raw_byte_count=preflight.raw_byte_count,
        captured_at=metadata.captured_at,
        collector_id=metadata.collector_id,
        system_id=metadata.system_id,
        system_version=metadata.system_version,
        boundary_profile_version=preflight.boundary_profile_version,
        boundary_check_status="passed",
        authorization_status=INTERNAL_AUTHORIZATION_STATUS,
        usable_for_execution=False,
    )
    record = replace(
        provisional,
        evidence_id=f"EVD-{sha256_json(provisional.identity_payload())}",
    )
    return parse_evidence_record(record.to_dict())


def _positive_integer(value: object, path: str) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 1 <= value <= 1_048_576
    ):
        raise contract_error(
            "invalid_integer", path, "expected a positive bounded integer"
        )
    return value


def parse_evidence_record(value: object) -> EvidenceRecord:
    """Parse an immutable index record and verify its content-derived ID."""

    data = object_value(value, "$")
    required = frozenset(
        {
            "schema_version",
            "evidence_id",
            "plan_id",
            "case_id",
            "case_token",
            "checkpoint",
            "source_type",
            "media_type",
            "raw_sha256",
            "raw_byte_count",
            "captured_at",
            "collector_id",
            "system_id",
            "system_version",
            "boundary_profile_version",
            "boundary_check_status",
            "authorization_status",
            "usable_for_execution",
        }
    )
    exact_keys(data, required, "$")
    schema_version = bounded_string(data["schema_version"], "$.schema_version")
    if schema_version != EVIDENCE_SCHEMA_VERSION:
        raise contract_error(
            "unsupported_schema", "$.schema_version", "evidence schema is unsupported"
        )
    evidence_id = bounded_string(
        data["evidence_id"], "$.evidence_id", pattern=_EVIDENCE_ID_PATTERN
    )
    case_id = bounded_string(data["case_id"], "$.case_id", pattern=_CASE_ID_PATTERN)
    case_token = bounded_string(
        data["case_token"], "$.case_token", pattern=_CASE_TOKEN_PATTERN
    )
    if case_token != f"{SYNTHETIC_VALUE_PREFIX}{case_id}":
        raise contract_error(
            "case_scope_mismatch", "$.case_token", "case token must match case ID"
        )
    checkpoint = enum_string(
        data["checkpoint"],
        "$.checkpoint",
        frozenset(item.value for item in Checkpoint),
    )
    source_type = enum_string(
        data["source_type"],
        "$.source_type",
        frozenset({CANONICAL_JSON_SOURCE_TYPE}),
    )
    media_type = bounded_string(data["media_type"], "$.media_type")
    if media_type != CANONICAL_JSON_MEDIA_TYPE:
        raise contract_error(
            "unsupported_media_type", "$.media_type", "media type is unsupported"
        )
    record = EvidenceRecord(
        schema_version=schema_version,
        evidence_id=evidence_id,
        plan_id=bounded_string(data["plan_id"], "$.plan_id", pattern=ID_PATTERN),
        case_id=case_id,
        case_token=case_token,
        checkpoint=Checkpoint(checkpoint),
        source_type=source_type,
        media_type=media_type,
        raw_sha256=bounded_string(
            data["raw_sha256"], "$.raw_sha256", pattern=SHA256_PATTERN
        ),
        raw_byte_count=_positive_integer(data["raw_byte_count"], "$.raw_byte_count"),
        captured_at=timestamp_value(data["captured_at"], "$.captured_at"),
        collector_id=bounded_string(
            data["collector_id"], "$.collector_id", pattern=SAFE_TOKEN_PATTERN
        ),
        system_id=bounded_string(data["system_id"], "$.system_id", pattern=ID_PATTERN),
        system_version=bounded_string(
            data["system_version"],
            "$.system_version",
            pattern=SAFE_TOKEN_PATTERN,
        ),
        boundary_profile_version=enum_string(
            data["boundary_profile_version"],
            "$.boundary_profile_version",
            frozenset({PREFLIGHT_PROFILE_VERSION}),
        ),
        boundary_check_status=enum_string(
            data["boundary_check_status"],
            "$.boundary_check_status",
            frozenset({"passed"}),
        ),
        authorization_status=enum_string(
            data["authorization_status"],
            "$.authorization_status",
            frozenset({INTERNAL_AUTHORIZATION_STATUS}),
        ),
        usable_for_execution=boolean_value(
            data["usable_for_execution"], "$.usable_for_execution"
        ),
    )
    if record.usable_for_execution:
        raise contract_error(
            "authorization_not_verified",
            "$.usable_for_execution",
            "unsigned internal evidence cannot be executable",
        )
    expected_id = f"EVD-{sha256_json(record.identity_payload())}"
    if record.evidence_id != expected_id:
        raise contract_error(
            "evidence_id_mismatch",
            "$.evidence_id",
            "evidence ID does not match its canonical content",
        )
    return record


def _nullable_token(value: object, path: str) -> str | None:
    if value is None:
        return None
    return bounded_string(value, path, pattern=_CONTEXT_TOKEN_PATTERN)


def parse_canonical_observation(value: object) -> CanonicalObservation:
    """Parse a v1 observation without discarding ambiguous candidates."""

    data = object_value(value, "$")
    exact_keys(
        data,
        frozenset(
            {
                "schema_version",
                "observation_id",
                "evidence_id",
                "case_id",
                "checkpoint",
                "concept",
                "canonical_path",
                "context_token",
                "mapping",
                "ambiguity",
                "candidates",
            }
        ),
        "$",
    )
    schema_version = bounded_string(data["schema_version"], "$.schema_version")
    if schema_version != CANONICAL_OBSERVATION_SCHEMA_VERSION:
        raise contract_error(
            "unsupported_schema",
            "$.schema_version",
            "observation schema is unsupported",
        )
    try:
        concept = ConceptKind(bounded_string(data["concept"], "$.concept"))
    except ValueError as exc:
        raise contract_error(
            "invalid_enum", "$.concept", "value is not supported"
        ) from exc
    canonical_path = bounded_string(
        data["canonical_path"], "$.canonical_path", pattern=_SOURCE_POINTER_PATTERN
    )
    if canonical_path != _CANONICAL_PATHS[concept]:
        raise contract_error(
            "canonical_path_mismatch",
            "$.canonical_path",
            "canonical path must match the observation concept",
        )
    ambiguity = enum_string(
        data["ambiguity"],
        "$.ambiguity",
        frozenset(item.value for item in AmbiguityStatus),
    )
    raw_candidates = array_value(data["candidates"], "$.candidates")
    minimum = 2 if ambiguity == AmbiguityStatus.AMBIGUOUS.value else 1
    maximum = 20
    if not minimum <= len(raw_candidates) <= maximum:
        raise contract_error(
            "ambiguity_mismatch",
            "$.candidates",
            "candidate count does not match ambiguity status",
        )
    if ambiguity == AmbiguityStatus.UNAMBIGUOUS.value and len(raw_candidates) != 1:
        raise contract_error(
            "ambiguity_mismatch",
            "$.candidates",
            "unambiguous observations require exactly one candidate",
        )
    candidates: list[ObservationCandidate] = []
    for index, raw_candidate in enumerate(raw_candidates):
        path = f"$.candidates[{index}]"
        candidate = object_value(raw_candidate, path)
        exact_keys(candidate, frozenset({"source_pointer", "typed_value"}), path)
        candidates.append(
            ObservationCandidate(
                source_pointer=bounded_string(
                    candidate["source_pointer"],
                    f"{path}.source_pointer",
                    pattern=_SOURCE_POINTER_PATTERN,
                ),
                typed_value=parse_semantic_value(
                    concept, candidate["typed_value"], f"{path}.typed_value"
                ),
            )
        )
    pointers = tuple(candidate.source_pointer for candidate in candidates)
    unique_strings(pointers, "$.candidates", code="duplicate_source_pointer")
    return CanonicalObservation(
        schema_version=schema_version,
        observation_id=bounded_string(
            data["observation_id"],
            "$.observation_id",
            pattern=_OBSERVATION_ID_PATTERN,
        ),
        evidence_id=bounded_string(
            data["evidence_id"], "$.evidence_id", pattern=_EVIDENCE_ID_PATTERN
        ),
        case_id=bounded_string(data["case_id"], "$.case_id", pattern=_CASE_ID_PATTERN),
        checkpoint=Checkpoint(
            enum_string(
                data["checkpoint"],
                "$.checkpoint",
                frozenset(item.value for item in Checkpoint),
            )
        ),
        concept=concept,
        canonical_path=canonical_path,
        context_token=_nullable_token(data["context_token"], "$.context_token"),
        mapping=parse_mapping_descriptor(data["mapping"], "$.mapping", concept),
        ambiguity=AmbiguityStatus(ambiguity),
        candidates=tuple(candidates),
    )
