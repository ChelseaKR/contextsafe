"""The receipt delta (B-037): strict parsing, fail-closed compatibility, and
the pure, order-independent comparison behind ``contextsafe receipt diff``.

Three properties carry the weight here. ``diff(A, A)`` is all-unchanged, the
delta is invariant under any reordering of either receipt's results, and
swapping the two inputs mirrors the delta exactly — the last of which is the
machine-checkable form of "the tool does not know which run came first".
Everything else is the fail-closed boundary: a document that is not exactly
the published receipt shape, or a pair that does not describe the same thing,
is rejected as a whole and the rejection names a category and a location,
never a value.
"""

from __future__ import annotations

import json
import random
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from contextsafe.canonical import canonical_json, sha256_json
from contextsafe.cli import EXIT_CONTRACT_ERROR, EXIT_SUCCESS, EXIT_USAGE_ERROR, main
from contextsafe.errors import ContextSafeError
from contextsafe.evaluator import evaluate
from contextsafe.eventlog import LOG_FILE_NAME
from contextsafe.models import Checkpoint, ConceptKind, OutcomeReason, OutcomeStatus
from contextsafe.receipt import build_receipt_document
from contextsafe.receipt_delta import (
    DELTA_LIMITATIONS,
    DELTA_SCHEMA_VERSION,
    IncompatibleField,
    ParsedReceipt,
    ReceiptResult,
    RuleChange,
    check_compatible,
    diff_receipts,
    parse_receipt_document,
)
from contextsafe.reference_fixtures import REFERENCE_ROOT
from contextsafe.validation import parse_bundle

Document = dict[str, Any]
Mutation = Callable[[Document], None]

_CANARY_CASE = "CTP-ZZZCANARY"
"""A grammar-valid case identifier that must never appear in a rejection."""


def _document(
    case_json: Document, observations_json: Document, rules_json: Document
) -> Document:
    bundle = parse_bundle(case_json, observations_json, rules_json)
    return build_receipt_document(bundle, evaluate(bundle))


def _refresh(document: Document) -> Document:
    """Recompute the payload hash after a deliberate payload edit."""

    document["payload_sha256"] = sha256_json(document["payload"])
    return document


@pytest.fixture
def before(
    case_json: Document, observations_json: Document, rules_json: Document
) -> Document:
    """The reference receipt: five passes."""

    return _document(case_json, observations_json, rules_json)


@pytest.fixture
def after(
    case_json: Document, observations_json: Document, rules_json: Document
) -> Document:
    """The same case and rules with one pronoun observation contradicted."""

    observations_json["observations"][4]["value"]["value"] = "ze/hir"
    return _document(case_json, observations_json, rules_json)


@pytest.fixture
def missing(
    case_json: Document, observations_json: Document, rules_json: Document
) -> Document:
    """The same case and rules with the pronoun observation absent."""

    del observations_json["observations"][4]
    return _document(case_json, observations_json, rules_json)


def _write(path: Path, document: Document) -> Path:
    path.write_bytes(canonical_json(document).encode("utf-8") + b"\n")
    return path


def _diff_args(before_path: Path, after_path: Path) -> list[str]:
    return ["receipt", "diff", "--before", str(before_path), "--after", str(after_path)]


# --- parsing -----------------------------------------------------------------


def test_the_emitted_receipt_parses_to_its_own_outcomes(
    before: Document,
    case_json: Document,
    observations_json: Document,
    rules_json: Document,
) -> None:
    parsed = parse_receipt_document(before)
    bundle = parse_bundle(case_json, observations_json, rules_json)
    outcomes = {item.rule_id: item for item in evaluate(bundle)}
    assert parsed.case_id == before["payload"]["case_id"]
    assert parsed.payload_sha256 == before["payload_sha256"]
    assert parsed.rule_set_sha256 == before["payload"]["hashes"]["rule_set_sha256"]
    assert {item.rule_id for item in parsed.results} == set(outcomes)
    for item in parsed.results:
        assert item.status is outcomes[item.rule_id].status
        assert item.reason is outcomes[item.rule_id].reason
        assert item.evidence_sha256s == outcomes[item.rule_id].evidence_sha256s


def _set_unknown(path: tuple[str | int, ...]) -> Mutation:
    def mutate(document: Document) -> None:
        target: Any = document
        for key in path:
            target = target[key]
        target["contextsafe_extension"] = "unreviewed"

    return mutate


