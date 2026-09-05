"""The pattern gate must fail on a published grammar nothing in the code decides.

The defect this closes is #58: `nameToUseTarget` inlined its own regular
expression instead of referencing the `syntheticToken` the same schema carried,
so nothing compared the published pattern with the runtime constant, and the two
drifted on the one field that carries a person's name. The check that would have
caught it existed for four other patterns in
`tests/test_mapping_profile_schema.py`, by hand, over a set somebody had to
remember to extend.

So the load-bearing cases here are: this repository is clean; a published pattern
with no runtime constant behind it is a finding; a derivation or a declaration
that matches nothing published is a finding; a derivation is recomputed rather
than trusted, so moving the runtime constant it is built from fails; and a gate
that read no contract, or no runtime pattern, is exit 2 and never a pass.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from contextsafe import validation

REPO_ROOT = Path(__file__).resolve().parents[1]
GATE_PATH = REPO_ROOT / "tools" / "pattern_gate.py"
SCHEMAS = REPO_ROOT / "schemas"

CLEAN, FOUND, UNAVAILABLE = 0, 1, 2


def _load_gate() -> ModuleType:
    spec = importlib.util.spec_from_file_location("pattern_gate", GATE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


gate = _load_gate()


def _copy_schemas(root: Path) -> Path:
    directory = root / "schemas"
    directory.mkdir(parents=True)
    for path in sorted(SCHEMAS.glob("*.schema.json")):
        (directory / path.name).write_text(
            path.read_text(encoding="utf-8"), encoding="utf-8"
        )
    return directory


def _edit(path: Path, mutate: Callable[[Any], None]) -> None:
    schema = json.loads(path.read_text(encoding="utf-8"))
    mutate(schema)
    path.write_text(json.dumps(schema, indent=2), encoding="utf-8")


# --- this repository ---------------------------------------------------------


def test_this_repository_accounts_for_every_published_pattern() -> None:
    assert gate.main([]) == CLEAN


def test_every_published_contract_is_read_and_every_pattern_counted() -> None:
    """The clean line is only worth reading if the count behind it is real."""

    published = gate.published_patterns(REPO_ROOT)
    occurrences = sum(len(where) for where in published.values())
    assert len(published) >= 40
    assert occurrences > len(published)
    _, counts = gate.check(published, gate.runtime_constants())
    assert sum(counts.values()) == len(published)
    assert counts["equal"] > counts["derived"] + counts["declared"]


def test_the_declared_exceptions_are_printed_on_a_clean_run(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A pattern declared to have no runtime counterpart is shown, not hidden."""

    assert gate.main([]) == CLEAN
    printed = capsys.readouterr().out
    for exception in gate.DECLARED_EXCEPTIONS:
        assert exception.reason in printed


def test_the_receipt_pointer_derivation_is_the_published_pattern() -> None:
    """#72: one function builds it, and the published contract carries the result."""

    published = gate.published_patterns(REPO_ROOT)
    assert gate.structural_pointer() in published


# --- a published pattern with nothing behind it ------------------------------


def test_a_published_pattern_with_no_runtime_constant_is_a_finding(
    tmp_path: Path,
) -> None:
    """The #58 shape: a schema inlines a grammar the code has never heard of."""

    directory = _copy_schemas(tmp_path)
    target = directory / "contextsafe-mapping-profile-v1.schema.json"

    def inline_a_looser_name_grammar(schema: Any) -> None:
        schema["$defs"]["nameToUseTarget"] = {"type": "string", "pattern": "^CSYN-.+$"}

    _edit(target, inline_a_looser_name_grammar)
    assert gate.main(["--root", str(tmp_path)]) == FOUND


def test_the_finding_names_the_contract_and_the_place_in_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    directory = _copy_schemas(tmp_path)

    def add(schema: Any) -> None:
        schema["$defs"]["invented"] = {"type": "string", "pattern": "^INVENTED-[0-9]+$"}

    _edit(directory / "contextsafe-case-v0.1.schema.json", add)
    assert gate.main(["--root", str(tmp_path)]) == FOUND
    reported = capsys.readouterr().err
    assert "contextsafe-case-v0.1.schema.json/$defs/invented" in reported
    assert "unbound-pattern" in reported


