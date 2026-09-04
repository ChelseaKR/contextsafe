"""Append-only review, finding, and disposition state machine, unsigned.

Architecture section 6.5 (``docs/04-ARCHITECTURE.md``) has a reviewer confirm or
change a proposed severity, a customer assign an owner and a disposition, and
two distinct signers stand behind an accepted clinical residual risk. This is
the B-032 slice of that flow, and it is deliberately the part that needs no
key: an event is *declared*, appended, and replayed. Nothing here verifies a
signature, and nothing here changes a receipt.

Four properties, each a decision rather than an omission.

**No free-text field exists, by construction.** An event is a fixed set of
fields drawn from closed sets: the outcome it binds to, the receipt hashes, a
decision, a severity from the rubric labels, an owner as a role plus the
SHA-256 of an opaque handle, a rationale *code*, an optional external
reference under the provenance grammar of ADR 0006, and declared signers as a
role plus an organization label. There is no message, note, comment, or name
field, so a sentence of clinical judgement has nowhere to go -- the same
argument ``contextsafe.safe_value`` makes for the support bundle. The two
operator-supplied labels are held to the ADR 0006 grammars and then scanned,
exactly as evidence provenance is, and that is the residual: a name-shaped
token still fits those grammars (``Jordan.Rivera`` is a well-formed
provenance label, ``JORDAN-RIVERA`` a well-formed system label), and only the
configured canaries and direct-identifier shapes are scanned for. ADR 0006
records that a grammar cannot see ordinary letters; the closed shape removes
the field a name would be typed into, not the possibility of typing one into a
label.

**Signers are declared, not verified.** Every event and every signer carries
``signature_status: not_verified`` and the parser refuses any other value. A
declared signer authorizes nothing: an ``accepted_residual_risk`` event needs
two declared signers with distinct roles (customer clinical owner, ContextSafe
clinical safety chair) and distinct organizations or it is refused, and that
threshold is a shape check on a declaration. Cryptographic review signatures
are B-035; until then, no disposition this module records can represent a risk
as accepted in any receipt, and binding dispositions into a receipt is a later
item that must not change the receipt contract.

**The state machine is data.** :data:`TRANSITIONS` says which decision moves
which disposition to which, :data:`DECISION_RULES` says what each decision must
and must not carry, and the code walks those tables. ``tests/test_review.py``
enumerates every pair the table does not contain and requires each to be
refused as ``illegal_transition``.

**The log is append-only and re-hashes on every read.** Each line is one
canonical JSON record carrying the event, the event's SHA-256, its sequence
number, and the SHA-256 of the record before it (a fixed genesis constant for
the first). Reading the log re-parses every line, requires it to be byte-exact
canonical JSON, re-derives every hash, and replays every transition before a
new line may be appended; a log that does not re-hash, does not replay, or is
bound to a different receipt is refused, and no line is ever rewritten. The
file is opened once with ``O_APPEND`` and ``O_NOFOLLOW``, read and appended
through that one descriptor, and the append is refused if the file is seen
to have grown between the read and the write. That check is a size comparison,
not a lock: it narrows the window in which a second writer can append without
closing it, so one writer at a time is an operating assumption, and a log two
writers reach is refused on its next read as ``log_chain_broken`` rather than
repaired. On a platform without ``O_NOFOLLOW`` the command fails closed with
``input_path_unsupported``, as the other descriptor-anchored commands do. What
the chain cannot see is a record removed from its end: a log cut back to an
earlier line is a valid shorter log, and only an external record of the state
document's ``log_head_sha256`` can show the cut. No clock is read: the log
carries sequence numbers, not timestamps, for the reason
``contextsafe.eventlog`` records.

The decision, severity, role, and rationale vocabularies are reference-only
and ungoverned: they are labels the tests need, not the approved rubric
(B-010) or the reviewer registry (B-035), and no clinical, community, legal,
or security review of them has happened.
"""

from __future__ import annotations

import os
import re
import stat
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from contextsafe.canonical import JsonValue, as_json_value, canonical_json, sha256_json
from contextsafe.contract_validation import (
    PROVENANCE_LABEL_GRAMMAR,
    PROVENANCE_SYSTEM_GRAMMAR,
    SHA256_PATTERN,
    Grammar,
    array_value,
    bounded_string,
    contract_error,
    enum_string,
    exact_keys,
    object_value,
    provenance_string,
)
from contextsafe.errors import ContextSafeError
from contextsafe.identifiers import provenance_hits
from contextsafe.jsonio import MAX_INPUT_BYTES, parse_json_bytes
from contextsafe.models import (
    RECEIPT_DOCUMENT_SCHEMA_VERSION,
    Checkpoint,
    ConceptKind,
    OutcomeStatus,
)

REVIEW_EVENT_SCHEMA_VERSION = "contextsafe.review-event/1.0.0"
REVIEW_LOG_SCHEMA_VERSION = "contextsafe.review-log/1.0.0"
REVIEW_STATE_SCHEMA_VERSION = "contextsafe.review-state/1.0.0"
SIGNATURE_STATUS = "not_verified"
"""The only value any event or signer may carry. A declared signer authorizes nothing."""