def _delete(path: tuple[str | int, ...], key: str) -> Mutation:
    def mutate(document: Document) -> None:
        target: Any = document
        for part in path:
            target = target[part]
        del target[key]

    return mutate


def _set(path: tuple[str | int, ...], key: str, value: object) -> Mutation:
    def mutate(document: Document) -> None:
        target: Any = document
        for part in path:
            target = target[part]
        target[key] = value

    return mutate


_REJECTIONS: list[tuple[str, Mutation, str, str]] = [
    ("unknown-root", _set_unknown(()), "unknown_field", "$"),
    ("unknown-envelope", _set_unknown(("envelope",)), "unknown_field", "$.envelope"),
    ("unknown-payload", _set_unknown(("payload",)), "unknown_field", "$.payload"),
    (
        "unknown-hashes",
        _set_unknown(("payload", "hashes")),
        "unknown_field",
        "$.payload.hashes",
    ),
    (
        "unknown-scope",
        _set_unknown(("payload", "scope")),
        "unknown_field",
        "$.payload.scope",
    ),
    (
        "unknown-summary",
        _set_unknown(("payload", "summary")),
        "unknown_field",
        "$.payload.summary",
    ),
    (
        "unknown-result",
        _set_unknown(("payload", "results", 0)),
        "unknown_field",
        "$.payload.results[0]",
    ),
    ("missing-envelope", _delete((), "envelope"), "missing_field", "$.envelope"),
    (
        "missing-results",
        _delete(("payload",), "results"),
        "missing_field",
        "$.payload.results",
    ),
    (
        "document-version",
        _set((), "schema_version", "contextsafe.receipt-document/0.2.0"),
        "unsupported_schema",
        "$.schema_version",
    ),
    (
        "payload-version",
        _set(("payload",), "schema_version", "contextsafe.receipt/0.2.0"),
        "unsupported_schema",
        "$.payload.schema_version",
    ),
    (
        "signed-envelope",
        _set(("envelope",), "signature_status", "signed"),
        "invalid_enum",
        "$.envelope.signature_status",
    ),
    (
        "trusted-time",
        _set(("envelope",), "trusted_time", True),
        "invalid_enum",
        "$.envelope.trusted_time",
    ),
    (
        "claimed-time-offset",
        _set(("envelope",), "claimed_generated_at", "2026-08-04T09:30:00+01:00"),
        "invalid_format",
        "$.envelope.claimed_generated_at",
    ),
    (
        "claimed-time-calendar",
        _set(("envelope",), "claimed_generated_at", "2026-02-30T09:30:00Z"),
        "invalid_timestamp",
        "$.envelope.claimed_generated_at",
    ),
    (
        "oracle-approved",
        _set(("payload", "scope"), "clinical_oracle_approved", True),
        "invalid_enum",
        "$.payload.scope.clinical_oracle_approved",
    ),
    (
        "scope-not-boolean",
        _set(("payload", "scope"), "synthetic_fixture_only", 1),
        "invalid_type",
        "$.payload.scope.synthetic_fixture_only",
    ),
    (
        "limitation-dropped",
        lambda document: document["payload"]["limitations"].pop(),
        "invalid_enum",
        "$.payload.limitations",
    ),
    (
        "limitation-reworded",
        _set(
            ("payload", "limitations"),
            0,
            "This evaluation was reviewed and found satisfactory.",
        ),
        "invalid_enum",
        "$.payload.limitations[0]",
    ),
    (
        "summary-overcounted",
        _set(("payload", "summary"), "pass", 6),
        "receipt_inconsistent",
        "$.payload.summary.pass",
    ),
    (
        "summary-boolean",
        _set(("payload", "summary"), "fail", False),
        "invalid_type",
        "$.payload.summary.fail",
    ),
    (
        "summary-negative",
        _set(("payload", "summary"), "fail", -1),
        "invalid_type",
        "$.payload.summary.fail",
    ),
    (
        "runner-version",
        _set(("payload",), "runner_version", "1.0"),
        "invalid_format",
        "$.payload.runner_version",
    ),
    (
        "case-id",
        _set(("payload",), "case_id", "not a case"),
        "invalid_format",
        "$.payload.case_id",
    ),
    (
        "hash-uppercase",
        _set(("payload", "hashes"), "rule_set_sha256", "A" * 64),
        "invalid_format",
        "$.payload.hashes.rule_set_sha256",
    ),
    (
        "status-unpublished",
        _set(("payload", "results", 0), "status", "passed"),
        "invalid_enum",
        "$.payload.results[0].status",
    ),
    (
        "reason-unpublished",
        _set(("payload", "results", 0), "reason", "looked fine"),
        "invalid_enum",
        "$.payload.results[0].reason",
    ),
    (
        "checkpoint-unpublished",
        _set(("payload", "results", 0), "checkpoint", "pharmacy"),
        "invalid_enum",
        "$.payload.results[0].checkpoint",
    ),
    (
        "concept-unpublished",
        _set(("payload", "results", 0), "concept", "sex"),
        "invalid_enum",
        "$.payload.results[0].concept",
    ),
    (
        "rule-id-shape",
        _set(("payload", "results", 0), "rule_id", "A-001"),
        "invalid_format",
        "$.payload.results[0].rule_id",
    ),
    (
        "evidence-hash-shape",
        _set(("payload", "results", 0), "evidence_sha256s", ["not-a-hash"]),
        "invalid_format",
        "$.payload.results[0].evidence_sha256s[0]",
    ),
    (
        "observed-not-array",
        _set(("payload", "results", 0), "observed_sha256s", "0" * 64),
        "invalid_type",
        "$.payload.results[0].observed_sha256s",
    ),
    (
        "results-empty",
        _set(("payload",), "results", []),
        "invalid_type",
        "$.payload.results",
    ),
    (
        "results-not-array",
        _set(("payload",), "results", {}),
        "invalid_type",
        "$.payload.results",
    ),
    (
        "envelope-not-object",
        _set((), "envelope", []),
        "invalid_type",
        "$.envelope",
    ),
]