def test_a_pattern_that_merely_looks_like_a_runtime_one_is_a_finding(
    tmp_path: Path,
) -> None:
    """One character of drift is the whole point: `{0,95}` is not `{0,96}`."""

    directory = _copy_schemas(tmp_path)

    def widen(schema: Any) -> None:
        schema["$defs"]["syntheticToken"]["pattern"] = (
            "^(CSYN-[A-Z0-9][A-Z0-9_.:-]{0,96}|fixture-[a-z0-9][a-z0-9-]{0,63})$"
        )

    _edit(directory / "contextsafe-mapping-profile-v1.schema.json", widen)
    assert gate.main(["--root", str(tmp_path)]) == FOUND


def test_capturing_and_non_capturing_grouping_is_not_drift() -> None:
    """Half the published patterns spell `(` where the runtime spells `(?:`."""

    assert gate.normalise("^(?:a|b)$") == gate.normalise("^(a|b)$")
    assert gate.normalise("^(?=a)b$") == "^(?=a)b$"


# --- entries that account for nothing ----------------------------------------


def test_a_derivation_matching_nothing_published_is_a_finding() -> None:
    findings, _ = gate.check(
        {"^CTP-[A-Z0-9]{3,16}$": ("case.json",)},
        gate.runtime_constants(),
        derivations=(
            gate.Derivation("invented", ("nothing",), lambda: "^NOT-PUBLISHED$"),
        ),
        exceptions=(),
    )
    assert [finding.rule_id for finding in findings] == ["stale-derivation"]


def test_a_declared_exception_matching_nothing_published_is_a_finding() -> None:
    findings, _ = gate.check(
        {"^CTP-[A-Z0-9]{3,16}$": ("case.json",)},
        gate.runtime_constants(),
        derivations=(),
        exceptions=(gate.DeclaredException("^NOT-PUBLISHED$", "a reason"),),
    )
    assert [finding.rule_id for finding in findings] == ["stale-exception"]


def test_two_derivations_that_build_the_same_pattern_are_a_refusal() -> None:
    """One of them is then checking nothing, and the gate cannot say which."""

    with pytest.raises(gate.GateUnavailable):
        gate.check(
            {"^A$": ("case.json",)},
            {},
            derivations=(
                gate.Derivation("first", (), lambda: "^A$"),
                gate.Derivation("second", (), lambda: "^A$"),
            ),
            exceptions=(),
        )


# --- the derivations are recomputed, not trusted -----------------------------


def test_moving_a_runtime_constant_moves_the_derivation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A derivation that did not follow its source would pin the wrong thing."""

    before = gate.structural_pointer()
    monkeypatch.setattr(validation, "JSON_POINTER_MAX_SEGMENTS", 8)
    after = gate.structural_pointer()
    assert before != after
    assert "{1,8}" in after
    assert gate.main([]) == FOUND


def test_a_derivation_whose_runtime_constant_is_gone_is_a_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delattr(validation, "SYNTHETIC_NAME_PREFIX")
    with pytest.raises(gate.GateUnavailable):
        gate.prefix_only("contextsafe.validation", "SYNTHETIC_NAME_PREFIX")()


def test_a_prefix_carrying_a_metacharacter_is_a_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`CSYN.` in a pattern is not the literal the runtime compares."""

    monkeypatch.setattr(validation, "SYNTHETIC_NAME_PREFIX", "CSYN.")
    with pytest.raises(gate.GateUnavailable):
        gate.prefix_only("contextsafe.validation", "SYNTHETIC_NAME_PREFIX")()


def test_an_unanchored_runtime_constant_cannot_be_built_from() -> None:
    with pytest.raises(gate.GateUnavailable):
        gate._body("CSYN-[A-Z]+")


def test_a_runtime_name_that_is_not_a_pattern_is_a_refusal() -> None:
    with pytest.raises(gate.GateUnavailable):
        gate._pattern_of("contextsafe.validation", "SYNTHETIC_NAME_PREFIX")


def test_a_runtime_name_that_is_not_text_is_a_refusal() -> None:
    with pytest.raises(gate.GateUnavailable):
        gate._text_of("contextsafe.validation", "_CASE_ID")


def test_a_runtime_name_that_does_not_exist_is_a_refusal() -> None:
    with pytest.raises(gate.GateUnavailable):
        gate._runtime("contextsafe.validation", "NOT_A_CONSTANT")


