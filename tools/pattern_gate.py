#!/usr/bin/env python3
"""Pattern gate: every published `pattern` has a runtime constant behind it.

What this catches that the other gates cannot
---------------------------------------------

A published contract and the runtime are two statements of the same grammar,
and nothing made them one statement. The defect fixed in #58 is what that
costs: `nameToUseTarget` in the mapping-profile contract inlined its own regular
expression instead of referencing the `syntheticToken` definition the same file
already carried, so no test compared the published pattern with the runtime
constant, the two drifted, the runtime was the looser of the pair, and the field
it was loose about was the one that carries a person's name.

`tests/test_mapping_profile_schema.py` pins four patterns against runtime
constants by hand. That is the right check performed over a set somebody has to
remember to extend: a new published pattern with no runtime counterpart is
exactly what slips past it, and did. This gate enumerates instead. Every
``pattern`` in every published contract (see *Scope* below) is collected, and
each one must be accounted for by the code that decides acceptance:

``equal``
    the pattern is a runtime constant, character for character once grouping is
    normalised. Nothing is declared for these and nothing needs to be: they are
    matched against the compiled objects the validators actually use.

``derived``
    the pattern is a stated function of named runtime constants -- a token
    grammar made optional, an alternation with a literal the reader accepts, the
    receipt's pointer grammar built from the segment vocabulary. The gate
    recomputes the function on every run and compares, so the derivation is
    checked rather than asserted.

``declared``
    the pattern has no runtime regular expression behind it, and the entry says
    what the runtime does instead. Every one is printed on every run, clean or
    not, so a reader sees what was declared away rather than only what was
    checked. There are three, and each names the code that decides the rule.

A published pattern in none of those three is a finding. So is a derivation or a
declaration that matches nothing published, because an entry describing a
contract that is not there is an entry nobody is maintaining.

Scope, and why it is declared rather than assumed
-------------------------------------------------

A published contract is any ``.json`` file anywhere under ``schemas/``. The
enumeration is recursive and by suffix, not by filename shape, because a flat
``schemas/*.schema.json`` glob reports clean over ``schemas/sub/`` and over a
contract named ``schemas/foo.json`` -- a check reporting clean over a file it
never opened, which is the defect this gate exists to catch, one level up.

Anything else under ``schemas/`` is placed or the gate refuses to run: a suffix
in ``DOCUMENTATION_SUFFIXES``, or a dot-prefixed name, is skipped by
declaration, and any other file ends the run at exit 2 naming it, because a file
this gate cannot place may be a published grammar going unexamined. The clean
line says how many contracts were read as well as how many patterns were found,
so a run that examined less than the directory holds is visible in the output
rather than indistinguishable from a real pass.

What this does not answer
-------------------------

Whether the *right* constant is behind a field. This gate answers "some runtime
constant says this"; swapping one published pattern for another runtime grammar
passes it. Holding a field to its own constant is still what
`tests/test_mapping_profile_schema.py` and `tests/test_receipt_schema.py` do,
and `tests/test_pattern_gate.py` states this boundary as a test rather than as
this paragraph, so a later reader cannot mistake the gate for more than it is.

Grouping, and why the comparison normalises it
-----------------------------------------------

Half the published patterns spell a group ``(`` where the runtime spells it
``(?:``. Capturing changes what a match object carries and not what the language
accepts, and no consumer of a JSON Schema ``pattern`` reads groups, so this gate
compares with ``(?:`` rewritten to ``(`` in both. Nothing else is normalised: a
quantifier, a character class or an anchor that differs is a difference.

Usage
-----

::

    tools/pattern_gate.py            # 0 clean, 1 finding, 2 could not examine
    tools/pattern_gate.py --root DIR # examine another checkout

Exit 0 when every published pattern is accounted for, 1 on a finding, and 2 when
the gate could not read the contracts or the runtime constants it compares --
including the case where it found no pattern at all, and the case where a file
sits under ``schemas/`` that it cannot place. Neither is a clean run.
See `docs/adr/0008-one-exit-code-contract-for-every-gate.md`.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import pkgutil
import re
import sys
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[1]

if str(REPO_ROOT / "src") not in sys.path:  # pragma: no cover - import shim
    sys.path.insert(0, str(REPO_ROOT / "src"))

import contextsafe  # noqa: E402
from contextsafe.contract_validation import Grammar  # noqa: E402

CONTRACT_SUFFIX = ".json"
"""What a published contract is named. Enumeration is by suffix, at any depth."""

DOCUMENTATION_SUFFIXES: frozenset[str] = frozenset({".md"})
"""What may sit beside the contracts without being one. Anything else refuses."""


class GateUnavailable(Exception):
    """The gate could not establish what is published or what the runtime says."""


@dataclass(frozen=True)
class Published:
    """Every published pattern, and how many contract files were read for them.

    The count travels with the patterns because the clean line prints it: a
    denominator nobody can see is how a gate reports clean over a directory it
    half read.
    """

    patterns: dict[str, tuple[str, ...]]
    files: int


@dataclass(frozen=True)
class Finding:
    """One published pattern with nothing behind it, or one stale entry."""

    rule_id: str
    subject: str
    detail: str

    def __str__(self) -> str:
        return f"{self.rule_id}: {self.subject}: {self.detail}"


@dataclass(frozen=True)
class Derivation:
    """One published pattern stated as a function of named runtime constants."""

    name: str
    sources: tuple[str, ...]
    build: Callable[[], str]


@dataclass(frozen=True)
class DeclaredException:
    """One published pattern with no runtime regular expression behind it."""

    pattern: str
    reason: str


def normalise(expression: str) -> str:
    """Return ``expression`` with grouping spelled one way."""

    return expression.replace("(?:", "(")


def _body(pattern: str) -> str:
    """Return an anchored pattern's body, refusing one that is not anchored."""

    if not pattern.startswith("^") or not pattern.endswith("$"):
        raise GateUnavailable(
            f"the runtime constant {pattern!r} is not anchored, so this gate "
            "cannot take its body to build a published pattern from"
        )
    return pattern[1:-1]