@pytest.mark.parametrize(
    ("mutate", "code", "path"),
    [(m, c, p) for _, m, c, p in _REJECTIONS],
    ids=[name for name, *_ in _REJECTIONS],
)
def test_a_document_off_the_published_shape_is_rejected_whole(
    before: Document, mutate: Mutation, code: str, path: str
) -> None:
    """Fail closed: nothing is stripped, normalized, or compared anyway."""

    mutate(before)
    _refresh(before)
    with pytest.raises(ContextSafeError) as raised:
        parse_receipt_document(before)
    assert raised.value.code == code
    assert raised.value.path == path


def test_a_payload_hash_that_does_not_cover_the_payload_is_rejected(
    before: Document,
) -> None:
    """A delta that named a hash which did not cover its input would lie."""

    before["payload"]["summary"]["pass"] -= 1
    before["payload"]["results"].pop()
    with pytest.raises(ContextSafeError) as raised:
        parse_receipt_document(before)
    assert raised.value.code == "receipt_inconsistent"
    assert raised.value.path == "$.payload_sha256"


def test_a_duplicated_rule_identifier_is_rejected(before: Document) -> None:
    results = before["payload"]["results"]
    results.append(dict(results[0]))
    before["payload"]["summary"]["pass"] += 1
    _refresh(before)
    with pytest.raises(ContextSafeError) as raised:
        parse_receipt_document(before)
    assert raised.value.code == "duplicate_rule_id"
    assert raised.value.path == "$.payload.results"


@pytest.mark.parametrize("document", [None, [], "receipt", 7])
def test_a_non_object_document_is_rejected(document: Any) -> None:
    with pytest.raises(ContextSafeError) as raised:
        parse_receipt_document(document)
    assert raised.value.code == "invalid_type"
    assert raised.value.path == "$"


def test_the_path_prefix_says_which_document_and_nothing_else(
    before: Document,
) -> None:
    before["payload"]["case_id"] = _CANARY_CASE
    before["payload"]["results"][0]["reason"] = "looked fine"
    _refresh(before)
    with pytest.raises(ContextSafeError) as raised:
        parse_receipt_document(before, path="$.after")
    assert raised.value.path == "$.after.payload.results[0].reason"
    assert _CANARY_CASE not in str(raised.value)
    assert "looked fine" not in str(raised.value)


def test_an_unknown_field_name_is_never_echoed(before: Document) -> None:
    before["payload"]["person@example.invalid"] = True
    _refresh(before)
    with pytest.raises(ContextSafeError) as raised:
        parse_receipt_document(before)
    assert raised.value.code == "unknown_field"
    assert "example.invalid" not in str(raised.value)


# --- compatibility -----------------------------------------------------------


def _incompatible(before: Document, after: Document) -> ContextSafeError:
    with pytest.raises(ContextSafeError) as raised:
        diff_receipts(parse_receipt_document(before), parse_receipt_document(after))
    assert raised.value.code == "incompatible_receipts"
    return raised.value


