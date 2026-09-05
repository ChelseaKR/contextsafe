"""The laboratory result observation family and its result, range, and flag predicates.

**Nothing here is clinical content.** Every analyte code, unit, bound, and
flag this module admits is a fixture token invented for software tests. No
laboratory medical director, clinical reviewer, or community reviewer has
approved any value, any interval, or any predicate below, and nothing here
is a reference-interval recommendation for any analyte, any person, or any
population. ``docs/05-DATA-AND-EVIDENCE.md`` section 4 is explicit that a
partner's laboratory medical director supplies the real fixture analyte
code, units, bounds, inclusivity, age band, effective version, and expected
flag; until that exists, what ships here is software-test data and the
predicates are an ungoverned mechanism for the assertions A-025 to A-030,
not the assertions themselves. Each covers less than the assertion it is
offered for: this family carries no age band and no effective oracle
version, which A-027 requires, and no result status, which A-026 requires,
so no predicate below decides those halves of anything.

**A separate observation kind, not a sixth concept.** A laboratory result is
not a Gender Harmony concept, so :class:`~contextsafe.models.ConceptKind` is
untouched: gender identity, recorded sex or gender, sex parameter for
clinical use, name to use, and pronouns remain exactly five, none of them
substitutable for another, and nothing here reads or writes any of them. A
result carries its own document (``contextsafe.result-set/0.1.0``), its own
rule document (``contextsafe.result-rule-set/0.1.0``), and its own predicate
and reason vocabularies, so widening this family can never widen the case
manifest, the observation set, or the receipt. The alternative — a sixth
``ConceptKind`` — would have added a required key to the case manifest's
closed concept set, put a laboratory value on the identity divergence
section, and made every identity contract move for a laboratory change. The
concepts stay distinct by construction rather than by review.

**A result never reaches a receipt yet.** The evaluator below returns typed
outcomes to its caller; no receipt section, no divergence entry, and no
command carries them, so the published receipt contract, its closed
outcome-reason set, and its structural-pointer vocabulary are all unchanged
by this module. That is also why an importer points a result at the row it
was read from (``$.rows[3]``) rather than at a cell: a cell word such as
``analyte`` would widen
:data:`~contextsafe.validation.STRUCTURAL_POINTER_SEGMENTS`, and that set is
copied into the receipt contract's pointer pattern, so widening it is a
receipt version bump. The row is where the result was read from; the cells
are what it was built out of.

**Fail closed, and absence is never normal.** A range the profile cannot
type is not an absent range and neither is a value it cannot compare: each
is reported ``indeterminate`` with its own reason, never ``pass`` and never
an accusation against the boundary. An absent range is a ``fail`` for
``reference_interval_present`` (A-029: an X in a recorded-sex-or-gender
field must not produce a silent blank interval) and ``indeterminate`` for
``flag_consistent_with_interval`` (A-030: an out-of-range value is never
reported normal because the range is missing). An out-of-range value
returned with no flag at all is a ``fail``; an in-range value with no flag
is ``indeterminate``, because a flag nobody sent is not evidence that the
result is normal.
"""

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from contextsafe.canonical import JsonValue, sha256_json
from contextsafe.contract_validation import (
    CASE_ID_PATTERN,
    SEMVER_PATTERN,
    array_value,
    boolean_value,
    bounded_string,
    contract_error,
    exact_keys,
    object_value,
    unique_strings,
)
from contextsafe.models import (
    Checkpoint,
    EvidencePointer,
    OutcomeStatus,
    SyntheticCase,
)
from contextsafe.validation import (
    parse_case,
    parse_structural_pointer,
    reject_prohibited_fields,
)

RESULT_SCHEMA_VERSION = "contextsafe.result/0.1.0"
"""The shape of one laboratory result observation."""

RESULT_SET_SCHEMA_VERSION = "contextsafe.result-set/0.1.0"
"""The shape of a versioned set of laboratory result observations."""

RESULT_RULE_SET_SCHEMA_VERSION = "contextsafe.result-rule-set/0.1.0"
"""The shape of a versioned set of ungoverned laboratory result rules."""

MAX_RESULTS = 512
"""The most results one document may carry."""

MAX_RESULT_RULES = 512
"""The most rules one result rule set may carry.

The document-size bound this family shares with :data:`MAX_RESULTS`, and
not a claim that five hundred rules could exist: rule ids are unique and
``A-Lnn`` admits a hundred of them, so a document reaches this bound only
by repeating one, and the size check is what refuses it first.
"""

RESULT_ID_PATTERN = re.compile(r"^RES-[A-Z0-9][A-Z0-9-]{2,47}$")
"""A result observation identifier."""

RESULT_RULE_ID_PATTERN = re.compile(r"^A-L[0-9]{2}$")
"""A laboratory rule identifier, distinct from the identity family's ``A-Inn``."""

RESULT_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9<>][A-Za-z0-9:/_.%<>-]{0,63}$")
"""An analyte code, value, unit, or flag cell: a bounded token with no whitespace.

The same alphabet the LIS export readers already hold a result cell to, so a
source token that reaches an importer reaches this family unchanged. It
bounds what a token may look like and says nothing about what it means:
binding a token to an approved analyte or unit is a mapping profile's job
(B-026) and no profile is reviewed.
"""

DECIMAL_PATTERN = re.compile(r"^-?(?:0|[1-9][0-9]{0,11})(?:\.[0-9]{1,6})?$")
"""A decimal carried as a string: bounded digits, optional sign, no exponent.

Decimals are compared exactly, as decimals, so a bound and a value that
print the same compare the same. Nothing here is a float and nothing is
rounded.
"""

