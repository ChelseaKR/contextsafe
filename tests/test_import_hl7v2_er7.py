"""The HL7 v2 ER7 importer and its reference-only profile (B-024).

Four things this module pins. The parse is exact: delimiters come from
MSH-1 and MSH-2 and nothing else, the five delimiter escapes round-trip and
every other escape rejects, and the same logical message under any legal
delimiter set converts to the same observations. The conversion is whole: a
segment outside the allowlist, a populated field outside the profile, a
repetition where the profile admits one value, free text, an identifier
outside the synthetic namespace, or a value the observation contract rejects
fails the message and produces nothing, with a code and a location and never
the content. The concepts stay distinct by construction: no message can put
a PID-8 value anywhere but recorded sex or gender with the context
``administrative``, and the label an observation carries is a function of
the type of its value. And the conversion does not claim what it cannot: the
profile says ``profile_reviewed`` is false and refuses otherwise, the
checkpoint is the caller's and the result says so, and a message without a
name to use produces no name observation rather than a default.
"""

import ast
import hashlib
import json
import os
import typing
from pathlib import Path
from typing import Any

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st
from jsonschema import Draft202012Validator

import contextsafe.preflight as preflight_module
from contextsafe.canonical import canonical_json
from contextsafe.cli import EXIT_CONTRACT_ERROR, EXIT_SUCCESS, main
from contextsafe.errors import ContextSafeError
from contextsafe.evaluator import evaluate
from contextsafe.importers import REGISTRY, ImportErrorCode, ImportWarningCode
from contextsafe.importers import hl7v2_er7 as module
from contextsafe.importers.hl7v2_er7 import (
    _CONCEPT_OF_TYPE,
    ADMINISTRATIVE_CONTEXT,
    GSP_SOURCE,
    HL7V2_ER7_FORMAT,
    HL7V2_ER7_MAPPING_VERSION,
    HL7V2_ER7_PROFILE,
    PID_8_SOURCE,
    UNBOUND_CONTEXT,
    Hl7RejectionCode,
    Hl7v2Profile,
    convert_raw,
    parse_er7,
)
from contextsafe.models import (
    Checkpoint,
    ConceptKind,
    GenderIdentity,
    NameToUse,
    Pronouns,
    RecordedSexOrGender,
    SexParameterForClinicalUse,
    SyntheticCase,
)
from contextsafe.preflight import MAX_EVIDENCE_BYTES, RawSource, read_source
from contextsafe.reference_fixtures import REFERENCE_ROOT
from contextsafe.validation import parse_bundle, parse_case, parse_observations

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = REFERENCE_ROOT
REJECTIONS = ROOT / "tests" / "fixtures" / "hl7v2"
OBSERVATION_SET_SCHEMA = json.loads(
    (ROOT / "schemas" / "contextsafe-observation-set-v0.1.schema.json").read_text(
        encoding="utf-8"
    )
)

MSH = (
    "MSH|^~\\&|CSYN-SENDER|CSYN-FACILITY|CSYN-RECEIVER|CSYN-LAB|20260904120000||"
    "ADT^A08^ADT_A01|CSYN-MSG-I01-0001|T|2.9.1|||AL|NE||UNICODE UTF-8"
)
PID = (
    "PID|1||CSYN-CTP-I01^^^&urn:contextsafe:synthetic&URI^MR||"
    "ZZZTESTCONTEXTSAFE^CSYN-ASTER^^^^^D~ZZZTESTCONTEXTSAFE^CSYN-LEGAL-I01^^^^^L|||X"
)
GI = "GSP|1|A||76691-5^^LN|fixture-gender-1^^urn:contextsafe:fixture"
PRN = "GSP|2|A||90778-2^^LN|they/them"
OBR = "OBR|1|ORDER-CSYN-I01-A||CSYN-SERVICE-A^^urn:contextsafe:fixture"
OBX = "OBX|1|CWE|CSYN-SUPPORT^^urn:contextsafe:fixture||SUP-CSYN-I01-A||||||F"
SPCU = "GSP|3|A||99501-9^^LN|fixture-context-1"
ACCEPTING = (MSH, PID, GI, PRN, OBR, OBX, SPCU)
"""The reference message, segment by segment, so a test can vary one."""

_CASE = parse_case(json.loads((REFERENCE / "case.json").read_text(encoding="utf-8")))
_CASE_JSON = json.loads((REFERENCE / "case.json").read_text(encoding="utf-8"))


def _encode(segments: tuple[str, ...] | list[str]) -> bytes:
    return ("\r".join(segments) + "\r").encode("utf-8")


def _raw(data: bytes) -> RawSource:
    return RawSource(
        raw_sha256=hashlib.sha256(data).hexdigest(), raw_byte_count=len(data), raw=data
    )


def _convert(
    segments: tuple[str, ...] | list[str],
    checkpoint: Checkpoint = Checkpoint.EHR,
    case: SyntheticCase = _CASE,
) -> Any:
    return convert_raw(_raw(_encode(segments)), case=case, checkpoint=checkpoint)


def _rejected(
    segments: tuple[str, ...] | list[str], code: str, path: str | None = None
) -> ContextSafeError:
    with pytest.raises(ContextSafeError) as raised:
        _convert(segments)
    assert raised.value.code == code, raised.value
    if path is not None:
        assert raised.value.path == path
    return raised.value


def _with(index: int, segment: str) -> list[str]:
    segments = list(ACCEPTING)
    segments[index] = segment
    return segments


def _import_args(source: Path, case_path: Path, checkpoint: str = "ehr") -> list[str]:
    return [
        "import",
        "--format",
        HL7V2_ER7_FORMAT,
        "--source",
        str(source),
        "--case",
        str(case_path),
        "--checkpoint",
        checkpoint,
    ]


@pytest.fixture
def case_path(tmp_path: Path, case_json: dict[str, Any]) -> Path:
    path = tmp_path / "case.json"
    path.write_text(json.dumps(case_json), encoding="utf-8")
    return path


# --- the reference round trip -------------------------------------------------


def test_reference_message_converts_to_five_typed_observations() -> None:
    source = REFERENCE / "hl7v2-er7-message.hl7"
    raw = source.read_bytes()
    result = REGISTRY[HL7V2_ER7_FORMAT].convert(
        source, case=_CASE, checkpoint=Checkpoint.EHR
    )

    assert result.record_count == len(result.observations) == 5
    assert result.source_sha256 == hashlib.sha256(raw).hexdigest()
    assert result.source_byte_count == len(raw)
    assert result.profile_reviewed is False
    assert set(result.warnings) == {
        ImportWarningCode.CHECKPOINT_NOT_IN_SOURCE,
        ImportWarningCode.MAPPING_PROFILE_NOT_BOUND,
    }
    by_concept = {item.concept: item for item in result.observations}
    assert [item.concept for item in result.observations] == [
        ConceptKind.NAME_TO_USE,
        ConceptKind.RECORDED_SEX_OR_GENDER,
        ConceptKind.GENDER_IDENTITY,
        ConceptKind.PRONOUNS,
        ConceptKind.SEX_PARAMETER_FOR_CLINICAL_USE,
    ]
    assert [item.evidence.source_pointer for item in result.observations] == [
        "$.PID[1]-5.1.2",
        "$.PID[1]-8.1.1",
        "$.GSP[1]-5.1.1",
        "$.GSP[2]-5.1.1",
        "$.GSP[3]-5.1.1",
    ]
    assert by_concept[ConceptKind.NAME_TO_USE].value.to_dict() == {
        "status": "specified",
        "use": "usual",
        "value": "CSYN-ASTER",
    }
    assert by_concept[ConceptKind.RECORDED_SEX_OR_GENDER].value.to_dict() == {
        "context": ADMINISTRATIVE_CONTEXT,
        "source": PID_8_SOURCE,
        "value": "X",
    }
    assert by_concept[ConceptKind.GENDER_IDENTITY].value.to_dict() == {
        "code_system": "urn:contextsafe:fixture",
        "status": "specified",
        "value": "fixture-gender-1",
    }
    assert by_concept[ConceptKind.PRONOUNS].value.to_dict() == {
        "status": "specified",
        "value": "they/them",
    }
    assert by_concept[ConceptKind.SEX_PARAMETER_FOR_CLINICAL_USE].value.to_dict() == {
        "context_id": "ORDER-CSYN-I01-A",
        "supporting_observation_ids": ["SUP-CSYN-I01-A"],
        "value": "fixture-context-1",
    }
    for index, item in enumerate(result.observations):
        assert item.observation_id == f"OBS-CTP-I01-R{index:04d}"
        assert item.checkpoint is Checkpoint.EHR
        assert item.evidence.source_sha256 == result.source_sha256
        assert item.mapping.mapping_version == HL7V2_ER7_MAPPING_VERSION
        assert (
            item.mapping.source_concept is item.mapping.target_concept is item.concept
        )
    report = result.to_dict()
    assert report["persisted"] is False
    assert report["profile_reviewed"] is False


