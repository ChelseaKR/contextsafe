"""The versioned mapping profile: a declared, unreviewed token table (B-026).

A mapping profile is the document that says what a source's tokens mean. An
importer carries every value verbatim -- ``CSYN-PRONOUN-THEY-THEM`` stays
that string -- and a rule that expects ``they/them`` reports
``semantic_mismatch`` until something binds the two. This is that something:
a closed table from a source token (the carrier it was read from and the
token itself) to the canonical concept and value the observation should
carry, versioned, hashed, and applied by ``contextsafe import --mapping``.

Reference-only and ungoverned. The only review status this iteration admits
is ``not_reviewed``, and a profile that declares anything else is rejected
rather than read: a declared approval authorizes nothing here, exactly as a
declared approval on a pack authorizes nothing there. ``contextsafe mapping
sign`` (Architecture section 7) does not exist, no ContextSafe
interoperability reviewer has enrolled a key, and the compiled form every
profile is reduced to says ``signature_status: not_verified`` and
``executable: false``.

What a row may not say, stated once here and enforced in one place.

**No row crosses a concept.** The source names the concept the importer
read the token as; the target names the concept the observation carries.
The two must be the same, and a row whose target is sex parameter for
clinical use while its source is gender identity or recorded sex or gender
is refused first and by name (``prohibited_spcu_mapping``, A-020 and
A-021), before any other check, so that the prohibition is what a reader
finds when they try it. A row whose target is a different concept for any
other reason is refused as ``concept_type_mismatch``.

**No row invents a context.** A sex parameter for clinical use row binds
the value token and nothing else: the order context and the supporting
observations come from the source, and a profile cannot put an SPCU on an
order the source did not carry it on.

**Two source values never become one.** Two rows whose targets are the same
canonical value would let two different source tokens arrive as one value;
a reviewer reading the receipt would see agreement where the source
disagreed. Such a row set is refused. Two observations that carry the same
token are still two observations after mapping, and the evaluator reports
them ambiguous.

**Every target is synthetic.** A target value is held to the synthetic
grammar below (a ``CSYN-`` or ``fixture-`` token, a ``urn:contextsafe:``
system, the contract's closed recorded-sex alphabet, a closed recording
context, or a lowercase pronoun set), so a profile cannot be the route by
which a name, a date, or a free-text value reaches an observation.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from contextsafe.canonical import JsonValue, sha256_json
from contextsafe.contract_validation import (
    ID_PATTERN,
    SEMVER_PATTERN,
    array_value,
    bounded_string,
    contract_error,
    enum_string,
    exact_keys,
    object_value,
)
from contextsafe.models import (
    ConceptKind,
    GenderIdentity,
    NameToUse,
    Pronouns,
    RecordedSexOrGender,
    SemanticValue,
    SexParameterForClinicalUse,
)
from contextsafe.preflight import scan_text
from contextsafe.validation import parse_semantic_value

MAPPING_PROFILE_SCHEMA_VERSION = "contextsafe.mapping-profile/1.0.0"
"""The ``schema_version`` a profile document must carry."""

COMPILED_MAPPING_PROFILE_SCHEMA_VERSION = "contextsafe.compiled-mapping-profile/1.0.0"
"""The ``schema_version`` of the document ``mapping validate`` emits."""

REVIEW_STATUS_NOT_REVIEWED = "not_reviewed"
"""The only review status a profile may declare in this iteration."""

MAX_ROWS = 256
"""A profile is a token table for one format, not a terminology service."""

COMPILED_LIMITATIONS: tuple[str, ...] = (
    "profile-is-unsigned",
    "profile-review-has-not-happened",
    "mapping-sign-command-is-unbuilt",
)
"""What every compiled profile says about itself, in this order."""

SOURCE_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:/_.+-]{0,95}$")
"""What a source token may look like: a bounded code, never prose.

