"""Near-miss, log, and crash-output canaries for the privacy boundary.

B-039 asks for a direct-identifier, Unicode, free-text, near-miss, log, and
crash-dump canary suite, and RG-12 requires that logs, crash output,
diagnostics, and support bundles carry no prohibited field. The
direct-identifier, Unicode, and free-text rejections themselves are covered by
``tests/test_preflight.py``. This module adds the three parts that were
missing: where the detector's boundary actually falls in both directions, that
nothing is ever logged, and that an unexpected crash carries neither evidence
content nor the caller's source path.

The near-miss matrix pins observed behavior rather than asserting a desired
detector. Tuning the patterns is a security-owned decision with an independent
review attached (B-039, SEC), so the blind spots below are recorded as tested
facts for that review, not approved behavior. B-039 is not closed: the
independent security review has not happened, and the diagnostics, support
bundle, and local logs those gates also cover do not exist yet (B-046).
"""

import json
import re
import sqlite3
import traceback
from pathlib import Path
from typing import Any

import jsonschema
import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

import contextsafe.preflight as preflight_module
from contextsafe.cli import main
from contextsafe.contract_validation import (
    PROVENANCE_LABEL_GRAMMAR,
    PROVENANCE_SYSTEM_GRAMMAR,
    PROVENANCE_VERSION_GRAMMAR,
    Grammar,
)
from contextsafe.errors import ContextSafeError
from contextsafe.evidence import (
    CANONICAL_JSON_MEDIA_TYPE,
    CANONICAL_JSON_SOURCE_TYPE,
    EvidenceMetadata,
    EvidenceScope,
    parse_evidence_metadata,
)
from contextsafe.evidence_store import store_internal_synthetic_evidence
from contextsafe.identifiers import (
    DETECTORS,
    PROVENANCE_EXEMPT_DETECTORS,
    provenance_hits,
)
from contextsafe.plan import ExecutionPlan
from contextsafe.preflight import preflight_source

ROOT = Path(__file__).resolve().parents[1]
SOURCE_MODULES = tuple(sorted((ROOT / "src" / "contextsafe").glob("*.py")))
EVIDENCE_SCHEMA: dict[str, Any] = json.loads(
    (ROOT / "schemas" / "contextsafe-evidence-v1.schema.json").read_text(
        encoding="utf-8"
    )
)

_LEAK_CANARY = "CSYN-LEAKCANARY-ZQXJ"
"""A grammar-valid synthetic code used to trace content through the boundary."""

_ACCEPTED_NEAR_MISSES = (
    "CSYN-PRONOUN-THEY-THEM",
    "CSYN-1234",
    "CSYN-123456",
    "CSYN-A.B:C_D-E",
    "CSYN-HTTPS",
)
"""Approved-shape codes that resemble identifiers and must still be accepted."""

_REJECTED_NEAR_MISSES = (
    ("CSYN-1234567", "direct_identifier_detected"),
    ("CSYN-MRN-CODE", "direct_identifier_detected"),
    ("CSYN-ACCOUNT-1234", "direct_identifier_detected"),
    ("CSYN-2026-07-14", "direct_identifier_detected"),
    ("CSYN-415-555-0199", "direct_identifier_detected"),
    ("CSYN-123-45-6789", "direct_identifier_detected"),
    ("CSYN-WWW.EXAMPLE", "direct_identifier_detected"),
    ("PATIENT-CODE-9", "unapproved_free_text"),
    ("csyn-lower", "unapproved_free_text"),
    ("CSYN-CODÉ", "unapproved_free_text"),
)
"""Values one character from acceptable that must fail, and the code they fail with."""

_ACCEPTED_PROVENANCE = (
    ("collector_id", "TEST-COLLECTOR"),
    ("collector_id", "collector.staging_v02"),
    ("collector_id", "SYS-MEDICAL-RECORD-EXPORT"),
    ("system_id", "SYS-STAGING-EHR"),
    ("system_id", "SYS-MEDICAL-RECORD-SYSTEM"),
    ("system_id", "EPIC-V2"),
    ("system_version", "1.0.0"),
    ("system_version", "2026.8.27"),
    ("system_version", "10.2.1-rc.4"),
)
"""Provenance the published schema declares valid and that must be accepted.

PR #38 was closed for rejecting values of this kind. Each of these is checked
against the published schema as well as against the parser, so "the schema says
yes and the code says no" is a test failure rather than a support ticket.
"""

