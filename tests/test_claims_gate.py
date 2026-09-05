"""The claims gate must fail on a drifted document, and differently on no document.

Every case here starts from a copy of the real repository's documents, so the
scaffold cannot drift away from what the gate reads in `make verify`, and then
breaks exactly one thing. The three-state contract is the load-bearing part, the
same one `tests/test_hygiene_gate.py` pins: a drifted claim is a finding, a
matching tree is a pass, and a gate that could not examine anything is exit 2 and
never a pass.

The other load-bearing property is that every check fails in *both* directions.
A gate that only catches a wrong number goes quiet the moment somebody deletes
the sentence carrying it, which is the failure mode the whole file exists to
prevent, so each check has a "the document stopped saying it" case as well as a
"the document says the wrong thing" one.
"""

from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
GATE_PATH = REPO_ROOT / "tools" / "claims_gate.py"

# Copied verbatim; the gate reads their prose.
DOCUMENTS = (
    "Makefile",
    "README.md",
    "CONTRIBUTING.md",
    "DEFINITION_OF_DONE.md",
    "schemas/README.md",
    "docs/PUBLICATION-READINESS.md",
    "docs/13-BACKLOG.md",
    "tools/a11y_gate.py",
)

# Reproduced by name only; the gate counts and names them, never reads them.
BY_NAME = (
    ("docs/adr", ".md"),
    ("schemas", ".json"),
    ("src/contextsafe/locales", ".json"),
)