GENESIS_SHA256 = "0" * 64
"""What the first record's ``previous_record_sha256`` must be."""

MAX_LOG_BYTES = MAX_INPUT_BYTES
MAX_SIGNERS = 4
STATE_LIMITATIONS: tuple[str, ...] = (
    "declared-signers-are-not-signatures",
    "dispositions-are-not-bound-into-any-receipt",
    "vocabularies-are-reference-only-and-ungoverned",
)
"""Pinned, closed, and in order, the way the compiled-pack limitations are."""


def _optional_flag(name: str) -> int:
    """The bits of an ``os.open`` flag, or no bits where the platform lacks it.

    ``_NOFOLLOW`` is the one whose absence matters, and ``_open_log`` refuses
    on it rather than opening without it.
    """

    bits: int = getattr(os, name, 0)
    return bits


_CLOEXEC = _optional_flag("O_CLOEXEC")
_NOFOLLOW = _optional_flag("O_NOFOLLOW")
_NONBLOCK = _optional_flag("O_NONBLOCK")
"""Without it, opening a FIFO read-only blocks until a writer appears, so a
``--log`` that names one would hang instead of being refused as not a regular
file. Harmless on the regular file the descriptor is then required to be, and
carried on the append flags too so the refusal does not depend on what a
platform does with ``O_RDWR`` on a FIFO."""
_APPEND_FLAGS = os.O_RDWR | os.O_APPEND | os.O_CREAT | _NOFOLLOW | _NONBLOCK | _CLOEXEC
_READ_FLAGS = os.O_RDONLY | _NOFOLLOW | _NONBLOCK | _CLOEXEC
_CHUNK_BYTES = 65_536
_MAX_CHUNKS = MAX_LOG_BYTES // _CHUNK_BYTES
"""How many full reads a log at the size limit takes, before the read that
sees end of file. The read loop is bounded by this rather than by end of file
alone, so a descriptor that never reports end of file cannot hold the command
open; the fstat and running-count checks bound the bytes, this bounds the
reads."""
_RULE_ID_PATTERN = re.compile(r"^[A-Z][A-Z0-9-]{2,63}$")
_CASE_ID_PATTERN = re.compile(r"^CTP-[A-Z0-9]{3,16}$")
FINDING_STATUSES = frozenset(
    {OutcomeStatus.FAIL, OutcomeStatus.INDETERMINATE, OutcomeStatus.BLOCKED}
)
"""Outcome statuses that are findings. A pass or a not-applicable is not reviewed here."""


class Decision(StrEnum):
    """The closed set of things a review event can do."""

    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    SEVERITY_CHANGED = "severity_changed"
    OWNER_ASSIGNED = "owner_assigned"
    REMEDIATED = "remediated"
    ACCEPTED_RESIDUAL_RISK = "accepted_residual_risk"
    WITHDRAWN = "withdrawn"


class Disposition(StrEnum):
    """The closed set of states a finding can be in."""

    UNREVIEWED = "unreviewed"
    CONFIRMED = "confirmed"
    OWNED = "owned"
    REMEDIATED = "remediated"
    ACCEPTED_RESIDUAL_RISK = "accepted_residual_risk"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class Severity(StrEnum):
    """Reference-only rubric labels after Service design §8; not the approved rubric."""

    CS1_CRITICAL = "cs1_critical"
    CS2_HIGH = "cs2_high"
    CS3_MODERATE = "cs3_moderate"
    CS4_LOW = "cs4_low"


class OwnerRole(StrEnum):
    """Reference-only owner roles, mirroring the plan's declared owners."""

    CUSTOMER_TECHNICAL_OWNER = "customer_technical_owner"
    CUSTOMER_CLINICAL_OWNER = "customer_clinical_owner"
    CUSTOMER_PRIVACY_OWNER = "customer_privacy_owner"
    CUSTOMER_CLEANUP_OWNER = "customer_cleanup_owner"


class SignerRole(StrEnum):
    """Reference-only declared-signer roles after Architecture §6.6; ungoverned."""

    CUSTOMER_CLINICAL_OWNER = "customer_clinical_owner"
    CUSTOMER_RELEASE_OWNER = "customer_release_owner"
    CUSTOMER_TECHNICAL_OWNER = "customer_technical_owner"
    CONTEXTSAFE_CLINICAL_SAFETY_CHAIR = "contextsafe_clinical_safety_chair"
    CONTEXTSAFE_COMMUNITY_CO_CHAIR = "contextsafe_community_co_chair"
    CONTEXTSAFE_INTEROPERABILITY_REVIEWER = "contextsafe_interoperability_reviewer"
    LABORATORY_REVIEWER = "laboratory_reviewer"


class RationaleCode(StrEnum):
    """A closed vocabulary standing where a rationale sentence would otherwise be."""

    EVIDENCE_VERIFIED_AGAINST_SOURCE = "evidence_verified_against_source"
    EVIDENCE_NOT_REPRODUCIBLE = "evidence_not_reproducible"
    EVIDENCE_AMBIGUOUS = "evidence_ambiguous"
    OUT_OF_SCOPE_FOR_PLAN = "out_of_scope_for_plan"
    SEVERITY_RUBRIC_APPLIED = "severity_rubric_applied"
    OWNERSHIP_ASSIGNED_BY_PLAN_ROLE = "ownership_assigned_by_plan_role"
    REMEDIATION_VERIFIED_BY_RERUN = "remediation_verified_by_rerun"
    RESIDUAL_RISK_BOUNDED_BY_DISPOSITION = "residual_risk_bounded_by_disposition"
    ENTERED_IN_ERROR = "entered_in_error"