_REJECTED_PROVENANCE = (
    ("collector_id", "realpatientcanary", "phi_canary_detected"),
    ("collector_id", "REAL-PATIENT-CANARY", "phi_canary_detected"),
    ("collector_id", "ctxsafephicanaryalice", "phi_canary_detected"),
    ("system_id", "REALPATIENTCANARY", "phi_canary_detected"),
    ("collector_id", "1987-03-14", "invalid_format"),
    ("collector_id", "123-45-6789", "invalid_format"),
    ("collector_id", "collector-1234567", "invalid_format"),
    ("collector_id", "www.collector.example", "invalid_format"),
    ("collector_id", "https://collector.example/agent", "invalid_format"),
    ("collector_id", "415-555-0199", "invalid_format"),
    ("collector_id", "nurse@example.org", "invalid_format"),
    ("system_id", "EPIC-2026-08-27", "invalid_format"),
    ("system_id", "SYS-1234567", "invalid_format"),
    ("system_id", "MRN-1234567", "invalid_format"),
    ("system_version", "1234567", "invalid_format"),
    ("system_version", "123.456.7890", "invalid_format"),
    ("system_version", "exports-Jordan-Rivera-1987", "invalid_format"),
    ("system_version", "1.0-www.example", "invalid_format"),
    # The shortest canary is seventeen characters and a version prerelease is
    # bounded at sixteen, so the grammar refuses this one before the scan runs.
    ("system_version", "1.0.0-realpatientcanary", "invalid_format"),
)
"""Provenance that must fail closed, and the code it must fail with.

The canary rows are the ones this file exists for: a canary is ordinary
letters, so no grammar excludes it and only content inspection finds it. Every
other row is caught by the grammar before any detector runs, which is the point
of ADR 0006 -- the type is the control and the scan is the second pass.
"""

_DOCUMENTED_PROVENANCE_BLIND_SPOTS = (
    ("collector_id", "MRN-ABCDE", "record-locator does not apply to a bounded token"),
    ("system_id", "ACCOUNT-CODE", "record-locator does not apply to a bounded token"),
)
"""Locator vocabulary the provenance scan deliberately allows through.

``PROVENANCE_EXEMPT_DETECTORS`` names ``record-locator`` and says why: it fires
on ``SYS-MEDICAL-RECORD-SYSTEM``, which is an ordinary system name. What bounds
the residual is the grammar, and these tests assert both halves -- the locator
word next to letters is accepted, and the same word next to a number is not.
"""

_DOCUMENTED_BLIND_SPOTS = (
    ("CSYN-1899-01-02", "date outside the pattern's 19xx/20xx window"),
    ("CSYN-01.02.1980", "date written with dots rather than hyphens"),
    ("CSYN-555-0199", "seven-digit local number without an area code"),
)
"""Identifier-shaped values the scan misses; the synthetic grammar still bounds them."""


def _write_source(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value, separators=(",", ":")), encoding="utf-8")
    return path


def _source_with(
    tmp_path: Path, evidence_source_json: dict[str, Any], value_code: str
) -> Path:
    evidence_source_json["records"][0]["value_code"] = value_code
    return _write_source(tmp_path / "source.json", evidence_source_json)


@pytest.mark.parametrize("value_code", _ACCEPTED_NEAR_MISSES)
def test_approved_codes_that_resemble_identifiers_are_not_false_positives(
    tmp_path: Path,
    evidence_source_json: dict[str, Any],
    evidence_scope: EvidenceScope,
    value_code: str,
) -> None:
    """A boundary check that rejects approved content is a defect, not caution."""

    source = _source_with(tmp_path, evidence_source_json, value_code)
    assert preflight_source(source, evidence_scope).to_dict()["persisted"] is False


@pytest.mark.parametrize(("value_code", "expected_code"), _REJECTED_NEAR_MISSES)
def test_one_character_from_acceptable_still_fails_closed(
    tmp_path: Path,
    evidence_source_json: dict[str, Any],
    evidence_scope: EvidenceScope,
    value_code: str,
    expected_code: str,
) -> None:
    """Both layers hold at the edge: pattern scan first, then the code grammar."""

    source = _source_with(tmp_path, evidence_source_json, value_code)
    with pytest.raises(ContextSafeError) as raised:
        preflight_source(source, evidence_scope)
    assert raised.value.code == expected_code
    assert raised.value.path == "$.records[0].value_code"
    assert value_code not in str(raised.value)