The union of the token grammars the importers admit, so a profile can name
any token an importer can emit and nothing an importer would refuse.
"""

SYNTHETIC_TOKEN_PATTERN = re.compile(
    r"^(?:CSYN-[A-Z0-9][A-Z0-9_.:-]{0,95}|fixture-[a-z0-9][a-z0-9-]{0,63})$"
)
"""A target value in the synthetic namespace: the two fixture token shapes."""

FIXTURE_SYSTEM_PATTERN = re.compile(r"^urn:contextsafe:[a-z0-9][a-z0-9.-]{0,63}$")
"""A code system or recording source a target may name: this project's URNs."""

PRONOUN_SET_PATTERN = re.compile(r"^[a-z]{1,12}/[a-z]{1,12}(?:/[a-z]{1,12})?$")
"""A pronoun set as a lowercase slash-separated shape, such as ``they/them``.

The one target form without a synthetic prefix, admitted because the case
contract's own reference pronouns value is ``they/them`` and a profile must
be able to bind a token to it. It is a shape, not a list: no closed set of
pronouns is published here, and it admits no capital, digit, or space, so no
name can be written in it.
"""

RSG_CONTEXTS = frozenset(
    {"administrative", "government-id", "jurisdictional", "laboratory", "payer"}
)
"""Recording contexts a recorded-sex-or-gender target may name, besides a token.

Closed and reference-only: the contexts the data model and the importers
already use. A context outside it must be a synthetic token.
"""

RSG_SOURCES = frozenset({"synthetic-fixture"})
"""Recording sources a recorded-sex-or-gender target may name, besides a token."""

_SPCU_VALUE = re.compile(r"^[A-Za-z0-9:/_.-]{1,96}$")
_CONCEPT_NAMES = frozenset(item.value for item in ConceptKind)
_PROHIBITED_SPCU_SOURCES = frozenset(
    {ConceptKind.GENDER_IDENTITY, ConceptKind.RECORDED_SEX_OR_GENDER}
)

type CarrierTable = Mapping[str, Mapping[str, frozenset[ConceptKind]]]
"""Format name to carrier name to the concepts that carrier may be read as.

The importer registry builds it from each importer's own declaration, so a
profile can only name a carrier an importer reads and only under a concept
that importer would emit it as. ``PID-8`` is recorded sex or gender and
nothing else here for the same reason it is nothing else in the reader.
"""


class MappingProfileErrorCode(StrEnum):
    """The rejection family a profile's own decisions may raise.

    Cross-concept rows raise the observation contract's own codes
    (``prohibited_spcu_mapping``, ``concept_type_mismatch``) so that the
    same prohibition has the same name wherever a reader meets it.
    """

    FORMAT_UNSUPPORTED = "mapping_profile_format_unsupported"
    """The profile names a format no importer is registered under."""

    REVIEW_NOT_AVAILABLE = "mapping_profile_review_not_available"
    """The profile declares a review status other than not_reviewed."""

    CARRIER_UNKNOWN = "mapping_profile_carrier_unknown"
    """A row names a carrier the format's importer does not read."""

    CARRIER_CONCEPT_MISMATCH = "mapping_profile_carrier_concept_mismatch"
    """A row reads a carrier as a concept the importer never emits it as."""

    SOURCE_DUPLICATE = "mapping_profile_source_duplicate"
    """Two rows name the same source token; which target applies is ambiguous."""

    TARGET_COLLAPSES_SOURCES = "mapping_profile_target_collapses_sources"
    """Two rows with different sources name one target value."""

    TARGET_NOT_SYNTHETIC = "mapping_profile_target_not_synthetic"
    """A target value is outside the synthetic grammar."""

    FORMAT_MISMATCH = "mapping_profile_format_mismatch"
    """The profile is for a format other than the one being imported."""

    NOT_APPLICABLE = "mapping_profile_not_applicable"
    """The import result carries nothing a profile could bind."""


@dataclass(frozen=True, slots=True)
class SourceToken:
    """What the source said: the concept it was read as, its carrier, its token.

    The carrier is the format's own name for where the token sat (a field
    code, an extension URL, a segment-field, a column); the token is the
    source's own value, verbatim. An importer records one per observation
    so a profile row matches on what the source said rather than on the
    canonical value the importer built from it.
    """

    concept: ConceptKind
    carrier: str
    token: str

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "carrier": self.carrier,
            "concept": self.concept.value,
            "token": self.token,
        }


