"""The FHIR R4 JSON importer: one Patient in, observation set out.

Reference-only and ungoverned. The reader below maps the HL7 Gender Harmony
representations on a FHIR R4 ``Patient`` to the five canonical concepts
through the closed profile in :data:`FHIR_R4_PROFILE`. No interoperability,
clinical, laboratory, or community reviewer has approved that profile; it is
not a mapping profile in the B-026 sense, and every result it produces says
``profile_reviewed: false`` and cannot say otherwise. Where the
implementation guide's exact element for a concept was uncertain, the choice
made here is written into the profile constant's docstring rather than into
the code path, so a reviewer can find and overturn it in one place.

The source converts whole or not at all, and nothing outside the allowlist
is dropped. A FHIR document is not read as "the parts we recognise": every
object is checked against an exact allowlist of element names, and the
first element outside it rejects the document with a code and a location. A
narrative, a contained resource, a note, an address, a telecom, a birth
date, or a URL that is not one of the profile's published constants is
rejected before this module sees the value, by the same boundary scan every
other format runs through. A ``display``, a ``comment`` sub-extension, a
resource type outside the allowlist, a reference to anything, an identifier
outside the synthetic namespace, a coded value outside the synthetic
alphabet, or a Gender Harmony extension this reader knows and cannot carry
rejects here. The rejection names a category and a location and never the
content.

What the allowlist admits and the canonical model cannot hold is validated
and not carried, and the list is closed: ``Patient.id`` and
``Patient.active``; every ``HumanName`` whose ``use`` is not ``usual``;
``family`` on the usual name; the system of the pronouns coding; and the
system of the recorded-sex-or-gender ``value`` coding. Each is a bounded
token, a boolean, or a synthetic name part, so nothing identifying passes
through the gap, but an emitted observation set is the five concepts and
not the whole Patient, and a consumer must not read it as one.

Values are the source's own tokens, verbatim. A gender-identity code of
``CSYN-GENDER-1`` becomes exactly that string with the coding's own system;
a pronouns code stays a token; a recorded-sex-or-gender code is carried only
if it is in the observation contract's own closed alphabet, which this
module imports rather than restates, and rejects at the extension's own
location otherwise, never normalized to the closest one (A-033). A
data-absent-reason code is not a recorded value at all and rejects too,
because the canonical concept has no presence state for it to become. Every
coding's system and code is bounded here to the contract's token length, so
that every rejection a caller sees names a location in the FHIR document
and the contract's re-validation of the converted document is a second
check that must not fire. Sex parameter for clinical use comes only from its own
extension, and this iteration cannot carry it: the canonical concept needs
an order context and a supporting-observation link, and neither an
``Encounter`` nor a ``ServiceRequest`` is implemented as a carrier, so the
extension rejects rather than arriving without what makes it safe to
evaluate. Nothing here derives SPCU from gender identity, recorded sex or
gender, or anything else; the mapping is an identity over concepts.

Ambiguity is preserved, not resolved. Two gender-identity extensions, or two
names with ``use`` equal to ``usual``, become two observations with two
source pointers, and the evaluator reports ``ambiguous_evidence`` for the
rule they both answer. Absence is not invented either: a ``Patient`` with
none of the concepts rejects rather than becoming an empty set that reads
as evidence, and a name without a declared ``use`` rejects rather than
being guessed to be, or not to be, the name to use.
"""

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from contextsafe.contract_validation import (
    array_value,
    boolean_value,
    bounded_string,
    contract_error,
    enum_string,
    object_value,
)
from contextsafe.importers.base import (
    UNBOUND_SOURCE,
    ImportErrorCode,
    ImportResult,
    ImportWarningCode,
    import_error,
)
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
    SyntheticCase,
    ValueStatus,
)
from contextsafe.plan import SYNTHETIC_IDENTIFIER_SYSTEM
from contextsafe.preflight import BoundaryProfile, ScannedSource, scan_source
from contextsafe.validation import RSG_VALUES, parse_observations

FHIR_R4_FORMAT = "fhir-r4-json"
"""The ``--format`` name of this importer."""


@dataclass(frozen=True, slots=True)
class FhirR4Profile:
    """The closed set of choices this reader makes about the FHIR R4 form.

    A profile is versioned so that a change to any choice is a change to the
    ``mapping.mapping_version`` on every observation, and it carries
    ``reviewed`` so that the question of governance cannot be omitted; the
    field is ``False`` and the constructor refuses ``True``. Every field is
    one decision, documented on the constant below.
    """

    version: str
    gender_identity_url: str
    pronouns_url: str
    recorded_sex_or_gender_url: str
    sex_parameter_url: str
    value_sub_extension: str
    rsg_context_sub_extension: str
    presence_code_system: str
    presence_codes: tuple[tuple[str, ValueStatus], ...]
    name_to_use_use: str
    synthetic_family_name: str
    reviewed: bool = False

    def __post_init__(self) -> None:
        if self.reviewed:
            raise contract_error(
                "profile_review_not_available",
                "$.reviewed",
                "no FHIR profile has been reviewed; the flag cannot be set",
            )