@pytest.mark.parametrize(("value_code", "gap"), _DOCUMENTED_BLIND_SPOTS)
def test_documented_detector_blind_spots_are_pinned_for_security_review(
    tmp_path: Path,
    evidence_source_json: dict[str, Any],
    evidence_scope: EvidenceScope,
    value_code: str,
    gap: str,
) -> None:
    """These pass the pattern scan today, and the README says the scan is fallible.

    Each value is identifier-shaped and still reaches acceptance because the
    direct-identifier patterns do not cover the form named in ``gap``. The
    synthetic-namespace grammar is what actually bounds them: every one still
    has to be a ``CSYN-`` code. Widening the patterns is B-039's security
    decision, so this pins the gap where a reviewer can see it and fails loudly
    if the behavior changes without one.
    """

    assert gap
    source = _source_with(tmp_path, evidence_source_json, value_code)
    assert preflight_source(source, evidence_scope).to_dict()["persisted"] is False
    assert value_code.startswith("CSYN-")


def test_no_module_logs_prints_or_configures_a_handler() -> None:
    """The log canary is structural: there is no logging surface to leak into."""

    assert SOURCE_MODULES
    for module in SOURCE_MODULES:
        text = module.read_text(encoding="utf-8")
        assert re.search(r"^\s*(?:import logging|from logging)", text, re.M) is None
        assert "logging." not in text
        assert re.search(r"(?<![A-Za-z_.])print\(", text) is None


