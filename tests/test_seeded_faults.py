"""The seeded-fault corpus: what of F-001 to F-036 runs today, and what cannot.

``docs/09-TEST-AND-EVALUATION.md`` section 4 names 36 seeded faults and the
assertion expected to detect each. B-048 defines the evaluation over that
library plus five hidden faults, run by independent QA. This module is the
part of B-048 that needs no external person: for every published fault it
holds one of four things, and a committed matrix (``MATRIX``) says which.

* **exercised outside the receipt** — a complete synthetic fixture under
  ``tests/fixtures/laboratory/seeded-faults/`` and a verdict from the
  laboratory result predicates (B-030), which reach no receipt: there is no
  divergence section to locate the fault in, so the row is counted apart
  from the receipt-level ones rather than claiming a localization the
  mechanism does not make. Each also has a clean counterpart proving the
  fault, not the rule, is what turned the outcome.
* **exercised** — a complete synthetic fixture under
  ``tests/fixtures/seeded-faults/`` (case, rule set, and observation set
  with exactly one fault applied), and tests proving the fault is reported
  as the assertion demands (``fail`` with the predicate's own reason; or
  ``indeterminate`` and ``unobserved`` where absence is the fault), and
  located in the divergence section at the observed checkpoint the fault
  touched and nowhere else.
* **refused** — the faulted input cannot reach the mechanism it would
  corrupt: a fail-closed gate refuses it with a named code at a structural
  path, and a fixture under ``seeded-faults/refused/`` or a named test pins
  that refusal. The gate is usually the bundle parser, but not always: a
  receipt document carrying a field the contract does not publish is refused
  by the renderer, a review event that disposes of a finding without an owner
  is refused before the log is appended, and a stored evidence object whose
  bytes were changed is refused on the store's next read. A refusal is
  detection without a receipt, so it is counted separately from exercised and
  never as localization — and where the refusal lands somewhere other than the
  fault's own claim (the store's next read rather than the receipt already
  issued), the row still names what would close that gap.
* **not yet exercisable** — nothing here can express or decide the fault,
  and the row names the missing item from a closed vocabulary.

Every expectation is restated here rather than read from a fixture, so a
fixture cannot declare its own verdict and the test then agree with it; the
mutation and detector columns are compared against section 4 verbatim, and
the dated status table in that section is compared row for row against
``MATRIX``, so neither document can drift from the other.

What this is not: it is not the 41-fault evaluation B-048 defines. There is
no hidden-fault set, no independent fault author or QA has reviewed the
corpus, and the counts are deterministic corpus coverage over faults the
implementer wrote — not a sensitivity estimate over unseen faults, and not a
population claim of any kind. The case variants (CTP-I07, CTP-I08, CTP-I10)
are shaped like CTP-007, CTP-008, and CTP-010 in
``docs/05-DATA-AND-EVIDENCE.md`` section 3 because the packaged CTP-I01 has
no declined, unknown, or second recorded-sex-or-gender value to corrupt.
They are fault-library inputs, not additions to any canonical pack, and
nothing here is governed content.
"""

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from contextsafe.canonical import sha256_json
from contextsafe.cli import main
from contextsafe.divergence import ConceptDivergence, compute_divergence
from contextsafe.errors import ContextSafeError
from contextsafe.evaluator import Outcome, evaluate
from contextsafe.html_receipt import render_receipt_page
from contextsafe.laboratory import (
    AFFIRMATIVE_RESULT_REASONS,
    REASON_STATUSES,
    ResultOutcome,
    ResultOutcomeReason,
    evaluate_results,
    parse_result_bundle,
)
from contextsafe.models import (
    FAILURE_REASONS,
    Checkpoint,
    ConceptKind,
    DivergenceStatus,
    EvidenceState,
    OutcomeReason,
    OutcomeStatus,
)
from contextsafe.receipt import build_receipt, build_receipt_document
from contextsafe.review import (
    FindingState,
    ReviewEvent,
    apply_event,
    bind_to_receipt,
    parse_receipt_findings,
    parse_review_event,
)
from contextsafe.validation import parse_bundle

ROOT = Path(__file__).resolve().parents[1]
FAULTS = ROOT / "tests" / "fixtures" / "seeded-faults"
REFUSED = FAULTS / "refused"
TEST_PLAN = ROOT / "docs" / "09-TEST-AND-EVALUATION.md"
README = ROOT / "README.md"
RULE_SET_SCHEMA = json.loads(
    (ROOT / "schemas" / "contextsafe-rule-set-v0.2.schema.json").read_text(
        encoding="utf-8"
    )
)

EXPECTED_DETECTION: dict[str, tuple[str, str, OutcomeReason]] = {
    # fault: (assertion from docs/09 section 4, detector rule id, reason)
    "F-001": ("A-005", "A-I02", OutcomeReason.VALUE_NOT_PRESENT),
    "F-004": ("A-008", "A-I02", OutcomeReason.VALUE_NOT_PRESENT),
    "F-005": ("A-009", "A-I01", OutcomeReason.STATUS_NOT_PRESERVED),
    "F-006": ("A-011", "A-I05", OutcomeReason.OVERWRITTEN_BY_OTHER_CONCEPT),
    "F-007": ("A-014", "A-I06", OutcomeReason.VALUE_COERCED),
    "F-008": ("A-014", "A-I01", OutcomeReason.VALUE_COERCED),
    "F-009": ("A-012", "A-I02", OutcomeReason.VALUE_CHANGED_ACROSS_CHECKPOINTS),
    "F-010": ("A-013", "A-I01", OutcomeReason.RECORD_COUNT_CHANGED),
    "F-025": ("A-034", "A-I02", OutcomeReason.VALUE_CHANGED_ACROSS_CHECKPOINTS),
    "F-031": ("A-009", "A-I01", OutcomeReason.STATUS_NOT_PRESERVED),
}
"""Faults reported as ``fail`` by one predicate with that predicate's reason.

Restated here rather than read from the fixture, so the fixture cannot
declare its own expected verdict and the test then agree with it.
"""

EVIDENCE_FAULTS: dict[str, str] = {"F-023": "A-032", "F-035": "A-035"}
"""Faults of the evaluator rather than of the system under test.

Each is reported as the assertion demands rather than as ``fail`` — nothing
passes on an omitted checkpoint (F-023); a changed mapping version can never
share a run identity with the original (F-035) — and each has its own test.
F-025 is also an evaluator fault (A-034) but is additionally reported as
``fail`` by its preserved-across rule, so it is in ``EXPECTED_DETECTION``.
"""

F023_INDETERMINATE_RULES: tuple[str, ...] = ("A-I02", "A-I03")
"""The rules that read the omitted laboratory return in F-023."""

F023_UNOBSERVED = Checkpoint.LIS_RETURN
"""The checkpoint F-023 omits."""

F035_MAPPING_VERSION = "0.2.0"
"""The mapping version F-035 substitutes for the case's declared 0.1.0."""

F035_CLEAN_MAPPING_VERSION = "0.1.0"

SPCU_DECLARED_FORM_ONLY = (
    "(declared form only; undeclared derivation needs A-020/A-021, B-029)"
)
"""What the F-015 and F-016 refusals do not cover, restated in the tables."""

NAME_DECLARED_FORM_ONLY = (
    "(the declared name use alone, and not the substitution: the same "
    "declaration over the faithful name is refused identically, and the same "
    "token in the usual slot declares nothing and is only a value that "
    "changed; telling either from a legal name needs A-006/A-007, B-019)"
)
"""What the F-002 refusal does not cover, restated in the tables.

``_name_to_use`` admits one name use, so a boundary that says it wrote the
official name is refused whole. Two things that refusal is not. It is not
isolated to the fault: revert the substituted token and leave the declaration
and the same code is raised at the same path, so what the gate refuses is the
declaration a legal-name substitution would have to be made under, never the
substitution. And it does not reach the undeclared form: a boundary that
writes the legal token into the usual slot and says nothing declares nothing
to refuse, and the receipt reports what it can see, a value that changed
between two boundaries.
"""

REFUSED_FAULTS: dict[str, tuple[str, str, str]] = {
    # fault: (assertion, error code, structural error path)
    "F-002": ("A-006", "invalid_name_use", "$.observations[1].value.use"),
    "F-015": ("A-020", "prohibited_spcu_mapping", "$.observations[0].mapping"),
    "F-016": ("A-021", "prohibited_spcu_mapping", "$.observations[0].mapping"),
    "F-024": ("A-033", "invalid_rsg_value", "$.observations[0].value.value"),
    "F-029": ("A-002", "invalid_synthetic_identifier", "$.synthetic_identifier"),
    "F-032": ("A-001", "case_mismatch", "$.observations"),
}
"""Faults a fail-closed gate refuses before any rule runs.

The whole input is refused — never the faulted record stripped and the rest
accepted — so no outcome, receipt, or divergence entry exists for these. The
error names a category and a structural location, never content.
"""


@dataclass(frozen=True, slots=True)
class Location:
    """Where the divergence section must locate one exercised fault."""

    concept: ConceptKind
    from_expected: tuple[DivergenceStatus, Checkpoint | None]
    from_previous: tuple[DivergenceStatus, Checkpoint | None, Checkpoint | None]


_EHR_ONLY = (DivergenceStatus.UNOBSERVED, None, None)
"""``from_previous`` when the concept is observed at one boundary only."""

LOCATED: dict[str, Location] = {
    "F-001": Location(
        ConceptKind.NAME_TO_USE,
        (DivergenceStatus.DIVERGED, Checkpoint.EHR),
        (DivergenceStatus.DIVERGED, Checkpoint.REGISTRATION, Checkpoint.EHR),
    ),
    "F-004": Location(
        ConceptKind.PRONOUNS, (DivergenceStatus.DIVERGED, Checkpoint.EHR), _EHR_ONLY
    ),
    "F-005": Location(
        ConceptKind.GENDER_IDENTITY,
        (DivergenceStatus.DIVERGED, Checkpoint.EHR),
        _EHR_ONLY,
    ),
    "F-006": Location(
        ConceptKind.GENDER_IDENTITY,
        (DivergenceStatus.DIVERGED, Checkpoint.EHR),
        _EHR_ONLY,
    ),
    "F-007": Location(
        ConceptKind.RECORDED_SEX_OR_GENDER,
        (DivergenceStatus.DIVERGED, Checkpoint.REGISTRATION),
        _EHR_ONLY,
    ),
    "F-008": Location(
        ConceptKind.RECORDED_SEX_OR_GENDER,
        (DivergenceStatus.DIVERGED, Checkpoint.REGISTRATION),
        _EHR_ONLY,
    ),
    "F-009": Location(
        ConceptKind.RECORDED_SEX_OR_GENDER,
        (DivergenceStatus.DIVERGED, Checkpoint.EHR),
        (DivergenceStatus.DIVERGED, Checkpoint.REGISTRATION, Checkpoint.EHR),
    ),
    "F-010": Location(
        ConceptKind.RECORDED_SEX_OR_GENDER,
        (DivergenceStatus.DIVERGED, Checkpoint.REGISTRATION),
        _EHR_ONLY,
    ),
    "F-023": Location(
        ConceptKind.NAME_TO_USE,
        (DivergenceStatus.AGREED_WHERE_OBSERVED, None),
        (DivergenceStatus.AGREED_WHERE_OBSERVED, None, None),
    ),
    "F-025": Location(
        ConceptKind.NAME_TO_USE,
        (DivergenceStatus.DIVERGED, Checkpoint.INTERFACE),
        (DivergenceStatus.DIVERGED, Checkpoint.REGISTRATION, Checkpoint.INTERFACE),
    ),
    "F-031": Location(
        ConceptKind.GENDER_IDENTITY,
        (DivergenceStatus.DIVERGED, Checkpoint.EHR),
        _EHR_ONLY,
    ),
    "F-035": Location(
        ConceptKind.GENDER_IDENTITY,
        (DivergenceStatus.AGREED_WHERE_OBSERVED, None),
        _EHR_ONLY,
    ),
}
"""The first observed divergence every exercised fault must be located at.

A fault whose observations sit at one boundary only has nothing to compare
from the previous boundary, so ``from_previous`` is ``unobserved`` for it; a
fault of absence (F-023) or of identity (F-035) agrees everywhere observed.
"""