FHIR_R4_PROFILE = FhirR4Profile(
    version="0.1.0",
    gender_identity_url=(
        "http://hl7.org/fhir/StructureDefinition/individual-genderIdentity"
    ),
    pronouns_url="http://hl7.org/fhir/StructureDefinition/individual-pronouns",
    recorded_sex_or_gender_url=(
        "http://hl7.org/fhir/StructureDefinition/individual-recordedSexOrGender"
    ),
    sex_parameter_url=(
        "http://hl7.org/fhir/StructureDefinition/patient-sexParameterForClinicalUse"
    ),
    value_sub_extension="value",
    rsg_context_sub_extension="type",
    presence_code_system="http://terminology.hl7.org/CodeSystem/data-absent-reason",
    presence_codes=(
        ("asked-declined", ValueStatus.DECLINED),
        ("unknown", ValueStatus.UNKNOWN),
        ("not-asked", ValueStatus.ABSENT),
    ),
    name_to_use_use="usual",
    synthetic_family_name="ZZZTESTCONTEXTSAFE",
)
"""Version 0.1.0 of the reader's choices. Reference-only; ``reviewed`` is False.

The four extension URLs are the ones the HL7 Gender Harmony implementation
guide publishes for FHIR (``docs/16-RESEARCH-SOURCES.md`` names the guide);
they are matched exactly, and the boundary scan exempts exactly these
strings from its URL detector, nothing that merely starts like them.

Choices the guide leaves less certain than the URLs, each of which a
reviewer may overturn by changing this constant and its version:

* Every Gender Harmony extension is read as a complex extension whose coded
  value sits in a sub-extension named ``value`` carrying one
  ``valueCodeableConcept`` with exactly one ``coding``. The guide's ``period``
  and ``comment`` sub-extensions are not carried: a period is a pair of
  dates, which the boundary treats as identifying, and a comment is free
  text. Either rejects the source rather than being dropped.
* Recorded sex or gender's canonical ``context`` is read from the guide's
  ``type`` sub-extension (the kind of record the value was taken from) and
  is required. The guide's ``jurisdiction``, ``sourceDocument``,
  ``sourceField``, ``effectivePeriod``, and ``acquisitionDate`` are not
  carried, so the canonical ``source`` is the fixed unbound token rather
  than a value guessed from one of them.
* A presence state (declined, unknown, not collected) is read only from a
  coding in the ``data-absent-reason`` system with one of three codes:
  ``asked-declined``, ``unknown``, ``not-asked``, and only for gender
  identity and pronouns, whose canonical models carry a status. Any other
  code in that system rejects. Whether the guide binds these exact codes
  for every concept is the choice a reviewer should check first.
* Recorded sex or gender carries no presence state. The canonical model has
  a value and a context and no status, so a ``value`` or ``type`` coding in
  the ``data-absent-reason`` system rejects as not convertible rather than
  arriving as a recorded value: the code ``unknown`` in that system means
  "not recorded" and the same token in the observation contract's alphabet
  means "recorded as unknown", and the reader does not let one become the
  other. The ``value`` code must be in the observation contract's closed
  alphabet (``F``, ``M``, ``X``, ``unknown``), checked at the extension's
  own location; the coding's system is otherwise not carried, because the
  canonical model has no field for it, and a reviewer may pin the systems
  an RSG value may come from by adding them here.
* Name to use is the ``HumanName`` whose ``use`` is ``usual``, with exactly
  one ``given`` part, which is the value. ``family``, when present on any
  name, must be the synthetic family token or a ``CSYN-`` token. Every
  name, whatever its ``use``, carries at least one of ``given`` and
  ``family``; a name that is only a ``use`` is an element the reader would
  otherwise admit and ignore, and it rejects instead.
* Sex parameter for clinical use is recognised by its URL and always
  rejects, because no allowlisted resource carries an order context or a
  supporting observation. This is a limit, not a mapping.
* Admitted, validated, and not carried, because the canonical model has no
  field for them: ``Patient.id`` (a synthetic token), ``Patient.active`` (a
  boolean), every ``HumanName`` whose ``use`` is not ``usual`` (its parts
  are still required to be synthetic), ``family`` on the usual name, the
  pronouns coding's system, and the recorded-sex-or-gender ``value``
  coding's system. Nothing else the allowlist admits goes uncarried, and a
  reviewer who wants any of these carried changes the canonical model
  first and this constant's version second.
"""

