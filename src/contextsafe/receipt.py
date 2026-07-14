"""Deterministic, claim-minimal JSON receipt construction."""

from collections import Counter

from contextsafe import __version__
from contextsafe.canonical import JsonValue, canonical_json, sha256_json
from contextsafe.evaluator import Outcome
from contextsafe.models import RECEIPT_SCHEMA_VERSION, EvaluationBundle, OutcomeStatus

_LIMITATIONS = [
    "Synthetic reference fixture only; not an approved clinical oracle.",
    "A passing result does not establish safety, compliance, or certification.",
    "Patient data is prohibited; bounded checks cannot prove an input is synthetic.",
    "This iteration does not ingest FHIR or sign artifacts.",
]


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
    """Build a deterministic receipt containing hashes, not semantic values."""

    results = result_payload(outcomes)
    counts = Counter(item.status.value for item in outcomes)
    summary: dict[str, JsonValue] = {
        status.value: counts.get(status.value, 0) for status in OutcomeStatus
    }
    return {
        "case_id": bundle.case.case_id,
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


def render_receipt(receipt: dict[str, JsonValue]) -> str:
    """Render a receipt as canonical UTF-8 JSON with one terminal newline."""

    return f"{canonical_json(receipt)}\n"