class CorpusStatus(StrEnum):
    """The four things the matrix may say about a published fault."""

    EXERCISED = "exercised"
    """A fixture, a receipt-level verdict, and a located boundary."""

    EXERCISED_OUTSIDE_THE_RECEIPT = "exercised outside the receipt"
    """A fixture and a verdict from a family no receipt carries yet.

    The laboratory result predicates (B-030) decide these faults and report
    them with their own reasons, but a laboratory outcome reaches no receipt
    and no divergence section, so there is no localization to check and the
    row is counted apart from the receipt-level ones. Counting it as
    ``exercised`` would claim a localization the mechanism does not make.
    """

    REFUSED = "refused"
    NOT_EXERCISABLE = "not yet exercisable"


class MissingItem(StrEnum):
    """The closed vocabulary of what a fault waits on, each a backlog item."""

    LABORATORY_ORACLE = "the laboratory oracle's approved fixture values (B-011)"
    LABORATORY_RECEIPT = "a receipt section for laboratory outcomes (B-030)"
    SPCU_PREDICATES = "SPCU predicates awaiting clinical review (B-029)"
    NAME_CONTEXTS = "name contexts and periods in the observation contract (B-019)"
    DISPLAY_OBSERVATION = "patient-facing display observation (E-DISPLAY, B-019)"
    NORMALIZER = "normalizer and adapters (B-022 to B-026)"
    AUTHORED_ASSERTIONS = "authored assertions with validity (B-010)"
    FINALIZATION_GATE = (
        "a gate closing a receipt's findings against a review log (B-032)"
    )
    SIGNATURES = "signatures and role thresholds (B-035)"
    RECEIPT_VERIFIER = "receipt verifier (B-036)"


MISSING_ITEM_ISSUES: Mapping[MissingItem, int | None] = {
    MissingItem.LABORATORY_ORACLE: None,
    MissingItem.LABORATORY_RECEIPT: None,
    MissingItem.SPCU_PREDICATES: 90,
    MissingItem.NAME_CONTEXTS: None,
    MissingItem.DISPLAY_OBSERVATION: None,
    MissingItem.NORMALIZER: None,
    MissingItem.AUTHORED_ASSERTIONS: None,
    MissingItem.FINALIZATION_GATE: None,
    MissingItem.SIGNATURES: 81,
    MissingItem.RECEIPT_VERIFIER: 81,
}
"""The issue tracking each missing item, where one exists.

B-048 closes when every row is exercised or waits on a dependency that has an
issue of its own, so which dependencies have one is data here rather than
prose: #90 holds the SPCU predicates pending clinical review, and #81 holds
the signing layer's ADR that blocks both B-035 and B-036. A ``None`` is not an
omission but the finding itself, and :data:`BLOCKED_WITHOUT_AN_ISSUE` says
which of them still stand between this corpus and that close.

An issue number here is a hand-checked claim: nothing offline can confirm
that an issue exists, is open, or is about what this docstring says it is, so
a renumbered or closed issue would keep passing every gate. The laboratory
receipt section was mapped to #76 until 2026-09-05, when checking by hand
found #76 closed: it delivered the B-025/B-030 result observations and
predicates and not a receipt section for their outcomes, so what the seven
laboratory rows still wait on has no issue asking for it. Those rows are
exercised outside the receipt rather than waiting, so this does not stand
between the corpus and B-048's close; it is untracked all the same.
"""

DECISION_ONLY_ISSUES: frozenset[MissingItem] = frozenset(
    {MissingItem.SIGNATURES, MissingItem.RECEIPT_VERIFIER}
)
"""Missing items whose issue is a decision that blocks them, not their own item.

#81 is the ADR-0010 decision for the signing layer and says implementation is
a separate item that it blocks. So B-035 and B-036 have no implementation
issue: a row tracked this way is tracked by the thing that has to be decided
before anyone can file one, which is less than a row tracked by its own item
and is disclosed rather than counted as the same thing.
"""

BLOCKED_WITHOUT_AN_ISSUE: tuple[MissingItem, ...] = (MissingItem.NAME_CONTEXTS,)
"""What a not-yet-exercisable row waits on that no issue tracks.

Derived from the matrix and compared with this tuple, so a row that starts
waiting on an untracked dependency has to be declared here and disclosed in
docs/09 rather than joining the count in silence.
"""


LABORATORY = ROOT / "tests" / "fixtures" / "laboratory" / "seeded-faults"
LABORATORY_CLEAN = LABORATORY / "clean"

LABORATORY_DETECTION: dict[str, tuple[str, str, str, ResultOutcomeReason]] = {
    # fault: (mutation, assertion -- both verbatim from docs/09 section 4 --
    #         detector rule id, reason)
    "F-017": (
        "attach order to wrong synthetic patient",
        "A-025",
        "A-L01",
        ResultOutcomeReason.RESULT_NOT_LINKED,
    ),
    "F-018": (
        "alter analyte code/value/unit",
        "A-026",
        "A-L02",
        ResultOutcomeReason.ANALYTE_VALUE_UNIT_CHANGED,
    ),
    "F-019": (
        "omit required reference interval",
        "A-027/A-029",
        "A-L03",
        ResultOutcomeReason.REFERENCE_INTERVAL_ABSENT,
    ),
    "F-020": (
        "return wrong interval bounds",
        "A-027",
        "A-L04",
        ResultOutcomeReason.FLAG_INCONSISTENT_WITH_INTERVAL,
    ),
    "F-021": (
        "omit abnormal flag above bound",
        "A-028/A-030",
        "A-L04",
        ResultOutcomeReason.FLAG_MISSING_OUT_OF_RANGE,
    ),
    "F-022": (
        "report out-of-range result as normal",
        "A-028/A-030",
        "A-L04",
        ResultOutcomeReason.FLAG_INCONSISTENT_WITH_INTERVAL,
    ),
    "F-033": (
        "preserve a numeric range with the wrong unit",
        "A-027/A-028",
        "A-L03",
        ResultOutcomeReason.REFERENCE_INTERVAL_UNIT_MISMATCH,
    ),
}
"""The laboratory faults, each reported as ``fail`` by one laboratory predicate.

Restated here rather than read from the fixture, like every other expectation
in this module. The reason is the predicate's own, from the closed laboratory
vocabulary; there is no receipt and therefore no divergence entry to locate,
which is what ``exercised outside the receipt`` says.
"""

LABORATORY_RULE_ASSERTIONS: dict[str, frozenset[str]] = {
    "A-L01": frozenset({"A-025"}),
    "A-L02": frozenset({"A-026"}),
    "A-L03": frozenset({"A-027", "A-029"}),
    "A-L04": frozenset({"A-028", "A-030"}),
}
"""Which assertions each laboratory predicate is offered as mechanism for.

Restated from the B-025/B-030 implementation note in ``docs/13-BACKLOG.md``,
which names the assertion behind each predicate. It says what a predicate is
offered *for*, never that the assertion is proved: none of these is a
governed assertion, because the approved bounds, the age band, and the
effective oracle version they would need are the laboratory oracle's to
supply (B-011).
"""

REPORTED_BY_ANOTHER_ASSERTION: tuple[str, ...] = ("F-020",)
"""Laboratory faults no predicate for their declared assertion reports.

F-020 mutates the interval bounds, and its library row names A-027. Over the
faulted fixture ``reference_interval_present`` -- the only mechanism for
A-027 here -- passes, because both bounds, both inclusivities, and a unit
that fits the value are all present, which is the whole of what that
predicate checks. What reports the fault is A-L04, the A-028/A-030 flag
predicate, and only because the fixture left a flag the moved bounds
contradict. Comparing returned bounds against approved ones needs the
oracle (B-011). The set is derived from the table above and compared with
this tuple, and every member has to be disclosed in the docs/09 corpus
status section, so a row can never quietly count a detection the mechanism
does not make.
"""

_LAB_MISSING = (MissingItem.LABORATORY_ORACLE, MissingItem.LABORATORY_RECEIPT)
"""What a laboratory row still waits on once its predicate exists.

The values in these fixtures are invented for software tests, and the real
ones come from a partner's laboratory medical director (B-011); and no
receipt carries a laboratory outcome, so nothing localizes one.
"""


def _laboratory_evidence(fault: str) -> str:
    """Render the evidence column for one laboratory row."""

    _mutation, _assertion, rule_id, reason = LABORATORY_DETECTION[fault]
    return f"`laboratory/{fault}.json`: {rule_id} `{reason.value}` at `lis_return`"


@dataclass(frozen=True, slots=True)
class FaultRow:
    """One row of the corpus matrix."""

    fault: str
    mutation: str
    """Verbatim from docs/09 section 4."""
    detector: str
    """Verbatim from docs/09 section 4."""
    status: CorpusStatus
    evidence: str
    """What proves the row's status: a fixture and verdict, or a test."""
    missing: tuple[MissingItem, ...]
    """What a receipt-level outcome for this fault still waits on."""


def _exercised(
    fault: str, mutation: str, detector: str, evidence: str, *missing: MissingItem
) -> FaultRow:
    return FaultRow(
        fault, mutation, detector, CorpusStatus.EXERCISED, evidence, missing
    )


def _outside_the_receipt(
    fault: str, mutation: str, detector: str, evidence: str, *missing: MissingItem
) -> FaultRow:
    return FaultRow(
        fault,
        mutation,
        detector,
        CorpusStatus.EXERCISED_OUTSIDE_THE_RECEIPT,
        evidence,
        missing,
    )


def _refused(
    fault: str, mutation: str, detector: str, evidence: str, *missing: MissingItem
) -> FaultRow:
    return FaultRow(fault, mutation, detector, CorpusStatus.REFUSED, evidence, missing)


