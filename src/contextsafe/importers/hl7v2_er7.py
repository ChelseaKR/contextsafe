"""The HL7 v2 ER7 importer: one bounded message in, observation set out.

Reference-only and ungoverned. Everything this module decides about an HL7
v2 message is a constant in :data:`HL7V2_ER7_PROFILE`, versioned and marked
``profile_reviewed = False``: which segments are admitted, which fields of
each, which name-type code carries the name to use, which concept-type codes
a GSP segment may name, and which processing IDs and version a message must
declare. No interoperability, clinical, laboratory, or community reviewer
has approved any of it, and the type refuses to be constructed otherwise.

The parse is strict and whole. Delimiters are the five characters MSH-1 and
MSH-2 declare, exactly; the segment terminator is the carriage return the
standard fixes; the only escape sequences handled are the five that encode a
delimiter (``\\F\\``, ``\\S\\``, ``\\T\\``, ``\\R\\``, ``\\E\\``). A segment
outside the allowlist (every Z-segment included), a populated field the
profile does not name, a repetition where the profile admits one value, an
escape sequence this module does not handle, a value that is not a bounded
token, a control character, a PHI canary, a direct-identifier pattern, or a
patient identifier outside the synthetic namespace rejects the message with
a code and a location and produces nothing. A rejection never carries the
content it rejected, and nothing is normalized to the closest supported
value (A-033).

Concepts stay distinct by construction rather than by configuration. PID-8
Administrative Sex is read by exactly one function, whose return type is
:class:`~contextsafe.models.RecordedSexOrGender`, and the concept an
observation is labelled with is a function of the Python type of its value
(:data:`_CONCEPT_OF_TYPE`). There is no table keyed by a field that could be
edited to send PID-8 anywhere else, and no path from any PID field to gender
identity or to sex parameter for clinical use. GSP carries each concept by
its concept-type field, each to its own concept, and OBR and OBX are read
only to locate the order context and supporting-observation tokens a sex
parameter for clinical use needs and to reject free text.

Values are the source's own tokens, verbatim. A GSP value of ``they/them``
becomes a pronouns value of exactly that string; PID-8 ``X`` becomes a
recorded-sex-or-gender value of exactly ``X`` with the context
``administrative``. Binding a token to the value a rule expects is what a
mapping profile does (B-026), applied after this conversion and never
inside it; this reader records the carrier and token beside each observation
so a profile row can match on what the message said.
"""

import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType

from contextsafe.contract_validation import contract_error
from contextsafe.errors import ContextSafeError
from contextsafe.identifiers import identifier_hits
from contextsafe.importers.base import (
    ImportErrorCode,
    ImportResult,
    ImportWarningCode,
    import_error,
)
from contextsafe.importers.canonical_json import UNBOUND_CODE_SYSTEM
from contextsafe.mapping_profile import SourceToken
from contextsafe.models import (
    OBSERVATION_SCHEMA_VERSION,
    OBSERVATION_SET_SCHEMA_VERSION,
    Checkpoint,
    ConceptKind,
    EvidencePointer,
    GenderIdentity,
    MappingDescriptor,
    NameToUse,
    Observation,
    Pronouns,
    RecordedSexOrGender,
    SemanticValue,
    SexParameterForClinicalUse,
    SyntheticCase,
    ValueStatus,
)
from contextsafe.plan import SYNTHETIC_IDENTIFIER_SYSTEM, SYNTHETIC_VALUE_PREFIX
from contextsafe.preflight import RawSource, read_source
from contextsafe.validation import parse_observations

HL7V2_ER7_FORMAT = "hl7v2-er7"
"""The ``--format`` name of this importer."""

HL7V2_ER7_MAPPING_VERSION = "0.1.0"
"""Recorded as ``mapping.mapping_version`` on every observation emitted.

The version of this conversion, not of a reviewed profile. A change to the
profile below, to the fixed context and source tokens, or to the presence
rules is a change to this number. No earlier version of this conversion
shipped: the GSP-5.3 rule and the OBX-11 requirement below are part of
0.1.0 from its first release.
"""

ADMINISTRATIVE_CONTEXT = "administrative"
"""The context of every recorded-sex-or-gender value read from PID-8.

PID-8 is Administrative Sex. It is not a government-ID, payer, or
jurisdictional recording, and this importer does not say it is one.
"""

PID_8_SOURCE = "urn:contextsafe:hl7v2-er7:PID-8"
"""The ``source`` of every recorded-sex-or-gender value read from PID-8."""

GSP_SOURCE = "urn:contextsafe:hl7v2-er7:GSP"
"""The ``source`` of a recorded-sex-or-gender value read from a GSP segment."""

UNBOUND_CONTEXT = "urn:contextsafe:unbound-context"
"""RSG's ``context`` when a GSP segment carries it.

A GSP segment has no field for the administrative or jurisdictional context
of a recorded sex or gender, so the observation says the context is unbound
rather than claiming one.
"""

SUPPORTING_OBSERVATION_PREFIX = "SUP-CSYN-"
"""What an OBX-5 value must start with to be read as a supporting-observation token."""

ORDER_CONTEXT_PREFIX = "ORDER-CSYN-"
"""What an OBR-2 placer order number must start with to be an SPCU context."""

NAME_CARRIER = "PID-5"
ADMINISTRATIVE_SEX_CARRIER = "PID-8"
GSP_VALUE_CARRIER = "GSP-5"

