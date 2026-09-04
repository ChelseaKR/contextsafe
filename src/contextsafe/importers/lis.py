"""The LIS export identity importers: a result export in, identity out.

Reference-only and ungoverned. A laboratory result export carries the
patient's identity beside the results, and that identity is what a
result-facing display shows (A-031). ``--format lis-csv`` and ``--format
lis-json`` read only the identity columns of such an export and produce
name-to-use, pronoun, and recorded-sex-or-gender observations at the
``lis_return`` checkpoint. The column set is the versioned profile constant
:data:`LIS_PROFILE`, whose ``profile_reviewed`` is ``False`` and whose type
refuses ``True``: no laboratory, interoperability, clinical, or community
reviewer has approved it as the shape of any real export, and it is not a
mapping profile in the B-026 sense.

What it does not read. The result columns (``analyte``, ``value``,
``unit``, ``range``, ``flag``, ``order``, ``specimen``) are recognized,
bounded, scanned, and counted, and produce no observation, because the
laboratory result observation family is a later item and the observation
contract has no concept for a result. A source that carries them gets the
closed warning ``result_columns_not_observed`` and a count of the cells it
did not claim, never a silently dropped column. A column outside the
allowlist rejects the whole source, with the column's position and never
its name.

What it never does. ``sex`` maps only to recorded sex or gender, in the
fixed context ``laboratory``; no column can name gender identity or sex
parameter for clinical use, and nothing here derives either from anything.
An empty identity cell is not a value and rejects the source, the rule the
canonical importer applies to a null value code; a cell outside the closed
set its column admits is not normalized to the closest supported value
(A-033); an identifier outside the synthetic namespace anywhere in the
table rejects the source; and a cell that begins with a character a
spreadsheet would execute rejects the source. Values are the source's own
tokens, carried verbatim, so evaluating them against a rule that expects a
bound value reports ``semantic_mismatch`` until a mapping profile binds
them.

One observation per distinct value per identity column. A result export
has one row per result and repeats the patient's identity on every row;
converting every row would make the same value ambiguous with itself.
Exact duplicates therefore collapse to one observation, pointed at the
first row that carries the value, while rows that disagree produce one
observation each and evaluate as ambiguous rather than pass. Nothing is
chosen between them.

Both formats read into one table. CSV is the RFC 4180 subset in
:mod:`contextsafe.importers.lis_csv` with a header row; JSON is the
document ``schemas/contextsafe-lis-export-v0.1.schema.json`` publishes,
whose rows are objects over the same allowlist and must all carry the
same key set. Both come through the evidence boundary's own open path
and are never copied, indexed, or logged.
"""

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from contextsafe.contract_validation import (
    array_value,
    bounded_string,
    contract_error,
    exact_keys,
    object_value,
)
from contextsafe.importers.base import (
    ImportErrorCode,
    ImportResult,
    ImportWarningCode,
    import_error,
)
from contextsafe.importers.canonical_json import UNBOUND_SOURCE
from contextsafe.importers.lis_csv import CsvBounds, parse_csv
from contextsafe.models import (
    OBSERVATION_SCHEMA_VERSION,
    OBSERVATION_SET_SCHEMA_VERSION,
    Checkpoint,
    ConceptKind,
    EvidencePointer,
    MappingDescriptor,
    NameToUse,
    Observation,
    Pronouns,
    RecordedSexOrGender,
    SemanticValue,
    SyntheticCase,
    ValueStatus,
)
from contextsafe.preflight import RawSource, read_source, scan_source, scan_text
from contextsafe.validation import parse_observations

LIS_CSV_FORMAT = "lis-csv"
"""The ``--format`` name of the CSV importer."""

LIS_JSON_FORMAT = "lis-json"
"""The ``--format`` name of the JSON importer."""

LIS_EXPORT_SCHEMA_VERSION = "contextsafe.lis-export/0.1.0"
"""The ``schema_version`` the JSON export document must carry."""

LIS_CHECKPOINT = Checkpoint.LIS_RETURN
"""The only checkpoint an LIS export is evidence for."""

LABORATORY_CONTEXT = "laboratory"
"""The recording context every ``sex`` cell is typed with.

An LIS's sex field is the laboratory's own administrative record of the
value. It is not a government-identity context, and it is not a clinical
parameter; the context is fixed here so the observation can be mistaken for
neither.
"""

CASE_TOKEN_PATTERN = re.compile(r"^CSYN-CTP-[A-Z0-9]{3,16}$")
"""The shape of the case identifier every row must carry."""