def _waiting(
    fault: str, mutation: str, detector: str, *missing: MissingItem
) -> FaultRow:
    return FaultRow(
        fault, mutation, detector, CorpusStatus.NOT_EXERCISABLE, "", missing
    )


_SPCU = MissingItem.SPCU_PREDICATES

MATRIX: tuple[FaultRow, ...] = (
    _exercised(
        "F-001",
        "drop current NtU",
        "A-005/A-006",
        "`F-001.json`: A-I02 `value_not_present` at `ehr`",
        MissingItem.DISPLAY_OBSERVATION,
    ),
    _refused(
        "F-002",
        "replace NtU with legal test name",
        "A-006/A-007",
        "`refused/F-002.json`: `invalid_name_use` at `$.observations[1].value.use` "
        + NAME_DECLARED_FORM_ONLY,
        MissingItem.DISPLAY_OBSERVATION,
        MissingItem.NAME_CONTEXTS,
    ),
    _waiting("F-003", "show expired prior NtU", "A-015", MissingItem.NAME_CONTEXTS),
    _exercised(
        "F-004",
        "drop pronouns",
        "A-008",
        "`F-004.json`: A-I02 `value_not_present` at `ehr`",
    ),
    _exercised(
        "F-005",
        "convert declined GI/pronouns to unknown",
        "A-009",
        "`F-005.json`: A-I01 `status_not_preserved` at `ehr`",
    ),
    _exercised(
        "F-006",
        "overwrite GI with RSG",
        "A-010/A-011",
        "`F-006.json`: A-I05 `overwritten_by_other_concept` at `ehr`",
    ),
    _exercised(
        "F-007",
        "coerce X to F",
        "A-014",
        "`F-007.json`: A-I06 `value_coerced` at `registration`",
    ),
    _exercised(
        "F-008",
        "coerce absent/unknown to M",
        "A-014",
        "`F-008.json`: A-I01 `value_coerced` at `registration`",
    ),
    _exercised(
        "F-009",
        "drop RSG source/context",
        "A-012",
        "`F-009.json`: A-I02 `value_changed_across_checkpoints` at `ehr`",
    ),
    _exercised(
        "F-010",
        "collapse two RSG records",
        "A-013",
        "`F-010.json`: A-I01 `record_count_changed` at `registration`",
    ),
    _waiting("F-011", "drop SPCU", "A-016", _SPCU),
    _waiting("F-012", "apply one SPCU to all orders", "A-017/A-023", _SPCU),
    _waiting("F-013", "treat expired SPCU as current", "A-018/A-022", _SPCU),
    _waiting("F-014", "detach supporting observation", "A-019", _SPCU),
    _refused(
        "F-015",
        "derive SPCU from GI",
        "A-020",
        "`refused/F-015.json`: `prohibited_spcu_mapping` at `$.observations[0].mapping` "
        + SPCU_DECLARED_FORM_ONLY,
        _SPCU,
    ),
    _refused(
        "F-016",
        "derive or map SPCU from RSG under any declared or undeclared local mapping",
        "A-021",
        "`refused/F-016.json`: `prohibited_spcu_mapping` at `$.observations[0].mapping` "
        + SPCU_DECLARED_FORM_ONLY,
        _SPCU,
    ),
    *(
        _outside_the_receipt(
            fault,
            mutation,
            detector,
            _laboratory_evidence(fault),
            *_LAB_MISSING,
        )
        for fault, (mutation, detector, _rule, _reason) in LABORATORY_DETECTION.items()
        if fault != "F-033"
    ),
    _exercised(
        "F-023",
        "omit checkpoint but report pass",
        "A-032",
        f"`F-023.json`: {' and '.join(F023_INDETERMINATE_RULES)} "
        f"`{OutcomeReason.MISSING_EVIDENCE.value}`; `{F023_UNOBSERVED.value}` unobserved",
    ),
    _refused(
        "F-024",
        "normalize unsupported value to closest code",
        "A-033",
        "`refused/F-024.json`: `invalid_rsg_value` at `$.observations[0].value.value`",
        MissingItem.NORMALIZER,
    ),
    _exercised(
        "F-025",
        "infer first divergence across an unobserved boundary",
        "A-034",
        "`F-025.json`: A-I02 `value_changed_across_checkpoints` at `interface`; `ehr` never named",
    ),
    _refused(
        "F-026",
        "mutate raw evidence after evaluation",
        "A-035/receipt verifier",
        "`tests/test_evidence_store.py"
        "::test_same_size_hash_corruption_and_missing_object_are_distinctly_detected`"
        " (the store's next read, not the receipt already issued)",
        MissingItem.RECEIPT_VERIFIER,
    ),
    _refused(
        "F-027",
        "include unnecessary legal-name/GI field in HTML",
        "A-031/A-036",
        "`tests/test_seeded_faults.py"
        "::test_f027_an_unnecessary_identity_field_never_reaches_a_page`; "
        "`tests/test_html_receipt.py"
        "::test_a_field_the_contract_does_not_publish_is_refused`; "
        "`tests/test_a11y_gate.py"
        "::test_a_receipt_value_the_page_does_not_need_is_caught`",
        MissingItem.DISPLAY_OBSERVATION,
    ),
    _refused(
        "F-028",
        "use expired assertion/oracle",
        "pack validity gate",
        "`tests/test_pack.py::test_pack_rejects_inactive_expired_or_incompatible_content`",
        MissingItem.AUTHORED_ASSERTIONS,
    ),
    _refused(
        "F-029",
        "ingest PHI canary/non-synthetic MRN",
        "P0-11 privacy preflight",
        "`refused/F-029.json`: `invalid_synthetic_identifier` at `$.synthetic_identifier`; `tests/test_preflight.py::test_field_namespace_free_text_and_canary_fail_closed`",
    ),
    _refused(
        "F-030",
        "strip limitations from report template",
        "receipt schema/presentation gate",
        "`tests/test_receipt_schema.py::test_stripped_or_padded_limitations_fail_the_contract`",
    ),
    _exercised(
        "F-031",
        "convert explicitly declined identity data to absent",
        "A-009/A-032",
        "`F-031.json`: A-I01 `status_not_preserved` at `ehr`",
    ),
    _refused(
        "F-032",
        "attach name/pronoun observation to the wrong synthetic case",
        "A-001/A-005/A-008",
        "`refused/F-032.json`: `case_mismatch` at `$.observations`",
        MissingItem.AUTHORED_ASSERTIONS,
    ),
    _outside_the_receipt(
        "F-033",
        *LABORATORY_DETECTION["F-033"][:2],
        _laboratory_evidence("F-033"),
        *_LAB_MISSING,
    ),
    _waiting(
        "F-034",
        "remove one required receipt signer or substitute the wrong-purpose role",
        "review/signature threshold verifier",
        MissingItem.SIGNATURES,
    ),
    _exercised(
        "F-035",
        "change mapping/terminology version without changing the run identity",
        "A-035/P0-12 verifier",
        f"`F-035.json`: trace names mapping `{F035_MAPPING_VERSION}`; "
        "`payload_sha256` moves",
        MissingItem.RECEIPT_VERIFIER,
    ),
    _refused(
        "F-036",
        "omit the owner or disposition for a mandatory failed outcome",
        "P0-10 finalization gate",
        "`tests/test_seeded_faults.py"
        "::test_f036_a_disposition_that_omits_the_owner_is_refused` (the owner "
        "half of the mutation; the omitted disposition is reported by nothing "
        "here)",
        MissingItem.FINALIZATION_GATE,
    ),
)
"""The corpus matrix: every published fault, its status, and what it waits on.

An exercised or refused row may still name a missing item: F-001 is reported
at the EHR as a value change, not at a patient-facing display (A-006); F-035
proves the identity moves, not that a verifier would notice a claimed one;
F-026's refusal is the evidence store's next read rather than a verifier over
the receipt already issued; and F-020 is reported by the flag predicate rather
than by the assertion its library row names, which
``REPORTED_BY_ANOTHER_ASSERTION`` says and docs/09 has to disclose.
"""

REFUSAL_DOES_NOT_COVER_THE_FAULT: Mapping[str, tuple[str, str | None]] = {
    # fault: (what docs/09 must disclose, the test in this module that pins it)
    "F-002": (
        "the refusal is the declared name use alone",
        "test_f002_the_refusal_is_the_declared_use_alone_and_not_the_substitution",
    ),
    "F-026": ("not the receipt verifier", None),
    "F-036": (
        "is reported by nothing here",
        "test_f036_a_finding_nobody_reviewed_is_reported_by_nothing_here",
    ),
}
"""Refused rows whose refusal is not the detection their fault names.

The counterpart of :data:`REPORTED_BY_ANOTHER_ASSERTION` for the refused
rows, and machine-checked the same way, because a refusal count is as capable
as a detection count of implying coverage nobody has. F-002's gate refuses
the declaration and not the substitution, and would refuse a faithful name
declared the same way. F-026's bytes did reach the store and are refused on
its next read, which is not the verifier that would notice the same mutation
from the receipt's side (B-036). F-036's published mutation is the owner *or*
the disposition; the owner half is refused before the log is appended, and a
mandatory failed outcome that no event ever names is reported by nothing here
at all. Each has to be disclosed in the docs/09 corpus status section, and
where a test in this module pins the gap it has to exist, so a row can never
count a refusal as more than it is. A row in here is still counted as
``refused``: what is refused is real, and what it does not cover is the
sentence beside it.
"""

MATRIX_DATE = "2026-09-05"
"""The date the docs/09 status table carries, so the two cannot disagree."""


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _bundle(document: dict[str, Any]) -> Any:
    return parse_bundle(document["case"], document["observations"], document["rules"])


def _outcomes(document: dict[str, Any]) -> tuple[Outcome, ...]:
    return evaluate(_bundle(document))


def _by_rule(outcomes: tuple[Outcome, ...], rule_id: str) -> Outcome:
    return next(item for item in outcomes if item.rule_id == rule_id)


def _divergence(document: dict[str, Any], concept: ConceptKind) -> ConceptDivergence:
    return next(
        item
        for item in compute_divergence(_bundle(document)).concepts
        if item.concept is concept
    )


def _rows(status: CorpusStatus) -> tuple[FaultRow, ...]:
    return tuple(row for row in MATRIX if row.status is status)


ALL_FAULT_FILES = sorted(FAULTS.glob("F-*.json"))
FAULT_FILES = [path for path in ALL_FAULT_FILES if path.stem in EXPECTED_DETECTION]
EVIDENCE_FAULT_FILES = [
    path for path in ALL_FAULT_FILES if path.stem in EVIDENCE_FAULTS
]
REFUSED_FILES = sorted(REFUSED.glob("F-*.json"))
CLEAN_FILES = sorted((FAULTS / "clean").glob("*.json"))
EXERCISED = sorted({*EXPECTED_DETECTION, *EVIDENCE_FAULTS})


# --- the denominator ---------------------------------------------------------