def _load_gate() -> ModuleType:
    spec = importlib.util.spec_from_file_location("claims_gate", GATE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


gate = _load_gate()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A copy of the real documents, plus name-only stand-ins for what is counted."""

    for name in DOCUMENTS:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO_ROOT / name, target)
    for directory, suffix in BY_NAME:
        target = tmp_path / directory
        target.mkdir(parents=True, exist_ok=True)
        for path in (REPO_ROOT / directory).glob(f"*{suffix}"):
            (target / path.name).write_text("{}\n", encoding="utf-8")
    return tmp_path


def _edit(root: Path, name: str, old: str, new: str) -> None:
    """Break exactly one claim, and prove the break landed."""

    path = root / name
    text = path.read_text(encoding="utf-8")
    assert old in text, f"{name} no longer contains {old!r}; the test is stale"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def _checks(findings: list[object]) -> set[str]:
    return {f.check for f in findings}  # type: ignore[attr-defined]


# --- the repository as it stands --------------------------------------------


def test_the_real_repository_is_clean() -> None:
    """The documents in this checkout match what the repository derives."""

    assert gate.run_gate(REPO_ROOT) == []


def test_the_scaffold_reproduces_that(repo: Path) -> None:
    """A test that started dirty would prove nothing about the breaks below."""

    assert gate.run_gate(repo) == []


# --- verify-stages ----------------------------------------------------------


def test_a_stage_added_to_verify_and_left_undocumented_is_a_finding(repo: Path) -> None:
    _edit(repo, "Makefile", "publication-sweep i18n", "publication-sweep newgate i18n")
    findings = gate.run_gate(repo)
    assert _checks(findings) == {"verify-stages"}
    assert {f.where for f in findings} == {"README.md", "CONTRIBUTING.md"}
    assert all("newgate" in f.detail for f in findings)


def test_a_documented_stage_verify_does_not_run_is_a_finding(repo: Path) -> None:
    _edit(
        repo,
        "README.md",
        "publication-sweep i18n",
        "publication-sweep mystery i18n",
    )
    findings = gate.run_gate(repo)
    assert [f.where for f in findings] == ["README.md"]
    assert "'mystery', which is not here" in findings[0].detail


def test_a_quickstart_that_stops_listing_the_stages_is_a_finding(repo: Path) -> None:
    """Deleting the claim must not be a way to satisfy the check."""

    _edit(
        repo,
        "README.md",
        "make verify                       # sync",
        "make verify\nmake nothing # sync",
    )
    findings = [f for f in gate.run_gate(repo) if f.check == "verify-stages"]
    assert any("no longer names the stages" in f.detail for f in findings)


def test_a_contributing_table_with_no_commands_is_a_finding(repo: Path) -> None:
    text = (repo / "CONTRIBUTING.md").read_text(encoding="utf-8")
    (repo / "CONTRIBUTING.md").write_text(
        text.replace("`make ", "`run "), encoding="utf-8"
    )
    findings = [f for f in gate.run_gate(repo) if f.where == "CONTRIBUTING.md"]
    assert any("no `make <target>` command column" in f.detail for f in findings)


def test_the_gates_outside_verify_are_documented_and_not_findings(repo: Path) -> None:
    """Both out-of-`verify` gates are tabled in the same file and excluded.

    They used to be excluded by a literal set inside the gate. `make mutants`
    then moved out of `verify` and the literal did not follow, so the gate read
    a correctly documented row as an undocumented stage. The exclusion is now
    read from the sentence the document already writes.
    """

    contributing = (repo / "CONTRIBUTING.md").read_text(encoding="utf-8")
    assert "`make secret-scan`" in contributing
    assert "`make mutants`" in contributing
    assert gate.run_gate(repo) == []


def test_losing_the_divider_between_the_tables_is_a_finding(repo: Path) -> None:
    """Without it every row reads as a `verify` stage, so it is not optional."""

    _edit(repo, "CONTRIBUTING.md", "Two gates sit outside", "These gates are outside")
    findings = [f for f in gate.run_gate(repo) if f.check == "verify-stages"]
    assert any("divides the gate table" in f.detail for f in findings)


def test_a_gate_verify_runs_tabled_as_outside_it_is_a_finding(repo: Path) -> None:
    _edit(repo, "CONTRIBUTING.md", "| `make secret-scan` |", "| `make hygiene` |")
    findings = gate.run_gate(repo)
    assert [f.check for f in findings] == ["verify-stages"]
    assert "`make hygiene` as sitting outside" in findings[0].detail


def test_a_documented_gate_the_makefile_has_no_target_for_is_a_finding(
    repo: Path,
) -> None:
    _edit(repo, "CONTRIBUTING.md", "| `make secret-scan` |", "| `make ghost` |")
    findings = gate.run_gate(repo)
    assert [f.check for f in findings] == ["verify-stages"]
    assert "`make ghost`, which the Makefile has no target for" in findings[0].detail


def test_a_count_that_does_not_match_the_second_table_is_a_finding(repo: Path) -> None:
    """The sentence states a number, so the number is a claim like any other."""

    _edit(repo, "CONTRIBUTING.md", "Two gates sit outside", "Three gates sit outside")
    findings = gate.run_gate(repo)
    assert [f.check for f in findings] == ["verify-stages"]
    assert "says three gate(s) sit outside `make verify` and then tables 2" in (
        findings[0].detail
    )


# --- adr-index --------------------------------------------------------------


def test_an_unlisted_adr_is_a_finding(repo: Path) -> None:
    (repo / "docs" / "adr" / "0007-a-later-decision.md").write_text(
        "{}\n", encoding="utf-8"
    )
    findings = gate.run_gate(repo)
    assert _checks(findings) == {"adr-index"}
    assert "0007-a-later-decision.md" in findings[0].detail


def test_an_index_entry_with_no_adr_behind_it_is_a_finding(repo: Path) -> None:
    (
        repo / "docs" / "adr" / "0006-provenance-token-grammar-and-boundary-scan.md"
    ).unlink()
    findings = gate.run_gate(repo)
    assert _checks(findings) == {"adr-index"}
    assert "which is not here" in findings[0].detail


def test_a_readme_with_no_adr_links_is_a_finding(repo: Path) -> None:
    text = (repo / "README.md").read_text(encoding="utf-8")
    (repo / "README.md").write_text(text.replace("docs/adr/0", "elsewhere/0"), "utf-8")
    findings = [f for f in gate.run_gate(repo) if f.check == "adr-index"]
    assert findings and "no ADR link found" in findings[0].detail


def test_an_empty_adr_directory_cannot_be_examined(repo: Path) -> None:
    for path in (repo / "docs" / "adr").iterdir():
        path.unlink()
    with pytest.raises(gate.GateUnavailable, match="no ADR"):
        gate.run_gate(repo)


def test_a_missing_adr_directory_cannot_be_examined(repo: Path) -> None:
    shutil.rmtree(repo / "docs" / "adr")
    with pytest.raises(gate.GateUnavailable, match="docs/adr"):
        gate.run_gate(repo)


# --- coverage-floors --------------------------------------------------------


def test_a_raised_floor_the_documents_do_not_carry_is_a_finding(repo: Path) -> None:
    """Raising the floor is welcome; leaving three documents quoting the old one is not."""

    _edit(repo, "Makefile", "--cov-fail-under=90", "--cov-fail-under=93")
    findings = gate.run_gate(repo)
    assert _checks(findings) == {"coverage-floors"}
    assert {f.where for f in findings} == {
        "README.md",
        "CONTRIBUTING.md",
        "DEFINITION_OF_DONE.md",
    }


def test_a_document_that_stops_quoting_the_floor_is_a_finding(repo: Path) -> None:
    _edit(
        repo,
        "DEFINITION_OF_DONE.md",
        "at least 90% overall branch coverage",
        "high overall branch coverage",
    )
    findings = gate.run_gate(repo)
    assert [f.where for f in findings] == ["DEFINITION_OF_DONE.md"]


def test_a_makefile_with_one_floor_cannot_be_examined(repo: Path) -> None:
    _edit(repo, "Makefile", "--cov-fail-under=90", "")
    with pytest.raises(gate.GateUnavailable, match="two coverage floors"):
        gate.run_gate(repo)


# --- standard-not-applicable ------------------------------------------------


def test_a_standard_declared_not_applicable_while_verify_gates_it(repo: Path) -> None:
    """The defect this gate was written for, reproduced from the table it sat in."""

    _edit(
        repo,
        "README.md",
        "| Accessibility | Applies",
        "| Accessibility | N/A - offline CLI/library with no human-facing HTML",
    )
    findings = [f for f in gate.run_gate(repo) if f.check == "standard-not-applicable"]
    assert findings and "runs `a11y`" in findings[0].detail


def test_a_standards_table_missing_a_gated_row_is_a_finding(repo: Path) -> None:
    _edit(repo, "README.md", "| Internationalization | Applies", "| I18N | Applies")
    findings = [f for f in gate.run_gate(repo) if f.check == "standard-not-applicable"]
    assert findings and "no 'Internationalization' row" in findings[0].detail


def test_a_standard_no_verify_stage_gates_is_left_alone(repo: Path) -> None:
    """`AI Evaluation` is N/A and nothing in `verify` contradicts it."""

    rows = gate.standards_rows((repo / "README.md").read_text(encoding="utf-8"))
    assert rows["AI Evaluation"].startswith("N/A")
    assert gate.run_gate(repo) == []


def test_dropping_the_gate_drops_the_rule_rather_than_asserting_it(repo: Path) -> None:
    """The Makefile decides. A standard `verify` stopped gating is not this check's call."""

    _edit(repo, "Makefile", "i18n a11y claims", "claims")
    findings = [f for f in gate.run_gate(repo) if f.check == "standard-not-applicable"]
    assert findings == []


# --- retired-phrase ---------------------------------------------------------


def test_the_frozen_wording_coming_back_is_a_finding(repo: Path) -> None:
    _edit(
        repo,
        "README.md",
        "installs from the locked lockfile",
        "uses the frozen lockfile",
    )
    findings = [f for f in gate.run_gate(repo) if f.check == "retired-phrase"]
    assert findings and "frozen lockfile" in findings[0].detail


def test_the_rule_lapses_if_the_makefile_goes_back_to_frozen(repo: Path) -> None:
    """A retired phrase is retired because of what the code does, not by decree."""

    _edit(repo, "Makefile", "uv sync --locked", "uv sync --frozen")
    _edit(
        repo,
        "README.md",
        "installs from the locked lockfile",
        "uses the frozen lockfile",
    )
    findings = [f for f in gate.run_gate(repo) if f.check == "retired-phrase"]
    assert findings == []


# --- schema-contracts -------------------------------------------------------


def _contract_count(repo: Path) -> int:
    """The count is a fact about the tree, so the tests read it from the tree.

    Two of these tests once said "twelve" and "14" outright, which was true of
    eleven published contracts plus the ones they add, and became false the
    day a twelfth contract was published.
    """

    return len(list((repo / "schemas").glob("*.schema.json")))


def test_a_new_contract_missing_from_the_schema_readme_is_a_finding(repo: Path) -> None:
    """The expected count is derived from the tree, so this test does not
    silently pin the number of contracts the repository happens to hold."""

    (repo / "schemas" / "contextsafe-later-v1.schema.json").write_text("{}\n", "utf-8")
    count = _contract_count(repo)
    stated = gate.NUMBER_WORDS.get(count, str(count))
    findings = gate.run_gate(repo)
    assert _checks(findings) == {"schema-contracts"}
    assert any(f"{stated} contracts" in f.detail for f in findings)
    assert any("contextsafe-later-v1.schema.json" in f.detail for f in findings)


def test_a_count_beyond_the_number_words_is_reported_in_digits(repo: Path) -> None:
    """Past the table the gate says the digits, and says them either way.

    Two things are pinned here: a stated count that has gone wrong is
    reported against the tree's real count, and a document that stopped
    stating a count at all is reported too, so dropping the sentence is not
    a way to pass.
    """

    beyond = max(gate.NUMBER_WORDS) + 1 - _contract_count(repo)
    assert beyond >= 1, "the tree already exceeds the number-word table"
    for index in range(beyond):
        (repo / "schemas" / f"contextsafe-extra{index}-v1.schema.json").write_text(
            "{}\n", encoding="utf-8"
        )
    count = _contract_count(repo)
    assert count not in gate.NUMBER_WORDS
    findings = [f for f in gate.run_gate(repo) if "contracts'" in f.detail]
    assert findings and f"'{count} contracts'" in findings[0].detail

    (repo / "schemas" / "README.md").write_text("no count stated\n", encoding="utf-8")
    findings = [f for f in gate.run_gate(repo) if "contracts'" in f.detail]
    assert findings and f"'{count} contracts'" in findings[0].detail


def test_an_empty_schemas_directory_cannot_be_examined(repo: Path) -> None:
    for path in (repo / "schemas").glob("*.json"):
        path.unlink()
    with pytest.raises(gate.GateUnavailable, match="no contract"):
        gate.run_gate(repo)


def test_a_missing_schemas_directory_cannot_be_examined(repo: Path) -> None:
    shutil.rmtree(repo / "schemas")
    with pytest.raises(gate.GateUnavailable, match="schemas is not a directory"):
        gate.run_gate(repo)


# --- a11y-locale-coverage ---------------------------------------------------


def test_a_locale_that_ships_without_an_accessibility_run_is_a_finding(
    repo: Path,
) -> None:
    """The hole this check exists for: i18n discovers locales, a11y does not."""

    (repo / "src" / "contextsafe" / "locales" / "fr-FR.json").write_text(
        "{}\n", "utf-8"
    )
    findings = gate.run_gate(repo)
    assert _checks(findings) == {"a11y-locale-coverage"}
    assert "does not state 'fr-FR'" in findings[0].detail


def test_an_audited_locale_that_does_not_ship_is_a_finding(repo: Path) -> None:
    (repo / "src" / "contextsafe" / "locales" / "es-US.json").unlink()
    findings = gate.run_gate(repo)
    assert _checks(findings) == {"a11y-locale-coverage"}
    assert "'es-US', which is not here" in findings[0].detail


def test_an_a11y_gate_with_no_declared_default_cannot_be_examined(repo: Path) -> None:
    _edit(repo, "tools/a11y_gate.py", "DEFAULT_LOCALES: tuple", "OTHER_NAME: tuple")
    with pytest.raises(gate.GateUnavailable, match="DEFAULT_LOCALES"):
        gate.run_gate(repo)


def test_no_shipped_catalog_cannot_be_examined(repo: Path) -> None:
    shutil.rmtree(repo / "src" / "contextsafe" / "locales")
    with pytest.raises(gate.GateUnavailable, match="locales is not a directory"):
        gate.run_gate(repo)


def test_an_empty_catalog_directory_cannot_be_examined(repo: Path) -> None:
    for path in (repo / "src" / "contextsafe" / "locales").iterdir():
        path.unlink()
    with pytest.raises(gate.GateUnavailable, match="no locale catalog"):
        gate.run_gate(repo)


# --- required-note ----------------------------------------------------------


def test_removing_the_dated_correction_is_a_finding(repo: Path) -> None:
    _edit(repo, "docs/PUBLICATION-READINESS.md", "Update, 2026-08-29", "Note")
    findings = gate.run_gate(repo)
    assert _checks(findings) == {"required-note"}


# --- iteration-status -------------------------------------------------------


def test_a_status_line_behind_the_iterations_described_is_a_finding(repo: Path) -> None:
    _edit(repo, "README.md", "and\niteration-6 file readers", "and\nfile readers")
    findings = gate.run_gate(repo)
    assert _checks(findings) == {"iteration-status"}
    assert "stops short of 'iteration-6'" in findings[0].detail


def test_a_readme_describing_no_iteration_cannot_be_examined(repo: Path) -> None:
    text = (repo / "README.md").read_text(encoding="utf-8")
    (repo / "README.md").write_text(text.replace("\nIteration ", "\nStage "), "utf-8")
    with pytest.raises(gate.GateUnavailable, match="no iteration"):
        gate.run_gate(repo)


# --- backlog-status ---------------------------------------------------------


def test_a_status_cell_that_disagrees_with_the_notes_is_a_finding(repo: Path) -> None:
    _edit(
        repo,
        "docs/13-BACKLOG.md",
        "| B-022 | P0-04 | Canonical JSON import with schema and property tests | F | B-017..021 | 3d | Open — note 2026-09-04 |",
        "| B-022 | P0-04 | Canonical JSON import with schema and property tests | F | B-017..021 | 3d | Closed |",
    )
    findings = gate.run_gate(repo)
    assert _checks(findings) == {"backlog-status"}
    assert "B-022 states 'Closed'" in findings[0].detail


def test_a_row_that_stops_carrying_a_status_is_a_finding(repo: Path) -> None:
    """The other direction: a column nobody states is a claim nobody checks."""

    _edit(
        repo,
        "docs/13-BACKLOG.md",
        "| B-001 | H-01..06, DG-01 | Recruit and complete 15\u201320 interviews; synthesis includes disconfirming evidence and buyer path | F | none | 10d | Open — no note |",
        "| B-001 | H-01..06, DG-01 | Recruit and complete 15\u201320 interviews; synthesis includes disconfirming evidence and buyer path | F | none | 10d |",
    )
    findings = gate.run_gate(repo)
    assert _checks(findings) == {"backlog-status"}
    assert "B-001 states '10d'" in findings[0].detail


def test_a_note_that_moves_to_a_later_date_moves_the_cell(repo: Path) -> None:
    """The cell is derived from the notes, so editing a note breaks the cell."""

    _edit(
        repo,
        "docs/13-BACKLOG.md",
        "Implementation note (2026-09-04, B-022):",
        "Implementation note (2026-09-30, B-022):",
    )
    findings = gate.run_gate(repo)
    assert _checks(findings) == {"backlog-status"}
    assert "derive 'Open \u2014 note 2026-09-30'" in findings[0].detail


def test_a_note_naming_no_item_leaves_its_row_saying_so(repo: Path) -> None:
    """A note header that names no item binds to nothing, and the row says it."""

    _edit(
        repo,
        "docs/13-BACKLOG.md",
        "Implementation note (2026-08-04, B-033):",
        "Implementation note (2026-08-04):",
    )
    findings = gate.run_gate(repo)
    assert _checks(findings) == {"backlog-status"}
    assert "B-033 states 'Open \u2014 note 2026-08-04'" in findings[0].detail
    assert "derive 'Open \u2014 no note'" in findings[0].detail


def test_a_backlog_with_no_phase_row_cannot_be_examined(repo: Path) -> None:
    path = repo / "docs" / "13-BACKLOG.md"
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("\n| B-0", "\n| X-0"), encoding="utf-8")
    with pytest.raises(gate.GateUnavailable, match="no phase-table row"):
        gate.run_gate(repo)