@dataclass(frozen=True, slots=True)
class SpcuValueBinding:
    """The only thing a profile may bind on a sex parameter for clinical use.

    The value token alone. The order context and the supporting observations
    are the source's, and a profile has no field for either.
    """

    value: str

    def to_dict(self) -> dict[str, JsonValue]:
        return {"value": self.value}


type TargetValue = SemanticValue | SpcuValueBinding


@dataclass(frozen=True, slots=True)
class MappingRow:
    """One binding: a source token to the value its observation should carry."""

    source: SourceToken
    target_concept: ConceptKind
    target: TargetValue

    @property
    def key(self) -> tuple[ConceptKind, str, str]:
        return (self.source.concept, self.source.carrier, self.source.token)

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "source": self.source.to_dict(),
            "target": {
                "concept": self.target_concept.value,
                "value": self.target.to_dict(),
            },
        }


@dataclass(frozen=True, slots=True)
class MappingProfile:
    """A validated profile. ``reviewed`` is ``False`` and cannot be set."""

    schema_version: str
    profile_id: str
    format: str
    version: str
    rows: tuple[MappingRow, ...]
    reviewed: bool = False

    def __post_init__(self) -> None:
        if self.reviewed:
            raise contract_error(
                MappingProfileErrorCode.REVIEW_NOT_AVAILABLE.value,
                "$.reviewed",
                "no mapping profile has been reviewed; the flag cannot be set",
            )

    def to_dict(self) -> dict[str, JsonValue]:
        """Return the canonical profile: rows in source order, review fixed."""

        return {
            "format": self.format,
            "profile_id": self.profile_id,
            "review": {
                "reviewed_at": None,
                "reviewed_by": None,
                "status": REVIEW_STATUS_NOT_REVIEWED,
            },
            "rows": [
                row.to_dict()
                for row in sorted(
                    self.rows, key=lambda row: (row.key[0].value, *row.key[1:])
                )
            ],
            "schema_version": self.schema_version,
            "version": self.version,
        }

    def sha256(self) -> str:
        """The digest every bound observation records."""

        return sha256_json(self.to_dict())

    def index(self) -> Mapping[tuple[ConceptKind, str, str], MappingRow]:
        """Rows by source key; validation has already made the keys unique."""

        return {row.key: row for row in self.rows}


@dataclass(frozen=True, slots=True)
class MappingProfileCompilation:
    """What ``mapping validate`` emits: the canonical profile and its digest."""

    profile: MappingProfile
    profile_sha256: str

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "executable": False,
            "format": self.profile.format,
            "limitations": list(COMPILED_LIMITATIONS),
            "profile": self.profile.to_dict(),
            "profile_id": self.profile.profile_id,
            "profile_sha256": self.profile_sha256,
            "review_status": REVIEW_STATUS_NOT_REVIEWED,
            "row_count": len(self.profile.rows),
            "schema_version": COMPILED_MAPPING_PROFILE_SCHEMA_VERSION,
            "signature_status": "not_verified",
            "valid_for_signing": True,
            "version": self.profile.version,
        }


def _concept(value: object, path: str) -> ConceptKind:
    return ConceptKind(enum_string(value, path, _CONCEPT_NAMES))


def _review(value: object, path: str) -> None:
    """Admit exactly one review record: not reviewed, by nobody, never."""

    data = object_value(value, path)
    exact_keys(data, frozenset({"status", "reviewed_by", "reviewed_at"}), path)
    status = bounded_string(data["status"], f"{path}.status")
    if status != REVIEW_STATUS_NOT_REVIEWED:
        raise contract_error(
            MappingProfileErrorCode.REVIEW_NOT_AVAILABLE.value,
            f"{path}.status",
            "a declared review authorizes nothing; the only status this "
            "iteration admits is not_reviewed",
        )
    for field in ("reviewed_by", "reviewed_at"):
        if data[field] is not None:
            raise contract_error(
                MappingProfileErrorCode.REVIEW_NOT_AVAILABLE.value,
                f"{path}.{field}",
                "an unreviewed profile names no reviewer and no date",
            )