def test_a_family_name_that_is_not_alphanumeric_is_a_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from contextsafe.importers import fhir_r4_json

    monkeypatch.setattr(
        fhir_r4_json,
        "FHIR_R4_PROFILE",
        type("Profile", (), {"synthetic_family_name": "ZZZ TEST"})(),
    )
    build = gate.token_or_literal(
        "contextsafe.importers.fhir_r4_json",
        "_NAME_TOKEN",
        "contextsafe.importers.fhir_r4_json",
        "FHIR_R4_PROFILE.synthetic_family_name",
    )
    with pytest.raises(gate.GateUnavailable):
        build()


def test_a_pointer_vocabulary_with_no_segment_name_is_a_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The HL7 dialect would then match nothing, which is not a grammar."""

    monkeypatch.setattr(
        validation, "STRUCTURAL_POINTER_SEGMENTS", frozenset({"concepts"})
    )
    with pytest.raises(gate.GateUnavailable):
        gate.structural_pointer()


def test_an_empty_pointer_vocabulary_is_a_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(validation, "STRUCTURAL_POINTER_SEGMENTS", frozenset())
    with pytest.raises(gate.GateUnavailable):
        gate.structural_pointer()


# --- it examined nothing -----------------------------------------------------


def test_a_checkout_with_no_published_contract_is_a_refusal(tmp_path: Path) -> None:
    assert gate.main(["--root", str(tmp_path)]) == UNAVAILABLE


def test_contracts_carrying_no_pattern_at_all_are_a_refusal(tmp_path: Path) -> None:
    """Zero patterns compared is not zero patterns wrong."""

    directory = tmp_path / "schemas"
    directory.mkdir()
    (directory / "contextsafe-empty-v1.schema.json").write_text(
        json.dumps({"type": "object"}), encoding="utf-8"
    )
    assert gate.main(["--root", str(tmp_path)]) == UNAVAILABLE


def test_a_contract_that_cannot_be_parsed_is_a_refusal(tmp_path: Path) -> None:
    directory = _copy_schemas(tmp_path)
    (directory / "contextsafe-case-v0.1.schema.json").write_text(
        "{ not json", encoding="utf-8"
    )
    assert gate.main(["--root", str(tmp_path)]) == UNAVAILABLE


def test_a_runtime_holding_no_pattern_is_a_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(gate.pkgutil, "walk_packages", lambda *a, **k: iter(()))
    with pytest.raises(gate.GateUnavailable):
        gate.runtime_constants()


def test_the_refusal_is_a_distinct_exit_code_from_a_finding(tmp_path: Path) -> None:
    """Two codes is how a gate lies about the difference."""

    assert gate.main(["--root", str(tmp_path)]) != FOUND


# --- what the gate does not claim --------------------------------------------


def test_a_grammar_the_runtime_holds_for_another_field_is_not_detected(
    tmp_path: Path,
) -> None:
    """Stated so the boundary is a test rather than a paragraph.

    The gate answers "some runtime constant says this", not "the right one
    does". Swapping one published pattern for another runtime grammar passes
    here, and `tests/test_mapping_profile_schema.py` is what holds a specific
    field to a specific constant.
    """

    directory = _copy_schemas(tmp_path)

    def swap(schema: Any) -> None:
        schema["$defs"]["fixtureSystem"]["pattern"] = validation._CASE_ID.pattern

    _edit(directory / "contextsafe-mapping-profile-v1.schema.json", swap)
    assert gate.main(["--root", str(tmp_path)]) == CLEAN


def test_the_runtime_index_reaches_a_published_token_grammar() -> None:
    """`Grammar` states its patterns as strings, not as compiled objects."""

    runtime = gate.runtime_constants()
    assert gate.normalise(r"^[A-Za-z][A-Za-z0-9._-]*$") in runtime
    assert gate.normalise(r"[0-9]{4}") in runtime
    assert any(
        name.endswith("PROVENANCE_LABEL_GRAMMAR")
        for names in runtime.values()
        for name in names
    )


def test_every_derivation_names_the_runtime_constants_it_is_built_from() -> None:
    """A derivation whose sources are unstated is not reviewable."""

    for derivation in gate.DERIVATIONS:
        assert derivation.sources
        for source in derivation.sources:
            module, _, attribute = source.rpartition(".")
            assert module.startswith("contextsafe")
            assert re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", attribute)