FHIR_R4_MAPPING_VERSION = FHIR_R4_PROFILE.version
"""Recorded as ``mapping.mapping_version`` on every observation emitted."""

NAME_CARRIER = "Patient.name"
"""The carrier a mapping profile names for the usual ``HumanName``'s given token.

The name to use is not an extension, so it has no URL; this is the one
carrier name in the FHIR table that is not one.
"""

FHIR_R4_CARRIERS: Mapping[str, frozenset[ConceptKind]] = {
    FHIR_R4_PROFILE.gender_identity_url: frozenset({ConceptKind.GENDER_IDENTITY}),
    FHIR_R4_PROFILE.pronouns_url: frozenset({ConceptKind.PRONOUNS}),
    FHIR_R4_PROFILE.recorded_sex_or_gender_url: frozenset(
        {ConceptKind.RECORDED_SEX_OR_GENDER}
    ),
    NAME_CARRIER: frozenset({ConceptKind.NAME_TO_USE}),
}
"""What a mapping profile for this format may name as a carrier.

Each extension URL reads as exactly its own concept. The sex parameter URL
is absent because the reader never emits it, so no profile can bind it.
"""

_PRESENCE_CODES: Mapping[str, ValueStatus] = dict(FHIR_R4_PROFILE.presence_codes)

FHIR_R4_BOUNDARY_PROFILE = BoundaryProfile(
    permitted_keys=frozenset({"name"}),
    path_keys=frozenset(
        {
            "active",
            "name",
            "code",
            "coding",
            "entry",
            "extension",
            "family",
            "fullUrl",
            "gender",
            "generalPractitioner",
            "given",
            "id",
            "identifier",
            "link",
            "managingOrganization",
            "meta",
            "resource",
            "resourceType",
            "total",
            "type",
            "url",
            "use",
            "valueCodeableConcept",
        }
    ),
    published_constants=frozenset(
        {
            FHIR_R4_PROFILE.gender_identity_url,
            FHIR_R4_PROFILE.pronouns_url,
            FHIR_R4_PROFILE.recorded_sex_or_gender_url,
            FHIR_R4_PROFILE.sex_parameter_url,
            FHIR_R4_PROFILE.presence_code_system,
        }
    ),
)
"""What this format's boundary scan differs in from the canonical scan.

``name`` is permitted because a ``Patient`` cannot say who a person is to
be called without it; what may be under it is decided below, and every
string under it is still scanned. It is also a path key, so a rejection
under a name says ``$.name[0]`` rather than a location that reads as if
the root were an array. The published constants are the five
URLs the standard itself defines; an extension URL outside them is
rejected by the scan as a URL pattern before this module runs, which is
the intended outcome for an unknown extension, not a detour around it.
"""

_MAX_LIST_ITEMS = 64
_RESOURCE_ID = re.compile(r"^CSYN-[A-Za-z0-9.-]{1,59}$")
_SYNTHETIC_CODE = re.compile(r"^CSYN-[A-Z0-9][A-Z0-9_.:-]{0,95}$")
_CODING_TOKEN_LENGTH = 96
"""The observation contract's token bound, applied to every coding here.

The contract bounds a code system, a context, and a value at 96 characters.
A coding's system and code are bounded to the same length at the coding's
own location, so an over-long one is rejected where it sits in the FHIR
document rather than in the converted document at a path the source never
had. The published FHIR source schema states the same bound.
"""
_CODING_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:/_.-]{0,95}$")
_NAME_TOKEN = re.compile(r"^CSYN-[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$")

_PATIENT_REQUIRED = frozenset({"resourceType", "identifier"})
_PATIENT_OPTIONAL = frozenset({"id", "active", "name", "extension"})
_PATIENT_REFERENCE_KEYS = frozenset(
    {"generalPractitioner", "link", "managingOrganization"}
)
"""``Patient`` elements that are references to other resources.

No other resource can be in the document, so a reference in one of these
can only point outside it. They are named so the rejection says why rather
than reporting an unsupported element.
"""
_BUNDLE_REQUIRED = frozenset({"resourceType", "type", "entry"})
_BUNDLE_OPTIONAL = frozenset({"total"})
_BUNDLE_TYPES = frozenset({"collection", "searchset"})
_ENTRY_KEYS = frozenset({"resource"})
_IDENTIFIER_KEYS = frozenset({"system", "value"})
_NAME_REQUIRED = frozenset({"use"})
_NAME_OPTIONAL = frozenset({"family", "given"})
_NAME_USES = frozenset(
    {"anonymous", "maiden", "nickname", "official", "old", "temp", "usual"}
)
_EXTENSION_KEYS = frozenset({"url", "extension"})
_SUB_EXTENSION_KEYS = frozenset({"url", "valueCodeableConcept"})
_CODEABLE_CONCEPT_KEYS = frozenset({"coding"})
_CODING_KEYS = frozenset({"system", "code"})