def test_emitted_document_validates_and_evaluates_without_a_false_pass(
    rules_json: dict[str, Any],
) -> None:
    """Contract and runtime agree on the shape; the receipt says what it can.

    The message carries the case's own tokens at ``ehr``, so the three rules
    at ``ehr`` pass on exact match. The rules at ``registration`` and
    ``interface`` have no observation at their checkpoint, and an ``ehr``
    observation is not borrowed for them: they stay indeterminate.
    """

    result = _convert(ACCEPTING)
    document = result.observation_set()
    Draft202012Validator.check_schema(OBSERVATION_SET_SCHEMA)
    Draft202012Validator(OBSERVATION_SET_SCHEMA).validate(document)
    assert [item.to_dict() for item in parse_observations(document)] == document[
        "observations"
    ]
    bundle = parse_bundle(_CASE_JSON, document, rules_json)
    by_rule = {item.rule_id: item for item in evaluate(bundle)}
    assert {rule: item.status.value for rule, item in by_rule.items()} == {
        "A-I01": "pass",
        "A-I02": "indeterminate",
        "A-I03": "indeterminate",
        "A-I04": "pass",
        "A-I05": "pass",
    }
    assert by_rule["A-I02"].reason.value == "missing_evidence"


def test_the_legal_test_name_is_read_for_shape_and_never_emitted() -> None:
    result = _convert(ACCEPTING)
    emitted = canonical_json(result.observation_set())
    assert "CSYN-LEGAL-I01" not in emitted
    assert "ZZZTESTCONTEXTSAFE" not in emitted
    assert "20260904120000" not in emitted
    assert "CSYN-MSG-I01-0001" not in emitted


# --- the committed rejection fixtures ----------------------------------------


@pytest.mark.parametrize(
    ("name", "code", "path", "content"),
    [
        ("z-segment", ImportErrorCode.SEGMENT_NOT_ALLOWED.value, "$[7]", "ZPI"),
        (
            "free-text-obx",
            "unapproved_free_text",
            "$.OBX[1]-2.1.1",
            "CSYN-FREE-TEXT-TOKEN",
        ),
        (
            "non-synthetic-mrn",
            ImportErrorCode.IDENTIFIER_NOT_SYNTHETIC.value,
            "$.PID[1]-3.1.1",
            "12345",
        ),
    ],
)
def test_rejection_fixtures_reject_whole_with_a_code_and_a_location(
    name: str, code: str, path: str, content: str
) -> None:
    with pytest.raises(ContextSafeError) as raised:
        REGISTRY[HL7V2_ER7_FORMAT].convert(
            REJECTIONS / f"{name}.hl7", case=_CASE, checkpoint=Checkpoint.EHR
        )
    assert raised.value.code == code
    assert raised.value.path == path
    assert content not in str(raised.value)


# --- delimiters and escapes ---------------------------------------------------

_DELIMITER_ALPHABET = "!\"#$%&'()*,;<=>?@[\\]^`{|}~"
"""Every printable non-alphanumeric ASCII character that cannot be in a token.

A sender whose delimiter also occurs inside a value escapes the value; this
test re-encodes the reference message by translation, so it draws only from
characters the message's tokens cannot contain (``+-./:_`` are token
characters and are left out here).
"""

_DELIMITER_SETS = st.lists(
    st.sampled_from(_DELIMITER_ALPHABET), min_size=5, max_size=5, unique=True
).map(lambda items: "".join(items))


def _re_encode(segment: str, delimiters: str) -> str:
    """Rewrite one standard-delimited segment under another delimiter set."""

    standard = "|^~\\&"
    if segment.startswith("MSH"):
        return (
            "MSH"
            + delimiters
            + segment[8:].translate(str.maketrans(standard, delimiters))
        )
    return segment.translate(str.maketrans(standard, delimiters))


@settings(max_examples=150, deadline=None)
@given(delimiters=_DELIMITER_SETS)
def test_any_legal_delimiter_set_converts_to_the_same_observations(
    delimiters: str,
) -> None:
    """The five characters MSH declares are the only delimiters used."""

    baseline = _convert(ACCEPTING)
    segments = [_re_encode(item, delimiters) for item in ACCEPTING]
    converted = _convert(segments)
    for first, second in zip(
        baseline.observations, converted.observations, strict=True
    ):
        left = {k: v for k, v in first.to_dict().items() if k != "evidence"}
        right = {k: v for k, v in second.to_dict().items() if k != "evidence"}
        assert left == right
        assert first.evidence.source_pointer == second.evidence.source_pointer


@settings(max_examples=100, deadline=None)
@given(
    four=st.lists(
        st.sampled_from(_DELIMITER_ALPHABET), min_size=4, max_size=4, unique=True
    ),
    # At most six characters: the long-digit-run detector rejects a run of
    # seven or more digits after a non-alphanumeric character on purpose, and
    # `+0000000` is one, so a longer all-digit draw would be a detector
    # finding rather than a round-trip failure.
    suffix=st.text(alphabet="ABCDEF0123456789", min_size=1, max_size=6),
)
def test_an_escaped_subcomponent_separator_round_trips_into_a_token(
    four: list[str], suffix: str
) -> None:
    """``\\T\\`` becomes the subcomponent separator, and only that.

    ``+`` is the one token character no value in the reference message
    uses, so it can be the subcomponent separator without an escape
    anywhere else, and an escaped one inside a value must come back as the
    literal ``+`` in a token the contract accepts.
    """

    delimiters = "".join(four) + "+"
    escape = four[3]
    pronouns = f"CSYN{escape}T{escape}{suffix}"
    segments = [_re_encode(item, delimiters) for item in ACCEPTING]
    segments[3] = _re_encode("GSP|2|A||90778-2^^LN|", delimiters) + pronouns
    result = _convert(segments)
    value = result.observations[3].value.to_dict()["value"]
    assert value == f"CSYN+{suffix}"
    assert result.observations[3].concept is ConceptKind.PRONOUNS


@pytest.mark.parametrize(
    "escaped",
    ["\\X0D\\", "\\.br\\", "\\H\\", "\\N\\", "\\Zabc\\", "\\F", "\\", "\\FF\\"],
)
def test_every_escape_but_the_five_delimiter_escapes_rejects(escaped: str) -> None:
    _rejected(
        _with(3, f"GSP|2|A||90778-2^^LN|CSYN{escaped}X"),
        Hl7RejectionCode.ESCAPE_UNSUPPORTED.value,
        "$.GSP[2]",
    )


def test_the_five_delimiter_escapes_are_handled() -> None:
    raw = _encode(_with(3, "GSP|2|A||90778-2^^LN|A\\F\\B\\S\\C\\T\\D\\R\\E\\E\\F"))
    segments = parse_er7(raw)
    assert segments[3].text(5) == "A|B^C&D~E\\F"


@pytest.mark.parametrize(
    "header",
    [
        "MSH|^~\\&#|",
        "MSH|^^\\&|",
        "MSH|a~\\&|",
        "MSH| ^~\\&|",
        "MSH|^~\\&^",
        "MSH",
        "MSH|^~\\",
    ],
    ids=[
        "truncation-character",
        "duplicate",
        "alphanumeric",
        "whitespace",
        "wrong-closing-separator",
        "no-delimiters",
        "short",
    ],
)
def test_delimiters_come_from_msh_exactly_or_the_message_rejects(header: str) -> None:
    raw = (header + "\r").encode("utf-8")
    with pytest.raises(ContextSafeError) as raised:
        parse_er7(raw)
    assert raised.value.code in {
        Hl7RejectionCode.DELIMITERS_INVALID.value,
        Hl7RejectionCode.NOT_ER7.value,
    }


