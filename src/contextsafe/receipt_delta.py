"""Deterministic delta between two compatible receipt documents (B-037).

Two receipts for the same synthetic case under the same rule set can be
compared rule by rule: which outcomes regressed, which improved, which stayed
the same. That is the whole of what this module does, and three limits bound
it, each of which is stated in the delta document itself.

**Compatibility fails closed.** A delta is meaningful only when both receipts
describe the same thing. The two documents must carry the same case, the same
rule-set hash, the same receipt schema versions, the same concept and
checkpoint sets, and the same rules bound the same way. Any difference is an
``incompatible_receipts`` rejection that names the field class that differed
and never its value. Nothing is aligned, mapped, or "diffed anyway".

**Nothing here establishes order.** The receipts are unsigned and carry no
trusted time. ``before`` and ``after`` are the caller's labels for two files;
the delta records which file the caller called which, and a reader who swaps
them gets the mirror image. A regression in this document is "the file called
*after* fails where the file called *before* passed", not a claim about which
run happened first.

**Hash agreement is not verification.** Each document's ``payload_sha256`` is
recomputed over its payload and must match, because a delta that named a hash
which did not cover the payload it compared would be asserting something
false. That is an internal-consistency check. It verifies no signature, no
approval, no evidence, and nothing about the run that produced the receipt;
that remains B-036.

The delta is value-minimized by construction: rule identifiers, statuses,
reasons, closed change codes, counts, and hashes. No expected or observed
hash is copied through, and no envelope field enters it.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import StrEnum

from contextsafe.canonical import JsonValue, as_json_value, sha256_json
from contextsafe.contract_validation import (
    CASE_ID_PATTERN,
    RULE_ID_PATTERN,
    SEMVER_PATTERN,
    SHA256_PATTERN,
    array_value,
    boolean_value,
    bounded_string,
    contract_error,
    enum_string,
    exact_keys,
    object_value,
    timestamp_value,
    unique_strings,
)
from contextsafe.errors import ContextSafeError
from contextsafe.models import (
    RECEIPT_DOCUMENT_SCHEMA_VERSION,
    RECEIPT_SCHEMA_VERSION,
    Checkpoint,
    ConceptKind,
    OutcomeReason,
    OutcomeStatus,
)
from contextsafe.receipt import MANDATED_LIMITATIONS

DELTA_SCHEMA_VERSION = "contextsafe.receipt-delta/0.1.0"

DELTA_LIMITATIONS = (
    "receipts-are-unsigned",
    "run-order-is-not-established",
    "payload-hash-agreement-is-not-verification",
)
"""The closed disclosure set every delta carries, in publication order.

Slugs rather than sentences, like the compiled-plan and compiled-pack
limitation sets: a delta is a machine artifact, and a closed code cannot drift
into prose. The published contract pins the same three values.
"""

_DOCUMENT_KEYS = frozenset({"schema_version", "envelope", "payload", "payload_sha256"})
_ENVELOPE_KEYS = frozenset({"claimed_generated_at", "signature_status", "trusted_time"})
_PAYLOAD_KEYS = frozenset(
    {
        "schema_version",
        "case_id",
        "hashes",
        "limitations",
        "results",
        "runner_version",
        "scope",
        "summary",
    }
)
_HASH_KEYS = frozenset({"input_sha256", "result_sha256", "rule_set_sha256"})
_SCOPE_CONSTANTS: dict[str, bool] = {
    "clinical_oracle_approved": False,
    "patient_data_allowed": False,
    "synthetic_fixture_only": True,
}
_RESULT_KEYS = frozenset(
    {
        "case_id",
        "checkpoint",
        "concept",
        "evidence_sha256s",
        "expected_sha256",
        "observed_sha256s",
        "reason",
        "rule_id",
        "rule_version",
        "status",
    }
)
_STATUS_VALUES = frozenset(member.value for member in OutcomeStatus)
_REASON_VALUES = frozenset(member.value for member in OutcomeReason)
_CHECKPOINT_VALUES = frozenset(member.value for member in Checkpoint)
_CONCEPT_VALUES = frozenset(member.value for member in ConceptKind)

_FAILURES = frozenset(
    {OutcomeStatus.FAIL, OutcomeStatus.INDETERMINATE, OutcomeStatus.BLOCKED}
)
"""The statuses a pass can regress to, and an improvement can come from.

