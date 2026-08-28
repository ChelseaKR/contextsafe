#!/usr/bin/env python3
"""Mutation gate: evidence that the suite would notice a change, not just run.

Why branch coverage is not this
-------------------------------

`make test` holds 90% branch coverage overall and 95% across the safety modules.
Coverage is an execution measure. It says a line ran; it says nothing about
whether anything would have failed had the line been wrong. A suite that
imports every module and asserts almost nothing reports the same number as a
suite that pins every boundary.

This gate answers the other question. It changes one operator or one constant
in a safety module, runs the declared tests, and requires them to fail. A
mutant the tests do not kill is a line they execute and do not check.

What is measured, and what is declared away
-------------------------------------------

Two modules, named in ``DECLARED_TARGETS``, and the tests that must kill their
mutants. That is a subset of ``SAFETY_MODULES`` and
it is a declaration rather than a silence: `make scope` is the model, and the
same rule applies here, that a declaration which no longer matches the tree is
itself a finding.

Mutants are generated only on lines the suite actually executes, measured with
`coverage` in the same run rather than assumed. A mutant on a line
nothing runs would survive for a reason mutation testing was not asked about,
and the run prints how many lines it covered so the denominator is visible.

Nothing is written into the working tree. The declared modules are copied to a
temporary directory, mutated there, and put in front of the editable install
with ``PYTHONPATH``, so a crash or an interrupt cannot leave a mutated source
file behind.

Survivors
---------

A mutant the whole suite does not kill is a finding, with no allowlist to put it
on. Nothing here is currently unkillable, so there is no exemption mechanism;
adding one before a mutant needs it would be building the escape hatch first.

Why this is not in `make verify`
--------------------------------

Runtime. Every mutant is a separate test run. The declared set takes on the
order of a minute, against roughly one second for the rest of `verify`, so this
is its own target the way `make secret-scan` and `make a11y-full` are. It needs
no tool a clean clone lacks.

Usage
-----

    tools/mutation_gate.py
    tools/mutation_gate.py --root PATH

Exit 0 when every mutant was killed, 1 when one survived, 2 when the gate could
not produce evidence: the suite does not pass unmutated, no line was covered, or
no mutant was generated.
"""

from __future__ import annotations

import argparse
import ast
import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

DECLARED_TARGETS: tuple[str, ...] = (
    "src/contextsafe/contract_validation.py",
    "src/contextsafe/identifiers.py",
)
"""The modules whose mutants must die.

A subset of the Makefile's ``SAFETY_MODULES``, chosen because these two are
where the accept-or-reject decisions live: the bounded-string and provenance
grammars, and the PHI canary and direct-identifier detectors. Widening the set
is a runtime decision, not a design one; the declaration is here so the subset
is visible rather than implied.
"""

SCREENING_TESTS: tuple[str, ...] = (
    "tests/test_contracts.py",
    "tests/test_evidence_models.py",
    "tests/test_plan.py",
    "tests/test_preflight.py",
)
"""The fast tests every mutant is run against first.

An optimisation, not the claim. A mutant these kill is killed; a mutant they do
not kill goes on to the whole suite, because the question this gate answers is
whether *the suite* would notice, and answering it with a subset would report a
survivor the suite in fact catches. Survivors are the only mutants that pay the
full run, so the gate gets faster as they are fixed.
"""

PACKAGE_DIR = "src/contextsafe"
"""The importable package, copied and mutated in a temporary directory."""

SUITE = "tests"
"""The whole suite, run for a mutant the screening set did not kill."""

COMPARISON_SWAPS: dict[type[ast.cmpop], type[ast.cmpop]] = {
    ast.Lt: ast.LtE,
    ast.LtE: ast.Lt,
    ast.Gt: ast.GtE,
    ast.GtE: ast.Gt,
    ast.Eq: ast.NotEq,
    ast.NotEq: ast.Eq,
    ast.In: ast.NotIn,
    ast.NotIn: ast.In,
    ast.Is: ast.IsNot,
    ast.IsNot: ast.Is,
}


class GateUnavailable(Exception):
    """The gate could not produce evidence, which is never a clean result."""


@dataclass(frozen=True)
class Mutant:
    """One changed operator or constant, and where it was."""

    module: str
    line: int
    column: int
    operator: str
    description: str

    @property
    def identity(self) -> str:
        return f"{self.module}:{self.line}:{self.column}:{self.operator}"

    def __str__(self) -> str:
        return f"{self.identity}: {self.description}"


def _numbered(tree: ast.AST) -> Iterator[tuple[int, ast.AST]]:
    """Yield every node with a stable index, so mutant order is deterministic."""

    yield from enumerate(ast.walk(tree))


