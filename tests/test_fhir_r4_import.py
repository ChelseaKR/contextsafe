"""The FHIR R4 JSON importer (B-023).

What this module pins. The conversion is exact: every Gender Harmony
extension and every usual name becomes one observation carrying the
source's own token, the coding's own system, the source digest, and an RFC
6901 pointer to the element it was read from. The conversion is whole: a
narrative, a contained resource, an element outside the allowlist, an
extension outside the profile, an identifier outside the synthetic
namespace, a display, a comment, a reference, a value outside the closed
alphabet, or an oversized source rejects the document and produces
nothing, and the rejection names a category and a location and never the
content. Ambiguity is two observations, not one guess. Sex parameter for
clinical use is never derived and never carried. And the profile is
reference-only: ``reviewed`` cannot be set, and the published schema and the
runtime agree on every committed fixture.
"""

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st
from jsonschema import Draft202012Validator

import contextsafe.preflight as preflight_module
from contextsafe.canonical import canonical_json
from contextsafe.cli import EXIT_CONTRACT_ERROR, EXIT_SUCCESS, EXIT_USAGE_ERROR, main
from contextsafe.errors import ContextSafeError
from contextsafe.evaluator import evaluate
from contextsafe.importers import (
    ImportErrorCode,
    ImportWarningCode,
    available_formats,
    import_source,
    importer_for,
)
from contextsafe.importers.base import UNBOUND_SOURCE
from contextsafe.importers.fhir_r4_json import (
    _EXTENSIONS,
    _PATIENT_REFERENCE_KEYS,
    FHIR_R4_BOUNDARY_PROFILE,
    FHIR_R4_FORMAT,
    FHIR_R4_MAPPING_VERSION,
    FHIR_R4_PROFILE,
    FhirR4Profile,
    convert_scanned,
)
from contextsafe.jsonio import parse_json_bytes
from contextsafe.models import Checkpoint, ConceptKind, SyntheticCase, ValueStatus
from contextsafe.preflight import (
    CANONICAL_JSON_PROFILE,
    MAX_EVIDENCE_BYTES,
    BoundaryProfile,
    ScannedSource,
    scan_source,
)
from contextsafe.reference_fixtures import REFERENCE_FILES, REFERENCE_ROOT
from contextsafe.validation import (
    RSG_VALUES,
    parse_bundle,
    parse_case,
    parse_observations,
)

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = REFERENCE_ROOT
FIXTURES = ROOT / "tests" / "fixtures" / "fhir-r4-json"
AUDIT = ROOT / "docs" / "PUBLICATION-READINESS.md"
CODING_TOKEN_LENGTH = 96
"""The observation contract's token bound; the reader applies it to every coding."""
PROFILE_SCHEMA = json.loads(
    (ROOT / "schemas" / "contextsafe-fhir-r4-source-v0.1.schema.json").read_text(
        encoding="utf-8"
    )
)
OBSERVATION_SET_SCHEMA = json.loads(
    (ROOT / "schemas" / "contextsafe-observation-set-v0.1.schema.json").read_text(
        encoding="utf-8"
    )
)
GI_URL = FHIR_R4_PROFILE.gender_identity_url
PRONOUNS_URL = FHIR_R4_PROFILE.pronouns_url
RSG_URL = FHIR_R4_PROFILE.recorded_sex_or_gender_url
SPCU_URL = FHIR_R4_PROFILE.sex_parameter_url
PRESENCE_SYSTEM = FHIR_R4_PROFILE.presence_code_system

REJECTIONS: dict[str, tuple[str, str]] = {
    "reject-birth-date.json": ("prohibited_field", "$"),
    "reject-bundle-resource-type.json": (
        ImportErrorCode.RESOURCE_UNSUPPORTED.value,
        "$.entry[1].resource",
    ),
    "reject-bundle-total.json": (
        ImportErrorCode.CARDINALITY_UNSUPPORTED.value,
        "$.total",
    ),
    "reject-bundle-two-patients.json": (
        ImportErrorCode.CARDINALITY_UNSUPPORTED.value,
        "$.entry",
    ),
    "reject-bundle-type.json": ("invalid_enum", "$.type"),
    "reject-canary.json": (
        "phi_canary_detected",
        "$.extension[0].extension[0].valueCodeableConcept.coding[0].code",
    ),
    "reject-case-mismatch.json": (ImportErrorCode.CASE_MISMATCH.value, "$.identifier"),
    "reject-code-not-synthetic.json": (
        ImportErrorCode.VALUE_UNSUPPORTED.value,
        "$.extension[0]",
    ),
    "reject-coding-system-too-long.json": (
        "invalid_string",
        "$.extension[0].extension[0].valueCodeableConcept.coding[0].system",
    ),
    "reject-comment-sub-extension.json": (
        ImportErrorCode.EXTENSION_UNKNOWN.value,
        "$.extension[0].extension[1]",
    ),
    "reject-contained.json": ("prohibited_field", "$"),
    "reject-direct-identifier.json": (
        "direct_identifier_detected",
        "$.extension[0].extension[0].valueCodeableConcept.coding[0].code",
    ),
    "reject-display.json": (
        ImportErrorCode.ELEMENT_UNSUPPORTED.value,
        "$.extension[0].extension[0].valueCodeableConcept.coding[0]",
    ),
    "reject-duplicate-sub-extension.json": (
        ImportErrorCode.CARDINALITY_UNSUPPORTED.value,
        "$.extension[0].extension[1]",
    ),
    "reject-extension-value-type.json": (
        ImportErrorCode.ELEMENT_UNSUPPORTED.value,
        "$.extension[0].extension[0]",
    ),
    "reject-gi-alphabet-code.json": (
        ImportErrorCode.VALUE_UNSUPPORTED.value,
        "$.extension[0]",
    ),
    "reject-id-not-synthetic.json": (
        ImportErrorCode.IDENTIFIER_NOT_SYNTHETIC.value,
        "$.id",
    ),
    "reject-identifier-namespace.json": (
        ImportErrorCode.IDENTIFIER_NOT_SYNTHETIC.value,
        "$.identifier[1]",
    ),
    "reject-identifier-value.json": (
        ImportErrorCode.IDENTIFIER_NOT_SYNTHETIC.value,
        "$.identifier[0]",
    ),
    "reject-meta.json": (ImportErrorCode.ELEMENT_UNSUPPORTED.value, "$"),
    "reject-name-not-synthetic.json": (
        ImportErrorCode.VALUE_UNSUPPORTED.value,
        "$.name[1].family",
    ),
    "reject-name-without-parts.json": (
        ImportErrorCode.CARDINALITY_UNSUPPORTED.value,
        "$.name[1]",
    ),
    "reject-name-without-use.json": ("missing_field", "$.name[0].use"),
    "reject-narrative.json": ("prohibited_field", "$"),
    "reject-nothing-to-convert.json": (
        ImportErrorCode.CARDINALITY_UNSUPPORTED.value,
        "$",
    ),
    "reject-presence-code-outside-set.json": (
        ImportErrorCode.VALUE_UNSUPPORTED.value,
        "$.extension[0]",
    ),
    "reject-reference.json": (
        ImportErrorCode.REFERENCE_OUTSIDE_DOCUMENT.value,
        "$.managingOrganization",
    ),
    "reject-resource-type.json": (ImportErrorCode.RESOURCE_UNSUPPORTED.value, "$"),
    "reject-rsg-presence-code.json": (
        ImportErrorCode.CONCEPT_NOT_CONVERTIBLE.value,
        "$.extension[0]",
    ),
    "reject-rsg-type-not-synthetic.json": (
        ImportErrorCode.VALUE_UNSUPPORTED.value,
        "$.extension[0]",
    ),
    "reject-rsg-unsupported-value.json": (
        ImportErrorCode.VALUE_UNSUPPORTED.value,
        "$.extension[0]",
    ),
    "reject-rsg-without-type.json": (
        ImportErrorCode.CONTEXT_MISSING.value,
        "$.extension[0]",
    ),
    "reject-simple-extension-form.json": (
        ImportErrorCode.ELEMENT_UNSUPPORTED.value,
        "$.extension[0]",
    ),
    "reject-spcu-extension.json": (
        ImportErrorCode.CONCEPT_NOT_CONVERTIBLE.value,
        "$.extension[1]",
    ),
    "reject-telecom.json": ("prohibited_field", "$"),
    "reject-two-codings.json": (
        ImportErrorCode.CARDINALITY_UNSUPPORTED.value,
        "$.extension[0].extension[0].valueCodeableConcept.coding",
    ),
    "reject-unknown-element.json": (ImportErrorCode.ELEMENT_UNSUPPORTED.value, "$"),
    "reject-unknown-extension-url.json": (
        "direct_identifier_detected",
        "$.extension[1].url",
    ),
    "reject-unknown-extension.json": (
        ImportErrorCode.EXTENSION_UNKNOWN.value,
        "$.extension[1]",
    ),
    "reject-usual-name-two-givens.json": (
        ImportErrorCode.CARDINALITY_UNSUPPORTED.value,
        "$.name[0].given",
    ),
}
"""Every committed rejection fixture, its code, and its location."""