def test_a_different_case_is_incompatible_and_unnamed(
    before: Document, after: Document
) -> None:
    after["payload"]["case_id"] = _CANARY_CASE
    _refresh(after)
    error = _incompatible(before, after)
    assert error.path == "$.payload.case_id"
    assert IncompatibleField.CASE_ID.value in error.message
    assert _CANARY_CASE not in str(error)
    assert before["payload"]["case_id"] not in str(error)


def test_a_different_rule_set_hash_is_incompatible(
    before: Document, after: Document
) -> None:
    after["payload"]["hashes"]["rule_set_sha256"] = "f" * 64
    _refresh(after)
    error = _incompatible(before, after)
    assert error.path == "$.payload.hashes.rule_set_sha256"
    assert "f" * 64 not in str(error)


def test_a_different_concept_set_is_incompatible(
    before: Document, after: Document
) -> None:
    after["payload"]["results"][0]["concept"] = ConceptKind.PRONOUNS.value
    _refresh(after)
    error = _incompatible(before, after)
    assert error.path == "$.payload.results[].concept"
    assert IncompatibleField.CONCEPT_SET.value in error.message


def test_a_different_checkpoint_set_is_incompatible(
    before: Document, after: Document
) -> None:
    for result in after["payload"]["results"]:
        result["checkpoint"] = Checkpoint.LIS_RETURN.value
    _refresh(after)
    error = _incompatible(before, after)
    assert error.path == "$.payload.results[].checkpoint"


def test_a_different_rule_identifier_set_is_incompatible(
    before: Document, after: Document
) -> None:
    after["payload"]["results"][0]["rule_id"] = "A-I99"
    _refresh(after)
    error = _incompatible(before, after)
    assert error.path == "$.payload.results[].rule_id"
    assert "A-I99" not in str(error)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("rule_version", "0.2.0"),
        ("expected_sha256", "e" * 64),
        ("case_id", "CTP-I02"),
    ],
)
def test_a_rule_bound_differently_is_incompatible(
    before: Document, after: Document, field: str, value: str
) -> None:
    """Same rule-set hash, different binding: the receipt contradicts itself."""

    after["payload"]["results"][0][field] = value
    _refresh(after)
    error = _incompatible(before, after)
    assert error.path == "$.payload.results[]"
    assert value not in str(error)


def test_compatibility_is_reported_in_a_fixed_order(
    before: Document, after: Document
) -> None:
    """The same pair always yields the same rejection, whatever else differs."""

    after["payload"]["case_id"] = "CTP-I02"
    after["payload"]["hashes"]["rule_set_sha256"] = "f" * 64
    after["payload"]["results"][0]["rule_id"] = "A-I99"
    _refresh(after)
    assert _incompatible(before, after).path == "$.payload.case_id"


def test_check_compatible_accepts_a_receipt_against_itself(before: Document) -> None:
    parsed = parse_receipt_document(before)
    check_compatible(parsed, parsed)


# --- the delta ---------------------------------------------------------------


def test_diff_of_a_receipt_against_itself_is_all_unchanged(before: Document) -> None:
    parsed = parse_receipt_document(before)
    delta = diff_receipts(parsed, parsed).to_dict()
    assert delta["schema_version"] == DELTA_SCHEMA_VERSION
    assert delta["summary"] == {
        "changed_other": 0,
        "improved": 0,
        "regressed": 0,
        "unchanged": 5,
    }
    assert delta["receipts"] == {
        "after": {"payload_sha256": before["payload_sha256"]},
        "before": {"payload_sha256": before["payload_sha256"]},
    }
    assert delta["runner_version_changed"] is False
    assert delta["limitations"] == list(DELTA_LIMITATIONS)
    for rule in delta["rules"]:
        assert rule["change"] == "unchanged"
        assert rule["changed"] is False
        assert rule["evidence_sha256s_changed"] is False