SYNTHETIC_IDENTIFIER_PATTERN = re.compile(
    r"^(?:ORDER-)?CSYN-[A-Z0-9][A-Z0-9_.:-]{0,95}$"
)
"""An order or specimen identifier: accession-shaped, so synthetic only.

One grammar for both, and the same one the LIS export readers hold an
identifier cell to, so an identifier that reaches an importer reaches this
family unchanged. Which of the two an identifier is comes from the field it
sits in, never from its prefix: a rule declares the order and the specimen it
expects, and ``result_linked`` compares them.
"""

_DECIMAL = r"-?(?:0|[1-9][0-9]{0,11})(?:\.[0-9]{1,6})?"
_UNIT = r"[A-Za-z0-9][A-Za-z0-9:/_.%<>-]{0,63}"
REFERENCE_INTERVAL_TOKEN_PATTERN = re.compile(
    rf"^(ge|gt)({_DECIMAL}):(le|lt)({_DECIMAL}):({_UNIT})$"
)
"""The one reference-interval dialect this ungoverned profile can type.

``ge2.500:le7.500:fixture-unit-alpha`` is a lower bound of 2.500 inclusive,
an upper bound of 7.500 inclusive, and a unit. ``gt`` and ``lt`` are the
exclusive forms, so inclusivity is stated rather than assumed — A-027
requires it, and no widely used export format carries it in a single cell.
A range cell in any other dialect is not this one and is not guessed at: it
is typed ``not_typed`` and every outcome that would have read it is
indeterminate.
"""


class CellStatus(StrEnum):
    """What a source said in a range or flag cell, before anything reads it."""

    ABSENT = "absent"
    """The source returned nothing here."""

    TYPED = "typed"
    """The source returned something this profile could type."""

    NOT_TYPED = "not_typed"
    """The source returned something in a dialect this profile cannot type.

    Distinct from ``absent`` on purpose: a range nobody sent and a range
    nobody here can read are different facts, and only the first is a
    finding against the boundary.
    """


class AbnormalFlag(StrEnum):
    """The closed, invented flag vocabulary this family admits.

    Deliberately not any laboratory's flag alphabet. A real ``H``, ``L``, or
    ``N`` from a partner export is a token this profile cannot type until a
    reviewed mapping profile binds it, which is what ``not_typed`` is for.
    """

    BELOW_LOW = "fixture-flag-below-low"
    IN_RANGE = "fixture-flag-in-range"
    ABOVE_HIGH = "fixture-flag-above-high"


class IntervalPosition(StrEnum):
    """Where a value sits against a typed interval's own bounds."""

    BELOW_LOW = "below_low"
    IN_RANGE = "in_range"
    ABOVE_HIGH = "above_high"


_FLAG_FOR_POSITION: Mapping[IntervalPosition, AbnormalFlag] = {
    IntervalPosition.BELOW_LOW: AbnormalFlag.BELOW_LOW,
    IntervalPosition.IN_RANGE: AbnormalFlag.IN_RANGE,
    IntervalPosition.ABOVE_HIGH: AbnormalFlag.ABOVE_HIGH,
}
"""The flag a fixture's own bounds imply at each position, and nothing more."""


class ResultPredicate(StrEnum):
    """The closed set of pure predicates a laboratory rule may name.

    Reference-only and ungoverned mechanisms for A-025 to A-030. Each is a
    pure function of the validated bundle and the rule: no clock, no
    environment, no clinical judgment, and no inference from any identity
    concept.
    """

    RESULT_LINKED = "result_linked"
    """A-025: the result carries the order and specimen the rule declares."""

    ANALYTE_VALUE_UNIT_PRESERVED = "analyte_value_unit_preserved"
    """A-026: analyte code, value, and unit are exactly the declared ones."""

    REFERENCE_INTERVAL_PRESENT = "reference_interval_present"
    """A-027, A-029: bounds, inclusivity, and a unit that fits the result."""

    FLAG_CONSISTENT_WITH_INTERVAL = "flag_consistent_with_interval"
    """A-028, A-030: the returned flag is the one the fixture's bounds imply."""


class ResultOutcomeReason(StrEnum):
    """The closed set of reasons a laboratory outcome may carry."""

    PREDECLARED_NOT_APPLICABLE = "predeclared_not_applicable"
    MISSING_EVIDENCE = "missing_evidence"
    RESULT_LINKED = "result_linked"
    RESULT_NOT_LINKED = "result_not_linked"
    ANALYTE_VALUE_UNIT_PRESERVED = "analyte_value_unit_preserved"
    ANALYTE_VALUE_UNIT_CHANGED = "analyte_value_unit_changed"
    REFERENCE_INTERVAL_PRESENT = "reference_interval_present"
    REFERENCE_INTERVAL_ABSENT = "reference_interval_absent"
    REFERENCE_INTERVAL_NOT_TYPED = "reference_interval_not_typed"
    REFERENCE_INTERVAL_UNIT_MISMATCH = "reference_interval_unit_mismatch"
    FLAG_CONSISTENT_WITH_INTERVAL = "flag_consistent_with_interval"
    FLAG_INCONSISTENT_WITH_INTERVAL = "flag_inconsistent_with_interval"
    FLAG_MISSING_OUT_OF_RANGE = "flag_missing_out_of_range"
    FLAG_ABSENT_IN_RANGE = "flag_absent_in_range"
    FLAG_NOT_TYPED = "flag_not_typed"
    VALUE_NOT_COMPARABLE = "value_not_comparable"