def _mutations_for(
    node: ast.AST,
) -> list[tuple[str, str, object]]:
    """Return the (operator, description, replacement) options for one node."""

    if isinstance(node, ast.Compare) and len(node.ops) == 1:
        original = type(node.ops[0])
        replacement = COMPARISON_SWAPS.get(original)
        if replacement is not None:
            return [
                (
                    "comparison",
                    f"{original.__name__} became {replacement.__name__}",
                    replacement(),
                )
            ]
    if isinstance(node, ast.BoolOp):
        replacement_op = ast.Or() if isinstance(node.op, ast.And) else ast.And()
        name = "and became or" if isinstance(node.op, ast.And) else "or became and"
        return [("boolean", name, replacement_op)]
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return [("negation", "not was removed", node.operand)]
    if isinstance(node, ast.Constant) and isinstance(node.value, bool):
        return [("constant", f"{node.value} became {not node.value}", not node.value)]
    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, int)
        and not isinstance(node.value, bool)
    ):
        return [("bound", f"{node.value} became {node.value + 1}", node.value + 1)]
    return []


def _apply(tree: ast.AST, index: int, replacement: object) -> ast.AST:
    """Return a copy of ``tree`` with the node at ``index`` mutated."""

    mutated = copy.deepcopy(tree)
    for position, node in _numbered(mutated):
        if position != index:
            continue
        if isinstance(node, ast.Compare) and isinstance(replacement, ast.cmpop):
            node.ops = [replacement]
        elif isinstance(node, ast.BoolOp) and isinstance(replacement, ast.boolop):
            node.op = replacement
        elif isinstance(node, ast.Constant) and isinstance(replacement, bool | int):
            node.value = replacement
        return mutated
    raise GateUnavailable(f"node {index} vanished while mutating")


def generate(
    module: str, source: str, covered: frozenset[int]
) -> list[tuple[Mutant, str]]:
    """Return every mutant of ``source`` on a covered line, in source order."""

    tree = ast.parse(source)
    produced: list[tuple[Mutant, str]] = []
    for index, node in _numbered(tree):
        line = getattr(node, "lineno", None)
        if line is None or line not in covered:
            continue
        for operator, description, replacement in _mutations_for(node):
            if isinstance(node, ast.UnaryOp):
                mutated_tree = _remove_negation(tree, index)
            else:
                mutated_tree = _apply(tree, index, replacement)
            produced.append(
                (
                    Mutant(
                        module,
                        line,
                        getattr(node, "col_offset", 0),
                        operator,
                        description,
                    ),
                    ast.unparse(mutated_tree),
                )
            )
    produced.sort(key=lambda item: item[0].identity)
    return produced


def _remove_negation(tree: ast.AST, index: int) -> ast.AST:
    """Return a copy of ``tree`` with ``not X`` at ``index`` replaced by ``X``.

    ``ast.walk`` visits a tree and its deep copy in the same order, so the index
    identifies the same node in both.
    """

    mutated = copy.deepcopy(tree)
    nodes = [node for _, node in _numbered(mutated)]
    target = nodes[index]
    if not isinstance(target, ast.UnaryOp):  # pragma: no cover - guarded by caller
        raise GateUnavailable("the negation mutant lost its node")
    for parent in nodes:
        for field, value in ast.iter_fields(parent):
            if value is target:
                setattr(parent, field, target.operand)
            elif isinstance(value, list):
                for position, item in enumerate(value):
                    if item is target:
                        value[position] = target.operand
    return mutated


def _run(argv: Sequence[str], cwd: Path, env: dict[str, str]) -> int:
    completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
        argv,
        cwd=cwd,
        capture_output=True,
        env=env,
        check=False,
    )
    return completed.returncode


def _pytest_argv(root: Path, selection: Sequence[str]) -> list[str]:
    return [
        sys.executable,
        "-m",
        "pytest",
        "-x",
        "-q",
        "--no-header",
        "-p",
        "no:cacheprovider",
        "--no-cov",
        *[str(root / test) for test in selection],
    ]


def baseline_coverage(
    root: Path,
    targets: Sequence[str] | None = None,
    suite: str | None = None,
    package: str | None = None,
) -> dict[str, frozenset[int]]:
    """Run the whole suite once and return the lines it executes.

    Raises ``GateUnavailable`` when it does not pass, because a mutant killed by
    an already-failing suite is not evidence of anything. The baseline is the
    *suite*, not the screening set, and that distinction is load-bearing: the
    kill decision in the second stage is the suite's, so a suite already red for
    an unrelated reason would make every mutant look killed and this gate would
    print `clean`. It did, once, on 2026-08-27, while an unrelated contract test
    was failing. That is this program's own defect class committed by the gate
    written to close it, and it is why the baseline moved here.

    The declared constants are read at call time rather than bound as argument
    defaults, so what this gate measures can be pointed somewhere else without
    editing it, which is how ``tests/test_mutation_gate.py`` builds a repository
    where a mutant must survive.
    """

    targets = DECLARED_TARGETS if targets is None else targets
    suite = SUITE if suite is None else suite
    package = PACKAGE_DIR if package is None else package

    with tempfile.TemporaryDirectory() as workspace:
        data = Path(workspace) / "coverage.json"
        # The baseline imports the package the same way a mutant run does, from
        # a directory on PYTHONPATH rather than from wherever the interpreter
        # would otherwise find it, so the two runs cannot resolve to different
        # files and report a mutation that never took effect.
        env = {
            **os.environ,
            "COVERAGE_FILE": str(Path(workspace) / ".coverage"),
            "PYTHONPATH": str(root / Path(package).parent),
        }
        argv = [
            sys.executable,
            "-m",
            "coverage",
            "run",
            "--branch",
            f"--source={package}",
            "-m",
            "pytest",
            "-q",
            "--no-header",
            "-p",
            "no:cacheprovider",
            "--no-cov",
            str(root / suite),
        ]
        if _run(argv, root, env) != 0:
            raise GateUnavailable(
                "the suite does not pass against unmutated source, so nothing "
                "this gate reports about a mutant would mean anything"
            )
        # `--fail-under=0` because `[tool.coverage.report]` sets a 90% floor and
        # `coverage json` exits non-zero under it. That floor is `make test`'s
        # gate, not this one; here the report is only a list of executed lines.
        report_argv = [
            sys.executable,
            "-m",
            "coverage",
            "json",
            "--fail-under=0",
            "-o",
            str(data),
        ]
        if _run(report_argv, root, env) != 0 or not data.is_file():
            raise GateUnavailable("coverage produced no report to read")
        report = json.loads(data.read_text(encoding="utf-8"))

    covered: dict[str, frozenset[int]] = {}
    for target in targets:
        entry = report["files"].get(target)
        if entry is None:
            raise GateUnavailable(
                f"the suite never imported {target}, so there is no line for "
                "this gate to mutate"
            )
        covered[target] = frozenset(entry["executed_lines"])
        if not covered[target]:
            raise GateUnavailable(f"the suite executed no line of {target}")
    return covered