def _source(
    value: object, path: str, carriers: Mapping[str, frozenset[ConceptKind]]
) -> SourceToken:
    data = object_value(value, path)
    exact_keys(data, frozenset({"concept", "carrier", "token"}), path)
    concept = _concept(data["concept"], f"{path}.concept")
    carrier = bounded_string(data["carrier"], f"{path}.carrier")
    admitted = carriers.get(carrier)
    if admitted is None:
        raise contract_error(
            MappingProfileErrorCode.CARRIER_UNKNOWN.value,
            f"{path}.carrier",
            "the format's importer does not read this carrier",
        )
    if concept not in admitted:
        raise contract_error(
            MappingProfileErrorCode.CARRIER_CONCEPT_MISMATCH.value,
            f"{path}.concept",
            "the importer never emits this carrier as this concept",
        )
    token_path = f"{path}.token"
    token = bounded_string(
        data["token"], token_path, pattern=SOURCE_TOKEN_PATTERN, max_length=96
    )
    scan_text(token, token_path)
    return SourceToken(concept=concept, carrier=carrier, token=token)


def _require_same_concept(source: ConceptKind, target: ConceptKind, path: str) -> None:
    """The prohibition first and by name, then the general rule."""

    if (
        target is ConceptKind.SEX_PARAMETER_FOR_CLINICAL_USE
        and source in _PROHIBITED_SPCU_SOURCES
    ):
        raise contract_error(
            "prohibited_spcu_mapping",
            path,
            "GI and RSG can never be mapped into SPCU",
        )
    if source is not target:
        raise contract_error(
            "concept_type_mismatch",
            path,
            "canonical concept types cannot be assigned across types",
        )


def _target_value(concept: ConceptKind, value: object, path: str) -> TargetValue:
    if concept is ConceptKind.SEX_PARAMETER_FOR_CLINICAL_USE:
        data = object_value(value, path)
        exact_keys(data, frozenset({"value"}), path)
        return SpcuValueBinding(
            value=bounded_string(data["value"], f"{path}.value", pattern=_SPCU_VALUE)
        )
    return parse_semantic_value(concept, value, path)


def _gender_identity_problem(target: GenderIdentity) -> str | None:
    if target.value is not None and not SYNTHETIC_TOKEN_PATTERN.fullmatch(target.value):
        return "value"
    if not FIXTURE_SYSTEM_PATTERN.fullmatch(target.code_system):
        return "code_system"
    return None


def _recorded_sex_or_gender_problem(target: RecordedSexOrGender) -> str | None:
    if target.context not in RSG_CONTEXTS and not SYNTHETIC_TOKEN_PATTERN.fullmatch(
        target.context
    ):
        return "context"
    if (
        target.source not in RSG_SOURCES
        and not SYNTHETIC_TOKEN_PATTERN.fullmatch(target.source)
        and not FIXTURE_SYSTEM_PATTERN.fullmatch(target.source)
    ):
        return "source"
    return None


def _pronouns_problem(target: Pronouns) -> str | None:
    if (
        target.value is not None
        and not SYNTHETIC_TOKEN_PATTERN.fullmatch(target.value)
        and not PRONOUN_SET_PATTERN.fullmatch(target.value)
    ):
        return "value"
    return None


def _target_problem(target: TargetValue) -> str | None:
    """The field of ``target`` outside the synthetic grammar, or ``None``.

    Name to use needs no check of its own: the observation contract already
    requires a ``CSYN-`` token. A complete sex parameter for clinical use
    value is never a target (only its value binding is), so it falls with
    name to use into the arm that has nothing to add.
    """

    match target:
        case GenderIdentity():
            return _gender_identity_problem(target)
        case RecordedSexOrGender():
            return _recorded_sex_or_gender_problem(target)
        case Pronouns():
            return _pronouns_problem(target)
        case SpcuValueBinding():
            return None if SYNTHETIC_TOKEN_PATTERN.fullmatch(target.value) else "value"
        case NameToUse() | SexParameterForClinicalUse():
            return None