AFFIRMATIVE_RESULT_REASONS: frozenset[ResultOutcomeReason] = frozenset(
    {
        ResultOutcomeReason.RESULT_LINKED,
        ResultOutcomeReason.ANALYTE_VALUE_UNIT_PRESERVED,
        ResultOutcomeReason.REFERENCE_INTERVAL_PRESENT,
        ResultOutcomeReason.FLAG_CONSISTENT_WITH_INTERVAL,
    }
)
"""The only reasons a laboratory ``pass`` may carry."""


@dataclass(frozen=True, slots=True)
class ReferenceInterval:
    """One typed interval: two bounds, their inclusivity, and a unit.

    A software-test interval. It is not a reference range for any analyte,
    and it is never chosen by, derived from, or associated with any identity
    concept.
    """

    low: str
    low_inclusive: bool
    high: str
    high_inclusive: bool
    unit: str

    def to_dict(self) -> dict[str, JsonValue]:
        """Return the canonical exchange representation."""

        return {
            "high": self.high,
            "high_inclusive": self.high_inclusive,
            "low": self.low,
            "low_inclusive": self.low_inclusive,
            "status": CellStatus.TYPED.value,
            "unit": self.unit,
        }

    def position_of(self, value: Decimal) -> IntervalPosition:
        """Return where ``value`` sits against these bounds, inclusivity honored."""

        low = Decimal(self.low)
        high = Decimal(self.high)
        if value < low or (value == low and not self.low_inclusive):
            return IntervalPosition.BELOW_LOW
        if value > high or (value == high and not self.high_inclusive):
            return IntervalPosition.ABOVE_HIGH
        return IntervalPosition.IN_RANGE


@dataclass(frozen=True, slots=True)
class LaboratoryResult:
    """One laboratory result observation at one checkpoint.

    Every field is a bounded token or a decimal carried as a string. No
    field of this record is, becomes, or is derived from gender identity,
    recorded sex or gender, sex parameter for clinical use, name to use, or
    pronouns, and none of those is derived from anything here.
    """

    schema_version: str
    result_id: str
    case_id: str
    checkpoint: Checkpoint
    analyte_code: str
    value: str
    unit: str
    order_id: str
    specimen_id: str
    interval_status: CellStatus
    reference_interval: ReferenceInterval | None
    flag_status: CellStatus
    abnormal_flag: AbnormalFlag | None
    evidence: EvidencePointer
    mapping_version: str

    def __post_init__(self) -> None:
        if (self.interval_status is CellStatus.TYPED) != (
            self.reference_interval is not None
        ):
            raise contract_error(
                "invalid_reference_interval",
                "$.reference_interval",
                "a typed interval carries its bounds and no other status does",
            )
        if (self.flag_status is CellStatus.TYPED) != (self.abnormal_flag is not None):
            raise contract_error(
                "invalid_abnormal_flag",
                "$.abnormal_flag",
                "a typed flag carries its value and no other status does",
            )

    def to_dict(self) -> dict[str, JsonValue]:
        """Return the canonical exchange representation."""

        interval: JsonValue = (
            {"status": self.interval_status.value}
            if self.reference_interval is None
            else self.reference_interval.to_dict()
        )
        flag: JsonValue = (
            {"status": self.flag_status.value}
            if self.abnormal_flag is None
            else {"flag": self.abnormal_flag.value, "status": CellStatus.TYPED.value}
        )
        return {
            "abnormal_flag": flag,
            "analyte_code": self.analyte_code,
            "case_id": self.case_id,
            "checkpoint": self.checkpoint.value,
            "evidence": self.evidence.to_dict(),
            "mapping_version": self.mapping_version,
            "order_id": self.order_id,
            "reference_interval": interval,
            "result_id": self.result_id,
            "schema_version": self.schema_version,
            "specimen_id": self.specimen_id,
            "unit": self.unit,
            "value": self.value,
        }


_PREDICATE_FIELDS: Mapping[ResultPredicate, frozenset[str]] = {
    ResultPredicate.RESULT_LINKED: frozenset(
        {"expected_order_id", "expected_specimen_id"}
    ),
    ResultPredicate.ANALYTE_VALUE_UNIT_PRESERVED: frozenset(
        {"expected_analyte_code", "expected_value", "expected_unit"}
    ),
    ResultPredicate.REFERENCE_INTERVAL_PRESENT: frozenset(),
    ResultPredicate.FLAG_CONSISTENT_WITH_INTERVAL: frozenset(),
}
"""The fields each predicate reads; any other predicate field is unknown.

``reference_interval_present`` and ``flag_consistent_with_interval`` declare
nothing: the first is a presence claim and the second is computed from the
fixture's own bounds, so neither can be told what to conclude.
"""

_RULE_KEYS = frozenset(
    {
        "rule_id",
        "version",
        "case_id",
        "checkpoint",
        "result_id",
        "predicate",
        "required",
    }
)


@dataclass(frozen=True, slots=True)
class ResultRule:
    """One pure rule over one laboratory result observation."""

    rule_id: str
    version: str
    case_id: str
    checkpoint: Checkpoint
    result_id: str
    predicate: ResultPredicate
    required: bool
    expected_order_id: str | None = None
    expected_specimen_id: str | None = None
    expected_analyte_code: str | None = None
    expected_value: str | None = None
    expected_unit: str | None = None

    def to_dict(self) -> dict[str, JsonValue]:
        """Return the canonical exchange representation, defaults omitted."""

        value: dict[str, JsonValue] = {
            "case_id": self.case_id,
            "checkpoint": self.checkpoint.value,
            "predicate": self.predicate.value,
            "required": self.required,
            "result_id": self.result_id,
            "rule_id": self.rule_id,
            "version": self.version,
        }
        declared = {
            "expected_analyte_code": self.expected_analyte_code,
            "expected_order_id": self.expected_order_id,
            "expected_specimen_id": self.expected_specimen_id,
            "expected_unit": self.expected_unit,
            "expected_value": self.expected_value,
        }
        value.update({key: item for key, item in declared.items() if item is not None})
        return value