``not_applicable`` is excluded on purpose: it is predeclared by the rule, and
two receipts under one rule-set hash predeclare the same rules, so a move into
or out of it is a change the rule set does not explain. It is reported as
``changed_other`` rather than folded into either count.
"""


class RuleChange(StrEnum):
    """The closed set of things one rule's outcome can do between receipts."""

    UNCHANGED = "unchanged"
    """Same status and same reason."""

    REGRESSED = "regressed"
    """Passed in the receipt called before; fails, is indeterminate, or is
    blocked in the receipt called after."""

    IMPROVED = "improved"
    """The mirror of regressed: from fail, indeterminate, or blocked to pass."""

    CHANGED_OTHER = "changed_other"
    """Changed in a way neither count describes: a reason change under the
    same status, a move between two non-pass statuses, or a move into or out
    of not_applicable."""


class IncompatibleField(StrEnum):
    """The field classes a compatibility rejection may name.

    Never a value: the error carries the class and a location, so a rejection
    of two receipts that differ in case cannot echo either case identifier.
    """

    CASE_ID = "case_id"
    RULE_SET_SHA256 = "rule_set_sha256"
    CONCEPT_SET = "concept_set"
    CHECKPOINT_SET = "checkpoint_set"
    RULE_ID_SET = "rule_id_set"
    RULE_BINDING = "rule_binding"


_INCOMPATIBLE_LOCATIONS: dict[IncompatibleField, str] = {
    IncompatibleField.CASE_ID: "$.payload.case_id",
    IncompatibleField.RULE_SET_SHA256: "$.payload.hashes.rule_set_sha256",
    IncompatibleField.CONCEPT_SET: "$.payload.results[].concept",
    IncompatibleField.CHECKPOINT_SET: "$.payload.results[].checkpoint",
    IncompatibleField.RULE_ID_SET: "$.payload.results[].rule_id",
    IncompatibleField.RULE_BINDING: "$.payload.results[]",
}


@dataclass(frozen=True, slots=True)
class ReceiptResult:
    """One parsed outcome row, exactly as the receipt contract shapes it."""

    rule_id: str
    rule_version: str
    case_id: str
    checkpoint: str
    concept: str
    status: OutcomeStatus
    reason: OutcomeReason
    expected_sha256: str
    observed_sha256s: tuple[str, ...]
    evidence_sha256s: tuple[str, ...]

    def binding(self) -> tuple[str, str, str, str, str]:
        """Return the fields two receipts under one rule set must agree on."""

        return (
            self.rule_version,
            self.case_id,
            self.checkpoint,
            self.concept,
            self.expected_sha256,
        )


@dataclass(frozen=True, slots=True)
class ParsedReceipt:
    """A receipt document reduced to what a delta reads, after strict parsing.

    Nothing from the envelope is kept. The envelope is parsed so that a
    document claiming a signature or trusted time is rejected rather than
    silently compared, but no field of it can reach the delta.
    """

    case_id: str
    rule_set_sha256: str
    runner_version: str
    payload_sha256: str
    results: tuple[ReceiptResult, ...]

    def by_rule(self) -> dict[str, ReceiptResult]:
        """Return results keyed by rule identifier."""

        return {item.rule_id: item for item in self.results}


@dataclass(frozen=True, slots=True)
class RuleDelta:
    """One rule's outcome in both receipts and the closed change code."""

    rule_id: str
    status_before: OutcomeStatus
    status_after: OutcomeStatus
    reason_before: OutcomeReason
    reason_after: OutcomeReason
    changed: bool
    evidence_sha256s_changed: bool
    change: RuleChange

    def to_dict(self) -> dict[str, JsonValue]:
        """Return the canonical exchange representation."""

        return {
            "change": self.change.value,
            "changed": self.changed,
            "evidence_sha256s_changed": self.evidence_sha256s_changed,
            "reason_after": self.reason_after.value,
            "reason_before": self.reason_before.value,
            "rule_id": self.rule_id,
            "status_after": self.status_after.value,
            "status_before": self.status_before.value,
        }


