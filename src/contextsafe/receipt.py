"""Deterministic, claim-minimal JSON receipt construction.

The deterministic payload and the untrusted envelope are deliberately
separate (P0-14, R-10): `payload_sha256` covers only the payload, and every
envelope field is unauthenticated caller-declared metadata that can never
change an evaluation result or its hash.
"""

from collections import Counter
from datetime import datetime, timedelta

from contextsafe import __version__
from contextsafe.canonical import JsonValue, canonical_json, sha256_json
from contextsafe.divergence import compute_divergence
from contextsafe.errors import ContextSafeError
from contextsafe.evaluator import Outcome
from contextsafe.models import (
    RECEIPT_DOCUMENT_SCHEMA_VERSION,
    RECEIPT_SCHEMA_VERSION,
    EvaluationBundle,
    OutcomeStatus,
)

_LIMITATIONS = [
    "Synthetic reference fixture only; not an approved clinical oracle.",
    "A passing result does not establish safety, compliance, or certification.",
    "Patient data is prohibited; bounded checks cannot prove an input is synthetic.",
    "This iteration does not ingest FHIR or sign artifacts.",
]

_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def input_payload(bundle: EvaluationBundle) -> dict[str, JsonValue]:
    """Return canonical evaluator inputs independently of file ordering."""

    return {
        "case": bundle.case.to_dict(),
        "observations": [
            item.to_dict()
            for item in sorted(
                bundle.observations, key=lambda value: value.observation_id
            )
        ],
    }


def result_payload(outcomes: tuple[Outcome, ...]) -> list[JsonValue]:
    """Return outcomes in stable rule-ID order."""

    return [
        item.to_dict() for item in sorted(outcomes, key=lambda value: value.rule_id)
    ]


def build_receipt(
    bundle: EvaluationBundle, outcomes: tuple[Outcome, ...]
) -> dict[str, JsonValue]:
    """Build a deterministic receipt payload containing hashes, not values.

    The payload never contains a timestamp, signature, or other
    run-environment metadata; identical inputs, rules, and runner version
    always produce identical payload bytes. The ``divergence`` section is a
    function of the case and observations alone (B-031); the rules do not
    reach it, and it does not reach ``result_sha256``.
    """

    results = result_payload(outcomes)
    counts = Counter(item.status.value for item in outcomes)
    summary: dict[str, JsonValue] = {
        status.value: counts.get(status.value, 0) for status in OutcomeStatus
    }
    return {
        "case_id": bundle.case.case_id,
        "divergence": compute_divergence(bundle).to_dict(),
        "hashes": {
            "input_sha256": sha256_json(input_payload(bundle)),
            "result_sha256": sha256_json(results),
            "rule_set_sha256": sha256_json(bundle.rule_set.to_dict()),
        },
        "limitations": list(_LIMITATIONS),
        "results": results,
        "runner_version": __version__,
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "scope": {
            "clinical_oracle_approved": False,
            "patient_data_allowed": False,
            "synthetic_fixture_only": True,
        },
        "summary": summary,
    }


def build_envelope(claimed_generated_at: datetime | None) -> dict[str, JsonValue]:
    """Return the untrusted metadata that lives outside the payload.

    `claimed_generated_at` is caller-declared and unauthenticated; it proves
    nothing about when evaluation actually ran. This iteration has no signing
    path, so `signature_status` is always `not_signed` and `trusted_time` is
    always false; a later signature layer may not relabel unsigned documents.
    """

    claimed: JsonValue = None
    if claimed_generated_at is not None:
        if (
            claimed_generated_at.utcoffset() != timedelta(0)
            or claimed_generated_at.microsecond != 0
        ):
            raise ContextSafeError(
                "invalid_timestamp",
                "$.envelope.claimed_generated_at",
                "claimed time must be a whole-second UTC timestamp",
            )
        claimed = claimed_generated_at.strftime(_TIMESTAMP_FORMAT)
    return {
        "claimed_generated_at": claimed,
        "signature_status": "not_signed",
        "trusted_time": False,
    }


def build_receipt_document(
    bundle: EvaluationBundle,
    outcomes: tuple[Outcome, ...],
    *,
    claimed_generated_at: datetime | None = None,
) -> dict[str, JsonValue]:
    """Wrap the deterministic payload in an explicitly untrusted envelope.

    `payload_sha256` is computed over the canonical payload only; changing
    any envelope field never changes it, and changing any payload byte
    always does.
    """

    payload = build_receipt(bundle, outcomes)
    return {
        "envelope": build_envelope(claimed_generated_at),
        "payload": payload,
        "payload_sha256": sha256_json(payload),
        "schema_version": RECEIPT_DOCUMENT_SCHEMA_VERSION,
    }


def render_receipt(receipt: dict[str, JsonValue]) -> str:
    """Render a receipt as canonical UTF-8 JSON with one terminal newline."""

    return f"{canonical_json(receipt)}\n"