def test_the_library_holds_exactly_the_faults_the_tables_expect() -> None:
    """Twelve exercised files, six refused files, and nothing unaccounted for."""

    assert [path.stem for path in ALL_FAULT_FILES] == EXERCISED
    assert len(FAULT_FILES) == 10
    assert len(EVIDENCE_FAULT_FILES) == 2
    assert not set(EXPECTED_DETECTION) & set(EVIDENCE_FAULTS)
    assert [path.stem for path in REFUSED_FILES] == sorted(REFUSED_FAULTS)
    assert not set(REFUSED_FAULTS) & set(EXERCISED)
    assert sorted(LOCATED) == EXERCISED


def test_the_matrix_names_every_published_fault_once() -> None:
    assert [row.fault for row in MATRIX] == [f"F-{n:03d}" for n in range(1, 37)]
    assert {row.fault for row in _rows(CorpusStatus.EXERCISED)} == set(EXERCISED)
    refused = _rows(CorpusStatus.REFUSED)
    assert set(REFUSED_FAULTS) < {row.fault for row in refused}
    for row in MATRIX:
        assert (row.status is CorpusStatus.NOT_EXERCISABLE) == (row.evidence == "")
        assert (
            row.status is CorpusStatus.EXERCISED
            or row.missing
            or row.fault
            in {
                "F-029",
                "F-030",
            }
        ), row.fault


def test_the_matrix_counts_are_the_ones_the_documents_state() -> None:
    """36 faults: the counts, and that none is double counted."""

    counts = {status: len(_rows(status)) for status in CorpusStatus}
    assert counts == {
        CorpusStatus.EXERCISED: 12,
        CorpusStatus.EXERCISED_OUTSIDE_THE_RECEIPT: 7,
        CorpusStatus.REFUSED: 11,
        CorpusStatus.NOT_EXERCISABLE: 6,
    }
    assert sum(counts.values()) == 36


def test_every_fault_file_names_the_assertion_the_table_names() -> None:
    expected = {
        **{fault: row[0] for fault, row in EXPECTED_DETECTION.items()},
        **EVIDENCE_FAULTS,
        **{fault: row[0] for fault, row in REFUSED_FAULTS.items()},
    }
    for path in (*ALL_FAULT_FILES, *REFUSED_FILES):
        document = _load(path)
        assert document["fault"] == path.stem
        assert document["assertion"] == expected[path.stem]
        assert document["mutation"].strip()
        assert set(document) == {
            "fault",
            "mutation",
            "assertion",
            "case",
            "rules",
            "observations",
        }


def test_every_exercised_row_names_its_detector_and_reason() -> None:
    """The prose evidence column cannot say something the test data does not."""

    by_fault = {row.fault: row for row in MATRIX}
    for fault, (_, rule_id, reason) in EXPECTED_DETECTION.items():
        evidence = by_fault[fault].evidence
        assert f"`{fault}.json`" in evidence
        assert rule_id in evidence
        assert f"`{reason.value}`" in evidence
        located = LOCATED[fault].from_expected[1]
        assert located is not None
        assert f"`{located.value}`" in evidence
    for fault, (_, code, path) in REFUSED_FAULTS.items():
        evidence = by_fault[fault].evidence
        assert f"`refused/{fault}.json`" in evidence
        assert f"`{code}` at `{path}`" in evidence
        assert (SPCU_DECLARED_FORM_ONLY in evidence) == (
            code == "prohibited_spcu_mapping"
        )
    f023 = by_fault["F-023"].evidence
    for rule_id in F023_INDETERMINATE_RULES:
        assert rule_id in f023
    assert f"`{OutcomeReason.MISSING_EVIDENCE.value}`" in f023
    assert f"`{F023_UNOBSERVED.value}` unobserved" in f023
    assert f"`{F035_MAPPING_VERSION}`" in by_fault["F-035"].evidence


# --- exercised: reported with the right reason ------------------------------


@pytest.mark.parametrize("path", FAULT_FILES, ids=[path.stem for path in FAULT_FILES])
def test_each_fault_is_reported_as_fail_with_its_own_reason_and_never_as_pass(
    path: Path,
) -> None:
    _, rule_id, reason = EXPECTED_DETECTION[path.stem]
    outcomes = _outcomes(_load(path))
    detector = _by_rule(outcomes, rule_id)
    assert detector.status is OutcomeStatus.FAIL
    assert detector.reason is reason
    assert detector.status is not OutcomeStatus.PASSED
    assert reason in FAILURE_REASONS
    assert detector.observed_sha256s
    if reason is OutcomeReason.VALUE_CHANGED_ACROSS_CHECKPOINTS:
        # A preserved-across outcome carries both sides; the fault is that
        # they differ, and the faithful side may well be the expected hash.
        assert len(set(detector.observed_sha256s)) == 2
    else:
        assert detector.expected_sha256 not in detector.observed_sha256s


@pytest.mark.parametrize("path", FAULT_FILES, ids=[path.stem for path in FAULT_FILES])
def test_each_fault_leaves_a_fail_count_in_the_receipt_summary(path: Path) -> None:
    document = _load(path)
    bundle = _bundle(document)
    receipt = build_receipt(bundle, evaluate(bundle))
    assert receipt["summary"]["fail"] >= 1


@pytest.mark.parametrize("path", CLEAN_FILES, ids=[path.stem for path in CLEAN_FILES])
def test_each_case_variant_passes_every_rule_before_its_fault_is_applied(
    path: Path,
) -> None:
    outcomes = _outcomes(_load(path))
    assert outcomes
    assert all(item.status is OutcomeStatus.PASSED for item in outcomes)


def test_every_fault_rule_set_validates_against_the_published_contract() -> None:
    validator = Draft202012Validator(RULE_SET_SCHEMA)
    for path in (*ALL_FAULT_FILES, *REFUSED_FILES, *CLEAN_FILES):
        validator.validate(_load(path)["rules"])


def test_faults_against_a_variant_case_have_a_clean_counterpart() -> None:
    """A variant without its clean form could hide a rule that never passes."""

    clean_cases = {path.stem for path in CLEAN_FILES}
    for path in (*ALL_FAULT_FILES, *REFUSED_FILES):
        case_id = _load(path)["case"]["case_id"]
        assert case_id == "CTP-I01" or case_id in clean_cases


# --- exercised: localized at the observed boundary the fault touched --------


@pytest.mark.parametrize("fault", EXERCISED)
def test_each_exercised_fault_is_located_where_the_table_says(fault: str) -> None:
    """The divergence section locates the fault, and only at an observed boundary."""

    location = LOCATED[fault]
    entry = _divergence(_load(FAULTS / f"{fault}.json"), location.concept)
    assert (entry.from_expected.status, entry.from_expected.at) == (
        location.from_expected
    )
    assert (
        entry.from_previous.status,
        entry.from_previous.after,
        entry.from_previous.at,
    ) == location.from_previous
    unobserved = {
        state.checkpoint
        for state in entry.checkpoints
        if state.state is EvidenceState.UNOBSERVED
    }
    named = {entry.from_expected.at, entry.from_previous.after, entry.from_previous.at}
    assert not (named - {None}) & unobserved


@pytest.mark.parametrize("fault", sorted(EXPECTED_DETECTION))
def test_the_detector_sits_at_the_first_observed_divergent_boundary(
    fault: str,
) -> None:
    """Localization no later than the first observed divergence (docs/09 §4).

    The rule that reports the fault reads the checkpoint the divergence
    section locates it at, so the receipt names one boundary twice, never two
    different ones.
    """

    _, rule_id, _ = EXPECTED_DETECTION[fault]
    document = _load(FAULTS / f"{fault}.json")
    detector = _by_rule(_outcomes(document), rule_id)
    located = LOCATED[fault].from_expected[1]
    assert located is not None
    assert Checkpoint(detector.checkpoint) is located


def test_no_exercised_fault_names_an_unobserved_boundary_anywhere() -> None:
    """A-034 over the whole library, not only the fixture written for it."""

    for path in ALL_FAULT_FILES:
        for entry in compute_divergence(_bundle(_load(path))).concepts:
            unobserved = {
                s.checkpoint.value
                for s in entry.checkpoints
                if s.state is EvidenceState.UNOBSERVED
            }
            rendered = entry.to_dict()
            from_expected = rendered["from_expected"]
            from_previous = rendered["from_previous"]
            assert isinstance(from_expected, dict)
            assert isinstance(from_previous, dict)
            for value in (
                from_expected["at"],
                from_previous["after"],
                from_previous["at"],
            ):
                assert value not in unobserved


# --- F-001 -------------------------------------------------------------------


def test_f001_the_dropped_name_is_reported_absent_and_not_preserved() -> None:
    """F-001, A-005: the name to use survived registration and not the EHR."""

    document = _load(FAULTS / "F-001.json")
    outcomes = _outcomes(document)
    assert _by_rule(outcomes, "A-I01").status is OutcomeStatus.PASSED
    present = _by_rule(outcomes, "A-I02")
    preserved = _by_rule(outcomes, "A-I03")
    assert (present.status, present.reason) == (
        OutcomeStatus.FAIL,
        OutcomeReason.VALUE_NOT_PRESENT,
    )
    assert (preserved.status, preserved.reason) == (
        OutcomeStatus.FAIL,
        OutcomeReason.VALUE_CHANGED_ACROSS_CHECKPOINTS,
    )
    assert all(item.status is not OutcomeStatus.PASSED for item in (present, preserved))


def test_f001_would_pass_if_the_name_had_survived() -> None:
    """The drop is what turned the outcomes, not the rules."""

    document = _load(FAULTS / "F-001.json")
    faithful = json.loads(json.dumps(document["observations"]["observations"][0]))
    faithful["observation_id"] = "OBS-I01-NTU-EHR"
    faithful["checkpoint"] = "ehr"
    document["observations"]["observations"][1] = faithful
    assert all(item.status is OutcomeStatus.PASSED for item in _outcomes(document))


def test_f001_a_name_removed_entirely_is_indeterminate_never_pass() -> None:
    """Removing the EHR observation is missing evidence, not a pass (A-032)."""

    document = _load(FAULTS / "F-001.json")
    del document["observations"]["observations"][1]
    outcomes = _outcomes(document)
    for rule_id in ("A-I02", "A-I03"):
        outcome = _by_rule(outcomes, rule_id)
        assert outcome.status is OutcomeStatus.INDETERMINATE
        assert outcome.reason is OutcomeReason.MISSING_EVIDENCE


# --- F-009 -------------------------------------------------------------------