@dataclass(frozen=True, slots=True)
class ReceiptDelta:
    """The deterministic, envelope-free delta document."""

    case_id: str
    rule_set_sha256: str
    before_payload_sha256: str
    after_payload_sha256: str
    runner_version_changed: bool
    rules: tuple[RuleDelta, ...]

    def summary(self) -> dict[str, int]:
        """Return one count per change code; every rule lands in exactly one."""

        counts = Counter(item.change.value for item in self.rules)
        return {member.value: counts.get(member.value, 0) for member in RuleChange}

    def to_dict(self) -> dict[str, JsonValue]:
        """Return the canonical exchange representation."""

        summary: dict[str, JsonValue] = dict(self.summary())
        return {
            "case_id": self.case_id,
            "limitations": list(DELTA_LIMITATIONS),
            "receipts": {
                "after": {"payload_sha256": self.after_payload_sha256},
                "before": {"payload_sha256": self.before_payload_sha256},
            },
            "rule_set_sha256": self.rule_set_sha256,
            "rules": [item.to_dict() for item in self.rules],
            "runner_version_changed": self.runner_version_changed,
            "schema_version": DELTA_SCHEMA_VERSION,
            "summary": summary,
        }


def _sha256(value: object, path: str) -> str:
    return bounded_string(value, path, pattern=SHA256_PATTERN)


def _sha256_list(value: object, path: str) -> tuple[str, ...]:
    return tuple(
        _sha256(item, f"{path}[{index}]")
        for index, item in enumerate(array_value(value, path))
    )