@dataclass(frozen=True, slots=True)
class ResultRuleSet:
    """A versioned collection of deterministic laboratory rules."""

    schema_version: str
    rules: tuple[ResultRule, ...]

    def to_dict(self) -> dict[str, JsonValue]:
        """Return rules in deterministic rule-ID order."""

        return {
            "rules": [
                rule.to_dict() for rule in sorted(self.rules, key=lambda x: x.rule_id)
            ],
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True, slots=True)
class ResultBundle:
    """Validated inputs to the pure laboratory evaluator."""

    case: SyntheticCase
    results: tuple[LaboratoryResult, ...]
    rule_set: ResultRuleSet


def type_reference_interval_cell(
    cell: str,
) -> tuple[CellStatus, ReferenceInterval | None]:
    """Type one range cell without guessing what an unreadable one meant.

    Empty is ``absent``: the source returned no interval. A cell in this
    profile's dialect whose bounds are usable is ``typed``. Everything else
    — another dialect, an inverted pair, an empty span — is ``not_typed``,
    which is neither an interval nor the absence of one.
    """

    if not cell:
        return CellStatus.ABSENT, None
    match = REFERENCE_INTERVAL_TOKEN_PATTERN.fullmatch(cell)
    if match is None:
        return CellStatus.NOT_TYPED, None
    interval = ReferenceInterval(
        low=match.group(2),
        low_inclusive=match.group(1) == "ge",
        high=match.group(4),
        high_inclusive=match.group(3) == "le",
        unit=match.group(5),
    )
    if _interval_is_empty(interval):
        return CellStatus.NOT_TYPED, None
    return CellStatus.TYPED, interval


def type_abnormal_flag_cell(cell: str) -> tuple[CellStatus, AbnormalFlag | None]:
    """Type one flag cell against the closed fixture vocabulary, or not at all."""

    if not cell:
        return CellStatus.ABSENT, None
    try:
        return CellStatus.TYPED, AbnormalFlag(cell)
    except ValueError:
        return CellStatus.NOT_TYPED, None


def _interval_is_empty(interval: ReferenceInterval) -> bool:
    """True when no decimal can sit inside the interval's own bounds."""

    low = Decimal(interval.low)
    high = Decimal(interval.high)
    if low > high:
        return True
    return low == high and not (interval.low_inclusive and interval.high_inclusive)


def _checkpoint(value: object, path: str) -> Checkpoint:
    raw = bounded_string(value, path)
    try:
        return Checkpoint(raw)
    except ValueError as exc:
        raise contract_error("invalid_enum", path, "value is not supported") from exc


def _cell_status(value: object, path: str) -> CellStatus:
    raw = bounded_string(value, path)
    try:
        return CellStatus(raw)
    except ValueError as exc:
        raise contract_error("invalid_enum", path, "value is not supported") from exc


def _parse_reference_interval(
    value: object, path: str
) -> tuple[CellStatus, ReferenceInterval | None]:
    """Parse the interval block: a status, and bounds only when typed."""

    data = object_value(value, path)
    bounds = frozenset({"low", "low_inclusive", "high", "high_inclusive", "unit"})
    exact_keys(data, frozenset({"status"}), path, optional=bounds)
    status = _cell_status(data["status"], f"{path}.status")
    if status is not CellStatus.TYPED:
        exact_keys(data, frozenset({"status"}), path)
        return status, None
    exact_keys(data, frozenset({"status"}) | bounds, path)
    interval = ReferenceInterval(
        low=bounded_string(data["low"], f"{path}.low", pattern=DECIMAL_PATTERN),
        low_inclusive=boolean_value(data["low_inclusive"], f"{path}.low_inclusive"),
        high=bounded_string(data["high"], f"{path}.high", pattern=DECIMAL_PATTERN),
        high_inclusive=boolean_value(data["high_inclusive"], f"{path}.high_inclusive"),
        unit=bounded_string(data["unit"], f"{path}.unit", pattern=RESULT_TOKEN_PATTERN),
    )
    if _interval_is_empty(interval):
        raise contract_error(
            "invalid_reference_interval",
            path,
            "a typed interval must admit at least one value",
        )
    return status, interval


def _parse_abnormal_flag(
    value: object, path: str
) -> tuple[CellStatus, AbnormalFlag | None]:
    """Parse the flag block: a status, and a closed flag only when typed."""

    data = object_value(value, path)
    exact_keys(data, frozenset({"status"}), path, optional=frozenset({"flag"}))
    status = _cell_status(data["status"], f"{path}.status")
    if status is not CellStatus.TYPED:
        exact_keys(data, frozenset({"status"}), path)
        return status, None
    exact_keys(data, frozenset({"status", "flag"}), path)
    raw = bounded_string(data["flag"], f"{path}.flag")
    try:
        return status, AbnormalFlag(raw)
    except ValueError as exc:
        raise contract_error(
            "invalid_abnormal_flag", f"{path}.flag", "flag is not supported"
        ) from exc


def _parse_evidence(value: object, path: str) -> EvidencePointer:
    data = object_value(value, path)
    exact_keys(data, frozenset({"source_sha256", "source_pointer"}), path)
    return EvidencePointer(
        source_sha256=bounded_string(
            data["source_sha256"],
            f"{path}.source_sha256",
            pattern=re.compile(r"^[0-9a-f]{64}$"),
        ),
        source_pointer=parse_structural_pointer(
            data["source_pointer"], f"{path}.source_pointer"
        ),
    )