class SeverityRule(StrEnum):
    """What a decision requires of its ``severity`` field."""

    FORBIDDEN = "forbidden"
    REQUIRED = "required"
    REQUIRED_DIFFERENT = "required_different"
    REQUIRED_UNCHANGED = "required_unchanged"


@dataclass(frozen=True, slots=True)
class DecisionRule:
    """What one decision must and must not carry. Data, not code."""

    severity: SeverityRule
    owner_required: bool
    required_signer_roles: frozenset[SignerRole]
    distinct_organizations: bool


TRANSITIONS: Mapping[Disposition, Mapping[Decision, Disposition]] = {
    Disposition.UNREVIEWED: {
        Decision.CONFIRMED: Disposition.CONFIRMED,
        Decision.REJECTED: Disposition.REJECTED,
    },
    Disposition.CONFIRMED: {
        Decision.SEVERITY_CHANGED: Disposition.CONFIRMED,
        Decision.OWNER_ASSIGNED: Disposition.OWNED,
        Decision.WITHDRAWN: Disposition.WITHDRAWN,
    },
    Disposition.OWNED: {
        Decision.SEVERITY_CHANGED: Disposition.OWNED,
        Decision.OWNER_ASSIGNED: Disposition.OWNED,
        Decision.REMEDIATED: Disposition.REMEDIATED,
        Decision.ACCEPTED_RESIDUAL_RISK: Disposition.ACCEPTED_RESIDUAL_RISK,
        Decision.WITHDRAWN: Disposition.WITHDRAWN,
    },
    Disposition.ACCEPTED_RESIDUAL_RISK: {
        Decision.REMEDIATED: Disposition.REMEDIATED,
    },
    Disposition.REMEDIATED: {},
    Disposition.REJECTED: {},
    Disposition.WITHDRAWN: {},
}
"""Every legal move. A pair absent here is ``illegal_transition``, and the
tests enumerate the absent pairs rather than the present ones."""

DECISION_RULES: Mapping[Decision, DecisionRule] = {
    Decision.CONFIRMED: DecisionRule(SeverityRule.REQUIRED, False, frozenset(), False),
    Decision.REJECTED: DecisionRule(SeverityRule.FORBIDDEN, False, frozenset(), False),
    Decision.SEVERITY_CHANGED: DecisionRule(
        SeverityRule.REQUIRED_DIFFERENT, False, frozenset(), False
    ),
    Decision.OWNER_ASSIGNED: DecisionRule(
        SeverityRule.FORBIDDEN, True, frozenset(), False
    ),
    Decision.REMEDIATED: DecisionRule(
        SeverityRule.FORBIDDEN, False, frozenset(), False
    ),
    Decision.ACCEPTED_RESIDUAL_RISK: DecisionRule(
        SeverityRule.REQUIRED_UNCHANGED,
        False,
        frozenset(
            {
                SignerRole.CUSTOMER_CLINICAL_OWNER,
                SignerRole.CONTEXTSAFE_CLINICAL_SAFETY_CHAIR,
            }
        ),
        True,
    ),
    Decision.WITHDRAWN: DecisionRule(SeverityRule.FORBIDDEN, False, frozenset(), False),
}
"""What each decision carries. An accepted residual risk confirms the current
severity rather than setting one, and needs exactly the two mandated roles from
distinct organizations."""

_DECISION_VALUES = frozenset(item.value for item in Decision)
_SEVERITY_VALUES = frozenset(item.value for item in Severity)
_OWNER_ROLE_VALUES = frozenset(item.value for item in OwnerRole)
_SIGNER_ROLE_VALUES = frozenset(item.value for item in SignerRole)
_RATIONALE_VALUES = frozenset(item.value for item in RationaleCode)
_CHECKPOINT_VALUES = frozenset(item.value for item in Checkpoint)
_CONCEPT_VALUES = frozenset(item.value for item in ConceptKind)
_FINDING_STATUS_VALUES = frozenset(item.value for item in FINDING_STATUSES)
_OUTCOME_STATUS_VALUES = frozenset(item.value for item in OutcomeStatus)
_EVENT_KEYS = frozenset(
    {
        "schema_version",
        "outcome",
        "receipt",
        "decision",
        "severity",
        "owner",
        "rationale_code",
        "external_reference",
        "signers",
        "signature_status",
    }
)
_OUTCOME_KEYS = frozenset({"rule_id", "case_id", "checkpoint", "concept"})
_RECEIPT_KEYS = frozenset({"payload_sha256", "rule_set_sha256"})
_OWNER_KEYS = frozenset({"role", "token_sha256"})
_SIGNER_KEYS = frozenset({"role", "organization_id", "signature_status"})
_RECORD_KEYS = frozenset(
    {"schema_version", "sequence", "previous_record_sha256", "event_sha256", "event"}
)