def test_a_pass_that_becomes_a_fail_is_a_regression(
    before: Document, after: Document
) -> None:
    delta = diff_receipts(
        parse_receipt_document(before), parse_receipt_document(after)
    ).to_dict()
    assert delta["summary"] == {
        "changed_other": 0,
        "improved": 0,
        "regressed": 1,
        "unchanged": 4,
    }
    (regressed,) = [rule for rule in delta["rules"] if rule["changed"]]
    assert regressed["change"] == "regressed"
    assert regressed["status_before"] == "pass"
    assert regressed["status_after"] == "fail"
    assert regressed["reason_before"] == "affirmative_evidence_match"
    assert regressed["reason_after"] == "semantic_mismatch"
    # The contradicting observation keeps its evidence pointer; only the value
    # hash moved, and the delta does not copy value hashes through.
    assert regressed["evidence_sha256s_changed"] is False
    assert delta["receipts"]["before"]["payload_sha256"] == before["payload_sha256"]
    assert delta["receipts"]["after"]["payload_sha256"] == after["payload_sha256"]


def test_a_pass_that_becomes_indeterminate_is_a_regression(
    before: Document, missing: Document
) -> None:
    delta = diff_receipts(
        parse_receipt_document(before), parse_receipt_document(missing)
    ).to_dict()
    assert delta["summary"]["regressed"] == 1
    (regressed,) = [rule for rule in delta["rules"] if rule["changed"]]
    assert regressed["status_after"] == "indeterminate"
    assert regressed["reason_after"] == "missing_evidence"
    assert regressed["evidence_sha256s_changed"] is True


def test_swapping_the_inputs_mirrors_the_delta(
    before: Document, after: Document
) -> None:
    """The tool has no trusted time; before and after are the caller's words."""

    forward = diff_receipts(
        parse_receipt_document(before), parse_receipt_document(after)
    ).to_dict()
    backward = diff_receipts(
        parse_receipt_document(after), parse_receipt_document(before)
    ).to_dict()
    assert backward["summary"]["improved"] == forward["summary"]["regressed"]
    assert backward["summary"]["regressed"] == forward["summary"]["improved"]
    assert backward["receipts"]["before"] == forward["receipts"]["after"]
    for one, other in zip(forward["rules"], backward["rules"], strict=True):
        assert one["status_before"] == other["status_after"]
        assert one["reason_before"] == other["reason_after"]


def test_a_reason_change_under_the_same_status_is_changed_other(
    missing: Document,
) -> None:
    ambiguous = json.loads(canonical_json(missing))
    for result in ambiguous["payload"]["results"]:
        if result["status"] == "indeterminate":
            result["reason"] = OutcomeReason.AMBIGUOUS_EVIDENCE.value
    _refresh(ambiguous)
    delta = diff_receipts(
        parse_receipt_document(missing), parse_receipt_document(ambiguous)
    ).to_dict()
    assert delta["summary"]["changed_other"] == 1
    (changed,) = [rule for rule in delta["rules"] if rule["changed"]]
    assert changed["status_before"] == changed["status_after"] == "indeterminate"
    assert changed["evidence_sha256s_changed"] is False


def test_a_runner_version_change_is_flagged_not_named(
    before: Document, after: Document
) -> None:
    after["payload"]["runner_version"] = "9.9.9"
    _refresh(after)
    delta = diff_receipts(
        parse_receipt_document(before), parse_receipt_document(after)
    ).to_dict()
    assert delta["runner_version_changed"] is True
    assert "9.9.9" not in canonical_json(delta)


def test_the_delta_carries_no_expected_observed_or_envelope_value(
    before: Document, after: Document
) -> None:
    """Value minimization: rule identifiers, closed codes, counts, two hashes."""

    after["envelope"]["claimed_generated_at"] = "2026-08-04T09:30:00Z"
    rendered = canonical_json(
        diff_receipts(
            parse_receipt_document(before), parse_receipt_document(after)
        ).to_dict()
    )
    assert "2026-08-04" not in rendered
    assert "claimed_generated_at" not in rendered
    assert "signature_status" not in rendered
    for result in [*before["payload"]["results"], *after["payload"]["results"]]:
        assert result["expected_sha256"] not in rendered
        for digest in [*result["observed_sha256s"], *result["evidence_sha256s"]]:
            assert digest not in rendered


# --- property tests ----------------------------------------------------------

_HEX = st.binary(min_size=32, max_size=32).map(bytes.hex)
_STATUS = st.sampled_from(tuple(OutcomeStatus))
_REASON = st.sampled_from(tuple(OutcomeReason))
_FAILURES = frozenset(
    {OutcomeStatus.FAIL, OutcomeStatus.INDETERMINATE, OutcomeStatus.BLOCKED}
)