HL7V2_ER7_CARRIERS: Mapping[str, frozenset[ConceptKind]] = MappingProxyType(
    {
        NAME_CARRIER: frozenset({ConceptKind.NAME_TO_USE}),
        ADMINISTRATIVE_SEX_CARRIER: frozenset({ConceptKind.RECORDED_SEX_OR_GENDER}),
        GSP_VALUE_CARRIER: frozenset(
            {
                ConceptKind.GENDER_IDENTITY,
                ConceptKind.PRONOUNS,
                ConceptKind.RECORDED_SEX_OR_GENDER,
                ConceptKind.SEX_PARAMETER_FOR_CLINICAL_USE,
            }
        ),
    }
)
"""What a mapping profile for this format may name as a carrier: a segment-field.

PID-8 is recorded sex or gender here for the same reason it is nothing else
in the reader: a profile row that reads it as gender identity or as sex
parameter for clinical use is refused. GSP-5 carries whichever concept
GSP-4 names, so a profile row for it says which.
"""


class Hl7RejectionCode(StrEnum):
    """Rejections that are about the ER7 encoding itself.

    Structural: the bytes are not one ER7 message this reader can parse. The
    profile decisions that follow a successful parse raise from the shared
    :class:`~contextsafe.importers.base.ImportErrorCode` family instead.
    """

    NOT_ER7 = "hl7v2_not_er7"
    """The bytes do not begin with an MSH segment header."""

    DELIMITERS_INVALID = "hl7v2_delimiters_invalid"
    """MSH-1 and MSH-2 do not declare five distinct printable delimiters."""

    SEGMENT_TERMINATOR_INVALID = "hl7v2_segment_terminator_invalid"
    """The message does not end every segment with a carriage return."""

    SEGMENT_MALFORMED = "hl7v2_segment_malformed"
    """A segment is empty or does not start with a three-character name."""

    SEGMENT_COUNT_EXCEEDED = "hl7v2_segment_count_exceeded"
    """The message carries more segments than the profile bounds."""

    ESCAPE_UNSUPPORTED = "hl7v2_escape_unsupported"
    """An escape sequence other than the five delimiter escapes was found."""

    SEGMENT_ORDER_INVALID = "hl7v2_segment_order_invalid"
    """A segment is somewhere the profile's message structure does not put it."""

    HEADER_INVALID = "hl7v2_header_invalid"
    """MSH lacks a message type, control ID, processing ID, or version."""

    VERSION_UNSUPPORTED = "hl7v2_version_unsupported"
    """MSH-12 names a version other than the one the profile is written for."""

    PROCESSING_ID_NOT_TEST = "hl7v2_processing_id_not_test"
    """MSH-11 is not a debugging or training processing ID."""

    CHARACTER_SET_UNSUPPORTED = "hl7v2_character_set_unsupported"
    """MSH-18 names a character set other than UTF-8."""


@dataclass(frozen=True, slots=True)
class Hl7v2Profile:
    """Every constant this importer decides an HL7 v2 message by.

    ``profile_reviewed`` is ``False`` and cannot be anything else: this is
    the reference-only profile the code was written against, and no reviewed
    profile exists (a B-026 mapping profile admits only ``not_reviewed``
    as well). The values are written
    out rather than derived so that a reader can line each one up against
    the Gender Harmony guidance and say whether it is right.
    """

    profile_version: str
    hl7_version: str
    name_to_use_type_code: str
    legal_name_type_code: str
    synthetic_family_name: str
    processing_ids: frozenset[str]
    character_sets: frozenset[str]
    accept_types: frozenset[str]
    identifier_type_codes: frozenset[str]
    segment_allowlist: frozenset[str]
    concept_types: Mapping[tuple[str, str], ConceptKind]
    max_segments: int
    profile_reviewed: bool = False

    def __post_init__(self) -> None:
        if self.profile_reviewed:
            raise contract_error(
                "profile_review_not_available",
                "$.profile_reviewed",
                "no HL7 v2 profile has been reviewed; the flag cannot be set",
            )


HL7V2_ER7_PROFILE = Hl7v2Profile(
    profile_version="0.1.0",
    hl7_version="2.9.1",
    name_to_use_type_code="D",
    legal_name_type_code="L",
    synthetic_family_name="ZZZTESTCONTEXTSAFE",
    processing_ids=frozenset({"D", "T"}),
    character_sets=frozenset({"UNICODE UTF-8"}),
    accept_types=frozenset({"AL", "ER", "NE", "SU"}),
    identifier_type_codes=frozenset({"MR", "PI", "PT"}),
    segment_allowlist=frozenset({"MSH", "PID", "GSP", "OBR", "OBX"}),
    concept_types=MappingProxyType(
        {
            ("76691-5", "LN"): ConceptKind.GENDER_IDENTITY,
            ("90778-2", "LN"): ConceptKind.PRONOUNS,
            ("99501-9", "LN"): ConceptKind.SEX_PARAMETER_FOR_CLINICAL_USE,
            ("99502-7", "LN"): ConceptKind.RECORDED_SEX_OR_GENDER,
        }
    ),
    max_segments=2000,
)
"""The reference-only profile, version 0.1.0, unreviewed.

``name_to_use_type_code`` is ``D`` (Customary Name, HL7 table 0200), the code
the Gender Harmony cross-paradigm guidance assigns to name to use in PID-5;
``legal_name_type_code`` ``L`` is admitted so a message that also carries a
synthetic legal test name is not rejected for carrying it, and that name is
never emitted. ``concept_types`` keys GSP-4 (code, coding system): the LOINC
codes for gender identity and personal pronouns are the ones v2.9.1 binds to
GSP-4; the codes for sex parameter for clinical use and recorded sex or
gender are the LOINC codes published for those Gender Harmony concepts,
placed in GSP here because this item's segment allowlist has no GSR or GSC.
That placement is exactly the kind of decision an interoperability reviewer
has to confirm or reverse, and nothing here says one has.

GSP-5.3, the coding system of the value, is read for exactly one thing: the
``code_system`` of a specified gender identity value, the only concept whose
value type has a field for it. A populated GSP-5.3 with pronouns, recorded
sex or gender, or sex parameter for clinical use, or with a presence state
under any concept, is a field the profile has no reading for and rejects
the message; a value asserted in a coding system is never carried as if it
were the bare token (A-033). OBX-11 Observation Result Status is required
and must be ``F``: an OBX without a final result status is not a supporting
observation. OBR-25 Result Status is optional in the standard and is
admitted empty or ``F``.
"""