def _load_module(module_name: str) -> ModuleType:
    """Import one module of the package under test, by the file that defines it.

    ``importlib.import_module`` would say the same thing in one line. It is not
    used here for the reason ADR 0004 gives for restructuring rather than
    waiving a SAST finding: the registry rule `non-literal-import` is a shape
    matcher, it fires on every dynamic name, and this repository does not write
    `# nosemgrep`. Loading through the spec the package itself reports is also
    the more exact statement of what this gate does, and it is the idiom
    ``tools/scope_gate.py`` already uses to read a sibling gate's constants.
    """

    module = sys.modules.get(module_name)
    if module is not None:
        return module
    spec = importlib.util.find_spec(module_name)
    if spec is None or spec.loader is None:
        raise GateUnavailable(f"{module_name} could not be located")
    module = importlib.util.module_from_spec(spec)
    # Registered before execution: a module that defines dataclasses resolves
    # its annotations through ``sys.modules[cls.__module__]``.
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        sys.modules.pop(spec.name, None)
        raise GateUnavailable(f"{module_name} could not be imported: {exc}") from exc
    return module


def _runtime(module_name: str, attribute: str) -> object:
    """Return one runtime constant by name, or refuse to run."""

    module = _load_module(module_name)
    try:
        return getattr(module, attribute)
    except AttributeError as exc:
        raise GateUnavailable(
            f"{module_name} has no `{attribute}`, so the pattern derived from it "
            "compares against nothing"
        ) from exc


def _pattern_of(module_name: str, attribute: str) -> str:
    value = _runtime(module_name, attribute)
    if not isinstance(value, re.Pattern):
        raise GateUnavailable(
            f"{module_name}.{attribute} is not a compiled pattern, so this gate "
            "cannot derive a published pattern from it"
        )
    return str(value.pattern)


def _text_of(module_name: str, attribute: str) -> str:
    value = _runtime(module_name, attribute)
    if not isinstance(value, str) or not value:
        raise GateUnavailable(
            f"{module_name}.{attribute} is not a non-empty string, so this gate "
            "cannot derive a published pattern from it"
        )
    if re.escape(value) != value.replace("-", "\\-"):
        raise GateUnavailable(
            f"{module_name}.{attribute} carries a regular-expression "
            "metacharacter, so writing it into a pattern would not be the "
            "literal the runtime compares"
        )
    return value


def optional_token(module_name: str, attribute: str) -> Callable[[], str]:
    """A token grammar, made optional: the empty cell a column may carry."""

    return lambda: f"^(?:{_body(_pattern_of(module_name, attribute))})?$"