@dataclass(frozen=True, slots=True, order=True)
class OutcomeKey:
    """The outcome an event binds to; the identity of a finding in the log."""

    rule_id: str
    case_id: str
    checkpoint: str
    concept: str

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "case_id": self.case_id,
            "checkpoint": self.checkpoint,
            "concept": self.concept,
            "rule_id": self.rule_id,
        }


@dataclass(frozen=True, slots=True)
class ReceiptBinding:
    """The two hashes that pin an event, and a log, to one receipt payload."""

    payload_sha256: str
    rule_set_sha256: str

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "payload_sha256": self.payload_sha256,
            "rule_set_sha256": self.rule_set_sha256,
        }


@dataclass(frozen=True, slots=True)
class Owner:
    """A role and the hash of an opaque handle. A name cannot be written here."""

    role: OwnerRole
    token_sha256: str

    def to_dict(self) -> dict[str, JsonValue]:
        return {"role": self.role.value, "token_sha256": self.token_sha256}


@dataclass(frozen=True, slots=True)
class DeclaredSigner:
    """A declared, unverified signer. Authorizes nothing."""

    role: SignerRole
    organization_id: str

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "organization_id": self.organization_id,
            "role": self.role.value,
            "signature_status": SIGNATURE_STATUS,
        }


@dataclass(frozen=True, slots=True)
class ReviewEvent:
    """One parsed review event. Every field is a closed value or a hash."""

    outcome: OutcomeKey
    receipt: ReceiptBinding
    decision: Decision
    severity: Severity | None
    owner: Owner | None
    rationale_code: RationaleCode
    external_reference: str | None
    signers: tuple[DeclaredSigner, ...]

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "decision": self.decision.value,
            "external_reference": self.external_reference,
            "outcome": self.outcome.to_dict(),
            "owner": None if self.owner is None else self.owner.to_dict(),
            "rationale_code": self.rationale_code.value,
            "receipt": self.receipt.to_dict(),
            "schema_version": REVIEW_EVENT_SCHEMA_VERSION,
            "severity": None if self.severity is None else self.severity.value,
            "signature_status": SIGNATURE_STATUS,
            "signers": [item.to_dict() for item in self.signers],
        }


@dataclass(frozen=True, slots=True)
class FindingState:
    """The current disposition of one outcome, derived from its events."""

    outcome: OutcomeKey
    disposition: Disposition = Disposition.UNREVIEWED
    severity: Severity | None = None
    owner: Owner | None = None
    event_count: int = 0
    last_event_sha256: str | None = None

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "disposition": self.disposition.value,
            "event_count": self.event_count,
            "last_event_sha256": self.last_event_sha256,
            "outcome": self.outcome.to_dict(),
            "owner": None if self.owner is None else self.owner.to_dict(),
            "severity": None if self.severity is None else self.severity.value,
        }


@dataclass(frozen=True, slots=True)
class LogRecord:
    """One appended line: the event, its hash, and the chain link before it."""

    sequence: int
    previous_record_sha256: str
    event_sha256: str
    event: ReviewEvent

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "event": self.event.to_dict(),
            "event_sha256": self.event_sha256,
            "previous_record_sha256": self.previous_record_sha256,
            "schema_version": REVIEW_LOG_SCHEMA_VERSION,
            "sequence": self.sequence,
        }

    def line(self) -> bytes:
        """The exact bytes this record occupies in the log."""

        return f"{canonical_json(self.to_dict())}\n".encode()

    def sha256(self) -> str:
        return sha256_json(self.to_dict())


@dataclass(frozen=True, slots=True)
class ReviewLogState:
    """Everything a replayed log establishes."""

    receipt: ReceiptBinding | None
    findings: Mapping[OutcomeKey, FindingState]
    event_count: int
    head_sha256: str

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "event_count": self.event_count,
            "findings": [self.findings[key].to_dict() for key in sorted(self.findings)],
            "limitations": list(STATE_LIMITATIONS),
            "log_head_sha256": self.head_sha256,
            "receipt": None if self.receipt is None else self.receipt.to_dict(),
            "schema_version": REVIEW_STATE_SCHEMA_VERSION,
            "signature_status": SIGNATURE_STATUS,
        }


EMPTY_LOG_STATE = ReviewLogState(
    receipt=None, findings={}, event_count=0, head_sha256=GENESIS_SHA256
)


# --- parsing ----------------------------------------------------------------


def _scanned_token(value: object, path: str, grammar: Grammar) -> str:
    """The grammar is the control and the scan is the second pass (ADR 0006)."""

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


def _sha256_value(value: object, path: str) -> str:
    return bounded_string(value, path, pattern=SHA256_PATTERN, max_length=64)


def _constant(value: object, path: str, expected: str, code: str) -> None:
    if value != expected:
        raise contract_error(code, path, "value is not the published constant")