# --- structure ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        (b'{"schema_version": "x"}', Hl7RejectionCode.NOT_ER7.value),
        (b"\xef\xbb\xbf" + _encode(ACCEPTING), "prohibited_unicode"),
        (b"\xff\xfe" + _encode(ACCEPTING), "invalid_utf8"),
        (_encode(ACCEPTING)[:-1], Hl7RejectionCode.SEGMENT_TERMINATOR_INVALID.value),
        (
            ("\n".join(ACCEPTING) + "\n").encode("utf-8"),
            "prohibited_unicode",
        ),
        (
            ("\r\n".join(ACCEPTING) + "\r\n").encode("utf-8"),
            "prohibited_unicode",
        ),
        (_encode(ACCEPTING) + b"\r", Hl7RejectionCode.SEGMENT_MALFORMED.value),
        (_encode(("MSH|^~\\&|X​",)), "prohibited_unicode"),
        (_encode((*ACCEPTING, "pid|1")), Hl7RejectionCode.SEGMENT_MALFORMED.value),
        (_encode((*ACCEPTING, "PIDX")), Hl7RejectionCode.SEGMENT_MALFORMED.value),
        (_encode((*ACCEPTING, MSH)), Hl7RejectionCode.SEGMENT_ORDER_INVALID.value),
        (_encode((*ACCEPTING, PID)), Hl7RejectionCode.SEGMENT_ORDER_INVALID.value),
        (_encode((MSH,)), Hl7RejectionCode.SEGMENT_ORDER_INVALID.value),
        (_encode((MSH, GI, PID)), Hl7RejectionCode.SEGMENT_ORDER_INVALID.value),
        (_encode((MSH, PID, OBX)), Hl7RejectionCode.SEGMENT_ORDER_INVALID.value),
        (
            _encode((MSH, PID, *(["GSP|1|A||90778-2^^LN|CSYN-P"] * 1999))),
            Hl7RejectionCode.SEGMENT_COUNT_EXCEEDED.value,
        ),
    ],
    ids=[
        "json",
        "byte-order-mark",
        "not-utf8",
        "missing-final-cr",
        "lf-terminated",
        "crlf-terminated",
        "empty-segment",
        "format-character",
        "lowercase-name",
        "no-separator-after-name",
        "second-msh",
        "second-pid",
        "no-pid",
        "gsp-before-pid",
        "obx-before-obr",
        "over-segment-bound",
    ],
)
def test_structural_defects_reject_the_message(raw: bytes, code: str) -> None:
    with pytest.raises(ContextSafeError) as raised:
        convert_raw(_raw(raw), case=_CASE, checkpoint=Checkpoint.EHR)
    assert raised.value.code == code


def test_two_thousand_segments_is_the_bound_and_within_it_converts() -> None:
    segments = [MSH, PID, *(["GSP|1|A||90778-2^^LN|CSYN-P"] * 1998)]
    assert len(segments) == 2000
    result = _convert(segments)
    assert result.record_count == 2000
    assert result.observations[-1].evidence.source_pointer == "$.GSP[1998]-5.1.1"


# --- every segment: the closed allowlist ------------------------------------


@pytest.mark.parametrize(
    "name", ["ZPI", "ZZZ", "NK1", "PV1", "EVN", "GSR", "GSC", "NTE"]
)
def test_a_segment_outside_the_allowlist_rejects_by_position_not_name(
    name: str,
) -> None:
    error = _rejected(
        (*ACCEPTING, f"{name}|1|CSYN-X"),
        ImportErrorCode.SEGMENT_NOT_ALLOWED.value,
        "$[7]",
    )
    assert name not in str(error)


def test_the_allowlist_is_exactly_the_five_segments() -> None:
    assert HL7V2_ER7_PROFILE.segment_allowlist == frozenset(
        {"MSH", "PID", "GSP", "OBR", "OBX"}
    )


# --- fields beyond the profile, repetition, prohibited fields ----------------


@pytest.mark.parametrize(
    ("index", "segment", "code", "path"),
    [
        (
            1,
            "PID|1||CSYN-CTP-I01^^^urn:contextsafe:synthetic^MR||||19900101|X",
            "prohibited_field",
            "$.PID[1]-7.1.1",
        ),
        (
            1,
            PID + "|||||||||||||||CSYN-PLACE",
            "prohibited_field",
            "$.PID[1]-23.1.1",
        ),
        (
            1,
            PID + "||||||||||||||CSYN-X",
            ImportErrorCode.FIELD_NOT_IN_PROFILE.value,
            "$.PID[1]-22.1.1",
        ),
        (
            1,
            PID + "|CSYN-ALIAS",
            "prohibited_field",
            "$.PID[1]-9.1.1",
        ),
        (
            0,
            MSH.replace("||ADT", "|CSYN-SEC|ADT"),
            ImportErrorCode.FIELD_NOT_IN_PROFILE.value,
            "$.MSH[1]-8.1.1",
        ),
        (
            2,
            "GSP|1|A|20260101|76691-5^^LN|fixture-gender-1",
            ImportErrorCode.FIELD_NOT_IN_PROFILE.value,
            "$.GSP[1]-3.1.1",
        ),
        (
            2,
            "GSP|1|A||76691-5^^LN|fixture-gender-1|CSYN-COMMENT",
            ImportErrorCode.FIELD_NOT_IN_PROFILE.value,
            "$.GSP[1]-6.1.1",
        ),
        (
            1,
            PID.replace("^CSYN-ASTER^^^^^D", "^CSYN-ASTER^^JR^^^D"),
            ImportErrorCode.FIELD_NOT_IN_PROFILE.value,
            "$.PID[1]-5.1.4",
        ),
        (
            1,
            PID.replace("&URI^MR|", "&URI^MR^CSYN-FAC|"),
            ImportErrorCode.FIELD_NOT_IN_PROFILE.value,
            "$.PID[1]-3.1.6",
        ),
        (
            1,
            PID.replace("&URI^MR|", "&URI&EXTRA^MR|"),
            ImportErrorCode.FIELD_NOT_IN_PROFILE.value,
            "$.PID[1]-3.1.4",
        ),
        (
            1,
            PID.replace("CSYN-CTP-I01^^^", "CSYN-CTP-I01^7^M10^"),
            ImportErrorCode.FIELD_NOT_IN_PROFILE.value,
            "$.PID[1]-3.1.2",
        ),
        (
            2,
            "GSP|1|A||76691-5^^LN^ALT|fixture-gender-1",
            ImportErrorCode.FIELD_NOT_IN_PROFILE.value,
            "$.GSP[1]-4.1.4",
        ),
        (
            2,
            "GSP|1|A||76691-5^^LN|fixture-gender-1&SUB",
            ImportErrorCode.FIELD_NOT_IN_PROFILE.value,
            "$.GSP[1]-5.1.1",
        ),
        (
            4,
            OBR + "|CSYN-PRIORITY",
            ImportErrorCode.FIELD_NOT_IN_PROFILE.value,
            "$.OBR[1]-5.1.1",
        ),
        (
            5,
            OBX.replace("SUP-CSYN-I01-A|", "SUP-CSYN-I01-A|CSYN-UNIT"),
            ImportErrorCode.FIELD_NOT_IN_PROFILE.value,
            "$.OBX[1]-6.1.1",
        ),
    ],
    ids=[
        "pid-7-birth-date",
        "pid-23-birth-place",
        "pid-22-ethnic-group",
        "pid-9-alias",
        "msh-8-security",
        "gsp-3-validity-range",
        "gsp-6",
        "xpn-4-suffix",
        "cx-6",
        "cx-4-fourth-subcomponent",
        "cx-2-check-digit",
        "cwe-4-alternate-code",
        "cwe-1-subcomponent",
        "obr-5",
        "obx-6",
    ],
)
def test_a_populated_field_outside_the_profile_rejects(
    index: int, segment: str, code: str, path: str
) -> None:
    _rejected(_with(index, segment), code, path)


def test_an_empty_field_beyond_the_profile_is_not_content() -> None:
    result = _convert(_with(1, PID + "|" * 30))
    assert result.record_count == 5