def token_or_literal(
    module_name: str, attribute: str, literal_module: str, literal_attribute: str
) -> Callable[[], str]:
    """A token grammar, or one literal string the reader accepts beside it."""

    def build() -> str:
        body = _body(_pattern_of(module_name, attribute))
        holder, _, member = literal_attribute.partition(".")
        if not member:
            raise GateUnavailable(
                f"{literal_module}.{literal_attribute} does not name an "
                "attribute of a runtime object, so this gate cannot read the "
                "literal it would write into a published pattern"
            )
        literal = getattr(_runtime(literal_module, holder), member, None)
        if not isinstance(literal, str) or not literal.isalnum():
            raise GateUnavailable(
                f"{literal_module}.{literal_attribute} is not an alphanumeric "
                "literal, so it cannot be written into a pattern as itself"
            )
        return f"^(?:{body}|{literal})$"

    return build


def prefix_only(module_name: str, attribute: str) -> Callable[[], str]:
    """A prefix, and nothing else: the whole of what the contract can state."""

    return lambda: f"^{_text_of(module_name, attribute)}"


def structural_pointer() -> str:
    """The receipt's pointer grammar, built from the runtime's own vocabulary.

    Three dialects over one closed vocabulary, and each dialect's bound is a
    runtime constant: the ``$``-rooted dialects are bounded in length, the
    RFC 6901 dialect in depth, and the published contract states both because
    neither implies the other. It stated ``maxLength: 160`` and an unbounded
    depth until #72, which is the same disagreement as #58 in a different field.
    """

    validation = _load_module("contextsafe.validation")
    vocabulary = getattr(validation, "STRUCTURAL_POINTER_SEGMENTS", None)
    if not isinstance(vocabulary, frozenset) or not vocabulary:
        raise GateUnavailable(
            "contextsafe.validation has no non-empty STRUCTURAL_POINTER_SEGMENTS, "
            "so the published pointer grammar compares against nothing"
        )
    segment_name = _runtime("contextsafe.validation", "_HL7_SEGMENT_NAME")
    words = "|".join(sorted(str(word) for word in vocabulary))
    segments = sorted(
        word for word in vocabulary if re.fullmatch(str(segment_name), str(word))
    )
    if not segments:
        raise GateUnavailable(
            "no word in the pointer vocabulary is shaped like an HL7 v2 segment "
            "name, so the published HL7 dialect could match nothing"
        )
    index = str(_runtime("contextsafe.validation", "_SEGMENT_INDEX"))
    depth = _runtime("contextsafe.validation", "JSON_POINTER_MAX_SEGMENTS")
    return (
        rf"^(?:\$(?:\.(?:{words})|\[{index}\])+"
        rf"|\$\.(?:{'|'.join(segments)})\[{index}\]-{index}\.{index}\.{index}"
        rf"|(?:/(?:{words}|{index})){{1,{depth}}})$"
    )


DERIVATIONS: tuple[Derivation, ...] = (
    Derivation(
        "lis-synthetic-identifier-cell",
        ("contextsafe.importers.lis.SYNTHETIC_IDENTIFIER_PATTERN",),
        optional_token("contextsafe.importers.lis", "SYNTHETIC_IDENTIFIER_PATTERN"),
    ),
    Derivation(
        "lis-result-cell",
        ("contextsafe.importers.lis.RESULT_TOKEN_PATTERN",),
        optional_token("contextsafe.importers.lis", "RESULT_TOKEN_PATTERN"),
    ),
    Derivation(
        "fhir-name-token",
        (
            "contextsafe.importers.fhir_r4_json._NAME_TOKEN",
            "contextsafe.importers.fhir_r4_json.FHIR_R4_PROFILE.synthetic_family_name",
        ),
        token_or_literal(
            "contextsafe.importers.fhir_r4_json",
            "_NAME_TOKEN",
            "contextsafe.importers.fhir_r4_json",
            "FHIR_R4_PROFILE.synthetic_family_name",
        ),
    ),
    Derivation(
        "synthetic-name-prefix",
        ("contextsafe.validation.SYNTHETIC_NAME_PREFIX",),
        prefix_only("contextsafe.validation", "SYNTHETIC_NAME_PREFIX"),
    ),
    Derivation(
        "receipt-structural-pointer",
        (
            "contextsafe.validation.STRUCTURAL_POINTER_SEGMENTS",
            "contextsafe.validation.JSON_POINTER_MAX_SEGMENTS",
        ),
        structural_pointer,
    ),
)
"""Published patterns that are a stated function of named runtime constants."""