def test_f009_the_restamped_record_is_a_change_and_never_a_coercion() -> None:
    """F-009, A-012: source and context gone, the X itself faithful.

    The preservation and exact rules report the record changed at the EHR;
    the not-coerced rule beside them passes, because A-014 is a claim about
    the value and the value survived. A receipt therefore says which claim
    turned, and never reports a lost context as a rewritten value.
    """

    outcomes = _outcomes(_load(FAULTS / "F-009.json"))
    assert _by_rule(outcomes, "A-I01").status is OutcomeStatus.PASSED
    changed = _by_rule(outcomes, "A-I02")
    mismatch = _by_rule(outcomes, "A-I03")
    coercion = _by_rule(outcomes, "A-I04")
    assert (changed.status, changed.reason) == (
        OutcomeStatus.FAIL,
        OutcomeReason.VALUE_CHANGED_ACROSS_CHECKPOINTS,
    )
    assert (mismatch.status, mismatch.reason) == (
        OutcomeStatus.FAIL,
        OutcomeReason.SEMANTIC_MISMATCH,
    )
    assert (coercion.status, coercion.reason) == (
        OutcomeStatus.PASSED,
        OutcomeReason.VALUE_NOT_COERCED,
    )


def test_f009_would_pass_with_the_declared_source_and_context() -> None:
    document = _load(FAULTS / "F-009.json")
    ehr = document["observations"]["observations"][1]
    ehr["value"].update({"context": "government-id", "source": "synthetic-fixture"})
    assert all(item.status is OutcomeStatus.PASSED for item in _outcomes(document))


def test_f009_the_dropped_descriptors_cannot_be_expressed_as_empty() -> None:
    """The contract has no way to carry a dropped source: it refuses instead."""

    for field in ("context", "source"):
        document = _load(FAULTS / "F-009.json")
        ehr = document["observations"]["observations"][1]["value"]
        del ehr[field]
        with pytest.raises(ContextSafeError) as raised:
            _bundle(document)
        assert raised.value.code == "missing_field"
        assert raised.value.path == f"$.observations[1].value.{field}"


# --- F-023 and F-025 --------------------------------------------------------


def test_f023_an_omitted_checkpoint_can_never_be_reported_as_pass() -> None:
    """F-023, A-032: no evidence at the laboratory return, so nothing passes there.

    Both rules that read the missing boundary are indeterminate with
    ``missing_evidence``; the rule at the observed boundary still passes, so
    the fixture shows that it is the omission and not the case that turned
    them. The divergence section marks the boundary unobserved and says
    nothing about it: not agreed, not diverged, not blamed.
    """

    document = _load(FAULTS / "F-023.json")
    outcomes = _outcomes(document)
    assert _by_rule(outcomes, "A-I01").status is OutcomeStatus.PASSED
    for rule_id in F023_INDETERMINATE_RULES:
        outcome = _by_rule(outcomes, rule_id)
        assert outcome.status is OutcomeStatus.INDETERMINATE
        assert outcome.reason is OutcomeReason.MISSING_EVIDENCE
        assert outcome.status is not OutcomeStatus.PASSED
        assert outcome.observed_sha256s == ()
    entry = _divergence(document, ConceptKind.NAME_TO_USE)
    lis = next(s for s in entry.checkpoints if s.checkpoint is F023_UNOBSERVED)
    assert lis.state is EvidenceState.UNOBSERVED
    assert lis.value_sha256s == ()
    receipt = build_receipt(_bundle(document), outcomes)
    assert receipt["summary"]["pass"] == 1
    assert receipt["summary"]["indeterminate"] == 2


def test_f023_would_pass_if_the_omitted_checkpoint_were_observed() -> None:
    """The omission is what turned the outcomes, not the rules."""

    document = _load(FAULTS / "F-023.json")
    restored = json.loads(json.dumps(document["observations"]["observations"][0]))
    restored["observation_id"] = "OBS-I01-NTU-LIS"
    restored["checkpoint"] = F023_UNOBSERVED.value
    document["observations"]["observations"].append(restored)
    assert all(item.status is OutcomeStatus.PASSED for item in _outcomes(document))


def test_f025_a_divergence_is_never_inferred_across_an_unobserved_boundary() -> None:
    """F-025, A-034: the EHR was never observed, so the EHR is never named.

    The value is faithful at registration and changed at the interface. The
    divergence is located at the interface, between registration and the
    interface, and every field that can name a checkpoint avoids the EHR.
    """

    document = _load(FAULTS / "F-025.json")
    entry = _divergence(document, ConceptKind.NAME_TO_USE)
    ehr = next(s for s in entry.checkpoints if s.checkpoint is Checkpoint.EHR)
    assert ehr.state is EvidenceState.UNOBSERVED
    rendered = json.dumps(entry.to_dict())
    assert '"at": "ehr"' not in rendered
    assert '"after": "ehr"' not in rendered
    outcomes = _outcomes(document)
    assert _by_rule(outcomes, "A-I01").status is OutcomeStatus.PASSED


def test_f025_observing_the_gap_faithfully_moves_nothing_but_the_near_side() -> None:
    """Filling the EHR with the faithful value leaves the location unchanged."""

    document = _load(FAULTS / "F-025.json")
    filled = json.loads(json.dumps(document["observations"]["observations"][0]))
    filled["observation_id"] = "OBS-I01-NTU-EHR"
    filled["checkpoint"] = "ehr"
    document["observations"]["observations"].append(filled)
    entry = _divergence(document, ConceptKind.NAME_TO_USE)
    assert entry.from_expected.at is Checkpoint.INTERFACE
    assert entry.from_previous.after is Checkpoint.EHR
    assert entry.from_previous.at is Checkpoint.INTERFACE


# --- F-035 -------------------------------------------------------------------


def _with_mapping_version(document: dict[str, Any], version: str) -> dict[str, Any]:
    copied = json.loads(json.dumps(document))
    copied["observations"]["observations"][0]["mapping"]["mapping_version"] = version
    return copied


def test_f035_a_changed_mapping_version_can_never_share_a_run_identity() -> None:
    """F-035, A-035: the same faithful value through another mapping version.

    Both forms pass, because the mapping version is not what a predicate
    decides. What must differ is the identity: the outcome's trace names the
    version and hash of the mapping the evidence came through, and the
    input, result, and payload hashes all move with it. Only the rule-set
    hash stays, because the rules did not change.
    """

    faulted_document = _load(FAULTS / "F-035.json")
    clean_document = _with_mapping_version(faulted_document, F035_CLEAN_MAPPING_VERSION)
    faulted_bundle = _bundle(faulted_document)
    clean_bundle = _bundle(clean_document)
    faulted = build_receipt_document(faulted_bundle, evaluate(faulted_bundle))
    clean = build_receipt_document(clean_bundle, evaluate(clean_bundle))
    for receipt in (faulted, clean):
        assert receipt["payload"]["summary"] == {
            "blocked": 0,
            "fail": 0,
            "indeterminate": 0,
            "not_applicable": 0,
            "pass": 1,
        }
    assert faulted["payload_sha256"] != clean["payload_sha256"]
    faulted_hashes = faulted["payload"]["hashes"]
    clean_hashes = clean["payload"]["hashes"]
    assert faulted_hashes["input_sha256"] != clean_hashes["input_sha256"]
    assert faulted_hashes["result_sha256"] != clean_hashes["result_sha256"]
    assert faulted_hashes["rule_set_sha256"] == clean_hashes["rule_set_sha256"]


def test_f035_the_trace_names_the_mapping_the_evidence_came_through() -> None:
    document = _load(FAULTS / "F-035.json")
    bundle = _bundle(document)
    outcome = _by_rule(evaluate(bundle), "A-I01")
    assert outcome.checkpoint == Checkpoint.EHR.value
    mapping = bundle.observations[0].mapping
    assert mapping.mapping_version == F035_MAPPING_VERSION
    assert [item.to_dict() for item in outcome.trace.mappings] == [
        {
            "mapping_sha256": sha256_json(mapping.to_dict()),
            "mapping_version": F035_MAPPING_VERSION,
        }
    ]


_F035_VERSIONS = (F035_CLEAN_MAPPING_VERSION, F035_MAPPING_VERSION, "1.0.0", "0.2.1")


def test_f035_every_distinct_mapping_version_is_a_distinct_identity() -> None:
    document = _load(FAULTS / "F-035.json")
    identities = set()
    for version in _F035_VERSIONS:
        bundle = _bundle(_with_mapping_version(document, version))
        receipt = build_receipt_document(bundle, evaluate(bundle))
        identities.add(receipt["payload_sha256"])
    assert len(identities) == len(_F035_VERSIONS)


# --- refused before evaluation ------------------------------------------------

_REFUSED_FIXTURE_TOKENS = (
    "fixture-unsupported",
    "fixture-record-not-synthetic",
    "CTP-I02",
)
"""The identity-shaped values the refused fixtures carry; none may surface."""


@pytest.mark.parametrize(
    "path", REFUSED_FILES, ids=[path.stem for path in REFUSED_FILES]
)
def test_each_refused_fault_is_refused_whole_with_its_own_code(path: Path) -> None:
    """The gate names a category and a structural location, never content."""

    document = _load(path)
    _, code, error_path = REFUSED_FAULTS[path.stem]
    with pytest.raises(ContextSafeError) as raised:
        _bundle(document)
    assert raised.value.code == code
    assert raised.value.path == error_path
    rendered = json.dumps(raised.value.to_dict())
    for token in _REFUSED_FIXTURE_TOKENS:
        assert token not in rendered


@pytest.mark.parametrize(
    "path", REFUSED_FILES, ids=[path.stem for path in REFUSED_FILES]
)
def test_each_refused_fault_exits_two_through_the_cli_and_writes_no_receipt(
    path: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    document = _load(path)
    inputs = {}
    for name in ("case", "observations", "rules"):
        inputs[name] = tmp_path / f"{name}.json"
        inputs[name].write_text(json.dumps(document[name]), encoding="utf-8")
    output = tmp_path / "receipt.json"
    argv = [
        "evaluate",
        "--case",
        str(inputs["case"]),
        "--observations",
        str(inputs["observations"]),
        "--rules",
        str(inputs["rules"]),
        "--output",
        str(output),
    ]
    assert main(argv) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err)["error"]["code"] == REFUSED_FAULTS[path.stem][1]
    for token in _REFUSED_FIXTURE_TOKENS:
        assert token not in captured.err
    assert not output.exists()


def test_f002_a_name_declared_as_the_official_one_is_refused_whole() -> None:
    """F-002, A-006: the contract carries one name use, and refuses the other.

    The EHR says it wrote the official (legal) name in place of the name to
    use. ``name_to_use`` admits ``usual`` and nothing else, so the whole
    observation set is refused before any rule runs and no receipt exists.

    The fixture applies two changes to reach that shape, the declaration and
    the substituted token, and this test says only that the pair is refused.
    Which one the refusal turns on is the next test's claim, not this one's.
    """

    document = _load(REFUSED / "F-002.json")
    ehr = document["observations"]["observations"][1]["value"]
    assert ehr["use"] == "official"
    assert ehr["value"] != document["case"]["concepts"]["name_to_use"]["value"]
    with pytest.raises(ContextSafeError) as raised:
        _bundle(document)
    assert raised.value.code == "invalid_name_use"
    assert "official" not in json.dumps(raised.value.to_dict())