_WARNINGS: tuple[ImportWarningCode, ...] = (
    ImportWarningCode.CHECKPOINT_ASSERTED_BY_CALLER,
    ImportWarningCode.MAPPING_PROFILE_NOT_BOUND,
)
"""Every conversion this importer makes carries both limits."""


@dataclass(frozen=True, slots=True)
class _Cursor:
    """One location in the document, in both notations a caller needs.

    ``path`` is the ``$``-rooted location every ContextSafe error carries;
    ``pointer`` is the RFC 6901 JSON Pointer an observation records. Both
    are built from allowlisted element names and array indexes only.
    """

    segments: tuple[str | int, ...] = ()

    def child(self, segment: str | int) -> "_Cursor":
        return _Cursor((*self.segments, segment))

    @property
    def path(self) -> str:
        return "$" + "".join(
            f"[{segment}]" if isinstance(segment, int) else f".{segment}"
            for segment in self.segments
        )

    @property
    def pointer(self) -> str:
        return "".join(f"/{segment}" for segment in self.segments)


@dataclass(frozen=True, slots=True)
class _Coding:
    system: str
    code: str


type _Found = tuple[_Cursor, ConceptKind, SemanticValue, SourceToken]
"""Where it was read, what it is, the value built, and what the source said."""


def _allowed_keys(
    data: dict[str, object],
    cursor: _Cursor,
    *,
    required: frozenset[str],
    optional: frozenset[str] = frozenset(),
) -> None:
    """Reject the first element outside the allowlist; nothing is stripped."""

    if data.keys() - required - optional:
        raise import_error(
            ImportErrorCode.ELEMENT_UNSUPPORTED,
            cursor.path,
            "an element is outside this profile's allowlist; nothing is "
            "stripped and the source is rejected whole",
        )
    missing = sorted(required - data.keys())
    if missing:
        raise contract_error(
            "missing_field", f"{cursor.path}.{missing[0]}", "required field is missing"
        )


def _bounded_list(value: object, cursor: _Cursor) -> list[object]:
    items = array_value(value, cursor.path)
    if not items or len(items) > _MAX_LIST_ITEMS:
        raise import_error(
            ImportErrorCode.CARDINALITY_UNSUPPORTED,
            cursor.path,
            "a list must carry between one and sixty-four items",
        )
    return items


def _resource_type(resource: dict[str, object], cursor: _Cursor) -> str:
    if "resourceType" not in resource:
        raise contract_error(
            "missing_field", f"{cursor.path}.resourceType", "required field is missing"
        )
    return bounded_string(resource["resourceType"], f"{cursor.path}.resourceType")


def _unsupported_resource(cursor: _Cursor) -> Exception:
    return import_error(
        ImportErrorCode.RESOURCE_UNSUPPORTED,
        cursor.path,
        "only a Patient, alone or as the entries of a Bundle, is readable; "
        "no Encounter, ServiceRequest, or other resource is implemented",
    )


def _document_patient(value: object) -> tuple[dict[str, object], _Cursor]:
    """Find the one Patient the document is, or carries."""

    root_cursor = _Cursor()
    root = object_value(value, root_cursor.path)
    resource_type = _resource_type(root, root_cursor)
    if resource_type == "Patient":
        return root, root_cursor
    if resource_type != "Bundle":
        raise _unsupported_resource(root_cursor)
    return _bundle_patient(root, root_cursor)


def _is_count(value: object, expected: int) -> bool:
    """True only for the integer ``expected``; ``1.0`` and ``True`` are not it."""

    return isinstance(value, int) and not isinstance(value, bool) and value == expected