SYNTHETIC_TOKEN_PATTERN = re.compile(r"^CSYN-[A-Z0-9][A-Z0-9_.:-]{0,95}$")
"""A name-to-use or pronoun cell that is a value rather than a presence state.

The same grammar the canonical envelope publishes for a synthetic value
code, so the two importers admit the same tokens.
"""

SYNTHETIC_IDENTIFIER_PATTERN = re.compile(
    r"^(?:ORDER-)?CSYN-[A-Z0-9][A-Z0-9_.:-]{0,95}$"
)
"""An order or specimen cell: an accession-shaped identifier, so synthetic only."""

RESULT_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9<>][A-Za-z0-9:/_.%<>-]{0,63}$")
"""A non-empty analyte, value, unit, range, or flag cell.

No whitespace, so a sentence cannot be written in a result cell, and
bounded, so nothing long can be either. Not interpreted: a later item
decides what a result cell means, and this pattern only keeps free text
out until then.
"""

FORMULA_PREFIXES = frozenset({"=", "+", "-", "@"})
"""Leading characters a spreadsheet treats as a formula. A cell with one rejects."""

_PRESENCE_STATES: Mapping[str, ValueStatus] = {
    ValueStatus.DECLINED.value: ValueStatus.DECLINED,
    ValueStatus.UNKNOWN.value: ValueStatus.UNKNOWN,
    ValueStatus.ABSENT.value: ValueStatus.ABSENT,
}
"""Cells that are presence states rather than values."""


@dataclass(frozen=True, slots=True)
class LisProfile:
    """The versioned column allowlist both LIS formats read.

    ``case_column`` binds every row to the case document. ``identity_columns``
    become observations, each under exactly the concept the mapping below
    names. ``result_columns`` are recognized and counted; the subset in
    ``identifier_columns`` must be synthetic when non-empty, and the rest
    must be bounded tokens. ``profile_reviewed`` cannot be ``True``: the
    field exists so a governed profile has a place to say so, and so this
    one cannot claim it.
    """

    version: str
    case_column: str
    identity_columns: tuple[str, ...]
    result_columns: tuple[str, ...]
    identifier_columns: tuple[str, ...]
    max_rows: int
    max_cell_length: int
    profile_reviewed: bool = False

    def __post_init__(self) -> None:
        if self.profile_reviewed:
            raise contract_error(
                "profile_review_not_available",
                "$.profile_reviewed",
                "no LIS profile has been reviewed; the flag cannot be set",
            )
        if not set(self.identifier_columns) <= set(self.result_columns):
            raise contract_error(
                "profile_columns_inconsistent",
                "$.identifier_columns",
                "identifier columns must be result columns",
            )

    @property
    def columns(self) -> tuple[str, ...]:
        """Every column the profile admits, in profile order."""

        return (self.case_column, *self.identity_columns, *self.result_columns)


LIS_PROFILE = LisProfile(
    version="0.1.0",
    case_column="patient_id",
    identity_columns=("name_to_use", "pronouns", "sex"),
    result_columns=("analyte", "value", "unit", "range", "flag", "order", "specimen"),
    identifier_columns=("order", "specimen"),
    max_rows=2000,
    max_cell_length=128,
)
"""Profile 0.1.0. Reference-only; ``profile_reviewed`` is ``False``.

Its version is recorded as ``mapping.mapping_version`` on every observation.
A change to the column set, to a cell grammar, to the fixed laboratory
context, or to the duplicate-collapsing rule is a change to this number.
"""

_IDENTITY_CONCEPTS: Mapping[str, ConceptKind] = {
    "name_to_use": ConceptKind.NAME_TO_USE,
    "pronouns": ConceptKind.PRONOUNS,
    "sex": ConceptKind.RECORDED_SEX_OR_GENDER,
}
"""Identity column to concept. ``sex`` is recorded sex or gender and nothing else.

Neither gender identity nor sex parameter for clinical use appears as a
target, and no column name reaches either; a source that carries a column
for one is a source with an unknown column.
"""

_IDENTITY_SUFFIXES: Mapping[str, str] = {
    "name_to_use": "NTU",
    "pronouns": "PRN",
    "sex": "RSG",
}


@dataclass(frozen=True, slots=True)
class LisTable:
    """One export as a header and rows of string cells, format forgotten."""

    columns: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]