def parse_outcome_key(value: object, path: str) -> OutcomeKey:
    """Parse the four fields that name an outcome."""

    data = object_value(value, path)
    exact_keys(data, _OUTCOME_KEYS, path)
    return OutcomeKey(
        rule_id=bounded_string(
            data["rule_id"], f"{path}.rule_id", pattern=_RULE_ID_PATTERN, max_length=64
        ),
        case_id=bounded_string(
            data["case_id"], f"{path}.case_id", pattern=_CASE_ID_PATTERN, max_length=20
        ),
        checkpoint=enum_string(
            data["checkpoint"], f"{path}.checkpoint", _CHECKPOINT_VALUES
        ),
        concept=enum_string(data["concept"], f"{path}.concept", _CONCEPT_VALUES),
    )


def _parse_receipt_binding(value: object, path: str) -> ReceiptBinding:
    data = object_value(value, path)
    exact_keys(data, _RECEIPT_KEYS, path)
    return ReceiptBinding(
        payload_sha256=_sha256_value(data["payload_sha256"], f"{path}.payload_sha256"),
        rule_set_sha256=_sha256_value(
            data["rule_set_sha256"], f"{path}.rule_set_sha256"
        ),
    )


def _parse_owner(value: object, path: str) -> Owner | None:
    if value is None:
        return None
    data = object_value(value, path)
    exact_keys(data, _OWNER_KEYS, path)
    return Owner(
        role=OwnerRole(enum_string(data["role"], f"{path}.role", _OWNER_ROLE_VALUES)),
        token_sha256=_sha256_value(data["token_sha256"], f"{path}.token_sha256"),
    )


def _parse_signer(value: object, path: str) -> DeclaredSigner:
    data = object_value(value, path)
    exact_keys(data, _SIGNER_KEYS, path)
    _constant(
        data["signature_status"],
        f"{path}.signature_status",
        SIGNATURE_STATUS,
        "signature_status_not_declarable",
    )
    return DeclaredSigner(
        role=SignerRole(enum_string(data["role"], f"{path}.role", _SIGNER_ROLE_VALUES)),
        organization_id=_scanned_token(
            data["organization_id"],
            f"{path}.organization_id",
            PROVENANCE_SYSTEM_GRAMMAR,
        ),
    )


def _parse_signers(value: object, path: str) -> tuple[DeclaredSigner, ...]:
    items = array_value(value, path)
    if not 1 <= len(items) <= MAX_SIGNERS:
        raise contract_error(
            "signer_count_out_of_bounds",
            path,
            f"an event declares between 1 and {MAX_SIGNERS} signers",
        )
    signers = tuple(
        _parse_signer(item, f"{path}[{index}]") for index, item in enumerate(items)
    )
    roles = [item.role for item in signers]
    if len(roles) != len(set(roles)):
        raise contract_error(
            "duplicate_signer_role", path, "declared signer roles must be distinct"
        )
    return signers


def _parse_severity(value: object, path: str) -> Severity | None:
    if value is None:
        return None
    return Severity(enum_string(value, path, _SEVERITY_VALUES))


def _parse_external_reference(value: object, path: str) -> str | None:
    if value is None:
        return None
    return _scanned_token(value, path, PROVENANCE_LABEL_GRAMMAR)


def parse_review_event(value: object) -> ReviewEvent:
    """Parse one event document, refusing anything outside the closed shape.

    Shape only: whether the decision is legal for the finding's current state
    is :func:`apply_event`'s question, and whether the event's outcome exists
    in the receipt is :func:`bind_to_receipt`'s.
    """

    data = object_value(value, "$")
    exact_keys(data, _EVENT_KEYS, "$")
    _constant(
        data["schema_version"],
        "$.schema_version",
        REVIEW_EVENT_SCHEMA_VERSION,
        "unsupported_schema_version",
    )
    _constant(
        data["signature_status"],
        "$.signature_status",
        SIGNATURE_STATUS,
        "signature_status_not_declarable",
    )
    decision = Decision(enum_string(data["decision"], "$.decision", _DECISION_VALUES))
    event = ReviewEvent(
        outcome=parse_outcome_key(data["outcome"], "$.outcome"),
        receipt=_parse_receipt_binding(data["receipt"], "$.receipt"),
        decision=decision,
        severity=_parse_severity(data["severity"], "$.severity"),
        owner=_parse_owner(data["owner"], "$.owner"),
        rationale_code=RationaleCode(
            enum_string(data["rationale_code"], "$.rationale_code", _RATIONALE_VALUES)
        ),
        external_reference=_parse_external_reference(
            data["external_reference"], "$.external_reference"
        ),
        signers=_parse_signers(data["signers"], "$.signers"),
    )
    _check_decision_shape(event)
    return event


def _check_decision_shape(event: ReviewEvent) -> None:
    """The state-independent half of :data:`DECISION_RULES`."""

    rule = DECISION_RULES[event.decision]
    if rule.severity is SeverityRule.FORBIDDEN and event.severity is not None:
        raise contract_error(
            "severity_forbidden", "$.severity", "this decision carries no severity"
        )
    if rule.severity is not SeverityRule.FORBIDDEN and event.severity is None:
        raise contract_error(
            "severity_required", "$.severity", "this decision requires a severity"
        )
    if rule.owner_required and event.owner is None:
        raise contract_error(
            "owner_required", "$.owner", "this decision requires an owner"
        )
    if not rule.owner_required and event.owner is not None:
        raise contract_error(
            "owner_forbidden", "$.owner", "this decision carries no owner"
        )
    _check_signer_threshold(event, rule)