@pytest.mark.parametrize(
    ("index", "segment", "path"),
    [
        (
            1,
            PID.replace("^MR|", "^MR~CSYN-CTP-I01^^^urn:contextsafe:synthetic^PI|"),
            "$.PID[1]-3.1.1",
        ),
        (1, PID + "~F", "$.PID[1]-8.1.1"),
        (2, GI + "~fixture-gender-2", "$.GSP[1]-5.1.1"),
        (2, "GSP|1|A||76691-5^^LN~90778-2^^LN|fixture-gender-1", "$.GSP[1]-4.1.1"),
        (
            5,
            OBX.replace("SUP-CSYN-I01-A|", "SUP-CSYN-I01-A~SUP-CSYN-I01-B|"),
            "$.OBX[1]-5.1.1",
        ),
        (0, MSH.replace("CSYN-SENDER", "CSYN-SENDER~CSYN-OTHER"), "$.MSH[1]-3.1.1"),
    ],
    ids=["pid-3", "pid-8", "gsp-5", "gsp-4", "obx-5", "msh-3"],
)
def test_repetition_where_the_profile_admits_one_value_rejects(
    index: int, segment: str, path: str
) -> None:
    _rejected(_with(index, segment), ImportErrorCode.REPETITION_NOT_ALLOWED.value, path)


def test_two_names_with_the_name_to_use_code_is_ambiguous_not_first_wins() -> None:
    _rejected(
        _with(
            1,
            PID.replace("^^^^^L|", "^^^^^D|"),
        ),
        ImportErrorCode.VALUE_AMBIGUOUS.value,
        "$.PID[1]-5.1.1",
    )


# --- MSH ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("segment", "code", "path"),
    [
        (
            MSH.replace("|T|", "|P|"),
            Hl7RejectionCode.PROCESSING_ID_NOT_TEST.value,
            "$.MSH[1]-11.1.1",
        ),
        (
            MSH.replace("|T|", "|Q|"),
            Hl7RejectionCode.PROCESSING_ID_NOT_TEST.value,
            "$.MSH[1]-11.1.1",
        ),
        (
            MSH.replace("|2.9.1|", "|2.5.1|"),
            Hl7RejectionCode.VERSION_UNSUPPORTED.value,
            "$.MSH[1]-12.1.1",
        ),
        (
            MSH.replace("UNICODE UTF-8", "8859/1"),
            Hl7RejectionCode.CHARACTER_SET_UNSUPPORTED.value,
            "$.MSH[1]-18.1.1",
        ),
        (
            MSH.replace("|CSYN-MSG-I01-0001|", "||"),
            Hl7RejectionCode.HEADER_INVALID.value,
            "$.MSH[1]",
        ),
        (
            MSH.replace("|ADT^A08^ADT_A01|", "||"),
            Hl7RejectionCode.HEADER_INVALID.value,
            "$.MSH[1]",
        ),
        (
            MSH.replace("20260904120000", "2026-09-04"),
            ImportErrorCode.VALUE_NOT_IN_PROFILE.value,
            "$.MSH[1]-7.1.1",
        ),
        (
            MSH.replace("20260904120000", "CSYN-NOW"),
            ImportErrorCode.VALUE_NOT_IN_PROFILE.value,
            "$.MSH[1]-7.1.1",
        ),
        (
            MSH.replace("|AL|NE|", "|XX|NE|"),
            ImportErrorCode.VALUE_NOT_IN_PROFILE.value,
            "$.MSH[1]-15.1.1",
        ),
        (
            MSH.replace("CSYN-SENDER", "123-45-6789"),
            "direct_identifier_detected",
            "$.MSH[1]-3.1.1",
        ),
        (
            MSH.replace("CSYN-SENDER", "person@example.invalid"),
            "unapproved_free_text",
            "$.MSH[1]-3.1.1",
        ),
        (
            MSH.replace("CSYN-SENDER", "CTXSAFE-PHI-CANARY-ALICE"),
            "phi_canary_detected",
            "$.MSH[1]-3.1.1",
        ),
        (
            MSH.replace("CSYN-SENDER", "CSYN SENDER"),
            "unapproved_free_text",
            "$.MSH[1]-3.1.1",
        ),
    ],
    ids=[
        "production",
        "unknown-processing-id",
        "other-version",
        "other-character-set",
        "no-control-id",
        "no-message-type",
        "iso-date",
        "token-timestamp",
        "accept-type",
        "identifier",
        "email-is-not-a-token",
        "canary",
        "free-text",
    ],
)
def test_message_header_checks(segment: str, code: str, path: str) -> None:
    error = _rejected(_with(0, segment), code, path)
    assert "example.invalid" not in str(error)
    assert "ALICE" not in str(error)


def test_header_optional_fields_may_be_empty() -> None:
    segment = "MSH|^~\\&|||||||ADT^A08|CSYN-MSG|D|2.9.1"
    assert _convert(_with(0, segment)).record_count == 5


# --- PID: identifier, names, administrative sex ------------------------------


@pytest.mark.parametrize(
    ("segment", "code"),
    [
        (
            PID.replace("CSYN-CTP-I01^^^", "CSYN-CTP-Z99^^^"),
            ImportErrorCode.CASE_MISMATCH.value,
        ),
        (
            PID.replace("urn:contextsafe:synthetic", "urn:example:real"),
            ImportErrorCode.IDENTIFIER_NOT_SYNTHETIC.value,
        ),
        (
            PID.replace(
                "&urn:contextsafe:synthetic&URI", "&urn:contextsafe:synthetic&ISO"
            ),
            ImportErrorCode.IDENTIFIER_NOT_SYNTHETIC.value,
        ),
        (
            PID.replace(
                "&urn:contextsafe:synthetic&URI",
                "urn:contextsafe:synthetic&urn:contextsafe:synthetic&URI",
            ),
            ImportErrorCode.IDENTIFIER_NOT_SYNTHETIC.value,
        ),
        (
            PID.replace("&urn:contextsafe:synthetic&URI", "&urn:contextsafe:synthetic"),
            ImportErrorCode.IDENTIFIER_NOT_SYNTHETIC.value,
        ),
        (
            PID.replace("&urn:contextsafe:synthetic&URI", ""),
            ImportErrorCode.IDENTIFIER_NOT_SYNTHETIC.value,
        ),
        (
            PID.replace("CSYN-CTP-I01^^^", "CTP-I01^^^"),
            ImportErrorCode.IDENTIFIER_NOT_SYNTHETIC.value,
        ),
        (
            PID.replace("CSYN-CTP-I01^^^", "MRN-12345^^^"),
            "direct_identifier_detected",
        ),
        (
            PID.replace("CSYN-CTP-I01^^^", "PAT-12345^^^"),
            ImportErrorCode.IDENTIFIER_NOT_SYNTHETIC.value,
        ),
        (PID.replace("CSYN-CTP-I01^^^", "0001234567^^^"), "direct_identifier_detected"),
        (
            PID.replace("CSYN-CTP-I01^^^&", "^^^&"),
            ImportErrorCode.IDENTIFIER_NOT_SYNTHETIC.value,
        ),
        (
            PID.replace("CSYN-CTP-I01^^^&urn:contextsafe:synthetic&URI^MR", ""),
            ImportErrorCode.VALUE_MISSING.value,
        ),
        (PID.replace("^MR|", "^SS|"), ImportErrorCode.VALUE_NOT_IN_PROFILE.value),
    ],
    ids=[
        "other-case",
        "other-system",
        "other-universal-type",
        "both-authority-forms",
        "universal-id-without-type",
        "no-authority",
        "no-prefix",
        "mrn-token",
        "non-synthetic-token",
        "digit-run",
        "authority-only",
        "empty",
        "identifier-type",
    ],
)
def test_pid_3_must_be_the_case_synthetic_identifier(segment: str, code: str) -> None:
    error = _rejected(_with(1, segment), code)
    assert error.path.startswith("$.PID[1]-3")
    assert "Z99" not in str(error)
    assert "12345" not in str(error)


def test_pid_3_accepts_the_namespace_id_spelling_too() -> None:
    segment = PID.replace("&urn:contextsafe:synthetic&URI", "urn:contextsafe:synthetic")
    assert _convert(_with(1, segment)).record_count == 5