def test_f002_the_refusal_is_the_declared_use_alone_and_not_the_substitution() -> None:
    """What the refusal is not isolated to, stated as a test rather than as prose.

    Revert the substituted token and leave the declaration: the EHR now
    carries the case's own name to use and still says it wrote it as the
    official one, and the same code is raised at the same path. So the gate
    refuses the declaration a legal-name substitution would have to be made
    under, never the substitution, and this row may not be read as a
    mechanism that tells one name from another. That is what A-006/A-007 and
    the name contexts of B-019 would decide.
    """

    document = _load(REFUSED / "F-002.json")
    ehr = document["observations"]["observations"][1]["value"]
    ehr["value"] = document["case"]["concepts"]["name_to_use"]["value"]
    assert ehr["value"] == document["observations"]["observations"][0]["value"]["value"]
    assert ehr["use"] == "official"
    with pytest.raises(ContextSafeError) as raised:
        _bundle(document)
    _, code, error_path = REFUSED_FAULTS["F-002"]
    assert (raised.value.code, raised.value.path) == (code, error_path)


def test_f002_the_undeclared_form_is_only_a_changed_value() -> None:
    """What the refusal does not cover, stated as a test rather than as prose.

    Put the same substituted token in the usual slot and nothing declares a
    legal name any more: what is reported is a value that changed between
    registration and the EHR, which is what a predicate can see. Nothing names the
    substitution for what it is, and telling a legal name from any other name
    is what A-006/A-007 and the name contexts of B-019 would decide.
    """

    document = _load(REFUSED / "F-002.json")
    document["observations"]["observations"][1]["value"]["use"] = "usual"
    outcomes = _outcomes(document)
    assert _by_rule(outcomes, "A-I02").status is OutcomeStatus.PASSED
    changed = _by_rule(outcomes, "A-I03")
    assert (changed.status, changed.reason) == (
        OutcomeStatus.FAIL,
        OutcomeReason.VALUE_CHANGED_ACROSS_CHECKPOINTS,
    )
    entry = _divergence(document, ConceptKind.NAME_TO_USE)
    assert entry.from_expected.at is Checkpoint.EHR
    rendered = json.dumps(entry.to_dict())
    for word in ("legal", "official"):
        assert word not in rendered


def test_f002_a_fixture_carrying_neither_change_passes_every_rule() -> None:
    """The rule set is clean over this fixture's case, and nothing more.

    Both of the fixture's changes are reverted at once, so this says only
    that the case and the rule set pass when neither is applied. It says
    nothing about which change turned the outcome: the declaration alone is
    refused, and the substituted token alone is a value that changed, which
    the two tests above establish one at a time.
    """

    document = _load(REFUSED / "F-002.json")
    document["observations"]["observations"][1]["value"] = json.loads(
        json.dumps(document["observations"]["observations"][0]["value"])
    )
    assert all(item.status is OutcomeStatus.PASSED for item in _outcomes(document))


def test_f015_and_f016_are_refused_by_the_mapping_not_the_value() -> None:
    """The SPCU value is the declared one; what is refused is the derivation."""

    for fault in ("F-015", "F-016"):
        document = _load(REFUSED / f"{fault}.json")
        observation = document["observations"]["observations"][0]
        assert (
            observation["value"]
            == document["case"]["concepts"]["sex_parameter_for_clinical_use"][0]
        )
        observation["mapping"]["source_concept"] = "sex_parameter_for_clinical_use"
        assert all(item.status is OutcomeStatus.PASSED for item in _outcomes(document))


def test_f015_a_manifest_that_drops_the_prohibition_is_refused_too() -> None:
    """A case that stops prohibiting GI-to-SPCU is not a case this runner reads."""

    document = _load(REFUSED / "F-015.json")
    document["case"]["prohibited_inferences"] = ["recorded_sex_or_gender_to_spcu"]
    with pytest.raises(ContextSafeError) as raised:
        _bundle(document)
    assert raised.value.code == "missing_safety_guard"


def test_f024_an_unsupported_status_is_refused_not_normalized() -> None:
    """The same fault on a status enum: refused at its path, never nearest-matched."""

    document = _load(REFUSED / "F-024.json")
    document["observations"]["observations"][0] = {
        **document["observations"]["observations"][0],
        "concept": "pronouns",
        "value": {"status": "not-asked", "value": None},
        "mapping": {
            "source_concept": "pronouns",
            "target_concept": "pronouns",
            "mapping_version": "0.1.0",
        },
        "evidence": {
            **document["observations"]["observations"][0]["evidence"],
            "source_pointer": "$.concepts.pronouns",
        },
    }
    with pytest.raises(ContextSafeError) as raised:
        _bundle(document)
    assert raised.value.code == "invalid_enum"
    assert raised.value.path == "$.observations[0].value.status"
    assert "not-asked" not in json.dumps(raised.value.to_dict())


def test_f024_would_pass_with_a_supported_value() -> None:
    document = _load(REFUSED / "F-024.json")
    document["observations"]["observations"][0]["value"]["value"] = "X"
    assert all(item.status is OutcomeStatus.PASSED for item in _outcomes(document))


def test_f029_an_identifying_field_is_refused_wherever_it_appears() -> None:
    """The prohibited-field form of F-029, on the case and on an observation."""

    document = _load(REFUSED / "F-029.json")
    document["case"]["synthetic_identifier"]["value"] = "CSYN-CTP-I01"
    assert all(item.status is OutcomeStatus.PASSED for item in _outcomes(document))
    for target in (document["case"], document["observations"]["observations"][0]):
        target["mrn"] = "fixture-record-locator"
        with pytest.raises(ContextSafeError) as raised:
            _bundle(document)
        assert raised.value.code == "prohibited_field"
        assert "fixture-record-locator" not in json.dumps(raised.value.to_dict())
        del target["mrn"]


def test_f032_the_misattached_observation_is_refused_not_reassigned() -> None:
    """Neither case gets the observation: the set is refused as a whole."""

    document = _load(REFUSED / "F-032.json")
    with pytest.raises(ContextSafeError):
        _bundle(document)
    document["observations"]["observations"][1]["case_id"] = "CTP-I01"
    assert all(item.status is OutcomeStatus.PASSED for item in _outcomes(document))


def test_every_refused_row_that_names_a_test_names_one_that_exists() -> None:
    """Six rows point at a named test; every pointer must resolve.

    A pointer here is evidence *for* the row's status, so a test that proves
    a non-detection does not belong in the column: what F-036's refusal does
    not cover is carried by :data:`REFUSAL_DOES_NOT_COVER_THE_FAULT` and the
    test below, which would otherwise inflate this count with a pointer at a
    test that guards nothing.
    """

    pattern = re.compile(r"`tests/(test_[a-z0-9_]+\.py)::(test_[a-z0-9_]+)`")
    named = 0
    for row in _rows(CorpusStatus.REFUSED):
        for module, function in pattern.findall(row.evidence):
            source = (ROOT / "tests" / module).read_text(encoding="utf-8")
            assert f"def {function}(" in source, row.fault
            named += 1
    assert named == 8


def test_every_refusal_that_does_not_cover_its_fault_says_so() -> None:
    """A refusal count may not imply coverage the gate does not have.

    The register names, for each such row, a sentence the docs/09 corpus
    status section has to carry and the test in this module that pins the
    gap. Both directions are checked: a row in the register that the section
    does not disclose is a finding, and so is a register entry whose row is
    not refused at all.
    """

    section = _corpus_status_section()
    source = Path(__file__).read_text(encoding="utf-8")
    refused = {row.fault for row in _rows(CorpusStatus.REFUSED)}
    for fault, (disclosure, pinned_by) in REFUSAL_DOES_NOT_COVER_THE_FAULT.items():
        assert fault in refused, fault
        assert fault in section, fault
        assert disclosure in section, fault
        if pinned_by is not None:
            assert f"def {pinned_by}(" in source, fault


# --- refused at the receipt document and at the review log -------------------


def _receipt_document(fault: str) -> dict[str, Any]:
    """The receipt document one exercised fault's fixture produces."""

    bundle = _bundle(_load(FAULTS / f"{fault}.json"))
    document = build_receipt_document(bundle, evaluate(bundle))
    assert isinstance(document, dict)
    return document


def _sealed(document: dict[str, Any]) -> dict[str, Any]:
    """Re-derive ``payload_sha256`` so a refusal is about the field, not the hash."""

    document["payload_sha256"] = sha256_json(document["payload"])
    return document


F027_INJECTED_FIELD = "legal_name"
F027_INJECTED_VALUE = "CSYN-ASTER-LEGAL"
"""The unnecessary field and the synthetic token this fault would carry."""

F027_LEVELS: tuple[tuple[str | int, ...], ...] = (
    (),
    ("envelope",),
    ("payload",),
    ("payload", "hashes"),
    ("payload", "results", 0),
)
"""Every level of the receipt document the field could be added at."""


def test_f027_an_unnecessary_identity_field_never_reaches_a_page() -> None:
    """F-027, A-031/A-036: the page carries what substantiates an outcome.

    Two halves. The receipt this corpus produces has no identity value in it
    to render, so the page has none: the name the fault library's fixtures
    carry appears nowhere on it. And a document carrying a field the contract
    does not publish is refused at every level of the document rather than
    rendered around, so a report template cannot acquire a legal-name field by
    having one added to the document it is rendered from -- the closed field
    set is what decides that, so the same holds for any other. The rejection
    names a location and never the field or the value.
    """

    page = render_receipt_page(_sealed(_receipt_document("F-001")))
    assert (
        _load(FAULTS / "F-001.json")["case"]["concepts"]["name_to_use"]["value"]
        not in page
    )
    for level in F027_LEVELS:
        document = _receipt_document("F-001")
        target: Any = document
        for step in level:
            target = target[step]
        target[F027_INJECTED_FIELD] = F027_INJECTED_VALUE
        with pytest.raises(ContextSafeError) as raised:
            render_receipt_page(_sealed(document))
        assert raised.value.code == "invalid_receipt_document", level
        rendered = json.dumps(raised.value.to_dict())
        assert F027_INJECTED_VALUE not in rendered
        assert F027_INJECTED_FIELD not in rendered


F036_FINDING: dict[str, str] = {
    "rule_id": "A-I02",
    "case_id": "CTP-I01",
    "checkpoint": Checkpoint.EHR.value,
    "concept": ConceptKind.NAME_TO_USE.value,
}
"""The mandatory failed outcome F-036 is reviewed against, from F-001."""

F036_SECOND_FINDING_RULE = "A-I03"
"""The other failed outcome in the same receipt, which no event here names."""

F036_SIGNER: dict[str, str] = {
    "role": "contextsafe_clinical_safety_chair",
    "organization_id": "ORG-CONTEXTSAFE-FIXTURE",
    "signature_status": "not_verified",
}
"""A declared signer, which authorizes nothing: no signature is verified (B-035)."""