_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:/_.+-]{0,95}$")
"""What a populated value may look like: a bounded code, never prose."""

_TIMESTAMP = re.compile(
    r"^[0-9]{8}(?:[0-9]{2}){0,3}(?:\.[0-9]{1,4})?(?:[+-][0-9]{4})?$"
)
"""MSH-7's shape, checked structurally and never carried anywhere."""

_SEGMENT_NAME = re.compile(r"^[A-Z][A-Z0-9]{2}$")
_SET_ID = re.compile(r"^[0-9]{1,4}$")
_SEGMENT_TERMINATOR = "\r"
_HEADER_LENGTH = 9
"""``MSH``, the field separator, four encoding characters, the separator again."""

_PROFILE_FIELDS: Mapping[str, Mapping[int, bool]] = MappingProxyType(
    {
        "MSH": MappingProxyType(
            dict.fromkeys((1, 2, 3, 4, 5, 6, 7, 9, 10, 11, 12, 15, 16, 18), False)
        ),
        "PID": MappingProxyType({1: False, 3: False, 5: True, 8: False}),
        "GSP": MappingProxyType(dict.fromkeys((1, 2, 4, 5), False)),
        "OBR": MappingProxyType(dict.fromkeys((1, 2, 3, 4, 25), False)),
        "OBX": MappingProxyType(dict.fromkeys((1, 2, 3, 4, 5, 11), False)),
    }
)
"""The fields the profile admits, by segment, and whether each may repeat.

A populated field outside this table rejects the message. An empty field is
not content and is not rejected for being where it is.
"""

_PID_PROHIBITED_FIELDS = frozenset(
    {4, 6, 7, 9, 10, 11, 12, 13, 14, 18, 19, 20, 21, 23, 29}
)
"""PID fields that are identifying by definition and reject as such."""

_VALUE_EXEMPT_FIELDS = frozenset({("MSH", 1), ("MSH", 2), ("MSH", 7), ("MSH", 18)})
"""Fields with their own closed check instead of the token-and-detector scan."""

_PRESENCE_STATES: Mapping[str, ValueStatus] = MappingProxyType(
    {
        ValueStatus.DECLINED.value: ValueStatus.DECLINED,
        ValueStatus.UNKNOWN.value: ValueStatus.UNKNOWN,
        ValueStatus.ABSENT.value: ValueStatus.ABSENT,
    }
)
"""GSP-5 codes that are presence states rather than values."""

_CONCEPT_OF_TYPE: Mapping[type, ConceptKind] = MappingProxyType(
    {
        GenderIdentity: ConceptKind.GENDER_IDENTITY,
        RecordedSexOrGender: ConceptKind.RECORDED_SEX_OR_GENDER,
        SexParameterForClinicalUse: ConceptKind.SEX_PARAMETER_FOR_CLINICAL_USE,
        NameToUse: ConceptKind.NAME_TO_USE,
        Pronouns: ConceptKind.PRONOUNS,
    }
)
"""The concept an observation is labelled with, from the type of its value.

This is what makes the PID-8 rule structural. :func:`_administrative_sex`
can only build a :class:`RecordedSexOrGender`, and a
:class:`RecordedSexOrGender` can only be labelled recorded sex or gender.
"""

_WARNINGS: tuple[ImportWarningCode, ...] = (
    ImportWarningCode.CHECKPOINT_NOT_IN_SOURCE,
    ImportWarningCode.MAPPING_PROFILE_NOT_BOUND,
)
"""Every conversion this importer makes carries both limits."""

type Component = tuple[str, ...]
type Repetition = tuple[Component, ...]
type Field = tuple[Repetition, ...]


@dataclass(frozen=True, slots=True)
class Delimiters:
    """The five characters MSH-1 and MSH-2 declare, in their declared order."""

    field: str
    component: str
    repetition: str
    escape: str
    subcomponent: str


@dataclass(frozen=True, slots=True)
class Segment:
    """One parsed segment: its name, its ordinal among its kind, its fields."""

    name: str
    ordinal: int
    fields: tuple[Field, ...]

    @property
    def path(self) -> str:
        return f"$.{self.name}[{self.ordinal}]"

    def pointer(self, number: int, repetition: int = 1, component: int = 1) -> str:
        """The ``SEG[n]-field.rep.comp`` pointer under the message root."""

        return f"{self.path}-{number}.{repetition}.{component}"

    def field(self, number: int) -> Field:
        return self.fields[number - 1] if number <= len(self.fields) else ()

    def populated(self, number: int) -> bool:
        return any(
            sub
            for repetition in self.field(number)
            for comp in repetition
            for sub in comp
        )

    def text(self, number: int, component: int = 1) -> str:
        """First repetition, first subcomponent of ``component``, or empty."""

        repetitions = self.field(number)
        if not repetitions or component > len(repetitions[0]):
            return ""
        return repetitions[0][component - 1][0]


@dataclass(frozen=True, slots=True)
class _Order:
    obr: Segment
    obx: tuple[Segment, ...] = ()
    gsp: tuple[Segment, ...] = ()


@dataclass(frozen=True, slots=True)
class _Message:
    msh: Segment
    pid: Segment
    gsp: tuple[Segment, ...]
    orders: tuple[_Order, ...]


@dataclass(frozen=True, slots=True)
class _OrderContext:
    context_id: str
    supporting_observation_ids: tuple[str, ...]


