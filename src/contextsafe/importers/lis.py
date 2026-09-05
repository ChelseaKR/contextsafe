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

What it reads beside the identity. A source that carries the whole result
column set (``analyte``, ``value``, ``unit``, ``range``, ``flag``,
``order``, ``specimen``) also produces one laboratory result observation per
row (:mod:`contextsafe.laboratory`), pointed at the row it was read from.
Those are a separate observation kind and not a sixth concept: they carry
their own document, they reach no receipt, and no command writes them, which
is what the closed warning ``result_observations_not_written`` says. A row that
does not carry the whole result column set, or that leaves an analyte, value,
unit, order, or specimen cell empty, produces no result: its result cells stay
recognized, bounded, scanned, and counted, under the closed warning
``result_columns_not_observed`` and a count of the cells the conversion did not
claim -- never a silently dropped column, and never a result with an invented
cell in it. A source whose rows differ carries both warnings and a count that
says how many cells the results left behind. A column outside the allowlist rejects the whole source, with the
column's position and never its name.

What a result cell is not interpreted as. A range cell is typed only in the
one invented dialect :mod:`contextsafe.laboratory` publishes
(``ge2.500:le7.500:fixture-unit-alpha``), and a flag cell only in its
invented flag vocabulary. A partner export's own range or flag dialect is
not guessed at and not normalized to the closest one it resembles (A-033):
the cell is carried as ``not_typed``, which is a different fact from an
empty cell, and every predicate that would have read it is indeterminate
rather than passing. Nothing here is a clinical reference range, and no
laboratory reviewer has approved any of it.

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
from contextsafe.laboratory import (
    RESULT_SCHEMA_VERSION,
    LaboratoryResult,
    parse_result_set,
    result_set_document,
    type_abnormal_flag_cell,
    type_reference_interval_cell,
)
from contextsafe.laboratory import (
    RESULT_TOKEN_PATTERN as LABORATORY_TOKEN_PATTERN,
)
from contextsafe.laboratory import (
    SYNTHETIC_IDENTIFIER_PATTERN as LABORATORY_IDENTIFIER_PATTERN,
)
from contextsafe.mapping_profile import SourceToken
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

SYNTHETIC_IDENTIFIER_PATTERN = LABORATORY_IDENTIFIER_PATTERN
"""An order or specimen cell: an accession-shaped identifier, so synthetic only.

The laboratory result family's own grammar, not a second copy of it, so a
cell this reader admits is a cell the result contract admits and the
re-validation below can never disagree with the reader about an identifier.
"""

RESULT_TOKEN_PATTERN = LABORATORY_TOKEN_PATTERN
"""A non-empty analyte, value, unit, range, or flag cell.

No whitespace, so a sentence cannot be written in a result cell, and
bounded, so nothing long can be either. Not interpreted here: what a range
or a flag cell means is decided by :mod:`contextsafe.laboratory`, whose
grammar this is, and a cell it cannot type is carried as untyped rather
than guessed at.
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
    version="0.2.0",
    case_column="patient_id",
    identity_columns=("name_to_use", "pronouns", "sex"),
    result_columns=("analyte", "value", "unit", "range", "flag", "order", "specimen"),
    identifier_columns=("order", "specimen"),
    max_rows=2000,
    max_cell_length=128,
)
"""Profile 0.2.0. Reference-only; ``profile_reviewed`` is ``False``.

Its version is recorded as ``mapping.mapping_version`` on every observation
and as ``mapping_version`` on every laboratory result. A change to the
column set, to a cell grammar, to the fixed laboratory context, to the
duplicate-collapsing rule, or to what the profile emits is a change to this
number. 0.2.0 is 0.1.0 plus the laboratory result observations: the identity
observations it produces are unchanged in value and shape, and only the
version they record moved, so two behaviours of one profile can never share
a run identity.
"""

RESULT_REQUIRED_COLUMNS: tuple[str, ...] = (
    "analyte",
    "value",
    "unit",
    "order",
    "specimen",
)
"""Result columns whose cell a row must carry to become a result.

``range`` and ``flag`` may be empty -- a blank interval is the published
failure pattern (A-029) and has to be representable. The five here are what
identifies a result at all: a row that leaves one of them empty carries no
result this profile can read, and nothing is invented to fill it. Its result
cells are counted as unobserved instead, under the warning that says so.
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

LIS_CARRIERS: Mapping[str, frozenset[ConceptKind]] = {
    column: frozenset({concept}) for column, concept in _IDENTITY_CONCEPTS.items()
}
"""What a mapping profile for either LIS format may name as a carrier: a column.

Each identity column reads as exactly its own concept, so a profile row
cannot read ``sex`` as gender identity or as sex parameter for clinical use.
"""


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
    results: tuple[LaboratoryResult, ...] = ()


def emits_results(table: LisTable) -> bool:
    """True when the table carries every result column, so a row is a result."""

    return set(LIS_PROFILE.result_columns) <= set(table.columns)