@pytest.mark.parametrize(
    ("segment", "code", "path"),
    [
        (
            PID.replace("ZZZTESTCONTEXTSAFE^CSYN-ASTER", "SMITH^CSYN-ASTER"),
            "non_synthetic_name",
            "$.PID[1]-5.1.1",
        ),
        (
            PID.replace("^CSYN-ASTER^", "^ASTER^"),
            "non_synthetic_name",
            "$.PID[1]-5.1.1",
        ),
        (
            PID.replace("^CSYN-LEGAL-I01^", "^LEGAL^"),
            "non_synthetic_name",
            "$.PID[1]-5.2.1",
        ),
        (
            PID.replace("^^^^^D~", "^^^^^N~"),
            ImportErrorCode.VALUE_NOT_IN_PROFILE.value,
            "$.PID[1]-5.1.7",
        ),
        (
            PID.replace("^^^^^D~", "^^^^^~"),
            ImportErrorCode.VALUE_NOT_IN_PROFILE.value,
            "$.PID[1]-5.1.7",
        ),
        (
            PID.replace(
                "ZZZTESTCONTEXTSAFE^CSYN-ASTER^^^^^D", "ZZZTESTCONTEXTSAFE^^^^^^D"
            ),
            "non_synthetic_name",
            "$.PID[1]-5.1.1",
        ),
    ],
    ids=["family", "given", "legal-given", "other-type", "no-type", "no-given"],
)
def test_pid_5_names_must_be_synthetic_and_typed(
    segment: str, code: str, path: str
) -> None:
    error = _rejected(_with(1, segment), code, path)
    assert "SMITH" not in str(error)


def test_no_name_to_use_means_no_name_observation_not_a_default(
    rules_json: dict[str, Any],
) -> None:
    segment = PID.replace("ZZZTESTCONTEXTSAFE^CSYN-ASTER^^^^^D~", "")
    result = _convert(_with(1, segment))
    assert ConceptKind.NAME_TO_USE not in {item.concept for item in result.observations}
    bundle = parse_bundle(_CASE_JSON, result.observation_set(), rules_json)
    by_rule = {item.rule_id: item for item in evaluate(bundle)}
    assert by_rule["A-I04"].status.value == "indeterminate"
    assert by_rule["A-I04"].reason.value == "missing_evidence"


def test_an_empty_trailing_name_repetition_is_not_a_name() -> None:
    segment = PID.replace("^^^^^L|", "^^^^^L~|")
    result = _convert(_with(1, segment))
    names = [i for i in result.observations if i.concept is ConceptKind.NAME_TO_USE]
    assert len(names) == 1
    assert names[0].evidence.source_pointer == "$.PID[1]-5.1.2"


def test_segment_text_is_empty_past_the_last_component() -> None:
    segments = parse_er7(_encode(ACCEPTING))
    obr = segments[4]
    assert obr.text(4) == "CSYN-SERVICE-A"
    assert obr.text(4, 3) == "urn:contextsafe:fixture"
    assert obr.text(4, 4) == ""
    assert obr.text(30) == ""


def test_an_empty_pid_5_and_pid_8_produce_nothing() -> None:
    segment = "PID|1||CSYN-CTP-I01^^^&urn:contextsafe:synthetic&URI^MR"
    result = _convert([MSH, segment, PRN])
    assert [item.concept for item in result.observations] == [ConceptKind.PRONOUNS]


@pytest.mark.parametrize("value", ["U", "O", "A", "N", "female", "CSYN-X", "declined"])
def test_pid_8_values_outside_the_rsg_set_reject_instead_of_normalizing(
    value: str,
) -> None:
    """A-033: ``U`` is not turned into ``unknown``; nothing is."""

    error = _rejected(_with(1, PID.replace("|||X", f"|||{value}")), "invalid_rsg_value")
    assert value not in error.message


def test_pid_8_reader_can_only_build_recorded_sex_or_gender() -> None:
    """The rule is in the types, not in a table anyone can edit."""

    hints = typing.get_type_hints(module._administrative_sex)
    assert hints["return"] == RecordedSexOrGender | None
    assert _CONCEPT_OF_TYPE[RecordedSexOrGender] is ConceptKind.RECORDED_SEX_OR_GENDER
    assert set(_CONCEPT_OF_TYPE) == {
        GenderIdentity,
        RecordedSexOrGender,
        SexParameterForClinicalUse,
        NameToUse,
        Pronouns,
    }
    assert len(set(_CONCEPT_OF_TYPE.values())) == len(ConceptKind)
    source = Path(module.__file__).read_text(encoding="utf-8")
    assert source.count("_components(pid, 8, 1)") == 1
    assert source.count("_administrative_sex(") == 2
    assert _readers_of_field_8_outside(ast.parse(source), "_administrative_sex") == []


_SEGMENT_READERS = frozenset(
    {"field", "text", "populated", "_components", "_closed_code", "_coded_identifier"}
)
"""Every way this module reads a field's content; ``pointer`` only names one."""


def _readers_of_field_8_outside(tree: ast.Module, owner: str) -> list[str]:
    """Calls that read field 8 of a segment from any function but ``owner``.

    A second reader written as ``pid.text(8)`` or ``pid.field(8)`` would
    pass a substring count; this walk fails it.
    """

    found: list[str] = []
    for function in ast.walk(tree):
        if not isinstance(function, ast.FunctionDef) or function.name == owner:
            continue
        for node in ast.walk(function):
            if not isinstance(node, ast.Call):
                continue
            callee = node.func
            name = callee.attr if isinstance(callee, ast.Attribute) else None
            if isinstance(callee, ast.Name):
                name = callee.id
            reads_eight = any(
                isinstance(arg, ast.Constant) and arg.value == 8 for arg in node.args
            )
            if name in _SEGMENT_READERS and reads_eight:
                found.append(f"{function.name}:{name}")
    return found


def test_the_field_8_walk_catches_a_second_reader() -> None:
    """The walk itself is checked: a reader it must find, it finds."""

    planted = ast.parse(
        "def _administrative_sex(pid):\n    return _components(pid, 8, 1)\n"
        "def _other(pid):\n    return pid.text(8)\n"
        "def _pointer_only(pid):\n    return pid.pointer(8)\n"
    )
    assert _readers_of_field_8_outside(planted, "_administrative_sex") == [
        "_other:text"
    ]


_PID_8_VALUES = st.one_of(
    st.sampled_from(("F", "M", "X", "unknown", "U", "O", "A", "N", "")),
    st.text(alphabet="ABCDEFXMU0123456789-_:", min_size=1, max_size=12),
)

_PID_8_REJECTIONS: tuple[dict[str, str], ...] = (
    {
        "code": "unapproved_free_text",
        "message": "a value must be a bounded code token; free text is prohibited",
        "path": "$.PID[1]-8.1.1",
    },
    {
        "code": "direct_identifier_detected",
        "message": "a direct-identifier pattern was detected",
        "path": "$.PID[1]-8.1.1",
    },
    {
        "code": "invalid_rsg_value",
        "message": "value is not supported",
        "path": "$.observations[1].value.value",
    },
)
"""Every error object a rejected PID-8 value may produce (closed).

Structural rather than substring: each message is a fixed sentence from the
code path that emits it, so membership proves the rejection carried no part
of the drawn value, which a substring check cannot prove for a short draw.
The observation path is index 1 because the name to use is emitted first.
"""


@settings(max_examples=200, deadline=None)
@example(value="-", checkpoint=Checkpoint.EHR)
@example(value="1234567", checkpoint=Checkpoint.REGISTRATION)
@example(value="2019-01-01", checkpoint=Checkpoint.INTERFACE)
@example(value="U", checkpoint=Checkpoint.LIS_RETURN)
@given(value=_PID_8_VALUES, checkpoint=st.sampled_from(tuple(Checkpoint)))
def test_no_parse_path_places_pid_8_anywhere_but_recorded_sex_or_gender(
    value: str, checkpoint: Checkpoint
) -> None:
    """The safety-negative: PID-8 never reaches GI or SPCU, on any input."""

    segment = PID.replace("|||X", f"|||{value}")
    try:
        result = _convert([MSH, segment], checkpoint=checkpoint)
    except ContextSafeError as error:
        assert error.to_dict() in _PID_8_REJECTIONS
        return
    from_pid_8 = [
        item
        for item in result.observations
        if item.evidence.source_pointer.startswith("$.PID[1]-8")
    ]
    assert len(from_pid_8) == (1 if value else 0)
    for item in from_pid_8:
        assert item.concept is ConceptKind.RECORDED_SEX_OR_GENDER
        assert isinstance(item.value, RecordedSexOrGender)
        assert item.value.context == ADMINISTRATIVE_CONTEXT
        assert item.value.source == PID_8_SOURCE
        assert item.value.value == value
        assert item.mapping.source_concept is ConceptKind.RECORDED_SEX_OR_GENDER
        assert item.mapping.target_concept is ConceptKind.RECORDED_SEX_OR_GENDER
    assert not any(
        item.concept
        in {ConceptKind.GENDER_IDENTITY, ConceptKind.SEX_PARAMETER_FOR_CLINICAL_USE}
        for item in result.observations
    )


