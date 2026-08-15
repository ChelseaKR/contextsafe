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

import pytest

import contextsafe.preflight as preflight_module
from contextsafe.cli import main
from contextsafe.errors import ContextSafeError
from contextsafe.evidence import (
    CANONICAL_JSON_MEDIA_TYPE,
    CANONICAL_JSON_SOURCE_TYPE,
    EvidenceMetadata,
    EvidenceScope,
)
from contextsafe.evidence_store import store_internal_synthetic_evidence
from contextsafe.plan import ExecutionPlan
from contextsafe.preflight import preflight_source

ROOT = Path(__file__).resolve().parents[1]
SOURCE_MODULES = tuple(sorted((ROOT / "src" / "contextsafe").glob("*.py")))

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