def parse_result(value: object, path: str) -> LaboratoryResult:
    """Validate and parse one laboratory result observation."""

    data = object_value(value, path)
    exact_keys(
        data,
        frozenset(
            {
                "schema_version",
                "result_id",
                "case_id",
                "checkpoint",
                "analyte_code",
                "value",
                "unit",
                "order_id",
                "specimen_id",
                "reference_interval",
                "abnormal_flag",
                "evidence",
                "mapping_version",
            }
        ),
        path,
    )
    if bounded_string(data["schema_version"], f"{path}.schema_version") != (
        RESULT_SCHEMA_VERSION
    ):
        raise contract_error(
            "unsupported_schema",
            f"{path}.schema_version",
            "result schema is unsupported",
        )
    interval_status, interval = _parse_reference_interval(
        data["reference_interval"], f"{path}.reference_interval"
    )
    flag_status, flag = _parse_abnormal_flag(
        data["abnormal_flag"], f"{path}.abnormal_flag"
    )
    return LaboratoryResult(
        schema_version=RESULT_SCHEMA_VERSION,
        result_id=bounded_string(
            data["result_id"], f"{path}.result_id", pattern=RESULT_ID_PATTERN
        ),
        case_id=bounded_string(
            data["case_id"], f"{path}.case_id", pattern=CASE_ID_PATTERN
        ),
        checkpoint=_checkpoint(data["checkpoint"], f"{path}.checkpoint"),
        analyte_code=bounded_string(
            data["analyte_code"], f"{path}.analyte_code", pattern=RESULT_TOKEN_PATTERN
        ),
        value=bounded_string(
            data["value"], f"{path}.value", pattern=RESULT_TOKEN_PATTERN
        ),
        unit=bounded_string(data["unit"], f"{path}.unit", pattern=RESULT_TOKEN_PATTERN),
        order_id=bounded_string(
            data["order_id"], f"{path}.order_id", pattern=SYNTHETIC_IDENTIFIER_PATTERN
        ),
        specimen_id=bounded_string(
            data["specimen_id"],
            f"{path}.specimen_id",
            pattern=SYNTHETIC_IDENTIFIER_PATTERN,
        ),
        interval_status=interval_status,
        reference_interval=interval,
        flag_status=flag_status,
        abnormal_flag=flag,
        evidence=_parse_evidence(data["evidence"], f"{path}.evidence"),
        mapping_version=bounded_string(
            data["mapping_version"], f"{path}.mapping_version", pattern=SEMVER_PATTERN
        ),
    )


def parse_result_set(value: object) -> tuple[LaboratoryResult, ...]:
    """Validate and parse a versioned laboratory result set."""

    reject_prohibited_fields(value)
    data = object_value(value, "$")
    exact_keys(data, frozenset({"schema_version", "results"}), "$")
    if bounded_string(data["schema_version"], "$.schema_version") != (
        RESULT_SET_SCHEMA_VERSION
    ):
        raise contract_error(
            "unsupported_schema",
            "$.schema_version",
            "result-set schema is unsupported",
        )
    raw = array_value(data["results"], "$.results")
    if not raw or len(raw) > MAX_RESULTS:
        raise contract_error(
            "invalid_result_count",
            "$.results",
            f"between 1 and {MAX_RESULTS} results are required",
        )
    results = tuple(
        parse_result(item, f"$.results[{index}]") for index, item in enumerate(raw)
    )
    unique_strings(
        tuple(item.result_id for item in results),
        "$.results",
        code="duplicate_result_id",
    )
    return results


def _predicate(value: object, path: str) -> ResultPredicate:
    raw = bounded_string(value, path)
    try:
        return ResultPredicate(raw)
    except ValueError as exc:
        raise contract_error("invalid_enum", path, "value is not supported") from exc


def _rule_keys(data: dict[str, object], path: str) -> ResultPredicate:
    """Return the rule's predicate after holding its key set to that predicate."""

    if "predicate" not in data:
        raise contract_error(
            "missing_field", f"{path}.predicate", "required field is missing"
        )
    predicate = _predicate(data["predicate"], f"{path}.predicate")
    specific = _PREDICATE_FIELDS[predicate]
    unexpected = data.keys() - _RULE_KEYS - specific
    if unexpected:
        raise contract_error(
            "unknown_field", path, "field is not allowed for this predicate"
        )
    missing = sorted((_RULE_KEYS | specific) - data.keys())
    if missing:
        raise contract_error(
            "missing_field", f"{path}.{missing[0]}", "required field is missing"
        )
    return predicate


def _expected(
    data: dict[str, object], path: str, field: str, pattern: re.Pattern[str]
) -> str | None:
    if field not in data:
        return None
    return bounded_string(data[field], f"{path}.{field}", pattern=pattern)


def parse_result_rule(value: object, path: str) -> ResultRule:
    """Validate and parse one laboratory rule."""

    data = object_value(value, path)
    predicate = _rule_keys(data, path)
    return ResultRule(
        rule_id=bounded_string(
            data["rule_id"], f"{path}.rule_id", pattern=RESULT_RULE_ID_PATTERN
        ),
        version=bounded_string(
            data["version"], f"{path}.version", pattern=SEMVER_PATTERN
        ),
        case_id=bounded_string(
            data["case_id"], f"{path}.case_id", pattern=CASE_ID_PATTERN
        ),
        checkpoint=_checkpoint(data["checkpoint"], f"{path}.checkpoint"),
        result_id=bounded_string(
            data["result_id"], f"{path}.result_id", pattern=RESULT_ID_PATTERN
        ),
        predicate=predicate,
        required=boolean_value(data["required"], f"{path}.required"),
        expected_order_id=_expected(
            data, path, "expected_order_id", SYNTHETIC_IDENTIFIER_PATTERN
        ),
        expected_specimen_id=_expected(
            data, path, "expected_specimen_id", SYNTHETIC_IDENTIFIER_PATTERN
        ),
        expected_analyte_code=_expected(
            data, path, "expected_analyte_code", RESULT_TOKEN_PATTERN
        ),
        expected_value=_expected(data, path, "expected_value", RESULT_TOKEN_PATTERN),
        expected_unit=_expected(data, path, "expected_unit", RESULT_TOKEN_PATTERN),
    )