ACCEPTED: dict[str, int] = {
    "accept-ambiguous.json": 5,
    "accept-bundle.json": 2,
    "accept-presence-states.json": 3,
}
"""Every committed acceptance fixture and the observation count it yields."""

SCHEMA_BLIND_REJECTIONS = frozenset(
    {
        "reject-canary.json",
        "reject-case-mismatch.json",
        "reject-direct-identifier.json",
        "reject-nothing-to-convert.json",
    }
)
"""Rejections the published schema cannot see and the runtime must.

Two are the boundary scan's (a canary and a direct-identifier pattern inside
a well-formed token), one is a cross-document check (the case token), and one
is a count over concepts. Every other rejection fixture must fail the schema
as well: which coding shape each sub-extension admits is written into the
schema per extension, so a recorded-sex-or-gender value outside the closed
alphabet, a presence code where the concept has no presence state, an
alphabet code where a synthetic token is required, and a name with no part
are all visible to it.
"""

FIXTURE_CONTENT = (
    "Notsynthetic",
    "nonbinary",
    "masked",
    "patient-1",
    "1980",
    "555",
    "narrative",
    "ALICE",
    "1234567890",
    "example.invalid",
    "hospital-record",
    "CSYN-GENDER",
    "CSYN-ASTER",
    "CSYN-CTP-Z99",
)
"""Strings that appear in fixture content and may never appear in an error."""

PII_SHAPED_LITERALS: dict[str, str] = {
    "1980-01-02": "reject-birth-date.json",
    "555-0100": "reject-telecom.json",
    "CSYN-1234567890": "reject-direct-identifier.json",
    "CSYN-CTXSAFE-PHI-CANARY-ALICE": "reject-canary.json",
}
"""Every deliberately PII-shaped literal a committed fixture carries, by carrier.

These are the repository's only fixture-file literals shaped like a date of
birth, a phone number, a ten-digit run, or a PHI canary. Each exists to be
refused. The synthetic-data confirmation in ``docs/PUBLICATION-READINESS.md``
section 4 names every one of them, and the test below is what keeps that
section describing the corpus after it was found stale on 2026-09-04.
"""


def _fixture(name: str) -> dict[str, Any]:
    value = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _write(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value, separators=(",", ":")), encoding="utf-8")
    return path


def _scanned(value: object) -> ScannedSource:
    """Run the FHIR boundary scan in memory, then wrap as a scanned source."""

    raw = canonical_json(json.loads(json.dumps(value))).encode("utf-8")
    parsed = parse_json_bytes(raw)
    preflight_module._boundary_scan(parsed, FHIR_R4_BOUNDARY_PROFILE)
    return ScannedSource(
        raw_sha256=hashlib.sha256(raw).hexdigest(),
        raw_byte_count=len(raw),
        value=parsed,
    )


def _coded(code: str, system: str = "urn:contextsafe:fixture") -> dict[str, Any]:
    return {"coding": [{"system": system, "code": code}]}


def _extension(url: str, parts: list[tuple[str, dict[str, Any]]]) -> dict[str, Any]:
    return {
        "url": url,
        "extension": [
            {"url": name, "valueCodeableConcept": value} for name, value in parts
        ],
    }