DECLARED_EXCEPTIONS: tuple[DeclaredException, ...] = (
    DeclaredException(
        "^(?:[0-9]{4}-(?:(?:0[13578]|1[02])-(?:0[1-9]|[12][0-9]|3[01])"
        "|(?:0[469]|11)-(?:0[1-9]|[12][0-9]|30)|02-(?:0[1-9]|1[0-9]|2[0-9])))"
        "T(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]Z$",
        "the runtime's calendar bound is `datetime`, not a regular expression: "
        "`contextsafe.contract_validation.TIMESTAMP_PATTERN` bounds the shape and "
        "`timestamp_value` parses the result, so month 13 is refused by the parse. "
        "A consumer holding only the published contract has no parser, so the "
        "contract states the calendar it can state",
    ),
    DeclaredException(
        "^[^\\uD800-\\uDFFF]*$",
        "the runtime refuses a lone surrogate by code point -- the "
        "`0xD800 <= ord(character) <= 0xDFFF` comparison in "
        "`contextsafe.validation` and `contextsafe.contract_validation` -- rather "
        "than by pattern, because the rule is about what a string *is* and not "
        "about what it spells. `tests/test_contracts.py` holds both ends of that "
        "block, and the published pattern is the same rule written for a validator "
        "that has only patterns",
    ),
    DeclaredException(
        "^CSYN-[A-Z0-9][A-Z0-9_.:-]{0,90}$",
        "two runtime bounds at one location, stated as one pattern: a FHIR coding's "
        "code is held to `_SYNTHETIC_CODE` (`{0,95}`) and, at the coding itself, to "
        "`_CODING_TOKEN_LENGTH` (96 characters), and 96 less the five characters of "
        "the prefix and the one leading class is 90. The contract carries "
        "`maxLength: 96` beside this, so the two together are the pair the reader "
        "applies",
    ),
)
"""Published patterns with no runtime regular expression. Printed on every run."""


def _walk(node: object, location: str) -> Iterator[tuple[str, str]]:
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "pattern" and isinstance(value, str):
                yield location, value
            else:
                yield from _walk(value, f"{location}/{key}")
    elif isinstance(node, list):
        for index, item in enumerate(node):
            yield from _walk(item, f"{location}/{index}")