@dataclass
class _Emitter:
    """Numbers observations in document order and binds them to the source."""

    case_id: str
    checkpoint: Checkpoint
    source_sha256: str
    observations: list[Observation] = field(default_factory=list)
    tokens: list[SourceToken] = field(default_factory=list)

    def emit(
        self, value: SemanticValue, pointer: str, carrier: str, token: str
    ) -> None:
        concept = _CONCEPT_OF_TYPE[type(value)]
        index = len(self.observations)
        self.tokens.append(SourceToken(concept=concept, carrier=carrier, token=token))
        self.observations.append(
            Observation(
                schema_version=OBSERVATION_SCHEMA_VERSION,
                observation_id=f"OBS-{self.case_id}-R{index:04d}",
                case_id=self.case_id,
                checkpoint=self.checkpoint,
                concept=concept,
                value=value,
                evidence=EvidencePointer(
                    source_sha256=self.source_sha256, source_pointer=pointer
                ),
                mapping=MappingDescriptor(
                    source_concept=concept,
                    target_concept=concept,
                    mapping_version=HL7V2_ER7_MAPPING_VERSION,
                ),
            )
        )


def _hl7_error(code: Hl7RejectionCode, path: str, message: str) -> ContextSafeError:
    return contract_error(code.value, path, message)


# --- the ER7 encoding ---------------------------------------------------------


def _decode(raw: bytes) -> str:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise contract_error("invalid_utf8", "$", "input must be UTF-8") from exc
    for character in text:
        if character != _SEGMENT_TERMINATOR and unicodedata.category(character) in {
            "Cc",
            "Cf",
        }:
            raise contract_error(
                "prohibited_unicode",
                "$",
                "control and format characters are prohibited outside the "
                "segment terminator",
            )
    return text


def _delimiter_character(character: str) -> bool:
    return 0x21 <= ord(character) <= 0x7E and not character.isalnum()


def _delimiters(text: str) -> Delimiters:
    if len(text) < _HEADER_LENGTH or not text.startswith("MSH"):
        raise _hl7_error(
            Hl7RejectionCode.NOT_ER7, "$", "input does not begin with an MSH segment"
        )
    declared = text[3:8]
    if (
        text[8] != declared[0]
        or len(set(declared)) != len(declared)
        or not all(_delimiter_character(item) for item in declared)
    ):
        raise _hl7_error(
            Hl7RejectionCode.DELIMITERS_INVALID,
            "$.MSH[1]-2.1.1",
            "MSH-1 and MSH-2 must declare five distinct printable, "
            "non-alphanumeric delimiters",
        )
    return Delimiters(*declared)


def _segment_texts(text: str) -> list[str]:
    if not text.endswith(_SEGMENT_TERMINATOR):
        raise _hl7_error(
            Hl7RejectionCode.SEGMENT_TERMINATOR_INVALID,
            "$",
            "every segment must end with a carriage return",
        )
    parts = text[:-1].split(_SEGMENT_TERMINATOR)
    if len(parts) > HL7V2_ER7_PROFILE.max_segments:
        raise _hl7_error(
            Hl7RejectionCode.SEGMENT_COUNT_EXCEEDED,
            "$",
            "message exceeds the profile's segment bound",
        )
    return parts


def _unescape(value: str, delimiters: Delimiters, path: str) -> str:
    escape = delimiters.escape
    if escape not in value:
        return value
    table = {
        "F": delimiters.field,
        "S": delimiters.component,
        "T": delimiters.subcomponent,
        "R": delimiters.repetition,
        "E": escape,
    }
    pieces: list[str] = []
    position = 0
    while position < len(value):
        character = value[position]
        if character != escape:
            pieces.append(character)
            position += 1
            continue
        end = value.find(escape, position + 1)
        replacement = table.get(value[position + 1 : end]) if end != -1 else None
        if replacement is None:
            raise _hl7_error(
                Hl7RejectionCode.ESCAPE_UNSUPPORTED,
                path,
                "only the five delimiter escape sequences are handled",
            )
        pieces.append(replacement)
        position = end + 1
    return "".join(pieces)


def _parse_field(text: str, delimiters: Delimiters, path: str) -> Field:
    return tuple(
        tuple(
            tuple(
                _unescape(sub, delimiters, path)
                for sub in comp.split(delimiters.subcomponent)
            )
            for comp in rep.split(delimiters.component)
        )
        for rep in text.split(delimiters.repetition)
    )


def _raw_field(value: str) -> Field:
    return (((value,),),)


def _parse_segment(
    text: str, index: int, delimiters: Delimiters, ordinals: dict[str, int]
) -> Segment:
    name = text[:3]
    if (
        _SEGMENT_NAME.fullmatch(name) is None
        or len(text) < 4
        or text[3] != delimiters.field
    ):
        raise _hl7_error(
            Hl7RejectionCode.SEGMENT_MALFORMED,
            f"$[{index}]",
            "a segment must be a three-character name and a field separator",
        )
    if name not in HL7V2_ER7_PROFILE.segment_allowlist:
        raise import_error(
            ImportErrorCode.SEGMENT_NOT_ALLOWED,
            f"$[{index}]",
            "segment is outside the profile's closed allowlist",
        )
    if name == "MSH" and index != 0:
        raise _hl7_error(
            Hl7RejectionCode.SEGMENT_ORDER_INVALID,
            f"$[{index}]",
            "a message carries exactly one MSH segment, first",
        )
    ordinals[name] = ordinals.get(name, 0) + 1
    path = f"$.{name}[{ordinals[name]}]"
    if name == "MSH":
        rest = text[_HEADER_LENGTH:].split(delimiters.field)
        fields = (
            _raw_field(delimiters.field),
            _raw_field(text[4:8]),
            *(_parse_field(item, delimiters, path) for item in rest),
        )
    else:
        fields = tuple(
            _parse_field(item, delimiters, path)
            for item in text[4:].split(delimiters.field)
        )
    return Segment(name=name, ordinal=ordinals[name], fields=fields)


def parse_er7(raw: bytes) -> tuple[Segment, ...]:
    """Parse one ER7 message into segments, or reject it whole.

    Structural only: delimiters, terminator, segment names, the allowlist,
    escapes, and the field/repetition/component/subcomponent tree. The
    profile checks and the boundary scan over values follow in
    :func:`convert_raw`.
    """

    text = _decode(raw)
    delimiters = _delimiters(text)
    ordinals: dict[str, int] = {}
    return tuple(
        _parse_segment(item, index, delimiters, ordinals)
        for index, item in enumerate(_segment_texts(text))
    )