def _patient(
    *,
    extensions: list[dict[str, Any]] | None = None,
    names: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    document: dict[str, Any] = {
        "resourceType": "Patient",
        "identifier": [
            {"system": "urn:contextsafe:synthetic", "value": "CSYN-CTP-I01"}
        ],
    }
    if extensions is not None:
        document["extension"] = extensions
    if names is not None:
        document["name"] = names
    return document


def _import_args(source: Path, case_path: Path, checkpoint: str = "ehr") -> list[str]:
    return [
        "import",
        "--format",
        FHIR_R4_FORMAT,
        "--source",
        str(source),
        "--case",
        str(case_path),
        "--checkpoint",
        checkpoint,
    ]


@pytest.fixture
def case(case_json: dict[str, Any]) -> SyntheticCase:
    return parse_case(case_json)


# --- the reference round trip -------------------------------------------------


def test_reference_patient_round_trips_to_four_pointed_observations(
    case: SyntheticCase,
) -> None:
    source = REFERENCE / "fhir-patient.json"
    raw = source.read_bytes()
    result = import_source(FHIR_R4_FORMAT, source, case=case, checkpoint=Checkpoint.EHR)

    assert result.record_count == len(result.observations) == 4
    by_concept = {item.concept: item for item in result.observations}
    assert by_concept[ConceptKind.GENDER_IDENTITY].value.to_dict() == {
        "code_system": "urn:contextsafe:fixture",
        "status": "specified",
        "value": "CSYN-GENDER-1",
    }
    assert by_concept[ConceptKind.PRONOUNS].value.to_dict() == {
        "status": "specified",
        "value": "CSYN-PRONOUN-THEY-THEM",
    }
    assert by_concept[ConceptKind.RECORDED_SEX_OR_GENDER].value.to_dict() == {
        "context": "CSYN-GOVERNMENT-ID",
        "source": UNBOUND_SOURCE,
        "value": "X",
    }
    assert by_concept[ConceptKind.NAME_TO_USE].value.to_dict() == {
        "status": "specified",
        "use": "usual",
        "value": "CSYN-ASTER",
    }
    assert [item.evidence.source_pointer for item in result.observations] == [
        "/extension/0",
        "/extension/1",
        "/extension/2",
        "/name/0",
    ]
    assert [item.observation_id for item in result.observations] == [
        f"OBS-CTP-I01-F{index:04d}" for index in range(4)
    ]
    digest = hashlib.sha256(raw).hexdigest()
    assert result.source_sha256 == digest
    assert result.source_byte_count == len(raw)
    assert all(item.evidence.source_sha256 == digest for item in result.observations)
    assert all(
        item.mapping.mapping_version == FHIR_R4_MAPPING_VERSION
        and item.mapping.source_concept is item.mapping.target_concept
        for item in result.observations
    )
    assert result.profile_reviewed is False
    assert set(result.warnings) == {
        ImportWarningCode.CHECKPOINT_ASSERTED_BY_CALLER,
        ImportWarningCode.MAPPING_PROFILE_NOT_BOUND,
    }
    assert result.to_dict()["persisted"] is False


def test_imported_document_validates_against_both_contracts_and_evaluates(
    case: SyntheticCase, case_json: dict[str, Any], rules_json: dict[str, Any]
) -> None:
    """Reference fixture in, published observation-set contract out, receipt after.

    The usual name is verbatim the token the reference rule expects, so that
    one rule passes on affirmative evidence; the gender-identity and pronoun
    tokens are unbound and mismatch; the two rules at other checkpoints
    have no evidence. Nothing passes on absence.
    """

    result = import_source(
        FHIR_R4_FORMAT,
        REFERENCE / "fhir-patient.json",
        case=case,
        checkpoint=Checkpoint.EHR,
    )
    document = result.observation_set()
    Draft202012Validator(OBSERVATION_SET_SCHEMA).validate(document)
    assert [item.to_dict() for item in parse_observations(document)] == document[
        "observations"
    ]
    bundle = parse_bundle(case_json, document, rules_json)
    by_rule = {item.rule_id: item for item in evaluate(bundle)}
    assert (by_rule["A-I04"].status.value, by_rule["A-I04"].reason.value) == (
        "pass",
        "affirmative_evidence_match",
    )
    for rule_id in ("A-I01", "A-I05"):
        assert by_rule[rule_id].status.value == "fail"
        assert by_rule[rule_id].reason.value == "semantic_mismatch"
    for rule_id in ("A-I02", "A-I03"):
        assert by_rule[rule_id].status.value == "indeterminate"
        assert by_rule[rule_id].reason.value == "missing_evidence"


def test_the_checkpoint_is_the_callers_claim_and_the_document_names_none(
    case: SyntheticCase,
) -> None:
    for checkpoint in Checkpoint:
        result = import_source(
            FHIR_R4_FORMAT,
            REFERENCE / "fhir-patient.json",
            case=case,
            checkpoint=checkpoint,
        )
        assert all(item.checkpoint is checkpoint for item in result.observations)
        assert ImportWarningCode.CHECKPOINT_ASSERTED_BY_CALLER in result.warnings


# --- every committed fixture is pinned ----------------------------------------


def test_every_committed_fixture_is_pinned_and_every_pin_exists() -> None:
    committed = {path.name for path in FIXTURES.iterdir()}
    assert committed == set(REJECTIONS) | set(ACCEPTED)
    assert set(REJECTIONS) >= SCHEMA_BLIND_REJECTIONS


@pytest.mark.parametrize("name", sorted(REJECTIONS))
def test_each_rejection_class_rejects_the_whole_source_without_content(
    case: SyntheticCase, name: str
) -> None:
    expected_code, expected_path = REJECTIONS[name]
    with pytest.raises(ContextSafeError) as raised:
        import_source(
            FHIR_R4_FORMAT, FIXTURES / name, case=case, checkpoint=Checkpoint.EHR
        )
    assert (raised.value.code, raised.value.path) == (expected_code, expected_path)
    rendered = str(raised.value)
    for content in FIXTURE_CONTENT:
        assert content not in rendered


def _audit_section_4() -> str:
    text = AUDIT.read_text(encoding="utf-8")
    start = text.index("### §4 Synthetic-data confirmation")
    return text[start : text.index("### §5", start)]


def test_pii_shaped_literals_live_only_in_pinned_rejections_and_the_audit_names_them() -> (
    None
):
    """The synthetic-data confirmation describes the corpus that exists.

    Each PII-shaped literal is carried by exactly the rejection fixture the
    table names, that fixture is pinned to its rejection, the literal is
    guarded by the never-echoed assertion, and the audit names both. No
    accepting or packaged fixture carries any of them or a ``birthDate``.
    """

    section = _audit_section_4()
    for literal, carrier in PII_SHAPED_LITERALS.items():
        carriers = sorted(
            path.name
            for path in FIXTURES.iterdir()
            if literal in path.read_text(encoding="utf-8")
        )
        assert carriers == [carrier], literal
        assert carrier in REJECTIONS
        assert any(marker in literal for marker in FIXTURE_CONTENT), literal
        assert f"`{literal}`" in section, literal
        assert f"`{carrier}`" in section, carrier
    accepting = [FIXTURES / name for name in ACCEPTED] + [
        REFERENCE / name for name in REFERENCE_FILES
    ]
    for path in accepting:
        text = path.read_text(encoding="utf-8")
        assert "birthDate" not in text, path.name
        assert not any(literal in text for literal in PII_SHAPED_LITERALS), path.name


@pytest.mark.parametrize("name", sorted(ACCEPTED))
def test_each_acceptance_fixture_converts_whole(case: SyntheticCase, name: str) -> None:
    result = import_source(
        FHIR_R4_FORMAT, FIXTURES / name, case=case, checkpoint=Checkpoint.EHR
    )
    assert len(result.observations) == ACCEPTED[name]
    pointers = [item.evidence.source_pointer for item in result.observations]
    assert len(set(pointers)) == len(pointers)
    Draft202012Validator(OBSERVATION_SET_SCHEMA).validate(result.observation_set())


def test_ambiguity_is_two_observations_and_the_evaluator_says_so(
    case: SyntheticCase, case_json: dict[str, Any], rules_json: dict[str, Any]
) -> None:
    result = import_source(
        FHIR_R4_FORMAT,
        FIXTURES / "accept-ambiguous.json",
        case=case,
        checkpoint=Checkpoint.EHR,
    )
    gender = [
        item
        for item in result.observations
        if item.concept is ConceptKind.GENDER_IDENTITY
    ]
    names = [
        item for item in result.observations if item.concept is ConceptKind.NAME_TO_USE
    ]
    assert [item.evidence.source_pointer for item in gender] == [
        "/extension/0",
        "/extension/1",
    ]
    assert [item.evidence.source_pointer for item in names] == ["/name/0", "/name/1"]
    by_rule = {
        item.rule_id: item
        for item in evaluate(
            parse_bundle(case_json, result.observation_set(), rules_json)
        )
    }
    for rule_id in ("A-I01", "A-I04"):
        assert by_rule[rule_id].status.value == "indeterminate"
        assert by_rule[rule_id].reason.value == "ambiguous_evidence"
        assert len(by_rule[rule_id].observed_sha256s) == 2


def test_presence_states_carry_no_value_and_their_own_system(
    case: SyntheticCase,
) -> None:
    result = import_source(
        FHIR_R4_FORMAT,
        FIXTURES / "accept-presence-states.json",
        case=case,
        checkpoint=Checkpoint.EHR,
    )
    values = {item.concept: item.value.to_dict() for item in result.observations}
    assert values[ConceptKind.GENDER_IDENTITY] == {
        "code_system": PRESENCE_SYSTEM,
        "status": "declined",
        "value": None,
    }
    assert values[ConceptKind.PRONOUNS] == {"status": "absent", "value": None}


def test_a_bundle_pointer_names_the_entry_it_was_read_from(case: SyntheticCase) -> None:
    result = import_source(
        FHIR_R4_FORMAT,
        FIXTURES / "accept-bundle.json",
        case=case,
        checkpoint=Checkpoint.EHR,
    )
    assert [item.evidence.source_pointer for item in result.observations] == [
        "/entry/0/resource/extension/0",
        "/entry/0/resource/name/0",
    ]


# --- boundary: size, links, platform, and the profile delta --------------------


def test_oversized_symlinked_and_unsupported_platform_sources_fail_closed(
    tmp_path: Path, case: SyntheticCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    padded = json.loads((REFERENCE / "fhir-patient.json").read_text(encoding="utf-8"))
    padded["identifier"].extend(
        {"system": "urn:contextsafe:synthetic", "value": f"CSYN-PAD-{index:06d}"}
        for index in range(60)
    )
    large = tmp_path / "large.json"
    large.write_text(json.dumps(padded, indent=8192)[: MAX_EVIDENCE_BYTES + 1], "utf-8")
    assert large.stat().st_size > MAX_EVIDENCE_BYTES
    with pytest.raises(ContextSafeError) as raised:
        import_source(FHIR_R4_FORMAT, large, case=case, checkpoint=Checkpoint.EHR)
    assert raised.value.code == "input_too_large"

    target = tmp_path / "target.json"
    target.write_bytes((REFERENCE / "fhir-patient.json").read_bytes())
    link = tmp_path / "link.json"
    link.symlink_to(target)
    with pytest.raises(ContextSafeError) as raised:
        import_source(FHIR_R4_FORMAT, link, case=case, checkpoint=Checkpoint.EHR)
    assert raised.value.code == "input_path_unsafe"

    monkeypatch.setattr(preflight_module, "_NOFOLLOW", 0)
    with pytest.raises(ContextSafeError) as raised:
        import_source(FHIR_R4_FORMAT, target, case=case, checkpoint=Checkpoint.EHR)
    assert raised.value.code == "input_path_unsupported"


def test_the_fhir_profile_permits_name_and_nothing_else() -> None:
    assert BoundaryProfile() == CANONICAL_JSON_PROFILE
    assert CANONICAL_JSON_PROFILE.permitted_keys == frozenset()
    assert CANONICAL_JSON_PROFILE.published_constants == frozenset()
    assert FHIR_R4_BOUNDARY_PROFILE.permitted_keys == frozenset({"name"})
    assert FHIR_R4_BOUNDARY_PROFILE.published_constants == frozenset(
        {GI_URL, PRONOUNS_URL, RSG_URL, SPCU_URL, PRESENCE_SYSTEM}
    )
    assert "name" not in FHIR_R4_BOUNDARY_PROFILE.prohibited_keys()
    assert (
        FHIR_R4_BOUNDARY_PROFILE.prohibited_keys()
        < CANONICAL_JSON_PROFILE.prohibited_keys()
    )
    assert (
        CANONICAL_JSON_PROFILE.safe_path_keys()
        < FHIR_R4_BOUNDARY_PROFILE.safe_path_keys()
    )


def test_the_canonical_scan_still_rejects_a_name_key(tmp_path: Path) -> None:
    source = _write(tmp_path / "patient.json", _patient(names=[{"use": "usual"}]))
    with pytest.raises(ContextSafeError) as raised:
        scan_source(source)
    assert raised.value.code == "prohibited_field"
    assert scan_source(source, FHIR_R4_BOUNDARY_PROFILE).value == _patient(
        names=[{"use": "usual"}]
    )


@pytest.mark.parametrize(
    "url",
    [
        GI_URL + "X",
        GI_URL.upper(),
        GI_URL.replace("http://", "https://"),
        "http://hl7.org/fhir/StructureDefinition/patient-birthPlace",
    ],
)
def test_a_url_that_merely_resembles_a_published_constant_is_scanned(
    url: str,
) -> None:
    document = _patient(extensions=[_extension(url, [("value", _coded("CSYN-X"))])])
    with pytest.raises(ContextSafeError) as raised:
        _scanned(document)
    assert raised.value.code == "direct_identifier_detected"
    assert url not in str(raised.value)


@pytest.mark.parametrize(
    "key", ["text", "contained", "note", "comment", "telecom", "address", "birthDate"]
)
def test_prohibited_keys_stay_prohibited_under_the_fhir_profile(key: str) -> None:
    document = _patient(extensions=[_extension(GI_URL, [("value", _coded("CSYN-X"))])])
    document[key] = "CSYN-X"
    with pytest.raises(ContextSafeError) as raised:
        _scanned(document)
    assert raised.value.code == "prohibited_field"


# --- safety negatives ---------------------------------------------------------


def test_the_profile_cannot_claim_review() -> None:
    assert FHIR_R4_PROFILE.reviewed is False
    with pytest.raises(ContextSafeError) as raised:
        FhirR4Profile(
            **{
                field: getattr(FHIR_R4_PROFILE, field)
                for field in FhirR4Profile.__slots__
                if field != "reviewed"
            },
            reviewed=True,
        )
    assert raised.value.code == "profile_review_not_available"
    with pytest.raises((AttributeError, TypeError)):
        FHIR_R4_PROFILE.reviewed = True  # type: ignore[misc]


def test_the_extension_table_is_an_identity_over_concepts_without_spcu() -> None:
    """No URL arrives at SPCU, and the SPCU URL is not a source of anything."""

    assert SPCU_URL not in _EXTENSIONS
    assert {rule.concept for rule in _EXTENSIONS.values()} == {
        ConceptKind.GENDER_IDENTITY,
        ConceptKind.PRONOUNS,
        ConceptKind.RECORDED_SEX_OR_GENDER,
    }
    assert ConceptKind.SEX_PARAMETER_FOR_CLINICAL_USE not in {
        rule.concept for rule in _EXTENSIONS.values()
    }


def test_spcu_is_never_derived_from_gender_identity_or_rsg(
    case: SyntheticCase,
) -> None:
    document = _patient(
        extensions=[
            _extension(GI_URL, [("value", _coded("CSYN-GENDER-1"))]),
            _extension(
                RSG_URL,
                [("value", _coded("M")), ("type", _coded("CSYN-GOVERNMENT-ID"))],
            ),
        ]
    )
    result = convert_scanned(
        _scanned(document), case=case, checkpoint=Checkpoint.INTERFACE
    )
    assert ConceptKind.SEX_PARAMETER_FOR_CLINICAL_USE not in {
        item.concept for item in result.observations
    }
    assert result.observations[1].value.to_dict()["value"] == "M"


_RSG_ALPHABET_REJECTION = {
    "code": ImportErrorCode.VALUE_UNSUPPORTED.value,
    "path": "$.extension[0]",
    "message": (
        "a recorded sex or gender value is outside the observation contract's "
        "closed alphabet and is not normalized to a member of it"
    ),
}
"""The whole error object for an RSG value outside the alphabet.

Fixed so that the assertion is structural: the message is a sentence that
names no value, and the location is the extension in the source document,
not a path in the converted document the source never had.
"""


@pytest.mark.parametrize("code", ["female", "f", "Male", "CSYN-X", "x", "U", "FM"])
def test_rsg_values_outside_the_alphabet_reject_at_the_source_and_never_normalize(
    case: SyntheticCase, code: str
) -> None:
    """A-033: ``female`` is not ``F`` and ``f`` is not ``F``; nothing is mapped."""

    assert code not in RSG_VALUES
    document = _patient(
        extensions=[
            _extension(
                RSG_URL,
                [("value", _coded(code)), ("type", _coded("CSYN-GOVERNMENT-ID"))],
            )
        ]
    )
    with pytest.raises(ContextSafeError) as raised:
        convert_scanned(_scanned(document), case=case, checkpoint=Checkpoint.EHR)
    assert raised.value.to_dict() == _RSG_ALPHABET_REJECTION


@pytest.mark.parametrize("code", sorted(RSG_VALUES))
def test_every_member_of_the_contract_alphabet_is_carried_verbatim(
    case: SyntheticCase, code: str
) -> None:
    document = _patient(
        extensions=[
            _extension(
                RSG_URL,
                [("value", _coded(code)), ("type", _coded("CSYN-GOVERNMENT-ID"))],
            )
        ]
    )
    result = convert_scanned(_scanned(document), case=case, checkpoint=Checkpoint.EHR)
    assert [item.value.to_dict()["value"] for item in result.observations] == [code]


def _coding_of_length(length: int, *, system: bool) -> dict[str, Any]:
    """A gender-identity coding whose system or code is exactly ``length`` long."""

    if system:
        return _coded("CSYN-GENDER-1", "urn:contextsafe:fixture:" + "a" * (length - 24))
    return _coded("CSYN-" + "A" * (length - 5))


@pytest.mark.parametrize("system", [True, False], ids=["system", "code"])
def test_a_coding_token_at_the_contract_bound_is_carried(
    case: SyntheticCase, system: bool
) -> None:
    coding = _coding_of_length(CODING_TOKEN_LENGTH, system=system)
    document = _patient(extensions=[_extension(GI_URL, [("value", coding)])])

    result = convert_scanned(_scanned(document), case=case, checkpoint=Checkpoint.EHR)

    value = result.observations[0].value.to_dict()
    assert len(value["code_system" if system else "value"]) == CODING_TOKEN_LENGTH


@pytest.mark.parametrize("system", [True, False], ids=["system", "code"])
def test_a_coding_token_over_the_contract_bound_rejects_at_its_own_location(
    case: SyntheticCase, system: bool
) -> None:
    """The bound is the contract's, applied where the token sits in the source.

    Without it a 97-character system passed the reader and was rejected by
    the observation contract at ``$.observations[0].value.code_system``, a
    path that exists in no FHIR document.
    """

    coding = _coding_of_length(CODING_TOKEN_LENGTH + 1, system=system)
    document = _patient(extensions=[_extension(GI_URL, [("value", coding)])])
    with pytest.raises(ContextSafeError) as raised:
        convert_scanned(_scanned(document), case=case, checkpoint=Checkpoint.EHR)
    assert raised.value.to_dict() == {
        "code": "invalid_string",
        "path": "$.extension[0].extension[0].valueCodeableConcept.coding[0]."
        + ("system" if system else "code"),
        "message": "expected a bounded non-empty string",
    }


def test_the_rsg_context_at_the_contract_bound_is_carried(case: SyntheticCase) -> None:
    context = _coded("CSYN-" + "A" * (CODING_TOKEN_LENGTH - 5))
    document = _patient(
        extensions=[_extension(RSG_URL, [("value", _coded("X")), ("type", context)])]
    )

    result = convert_scanned(_scanned(document), case=case, checkpoint=Checkpoint.EHR)

    assert len(result.observations[0].value.to_dict()["context"]) == CODING_TOKEN_LENGTH


def test_no_rejection_the_reader_produces_names_a_converted_document_path(
    case: SyntheticCase,
) -> None:
    """Every committed rejection is located in the FHIR document, not after it."""

    for name in REJECTIONS:
        with pytest.raises(ContextSafeError) as raised:
            import_source(
                FHIR_R4_FORMAT, FIXTURES / name, case=case, checkpoint=Checkpoint.EHR
            )
        assert not raised.value.path.startswith("$.observations"), name


@pytest.mark.parametrize("part", ["value", "type"])
@pytest.mark.parametrize("code", sorted(dict(FHIR_R4_PROFILE.presence_codes)))
def test_rsg_carries_no_presence_state_and_a_data_absent_code_is_not_a_value(
    case: SyntheticCase, part: str, code: str
) -> None:
    """A data-absent ``unknown`` is not the recorded value ``unknown``.

    The canonical model has a value and a context and no status, so a
    presence coding on either sub-extension rejects as not convertible; it
    must never arrive as ``RecordedSexOrGender(value=...)`` and match a rule
    that expects a recorded value.
    """

    parts = {"value": _coded("X"), "type": _coded("CSYN-GOVERNMENT-ID")}
    parts[part] = _coded(code, PRESENCE_SYSTEM)
    document = _patient(
        extensions=[
            _extension(RSG_URL, [("value", parts["value"]), ("type", parts["type"])])
        ]
    )
    with pytest.raises(ContextSafeError) as raised:
        convert_scanned(_scanned(document), case=case, checkpoint=Checkpoint.EHR)
    assert raised.value.code == ImportErrorCode.CONCEPT_NOT_CONVERTIBLE.value
    assert raised.value.path == "$.extension[0]"
    assert code not in raised.value.message
    assert not Draft202012Validator(PROFILE_SCHEMA).is_valid(document)


def test_a_recorded_unknown_and_a_data_absent_unknown_are_not_the_same(
    case: SyntheticCase,
) -> None:
    """The one token the two alphabets share converts only from a value system."""

    recorded = _patient(
        extensions=[
            _extension(
                RSG_URL,
                [("value", _coded("unknown")), ("type", _coded("CSYN-GOVERNMENT-ID"))],
            )
        ]
    )
    result = convert_scanned(_scanned(recorded), case=case, checkpoint=Checkpoint.EHR)
    assert result.observations[0].value.to_dict()["value"] == "unknown"
    absent = copy.deepcopy(recorded)
    absent["extension"][0]["extension"][0]["valueCodeableConcept"] = _coded(
        "unknown", PRESENCE_SYSTEM
    )
    with pytest.raises(ContextSafeError) as raised:
        convert_scanned(_scanned(absent), case=case, checkpoint=Checkpoint.EHR)
    assert raised.value.code == ImportErrorCode.CONCEPT_NOT_CONVERTIBLE.value


def test_a_bundle_total_must_be_the_integer_one(case: SyntheticCase) -> None:
    def bundle(total: object) -> dict[str, Any]:
        return {
            "resourceType": "Bundle",
            "type": "collection",
            "total": total,
            "entry": [
                {
                    "resource": _patient(
                        names=[{"use": "usual", "given": ["CSYN-ASTER"]}]
                    )
                }
            ],
        }

    accepted = convert_scanned(
        _scanned(bundle(1)), case=case, checkpoint=Checkpoint.EHR
    )
    assert len(accepted.observations) == 1
    for total in (1.0, True, 2, 0, "1"):
        with pytest.raises(ContextSafeError) as raised:
            convert_scanned(
                _scanned(bundle(total)), case=case, checkpoint=Checkpoint.EHR
            )
        assert raised.value.code == ImportErrorCode.CARDINALITY_UNSUPPORTED.value
        assert raised.value.path == "$.total"


def test_a_rejection_under_a_name_is_located_under_the_name() -> None:
    """``name`` is a path key: the location says ``$.name[0]``, not ``$[0]``."""

    document = _patient(names=[{"use": "usual", "given": ["CSYN-ASTER"], "text": "x"}])
    with pytest.raises(ContextSafeError) as raised:
        _scanned(document)
    assert (raised.value.code, raised.value.path) == ("prohibited_field", "$.name[0]")


def test_a_name_with_no_part_rejects_and_a_family_only_name_is_read(
    case: SyntheticCase,
) -> None:
    usual = {"use": "usual", "given": ["CSYN-ASTER"]}
    with pytest.raises(ContextSafeError) as raised:
        convert_scanned(
            _scanned(_patient(names=[usual, {"use": "official"}])),
            case=case,
            checkpoint=Checkpoint.EHR,
        )
    assert raised.value.code == ImportErrorCode.CARDINALITY_UNSUPPORTED.value
    assert raised.value.path == "$.name[1]"
    result = convert_scanned(
        _scanned(
            _patient(names=[usual, {"use": "official", "family": "ZZZTESTCONTEXTSAFE"}])
        ),
        case=case,
        checkpoint=Checkpoint.EHR,
    )
    assert [item.evidence.source_pointer for item in result.observations] == ["/name/0"]


def test_the_case_document_never_supplies_a_value(case: SyntheticCase) -> None:
    document = _patient(names=[{"use": "usual", "given": ["CSYN-OTHER"]}])
    result = convert_scanned(_scanned(document), case=case, checkpoint=Checkpoint.EHR)
    assert result.observations[0].value.to_dict()["value"] == "CSYN-OTHER"
    assert result.observations[0].value != case.name_to_use


def test_a_second_synthetic_identifier_is_allowed_but_the_case_token_is_required(
    case: SyntheticCase,
) -> None:
    document = _patient(names=[{"use": "usual", "given": ["CSYN-ASTER"]}])
    document["identifier"].append(
        {"system": "urn:contextsafe:synthetic", "value": "CSYN-LOCAL-TOKEN-1"}
    )
    assert (
        len(
            convert_scanned(
                _scanned(document), case=case, checkpoint=Checkpoint.EHR
            ).observations
        )
        == 1
    )
    document["identifier"] = document["identifier"][1:]
    with pytest.raises(ContextSafeError) as raised:
        convert_scanned(_scanned(document), case=case, checkpoint=Checkpoint.EHR)
    assert raised.value.code == ImportErrorCode.CASE_MISMATCH.value


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        (
            lambda d: d.update({"identifier": []}),
            ImportErrorCode.CARDINALITY_UNSUPPORTED.value,
        ),
        (lambda d: d.update({"identifier": "CSYN-CTP-I01"}), "invalid_type"),
        (lambda d: d.update({"active": "true"}), "invalid_type"),
        (lambda d: d["extension"].append({"extension": []}), "missing_field"),
        (
            lambda d: d["extension"].append({"url": GI_URL, "extension": []}),
            ImportErrorCode.CARDINALITY_UNSUPPORTED.value,
        ),
        (
            lambda d: d["extension"].append(_extension(GI_URL, [])),
            ImportErrorCode.CARDINALITY_UNSUPPORTED.value,
        ),
        (
            lambda d: d["extension"].append(
                _extension(RSG_URL, [("type", _coded("CSYN-ID"))])
            ),
            ImportErrorCode.VALUE_MISSING.value,
        ),
        (
            lambda d: d["extension"].append(
                _extension(GI_URL, [("value", {"coding": []})])
            ),
            ImportErrorCode.CARDINALITY_UNSUPPORTED.value,
        ),
        (
            lambda d: d["extension"].append(
                _extension(GI_URL, [("value", {"coding": [{"code": "CSYN-X"}]})])
            ),
            "missing_field",
        ),
        (
            lambda d: d["extension"].append(
                _extension(
                    GI_URL,
                    [("value", {"coding": [{"system": "urn:x", "code": "CSYN X"}]})],
                )
            ),
            "invalid_format",
        ),
        (
            lambda d: d["name"].append({"use": "usual", "given": []}),
            ImportErrorCode.CARDINALITY_UNSUPPORTED.value,
        ),
        (
            lambda d: d["name"].append({"use": "usual"}),
            ImportErrorCode.CARDINALITY_UNSUPPORTED.value,
        ),
        (
            lambda d: d["name"].append({"use": "usual", "given": "CSYN-ASTER"}),
            "invalid_type",
        ),
        (
            lambda d: d["name"].append({"use": "legal", "given": ["CSYN-ASTER"]}),
            "invalid_enum",
        ),
        (
            lambda d: d["name"].append(
                {"use": "old", "given": ["CSYN-ASTER"], "period": {}}
            ),
            ImportErrorCode.ELEMENT_UNSUPPORTED.value,
        ),
        (
            lambda d: d.update({"generalPractitioner": []}),
            ImportErrorCode.REFERENCE_OUTSIDE_DOCUMENT.value,
        ),
        (
            lambda d: d.update({"link": []}),
            ImportErrorCode.REFERENCE_OUTSIDE_DOCUMENT.value,
        ),
        (lambda d: d.update({"resourceType": 1}), "invalid_string"),
        (lambda d: d.pop("resourceType"), "missing_field"),
    ],
    ids=[
        "no-identifier",
        "identifier-not-a-list",
        "active-not-a-boolean",
        "extension-without-url",
        "extension-without-parts",
        "gender-identity-without-value",
        "rsg-without-value",
        "no-coding",
        "coding-without-system",
        "code-with-whitespace",
        "usual-name-empty-given",
        "usual-name-no-given",
        "given-not-a-list",
        "name-use-outside-fhir",
        "name-with-period",
        "general-practitioner",
        "link",
        "resource-type-not-a-string",
        "resource-type-missing",
    ],
)
def test_malformed_shapes_reject_with_a_category_and_a_location(
    case: SyntheticCase, mutation: Any, expected_code: str
) -> None:
    document = _patient(
        extensions=[_extension(GI_URL, [("value", _coded("CSYN-GENDER-1"))])],
        names=[{"use": "usual", "given": ["CSYN-ASTER"]}],
    )
    mutation(document)
    with pytest.raises(ContextSafeError) as raised:
        convert_scanned(_scanned(document), case=case, checkpoint=Checkpoint.EHR)
    assert raised.value.code == expected_code
    assert "CSYN" not in raised.value.message