@st.composite
def _results(draw: st.DrawFn) -> tuple[ReceiptResult, ...]:
    indices = draw(st.lists(st.integers(0, 99), min_size=1, max_size=8, unique=True))
    results = []
    for index in indices:
        results.append(
            ReceiptResult(
                rule_id=f"A-I{index:02d}",
                rule_version="0.1.0",
                case_id="CTP-P01",
                checkpoint=draw(st.sampled_from(tuple(Checkpoint))).value,
                concept=draw(st.sampled_from(tuple(ConceptKind))).value,
                status=draw(_STATUS),
                reason=draw(_REASON),
                expected_sha256=draw(_HEX),
                observed_sha256s=tuple(draw(st.lists(_HEX, max_size=2))),
                evidence_sha256s=tuple(draw(st.lists(_HEX, max_size=2))),
            )
        )
    return tuple(results)


@st.composite
def _receipt_pairs(draw: st.DrawFn) -> tuple[ParsedReceipt, ParsedReceipt]:
    """Two compatible receipts: same bindings, independently drawn outcomes."""

    results = draw(_results())
    rule_set = draw(_HEX)
    rerun = tuple(
        ReceiptResult(
            rule_id=item.rule_id,
            rule_version=item.rule_version,
            case_id=item.case_id,
            checkpoint=item.checkpoint,
            concept=item.concept,
            status=draw(_STATUS),
            reason=draw(_REASON),
            expected_sha256=item.expected_sha256,
            observed_sha256s=tuple(draw(st.lists(_HEX, max_size=2))),
            evidence_sha256s=tuple(draw(st.lists(_HEX, max_size=2))),
        )
        for item in results
    )
    return (
        ParsedReceipt(
            case_id="CTP-P01",
            rule_set_sha256=rule_set,
            runner_version="0.1.0",
            payload_sha256=draw(_HEX),
            results=results,
        ),
        ParsedReceipt(
            case_id="CTP-P01",
            rule_set_sha256=rule_set,
            runner_version=draw(st.sampled_from(("0.1.0", "0.2.0"))),
            payload_sha256=draw(_HEX),
            results=rerun,
        ),
    )


def _shuffled(receipt: ParsedReceipt, seed: random.Random) -> ParsedReceipt:
    results = list(receipt.results)
    seed.shuffle(results)
    return ParsedReceipt(
        case_id=receipt.case_id,
        rule_set_sha256=receipt.rule_set_sha256,
        runner_version=receipt.runner_version,
        payload_sha256=receipt.payload_sha256,
        results=tuple(results),
    )


@settings(max_examples=200, deadline=None)
@given(pair=_receipt_pairs())
def test_diff_of_any_receipt_against_itself_is_all_unchanged(
    pair: tuple[ParsedReceipt, ParsedReceipt],
) -> None:
    receipt, _ = pair
    delta = diff_receipts(receipt, receipt)
    assert delta.summary() == {
        "changed_other": 0,
        "improved": 0,
        "regressed": 0,
        "unchanged": len(receipt.results),
    }
    assert all(rule.change is RuleChange.UNCHANGED for rule in delta.rules)
    assert not any(rule.changed for rule in delta.rules)
    assert not any(rule.evidence_sha256s_changed for rule in delta.rules)
    assert delta.runner_version_changed is False


@settings(max_examples=200, deadline=None)
@given(pair=_receipt_pairs(), seed=st.randoms(use_true_random=False))
def test_the_delta_is_invariant_under_reordering_of_results(
    pair: tuple[ParsedReceipt, ParsedReceipt], seed: random.Random
) -> None:
    before, after = pair
    expected = diff_receipts(before, after).to_dict()
    shuffled = diff_receipts(_shuffled(before, seed), _shuffled(after, seed))
    assert shuffled.to_dict() == expected
    assert [rule["rule_id"] for rule in expected["rules"]] == sorted(
        rule["rule_id"] for rule in expected["rules"]
    )


@settings(max_examples=200, deadline=None)
@given(pair=_receipt_pairs())
def test_every_rule_lands_in_exactly_one_count_with_the_published_meaning(
    pair: tuple[ParsedReceipt, ParsedReceipt],
) -> None:
    before, after = pair
    delta = diff_receipts(before, after)
    assert sum(delta.summary().values()) == len(delta.rules)
    before_rules = before.by_rule()
    after_rules = after.by_rule()
    for rule in delta.rules:
        one, other = before_rules[rule.rule_id], after_rules[rule.rule_id]
        same = one.status is other.status and one.reason is other.reason
        assert rule.changed is (not same)
        assert (rule.change is RuleChange.UNCHANGED) is same
        if one.status is OutcomeStatus.PASSED and other.status in _FAILURES:
            assert rule.change is RuleChange.REGRESSED
        elif one.status in _FAILURES and other.status is OutcomeStatus.PASSED:
            assert rule.change is RuleChange.IMPROVED
        elif not same:
            assert rule.change is RuleChange.CHANGED_OTHER
        assert rule.evidence_sha256s_changed is (
            sorted(one.evidence_sha256s) != sorted(other.evidence_sha256s)
        )