def _bundle_patient(
    bundle: dict[str, object], cursor: _Cursor
) -> tuple[dict[str, object], _Cursor]:
    _allowed_keys(bundle, cursor, required=_BUNDLE_REQUIRED, optional=_BUNDLE_OPTIONAL)
    enum_string(bundle["type"], f"{cursor.path}.type", _BUNDLE_TYPES)
    entries = _bounded_list(bundle["entry"], cursor.child("entry"))
    if "total" in bundle and not _is_count(bundle["total"], len(entries)):
        raise import_error(
            ImportErrorCode.CARDINALITY_UNSUPPORTED,
            f"{cursor.path}.total",
            "a stated total must be an integer equal to the number of entries carried",
        )
    patients: list[tuple[dict[str, object], _Cursor]] = []
    for index, raw_entry in enumerate(entries):
        entry_cursor = cursor.child("entry").child(index)
        entry = object_value(raw_entry, entry_cursor.path)
        _allowed_keys(entry, entry_cursor, required=_ENTRY_KEYS)
        resource_cursor = entry_cursor.child("resource")
        resource = object_value(entry["resource"], resource_cursor.path)
        if _resource_type(resource, resource_cursor) != "Patient":
            raise _unsupported_resource(resource_cursor)
        patients.append((resource, resource_cursor))
    if len(patients) != 1:
        raise import_error(
            ImportErrorCode.CARDINALITY_UNSUPPORTED,
            cursor.child("entry").path,
            "a document carries exactly one Patient",
        )
    return patients[0]


def _reject_references(resource: dict[str, object], cursor: _Cursor) -> None:
    for key in sorted(_PATIENT_REFERENCE_KEYS & resource.keys()):
        raise import_error(
            ImportErrorCode.REFERENCE_OUTSIDE_DOCUMENT,
            cursor.child(key).path,
            "a reference cannot resolve to a resource in this document",
        )


def _resource_id(value: object, cursor: _Cursor) -> None:
    if not isinstance(value, str) or _RESOURCE_ID.fullmatch(value) is None:
        raise import_error(
            ImportErrorCode.IDENTIFIER_NOT_SYNTHETIC,
            cursor.path,
            "a resource id must be a synthetic token",
        )


def _identifiers(value: object, cursor: _Cursor, case: SyntheticCase) -> None:
    """Every identifier is synthetic, and one of them is the case token."""

    tokens: list[str] = []
    for index, raw in enumerate(_bounded_list(value, cursor)):
        item_cursor = cursor.child(index)
        identifier = object_value(raw, item_cursor.path)
        _allowed_keys(identifier, item_cursor, required=_IDENTIFIER_KEYS)
        system = bounded_string(identifier["system"], item_cursor.child("system").path)
        token = bounded_string(identifier["value"], item_cursor.child("value").path)
        if system != SYNTHETIC_IDENTIFIER_SYSTEM or (
            _SYNTHETIC_CODE.fullmatch(token) is None
        ):
            raise import_error(
                ImportErrorCode.IDENTIFIER_NOT_SYNTHETIC,
                item_cursor.path,
                "every identifier must be in the synthetic namespace",
            )
        tokens.append(token)
    if case.synthetic_identifier.value not in tokens:
        raise import_error(
            ImportErrorCode.CASE_MISMATCH,
            cursor.path,
            "no identifier carries the case document's synthetic token",
        )


def _extension_url(extension: dict[str, object], cursor: _Cursor) -> str:
    if "url" not in extension:
        raise contract_error(
            "missing_field", f"{cursor.path}.url", "required field is missing"
        )
    return bounded_string(extension["url"], f"{cursor.path}.url")


def _coding(value: object, cursor: _Cursor) -> _Coding:
    concept = object_value(value, cursor.path)
    _allowed_keys(concept, cursor, required=_CODEABLE_CONCEPT_KEYS)
    codings_cursor = cursor.child("coding")
    codings = array_value(concept["coding"], codings_cursor.path)
    if len(codings) != 1:
        raise import_error(
            ImportErrorCode.CARDINALITY_UNSUPPORTED,
            codings_cursor.path,
            "a coded value carries exactly one coding; no profile binds "
            "translations to one another",
        )
    coding_cursor = codings_cursor.child(0)
    coding = object_value(codings[0], coding_cursor.path)
    _allowed_keys(coding, coding_cursor, required=_CODING_KEYS)
    return _Coding(
        system=bounded_string(
            coding["system"],
            coding_cursor.child("system").path,
            pattern=_CODING_TOKEN,
            max_length=_CODING_TOKEN_LENGTH,
        ),
        code=bounded_string(
            coding["code"],
            coding_cursor.child("code").path,
            pattern=_CODING_TOKEN,
            max_length=_CODING_TOKEN_LENGTH,
        ),
    )