def _header_columns(
    names: tuple[str, ...], path: str, locate: Callable[[int], str]
) -> None:
    """Hold a header to the allowlist before any cell is read.

    ``locate`` turns the position of an offending name into the path the
    rejection names: a CSV header has positions, a JSON row does not. The
    name itself is never written into the path.
    """

    admitted = LIS_PROFILE.columns
    for index, name in enumerate(names):
        if name not in admitted:
            raise import_error(
                ImportErrorCode.COLUMN_UNKNOWN,
                locate(index),
                "column is outside the profile allowlist",
            )
    if len(set(names)) != len(names):
        raise import_error(
            ImportErrorCode.COLUMN_DUPLICATE, path, "a column appears more than once"
        )
    if LIS_PROFILE.case_column not in names:
        raise import_error(
            ImportErrorCode.COLUMN_MISSING,
            path,
            "the case identifier column is required on every row",
        )
    if not any(name in LIS_PROFILE.identity_columns for name in names):
        raise import_error(
            ImportErrorCode.COLUMN_MISSING,
            path,
            "at least one identity column is required; a source with none "
            "carries no observation for this checkpoint",
        )


def _row_bounds(count: int, path: str) -> None:
    if count < 1:
        raise import_error(
            ImportErrorCode.BOUND_EXCEEDED, path, "at least one data row is required"
        )
    if count > LIS_PROFILE.max_rows:
        raise import_error(
            ImportErrorCode.BOUND_EXCEEDED, path, "row count exceeds the bound"
        )


def parse_lis_csv(text: str) -> LisTable:
    """Read a CSV export into a table, header first and rows bounded."""

    records = parse_csv(
        text,
        bounds=CsvBounds(
            max_records=LIS_PROFILE.max_rows + 1,
            max_fields=len(LIS_PROFILE.columns),
            max_field_length=LIS_PROFILE.max_cell_length,
        ),
    )
    _header_columns(records[0], "$.header", lambda index: f"$.header[{index}]")
    _row_bounds(len(records) - 1, "$.rows")
    return LisTable(columns=records[0], rows=records[1:])


def _row_object(value: object, path: str, columns: tuple[str, ...]) -> tuple[str, ...]:
    """Require one row to carry exactly ``columns`` and a string in each."""

    data = object_value(value, path)
    if data.keys() != set(columns):
        raise import_error(
            ImportErrorCode.COLUMN_MISSING,
            path,
            "every row must carry exactly the first row's key set, no more and "
            "no fewer",
        )
    cells: list[str] = []
    for column in columns:
        cell = data[column]
        if not isinstance(cell, str):
            raise import_error(
                ImportErrorCode.SOURCE_MALFORMED,
                f"{path}.{column}",
                "a cell must be a JSON string",
            )
        cells.append(cell)
    return tuple(cells)


def parse_lis_json(value: object) -> LisTable:
    """Read a JSON export document into a table with the published shape."""

    data = object_value(value, "$")
    exact_keys(data, frozenset({"schema_version", "rows"}), "$")
    if bounded_string(data["schema_version"], "$.schema_version") != (
        LIS_EXPORT_SCHEMA_VERSION
    ):
        raise contract_error(
            "unsupported_schema", "$.schema_version", "LIS export schema is unsupported"
        )
    rows = array_value(data["rows"], "$.rows")
    _row_bounds(len(rows), "$.rows")
    first = object_value(rows[0], "$.rows[0]")
    # The first row's keys are the header. Held to the allowlist before any
    # cell of any row is read, so a key that is free text is refused before
    # it could be interpolated anywhere; the rejection names the row only.
    _header_columns(tuple(first), "$.rows[0]", lambda _index: "$.rows[0]")
    columns = tuple(column for column in LIS_PROFILE.columns if column in first)
    return LisTable(
        columns=columns,
        rows=tuple(
            _row_object(row, f"$.rows[{index}]", columns)
            for index, row in enumerate(rows)
        ),
    )


def _presence_cell(cell: str, path: str) -> tuple[ValueStatus, str | None]:
    """Type a name or pronoun cell without guessing what an empty one means.

    ``declined``, ``unknown``, and ``absent`` are presence states and carry
    no value. An empty cell is none of those: the source did not say, and
    the importer does not say for it. ``specified`` without the value is
    ambiguous in the same way. A synthetic token is the value, verbatim.
    Anything else is free text or another vocabulary, and neither becomes a
    name or a pronoun.
    """

    if not cell:
        raise import_error(
            ImportErrorCode.VALUE_MISSING,
            path,
            "an empty identity cell is not typed; absence is not a value",
        )
    status = _PRESENCE_STATES.get(cell)
    if status is not None:
        return status, None
    if cell == ValueStatus.SPECIFIED.value:
        raise import_error(
            ImportErrorCode.VALUE_AMBIGUOUS,
            path,
            "a cell that says specified must carry the value itself",
        )
    if SYNTHETIC_TOKEN_PATTERN.fullmatch(cell) is None:
        raise import_error(
            ImportErrorCode.CONCEPT_NOT_CONVERTIBLE,
            path,
            "a name-to-use or pronoun cell is a presence state or a synthetic "
            "token; anything else is not converted",
        )
    return ValueStatus.SPECIFIED, cell