# --- GSP ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("segment", "code", "path"),
    [
        (
            "GSP|1|A||76690-7^^LN|CSYN-SO",
            ImportErrorCode.FIELD_CODE_UNMAPPED.value,
            "$.GSP[1]-4.1.1",
        ),
        (
            "GSP|1|A||76691-5^^SCT|fixture-gender-1",
            ImportErrorCode.FIELD_CODE_UNMAPPED.value,
            "$.GSP[1]-4.1.1",
        ),
        (
            "GSP|1|A||76691-5|fixture-gender-1",
            ImportErrorCode.FIELD_CODE_UNMAPPED.value,
            "$.GSP[1]-4.1.1",
        ),
        (
            "GSP|1|A|||fixture-gender-1",
            ImportErrorCode.VALUE_MISSING.value,
            "$.GSP[1]-4.1.1",
        ),
        (
            "GSP|1|A||76691-5^^LN|",
            ImportErrorCode.VALUE_MISSING.value,
            "$.GSP[1]-5.1.1",
        ),
        (
            "GSP|1|A||76691-5^^LN|^^urn:contextsafe:fixture",
            ImportErrorCode.VALUE_MISSING.value,
            "$.GSP[1]-5.1.1",
        ),
        (
            "GSP|1|A||76691-5^Gender^LN|fixture-gender-1",
            "unapproved_free_text",
            "$.GSP[1]-4.1.2",
        ),
        (
            "GSP|1|A||76691-5^^LN|fixture-gender-1^Nonbinary",
            "unapproved_free_text",
            "$.GSP[1]-5.1.2",
        ),
        ("GSP|1|A||76691-5^^LN|non binary", "unapproved_free_text", "$.GSP[1]-5.1.1"),
        (
            "GSP|1|D||76691-5^^LN|fixture-gender-1",
            ImportErrorCode.VALUE_NOT_IN_PROFILE.value,
            "$.GSP[1]-2.1.1",
        ),
        (
            "GSP|ONE|A||76691-5^^LN|fixture-gender-1",
            ImportErrorCode.VALUE_NOT_IN_PROFILE.value,
            "$.GSP[1]-1.1.1",
        ),
        (
            "GSP|1|A||99501-9^^LN|fixture-context-1",
            ImportErrorCode.CONCEPT_NOT_CONVERTIBLE.value,
            "$.GSP[1]-4.1.1",
        ),
        (
            "GSP|1|A||99502-7^^LN|CSYN-NB",
            "invalid_rsg_value",
            "$.observations[2].value.value",
        ),
        (
            "GSP|1|A||76691-5^^LN|CTXSAFE-PHI-CANARY-ALICE",
            "phi_canary_detected",
            "$.GSP[1]-5.1.1",
        ),
    ],
    ids=[
        "sexual-orientation",
        "other-coding-system",
        "no-coding-system",
        "no-type",
        "no-value",
        "system-without-code",
        "type-display-text",
        "value-display-text",
        "prose-value",
        "action-code",
        "set-id",
        "spcu-before-any-obr",
        "rsg-outside-set",
        "canary",
    ],
)
def test_gsp_checks(segment: str, code: str, path: str) -> None:
    error = _rejected(_with(2, segment), code, path)
    assert "ALICE" not in str(error)
    assert "Nonbinary" not in str(error)


@pytest.mark.parametrize("status", ["declined", "unknown", "absent"])
@pytest.mark.parametrize(
    ("segment", "concept"),
    [
        ("GSP|1|A||76691-5^^LN|{status}", ConceptKind.GENDER_IDENTITY),
        ("GSP|1|A||90778-2^^LN|{status}", ConceptKind.PRONOUNS),
    ],
)
def test_gsp_presence_states_carry_no_value(
    status: str, segment: str, concept: ConceptKind
) -> None:
    result = _convert([MSH, PID, segment.format(status=status)])
    observation = result.observations[2]
    assert observation.concept is concept
    value = observation.value.to_dict()
    assert value["status"] == status
    assert value["value"] is None
    if concept is ConceptKind.GENDER_IDENTITY:
        assert value["code_system"] == module.UNBOUND_CODE_SYSTEM


def test_gsp_presence_state_is_not_a_sex_parameter() -> None:
    segments = [*ACCEPTING[:6], "GSP|3|A||99501-9^^LN|declined"]
    _rejected(segments, ImportErrorCode.VALUE_NOT_IN_PROFILE.value, "$.GSP[3]-5.1.1")


def test_gsp_recorded_sex_or_gender_says_its_context_is_unbound() -> None:
    result = _convert([MSH, PID, "GSP|1|A||99502-7^^LN|F"])
    values = [item.value.to_dict() for item in result.observations]
    assert values[1] == {
        "context": ADMINISTRATIVE_CONTEXT,
        "source": PID_8_SOURCE,
        "value": "X",
    }
    assert values[2] == {"context": UNBOUND_CONTEXT, "source": GSP_SOURCE, "value": "F"}
    assert result.observations[2].concept is ConceptKind.RECORDED_SEX_OR_GENDER


def test_gsp_gender_identity_without_a_coding_system_is_unbound() -> None:
    result = _convert([MSH, PID, "GSP|1|A||76691-5^^LN|CSYN-GI"])
    assert result.observations[2].value.to_dict() == {
        "code_system": module.UNBOUND_CODE_SYSTEM,
        "status": "specified",
        "value": "CSYN-GI",
    }


_FOREIGN_SYSTEM_SEGMENTS = [
    (3, "GSP|2|A||90778-2^^LN|they/them^^urn:vendor:pronoun-codes", "$.GSP[2]-5.1.3"),
    (
        6,
        "GSP|3|A||99501-9^^LN|fixture-context-1^^urn:vendor:spcu-codes",
        "$.GSP[3]-5.1.3",
    ),
    (2, "GSP|1|A||99502-7^^LN|F^^urn:other:system", "$.GSP[1]-5.1.3"),
    (2, "GSP|1|A||99502-7^^LN|X^^LN", "$.GSP[1]-5.1.3"),
    (2, "GSP|1|A||76691-5^^LN|declined^^LN", "$.GSP[1]-5.1.3"),
    (2, "GSP|1|A||76691-5^^LN|unknown^^urn:contextsafe:fixture", "$.GSP[1]-5.1.3"),
    (3, "GSP|2|A||90778-2^^LN|absent^^LN", "$.GSP[2]-5.1.3"),
]
"""A populated GSP-5.3 everywhere the profile has no reading for one."""


@pytest.mark.parametrize(
    ("index", "segment", "path"),
    _FOREIGN_SYSTEM_SEGMENTS,
    ids=[
        "pronouns",
        "spcu",
        "rsg-foreign-system",
        "rsg-loinc",
        "gi-declined",
        "gi-unknown",
        "pronouns-absent",
    ],
)
def test_gsp_5_3_is_read_only_with_a_specified_gender_identity(
    index: int, segment: str, path: str
) -> None:
    """A value asserted in a coding system is not carried as the bare token.

    Pronouns, recorded sex or gender, and sex parameter for clinical use have
    no field for a coding system, and a presence state is not a code in any
    system; a populated GSP-5.3 there rejects the whole message rather than
    being dropped (A-033).
    """

    error = _rejected(
        _with(index, segment), ImportErrorCode.FIELD_NOT_IN_PROFILE.value, path
    )
    assert "vendor" not in str(error)
    assert "they/them" not in str(error)


def _statuses(
    segments: list[str], checkpoint: Checkpoint, rules_json: dict[str, Any]
) -> dict[str, str]:
    document = _convert(segments, checkpoint=checkpoint).observation_set()
    bundle = parse_bundle(_CASE_JSON, document, rules_json)
    return {item.rule_id: item.status.value for item in evaluate(bundle)}