def _stage(root: Path, workspace: Path, package: str = PACKAGE_DIR) -> Path:
    """Copy the package into ``workspace`` so nothing is written to the tree."""

    source = root / package
    destination = workspace / source.name
    # `__pycache__` is excluded deliberately: a stale `.pyc` alongside a mutated
    # source would be imported instead of it, and every mutant would survive for
    # a reason that has nothing to do with the tests.
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns("__pycache__"))
    return workspace


def run_gate(
    root: Path,
    targets: Sequence[str] | None = None,
    screening: Sequence[str] | None = None,
    package: str | None = None,
    suite: str | None = None,
) -> tuple[list[Mutant], int, int]:
    """Return the survivors, the mutants run, and the lines they were drawn from."""

    targets = DECLARED_TARGETS if targets is None else targets
    screening = SCREENING_TESTS if screening is None else screening
    package = PACKAGE_DIR if package is None else package
    suite = SUITE if suite is None else suite
    covered = baseline_coverage(root, targets, suite, package)
    plans: list[tuple[Mutant, str]] = []
    for target in targets:
        source = (root / target).read_text(encoding="utf-8")
        plans.extend(generate(target, source, covered[target]))
    if not plans:
        raise GateUnavailable(
            "no mutant was generated over the declared modules, so this gate "
            "proved nothing; a run of zero mutants is not a pass"
        )

    survivors: list[Mutant] = []
    with tempfile.TemporaryDirectory() as staging:
        workspace = _stage(root, Path(staging), package)
        originals = {
            target: (root / target).read_text(encoding="utf-8") for target in targets
        }
        env = {**os.environ, "PYTHONPATH": str(workspace)}
        package_name = Path(package).name
        for mutant, mutated_source in plans:
            staged = workspace / package_name / Path(mutant.module).name
            staged.write_text(mutated_source, encoding="utf-8")
            try:
                if _run(_pytest_argv(root, screening), root, env) != 0:
                    continue
                # The screening set did not notice. Ask the whole suite before
                # reporting a survivor, so the claim is about the suite rather
                # than about the subset this gate happens to run first.
                if _run(_pytest_argv(root, (suite,)), root, env) == 0:
                    survivors.append(mutant)
            finally:
                staged.write_text(originals[mutant.module], encoding="utf-8")
    total_covered = sum(len(lines) for lines in covered.values())
    return survivors, len(plans), total_covered


def main(argv: Sequence[str] | None = None) -> int:
    """Run the gate: 0 all killed, 1 a survivor, 2 no evidence produced."""

    parser = argparse.ArgumentParser(
        prog="mutation_gate",
        description="Fail when a change to a safety module would not be noticed.",
    )
    parser.add_argument("--root", type=Path, default=None)
    args = parser.parse_args(argv)
    root = args.root.resolve() if args.root is not None else Path.cwd()

    try:
        survivors, total, covered = run_gate(root)
    except (GateUnavailable, OSError, KeyError, json.JSONDecodeError) as exc:
        print(f"mutants: {exc}.", file=sys.stderr)
        print(
            "mutants: this is a failure to produce evidence, not a clean result.",
            file=sys.stderr,
        )
        return 2

    if survivors:
        print(
            f"mutants: {len(survivors)} survivor(s) of {total} mutant(s) over "
            f"{covered} covered line(s)",
            file=sys.stderr,
        )
        for survivor in survivors:
            print(f"  survived: {survivor}", file=sys.stderr)
        return 1

    print(
        f"mutants: clean - {total} mutant(s) over {covered} covered line(s) in "
        f"{', '.join(DECLARED_TARGETS)}, every one killed by the suite"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - module entry point
    raise SystemExit(main())