@settings(max_examples=200, deadline=None)
@given(pair=_receipt_pairs())
def test_swapping_any_pair_mirrors_the_delta(
    pair: tuple[ParsedReceipt, ParsedReceipt],
) -> None:
    before, after = pair
    forward = diff_receipts(before, after)
    backward = diff_receipts(after, before)
    assert forward.summary()["regressed"] == backward.summary()["improved"]
    assert forward.summary()["improved"] == backward.summary()["regressed"]
    assert forward.summary()["unchanged"] == backward.summary()["unchanged"]
    assert forward.before_payload_sha256 == backward.after_payload_sha256


@settings(max_examples=200, deadline=None)
@given(pair=_receipt_pairs())
def test_no_generated_hash_but_the_two_payload_hashes_reaches_the_delta(
    pair: tuple[ParsedReceipt, ParsedReceipt],
) -> None:
    before, after = pair
    rendered = canonical_json(diff_receipts(before, after).to_dict())
    reported = {before.payload_sha256, after.payload_sha256, before.rule_set_sha256}
    for receipt in (before, after):
        for item in receipt.results:
            digests = {
                item.expected_sha256,
                *item.observed_sha256s,
                *item.evidence_sha256s,
            }
            for digest in digests - reported:
                assert digest not in rendered


def _reference_document() -> Document:
    """A fresh reference receipt, read from the packaged fixtures each time."""

    def read(name: str) -> Document:
        value = json.loads((REFERENCE_ROOT / name).read_text(encoding="utf-8"))
        assert isinstance(value, dict)
        return value

    return json.loads(
        canonical_json(
            _document(read("case.json"), read("observations.json"), read("rules.json"))
        )
    )


@settings(max_examples=50, deadline=None)
@given(seed=st.randoms(use_true_random=False))
def test_reordering_a_document_changes_only_the_hashes_it_reports(
    seed: random.Random,
) -> None:
    """At the document level, order changes the payload hash and nothing else."""

    original = _reference_document()
    reordered = _reference_document()
    seed.shuffle(reordered["payload"]["results"])
    _refresh(reordered)
    expected = diff_receipts(
        parse_receipt_document(original), parse_receipt_document(original)
    ).to_dict()
    actual = diff_receipts(
        parse_receipt_document(reordered), parse_receipt_document(reordered)
    ).to_dict()
    assert actual["rules"] == expected["rules"]
    assert actual["summary"] == expected["summary"]


# --- the command -------------------------------------------------------------


def test_the_command_writes_the_delta_and_prints_nothing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    before: Document,
    after: Document,
) -> None:
    before_path = _write(tmp_path / "before.json", before)
    after_path = _write(tmp_path / "after.json", after)
    output = tmp_path / "delta.json"
    assert (
        main([*_diff_args(before_path, after_path), "--output", str(output)])
        == EXIT_SUCCESS
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
    raw = output.read_bytes()
    assert raw.endswith(b"\n")
    assert raw.count(b"\n") == 1
    delta = json.loads(raw.decode("utf-8"))
    assert delta["schema_version"] == DELTA_SCHEMA_VERSION
    assert delta["summary"]["regressed"] == 1
    assert (
        delta
        == diff_receipts(
            parse_receipt_document(before), parse_receipt_document(after)
        ).to_dict()
    )


def test_the_command_prints_the_same_bytes_without_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], before: Document
) -> None:
    path = _write(tmp_path / "receipt.json", before)
    output = tmp_path / "delta.json"
    assert main([*_diff_args(path, path), "--output", str(output)]) == EXIT_SUCCESS
    assert main(_diff_args(path, path)) == EXIT_SUCCESS
    captured = capsys.readouterr()
    assert captured.out.encode("utf-8") == output.read_bytes()
    assert captured.err == ""