def _check_signer_threshold(event: ReviewEvent, rule: DecisionRule) -> None:
    """Each half of the rule is checked on its own, so neither is dead data."""

    if rule.required_signer_roles:
        roles = frozenset(item.role for item in event.signers)
        if roles != rule.required_signer_roles:
            raise contract_error(
                "signer_threshold_unmet",
                "$.signers",
                "this decision requires exactly the mandated declared signer roles",
            )
    organizations = {item.organization_id for item in event.signers}
    if rule.distinct_organizations and len(organizations) != len(event.signers):
        raise contract_error(
            "signer_organizations_not_distinct",
            "$.signers",
            "the mandated declared signers must come from distinct organizations",
        )


# --- the receipt ------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ReceiptFindings:
    """What a receipt document establishes for review: its hashes and its findings."""

    binding: ReceiptBinding
    findings: frozenset[OutcomeKey]


def _receipt_outcome(value: object, path: str) -> tuple[OutcomeKey, str]:
    data = object_value(value, path)
    for key in ("rule_id", "case_id", "checkpoint", "concept", "status"):
        if key not in data:
            raise contract_error(
                "missing_field", f"{path}.{key}", "required field is missing"
            )
    outcome = parse_outcome_key(
        {key: data[key] for key in _OUTCOME_KEYS if key in data}, path
    )
    status = enum_string(data["status"], f"{path}.status", _OUTCOME_STATUS_VALUES)
    return outcome, status


def parse_receipt_findings(value: object) -> ReceiptFindings:
    """Read the hashes and finding outcomes out of a receipt document.

    The payload hash is re-derived: an event may not bind to a receipt whose
    ``payload_sha256`` no longer matches its payload. A result whose status is
    outside the published algebra refuses the receipt rather than being read
    as "not a finding": an unsupported value is never quietly the safe case.
    This is not receipt verification (B-036); it reads the fields review needs
    and nothing else.
    """

    data = object_value(value, "$")
    for key in ("schema_version", "payload", "payload_sha256"):
        if key not in data:
            raise contract_error(
                "missing_field", f"$.{key}", "required field is missing"
            )
    _constant(
        data["schema_version"],
        "$.schema_version",
        RECEIPT_DOCUMENT_SCHEMA_VERSION,
        "unsupported_schema_version",
    )
    payload = object_value(data["payload"], "$.payload")
    payload_sha256 = _sha256_value(data["payload_sha256"], "$.payload_sha256")
    if sha256_json(as_json_value(payload)) != payload_sha256:
        raise contract_error(
            "receipt_hash_mismatch",
            "$.payload_sha256",
            "payload_sha256 does not match the receipt payload",
        )
    hashes = object_value(payload.get("hashes"), "$.payload.hashes")
    rule_set_sha256 = _sha256_value(
        hashes.get("rule_set_sha256"), "$.payload.hashes.rule_set_sha256"
    )
    results = array_value(payload.get("results"), "$.payload.results")
    findings: set[OutcomeKey] = set()
    for index, item in enumerate(results):
        outcome, status = _receipt_outcome(item, f"$.payload.results[{index}]")
        if status in _FINDING_STATUS_VALUES:
            findings.add(outcome)
    return ReceiptFindings(
        binding=ReceiptBinding(
            payload_sha256=payload_sha256, rule_set_sha256=rule_set_sha256
        ),
        findings=frozenset(findings),
    )


def bind_to_receipt(event: ReviewEvent, receipt: ReceiptFindings) -> None:
    """Refuse an event that does not name this receipt and one of its findings."""

    if event.receipt != receipt.binding:
        raise contract_error(
            "receipt_binding_mismatch",
            "$.receipt",
            "event receipt hashes do not match the receipt document",
        )
    if event.outcome not in receipt.findings:
        raise contract_error(
            "outcome_not_a_finding",
            "$.outcome",
            "the receipt has no fail, indeterminate, or blocked outcome by this name",
        )


# --- the state machine ------------------------------------------------------


def apply_event(
    state: FindingState, event: ReviewEvent, event_sha256: str
) -> FindingState:
    """Move one finding by one event, or refuse.

    Every check here reads :data:`TRANSITIONS` and :data:`DECISION_RULES`; the
    function adds no rule of its own.
    """

    if event.outcome != state.outcome:
        raise contract_error(
            "outcome_mismatch", "$.outcome", "event names a different outcome"
        )
    target = TRANSITIONS[state.disposition].get(event.decision)
    if target is None:
        raise contract_error(
            "illegal_transition",
            "$.decision",
            "this decision is not permitted from the finding's current disposition",
        )
    rule = DECISION_RULES[event.decision]
    if rule.severity is SeverityRule.REQUIRED_DIFFERENT and (
        event.severity == state.severity
    ):
        raise contract_error(
            "severity_unchanged",
            "$.severity",
            "a severity change must name a different severity",
        )
    if rule.severity is SeverityRule.REQUIRED_UNCHANGED and (
        event.severity != state.severity
    ):
        raise contract_error(
            "severity_changed_by_acceptance",
            "$.severity",
            "an accepted residual risk confirms the current severity; it cannot change it",
        )
    return FindingState(
        outcome=state.outcome,
        disposition=target,
        severity=state.severity if event.severity is None else event.severity,
        owner=state.owner if event.owner is None else event.owner,
        event_count=state.event_count + 1,
        last_event_sha256=event_sha256,
    )