# --- the profile: fields, values, structure -----------------------------------


def _check_fields(segment: Segment) -> None:
    """Reject a populated field the profile does not name, or one that repeats."""

    rules = _PROFILE_FIELDS[segment.name]
    for number in range(1, len(segment.fields) + 1):
        if not segment.populated(number):
            continue
        pointer = segment.pointer(number)
        if segment.name == "PID" and number in _PID_PROHIBITED_FIELDS:
            raise contract_error(
                "prohibited_field", pointer, "an identifying field is prohibited"
            )
        repeats = rules.get(number)
        if repeats is None:
            raise import_error(
                ImportErrorCode.FIELD_NOT_IN_PROFILE,
                pointer,
                "field is outside the profile",
            )
        if not repeats and len(segment.field(number)) > 1:
            raise import_error(
                ImportErrorCode.REPETITION_NOT_ALLOWED,
                pointer,
                "the profile admits one value in this field",
            )


def _check_value(value: str, pointer: str) -> None:
    if _TOKEN.fullmatch(value) is None:
        raise contract_error(
            "unapproved_free_text",
            pointer,
            "a value must be a bounded code token; free text is prohibited",
        )
    hits = identifier_hits(value)
    if any(hit.startswith("canary:") for hit in hits):
        raise contract_error(
            "phi_canary_detected", pointer, "a configured PHI canary was detected"
        )
    if hits:
        raise contract_error(
            "direct_identifier_detected",
            pointer,
            "a direct-identifier pattern was detected",
        )


def _check_values(segment: Segment) -> None:
    """Every populated value is a token, and trips no boundary detector."""

    for number, repetitions in enumerate(segment.fields, 1):
        if (segment.name, number) in _VALUE_EXEMPT_FIELDS:
            continue
        for rep_index, repetition in enumerate(repetitions, 1):
            for comp_index, component in enumerate(repetition, 1):
                for value in component:
                    if value:
                        _check_value(
                            value, segment.pointer(number, rep_index, comp_index)
                        )


def _components(segment: Segment, number: int, limit: int) -> tuple[str, ...]:
    """Components 1..``limit`` of the first repetition, first subcomponents.

    A populated component beyond ``limit`` or a populated second
    subcomponent is content the profile has no reading for.
    """

    repetitions = segment.field(number)
    repetition: Repetition = repetitions[0] if repetitions else ()
    for comp_index, component in enumerate(repetition, 1):
        for sub_index, value in enumerate(component, 1):
            if value and (comp_index > limit or sub_index > 1):
                raise import_error(
                    ImportErrorCode.FIELD_NOT_IN_PROFILE,
                    segment.pointer(number, 1, comp_index),
                    "component is outside the profile",
                )
    values = [component[0] for component in repetition[:limit]]
    return tuple(values + [""] * (limit - len(values)))


def _closed_code(segment: Segment, number: int, allowed: frozenset[str]) -> str:
    (value,) = _components(segment, number, 1)
    if value and value not in allowed:
        raise import_error(
            ImportErrorCode.VALUE_NOT_IN_PROFILE,
            segment.pointer(number),
            "value is outside the profile's closed set",
        )
    return value


def _set_id(segment: Segment, number: int) -> None:
    (value,) = _components(segment, number, 1)
    if value and _SET_ID.fullmatch(value) is None:
        raise import_error(
            ImportErrorCode.VALUE_NOT_IN_PROFILE,
            segment.pointer(number),
            "a set ID must be a short number",
        )


def _check_msh(msh: Segment) -> None:
    profile = HL7V2_ER7_PROFILE
    _check_fields(msh)
    _check_values(msh)
    if any(not msh.populated(number) for number in (9, 10, 11, 12)):
        raise _hl7_error(
            Hl7RejectionCode.HEADER_INVALID,
            msh.path,
            "MSH must carry a message type, control ID, processing ID, and version",
        )
    (timestamp,) = _components(msh, 7, 1)
    if timestamp and _TIMESTAMP.fullmatch(timestamp) is None:
        raise import_error(
            ImportErrorCode.VALUE_NOT_IN_PROFILE,
            msh.pointer(7),
            "MSH-7 must be an HL7 timestamp",
        )
    _components(msh, 9, 3)
    _components(msh, 10, 1)
    if _components(msh, 11, 1)[0] not in profile.processing_ids:
        raise _hl7_error(
            Hl7RejectionCode.PROCESSING_ID_NOT_TEST,
            msh.pointer(11),
            "MSH-11 must be a debugging or training processing ID",
        )
    if _components(msh, 12, 1)[0] != profile.hl7_version:
        raise _hl7_error(
            Hl7RejectionCode.VERSION_UNSUPPORTED,
            msh.pointer(12),
            "MSH-12 must name the version the profile is written for",
        )
    _closed_code(msh, 15, profile.accept_types)
    _closed_code(msh, 16, profile.accept_types)
    (character_set,) = _components(msh, 18, 1)
    if character_set and character_set not in profile.character_sets:
        raise _hl7_error(
            Hl7RejectionCode.CHARACTER_SET_UNSUPPORTED,
            msh.pointer(18),
            "MSH-18 must be empty or name UTF-8",
        )