def _sub_extensions(
    value: object, cursor: _Cursor, *, allowed: frozenset[str]
) -> dict[str, _Coding]:
    parts: dict[str, _Coding] = {}
    for index, raw in enumerate(_bounded_list(value, cursor)):
        sub_cursor = cursor.child(index)
        sub = object_value(raw, sub_cursor.path)
        url = _extension_url(sub, sub_cursor)
        if url not in allowed:
            raise import_error(
                ImportErrorCode.EXTENSION_UNKNOWN,
                sub_cursor.path,
                "a sub-extension is outside the profile for this extension",
            )
        if url in parts:
            raise import_error(
                ImportErrorCode.CARDINALITY_UNSUPPORTED,
                sub_cursor.path,
                "a sub-extension appears at most once",
            )
        _allowed_keys(sub, sub_cursor, required=_SUB_EXTENSION_KEYS)
        parts[url] = _coding(
            sub["valueCodeableConcept"], sub_cursor.child("valueCodeableConcept")
        )
    return parts


def _required_part(parts: dict[str, _Coding], name: str, cursor: _Cursor) -> _Coding:
    part = parts.get(name)
    if part is None:
        code = (
            ImportErrorCode.CONTEXT_MISSING
            if name == FHIR_R4_PROFILE.rsg_context_sub_extension
            else ImportErrorCode.VALUE_MISSING
        )
        raise import_error(
            code, cursor.path, "the extension does not carry a required sub-extension"
        )
    return part


def _synthetic_code(coding: _Coding, cursor: _Cursor) -> str:
    if _SYNTHETIC_CODE.fullmatch(coding.code) is None:
        raise import_error(
            ImportErrorCode.VALUE_UNSUPPORTED,
            cursor.path,
            "a coded value must be a synthetic token",
        )
    return coding.code


def _presence(coding: _Coding, cursor: _Cursor) -> tuple[ValueStatus, str | None]:
    """Type a coding as a presence state or a verbatim synthetic value."""

    if coding.system == FHIR_R4_PROFILE.presence_code_system:
        status = _PRESENCE_CODES.get(coding.code)
        if status is None:
            raise import_error(
                ImportErrorCode.VALUE_UNSUPPORTED,
                cursor.path,
                "a presence code is outside the profile's closed set",
            )
        return status, None
    return ValueStatus.SPECIFIED, _synthetic_code(coding, cursor)


def _gender_identity(parts: dict[str, _Coding], cursor: _Cursor) -> SemanticValue:
    coding = _required_part(parts, FHIR_R4_PROFILE.value_sub_extension, cursor)
    status, value = _presence(coding, cursor)
    return GenderIdentity(status=status, value=value, code_system=coding.system)


def _pronouns(parts: dict[str, _Coding], cursor: _Cursor) -> SemanticValue:
    coding = _required_part(parts, FHIR_R4_PROFILE.value_sub_extension, cursor)
    status, value = _presence(coding, cursor)
    return Pronouns(status=status, value=value)


def _recorded_coding(coding: _Coding, cursor: _Cursor) -> _Coding:
    """Refuse a presence coding where the canonical model has no status.

    Recorded sex or gender is a value and a context; it has nowhere to carry
    "declined", "unknown", or "not asked" as a state, and ``unknown`` in the
    data-absent-reason system is not the recorded value ``unknown``. The
    coding rejects as not convertible rather than becoming a recorded value.
    """

    if coding.system == FHIR_R4_PROFILE.presence_code_system:
        raise import_error(
            ImportErrorCode.CONCEPT_NOT_CONVERTIBLE,
            cursor.path,
            "recorded sex or gender carries no presence state; a data-absent "
            "code is not a recorded value and is not carried as one",
        )
    return coding


def _recorded_value(coding: _Coding, cursor: _Cursor) -> str:
    """Admit only the observation contract's own closed alphabet, verbatim.

    ``female`` is not ``F`` and ``f`` is not ``F``: a code outside the
    alphabet rejects at the extension's location and is never mapped to the
    nearest member (A-033). The alphabet is imported from the contract, so
    this reader cannot admit a value the contract would refuse.
    """

    if coding.code not in RSG_VALUES:
        raise import_error(
            ImportErrorCode.VALUE_UNSUPPORTED,
            cursor.path,
            "a recorded sex or gender value is outside the observation "
            "contract's closed alphabet and is not normalized to a member of it",
        )
    return coding.code


def _recorded_sex_or_gender(
    parts: dict[str, _Coding], cursor: _Cursor
) -> SemanticValue:
    value = _recorded_value(
        _recorded_coding(
            _required_part(parts, FHIR_R4_PROFILE.value_sub_extension, cursor),
            cursor,
        ),
        cursor,
    )
    context = _recorded_coding(
        _required_part(parts, FHIR_R4_PROFILE.rsg_context_sub_extension, cursor),
        cursor,
    )
    return RecordedSexOrGender(
        value=value,
        context=_synthetic_code(context, cursor),
        source=UNBOUND_SOURCE,
    )