def _extend(state: ReviewLogState, record: LogRecord) -> ReviewLogState:
    event = record.event
    if state.receipt is not None and event.receipt != state.receipt:
        raise contract_error(
            "receipt_binding_mismatch",
            "$.receipt",
            "a log is bound to one receipt; this event names another",
        )
    findings = dict(state.findings)
    current = findings.get(event.outcome, FindingState(outcome=event.outcome))
    findings[event.outcome] = apply_event(current, event, record.event_sha256)
    return ReviewLogState(
        receipt=event.receipt,
        findings=findings,
        event_count=state.event_count + 1,
        head_sha256=record.sha256(),
    )


def _replay_error(exc: ContextSafeError, index: int) -> ContextSafeError:
    """The same code, at the log line that failed, never at the new event's path."""

    return ContextSafeError(
        code=exc.code, path=f"$.log[{index}]{exc.path[1:]}", message=exc.message
    )


def _event_error(exc: ContextSafeError) -> ContextSafeError:
    """The same code, at the field's place inside the record's ``event`` member.

    The event parser and the transition rules report paths relative to an
    event (``$.severity``, ``$.decision``). Inside a log record the event is
    the ``event`` member, so a replay refusal must say ``$.log[1].event.severity``
    or it points at a field the record does not have.
    """

    return ContextSafeError(
        code=exc.code, path=f"$.event{exc.path[1:]}", message=exc.message
    )


def _parse_record(raw: bytes, index: int, previous_sha256: str) -> LogRecord:
    parsed = parse_json_bytes(raw)
    data = object_value(parsed, "$")
    exact_keys(data, _RECORD_KEYS, "$")
    _constant(
        data["schema_version"],
        "$.schema_version",
        REVIEW_LOG_SCHEMA_VERSION,
        "unsupported_schema_version",
    )
    try:
        event = parse_review_event(data["event"])
    except ContextSafeError as exc:
        raise _event_error(exc) from exc
    record = LogRecord(
        sequence=index,
        previous_record_sha256=previous_sha256,
        event_sha256=sha256_json(event.to_dict()),
        event=event,
    )
    if data["sequence"] != index:
        raise contract_error(
            "log_sequence_mismatch", "$.sequence", "log line is out of sequence"
        )
    if data["event_sha256"] != record.event_sha256:
        raise contract_error(
            "log_chain_broken", "$.event_sha256", "event does not re-hash"
        )
    if data["previous_record_sha256"] != previous_sha256:
        raise contract_error(
            "log_chain_broken",
            "$.previous_record_sha256",
            "record does not chain to the record before it",
        )
    if record.line() != raw + b"\n":
        raise contract_error("invalid_log_line", "$", "log line is not canonical JSON")
    return record


def replay_log(raw: bytes) -> ReviewLogState:
    """Re-hash and replay every line, or refuse the whole log."""

    if not raw:
        return EMPTY_LOG_STATE
    if not raw.endswith(b"\n"):
        raise contract_error(
            "invalid_log_line", "$.log", "log does not end with a newline"
        )
    state = EMPTY_LOG_STATE
    for index, line in enumerate(raw[:-1].split(b"\n")):
        try:
            state = _replay_record(state, line, index)
        except ContextSafeError as exc:
            raise _replay_error(exc, index) from exc
    return state


def _replay_record(state: ReviewLogState, raw: bytes, index: int) -> ReviewLogState:
    """Parse one line and apply it; a transition refusal is at the event's field."""

    record = _parse_record(raw, index, state.head_sha256)
    try:
        return _extend(state, record)
    except ContextSafeError as exc:
        raise _event_error(exc) from exc


# --- the log file -----------------------------------------------------------


def _log_io_error() -> ContextSafeError:
    return ContextSafeError("log_io_error", "$", "the review log could not be accessed")


def _open_log(path: Path, flags: int) -> int:
    if _NOFOLLOW == 0:
        raise ContextSafeError(
            "input_path_unsupported",
            "$",
            "platform cannot enforce no-follow review-log access",
        )
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise _log_io_error() from exc
    try:
        details = os.fstat(descriptor)
        if not stat.S_ISREG(details.st_mode):
            raise ContextSafeError(
                "input_path_unsafe", "$", "the review log must be a regular file"
            )
        if details.st_size > MAX_LOG_BYTES:
            raise ContextSafeError(
                "input_too_large", "$", "the review log exceeds the one MiB limit"
            )
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