def _structure(segments: tuple[Segment, ...]) -> _Message:
    """Arrange segments as MSH, PID, patient GSPs, then order groups."""

    if len(segments) < 2 or segments[0].name != "MSH" or segments[1].name != "PID":
        raise _hl7_error(
            Hl7RejectionCode.SEGMENT_ORDER_INVALID,
            "$",
            "a message is MSH, then PID, then GSP and order groups",
        )
    patient_gsp: list[Segment] = []
    groups: list[tuple[Segment, list[Segment], list[Segment]]] = []
    for index, segment in enumerate(segments[2:], 2):
        if segment.name == "OBR":
            groups.append((segment, [], []))
        elif segment.name == "GSP" and not groups:
            patient_gsp.append(segment)
        elif segment.name == "GSP":
            groups[-1][2].append(segment)
        elif segment.name == "OBX" and groups:
            groups[-1][1].append(segment)
        else:
            raise _hl7_error(
                Hl7RejectionCode.SEGMENT_ORDER_INVALID,
                f"$[{index}]",
                "segment is outside the profile's message structure",
            )
    return _Message(
        msh=segments[0],
        pid=segments[1],
        gsp=tuple(patient_gsp),
        orders=tuple(_Order(obr, tuple(obx), tuple(gsp)) for obr, obx, gsp in groups),
    )


# --- PID ----------------------------------------------------------------------


def _not_synthetic(pid: Segment) -> ContextSafeError:
    return import_error(
        ImportErrorCode.IDENTIFIER_NOT_SYNTHETIC,
        pid.pointer(3),
        "PID-3 must carry the synthetic identifier system and a synthetic value",
    )


def _cx(pid: Segment) -> tuple[str, str, str, str]:
    """PID-3 as (ID, check digit, check-digit scheme, identifier type code).

    CX.4, the assigning authority, is the one component that may carry
    subcomponents; :func:`_authority` reads it. Anything populated past
    CX.5, or a second subcomponent anywhere else, is outside the profile.
    """

    repetitions = pid.field(3)
    repetition: Repetition = repetitions[0] if repetitions else ()
    for comp_index, component in enumerate(repetition, 1):
        for sub_index, value in enumerate(component, 1):
            if value and (comp_index > 5 or (sub_index > 1 and comp_index != 4)):
                raise import_error(
                    ImportErrorCode.FIELD_NOT_IN_PROFILE,
                    pid.pointer(3, 1, comp_index),
                    "identifier component is outside the profile",
                )
    values = [component[0] for component in repetition] + [""] * 5
    return values[0], values[1], values[2], values[4]


def _authority(pid: Segment) -> str:
    """CX.4, the assigning authority, as the one identifier system it names.

    Two spellings are admitted and nothing else: the system as the
    namespace ID alone (``system``), or as the universal ID with the
    universal ID type ``URI`` (``^system^URI``). Both must name the
    synthetic identifier system.
    """

    repetitions = pid.field(3)
    repetition: Repetition = repetitions[0] if repetitions else ()
    subcomponents = repetition[3] if len(repetition) >= 4 else ()
    if any(subcomponents[3:]):
        raise import_error(
            ImportErrorCode.FIELD_NOT_IN_PROFILE,
            pid.pointer(3, 1, 4),
            "assigning authority carries subcomponents outside the profile",
        )
    padded = (*subcomponents, "", "", "")
    namespace, universal_id, universal_type = padded[0], padded[1], padded[2]
    as_namespace = namespace and not universal_id and not universal_type
    as_universal = not namespace and universal_id and universal_type == "URI"
    if not (as_namespace or as_universal):
        raise _not_synthetic(pid)
    return universal_id if as_universal else namespace


def _check_identifier(pid: Segment, case: SyntheticCase) -> None:
    """PID-3 must be the case's synthetic identifier, in its namespace."""

    if not pid.populated(3):
        raise import_error(
            ImportErrorCode.VALUE_MISSING, pid.pointer(3), "PID-3 is required"
        )
    identifier, check_digit, scheme, type_code = _cx(pid)
    if check_digit or scheme:
        raise import_error(
            ImportErrorCode.FIELD_NOT_IN_PROFILE,
            pid.pointer(3, 1, 2),
            "check digits are outside the profile",
        )
    system = _authority(pid)
    if (
        not identifier.startswith(SYNTHETIC_VALUE_PREFIX)
        or system != SYNTHETIC_IDENTIFIER_SYSTEM
    ):
        raise _not_synthetic(pid)
    if type_code and type_code not in HL7V2_ER7_PROFILE.identifier_type_codes:
        raise import_error(
            ImportErrorCode.VALUE_NOT_IN_PROFILE,
            pid.pointer(3, 1, 5),
            "identifier type code is outside the profile",
        )
    if (
        identifier != case.synthetic_identifier.value
        or system != case.synthetic_identifier.system
        or identifier != f"{SYNTHETIC_VALUE_PREFIX}{case.case_id}"
    ):
        raise import_error(
            ImportErrorCode.CASE_MISMATCH,
            pid.pointer(3),
            "PID-3 must match the case document's synthetic identifier",
        )


def _name_repetition(
    pid: Segment, repetition: Repetition, rep_index: int
) -> tuple[str, str]:
    """One XPN: (name type code, given name), with the family name checked."""

    profile = HL7V2_ER7_PROFILE
    pointer = pid.pointer(5, rep_index)
    for comp_index, component in enumerate(repetition, 1):
        for sub_index, value in enumerate(component, 1):
            if value and (comp_index not in {1, 2, 7} or sub_index > 1):
                raise import_error(
                    ImportErrorCode.FIELD_NOT_IN_PROFILE,
                    pid.pointer(5, rep_index, comp_index),
                    "name component is outside the profile",
                )
    values = [component[0] for component in repetition] + [""] * 7
    family, given, type_code = values[0], values[1], values[6]
    if type_code not in {profile.name_to_use_type_code, profile.legal_name_type_code}:
        raise import_error(
            ImportErrorCode.VALUE_NOT_IN_PROFILE,
            pid.pointer(5, rep_index, 7),
            "name type code is outside the profile",
        )
    if family != profile.synthetic_family_name or not given.startswith(
        SYNTHETIC_VALUE_PREFIX
    ):
        raise contract_error(
            "non_synthetic_name", pointer, "names must use the synthetic tokens"
        )
    return type_code, given