def _name_to_use(cell: str, path: str) -> SemanticValue:
    # ``use`` is fixed by the observation contract, which admits only
    # ``usual``; the export carries no name-use column and none is read.
    status, value = _presence_cell(cell, path)
    return NameToUse(status=status, value=value, use="usual")


def _pronouns(cell: str, path: str) -> SemanticValue:
    status, value = _presence_cell(cell, path)
    return Pronouns(status=status, value=value)


def _recorded_sex_or_gender(cell: str, path: str) -> SemanticValue:
    """Type a sex cell as recorded sex or gender in the laboratory context.

    The cell is carried verbatim; the observation contract, not this
    importer, decides whether it is a supported RSG value, so ``f`` is
    rejected there rather than read as ``F`` here.
    """

    if not cell:
        raise import_error(
            ImportErrorCode.VALUE_MISSING,
            path,
            "an empty identity cell is not typed; absence is not a value",
        )
    return RecordedSexOrGender(
        value=cell, context=LABORATORY_CONTEXT, source=UNBOUND_SOURCE
    )


_CONVERTERS: Mapping[str, Callable[[str, str], SemanticValue]] = {
    "name_to_use": _name_to_use,
    "pronouns": _pronouns,
    "sex": _recorded_sex_or_gender,
}


def _case_cell(cell: str, path: str, case: SyntheticCase) -> None:
    if CASE_TOKEN_PATTERN.fullmatch(cell) is None:
        raise import_error(
            ImportErrorCode.IDENTIFIER_NOT_SYNTHETIC,
            path,
            "the case identifier must be a synthetic case token",
        )
    if cell != case.synthetic_identifier.value:
        raise import_error(
            ImportErrorCode.CASE_MISMATCH,
            path,
            "the row's case identifier must match the case document",
        )


def _result_cell(cell: str, path: str, column: str) -> None:
    """Hold a result cell to its grammar without interpreting it."""

    if not cell:
        return
    if column in LIS_PROFILE.identifier_columns:
        if SYNTHETIC_IDENTIFIER_PATTERN.fullmatch(cell) is None:
            raise import_error(
                ImportErrorCode.IDENTIFIER_NOT_SYNTHETIC,
                path,
                "an order or specimen identifier must be synthetic",
            )
        return
    if RESULT_TOKEN_PATTERN.fullmatch(cell) is None:
        raise import_error(
            ImportErrorCode.CELL_FREE_TEXT,
            path,
            "a result cell must be a bounded token; free text is not accepted",
        )


def _check_cell(cell: str, path: str) -> None:
    """The checks every cell gets before its column is considered."""

    if len(cell) > LIS_PROFILE.max_cell_length:
        raise import_error(
            ImportErrorCode.BOUND_EXCEEDED, path, "cell length exceeds the bound"
        )
    if cell[:1] in FORMULA_PREFIXES:
        raise import_error(
            ImportErrorCode.FORMULA_CELL,
            path,
            "a cell may not begin with a character a spreadsheet would execute",
        )
    scan_text(cell, path)


@dataclass(frozen=True, slots=True)
class _Read:
    """What one pass over the rows established, before observations exist."""

    first_rows: dict[str, dict[str, int]]
    """Identity column to distinct cell to the first row carrying it."""

    unobserved_cell_count: int


def _read_rows(table: LisTable, case: SyntheticCase) -> _Read:
    first_rows: dict[str, dict[str, int]] = {
        column: {} for column in table.columns if column in _IDENTITY_CONCEPTS
    }
    unobserved = 0
    for row_index, row in enumerate(table.rows):
        for column, cell in zip(table.columns, row, strict=True):
            path = f"$.rows[{row_index}].{column}"
            _check_cell(cell, path)
            if column == LIS_PROFILE.case_column:
                _case_cell(cell, path, case)
            elif column in first_rows:
                _CONVERTERS[column](cell, path)
                first_rows[column].setdefault(cell, row_index)
            else:
                _result_cell(cell, path, column)
                unobserved += 1
    return _Read(first_rows=first_rows, unobserved_cell_count=unobserved)