def test_quiet_suppresses_stdout_and_keeps_the_artifact(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], before: Document
) -> None:
    path = _write(tmp_path / "receipt.json", before)
    output = tmp_path / "delta.json"
    assert (
        main([*_diff_args(path, path), "--quiet", "--output", str(output)])
        == EXIT_SUCCESS
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
    assert json.loads(output.read_text(encoding="utf-8"))["summary"]["unchanged"] == 5


def test_an_incompatible_pair_exits_two_with_one_error_object(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    before: Document,
    after: Document,
) -> None:
    after["payload"]["case_id"] = _CANARY_CASE
    _refresh(after)
    before_path = _write(tmp_path / "before.json", before)
    after_path = _write(tmp_path / "after.json", after)
    output = tmp_path / "delta.json"
    assert (
        main([*_diff_args(before_path, after_path), "--output", str(output)])
        == EXIT_CONTRACT_ERROR
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert not output.exists()
    error = json.loads(captured.err)["error"]
    assert set(error) == {"code", "message", "path"}
    assert error["code"] == "incompatible_receipts"
    assert error["path"] == "$.payload.case_id"
    assert _CANARY_CASE not in captured.err
    assert "CTP-I01" not in captured.err


def test_a_malformed_after_document_is_located_without_being_quoted(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    before: Document,
    after: Document,
) -> None:
    after["payload"]["results"][0]["status"] = "looked fine to me"
    _refresh(after)
    before_path = _write(tmp_path / "before.json", before)
    after_path = _write(tmp_path / "after.json", after)
    assert main(_diff_args(before_path, after_path)) == EXIT_CONTRACT_ERROR
    captured = capsys.readouterr()
    error = json.loads(captured.err)["error"]
    assert error["code"] == "invalid_enum"
    assert error["path"] == "$.after.payload.results[0].status"
    assert "looked fine" not in captured.err


def test_an_unreadable_or_oversized_input_fails_closed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], before: Document
) -> None:
    path = _write(tmp_path / "receipt.json", before)
    assert main(_diff_args(tmp_path / "missing.json", path)) == EXIT_CONTRACT_ERROR
    assert json.loads(capsys.readouterr().err)["error"]["code"] == "input_io_error"
    large = tmp_path / "large.json"
    large.write_bytes(b" " * 1_048_577)
    assert main(_diff_args(path, large)) == EXIT_CONTRACT_ERROR
    assert json.loads(capsys.readouterr().err)["error"]["code"] == "input_too_large"


def test_an_output_failure_is_reported(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], before: Document
) -> None:
    path = _write(tmp_path / "receipt.json", before)
    assert (
        main([*_diff_args(path, path), "--output", str(tmp_path)])
        == EXIT_CONTRACT_ERROR
    )
    assert json.loads(capsys.readouterr().err)["error"]["code"] == "output_io_error"


def test_the_log_records_the_receipt_command_by_its_closed_name(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], before: Document
) -> None:
    path = _write(tmp_path / "receipt.json", before)
    log_dir = tmp_path / "logs"
    assert (
        main([*_diff_args(path, path), "--quiet", "--log-dir", str(log_dir)])
        == EXIT_SUCCESS
    )
    assert (
        main([*_diff_args(path, tmp_path / "missing.json"), "--log-dir", str(log_dir)])
        == EXIT_CONTRACT_ERROR
    )
    capsys.readouterr()
    lines = (log_dir / LOG_FILE_NAME).read_text(encoding="utf-8").splitlines()
    records = [json.loads(line) for line in lines]
    assert [record["command"] for record in records] == ["receipt", "receipt"]
    assert [record["outcome"] for record in records] == ["accepted", "rejected"]
    assert records[1]["error_code"] == "input_io_error"
    assert str(path) not in "".join(lines)


def test_no_color_is_accepted_and_output_carries_no_escape(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], before: Document
) -> None:
    path = _write(tmp_path / "receipt.json", before)
    assert main([*_diff_args(path, path), "--no-color"]) == EXIT_SUCCESS
    captured = capsys.readouterr()
    assert "\x1b" not in captured.out
    assert "\x1b" not in captured.err


@pytest.mark.parametrize(
    "argv",
    [
        ["receipt"],
        ["receipt", "diff"],
        ["receipt", "diff", "--before", "a.json"],
        ["receipt", "verify", "--receipt", "a.json"],
    ],
)
def test_usage_errors_exit_with_the_dedicated_code(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(argv)
    assert raised.value.code == EXIT_USAGE_ERROR
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "error:" in captured.err


def test_the_help_says_the_labels_prove_no_order(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["receipt", "diff", "--help"])
    assert raised.value.code == 0
    assert "which run came first" in capsys.readouterr().out