def _name_to_use(pid: Segment) -> tuple[NameToUse, str, str] | None:
    """The one PID-5 repetition typed as the name to use, if there is one.

    Returns the value, its pointer, and the given token the source said.
    """

    profile = HL7V2_ER7_PROFILE
    found: list[tuple[NameToUse, str, str]] = []
    for rep_index, repetition in enumerate(pid.field(5), 1):
        if not any(value for component in repetition for value in component):
            continue
        type_code, given = _name_repetition(pid, repetition, rep_index)
        if type_code == profile.name_to_use_type_code:
            found.append(
                (
                    NameToUse(status=ValueStatus.SPECIFIED, value=given, use="usual"),
                    pid.pointer(5, rep_index, 2),
                    given,
                )
            )
    if len(found) > 1:
        raise import_error(
            ImportErrorCode.VALUE_AMBIGUOUS,
            pid.pointer(5),
            "more than one name carries the name-to-use type code",
        )
    return found[0] if found else None


def _administrative_sex(pid: Segment) -> RecordedSexOrGender | None:
    """The only reader of PID-8, and it can only build a recorded sex or gender.

    The return type is the rule. A value read here is labelled
    ``recorded_sex_or_gender`` with the context ``administrative`` because
    :data:`_CONCEPT_OF_TYPE` labels every :class:`RecordedSexOrGender` that
    way; there is no argument, table, or flag by which it could be labelled
    gender identity or sex parameter for clinical use.
    """

    (value,) = _components(pid, 8, 1)
    if not value:
        return None
    return RecordedSexOrGender(
        value=value, context=ADMINISTRATIVE_CONTEXT, source=PID_8_SOURCE
    )


def _convert_pid(pid: Segment, case: SyntheticCase, emitter: _Emitter) -> None:
    _check_fields(pid)
    _check_values(pid)
    _set_id(pid, 1)
    _check_identifier(pid, case)
    name = _name_to_use(pid)
    if name is not None:
        emitter.emit(name[0], name[1], NAME_CARRIER, name[2])
    sex = _administrative_sex(pid)
    if sex is not None:
        emitter.emit(sex, pid.pointer(8), ADMINISTRATIVE_SEX_CARRIER, sex.value)


# --- GSP, OBR, OBX ------------------------------------------------------------


def _concept_type(gsp: Segment) -> ConceptKind:
    code, text, system = _components(gsp, 4, 3)
    if text:
        raise contract_error(
            "unapproved_free_text",
            gsp.pointer(4, 1, 2),
            "display text is not read; the profile admits the code alone",
        )
    concept = HL7V2_ER7_PROFILE.concept_types.get((code, system))
    if concept is None:
        raise import_error(
            ImportErrorCode.FIELD_CODE_UNMAPPED,
            gsp.pointer(4),
            "GSP-4 has no entry in the profile's closed concept-type table",
        )
    return concept


def _gsp_code(gsp: Segment) -> tuple[str, str]:
    """GSP-5 as (code, coding system); the code is required."""

    code, text, system = _components(gsp, 5, 3)
    if text:
        raise contract_error(
            "unapproved_free_text",
            gsp.pointer(5, 1, 2),
            "display text is not read; the profile admits the code alone",
        )
    if not code:
        raise import_error(
            ImportErrorCode.VALUE_MISSING,
            gsp.pointer(5),
            "GSP-5 carries no code; absence is not a value",
        )
    return code, system


def _presence(code: str) -> tuple[ValueStatus, str | None]:
    status = _PRESENCE_STATES.get(code)
    if status is not None:
        return status, None
    return ValueStatus.SPECIFIED, code


def _check_coding_system(
    gsp: Segment, concept: ConceptKind, code: str, system: str
) -> None:
    """GSP-5.3 is read with a specified gender identity value and nowhere else.

    Pronouns, recorded sex or gender, and sex parameter for clinical use
    have no field for a coding system, and a presence state is not a code
    in any system. Dropping the system and carrying the bare code would
    accept a value the sender asserted in a namespace this profile does not
    read, as if it were the fixture's own token (A-033).
    """

    if not system:
        return
    if concept is not ConceptKind.GENDER_IDENTITY or code in _PRESENCE_STATES:
        raise import_error(
            ImportErrorCode.FIELD_NOT_IN_PROFILE,
            gsp.pointer(5, 1, 3),
            "a coding system is read only with a specified gender identity "
            "value; the profile has no reading for it here",
        )


def _gsp_value(gsp: Segment, order: _OrderContext | None) -> tuple[SemanticValue, str]:
    """The typed GSP-5 value and the code the source said."""

    concept = _concept_type(gsp)
    code, system = _gsp_code(gsp)
    _check_coding_system(gsp, concept, code, system)
    if concept is ConceptKind.GENDER_IDENTITY:
        status, value = _presence(code)
        return GenderIdentity(
            status=status, value=value, code_system=system or UNBOUND_CODE_SYSTEM
        ), code
    if concept is ConceptKind.PRONOUNS:
        status, value = _presence(code)
        return Pronouns(status=status, value=value), code
    if concept is ConceptKind.RECORDED_SEX_OR_GENDER:
        return RecordedSexOrGender(
            value=code, context=UNBOUND_CONTEXT, source=GSP_SOURCE
        ), code
    return _sex_parameter(gsp, code, order), code


def _sex_parameter(
    gsp: Segment, code: str, order: _OrderContext | None
) -> SexParameterForClinicalUse:
    if order is None:
        raise import_error(
            ImportErrorCode.CONCEPT_NOT_CONVERTIBLE,
            gsp.pointer(4),
            "sex parameter for clinical use needs an order context; this GSP "
            "segment precedes every OBR",
        )
    if code in _PRESENCE_STATES:
        raise import_error(
            ImportErrorCode.VALUE_NOT_IN_PROFILE,
            gsp.pointer(5),
            "a presence state is not a sex parameter for clinical use",
        )
    return SexParameterForClinicalUse(
        value=code,
        context_id=order.context_id,
        supporting_observation_ids=order.supporting_observation_ids,
    )