def _target(
    value: object, path: str, source_concept: ConceptKind
) -> tuple[ConceptKind, TargetValue]:
    """Parse a target against its source concept: same concept, synthetic value."""

    data = object_value(value, path)
    exact_keys(data, frozenset({"concept", "value"}), path)
    concept = _concept(data["concept"], f"{path}.concept")
    _require_same_concept(source_concept, concept, path)
    target = _target_value(concept, data["value"], f"{path}.value")
    problem = _target_problem(target)
    if problem is not None:
        raise contract_error(
            MappingProfileErrorCode.TARGET_NOT_SYNTHETIC.value,
            f"{path}.value.{problem}",
            "a target value must be in the synthetic namespace; a profile is "
            "not a route by which a real value reaches an observation",
        )
    return concept, target


def _row(
    value: object, path: str, carriers: Mapping[str, frozenset[ConceptKind]]
) -> MappingRow:
    data = object_value(value, path)
    exact_keys(data, frozenset({"source", "target"}), path)
    source = _source(data["source"], f"{path}.source", carriers)
    concept, target = _target(data["target"], f"{path}.target", source.concept)
    return MappingRow(source=source, target_concept=concept, target=target)


def _rows(
    value: object, path: str, carriers: Mapping[str, frozenset[ConceptKind]]
) -> tuple[MappingRow, ...]:
    items = array_value(value, path)
    if not items or len(items) > MAX_ROWS:
        raise contract_error(
            "invalid_row_count",
            path,
            f"a profile carries between 1 and {MAX_ROWS} rows",
        )
    rows: list[MappingRow] = []
    sources: set[tuple[ConceptKind, str, str]] = set()
    targets: set[str] = set()
    for index, item in enumerate(items):
        row_path = f"{path}[{index}]"
        row = _row(item, row_path, carriers)
        if row.key in sources:
            raise contract_error(
                MappingProfileErrorCode.SOURCE_DUPLICATE.value,
                f"{row_path}.source",
                "two rows name the same source token",
            )
        target_key = sha256_json(
            {"concept": row.target_concept.value, "value": row.target.to_dict()}
        )
        if target_key in targets:
            raise contract_error(
                MappingProfileErrorCode.TARGET_COLLAPSES_SOURCES.value,
                f"{row_path}.target",
                "two source tokens would collapse into one target value; both "
                "must be retained as distinct observations",
            )
        sources.add(row.key)
        targets.add(target_key)
        rows.append(row)
    return tuple(rows)


def parse_mapping_profile(value: object, *, carriers: CarrierTable) -> MappingProfile:
    """Validate one profile document against the registered carrier table.

    ``carriers`` is the importer registry's declaration of what each format
    reads and as which concept; the profile may name nothing outside it.
    The rejection names a code and a location, never a token.
    """

    data = object_value(value, "$")
    exact_keys(
        data,
        frozenset(
            {"schema_version", "profile_id", "format", "version", "review", "rows"}
        ),
        "$",
    )
    schema_version = bounded_string(data["schema_version"], "$.schema_version")
    if schema_version != MAPPING_PROFILE_SCHEMA_VERSION:
        raise contract_error(
            "unsupported_schema",
            "$.schema_version",
            "mapping profile schema is unsupported",
        )
    format_name = bounded_string(data["format"], "$.format")
    format_carriers = carriers.get(format_name)
    if format_carriers is None:
        raise contract_error(
            MappingProfileErrorCode.FORMAT_UNSUPPORTED.value,
            "$.format",
            "no importer is registered for the profile's format",
        )
    _review(data["review"], "$.review")
    return MappingProfile(
        schema_version=schema_version,
        profile_id=bounded_string(
            data["profile_id"], "$.profile_id", pattern=ID_PATTERN
        ),
        format=format_name,
        version=bounded_string(data["version"], "$.version", pattern=SEMVER_PATTERN),
        rows=_rows(data["rows"], "$.rows", format_carriers),
    )


def compile_mapping_profile(
    value: object, *, carriers: CarrierTable
) -> MappingProfileCompilation:
    """Validate a profile and return its canonical form with its digest."""

    profile = parse_mapping_profile(value, carriers=carriers)
    return MappingProfileCompilation(profile=profile, profile_sha256=profile.sha256())