def test_the_parking_lot_and_the_allocation_rows_are_not_status_rows(
    repo: Path,
) -> None:
    """Only per-item phase rows carry a status; B-1xx and B-001-007 do not."""

    backlog = (repo / "docs" / "13-BACKLOG.md").read_text(encoding="utf-8")
    rows = {m.group("item") for m in gate._BACKLOG_ROW.finditer(backlog)}
    assert "B-101" not in rows
    assert len(rows) == 57


# --- the gate could not look ------------------------------------------------


def test_a_missing_document_is_exit_two_not_a_pass(repo: Path) -> None:
    (repo / "CONTRIBUTING.md").unlink()
    with pytest.raises(gate.GateUnavailable, match=r"cannot read CONTRIBUTING\.md"):
        gate.run_gate(repo)


def test_a_makefile_with_no_verify_target_cannot_be_examined(repo: Path) -> None:
    _edit(repo, "Makefile", "verify: sync", "notverify: sync")
    with pytest.raises(gate.GateUnavailable, match="no `verify` target"):
        gate.run_gate(repo)


def test_a_verify_target_with_no_prerequisites_cannot_be_examined(
    tmp_path: Path,
) -> None:
    (tmp_path / "Makefile").write_text("verify:\n\techo nothing\n", encoding="utf-8")
    with pytest.raises(gate.GateUnavailable, match="no prerequisites"):
        gate.verify_stages(tmp_path)


# --- the command line -------------------------------------------------------


def test_main_is_zero_and_prints_its_own_boundary(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert gate.main(["--root", str(repo)]) == 0
    out = capsys.readouterr().out
    assert "claims: clean" in out
    assert f"outside this gate ({len(gate.UNCOVERED)})" in out
    for item in gate.UNCOVERED:
        assert item.claim in out


def test_main_is_one_on_a_finding_and_says_where(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _edit(repo, "README.md", "and\niteration-6 file readers", "and\nfile readers")
    assert gate.main(["--root", str(repo)]) == 1
    err = capsys.readouterr().err
    assert "iteration-status" in err
    assert "derive the figure instead of restating it" in err


def test_main_is_two_when_it_could_not_examine(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert gate.main(["--root", str(tmp_path)]) == 2
    err = capsys.readouterr().err
    assert "not a clean result" in err


def test_main_defaults_to_this_checkout() -> None:
    assert gate.main([]) == 0