def _convert_gsp(gsp: Segment, order: _OrderContext | None, emitter: _Emitter) -> None:
    _check_fields(gsp)
    _check_values(gsp)
    _set_id(gsp, 1)
    _closed_code(gsp, 2, frozenset({"A"}))
    if not gsp.populated(4):
        raise import_error(
            ImportErrorCode.VALUE_MISSING, gsp.pointer(4), "GSP-4 is required"
        )
    value, code = _gsp_value(gsp, order)
    emitter.emit(value, gsp.pointer(5), GSP_VALUE_CARRIER, code)


def _order_identifier(obr: Segment, number: int, *, required: bool) -> str:
    identifier = _components(obr, number, 1)[0]
    if not identifier and required:
        raise import_error(
            ImportErrorCode.CONTEXT_MISSING,
            obr.pointer(number),
            "an order needs a placer order number to be an SPCU context",
        )
    if identifier and not identifier.startswith(ORDER_CONTEXT_PREFIX):
        raise contract_error(
            "non_synthetic_context",
            obr.pointer(number),
            "order numbers must use the synthetic order namespace",
        )
    return identifier


def _coded_identifier(segment: Segment, number: int) -> None:
    """A CWE that is read for shape only: code and coding system, no text."""

    _code, text, _system = _components(segment, number, 3)
    if text:
        raise contract_error(
            "unapproved_free_text",
            segment.pointer(number, 1, 2),
            "display text is not read; the profile admits the code alone",
        )


def _supporting_observation(obx: Segment) -> str:
    _check_fields(obx)
    _check_values(obx)
    _set_id(obx, 1)
    value_type = _components(obx, 2, 1)[0]
    if value_type in {"FT", "ST", "TX"}:
        raise contract_error(
            "unapproved_free_text",
            obx.pointer(2),
            "a text-typed OBX is free text and is prohibited",
        )
    if value_type != "CWE":
        raise import_error(
            ImportErrorCode.VALUE_NOT_IN_PROFILE,
            obx.pointer(2),
            "OBX-2 must be CWE; other value types are outside the profile",
        )
    _coded_identifier(obx, 3)
    _components(obx, 4, 1)
    _coded_identifier(obx, 5)
    if not _closed_code(obx, 11, frozenset({"F"})):
        raise import_error(
            ImportErrorCode.VALUE_MISSING,
            obx.pointer(11),
            "OBX-11 is required; an OBX without a final result status is not "
            "a supporting observation",
        )
    token = obx.text(5)
    if not token.startswith(SUPPORTING_OBSERVATION_PREFIX):
        raise import_error(
            ImportErrorCode.VALUE_NOT_IN_PROFILE,
            obx.pointer(5),
            "OBX-5 must carry a synthetic supporting-observation token",
        )
    return token


def _order_context(order: _Order) -> _OrderContext:
    obr = order.obr
    _check_fields(obr)
    _check_values(obr)
    _set_id(obr, 1)
    context_id = _order_identifier(obr, 2, required=True)
    _order_identifier(obr, 3, required=False)
    _coded_identifier(obr, 4)
    _closed_code(obr, 25, frozenset({"F"}))
    return _OrderContext(
        context_id=context_id,
        supporting_observation_ids=tuple(
            _supporting_observation(obx) for obx in order.obx
        ),
    )


# --- the conversion -----------------------------------------------------------


def convert_raw(
    source: RawSource, *, case: SyntheticCase, checkpoint: Checkpoint
) -> ImportResult:
    """Convert one already-read message against a case document.

    The message is parsed structurally, arranged into the profile's message
    structure, checked field by field and value by value, cross-checked
    against the case document, and converted in document order. The
    converted document is then re-validated by the observation contract
    itself, so a value this profile typed and the contract rejects (an RSG
    value outside its set, a missing supporting observation) rejects the
    source with the contract's own code. The message cannot state a
    checkpoint, so the requested one is applied and the result says so.
    """

    message = _structure(parse_er7(source.raw))
    _check_msh(message.msh)
    emitter = _Emitter(
        case_id=case.case_id, checkpoint=checkpoint, source_sha256=source.raw_sha256
    )
    _convert_pid(message.pid, case, emitter)
    for gsp in message.gsp:
        _convert_gsp(gsp, None, emitter)
    for order in message.orders:
        context = _order_context(order)
        for gsp in order.gsp:
            _convert_gsp(gsp, context, emitter)
    validated = parse_observations(
        {
            "observations": [item.to_dict() for item in emitter.observations],
            "schema_version": OBSERVATION_SET_SCHEMA_VERSION,
        }
    )
    return ImportResult(
        format_name=HL7V2_ER7_FORMAT,
        mapping_version=HL7V2_ER7_MAPPING_VERSION,
        source_sha256=source.raw_sha256,
        source_byte_count=source.raw_byte_count,
        record_count=len(validated),
        observations=validated,
        warnings=_WARNINGS,
        source_tokens=tuple(emitter.tokens),
    )


class Hl7v2Er7Importer:
    """The registered importer for one HL7 v2 ER7 message."""

    @property
    def format_name(self) -> str:
        return HL7V2_ER7_FORMAT

    @property
    def mapping_version(self) -> str:
        return HL7V2_ER7_MAPPING_VERSION

    @property
    def carriers(self) -> Mapping[str, frozenset[ConceptKind]]:
        return HL7V2_ER7_CARRIERS

    def convert(
        self, source: Path, *, case: SyntheticCase, checkpoint: Checkpoint
    ) -> ImportResult:
        """Read ``source`` through the evidence boundary, then convert it."""

        return convert_raw(read_source(source), case=case, checkpoint=checkpoint)


HL7V2_ER7_IMPORTER = Hl7v2Er7Importer()