@pytest.mark.parametrize(
    ("index", "segment", "checkpoint", "rule"),
    [
        (3, _FOREIGN_SYSTEM_SEGMENTS[0][1], Checkpoint.EHR, "A-I05"),
        (6, _FOREIGN_SYSTEM_SEGMENTS[1][1], Checkpoint.INTERFACE, "A-I03"),
    ],
    ids=["pronouns-at-ehr", "spcu-at-interface"],
)
def test_a_value_in_a_foreign_coding_system_cannot_become_a_pass(
    index: int,
    segment: str,
    checkpoint: Checkpoint,
    rule: str,
    rules_json: dict[str, Any],
) -> None:
    """The safety-negative, run through ``evaluate``.

    The reference token passes its rule at its checkpoint. The same token
    asserted in a vendor coding system must not: the message rejects before
    there is anything to evaluate, so the pass cannot come back by way of a
    dropped system.
    """

    assert _statuses(list(ACCEPTING), checkpoint, rules_json)[rule] == "pass"
    with pytest.raises(ContextSafeError) as raised:
        _statuses(_with(index, segment), checkpoint, rules_json)
    assert raised.value.code == ImportErrorCode.FIELD_NOT_IN_PROFILE.value


def test_a_gender_identity_presence_state_is_always_unbound() -> None:
    """GI presence states hash the same from every importer: no system."""

    for status in ("declined", "unknown", "absent"):
        result = _convert([MSH, PID, f"GSP|1|A||76691-5^^LN|{status}"])
        assert result.observations[2].value.to_dict() == {
            "code_system": module.UNBOUND_CODE_SYSTEM,
            "status": status,
            "value": None,
        }


# --- OBR and OBX --------------------------------------------------------------


@pytest.mark.parametrize(
    ("index", "segment", "code", "path"),
    [
        (4, "OBR|1|ORD-1||CSYN-SERVICE-A", "non_synthetic_context", "$.OBR[1]-2.1.1"),
        (
            4,
            "OBR|1|||CSYN-SERVICE-A",
            ImportErrorCode.CONTEXT_MISSING.value,
            "$.OBR[1]-2.1.1",
        ),
        (
            4,
            "OBR|1|ORDER-CSYN-I01-A|FILL-1|CSYN-SERVICE-A",
            "non_synthetic_context",
            "$.OBR[1]-3.1.1",
        ),
        (
            4,
            "OBR|1|ORDER-CSYN-I01-A||CSYN-SERVICE-A^Service",
            "unapproved_free_text",
            "$.OBR[1]-4.1.2",
        ),
        (
            4,
            OBR + "|" * 21 + "P",
            ImportErrorCode.VALUE_NOT_IN_PROFILE.value,
            "$.OBR[1]-25.1.1",
        ),
        (
            5,
            OBX.replace("|CWE|", "|NM|"),
            ImportErrorCode.VALUE_NOT_IN_PROFILE.value,
            "$.OBX[1]-2.1.1",
        ),
        (5, OBX.replace("|CWE|", "|ST|"), "unapproved_free_text", "$.OBX[1]-2.1.1"),
        (5, OBX.replace("|CWE|", "|FT|"), "unapproved_free_text", "$.OBX[1]-2.1.1"),
        (5, OBX.replace("|CWE|", "|TX|"), "unapproved_free_text", "$.OBX[1]-2.1.1"),
        (
            5,
            OBX.replace("|CWE|", "||"),
            ImportErrorCode.VALUE_NOT_IN_PROFILE.value,
            "$.OBX[1]-2.1.1",
        ),
        (
            5,
            OBX.replace("SUP-CSYN-I01-A", "CSYN-RESULT"),
            ImportErrorCode.VALUE_NOT_IN_PROFILE.value,
            "$.OBX[1]-5.1.1",
        ),
        (
            5,
            OBX.replace("SUP-CSYN-I01-A", ""),
            ImportErrorCode.VALUE_NOT_IN_PROFILE.value,
            "$.OBX[1]-5.1.1",
        ),
        (
            5,
            OBX.replace("SUP-CSYN-I01-A", "SUP-CSYN-I01-A^Support"),
            "unapproved_free_text",
            "$.OBX[1]-5.1.2",
        ),
        (
            5,
            OBX.replace("||||||F", "||||||P"),
            ImportErrorCode.VALUE_NOT_IN_PROFILE.value,
            "$.OBX[1]-11.1.1",
        ),
        (
            5,
            OBX.replace("||||||F", "||||||"),
            ImportErrorCode.VALUE_MISSING.value,
            "$.OBX[1]-11.1.1",
        ),
        (
            5,
            OBX.replace("||||||F", ""),
            ImportErrorCode.VALUE_MISSING.value,
            "$.OBX[1]-11.1.1",
        ),
        (
            5,
            OBX.replace("CSYN-SUPPORT^^", "CSYN-SUPPORT^Supporting observation^"),
            "unapproved_free_text",
            "$.OBX[1]-3.1.2",
        ),
    ],
    ids=[
        "obr-2-not-synthetic",
        "obr-2-missing",
        "obr-3-not-synthetic",
        "obr-4-text",
        "obr-25",
        "obx-2-numeric",
        "obx-2-st",
        "obx-2-ft",
        "obx-2-tx",
        "obx-2-empty",
        "obx-5-not-a-support-token",
        "obx-5-empty",
        "obx-5-text",
        "obx-11",
        "obx-11-empty",
        "obx-11-absent",
        "obx-3-text",
    ],
)
def test_order_and_observation_checks(
    index: int, segment: str, code: str, path: str
) -> None:
    error = _rejected(_with(index, segment), code, path)
    assert "Support" not in str(error)


def test_spcu_without_a_supporting_observation_rejects_by_contract() -> None:
    _rejected(
        [MSH, PID, OBR, SPCU],
        "invalid_support",
        "$.observations[2].value.supporting_observation_ids",
    )


def test_every_obx_in_the_order_group_is_a_supporting_observation() -> None:
    second = OBX.replace("OBX|1|", "OBX|2|").replace("SUP-CSYN-I01-A", "SUP-CSYN-I01-B")
    result = _convert([MSH, PID, OBR, OBX, second, SPCU])
    assert result.observations[2].value.to_dict()["supporting_observation_ids"] == [
        "SUP-CSYN-I01-A",
        "SUP-CSYN-I01-B",
    ]


def test_each_order_group_binds_its_own_context() -> None:
    order_b = OBR.replace("OBR|1|ORDER-CSYN-I01-A", "OBR|2|ORDER-CSYN-I01-B")
    obx_b = OBX.replace("OBX|1|", "OBX|2|").replace("SUP-CSYN-I01-A", "SUP-CSYN-I01-B")
    spcu_b = "GSP|4|A||99501-9^^LN|fixture-context-2"
    result = _convert([*ACCEPTING, order_b, obx_b, spcu_b])
    values = [
        item.value.to_dict()
        for item in result.observations
        if item.concept is ConceptKind.SEX_PARAMETER_FOR_CLINICAL_USE
    ]
    assert values == [
        {
            "context_id": "ORDER-CSYN-I01-A",
            "supporting_observation_ids": ["SUP-CSYN-I01-A"],
            "value": "fixture-context-1",
        },
        {
            "context_id": "ORDER-CSYN-I01-B",
            "supporting_observation_ids": ["SUP-CSYN-I01-B"],
            "value": "fixture-context-2",
        },
    ]
    assert result.observations[-1].evidence.source_pointer == "$.GSP[4]-5.1.1"


# --- the profile is a constant that says it is unreviewed --------------------


def test_the_profile_is_versioned_unreviewed_and_refuses_review() -> None:
    profile = HL7V2_ER7_PROFILE
    assert profile.profile_version == "0.1.0"
    assert profile.profile_reviewed is False
    assert profile.name_to_use_type_code == "D"
    assert profile.hl7_version == "2.9.1"
    assert "P" not in profile.processing_ids
    assert set(profile.concept_types.values()) == {
        ConceptKind.GENDER_IDENTITY,
        ConceptKind.PRONOUNS,
        ConceptKind.SEX_PARAMETER_FOR_CLINICAL_USE,
        ConceptKind.RECORDED_SEX_OR_GENDER,
    }
    assert ConceptKind.NAME_TO_USE not in profile.concept_types.values()
    fields = {name: getattr(profile, name) for name in profile.__slots__}
    with pytest.raises(ContextSafeError) as raised:
        Hl7v2Profile(**{**fields, "profile_reviewed": True})
    assert raised.value.code == "profile_review_not_available"
    with pytest.raises((AttributeError, TypeError)):
        profile.profile_reviewed = True  # type: ignore[misc]
    with pytest.raises(TypeError):
        profile.concept_types[("1-1", "LN")] = ConceptKind.GENDER_IDENTITY  # type: ignore[index]