@dataclass(frozen=True, slots=True)
class _ExtensionRule:
    concept: ConceptKind
    sub_extensions: frozenset[str]
    convert: Callable[[dict[str, _Coding], _Cursor], SemanticValue]


_EXTENSIONS: Mapping[str, _ExtensionRule] = {
    FHIR_R4_PROFILE.gender_identity_url: _ExtensionRule(
        ConceptKind.GENDER_IDENTITY,
        frozenset({FHIR_R4_PROFILE.value_sub_extension}),
        _gender_identity,
    ),
    FHIR_R4_PROFILE.pronouns_url: _ExtensionRule(
        ConceptKind.PRONOUNS,
        frozenset({FHIR_R4_PROFILE.value_sub_extension}),
        _pronouns,
    ),
    FHIR_R4_PROFILE.recorded_sex_or_gender_url: _ExtensionRule(
        ConceptKind.RECORDED_SEX_OR_GENDER,
        frozenset(
            {
                FHIR_R4_PROFILE.value_sub_extension,
                FHIR_R4_PROFILE.rsg_context_sub_extension,
            }
        ),
        _recorded_sex_or_gender,
    ),
}
"""The closed extension mapping: a URL, its sub-extensions, its concept.

An identity over concepts: each URL names one concept and converts to that
concept, so no path through this table can arrive at sex parameter for
clinical use from anything, and the SPCU URL is deliberately not in it.
"""


def _extensions(value: object, cursor: _Cursor) -> list[_Found]:
    found: list[_Found] = []
    for index, raw in enumerate(_bounded_list(value, cursor)):
        extension_cursor = cursor.child(index)
        extension = object_value(raw, extension_cursor.path)
        url = _extension_url(extension, extension_cursor)
        if url == FHIR_R4_PROFILE.sex_parameter_url:
            raise import_error(
                ImportErrorCode.CONCEPT_NOT_CONVERTIBLE,
                extension_cursor.path,
                "sex parameter for clinical use needs an order context and a "
                "supporting-observation link; no allowlisted resource carries "
                "them, and the extension is not carried without them",
            )
        rule = _EXTENSIONS.get(url)
        if rule is None:
            raise import_error(
                ImportErrorCode.EXTENSION_UNKNOWN,
                extension_cursor.path,
                "an extension is outside the profile's published set",
            )
        _allowed_keys(extension, extension_cursor, required=_EXTENSION_KEYS)
        parts = _sub_extensions(
            extension["extension"],
            extension_cursor.child("extension"),
            allowed=rule.sub_extensions,
        )
        value = rule.convert(parts, extension_cursor)
        # The conversion required the value sub-extension, so it is present;
        # its code is the token the source said, before any profile binds it.
        token = SourceToken(
            concept=rule.concept,
            carrier=url,
            token=parts[FHIR_R4_PROFILE.value_sub_extension].code,
        )
        found.append((extension_cursor, rule.concept, value, token))
    return found


def _name_part(value: object, cursor: _Cursor) -> str:
    token = bounded_string(value, cursor.path)
    if _NAME_TOKEN.fullmatch(token) is None and (
        token != FHIR_R4_PROFILE.synthetic_family_name
    ):
        raise import_error(
            ImportErrorCode.VALUE_UNSUPPORTED,
            cursor.path,
            "a name part must be a synthetic token",
        )
    return token


def _given(name: dict[str, object], cursor: _Cursor) -> list[str]:
    if "given" not in name:
        return []
    given_cursor = cursor.child("given")
    return [
        _name_part(item, given_cursor.child(index))
        for index, item in enumerate(_bounded_list(name["given"], given_cursor))
    ]


def _names(value: object, cursor: _Cursor) -> list[_Found]:
    found: list[_Found] = []
    for index, raw in enumerate(_bounded_list(value, cursor)):
        name_cursor = cursor.child(index)
        name = object_value(raw, name_cursor.path)
        _allowed_keys(
            name, name_cursor, required=_NAME_REQUIRED, optional=_NAME_OPTIONAL
        )
        use = enum_string(name["use"], name_cursor.child("use").path, _NAME_USES)
        if not _NAME_OPTIONAL & name.keys():
            raise import_error(
                ImportErrorCode.CARDINALITY_UNSUPPORTED,
                name_cursor.path,
                "a name carries at least one part; a use alone is not a name "
                "and is not admitted to be ignored",
            )
        given = _given(name, name_cursor)
        if "family" in name:
            _name_part(name["family"], name_cursor.child("family"))
        if use != FHIR_R4_PROFILE.name_to_use_use:
            continue
        if len(given) != 1:
            raise import_error(
                ImportErrorCode.CARDINALITY_UNSUPPORTED,
                name_cursor.child("given").path,
                "the name to use carries exactly one given token",
            )
        value_to_use = NameToUse(status=ValueStatus.SPECIFIED, value=given[0], use=use)
        token = SourceToken(
            concept=ConceptKind.NAME_TO_USE, carrier=NAME_CARRIER, token=given[0]
        )
        found.append((name_cursor, ConceptKind.NAME_TO_USE, value_to_use, token))
    return found