def _carries_a_result(cells: Mapping[str, str]) -> bool:
    """True when the row names an analyte, a value, a unit, an order and a specimen.

    A row that leaves one of those empty is not a result with a hole in it:
    it is a row this profile cannot read as a result at all. Nothing is
    invented for the empty cell and nothing is dropped quietly -- the row's
    result cells are counted as unobserved and the source carries the closed
    warning that says so.
    """

    return all(cells[column] for column in RESULT_REQUIRED_COLUMNS)


def _result(
    cells: Mapping[str, str], row_index: int, *, case_id: str, source_sha256: str
) -> LaboratoryResult:
    """Build one laboratory result from one row.

    The evidence pointer is the row, not a cell: a result is read from every
    result column of one row at once, and a cell word would widen the closed
    structural-pointer vocabulary the receipt contract copies.
    """

    interval_status, interval = type_reference_interval_cell(cells["range"])
    flag_status, flag = type_abnormal_flag_cell(cells["flag"])
    return LaboratoryResult(
        schema_version=RESULT_SCHEMA_VERSION,
        result_id=f"RES-{case_id}-L{row_index:04d}",
        case_id=case_id,
        checkpoint=LIS_CHECKPOINT,
        analyte_code=cells["analyte"],
        value=cells["value"],
        unit=cells["unit"],
        order_id=cells["order"],
        specimen_id=cells["specimen"],
        interval_status=interval_status,
        reference_interval=interval,
        flag_status=flag_status,
        abnormal_flag=flag,
        evidence=EvidencePointer(
            source_sha256=source_sha256, source_pointer=f"$.rows[{row_index}]"
        ),
        mapping_version=LIS_PROFILE.version,
    )


def _read_rows(table: LisTable, case: SyntheticCase, source_sha256: str) -> _Read:
    first_rows: dict[str, dict[str, int]] = {
        column: {} for column in table.columns if column in _IDENTITY_CONCEPTS
    }
    complete = emits_results(table)
    unobserved = 0
    results: list[LaboratoryResult] = []
    for row_index, row in enumerate(table.rows):
        # Every cell is checked from the header/row pairs, never from a
        # mapping of them: a mapping keyed by column name would collapse a
        # repeated column and leave the collapsed cell unchecked, uncounted,
        # and unscanned. A repeated column is refused before this runs, and
        # this loop does not depend on that refusal.
        cells = dict(zip(table.columns, row, strict=True))
        result_cells = 0
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
                result_cells += 1
        if complete and _carries_a_result(cells):
            results.append(
                _result(
                    cells,
                    row_index,
                    case_id=case.case_id,
                    source_sha256=source_sha256,
                )
            )
        else:
            unobserved += result_cells
    return _Read(
        first_rows=first_rows,
        unobserved_cell_count=unobserved,
        results=tuple(results),
    )


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


def _require_distinct_columns(table: LisTable) -> None:
    """Refuse a table whose header repeats a column, whoever built it.

    The file readers reject a repeated header before a cell is read, and
    ``convert_table`` is an entry point of its own: a caller that hands it a
    table directly gets the same refusal, rather than a row whose repeated
    column collapses into one cell and leaves the other unchecked.
    """

    if len(set(table.columns)) != len(table.columns):
        raise import_error(
            ImportErrorCode.COLUMN_DUPLICATE,
            "$.header",
            "a column appears more than once",
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

    A header that repeats a column is refused here as well as at each
    reader, so no cell of a repeated column can go unchecked. Every cell is
    bounded, checked for a formula prefix, and boundary scanned; the case
    column is cross-checked against the case document; identity cells are
    typed; result cells are held to their grammars and either counted or
    built into a laboratory result. Then one observation
    is built per distinct value per identity column, and both documents are
    re-validated by their own contracts, so a value this module typed and a
    contract rejects (an unsupported RSG value, a bound outside the decimal
    grammar) rejects the source with that contract's own code.
    """

    _require_lis_checkpoint(checkpoint)
    _require_distinct_columns(table)
    read = _read_rows(table, case, source_sha256)
    distinct = tuple(
        (column, cell, row_index)
        for column in LIS_PROFILE.identity_columns
        if column in read.first_rows
        for cell, row_index in read.first_rows[column].items()
    )
    converted = tuple(
        _observation(
            column,
            cell,
            row_index,
            case_id=case.case_id,
            source_sha256=source_sha256,
        )
        for column, cell, row_index in distinct
    )
    tokens = tuple(
        SourceToken(concept=_IDENTITY_CONCEPTS[column], carrier=column, token=cell)
        for column, cell, _row_index in distinct
    )
    validated = parse_observations(
        {
            "observations": [item.to_dict() for item in converted],
            "schema_version": OBSERVATION_SET_SCHEMA_VERSION,
        }
    )
    results = (
        parse_result_set(result_set_document(read.results)) if read.results else ()
    )
    warnings = [ImportWarningCode.MAPPING_PROFILE_NOT_BOUND]
    if results:
        warnings.append(ImportWarningCode.RESULT_OBSERVATIONS_NOT_WRITTEN)
    if read.unobserved_cell_count:
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
        results=results,
        source_tokens=tokens,
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

    @property
    def carriers(self) -> Mapping[str, frozenset[ConceptKind]]:
        return LIS_CARRIERS

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

    @property
    def carriers(self) -> Mapping[str, frozenset[ConceptKind]]:
        return LIS_CARRIERS

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