def test_registry_carries_the_format_and_every_code_is_in_a_family() -> None:
    importer = REGISTRY[HL7V2_ER7_FORMAT]
    assert importer.format_name == HL7V2_ER7_FORMAT
    assert importer.mapping_version == HL7V2_ER7_MAPPING_VERSION
    assert all(code.value.startswith("hl7v2_") for code in Hl7RejectionCode)
    assert len({code.value for code in Hl7RejectionCode}) == len(Hl7RejectionCode)


# --- the file boundary ----------------------------------------------------------


def test_read_source_is_bounded_no_follow_and_closes_its_descriptor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_open = os.open
    opened: list[int] = []

    def recording_open(*args: Any, **kwargs: Any) -> int:
        descriptor = original_open(*args, **kwargs)
        opened.append(descriptor)
        return descriptor

    monkeypatch.setattr(preflight_module.os, "open", recording_open)
    source = tmp_path / "message.hl7"
    source.write_bytes(_encode(ACCEPTING))
    read = read_source(source)
    assert read.raw == _encode(ACCEPTING)
    assert read.raw_byte_count == len(read.raw)
    assert read.raw_sha256 == hashlib.sha256(read.raw).hexdigest()

    large = tmp_path / "large.hl7"
    large.write_bytes(b"M" * (MAX_EVIDENCE_BYTES + 1))
    with pytest.raises(ContextSafeError) as raised:
        read_source(large)
    assert raised.value.code == "input_too_large"

    link = tmp_path / "link.hl7"
    link.symlink_to(source)
    with pytest.raises(ContextSafeError) as raised:
        read_source(link)
    assert raised.value.code == "input_path_unsafe"

    with pytest.raises(ContextSafeError) as raised:
        read_source(tmp_path)
    assert raised.value.code == "input_path_unsafe"

    for descriptor in opened:
        with pytest.raises(OSError):
            os.fstat(descriptor)


def test_read_source_closes_the_descriptor_when_the_first_pass_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A read that fails after the open still releases what it opened."""

    original_open = os.open
    opened: list[int] = []

    def recording_open(*args: Any, **kwargs: Any) -> int:
        descriptor = original_open(*args, **kwargs)
        opened.append(descriptor)
        return descriptor

    def failing_first_pass(_descriptor: int) -> tuple[bytes, str]:
        raise ContextSafeError("input_io_error", "$", "injected read failure")

    monkeypatch.setattr(preflight_module.os, "open", recording_open)
    monkeypatch.setattr(preflight_module, "_read_first_pass", failing_first_pass)
    source = tmp_path / "message.hl7"
    source.write_bytes(_encode(ACCEPTING))
    with pytest.raises(ContextSafeError) as raised:
        read_source(source)
    assert raised.value.code == "input_io_error"
    assert len(opened) == 1
    with pytest.raises(OSError):
        os.fstat(opened[0])


def test_platforms_without_no_follow_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "message.hl7"
    source.write_bytes(_encode(ACCEPTING))
    monkeypatch.setattr(preflight_module, "_NOFOLLOW", 0)
    with pytest.raises(ContextSafeError) as raised:
        REGISTRY[HL7V2_ER7_FORMAT].convert(
            source, case=_CASE, checkpoint=Checkpoint.EHR
        )
    assert raised.value.code == "input_path_unsupported"


def test_a_message_at_exactly_the_byte_bound_is_read() -> None:
    filler = "GSP|1|A||90778-2^^LN|CSYN-P"
    segments = [MSH, PID]
    while len(_encode([*segments, filler])) <= MAX_EVIDENCE_BYTES:
        segments.append(filler)
    raw = _encode(segments)
    assert len(raw) <= MAX_EVIDENCE_BYTES
    with pytest.raises(ContextSafeError) as raised:
        convert_raw(_raw(raw), case=_CASE, checkpoint=Checkpoint.EHR)
    assert raised.value.code == Hl7RejectionCode.SEGMENT_COUNT_EXCEEDED.value


# --- the command line ---------------------------------------------------------


def test_cli_import_is_read_only_and_emits_the_observation_set(
    tmp_path: Path, case_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "message.hl7"
    source.write_bytes(_encode(ACCEPTING))
    before = source.read_bytes()

    assert main(_import_args(source, case_path)) == EXIT_SUCCESS

    captured = capsys.readouterr()
    assert captured.err == ""
    document = json.loads(captured.out)
    assert document["schema_version"] == "contextsafe.observation-set/0.1.0"
    assert len(document["observations"]) == 5
    assert {item.name for item in tmp_path.iterdir()} == {"message.hl7", "case.json"}
    assert source.read_bytes() == before


def test_cli_checkpoint_is_applied_to_every_observation(
    tmp_path: Path, case_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "message.hl7"
    source.write_bytes(_encode(ACCEPTING))
    assert main(_import_args(source, case_path, "interface")) == EXIT_SUCCESS
    document = json.loads(capsys.readouterr().out)
    assert {item["checkpoint"] for item in document["observations"]} == {"interface"}


def test_cli_output_quiet_and_log_dir(
    tmp_path: Path, case_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "message.hl7"
    source.write_bytes(_encode(ACCEPTING))
    assert main(_import_args(source, case_path)) == EXIT_SUCCESS
    printed = capsys.readouterr().out
    output = tmp_path / "observations.json"
    log_dir = tmp_path / "log"
    assert (
        main(
            [
                *_import_args(source, case_path),
                "--quiet",
                "--no-color",
                "--output",
                str(output),
                "--log-dir",
                str(log_dir),
            ]
        )
        == EXIT_SUCCESS
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
    assert output.read_bytes() == printed.encode("utf-8")
    assert "\x1b" not in printed
    records = [
        json.loads(line)
        for path in log_dir.iterdir()
        for line in path.read_text(encoding="utf-8").splitlines()
    ]
    assert len(records) == 1
    assert records[0]["command"] == "import"
    assert records[0]["outcome"] == "accepted"
    assert "CSYN" not in json.dumps(records)


def test_cli_rejection_is_one_json_error_without_source_content(
    tmp_path: Path, case_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "message.hl7"
    source.write_bytes(_encode((*ACCEPTING, "ZPI|1|CSYN-SECRET-VALUE")))
    output = tmp_path / "observations.json"

    assert (
        main([*_import_args(source, case_path), "--output", str(output)])
        == EXIT_CONTRACT_ERROR
    )

    captured = capsys.readouterr()
    assert captured.out == ""
    error = json.loads(captured.err)["error"]
    assert error["code"] == ImportErrorCode.SEGMENT_NOT_ALLOWED.value
    assert error["path"] == "$[7]"
    assert "CSYN-SECRET-VALUE" not in captured.err
    assert "ZPI" not in captured.err
    assert str(tmp_path) not in captured.err
    assert not output.exists()


# --- determinism ----------------------------------------------------------------


@st.composite
def _messages(draw: st.DrawFn) -> list[str]:
    segments = [MSH, PID]
    for index in range(draw(st.integers(min_value=0, max_value=4))):
        kind = draw(st.sampled_from(("76691-5", "90778-2")))
        token = draw(st.text(alphabet="ABCDEF0123456789", min_size=1, max_size=6))
        segments.append(f"GSP|{index + 1}|A||{kind}^^LN|CSYN-{token}")
    if draw(st.booleans()):
        segments.extend([OBR, OBX, SPCU])
    return segments


@settings(max_examples=100, deadline=None)
@given(segments=_messages(), checkpoint=st.sampled_from(tuple(Checkpoint)))
def test_conversion_is_deterministic_and_binds_every_observation_to_the_source(
    segments: list[str], checkpoint: Checkpoint
) -> None:
    first = _convert(segments, checkpoint)
    second = _convert(list(segments), checkpoint)
    assert canonical_json(first.observation_set()) == canonical_json(
        second.observation_set()
    )
    assert first.to_dict() == second.to_dict()
    assert first.record_count == len(first.observations)
    for item in first.observations:
        assert item.evidence.source_sha256 == first.source_sha256
        assert item.checkpoint is checkpoint
        assert item.mapping.source_concept is item.mapping.target_concept
        assert _CONCEPT_OF_TYPE[type(item.value)] is item.concept