def test_a_list_over_the_bound_rejects(case: SyntheticCase) -> None:
    document = _patient(
        extensions=[_extension(GI_URL, [("value", _coded("CSYN-GENDER-1"))])] * 65
    )
    with pytest.raises(ContextSafeError) as raised:
        convert_scanned(_scanned(document), case=case, checkpoint=Checkpoint.EHR)
    assert raised.value.code == ImportErrorCode.CARDINALITY_UNSUPPORTED.value
    assert raised.value.path == "$.extension"
    document["extension"] = document["extension"][:64]
    assert (
        len(
            convert_scanned(
                _scanned(document), case=case, checkpoint=Checkpoint.EHR
            ).observations
        )
        == 64
    )


def test_a_bundle_with_a_non_patient_root_or_no_entries_rejects(
    case: SyntheticCase,
) -> None:
    with pytest.raises(ContextSafeError) as raised:
        convert_scanned(
            _scanned({"resourceType": "Bundle", "type": "collection", "entry": []}),
            case=case,
            checkpoint=Checkpoint.EHR,
        )
    assert raised.value.code == ImportErrorCode.CARDINALITY_UNSUPPORTED.value
    with pytest.raises(ContextSafeError) as raised:
        convert_scanned(
            _scanned(
                {
                    "resourceType": "Bundle",
                    "type": "collection",
                    "entry": [{"resource": {}, "fullUrl": "urn:uuid:CSYN"}],
                }
            ),
            case=case,
            checkpoint=Checkpoint.EHR,
        )
    assert raised.value.code == ImportErrorCode.ELEMENT_UNSUPPORTED.value
    with pytest.raises(ContextSafeError) as raised:
        convert_scanned(
            _scanned(
                {
                    "resourceType": "Bundle",
                    "type": "collection",
                    "entry": [{"resource": {}}],
                }
            ),
            case=case,
            checkpoint=Checkpoint.EHR,
        )
    assert raised.value.code == "missing_field"
    with pytest.raises(ContextSafeError) as raised:
        convert_scanned(
            _scanned(
                {
                    "resourceType": "Bundle",
                    "type": "collection",
                    "total": True,
                    "entry": [{"resource": _patient()}],
                }
            ),
            case=case,
            checkpoint=Checkpoint.EHR,
        )
    assert raised.value.code == ImportErrorCode.CARDINALITY_UNSUPPORTED.value
    with pytest.raises(ContextSafeError) as raised:
        convert_scanned(_scanned([]), case=case, checkpoint=Checkpoint.EHR)
    assert raised.value.code == "invalid_type"