def _read_log(descriptor: int) -> bytes:
    chunks: list[bytes] = []
    count = 0
    try:
        while len(chunks) <= _MAX_CHUNKS:
            chunk = os.read(descriptor, _CHUNK_BYTES)
            if not chunk:
                return b"".join(chunks)
            count += len(chunk)
            if count > MAX_LOG_BYTES:
                raise ContextSafeError(
                    "input_too_large", "$", "the review log exceeds the one MiB limit"
                )
            chunks.append(chunk)
    except OSError as exc:
        raise _log_io_error() from exc
    raise ContextSafeError(
        "log_io_error", "$", "the review log did not end within its read bound"
    )


def refuse_output_over_log(output: Path | None, log: Path) -> None:
    """Refuse an ``--output`` that names the review log, however it is spelled.

    ``contextsafe.cli.main`` writes ``--output`` with a plain truncating write
    after the command has run. For every other command that is harmless; for
    ``finding`` it would replace an append-only log with the state document
    derived from it, after ``finding review`` had already appended, and exit
    0. Two comparisons, each catching a spelling the other cannot. Device and
    inode see a symlink or a hard link to a log that exists, anywhere in the
    tree. For a log that does not exist yet, the two parent directories are
    compared by device and inode (they exist, or the log could not be
    created) and the two leaf names folded for case and Unicode
    normalization, which is what a case-insensitive filesystem does to them.
    That fold is applied on every filesystem rather than asking which kind
    the log is on, so it is deliberately an over-refusal on a case-sensitive
    one, where the two names are different files: the state document can be
    written under any other name. Path text is compared through the
    filesystem, never as strings, so ``/tmp`` and ``/private/tmp`` and a
    symlinked parent chain resolve before the comparison, and ``..`` is
    collapsed lexically before the parent is looked up.

    ``contextsafe.cli`` runs this before the log is opened, so a refusal
    leaves the log exactly as it was, and once more after ``finding review``
    has appended and the log exists, so a spelling the first pass could not
    resolve, such as a platform short name, is still refused before the
    write; a refusal there has recorded the event and not written the state.
    The two paths are named by category only; the rejection carries neither.
    """

    if output is None:
        return
    if _names_the_review_log(Path(output), Path(log)):
        raise ContextSafeError(
            "output_path_unsafe", "$", "output must not name the review log"
        )


def _names_the_review_log(output: Path, log: Path) -> bool:
    return _same_existing_file(output, log) or (
        _same_existing_file(_parent(output), _parent(log))
        and _folded(output.name) == _folded(log.name)
    )


def _parent(path: Path) -> Path:
    """The directory a path names, with ``..`` collapsed lexically first, so a
    parent that only a lexical reading reaches is still compared."""

    return Path(os.path.dirname(os.path.abspath(path)))


def _same_existing_file(left: Path, right: Path) -> bool:
    """Device and inode, or ``False`` when either path cannot be stat-ed."""

    try:
        return os.path.samefile(left, right)
    except OSError:
        return False


def _folded(name: str) -> str:
    """A leaf name as a case-insensitive, normalization-insensitive filesystem
    would compare it: NFC before and after the case fold, because the fold of
    a composed character is not always composed."""

    return unicodedata.normalize("NFC", unicodedata.normalize("NFC", name).casefold())


def derive_review_state(log_path: Path) -> ReviewLogState:
    """Replay a log without touching it."""

    descriptor = _open_log(log_path, _READ_FLAGS)
    try:
        return replay_log(_read_log(descriptor))
    finally:
        os.close(descriptor)


def append_review_event(
    log_path: Path, event_value: object, receipt_value: object
) -> ReviewLogState:
    """Validate one event against the receipt and the log, then append it.

    The log is opened once, read through that descriptor, and appended through
    it. If the file is seen to have grown between the read and the write,
    nothing is written; that is a size comparison, not a lock.
    """

    receipt = parse_receipt_findings(receipt_value)
    event = parse_review_event(event_value)
    bind_to_receipt(event, receipt)
    descriptor = _open_log(log_path, _APPEND_FLAGS)
    try:
        raw = _read_log(descriptor)
        state = replay_log(raw)
        if state.receipt is not None and state.receipt != receipt.binding:
            raise contract_error(
                "receipt_binding_mismatch",
                "$.receipt",
                "the log is bound to a different receipt",
            )
        record = LogRecord(
            sequence=state.event_count,
            previous_record_sha256=state.head_sha256,
            event_sha256=sha256_json(event.to_dict()),
            event=event,
        )
        extended = _extend(state, record)
        line = record.line()
        _append_line(descriptor, line, expected_size=len(raw))
    finally:
        os.close(descriptor)
    return extended


def _append_line(descriptor: int, line: bytes, *, expected_size: int) -> None:
    try:
        size = os.fstat(descriptor).st_size
    except OSError as exc:
        raise _log_io_error() from exc
    if size != expected_size:
        raise ContextSafeError(
            "log_concurrent_append",
            "$",
            "the review log changed after it was read; nothing was written",
        )
    if size + len(line) > MAX_LOG_BYTES:
        raise ContextSafeError(
            "log_full", "$", "the review log has reached its published size limit"
        )
    try:
        written = os.write(descriptor, line)
    except OSError as exc:
        raise _log_io_error() from exc
    if written != len(line):
        raise ContextSafeError(
            "log_io_error", "$", "the review log append was incomplete"
        )