def _review_event(
    document: dict[str, Any], decision: str, **fields: Any
) -> ReviewEvent:
    """Parse one shape-valid review event bound to this receipt document."""

    event: dict[str, Any] = {
        "schema_version": "contextsafe.review-event/1.0.0",
        "outcome": dict(F036_FINDING),
        "receipt": {
            "payload_sha256": document["payload_sha256"],
            "rule_set_sha256": document["payload"]["hashes"]["rule_set_sha256"],
        },
        "decision": decision,
        "severity": None,
        "owner": None,
        "rationale_code": "evidence_verified_against_source",
        "external_reference": None,
        "signers": [dict(F036_SIGNER)],
        "signature_status": "not_verified",
        **fields,
    }
    return parse_review_event(event)


def test_f036_a_disposition_that_omits_the_owner_is_refused() -> None:
    """F-036: neither half of a disposition can be left out of the log.

    Omitting the owner is refused on the event's own shape; reaching a
    disposition without ever assigning one is refused by the transition table,
    because ``remediated`` is reachable only from ``owned``. Each names a
    field, and neither event can be appended to a log.
    """

    document = _sealed(_receipt_document("F-001"))
    findings = parse_receipt_findings(document)
    with pytest.raises(ContextSafeError) as raised:
        _review_event(
            document,
            "owner_assigned",
            owner=None,
            rationale_code="ownership_assigned_by_plan_role",
        )
    assert (raised.value.code, raised.value.path) == ("owner_required", "$.owner")

    confirmed = _review_event(document, "confirmed", severity="cs2_high")
    bind_to_receipt(confirmed, findings)
    state = apply_event(FindingState(outcome=confirmed.outcome), confirmed, "0" * 64)
    assert state.owner is None
    remediated = _review_event(
        document, "remediated", rationale_code="remediation_verified_by_rerun"
    )
    with pytest.raises(ContextSafeError) as raised:
        apply_event(state, remediated, "1" * 64)
    assert (raised.value.code, raised.value.path) == (
        "illegal_transition",
        "$.decision",
    )


def test_f036_a_finding_nobody_reviewed_is_reported_by_nothing_here() -> None:
    """What the refusal does not cover, stated as a test rather than as prose.

    The receipt carries two mandatory failed outcomes. A log that disposes of
    one says nothing at all about the other: the review state is derived from
    the log, and no mechanism here reads a receipt's findings back against it.
    A finding with no owner and no disposition is therefore silent rather than
    reported, which is the gate F-036's row still waits on.
    """

    document = _sealed(_receipt_document("F-001"))
    findings = parse_receipt_findings(document)
    reviewed = {key.to_dict()["rule_id"] for key in findings.findings}
    assert reviewed == {F036_FINDING["rule_id"], F036_SECOND_FINDING_RULE}

    confirmed = _review_event(document, "confirmed", severity="cs2_high")
    bind_to_receipt(confirmed, findings)
    state = apply_event(FindingState(outcome=confirmed.outcome), confirmed, "0" * 64)
    assert state.outcome.to_dict()["rule_id"] == F036_FINDING["rule_id"]
    undisposed = {key for key in findings.findings if key != confirmed.outcome}
    assert {key.to_dict()["rule_id"] for key in undisposed} == {
        F036_SECOND_FINDING_RULE
    }


# --- the documents ----------------------------------------------------------


def _doc_lines() -> list[str]:
    return TEST_PLAN.read_text(encoding="utf-8").splitlines()


def _corpus_status_section() -> str:
    """The dated corpus-status section of docs/09, whitespace collapsed."""

    text = TEST_PLAN.read_text(encoding="utf-8")
    start = text.index(f"### Corpus status, {MATRIX_DATE}")
    return " ".join(text[start : text.index("## 5.", start)].split())


_LIBRARY_ROW = re.compile(r"^\| (F-0\d\d) \| ([^|]+) \| ([^|]+) \|$")
_STATUS_ROW = re.compile(r"^\| (F-0\d\d) \| ([^|]+) \| ([^|]+) \| ([^|]+) \|$")
_COUNTS = re.compile(
    r"As of (\d{4}-\d{2}-\d{2}): (\d+) of 36 exercised at receipt level, "
    r"(\d+) exercised outside the receipt, (\d+) refused by a fail-closed gate, "
    r"and (\d+) not yet exercisable\."
)


def docs_status_row(row: FaultRow) -> str:
    """Render one matrix row the way the docs/09 status table carries it."""

    evidence = row.evidence or "—"
    missing = "; ".join(item.value for item in row.missing) or "—"
    return f"| {row.fault} | {row.status.value} | {evidence} | {missing} |"


def test_the_matrix_restates_the_library_table_verbatim() -> None:
    """The mutation and detector columns are docs/09 section 4's, unchanged."""

    library = {
        match.group(1): (match.group(2).strip(), match.group(3).strip())
        for line in _doc_lines()
        if (match := _LIBRARY_ROW.match(line)) is not None
    }
    assert len(library) == 36
    for row in MATRIX:
        assert library[row.fault] == (row.mutation, row.detector), row.fault


def test_the_docs_status_table_is_the_matrix_row_for_row() -> None:
    """Both directions: a changed row and a missing row are each a finding."""

    documented = [line for line in _doc_lines() if _STATUS_ROW.match(line)]
    assert documented == [docs_status_row(row) for row in MATRIX]


def test_the_docs_counts_are_the_matrix_counts_and_carry_the_date() -> None:
    matches = [
        match for line in _doc_lines() if (match := _COUNTS.search(line)) is not None
    ]
    assert len(matches) == 1
    date, exercised, outside, refused, waiting = matches[0].groups()
    assert date == MATRIX_DATE
    assert (int(exercised), int(outside), int(refused), int(waiting)) == (
        len(_rows(CorpusStatus.EXERCISED)),
        len(_rows(CorpusStatus.EXERCISED_OUTSIDE_THE_RECEIPT)),
        len(_rows(CorpusStatus.REFUSED)),
        len(_rows(CorpusStatus.NOT_EXERCISABLE)),
    )


_NUMBER_WORDS = [
    "Zero",
    "One",
    "Two",
    "Three",
    "Four",
    "Five",
    "Six",
    "Seven",
    "Eight",
    "Nine",
    "Ten",
    "Eleven",
    "Twelve",
    "Thirteen",
    "Fourteen",
    "Fifteen",
    "Sixteen",
    "Seventeen",
    "Eighteen",
    "Nineteen",
    "Twenty",
    "Twenty-one",
    "Twenty-two",
    "Twenty-three",
    "Twenty-four",
    "Twenty-five",
    "Twenty-six",
    "Twenty-seven",
    "Twenty-eight",
    "Twenty-nine",
    "Thirty",
    "Thirty-one",
    "Thirty-two",
    "Thirty-three",
    "Thirty-four",
    "Thirty-five",
    "Thirty-six",
]


def _readme_item(item: str) -> str:
    """One iteration bullet group, located by the item its lead-in names.

    The 2026-09 wave's per-item ``### B-0xx`` subsections were consolidated
    into the README's iteration-6 bullet list on 2026-09-04, so a heading is no
    longer what holds these counts; the bullet that names the item is. A bullet
    runs from its own ``- **`` to the next one, or to the end of the list.
    """

    text = README.read_text(encoding="utf-8")
    named = text.index(f"({item}).**")
    start = text.rindex("\n- **", 0, named)
    following = re.compile(r"\n- \*\*|\n#+ ").search(text, named)
    assert following is not None, item
    return " ".join(text[start : following.start()].split())


def test_the_readme_carries_one_current_count_and_older_slices_defer_to_it() -> None:
    """A slice's bullet may say what it detected, never what the tree detects.

    The B-028 bullet was written when twenty-seven faults had no answer here;
    that count is dated to its slice and points at the bullet that carries the
    current one, whose figures are the matrix's.

    The headline sentence is pinned here word for word, not only its four
    per-status figures, because the arithmetic behind a summary word is what
    drifts: a headline that quietly starts counting refusals as verdicts
    rises without any row moving. So the sentence names its three figures and
    what each is over, and every one of them is derived from the matrix. The
    missing items the waiting rows name are pinned the same way, so the
    README cannot compress one into a shorter dependency than the row waits
    on.
    """

    older = _readme_item("B-028")
    assert "are not detectable by anything here" not in older
    assert "were not detectable by that slice" in older
    assert "the B-048 bullet below carries the current count" in older
    current = _readme_item("B-048")
    for status, phrase in (
        (CorpusStatus.EXERCISED, "are *exercised*"),
        (
            CorpusStatus.EXERCISED_OUTSIDE_THE_RECEIPT,
            "are *exercised outside the receipt*",
        ),
        (CorpusStatus.REFUSED, "are *refused*"),
        (CorpusStatus.NOT_EXERCISABLE, "are *not yet exercisable*"),
    ):
        assert f"{_NUMBER_WORDS[len(_rows(status))]} {phrase}" in current, phrase
    with_a_verdict = len(_rows(CorpusStatus.EXERCISED)) + len(
        _rows(CorpusStatus.EXERCISED_OUTSIDE_THE_RECEIPT)
    )
    assert (
        f"{_NUMBER_WORDS[len(_rows(CorpusStatus.EXERCISED))]} of 36 at receipt level, "
        f"{_NUMBER_WORDS[with_a_verdict].lower()} with a verdict in all, and "
        f"{_NUMBER_WORDS[len(_rows(CorpusStatus.REFUSED))].lower()} more refused "
        "before a verdict could exist" in current
    )
    for row in _rows(CorpusStatus.NOT_EXERCISABLE):
        for item in row.missing:
            assert item.value.split(" (")[0] in current, item


def waiting_dependencies() -> tuple[tuple[MissingItem, int | None], ...]:
    """What the not-yet-exercisable rows wait on, with the issue tracking each."""

    seen = {
        item: MISSING_ITEM_ISSUES[item]
        for row in _rows(CorpusStatus.NOT_EXERCISABLE)
        for item in row.missing
    }
    return tuple(sorted(seen.items(), key=lambda pair: pair[0].value))


def test_every_missing_item_says_whether_an_issue_tracks_it() -> None:
    """A dependency with no issue is the finding, not a blank in the table."""

    assert set(MISSING_ITEM_ISSUES) == set(MissingItem)
    assert (
        tuple(item for item, issue in waiting_dependencies() if issue is None)
        == BLOCKED_WITHOUT_AN_ISSUE
    )


def test_the_docs_name_the_issue_behind_every_waiting_row() -> None:
    """B-048's closing condition, restated where the table is read.

    B-048 closes when every row is exercised, refused, or waiting on a
    dependency that has an issue of its own. So the corpus status section has
    to say, for each thing the waiting rows wait on, either which issue tracks
    it or that none does -- and the sentences are derived from the matrix here
    rather than read from the prose, so a new waiting row cannot arrive
    without one. An issue that only blocks the item, rather than asking for
    it, is disclosed as that: :data:`DECISION_ONLY_ISSUES` says which, and the
    section has to say so beside the number.
    """

    section = _corpus_status_section()
    for item, issue in waiting_dependencies():
        if issue is None:
            assert f"{item.value} has no issue of its own" in section, item
        else:
            assert f"{item.value} is issue #{issue}" in section, item
        if item in DECISION_ONLY_ISSUES:
            assert f"#{issue} is the decision that blocks it" in section, item