def contract_files(root: Path) -> tuple[Path, ...]:
    """Every published contract under ``schemas/``, at any depth.

    By suffix and recursively, and refusing rather than skipping what it cannot
    place. A ``schemas/*.schema.json`` glob answers for the files somebody
    remembered to name that way: ``schemas/sub/contextsafe-x-v1.schema.json``
    and ``schemas/x.json`` are both published grammars it never opens, and a
    gate reporting clean over a contract it never opened is #58 again with this
    file as the subject.
    """

    directory = root / "schemas"
    files: list[Path] = []
    for path in sorted(directory.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix == CONTRACT_SUFFIX:
            files.append(path)
        elif path.name.startswith(".") or path.suffix in DOCUMENTATION_SUFFIXES:
            continue
        else:
            raise GateUnavailable(
                f"{path.relative_to(directory).as_posix()} is under {directory} "
                f"and is neither a `{CONTRACT_SUFFIX}` contract this gate reads "
                "nor a documentation suffix it declares, so it may be a "
                "published grammar going unexamined"
            )
    if not files:
        raise GateUnavailable(
            f"no published contract under {directory}, so there is nothing to "
            "compare against the runtime and a clean result would mean nothing"
        )
    return tuple(files)


def published_patterns(root: Path) -> Published:
    """Every ``pattern`` in every published contract, by the pattern itself."""

    directory = root / "schemas"
    files = contract_files(root)
    found: dict[str, list[str]] = {}
    for path in files:
        name = path.relative_to(directory).as_posix()
        try:
            schema = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GateUnavailable(f"{name} could not be read: {exc}") from exc
        for location, pattern in _walk(schema, name):
            found.setdefault(pattern, []).append(location)
    if not found:
        raise GateUnavailable(
            f"{len(files)} published contract(s) carry no `pattern` at all, which "
            "is not a repository this gate can report clean over"
        )
    return Published(
        {pattern: tuple(sorted(where)) for pattern, where in found.items()},
        len(files),
    )


def _module_constants(module: ModuleType, found: dict[str, list[str]]) -> None:
    for name, value in sorted(vars(module).items()):
        if isinstance(value, re.Pattern):
            found.setdefault(normalise(str(value.pattern)), []).append(
                f"{module.__name__}.{name}"
            )
        elif isinstance(value, Grammar):
            expressions = (value.base, *(item[0] for item in value.exclusions))
            for expression in expressions:
                found.setdefault(normalise(expression), []).append(
                    f"{module.__name__}.{name}"
                )


def runtime_constants() -> dict[str, tuple[str, ...]]:
    """Every compiled pattern and published grammar the runtime holds."""

    found: dict[str, list[str]] = {}
    for info in pkgutil.walk_packages(
        contextsafe.__path__, prefix=f"{contextsafe.__name__}."
    ):
        _module_constants(_load_module(info.name), found)
    if not found:
        raise GateUnavailable(
            "the runtime holds no compiled pattern, so every published pattern "
            "would be unaccounted for and none of them would have been compared"
        )
    return {pattern: tuple(sorted(set(where))) for pattern, where in found.items()}


def _derived_index(
    derivations: Sequence[Derivation],
) -> dict[str, Derivation]:
    built: dict[str, Derivation] = {}
    for derivation in derivations:
        pattern = normalise(derivation.build())
        if pattern in built:
            raise GateUnavailable(
                f"the derivations `{built[pattern].name}` and `{derivation.name}` "
                "produce the same pattern, so one of them is checking nothing"
            )
        built[pattern] = derivation
    return built


def check(
    published: dict[str, tuple[str, ...]],
    runtime: dict[str, tuple[str, ...]],
    derivations: Sequence[Derivation] = DERIVATIONS,
    exceptions: Sequence[DeclaredException] = DECLARED_EXCEPTIONS,
) -> tuple[list[Finding], dict[str, int]]:
    """Account for every published pattern, and for every entry that accounts."""

    derived = _derived_index(derivations)
    declared = {normalise(item.pattern): item for item in exceptions}
    counts = {"equal": 0, "derived": 0, "declared": 0}
    findings: list[Finding] = []
    used: set[str] = set()
    for pattern, where in sorted(published.items()):
        key = normalise(pattern)
        used.add(key)
        if key in runtime:
            counts["equal"] += 1
        elif key in derived:
            counts["derived"] += 1
        elif key in declared:
            counts["declared"] += 1
        else:
            findings.append(
                Finding(
                    "unbound-pattern",
                    ", ".join(where),
                    "published with no runtime constant behind it: no compiled "
                    "pattern in the package equals it, no derivation builds it, "
                    "and no declared exception names it. A published grammar "
                    "nothing compares to the code is the drift #58 was",
                )
            )
    findings += _stale(derived, declared, used)
    return findings, counts


def _stale(
    derived: dict[str, Derivation],
    declared: dict[str, DeclaredException],
    used: set[str],
) -> list[Finding]:
    """An entry that accounts for nothing describes contracts that are not here."""

    findings: list[Finding] = []
    for pattern, derivation in sorted(derived.items(), key=lambda item: item[1].name):
        if pattern not in used:
            findings.append(
                Finding(
                    "stale-derivation",
                    derivation.name,
                    "builds a pattern no published contract carries, so it "
                    "verifies nothing and the contract it described is gone",
                )
            )
    for pattern, exception in sorted(declared.items()):
        if pattern not in used:
            findings.append(
                Finding(
                    "stale-exception",
                    exception.pattern,
                    "declared as having no runtime counterpart, but no published "
                    "contract carries it, so it excuses nothing",
                )
            )
    return findings


def _report(published: Published, counts: dict[str, int]) -> None:
    occurrences = sum(len(where) for where in published.patterns.values())
    print(
        f"pattern-gate: clean - {len(published.patterns)} distinct pattern(s) in "
        f"{occurrences} place(s) across {published.files} published contract(s): "
        f"{counts['equal']} equal to a runtime constant, "
        f"{counts['derived']} derived from one, {counts['declared']} declared "
        "without one"
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the gate: 0 when every pattern is accounted for, 1 finding, 2 no answer."""

    parser = argparse.ArgumentParser(
        prog="pattern_gate",
        description="Fail when a published `pattern` has no runtime constant "
        "behind it, and fail louder when the comparison could not be made.",
    )
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    args = parser.parse_args(argv)

    try:
        published = published_patterns(args.root)
        findings, counts = check(published.patterns, runtime_constants())
    except GateUnavailable as exc:
        print(f"pattern-gate: {exc}.", file=sys.stderr)
        print(
            "pattern-gate: this is a failure to run the gate, not a clean result.",
            file=sys.stderr,
        )
        return 2

    for item in DECLARED_EXCEPTIONS:
        print(f"pattern-gate: declared without a runtime pattern: {item.reason}")

    if findings:
        print(
            f"pattern-gate: {len(findings)} finding(s) over "
            f"{len(published.patterns)} distinct pattern(s) in "
            f"{published.files} published contract(s)",
            file=sys.stderr,
        )
        for finding in findings:
            print(f"  {finding}", file=sys.stderr)
        return 1

    _report(published, counts)
    return 0


if __name__ == "__main__":  # pragma: no cover - module entry point
    raise SystemExit(main())