def _count(value: object, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise contract_error("invalid_type", path, "expected a non-negative integer")
    return value


def _schema_version(value: object, path: str, expected: str) -> None:
    if value != expected:
        raise contract_error(
            "unsupported_schema", path, "schema version is not supported"
        )


def _parse_envelope(value: object, path: str) -> None:
    """Reject an envelope this iteration cannot have produced; keep nothing.

    A document that says it is signed, or that its time is trusted, is not one
    the runner emits, and comparing it as if it were would lend the delta a
    claim neither receipt is entitled to.
    """

    envelope = object_value(value, path)
    exact_keys(envelope, _ENVELOPE_KEYS, path)
    if envelope["claimed_generated_at"] is not None:
        timestamp_value(
            envelope["claimed_generated_at"], f"{path}.claimed_generated_at"
        )
    enum_string(
        envelope["signature_status"],
        f"{path}.signature_status",
        frozenset({"not_signed"}),
    )
    if boolean_value(envelope["trusted_time"], f"{path}.trusted_time"):
        raise contract_error(
            "invalid_enum", f"{path}.trusted_time", "value is not supported"
        )


def _parse_scope(value: object, path: str) -> None:
    scope = object_value(value, path)
    exact_keys(scope, frozenset(_SCOPE_CONSTANTS), path)
    for name, expected in _SCOPE_CONSTANTS.items():
        if boolean_value(scope[name], f"{path}.{name}") is not expected:
            raise contract_error(
                "invalid_enum", f"{path}.{name}", "value is not supported"
            )


def _parse_limitations(value: object, path: str) -> None:
    items = array_value(value, path)
    if len(items) != len(MANDATED_LIMITATIONS):
        raise contract_error(
            "invalid_enum", path, "limitations are not the mandated disclosure set"
        )
    for index, (item, expected) in enumerate(
        zip(items, MANDATED_LIMITATIONS, strict=True)
    ):
        if item != expected:
            raise contract_error(
                "invalid_enum",
                f"{path}[{index}]",
                "limitation is not the mandated disclosure",
            )


def _parse_result(value: object, path: str) -> ReceiptResult:
    result = object_value(value, path)
    exact_keys(result, _RESULT_KEYS, path)
    return ReceiptResult(
        rule_id=bounded_string(
            result["rule_id"], f"{path}.rule_id", pattern=RULE_ID_PATTERN
        ),
        rule_version=bounded_string(
            result["rule_version"], f"{path}.rule_version", pattern=SEMVER_PATTERN
        ),
        case_id=bounded_string(
            result["case_id"], f"{path}.case_id", pattern=CASE_ID_PATTERN
        ),
        checkpoint=enum_string(
            result["checkpoint"], f"{path}.checkpoint", _CHECKPOINT_VALUES
        ),
        concept=enum_string(result["concept"], f"{path}.concept", _CONCEPT_VALUES),
        status=OutcomeStatus(
            enum_string(result["status"], f"{path}.status", _STATUS_VALUES)
        ),
        reason=OutcomeReason(
            enum_string(result["reason"], f"{path}.reason", _REASON_VALUES)
        ),
        expected_sha256=_sha256(result["expected_sha256"], f"{path}.expected_sha256"),
        observed_sha256s=_sha256_list(
            result["observed_sha256s"], f"{path}.observed_sha256s"
        ),
        evidence_sha256s=_sha256_list(
            result["evidence_sha256s"], f"{path}.evidence_sha256s"
        ),
    )


def _parse_results(value: object, path: str) -> tuple[ReceiptResult, ...]:
    items = array_value(value, path)
    if not items:
        raise contract_error("invalid_type", path, "expected at least one result")
    results = tuple(
        _parse_result(item, f"{path}[{index}]") for index, item in enumerate(items)
    )
    unique_strings(
        tuple(item.rule_id for item in results), path, code="duplicate_rule_id"
    )
    return results


def _parse_summary(
    value: object, path: str, results: tuple[ReceiptResult, ...]
) -> None:
    """Require the summary to be the count of the results it summarizes."""

    summary = object_value(value, path)
    exact_keys(summary, _STATUS_VALUES, path)
    counted = Counter(item.status.value for item in results)
    for status in sorted(_STATUS_VALUES):
        if _count(summary[status], f"{path}.{status}") != counted.get(status, 0):
            raise contract_error(
                "receipt_inconsistent",
                f"{path}.{status}",
                "summary count does not match the results",
            )


def _parse_payload(value: object, path: str) -> ParsedReceipt:
    payload = object_value(value, path)
    exact_keys(payload, _PAYLOAD_KEYS, path)
    _schema_version(
        payload["schema_version"], f"{path}.schema_version", RECEIPT_SCHEMA_VERSION
    )
    hashes = object_value(payload["hashes"], f"{path}.hashes")
    exact_keys(hashes, _HASH_KEYS, f"{path}.hashes")
    for name in sorted(_HASH_KEYS):
        _sha256(hashes[name], f"{path}.hashes.{name}")
    _parse_limitations(payload["limitations"], f"{path}.limitations")
    _parse_scope(payload["scope"], f"{path}.scope")
    results = _parse_results(payload["results"], f"{path}.results")
    _parse_summary(payload["summary"], f"{path}.summary", results)
    return ParsedReceipt(
        case_id=bounded_string(
            payload["case_id"], f"{path}.case_id", pattern=CASE_ID_PATTERN
        ),
        rule_set_sha256=_sha256(
            hashes["rule_set_sha256"], f"{path}.hashes.rule_set_sha256"
        ),
        runner_version=bounded_string(
            payload["runner_version"],
            f"{path}.runner_version",
            pattern=SEMVER_PATTERN,
        ),
        payload_sha256=sha256_json(as_json_value(payload)),
        results=results,
    )


def parse_receipt_document(document: JsonValue, *, path: str = "$") -> ParsedReceipt:
    """Parse one receipt document strictly, or reject it whole.

    Every object is closed, every enum is the published one, the payload hash
    must cover the payload, and the summary must count the results. ``path``
    prefixes every pointer so a caller comparing two documents can say which
    one was rejected without saying anything about what it contained.
    """

    data = object_value(document, path)
    exact_keys(data, _DOCUMENT_KEYS, path)
    _schema_version(
        data["schema_version"],
        f"{path}.schema_version",
        RECEIPT_DOCUMENT_SCHEMA_VERSION,
    )
    _parse_envelope(data["envelope"], f"{path}.envelope")
    parsed = _parse_payload(data["payload"], f"{path}.payload")
    declared = _sha256(data["payload_sha256"], f"{path}.payload_sha256")
    if declared != parsed.payload_sha256:
        raise contract_error(
            "receipt_inconsistent",
            f"{path}.payload_sha256",
            "payload hash does not cover the payload",
        )
    return parsed


def _incompatible(field: IncompatibleField) -> ContextSafeError:
    return contract_error(
        "incompatible_receipts",
        _INCOMPATIBLE_LOCATIONS[field],
        f"receipts differ in {field.value}",
    )


def check_compatible(before: ParsedReceipt, after: ParsedReceipt) -> None:
    """Raise ``incompatible_receipts`` unless a delta between the two means something.

    The checks run in a fixed order and the first failure is reported, so the
    same pair always produces the same rejection. Both schema versions are
    already pinned by the parser to the one version this runner emits, which
    is stricter than "identical" and is why they do not appear here.
    """

    if before.case_id != after.case_id:
        raise _incompatible(IncompatibleField.CASE_ID)
    if before.rule_set_sha256 != after.rule_set_sha256:
        raise _incompatible(IncompatibleField.RULE_SET_SHA256)
    before_rules = before.by_rule()
    after_rules = after.by_rule()
    if {r.concept for r in before.results} != {r.concept for r in after.results}:
        raise _incompatible(IncompatibleField.CONCEPT_SET)
    if {r.checkpoint for r in before.results} != {r.checkpoint for r in after.results}:
        raise _incompatible(IncompatibleField.CHECKPOINT_SET)
    if before_rules.keys() != after_rules.keys():
        raise _incompatible(IncompatibleField.RULE_ID_SET)
    for rule_id in sorted(before_rules):
        if before_rules[rule_id].binding() != after_rules[rule_id].binding():
            raise _incompatible(IncompatibleField.RULE_BINDING)


def _classify(before: ReceiptResult, after: ReceiptResult) -> RuleChange:
    if before.status is after.status and before.reason is after.reason:
        return RuleChange.UNCHANGED
    if before.status is OutcomeStatus.PASSED and after.status in _FAILURES:
        return RuleChange.REGRESSED
    if before.status in _FAILURES and after.status is OutcomeStatus.PASSED:
        return RuleChange.IMPROVED
    return RuleChange.CHANGED_OTHER


def _rule_delta(before: ReceiptResult, after: ReceiptResult) -> RuleDelta:
    change = _classify(before, after)
    return RuleDelta(
        rule_id=before.rule_id,
        status_before=before.status,
        status_after=after.status,
        reason_before=before.reason,
        reason_after=after.reason,
        changed=change is not RuleChange.UNCHANGED,
        evidence_sha256s_changed=(
            tuple(sorted(before.evidence_sha256s))
            != tuple(sorted(after.evidence_sha256s))
        ),
        change=change,
    )


def diff_receipts(before: ParsedReceipt, after: ParsedReceipt) -> ReceiptDelta:
    """Compute the delta, or raise ``incompatible_receipts``.

    Pure and order-independent: results are joined by rule identifier and
    emitted in rule-identifier order, so the order either receipt listed them
    in cannot reach the delta.
    """

    check_compatible(before, after)
    before_rules = before.by_rule()
    after_rules = after.by_rule()
    return ReceiptDelta(
        case_id=before.case_id,
        rule_set_sha256=before.rule_set_sha256,
        before_payload_sha256=before.payload_sha256,
        after_payload_sha256=after.payload_sha256,
        runner_version_changed=before.runner_version != after.runner_version,
        rules=tuple(
            _rule_delta(before_rules[rule_id], after_rules[rule_id])
            for rule_id in sorted(before_rules)
        ),
    )