def test_the_docs_say_what_this_corpus_is_not() -> None:
    """The disclaimers B-048 requires travel with the table, not only with this file."""

    section = _corpus_status_section()
    for phrase in (
        "not the 41-fault evaluation",
        "no hidden-fault set",
        "no independent",
        "no population-sensitivity claim",
    ):
        assert phrase in section, phrase


# --- the corpus itself ------------------------------------------------------


@pytest.mark.parametrize(
    "restamp",
    [
        {"context": "payer"},
        {"source": "interface-engine"},
        {"context": "payer", "source": "interface-engine"},
    ],
    ids=["context", "source", "both"],
)
@pytest.mark.parametrize("name", ["F-007", "F-008"])
def test_the_coercion_faults_are_still_detected_when_the_boundary_restamps_the_record(
    name: str, restamp: dict[str, str]
) -> None:
    """F-007 and F-008 with the boundary's own context or source on the record.

    The coerced value then hashes like nothing in the forbidden set, and the
    detector must still report ``fail``/``value_coerced``: A-014 is a claim
    about the value, and a boundary that relabels what it rewrote does not
    earn a pass for it.
    """

    document = _load(FAULTS / f"{name}.json")
    _, rule_id, reason = EXPECTED_DETECTION[name]
    coerced = next(
        item
        for item in document["observations"]["observations"]
        if item["concept"] == "recorded_sex_or_gender"
    )
    coerced["value"].update(restamp)
    bundle = _bundle(document)
    detector = _by_rule(evaluate(bundle), rule_id)
    forbidden_hashes = {
        sha256_json(item.to_dict())
        for rule in bundle.rule_set.rules
        for item in rule.forbidden
    }
    assert detector.status is OutcomeStatus.FAIL
    assert detector.reason is reason
    assert forbidden_hashes.isdisjoint(detector.observed_sha256s)


def test_the_declined_fault_would_pass_if_declined_became_declined_again() -> None:
    """F-005 and F-031 fail because the status moved, not because of the case."""

    for name in ("F-005", "F-031"):
        document = _load(FAULTS / f"{name}.json")
        clean = _load(FAULTS / "clean" / "CTP-I07.json")
        document["observations"] = clean["observations"]
        assert all(item.status is OutcomeStatus.PASSED for item in _outcomes(document))


def test_no_fault_fixture_carries_a_non_synthetic_identifier() -> None:
    """F-029 is the one deliberate exception, and even it uses a fixture token."""

    for path in (*ALL_FAULT_FILES, *REFUSED_FILES, *CLEAN_FILES):
        document = _load(path)
        identifier = document["case"]["synthetic_identifier"]
        assert identifier["system"] == "urn:contextsafe:synthetic"
        if path.stem == "F-029":
            assert identifier["value"] == "fixture-record-not-synthetic"
        else:
            assert identifier["value"] == f"CSYN-{document['case']['case_id']}"
        name = document["case"]["concepts"]["name_to_use"]["value"]
        assert name is None or name.startswith("CSYN-")
        for observation in document["observations"]["observations"]:
            if observation["concept"] == "name_to_use":
                value = observation["value"]["value"]
                assert value is None or value.startswith("CSYN-")


# --- exercised outside the receipt: the laboratory faults --------------------

LABORATORY_FILES = sorted(LABORATORY.glob("F-*.json"))
LABORATORY_CLEAN_FILES = sorted(LABORATORY_CLEAN.glob("F-*.json"))


def _laboratory_outcomes(path: Path) -> tuple[ResultOutcome, ...]:
    document = _load(path)
    return evaluate_results(
        parse_result_bundle(document["case"], document["results"], document["rules"])
    )


def _laboratory_by_rule(
    outcomes: tuple[ResultOutcome, ...], rule_id: str
) -> ResultOutcome:
    return next(item for item in outcomes if item.rule_id == rule_id)


def test_the_laboratory_library_holds_exactly_the_faults_the_table_expects() -> None:
    """Seven faults, each with a fixture and a clean counterpart, and no others."""

    assert [path.stem for path in LABORATORY_FILES] == sorted(LABORATORY_DETECTION)
    assert [path.stem for path in LABORATORY_CLEAN_FILES] == sorted(
        LABORATORY_DETECTION
    )
    assert not set(LABORATORY_DETECTION) & set(EXERCISED)
    assert not set(LABORATORY_DETECTION) & set(REFUSED_FAULTS)
    assert {
        row.fault for row in _rows(CorpusStatus.EXERCISED_OUTSIDE_THE_RECEIPT)
    } == set(LABORATORY_DETECTION)


def test_every_laboratory_fault_file_names_the_assertion_the_table_names() -> None:
    for path in (*LABORATORY_FILES, *LABORATORY_CLEAN_FILES):
        document = _load(path)
        mutation, assertion, _rule_id, _reason = LABORATORY_DETECTION[path.stem]
        assert document["fault"] == path.stem
        assert document["mutation"] == mutation
        assert document["assertion"] == assertion
        assert set(document) == {
            "fault",
            "mutation",
            "assertion",
            "case",
            "results",
            "rules",
        }


@pytest.mark.parametrize(
    "path", LABORATORY_FILES, ids=[path.stem for path in LABORATORY_FILES]
)
def test_each_laboratory_fault_is_reported_by_its_predicate_and_never_as_pass(
    path: Path,
) -> None:
    _mutation, _assertion, rule_id, reason = LABORATORY_DETECTION[path.stem]
    outcomes = _laboratory_outcomes(path)
    detector = _laboratory_by_rule(outcomes, rule_id)
    assert detector.status is OutcomeStatus.FAIL
    assert detector.reason is reason
    assert detector.observed_sha256s
    # "never as pass" is a property of every outcome of the faulted fixture,
    # not of the detector alone: no outcome may sit under a status its reason
    # does not admit, which is what keeps a `pass` out of a finding reason and
    # a finding out of an affirmative one, on the three rules the fault is not
    # aimed at as much as on the one it is.
    assert all(item.status in REASON_STATUSES[item.reason] for item in outcomes)
    assert AFFIRMATIVE_RESULT_REASONS.isdisjoint(
        item.reason for item in outcomes if item.rule_id == rule_id
    )


@pytest.mark.parametrize(
    "path", LABORATORY_FILES, ids=[path.stem for path in LABORATORY_FILES]
)
def test_each_laboratory_fault_leaves_exactly_one_failing_rule(path: Path) -> None:
    """One fault, one fail: the other predicates are not collateral damage."""

    _mutation, _assertion, rule_id, _reason = LABORATORY_DETECTION[path.stem]
    outcomes = _laboratory_outcomes(path)
    failed = [item for item in outcomes if item.status is OutcomeStatus.FAIL]
    assert [item.rule_id for item in failed] == [rule_id]


@pytest.mark.parametrize(
    "path", LABORATORY_CLEAN_FILES, ids=[path.stem for path in LABORATORY_CLEAN_FILES]
)
def test_each_laboratory_fixture_passes_every_rule_before_its_fault_is_applied(
    path: Path,
) -> None:
    """The fault turned the outcome, not the rule set."""

    outcomes = _laboratory_outcomes(path)
    assert outcomes
    assert all(item.status is OutcomeStatus.PASSED for item in outcomes)


def test_no_laboratory_fault_of_a_missing_range_is_ever_reported_normal() -> None:
    """A-030: F-019 fails the presence claim and decides no flag at all."""

    outcomes = _laboratory_outcomes(LABORATORY / "F-019.json")
    flag = _laboratory_by_rule(outcomes, "A-L04")
    assert flag.status is OutcomeStatus.INDETERMINATE
    assert flag.reason is ResultOutcomeReason.REFERENCE_INTERVAL_ABSENT


def test_the_wrong_unit_fault_decides_no_flag_either() -> None:
    """F-033: a range in another unit cannot be compared with the value."""

    outcomes = _laboratory_outcomes(LABORATORY / "F-033.json")
    flag = _laboratory_by_rule(outcomes, "A-L04")
    assert flag.status is OutcomeStatus.INDETERMINATE
    assert flag.reason is ResultOutcomeReason.REFERENCE_INTERVAL_UNIT_MISMATCH


def test_every_laboratory_row_names_its_detector_and_reason() -> None:
    """The prose evidence column cannot say something the test data does not."""

    by_fault = {row.fault: row for row in MATRIX}
    for fault, (_m, _a, rule_id, reason) in LABORATORY_DETECTION.items():
        evidence = by_fault[fault].evidence
        assert f"`laboratory/{fault}.json`" in evidence
        assert rule_id in evidence
        assert f"`{reason.value}`" in evidence
        assert by_fault[fault].missing == _LAB_MISSING


def test_a_laboratory_fault_its_declared_assertion_misses_is_disclosed() -> None:
    """A row may not count a detection its declared assertion does not make.

    F-020's library row names A-027, and the only mechanism for A-027 here
    passes over the faulted fixture: what reports the fault is the A-028/A-030
    flag predicate, and only because the fixture left a flag the moved bounds
    contradict. That is disclosable, not countable in silence, so the docs/09
    corpus status section has to name the fault, the assertion its row
    declares, the assertions that actually fire, and the predicate that
    passes over the faulted fixture. The set is derived here rather than
    read from the prose, so a new laboratory row of this shape fails until
    it is disclosed too.
    """

    section = _corpus_status_section()
    reported_elsewhere = []
    for fault, (_mutation, assertion, rule_id, _reason) in LABORATORY_DETECTION.items():
        declared = frozenset(assertion.split("/"))
        if declared & LABORATORY_RULE_ASSERTIONS[rule_id]:
            continue
        reported_elsewhere.append(fault)
        passing = sorted(
            item.predicate.value
            for item in _laboratory_outcomes(LABORATORY / f"{fault}.json")
            if item.status is OutcomeStatus.PASSED
            and declared & LABORATORY_RULE_ASSERTIONS[item.rule_id]
        )
        assert passing, fault
        for phrase in (
            fault,
            *sorted(declared),
            *sorted(LABORATORY_RULE_ASSERTIONS[rule_id]),
            *passing,
        ):
            assert phrase in section, (fault, phrase)
    assert reported_elsewhere == list(REPORTED_BY_ANOTHER_ASSERTION)


def test_no_laboratory_fixture_carries_a_real_analyte_unit_or_range() -> None:
    """Every token in the laboratory corpus is invented for software tests."""

    for path in (*LABORATORY_FILES, *LABORATORY_CLEAN_FILES):
        for result in _load(path)["results"]["results"]:
            assert result["analyte_code"].startswith("fixture-analyte-")
            assert result["unit"].startswith("fixture-unit-")
            assert result["order_id"].startswith("ORDER-CSYN-")
            assert result["specimen_id"].startswith("CSYN-SPEC-")