def test_no_command_emits_a_log_record(
    tmp_path: Path,
    evidence_source_json: dict[str, Any],
    execution_plan: ExecutionPlan,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Accepted and rejected runs alike must leave the logging system empty."""

    source = _write_source(tmp_path / "source.json", evidence_source_json)
    plan = _write_source(tmp_path / "plan.json", execution_plan.to_dict())
    rejected = _write_source(tmp_path / "rejected.json", {"plan_id": _LEAK_CANARY})
    preflight_argv = [
        "evidence",
        "preflight",
        "--source",
        str(source),
        "--plan",
        str(plan),
        "--case-token",
        "CSYN-CTP-I01",
        "--checkpoint",
        "ehr",
        "--source-type",
        CANONICAL_JSON_SOURCE_TYPE,
        "--media-type",
        CANONICAL_JSON_MEDIA_TYPE,
    ]
    rejected_argv = list(preflight_argv)
    rejected_argv[3] = str(rejected)

    with caplog.at_level(0):
        assert main(preflight_argv) == 0
        assert main(rejected_argv) == 2
    capsys.readouterr()
    assert caplog.records == []


def test_unexpected_crash_output_carries_no_content_or_source_path(
    tmp_path: Path,
    evidence_source_json: dict[str, Any],
    evidence_scope: EvidenceScope,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A crash after the read must not turn a traceback into an evidence dump."""

    source = _source_with(tmp_path, evidence_source_json, _LEAK_CANARY)

    def _fail(_parsed: object, *, scope: EvidenceScope) -> None:
        raise RuntimeError("injected failure after the boundary read")

    monkeypatch.setattr(preflight_module, "parse_evidence_source", _fail)
    with pytest.raises(RuntimeError) as raised:
        preflight_source(source, evidence_scope)
    crash_output = "".join(
        traceback.format_exception(
            type(raised.value), raised.value, raised.value.__traceback__
        )
    )
    assert "boundary read" in crash_output
    assert _LEAK_CANARY not in crash_output
    assert str(source) not in crash_output
    assert source.name not in crash_output


def test_cli_rejection_prints_no_traceback_and_no_source_path(
    tmp_path: Path,
    execution_plan: ExecutionPlan,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The chained OSError knows the path; the operator-facing error must not."""

    missing = tmp_path / "absent-evidence.json"
    plan = _write_source(tmp_path / "plan.json", execution_plan.to_dict())
    assert (
        main(
            [
                "evidence",
                "preflight",
                "--source",
                str(missing),
                "--plan",
                str(plan),
                "--case-token",
                "CSYN-CTP-I01",
                "--checkpoint",
                "ehr",
                "--source-type",
                CANONICAL_JSON_SOURCE_TYPE,
                "--media-type",
                CANONICAL_JSON_MEDIA_TYPE,
            ]
        )
        == 2
    )
    captured = capsys.readouterr()
    assert json.loads(captured.err)["error"]["code"] == "input_io_error"
    assert "Traceback" not in captured.err
    assert str(missing) not in captured.err
    assert missing.name not in captured.err
    assert captured.out == ""


def test_evidence_index_records_hashes_while_content_stays_in_the_object(
    tmp_path: Path,
    evidence_source_json: dict[str, Any],
    evidence_scope: EvidenceScope,
    evidence_metadata: EvidenceMetadata,
) -> None:
    """The index is the queryable surface, so no source value may reach it.

    Raw bytes live in the content-addressed object by design — that is what
    ``raw_sha256`` addresses. The SQLite index beside it is the part a
    diagnostic, support bundle, or careless query would read, so it must carry
    hashes, tokens, and provenance only.
    """

    workspace = tmp_path / "workspace"
    source = _source_with(tmp_path, evidence_source_json, _LEAK_CANARY)
    record = store_internal_synthetic_evidence(
        source,
        workspace=workspace,
        scope=evidence_scope,
        metadata=evidence_metadata,
    )
    database = workspace / "contextsafe.sqlite"
    object_path = (
        workspace / "evidence" / "raw" / "sha256" / record.raw_sha256[:2]
    ) / record.raw_sha256

    assert _LEAK_CANARY.encode("utf-8") in object_path.read_bytes()
    assert _LEAK_CANARY.encode("utf-8") not in database.read_bytes()

    connection = sqlite3.connect(database)
    try:
        rows = connection.execute(
            "SELECT evidence_id, raw_sha256, record_json FROM evidence_records"
        ).fetchall()
    finally:
        connection.close()
    assert len(rows) == 1
    evidence_id, raw_sha256, record_json = rows[0]
    assert evidence_id == record.evidence_id
    assert raw_sha256 == record.raw_sha256
    assert re.fullmatch(r"EVD-[0-9a-f]{64}", evidence_id) is not None
    assert _LEAK_CANARY not in record_json
    assert json.loads(record_json)["usable_for_execution"] is False


# --- the provenance fields on an accepted record ----------------------------
#
# `EvidenceRecord` carries `boundary_check_status: "passed"`. Until this suite
# grew this section, three of that record's own fields had never been examined
# by any boundary check: `collector_id`, `system_id` and `system_version` were
# validated for token shape and nothing else, so `collector_id='realpatientcanary'`
# was accepted, hashed into the evidence id, and written to contextsafe.sqlite.


def _metadata_json(field: str, value: str) -> dict[str, Any]:
    base = {
        "captured_at": "2026-07-14T00:00:00Z",
        "collector_id": "TEST-COLLECTOR",
        "system_id": "SYS-STAGING-EHR",
        "system_version": "1.0.0",
    }
    base[field] = value
    return base


@pytest.mark.parametrize(("field", "value"), _ACCEPTED_PROVENANCE)
def test_provenance_the_schema_declares_valid_is_accepted(
    field: str, value: str
) -> None:
    """A boundary check that rejects published-valid provenance is a defect."""

    jsonschema.Draft202012Validator(EVIDENCE_SCHEMA["properties"][field]).validate(
        value
    )
    assert (
        getattr(parse_evidence_metadata(_metadata_json(field, value)), field) == value
    )


@pytest.mark.parametrize(("field", "value", "expected_code"), _REJECTED_PROVENANCE)
def test_provenance_that_must_fail_closed_does(
    field: str, value: str, expected_code: str
) -> None:
    """Both layers hold: the grammar first, then the canary scan."""

    with pytest.raises(ContextSafeError) as raised:
        parse_evidence_metadata(_metadata_json(field, value))
    assert raised.value.code == expected_code
    assert raised.value.path == f"$.{field}"
    assert value not in str(raised.value)


@pytest.mark.parametrize(("field", "value", "gap"), _DOCUMENTED_PROVENANCE_BLIND_SPOTS)
def test_documented_provenance_blind_spots_are_pinned_for_security_review(
    field: str, value: str, gap: str
) -> None:
    """The one exempted detector, recorded where a reviewer can see it."""

    assert gap
    assert (
        getattr(parse_evidence_metadata(_metadata_json(field, value)), field) == value
    )
    assert re.search(r"[0-9]{4}", value) is None


def test_a_canary_in_provenance_never_reaches_the_index(
    tmp_path: Path,
    evidence_source_json: dict[str, Any],
    evidence_scope: EvidenceScope,
) -> None:
    """The surface this file exists to protect, exercised end to end.

    ``store_internal_synthetic_evidence`` is the only caller of
    ``parse_evidence_metadata``. Before this change it accepted a canary
    ``collector_id``, hashed it into the evidence id and wrote it into
    ``contextsafe.sqlite``, inside a record whose own field says the boundary
    check passed.
    """

    workspace = tmp_path / "workspace"
    source = _source_with(tmp_path, evidence_source_json, _LEAK_CANARY)
    with pytest.raises(ContextSafeError) as raised:
        store_internal_synthetic_evidence(
            source,
            workspace=workspace,
            scope=evidence_scope,
            metadata=parse_evidence_metadata(
                _metadata_json("collector_id", "realpatientcanary")
            ),
        )
    assert raised.value.code == "phi_canary_detected"
    database = workspace / "contextsafe.sqlite"
    if database.exists():  # pragma: no cover - the store never gets this far
        assert b"realpatientcanary" not in database.read_bytes()


@pytest.mark.parametrize(
    "grammar",
    [PROVENANCE_LABEL_GRAMMAR, PROVENANCE_SYSTEM_GRAMMAR, PROVENANCE_VERSION_GRAMMAR],
    ids=["label", "system", "version"],
)
@given(data=st.data())
@settings(max_examples=300, deadline=None, suppress_health_check=list(HealthCheck))
def test_every_value_the_schema_admits_passes_the_provenance_scan(
    grammar: Grammar, data: st.DataObject
) -> None:
    """The property that keeps the grammar and the detectors from disagreeing.

    A detector firing on a value the published grammar admits would mean the
    code rejects something the contract declares valid, which is the defect
    that closed PR #38. Rather than asserting that of a handful of examples,
    this draws from the published base shape and asserts it of anything the
    exclusions then let through.
    """

    value = data.draw(st.from_regex(grammar.base, fullmatch=True))
    assume(grammar.rejection(value) is None)
    assert [
        hit for hit in provenance_hits(value) if hit.startswith("direct-identifier:")
    ] == []


def test_the_published_schema_carries_the_grammars_the_code_enforces() -> None:
    """Code and contract cannot drift: the strings are compared, not described."""

    for field, grammar in (
        ("collector_id", PROVENANCE_LABEL_GRAMMAR),
        ("system_id", PROVENANCE_SYSTEM_GRAMMAR),
        ("system_version", PROVENANCE_VERSION_GRAMMAR),
    ):
        published = EVIDENCE_SCHEMA["properties"][field]
        assert published["maxLength"] == grammar.max_length
        clauses = published["allOf"]
        assert clauses[0]["pattern"] == grammar.base
        assert [clause["not"]["pattern"] for clause in clauses[1:]] == [
            expression for expression, _ in grammar.exclusions
        ]


def test_the_only_exempt_detector_is_the_one_the_blind_spots_record() -> None:
    assert frozenset({"record-locator"}) == PROVENANCE_EXEMPT_DETECTORS
    assert "record-locator" in {detector.name for detector in DETECTORS}


def test_no_rejection_ever_echoes_the_value_that_triggered_it(
    tmp_path: Path,
    evidence_source_json: dict[str, Any],
    evidence_scope: EvidenceScope,
) -> None:
    """One property over the whole rejection matrix, not one case at a time."""

    triggers = (
        "CTXSAFE-PHI-CANARY-ALICE",
        "person@example.invalid",
        "123-45-6789",
        "https://patient.invalid/record",
        "CSYN-SAFE​TOKEN",
        " CSYN-SAFE",
        "patient-like prose",
        *(value for value, _ in _REJECTED_NEAR_MISSES),
    )
    for trigger in triggers:
        source = _source_with(tmp_path, dict(evidence_source_json), trigger)
        with pytest.raises(ContextSafeError) as raised:
            preflight_source(source, evidence_scope)
        rendered = json.dumps(raised.value.to_dict())
        assert trigger not in rendered
        assert trigger.strip() not in rendered