def _observation(
    column: str,
    cell: str,
    row_index: int,
    *,
    case_id: str,
    source_sha256: str,
) -> Observation:
    concept = _IDENTITY_CONCEPTS[column]
    path = f"$.rows[{row_index}].{column}"
    return Observation(
        schema_version=OBSERVATION_SCHEMA_VERSION,
        observation_id=(f"OBS-{case_id}-L{row_index:04d}-{_IDENTITY_SUFFIXES[column]}"),
        case_id=case_id,
        checkpoint=LIS_CHECKPOINT,
        concept=concept,
        value=_CONVERTERS[column](cell, path),
        evidence=EvidencePointer(source_sha256=source_sha256, source_pointer=path),
        mapping=MappingDescriptor(
            source_concept=concept,
            target_concept=concept,
            mapping_version=LIS_PROFILE.version,
        ),
    )


def _require_lis_checkpoint(checkpoint: Checkpoint) -> None:
    if checkpoint is not LIS_CHECKPOINT:
        raise import_error(
            ImportErrorCode.CHECKPOINT_MISMATCH,
            "$.checkpoint",
            "an LIS export is evidence for the lis_return checkpoint only",
        )


def convert_table(
    table: LisTable,
    *,
    format_name: str,
    case: SyntheticCase,
    checkpoint: Checkpoint,
    source_sha256: str,
    source_byte_count: int,
) -> ImportResult:
    """Convert one table whole, or raise and produce nothing.

    Every cell is bounded, checked for a formula prefix, and boundary
    scanned; the case column is cross-checked against the case document;
    identity cells are typed; result cells are held to their grammars and
    counted. Then one observation is built per distinct value per identity
    column, and the document is re-validated by the observation contract so
    a value this module typed and the contract rejects (an unsupported RSG
    value) rejects the source with the contract's own code.
    """

    _require_lis_checkpoint(checkpoint)
    read = _read_rows(table, case)
    converted = tuple(
        _observation(
            column,
            cell,
            row_index,
            case_id=case.case_id,
            source_sha256=source_sha256,
        )
        for column in LIS_PROFILE.identity_columns
        if column in read.first_rows
        for cell, row_index in read.first_rows[column].items()
    )
    validated = parse_observations(
        {
            "observations": [item.to_dict() for item in converted],
            "schema_version": OBSERVATION_SET_SCHEMA_VERSION,
        }
    )
    warnings = [ImportWarningCode.MAPPING_PROFILE_NOT_BOUND]
    if any(column in LIS_PROFILE.result_columns for column in table.columns):
        warnings.append(ImportWarningCode.RESULT_COLUMNS_NOT_OBSERVED)
    return ImportResult(
        format_name=format_name,
        mapping_version=LIS_PROFILE.version,
        source_sha256=source_sha256,
        source_byte_count=source_byte_count,
        record_count=len(converted),
        observations=validated,
        warnings=tuple(warnings),
        unobserved_cell_count=read.unobserved_cell_count,
    )


def _decode(source: RawSource) -> str:
    try:
        return source.raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise contract_error("invalid_utf8", "$", "input must be UTF-8") from exc


class LisCsvImporter:
    """The registered importer for an LIS CSV export's identity columns."""

    @property
    def format_name(self) -> str:
        return LIS_CSV_FORMAT

    @property
    def mapping_version(self) -> str:
        return LIS_PROFILE.version

    def convert(
        self, source: Path, *, case: SyntheticCase, checkpoint: Checkpoint
    ) -> ImportResult:
        """Read ``source`` through the boundary's open path, then convert it."""

        _require_lis_checkpoint(checkpoint)
        raw = read_source(source)
        return convert_table(
            parse_lis_csv(_decode(raw)),
            format_name=LIS_CSV_FORMAT,
            case=case,
            checkpoint=checkpoint,
            source_sha256=raw.raw_sha256,
            source_byte_count=len(raw.raw),
        )


class LisJsonImporter:
    """The registered importer for an LIS JSON export's identity columns."""

    @property
    def format_name(self) -> str:
        return LIS_JSON_FORMAT

    @property
    def mapping_version(self) -> str:
        return LIS_PROFILE.version

    def convert(
        self, source: Path, *, case: SyntheticCase, checkpoint: Checkpoint
    ) -> ImportResult:
        """Scan ``source`` through the evidence boundary, then convert it."""

        _require_lis_checkpoint(checkpoint)
        scanned = scan_source(source)
        return convert_table(
            parse_lis_json(scanned.value),
            format_name=LIS_JSON_FORMAT,
            case=case,
            checkpoint=checkpoint,
            source_sha256=scanned.raw_sha256,
            source_byte_count=scanned.raw_byte_count,
        )


LIS_CSV_IMPORTER = LisCsvImporter()
LIS_JSON_IMPORTER = LisJsonImporter()