def parse_result_rule_set(value: object) -> ResultRuleSet:
    """Validate and parse a versioned laboratory rule set."""

    reject_prohibited_fields(value)
    data = object_value(value, "$")
    exact_keys(data, frozenset({"schema_version", "rules"}), "$")
    if bounded_string(data["schema_version"], "$.schema_version") != (
        RESULT_RULE_SET_SCHEMA_VERSION
    ):
        raise contract_error(
            "unsupported_schema",
            "$.schema_version",
            "result-rule-set schema is unsupported",
        )
    raw = array_value(data["rules"], "$.rules")
    if not raw or len(raw) > MAX_RESULT_RULES:
        raise contract_error(
            "invalid_rule_count",
            "$.rules",
            f"between 1 and {MAX_RESULT_RULES} rules are required",
        )
    rules = tuple(
        parse_result_rule(item, f"$.rules[{index}]") for index, item in enumerate(raw)
    )
    unique_strings(
        tuple(rule.rule_id for rule in rules), "$.rules", code="duplicate_rule_id"
    )
    return ResultRuleSet(schema_version=RESULT_RULE_SET_SCHEMA_VERSION, rules=rules)


def parse_result_bundle(
    case_value: object, result_value: object, rule_value: object
) -> ResultBundle:
    """Validate all inputs and their cross-document synthetic-case contract.

    A result or a rule that names another case refuses the whole bundle, the
    way an observation naming another case does (A-001). The case link is
    therefore established before any predicate runs, which is why
    ``result_linked`` decides the order and the specimen and not the case.
    """

    case = parse_case(case_value)
    results = parse_result_set(result_value)
    rule_set = parse_result_rule_set(rule_value)
    if any(item.case_id != case.case_id for item in results):
        raise contract_error(
            "case_mismatch",
            "$.results",
            "every result must reference the case manifest",
        )
    if any(rule.case_id != case.case_id for rule in rule_set.rules):
        raise contract_error(
            "case_mismatch", "$.rules", "every rule must reference the case manifest"
        )
    return ResultBundle(case=case, results=results, rule_set=rule_set)


@dataclass(frozen=True, slots=True)
class ResultTrace:
    """Where a laboratory outcome's evidence came from (A-035).

    The distinct source hash and structural pointer of every result the
    predicate read, and the distinct mapping versions they came through,
    both sorted, so the trace is independent of result order.
    """

    sources: tuple[EvidencePointer, ...] = ()
    mapping_versions: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, JsonValue]:
        """Return the canonical, value-minimized representation."""

        return {
            "mapping_versions": list(self.mapping_versions),
            "sources": [item.to_dict() for item in self.sources],
        }


