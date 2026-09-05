"""The Windows story in the documents, held against the code that decides it.

`docs/10-OPERATIONS-SRE.md` section 3.1 exists so an operator learns which
commands refuse on a platform without `O_NOFOLLOW` or `dir_fd` before running
one, and which ones run there with a capability missing instead. Both halves
are hand-typed prose over facts that live in `src/contextsafe`, so both can go
out of date the same way the supported-platform list did.

These tests derive the facts and require the prose to name them: every module
that folds an optional platform flag into an open without ever refusing when it
is absent, every capability flag `contextsafe diagnostics` emits, and the
refusal code each refusing command actually carries. Nothing here reads or
changes behaviour; a failure here is a document to correct.
"""

from __future__ import annotations

import re
from pathlib import Path

from contextsafe.diagnostics import build_diagnostics

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "contextsafe"
OPERATIONS = ROOT / "docs" / "10-OPERATIONS-SRE.md"
BACKLOG = ROOT / "docs" / "13-BACKLOG.md"

_OPTIONAL_NOFOLLOW = re.compile(
    r'_NOFOLLOW = (?:getattr\(os, "O_NOFOLLOW", 0\)|_optional_flag\("O_NOFOLLOW"\))'
)
"""A module that takes zero for `O_NOFOLLOW` where the platform lacks it."""

_REFUSES_WITHOUT_NOFOLLOW = re.compile(r"_NOFOLLOW [!=]= 0")
"""The guard that turns that absence into a refusal rather than a weaker open."""

_OWNER_PERMISSION_SWITCH = re.compile(r'_[A-Z_]+ = os\.name == "posix"')
"""A module-level switch that turns an owner-only refusal off elsewhere."""

_REFUSING_ROW = re.compile(
    r"^\| (?P<commands>[^|]*) \| \*\*refuses\*\* \| (?P<detail>[^|]*)\|\s*$",
    re.MULTILINE,
)

_NOTE = re.compile(
    r"^Implementation note \([0-9]{4}-[0-9]{2}-[0-9]{2}, [^)]*\):", re.MULTILINE
)


def _section_3_1() -> str:
    """The section that makes the Windows claim, and nothing around it."""

    text = OPERATIONS.read_text(encoding="utf-8")
    start = text.index("### 3.1 What runs on Windows, and what refuses")
    return text[start : text.index("\n## ", start)]


def _package_sources() -> list[Path]:
    return sorted(PACKAGE.rglob("*.py"))


def _degrading_modules() -> set[str]:
    """Modules that open with a platform flag they may not have, and do not refuse."""

    degrading: set[str] = set()
    for path in _package_sources():
        source = path.read_text(encoding="utf-8")
        optional = _OPTIONAL_NOFOLLOW.search(source) is not None
        if optional and _REFUSES_WITHOUT_NOFOLLOW.search(source) is None:
            degrading.add(path.relative_to(ROOT).as_posix())
        if _OWNER_PERMISSION_SWITCH.search(source) is not None:
            degrading.add(path.relative_to(ROOT).as_posix())
    return degrading


def test_the_degrading_modules_are_derivable_at_all() -> None:
    """A derivation that finds nothing would pass for the wrong reason."""

    modules = _degrading_modules()
    assert modules, "no module folds an optional platform flag into an open"
    assert "src/contextsafe/jsonio.py" not in modules
    assert "src/contextsafe/preflight.py" not in modules


def test_operations_names_every_module_that_degrades_rather_than_refuses() -> None:
    """The section that lists the fail-open surface must list all of it.

    `src/contextsafe/eventlog.py` was named and
    `src/contextsafe/evidence_store.py` was not, although the store drops
    `O_NOFOLLOW` the same way and skips its owner-only refusals off POSIX, and
    `cleanup` and `diagnostics` reach it on the platform the table marks as
    running them.
    """

    section = _section_3_1()
    for module in sorted(_degrading_modules()):
        assert module in section, f"section 3.1 does not name {module}"


def test_operations_makes_no_the_one_place_claim() -> None:
    """An absolute over a set this test derives is the claim that decayed."""

    assert "the one place" not in _section_3_1()


def test_the_diagnostics_row_names_every_capability_flag_emitted() -> None:
    """An operator is told to read these flags, so all of them are named."""

    section = _section_3_1()
    row = next(
        line
        for line in section.splitlines()
        if line.startswith("| `contextsafe diagnostics` |")
    )
    capabilities = build_diagnostics()["capabilities"]
    assert isinstance(capabilities, dict)
    for flag in sorted(capabilities):
        assert f"`{flag}`" in row, f"the diagnostics row does not name {flag}"


def _refusal_codes() -> dict[str, str]:
    """Each refusing command in the matrix, with the code its row states.

    A row that says "same code" rather than repeating one inherits the code
    from the row above, which is how the table is written.
    """

    codes: dict[str, str] = {}
    previous = ""
    for row in _REFUSING_ROW.finditer(_section_3_1()):
        stated = re.findall(r"`([a-z_]+)`", row.group("detail"))
        code = stated[0] if stated else previous
        assert code, "the first refusing row states no error code"
        previous = code
        for command in re.findall(r"`contextsafe ([a-z ]+)`", row.group("commands")):
            codes[command.strip()] = code
    return codes


def test_the_refusal_matrix_states_a_code_for_every_refusing_command() -> None:
    """The derivation below is only as good as what it reads."""

    codes = _refusal_codes()
    assert codes["evidence preflight"] == "input_path_unsupported"
    assert codes["pack validate"] == "component_path_escape"
    assert codes["plan validate"] == "component_path_escape"


def _notes() -> list[str]:
    """Each dated implementation note in the backlog, header through body."""

    backlog = BACKLOG.read_text(encoding="utf-8")
    starts = [match.start() for match in _NOTE.finditer(backlog)]
    assert starts, "the backlog carries no implementation note"
    bounds = [*starts[1:], len(backlog)]
    return [backlog[start:end] for start, end in zip(starts, bounds, strict=True)]


def test_no_backlog_note_states_a_refusal_code_the_matrix_contradicts() -> None:
    """A note may be historical; it may not leave a wrong code standing.

    The 2026-08-15 B-021 note said `pack validate` and `plan validate` fail
    closed with `input_path_unsupported`. They report `component_path_escape`.
    A dated correction inside the note satisfies this without rewriting the
    paragraph, which is how this repository corrects a dated record.
    """

    codes = _refusal_codes()
    vocabulary = set(codes.values())
    for note in _notes():
        if not any(f"`{code}`" in note for code in vocabulary):
            continue
        for command, code in sorted(codes.items()):
            if f"`{command}`" not in note and f"`contextsafe {command}`" not in note:
                continue
            assert f"`{code}`" in note, (
                f"a backlog note names `{command}` and a refusal code, but not "
                f"`{code}`, which is the code that command carries"
            )