# --- schema and runtime agree on every committed fixture ----------------------


def test_the_profile_schema_is_a_published_contract() -> None:
    Draft202012Validator.check_schema(PROFILE_SCHEMA)
    assert PROFILE_SCHEMA["$id"].endswith(
        "/schemas/contextsafe-fhir-r4-source-v0.1.schema.json"
    )
    assert "ungoverned" in PROFILE_SCHEMA["description"]


@pytest.mark.parametrize(
    "name", ["fhir-patient.json", *sorted(ACCEPTED)], ids=lambda name: name
)
def test_every_accepted_document_validates_against_the_profile_schema(
    name: str,
) -> None:
    root = REFERENCE if name == "fhir-patient.json" else FIXTURES
    Draft202012Validator(PROFILE_SCHEMA).validate(
        json.loads((root / name).read_text(encoding="utf-8"))
    )


@pytest.mark.parametrize("name", sorted(REJECTIONS))
def test_every_rejection_the_schema_can_see_fails_it(name: str) -> None:
    valid = Draft202012Validator(PROFILE_SCHEMA).is_valid(_fixture(name))
    assert valid == (name in SCHEMA_BLIND_REJECTIONS), name


# --- the command line ---------------------------------------------------------


def test_cli_lists_the_format_and_imports_read_only(
    tmp_path: Path,
    case_json: dict[str, Any],
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert FHIR_R4_FORMAT in available_formats()
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "patient.json"
    source.write_bytes((REFERENCE / "fhir-patient.json").read_bytes())
    before = source.read_bytes()
    case_path = _write(tmp_path / "case.json", case_json)

    assert main(_import_args(source, case_path)) == EXIT_SUCCESS

    captured = capsys.readouterr()
    assert captured.err == ""
    document = json.loads(captured.out)
    assert document["schema_version"] == "contextsafe.observation-set/0.1.0"
    assert [
        item["evidence"]["source_pointer"] for item in document["observations"]
    ] == [
        "/extension/0",
        "/extension/1",
        "/extension/2",
        "/name/0",
    ]
    assert {item.name for item in tmp_path.iterdir()} == {"patient.json", "case.json"}
    assert source.read_bytes() == before

    output = tmp_path / "observations.json"
    assert (
        main(
            [
                *_import_args(source, case_path),
                "--quiet",
                "--no-color",
                "--output",
                str(output),
            ]
        )
        == EXIT_SUCCESS
    )
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == ""
    assert output.read_bytes() == canonical_json(document).encode("utf-8") + b"\n"
    assert b"\x1b" not in output.read_bytes()


def test_cli_rejection_is_one_json_error_without_content_and_no_output(
    tmp_path: Path, case_json: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    case_path = _write(tmp_path / "case.json", case_json)
    output = tmp_path / "observations.json"
    log_dir = tmp_path / "log"
    assert (
        main(
            [
                *_import_args(FIXTURES / "reject-name-not-synthetic.json", case_path),
                "--output",
                str(output),
                "--log-dir",
                str(log_dir),
            ]
        )
        == EXIT_CONTRACT_ERROR
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    error = json.loads(captured.err)["error"]
    assert error["code"] == ImportErrorCode.VALUE_UNSUPPORTED.value
    assert error["path"] == "$.name[1].family"
    assert "Notsynthetic" not in captured.err
    assert str(tmp_path) not in captured.err
    assert not output.exists()
    records = [
        json.loads(line)
        for path in log_dir.iterdir()
        for line in path.read_text(encoding="utf-8").splitlines()
    ]
    assert [(item["command"], item["outcome"]) for item in records] == [
        ("import", "rejected")
    ]
    assert "Notsynthetic" not in json.dumps(records)


def test_cli_format_choices_are_the_registry(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(
            [
                "import",
                "--format",
                "hl7-v2-er7",
                "--source",
                "a",
                "--case",
                "b",
                "--checkpoint",
                "ehr",
            ]
        )
    assert raised.value.code == EXIT_USAGE_ERROR
    assert FHIR_R4_FORMAT in capsys.readouterr().err


# --- properties ---------------------------------------------------------------

_TOKEN_SUFFIX = st.text(alphabet="ABCDEFGH0123456789", min_size=1, max_size=6)
"""At most six characters, so no drawn token can carry a seven-digit run.

The long-digit-run detector is a boundary rule, not a shape this suite is
testing; a token that trips it is rejected by the scan before the reader
runs, which is correct and is pinned elsewhere.
"""
_CASE = parse_case(json.loads((REFERENCE / "case.json").read_text(encoding="utf-8")))
_CASE_JSON = json.loads((REFERENCE / "case.json").read_text(encoding="utf-8"))
_RULES_JSON = json.loads((REFERENCE / "rules.json").read_text(encoding="utf-8"))
_PATIENT_KEYS = frozenset(
    {"resourceType", "id", "identifier", "active", "name", "extension"}
)


_USUAL_NAME: dict[str, Any] = {"use": "usual", "given": ["CSYN-ASTER"]}
_SCAN_REJECTIONS: tuple[tuple[str, str], ...] = (
    ("unapproved_free_text", "strings cannot contain boundary whitespace"),
    ("prohibited_unicode", "control and format characters are prohibited"),
    ("phi_canary_detected", "a configured PHI canary was detected"),
    ("direct_identifier_detected", "a direct-identifier pattern was detected"),
)
"""The boundary scan's string rejections: fixed sentences, no value in any."""
_PROHIBITED_FIELD_MESSAGE = "a free-text or identifying field is prohibited"
_ELEMENT_UNSUPPORTED_MESSAGE = (
    "an element is outside this profile's allowlist; nothing is stripped and "
    "the source is rejected whole"
)
_REFERENCE_MESSAGE = "a reference cannot resolve to a resource in this document"
_INVALID_STRING_MESSAGE = "expected a bounded non-empty string"
_INVALID_UNICODE_MESSAGE = "string must contain only Unicode scalar values"


def _element_rejections(key: str) -> tuple[dict[str, str], ...]:
    """Every error object one element outside the allowlist may produce.

    The set is closed and every message is a fixed sentence from the code
    path that emits it, so membership proves the rejection carried no part
    of the drawn key or value. A location is ``$`` or ``$.<key>``, and the
    latter only when the key is one of the profile's own safe path keys: the
    scan locates a string value under its key only for names it already
    knows, so a drawn key that is not an element name never reaches a path.
    """

    paths = ["$"]
    if key in FHIR_R4_BOUNDARY_PROFILE.safe_path_keys():
        paths.append(f"$.{key}")
    rejections: list[dict[str, str]] = [
        {
            "code": ImportErrorCode.ELEMENT_UNSUPPORTED.value,
            "message": _ELEMENT_UNSUPPORTED_MESSAGE,
            "path": "$",
        },
        {"code": "prohibited_field", "message": _PROHIBITED_FIELD_MESSAGE, "path": "$"},
    ]
    if key in _PATIENT_REFERENCE_KEYS:
        rejections.append(
            {
                "code": ImportErrorCode.REFERENCE_OUTSIDE_DOCUMENT.value,
                "message": _REFERENCE_MESSAGE,
                "path": f"$.{key}",
            }
        )
    rejections.extend(
        {"code": code, "message": message, "path": path}
        for path in paths
        for code, message in _SCAN_REJECTIONS
    )
    return tuple(rejections)


_IDENTIFIER_REJECTIONS: tuple[dict[str, str], ...] = (
    {
        "code": ImportErrorCode.IDENTIFIER_NOT_SYNTHETIC.value,
        "message": "every identifier must be in the synthetic namespace",
        "path": "$.identifier[0]",
    },
    {
        "code": ImportErrorCode.CASE_MISMATCH.value,
        "message": "no identifier carries the case document's synthetic token",
        "path": "$.identifier",
    },
    *(
        {"code": code, "message": message, "path": f"$.identifier[0].{field}"}
        for field in ("system", "value")
        for code, message in (
            ("invalid_string", _INVALID_STRING_MESSAGE),
            ("invalid_unicode", _INVALID_UNICODE_MESSAGE),
            *_SCAN_REJECTIONS,
        )
    ),
)
"""Every error object a rejected identifier may produce (closed)."""


@st.composite
def _documents(draw: st.DrawFn) -> tuple[dict[str, Any], dict[ConceptKind, int]]:
    """A Patient with a drawn number of carriers per concept, and the counts."""

    gender = draw(st.integers(min_value=0, max_value=3))
    pronouns = draw(st.integers(min_value=0, max_value=2))
    rsg = draw(st.integers(min_value=0, max_value=2))
    usual = draw(st.integers(min_value=0, max_value=3))
    other = draw(st.integers(min_value=0, max_value=2))
    extensions: list[dict[str, Any]] = []
    for _ in range(gender):
        code = draw(
            st.one_of(
                _TOKEN_SUFFIX.map(lambda s: _coded(f"CSYN-GENDER-{s}")),
                st.sampled_from(("asked-declined", "unknown", "not-asked")).map(
                    lambda s: _coded(s, PRESENCE_SYSTEM)
                ),
            )
        )
        extensions.append(_extension(GI_URL, [("value", code)]))
    extensions.extend(
        _extension(
            PRONOUNS_URL, [("value", _coded(f"CSYN-PRONOUN-{draw(_TOKEN_SUFFIX)}"))]
        )
        for _ in range(pronouns)
    )
    extensions.extend(
        _extension(
            RSG_URL,
            [
                ("value", _coded(draw(st.sampled_from(("F", "M", "X", "unknown"))))),
                ("type", _coded(f"CSYN-CONTEXT-{draw(_TOKEN_SUFFIX)}")),
            ],
        )
        for _ in range(rsg)
    )
    draw(st.randoms()).shuffle(extensions)
    names = [
        {"use": "usual", "given": [f"CSYN-{draw(_TOKEN_SUFFIX)}"]} for _ in range(usual)
    ] + [
        {
            "use": draw(st.sampled_from(("official", "old", "nickname"))),
            "family": "ZZZTESTCONTEXTSAFE",
            "given": [f"CSYN-{draw(_TOKEN_SUFFIX)}"],
        }
        for _ in range(other)
    ]
    document = _patient(extensions=extensions or None, names=names or None)
    counts = {
        ConceptKind.GENDER_IDENTITY: gender,
        ConceptKind.PRONOUNS: pronouns,
        ConceptKind.RECORDED_SEX_OR_GENDER: rsg,
        ConceptKind.NAME_TO_USE: usual,
        ConceptKind.SEX_PARAMETER_FOR_CLINICAL_USE: 0,
    }
    return document, counts


@settings(max_examples=150, deadline=None)
@given(example=_documents())
def test_one_observation_per_carrier_and_more_than_one_is_ambiguous(
    example: tuple[dict[str, Any], dict[ConceptKind, int]],
) -> None:
    document, counts = example
    if sum(counts.values()) == 0:
        with pytest.raises(ContextSafeError) as raised:
            convert_scanned(_scanned(document), case=_CASE, checkpoint=Checkpoint.EHR)
        assert raised.value.code == ImportErrorCode.CARDINALITY_UNSUPPORTED.value
        return
    first = convert_scanned(_scanned(document), case=_CASE, checkpoint=Checkpoint.EHR)
    second = convert_scanned(
        _scanned(copy.deepcopy(document)), case=_CASE, checkpoint=Checkpoint.EHR
    )
    assert canonical_json(first.observation_set()) == canonical_json(
        second.observation_set()
    )
    observed = {concept: 0 for concept in ConceptKind}
    for item in first.observations:
        observed[item.concept] += 1
    assert observed == counts
    pointers = [item.evidence.source_pointer for item in first.observations]
    assert len(set(pointers)) == len(pointers)
    for outcome in evaluate(
        parse_bundle(_CASE_JSON, first.observation_set(), _RULES_JSON)
    ):
        if outcome.checkpoint != Checkpoint.EHR.value:
            assert outcome.reason.value == "missing_evidence"
        elif counts[outcome.concept] > 1:
            assert outcome.reason.value == "ambiguous_evidence"
            assert outcome.status.value == "indeterminate"
        elif counts[outcome.concept] == 0:
            assert outcome.reason.value == "missing_evidence"
        else:
            assert outcome.status.value in {"pass", "fail"}


@settings(max_examples=150, deadline=None)
@example(example=(_patient(names=[_USUAL_NAME]), {}), key="m", value=None)
@example(example=(_patient(names=[_USUAL_NAME]), {}), key=" ", value=None)
@example(example=(_patient(names=[_USUAL_NAME]), {}), key="code", value=" x")
@example(example=(_patient(names=[_USUAL_NAME]), {}), key="link", value=None)
@example(example=(_patient(names=[_USUAL_NAME]), {}), key="birthDate", value=None)
@given(
    example=_documents(),
    key=st.text(min_size=1, max_size=24).filter(lambda s: s not in _PATIENT_KEYS),
    value=st.one_of(st.none(), st.booleans(), st.integers(), st.text(max_size=8)),
)
def test_any_element_outside_the_allowlist_rejects_the_whole_source(
    example: tuple[dict[str, Any], dict[ConceptKind, int]], key: str, value: object
) -> None:
    document, _counts = example
    document[key] = value
    with pytest.raises(ContextSafeError) as raised:
        convert_scanned(_scanned(document), case=_CASE, checkpoint=Checkpoint.EHR)
    # Structural, not substring: the error object must be one of the fixed
    # rejections at a location built from the profile's own element names.
    # A substring check cannot prove a value was not echoed, because a
    # one-character draw is a substring of every English sentence.
    assert raised.value.to_dict() in _element_rejections(key)


@settings(max_examples=150, deadline=None)
@example(
    example=(_patient(names=[_USUAL_NAME]), {}),
    system="urn:contextsafe:synthetic",
    value="m",
)
@example(example=(_patient(names=[_USUAL_NAME]), {}), system="", value="CSYN-CTP-I01")
@example(
    example=(_patient(names=[_USUAL_NAME]), {}), system="urn:example:real", value=" "
)
@example(
    example=(_patient(names=[_USUAL_NAME]), {}),
    system="urn:contextsafe:synthetic",
    value="CSYN-CTP-Z99",
)
@given(
    example=_documents(),
    system=st.sampled_from(("urn:contextsafe:synthetic", "urn:example:real", "")),
    value=st.one_of(
        st.sampled_from(("CTP-I01", "CSYN-CTP-Z99", "MRN-12345", "12345678", "")),
        st.text(min_size=1, max_size=24).filter(lambda s: s != "CSYN-CTP-I01"),
    ),
)
def test_any_identifier_outside_the_case_namespace_rejects(
    example: tuple[dict[str, Any], dict[ConceptKind, int]], system: str, value: str
) -> None:
    document, _counts = example
    document["identifier"] = [{"system": system, "value": value}]
    with pytest.raises(ContextSafeError) as raised:
        convert_scanned(_scanned(document), case=_CASE, checkpoint=Checkpoint.EHR)
    # Structural, not substring: the error object must be one of the fixed
    # identifier rejections, whose messages are sentences that name no value.
    assert raised.value.to_dict() in _IDENTIFIER_REJECTIONS


def test_the_registered_importer_reports_the_profile_version() -> None:
    importer = importer_for(FHIR_R4_FORMAT)
    assert importer.format_name == FHIR_R4_FORMAT
    assert (
        importer.mapping_version == FHIR_R4_MAPPING_VERSION == FHIR_R4_PROFILE.version
    )


def test_presence_codes_are_the_profile_and_nothing_else() -> None:
    assert dict(FHIR_R4_PROFILE.presence_codes) == {
        "asked-declined": ValueStatus.DECLINED,
        "unknown": ValueStatus.UNKNOWN,
        "not-asked": ValueStatus.ABSENT,
    }
    assert ValueStatus.SPECIFIED not in dict(FHIR_R4_PROFILE.presence_codes).values()