@dataclass(frozen=True, slots=True)
class ResultOutcome:
    """A claim-minimal laboratory outcome: hashes, codes, and pointers only.

    No analyte code, value, unit, bound, or flag appears here. What the
    outcome says is which rule decided what about which result identifier,
    with the hash of the whole result beside it.
    """

    rule_id: str
    rule_version: str
    case_id: str
    checkpoint: str
    result_id: str
    predicate: ResultPredicate
    status: OutcomeStatus
    reason: ResultOutcomeReason
    observed_sha256s: tuple[str, ...]
    evidence_sha256s: tuple[str, ...]
    trace: ResultTrace = ResultTrace()

    def to_dict(self) -> dict[str, JsonValue]:
        """Return the deterministic, value-minimized representation."""

        return {
            "case_id": self.case_id,
            "checkpoint": self.checkpoint,
            "evidence_sha256s": list(self.evidence_sha256s),
            "observed_sha256s": list(self.observed_sha256s),
            "predicate": self.predicate.value,
            "reason": self.reason.value,
            "result_id": self.result_id,
            "rule_id": self.rule_id,
            "rule_version": self.rule_version,
            "status": self.status.value,
            "trace": self.trace.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class _Verdict:
    """What a predicate decided, before it is bound to a rule."""

    status: OutcomeStatus
    reason: ResultOutcomeReason
    read: tuple[LaboratoryResult, ...]


def _matched(bundle: ResultBundle, rule: ResultRule) -> LaboratoryResult | None:
    """The one result a rule reads, or None when the boundary produced none.

    A result set carries each result identifier once — a duplicate refuses
    the document — so a rule matches at most one result and ambiguity is
    decided at the contract rather than at evaluation.
    """

    for item in bundle.results:
        if (
            item.case_id == rule.case_id
            and item.checkpoint is rule.checkpoint
            and item.result_id == rule.result_id
        ):
            return item
    return None


def _decided(
    passed: bool,
    affirmative: ResultOutcomeReason,
    failure: ResultOutcomeReason,
    read: LaboratoryResult,
) -> _Verdict:
    return _Verdict(
        status=OutcomeStatus.PASSED if passed else OutcomeStatus.FAIL,
        reason=affirmative if passed else failure,
        read=(read,),
    )


def _result_linked(result: LaboratoryResult, rule: ResultRule) -> _Verdict:
    """A-025: the order and the specimen are the case's own synthetic tokens.

    The case half of A-025 is established by ``parse_result_bundle``, which
    refuses a result naming another case, and the analyte half is A-026's.
    What is left, and what this decides, is whether the order and specimen
    the boundary returned are the ones the case declares.
    """

    return _decided(
        result.order_id == rule.expected_order_id
        and result.specimen_id == rule.expected_specimen_id,
        ResultOutcomeReason.RESULT_LINKED,
        ResultOutcomeReason.RESULT_NOT_LINKED,
        result,
    )


def _analyte_value_unit_preserved(
    result: LaboratoryResult, rule: ResultRule
) -> _Verdict:
    """A-026, exact: the three tokens are the declared ones, character for character.

    The value is compared as the string it was carried as, not as a number:
    ``4.10`` and ``4.1`` are the same quantity and different round trips, and
    A-026 is a claim about the round trip.

    Three of the four things A-026 names. It also names the result's status,
    and this family carries no status field at all, so nothing here decides
    whether a status survived a boundary; a result whose status changed and
    whose analyte code, value, and unit did not passes this predicate.
    """

    return _decided(
        result.analyte_code == rule.expected_analyte_code
        and result.value == rule.expected_value
        and result.unit == rule.expected_unit,
        ResultOutcomeReason.ANALYTE_VALUE_UNIT_PRESERVED,
        ResultOutcomeReason.ANALYTE_VALUE_UNIT_CHANGED,
        result,
    )


def _reference_interval_present(
    result: LaboratoryResult, _rule: ResultRule
) -> _Verdict:
    """A-027, A-029: an interval with bounds, inclusivity, and a usable unit.

    A blank interval is a failure and not an absence of evidence: the
    boundary answered, and what it returned was nothing where the fixture
    requires bounds. An interval this ungoverned profile could not type is
    indeterminate instead, because an unreadable answer is not a missing
    one. An interval in a different unit from the value cannot be compared
    with the value at all, so it is a failure rather than a present
    interval.
    """

    if result.interval_status is CellStatus.ABSENT:
        return _Verdict(
            OutcomeStatus.FAIL, ResultOutcomeReason.REFERENCE_INTERVAL_ABSENT, (result,)
        )
    if result.reference_interval is None:
        return _Verdict(
            OutcomeStatus.INDETERMINATE,
            ResultOutcomeReason.REFERENCE_INTERVAL_NOT_TYPED,
            (result,),
        )
    return _decided(
        result.reference_interval.unit == result.unit,
        ResultOutcomeReason.REFERENCE_INTERVAL_PRESENT,
        ResultOutcomeReason.REFERENCE_INTERVAL_UNIT_MISMATCH,
        result,
    )


def _readable_interval(
    result: LaboratoryResult,
) -> ReferenceInterval | ResultOutcomeReason:
    """The interval the flag predicate may read, or why it may read none."""

    if result.interval_status is CellStatus.ABSENT:
        return ResultOutcomeReason.REFERENCE_INTERVAL_ABSENT
    interval = result.reference_interval
    if interval is None:
        return ResultOutcomeReason.REFERENCE_INTERVAL_NOT_TYPED
    if interval.unit != result.unit:
        return ResultOutcomeReason.REFERENCE_INTERVAL_UNIT_MISMATCH
    if DECIMAL_PATTERN.fullmatch(result.value) is None:
        return ResultOutcomeReason.VALUE_NOT_COMPARABLE
    if result.flag_status is CellStatus.NOT_TYPED:
        return ResultOutcomeReason.FLAG_NOT_TYPED
    return interval


def _flag_consistent_with_interval(
    result: LaboratoryResult, _rule: ResultRule
) -> _Verdict:
    """A-028, A-030: the flag the fixture's own bounds imply, or a finding.

    Every reason this predicate cannot compute — no interval, an interval it
    cannot type, an interval in another unit, a value it cannot compare, a
    flag outside the vocabulary — is ``indeterminate``. None of them is
    ``pass``, so an out-of-range result never reads as normal because
    something was missing (A-030). A result outside the bounds with no flag
    at all is a failure; a result inside them with no flag is indeterminate,
    because a flag nobody sent is not evidence that anything is normal.
    """

    interval = _readable_interval(result)
    if isinstance(interval, ResultOutcomeReason):
        return _Verdict(OutcomeStatus.INDETERMINATE, interval, (result,))
    position = interval.position_of(Decimal(result.value))
    if result.abnormal_flag is None:
        if position is IntervalPosition.IN_RANGE:
            return _Verdict(
                OutcomeStatus.INDETERMINATE,
                ResultOutcomeReason.FLAG_ABSENT_IN_RANGE,
                (result,),
            )
        return _Verdict(
            OutcomeStatus.FAIL,
            ResultOutcomeReason.FLAG_MISSING_OUT_OF_RANGE,
            (result,),
        )
    return _decided(
        result.abnormal_flag is _FLAG_FOR_POSITION[position],
        ResultOutcomeReason.FLAG_CONSISTENT_WITH_INTERVAL,
        ResultOutcomeReason.FLAG_INCONSISTENT_WITH_INTERVAL,
        result,
    )


_PREDICATES: Mapping[
    ResultPredicate, Callable[[LaboratoryResult, ResultRule], _Verdict]
] = {
    ResultPredicate.RESULT_LINKED: _result_linked,
    ResultPredicate.ANALYTE_VALUE_UNIT_PRESERVED: _analyte_value_unit_preserved,
    ResultPredicate.REFERENCE_INTERVAL_PRESENT: _reference_interval_present,
    ResultPredicate.FLAG_CONSISTENT_WITH_INTERVAL: _flag_consistent_with_interval,
}

REASON_STATUSES: Mapping[ResultOutcomeReason, frozenset[OutcomeStatus]] = {
    ResultOutcomeReason.PREDECLARED_NOT_APPLICABLE: frozenset(
        {OutcomeStatus.NOT_APPLICABLE}
    ),
    ResultOutcomeReason.MISSING_EVIDENCE: frozenset({OutcomeStatus.INDETERMINATE}),
    ResultOutcomeReason.RESULT_LINKED: frozenset({OutcomeStatus.PASSED}),
    ResultOutcomeReason.RESULT_NOT_LINKED: frozenset({OutcomeStatus.FAIL}),
    ResultOutcomeReason.ANALYTE_VALUE_UNIT_PRESERVED: frozenset({OutcomeStatus.PASSED}),
    ResultOutcomeReason.ANALYTE_VALUE_UNIT_CHANGED: frozenset({OutcomeStatus.FAIL}),
    ResultOutcomeReason.REFERENCE_INTERVAL_PRESENT: frozenset({OutcomeStatus.PASSED}),
    ResultOutcomeReason.REFERENCE_INTERVAL_ABSENT: frozenset(
        {OutcomeStatus.FAIL, OutcomeStatus.INDETERMINATE}
    ),
    ResultOutcomeReason.REFERENCE_INTERVAL_NOT_TYPED: frozenset(
        {OutcomeStatus.INDETERMINATE}
    ),
    ResultOutcomeReason.REFERENCE_INTERVAL_UNIT_MISMATCH: frozenset(
        {OutcomeStatus.FAIL, OutcomeStatus.INDETERMINATE}
    ),
    ResultOutcomeReason.FLAG_CONSISTENT_WITH_INTERVAL: frozenset(
        {OutcomeStatus.PASSED}
    ),
    ResultOutcomeReason.FLAG_INCONSISTENT_WITH_INTERVAL: frozenset(
        {OutcomeStatus.FAIL}
    ),
    ResultOutcomeReason.FLAG_MISSING_OUT_OF_RANGE: frozenset({OutcomeStatus.FAIL}),
    ResultOutcomeReason.FLAG_ABSENT_IN_RANGE: frozenset({OutcomeStatus.INDETERMINATE}),
    ResultOutcomeReason.FLAG_NOT_TYPED: frozenset({OutcomeStatus.INDETERMINATE}),
    ResultOutcomeReason.VALUE_NOT_COMPARABLE: frozenset({OutcomeStatus.INDETERMINATE}),
}
"""Which statuses each reason may be published under.

Two reasons carry two statuses, and both say the same thing twice: an
absent or unusable interval is a finding for the predicate whose claim is
that the interval is there, and a reason to decide nothing for the
predicate that would have read it. No reason may sit under a status this
table does not name, which is what keeps ``pass`` out of every absence.
"""


def _trace_of(read: tuple[LaboratoryResult, ...]) -> ResultTrace:
    sources = {item.evidence for item in read}
    versions = {item.mapping_version for item in read}
    return ResultTrace(
        sources=tuple(
            sorted(sources, key=lambda item: (item.source_sha256, item.source_pointer))
        ),
        mapping_versions=tuple(sorted(versions)),
    )


def _outcome(bundle: ResultBundle, rule: ResultRule) -> ResultOutcome:
    matched = _matched(bundle, rule)
    if not rule.required:
        verdict = _Verdict(
            OutcomeStatus.NOT_APPLICABLE,
            ResultOutcomeReason.PREDECLARED_NOT_APPLICABLE,
            () if matched is None else (matched,),
        )
    elif matched is None:
        verdict = _Verdict(
            OutcomeStatus.INDETERMINATE, ResultOutcomeReason.MISSING_EVIDENCE, ()
        )
    else:
        verdict = _PREDICATES[rule.predicate](matched, rule)
    return ResultOutcome(
        rule_id=rule.rule_id,
        rule_version=rule.version,
        case_id=rule.case_id,
        checkpoint=rule.checkpoint.value,
        result_id=rule.result_id,
        predicate=rule.predicate,
        status=verdict.status,
        reason=verdict.reason,
        observed_sha256s=tuple(
            sorted(sha256_json(item.to_dict()) for item in verdict.read)
        ),
        evidence_sha256s=tuple(
            sorted({item.evidence.source_sha256 for item in verdict.read})
        ),
        trace=_trace_of(verdict.read),
    )


def evaluate_results(bundle: ResultBundle) -> tuple[ResultOutcome, ...]:
    """Evaluate laboratory rules deterministically, without clinical judgment.

    Rule order is rule-ID order, so the outcomes of one bundle are the same
    sequence on every run, platform, locale, and hash seed.
    """

    return tuple(
        _outcome(bundle, rule)
        for rule in sorted(bundle.rule_set.rules, key=lambda item: item.rule_id)
    )


def result_set_document(results: tuple[LaboratoryResult, ...]) -> dict[str, JsonValue]:
    """Return the ``contextsafe.result-set/0.1.0`` document for ``results``."""

    return {
        "results": [item.to_dict() for item in results],
        "schema_version": RESULT_SET_SCHEMA_VERSION,
    }


def outcome_report(outcomes: tuple[ResultOutcome, ...]) -> dict[str, JsonValue]:
    """Return the in-process, value-minimized report of one evaluation.

    In-process and test-only. This shape has no schema in ``schemas/`` and
    no command emits it: laboratory outcomes reach no receipt and no file
    yet. If a second output document is ever decided, it gets a contract, a
    row in ``schemas/README.md``, and an emitter in that item, not here.
    """

    return {
        "outcomes": [item.to_dict() for item in outcomes],
        "summary": {
            status.value: sum(1 for item in outcomes if item.status is status)
            for status in OutcomeStatus
        },
    }