def _patient(
    resource: dict[str, object], cursor: _Cursor, *, case: SyntheticCase
) -> list[_Found]:
    """Read one Patient against the allowlist and return what it carries."""

    _reject_references(resource, cursor)
    _allowed_keys(
        resource, cursor, required=_PATIENT_REQUIRED, optional=_PATIENT_OPTIONAL
    )
    if "id" in resource:
        _resource_id(resource["id"], cursor.child("id"))
    if "active" in resource:
        boolean_value(resource["active"], cursor.child("active").path)
    _identifiers(resource["identifier"], cursor.child("identifier"), case)
    found: list[_Found] = []
    if "extension" in resource:
        found.extend(_extensions(resource["extension"], cursor.child("extension")))
    if "name" in resource:
        found.extend(_names(resource["name"], cursor.child("name")))
    if not found:
        raise import_error(
            ImportErrorCode.CARDINALITY_UNSUPPORTED,
            cursor.path,
            "the Patient carries none of the five concepts; an empty set is "
            "not evidence and is not emitted",
        )
    return found


def _observation(
    index: int,
    found: _Found,
    *,
    case_id: str,
    checkpoint: Checkpoint,
    source_sha256: str,
) -> Observation:
    cursor, concept, value, _token = found
    return Observation(
        schema_version=OBSERVATION_SCHEMA_VERSION,
        observation_id=f"OBS-{case_id}-F{index:04d}",
        case_id=case_id,
        checkpoint=checkpoint,
        concept=concept,
        value=value,
        evidence=EvidencePointer(
            source_sha256=source_sha256, source_pointer=cursor.pointer
        ),
        mapping=MappingDescriptor(
            source_concept=concept,
            target_concept=concept,
            mapping_version=FHIR_R4_MAPPING_VERSION,
        ),
    )


def convert_scanned(
    scanned: ScannedSource, *, case: SyntheticCase, checkpoint: Checkpoint
) -> ImportResult:
    """Convert an already boundary-scanned FHIR document against a case.

    The document is read against the exact allowlist, its identifiers are
    cross-checked against the case document the caller holds, and every
    Gender Harmony extension and usual name becomes one observation at the
    checkpoint the caller asked for; a FHIR document names no checkpoint,
    and the result says so. The converted document is then re-validated by
    the observation contract as a second check: every value this reader
    carries is bounded and alphabet-checked at its own location in the
    source first, so a rejection from the contract here would be a defect
    in this module, not a location a caller is expected to see.
    """

    resource, cursor = _document_patient(scanned.value)
    found = _patient(resource, cursor, case=case)
    converted = tuple(
        _observation(
            index,
            item,
            case_id=case.case_id,
            checkpoint=checkpoint,
            source_sha256=scanned.raw_sha256,
        )
        for index, item in enumerate(found)
    )
    validated = parse_observations(
        {
            "observations": [item.to_dict() for item in converted],
            "schema_version": OBSERVATION_SET_SCHEMA_VERSION,
        }
    )
    return ImportResult(
        format_name=FHIR_R4_FORMAT,
        mapping_version=FHIR_R4_MAPPING_VERSION,
        source_sha256=scanned.raw_sha256,
        source_byte_count=scanned.raw_byte_count,
        record_count=len(found),
        observations=validated,
        warnings=_WARNINGS,
        source_tokens=tuple(item[3] for item in found),
    )


class FhirR4JsonImporter:
    """The registered importer for one FHIR R4 JSON Patient document."""

    @property
    def format_name(self) -> str:
        return FHIR_R4_FORMAT

    @property
    def mapping_version(self) -> str:
        return FHIR_R4_MAPPING_VERSION

    @property
    def carriers(self) -> Mapping[str, frozenset[ConceptKind]]:
        return FHIR_R4_CARRIERS

    def convert(
        self, source: Path, *, case: SyntheticCase, checkpoint: Checkpoint
    ) -> ImportResult:
        """Scan ``source`` through the FHIR boundary profile, then convert it."""

        return convert_scanned(
            scan_source(source, FHIR_R4_BOUNDARY_PROFILE),
            case=case,
            checkpoint=checkpoint,
        )


FHIR_R4_JSON_IMPORTER = FhirR4JsonImporter()
