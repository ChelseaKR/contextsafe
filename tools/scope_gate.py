#!/usr/bin/env python3
"""Scope gate: every tracked Python file is claimed by every analysis, or declared.

What this catches that the other gates cannot
---------------------------------------------

Each gate in this repository now tells "I looked and found nothing" apart from
"I could not look". None of them can tell either of those apart from "I was
never pointed at that tree in the first place".

That was not hypothetical. `tools/` held four gate implementations and a shell
script, and until 2026-08-27 it was outside the marker scan and outside the
branch-coverage floor. Both of those gates reported clean, correctly, over the
trees they had been given. Nothing in the repository was in a position to say
that a third tree of Python existed and neither gate had heard of it.

So this gate does not scan files. It compares two things:

* the trees each analysis *claims*, read from the configuration that makes the
  claim rather than from a copy of it, and
* the tracked Python files that actually exist.

A file under no claimed root is a finding. A declared exception that matches no
file is a finding, because a stale exception describes a repository that is not
this one. A claimed root that matches no file is a finding, because an analysis
pointed at a tree that is not there is an analysis whose green result covers
less than its configuration says.

Where the claims are read from
------------------------------

``marker-scan``
    ``tools.hygiene_gate.MARKER_ROOTS``, by import. The tuple the scan actually
    iterates.

``strict-typing``
    ``[tool.mypy] files`` in ``pyproject.toml``. `make typecheck` deliberately
    passes no path, because a path on the command line overrides the config and
    the claim would then live somewhere this gate is not reading.

``branch-coverage``
    ``[tool.coverage.run] source`` in ``pyproject.toml``, for the same reason:
    `make test` passes bare ``--cov``.

Reading the config is not enough on its own, because a command can still
override it. So the recipes for ``typecheck`` and ``test`` are read out of the
Makefile and checked for the arguments that would do that. A recipe this gate
cannot find, or cannot recognise, ends the run with exit 2 rather than a pass.

Declared exceptions
-------------------

An exception says a tree is deliberately outside an analysis, and why. It is
data in this file, visible in one place, and every one of them is printed on
every run, clean or not, so a reader sees the coverage that was declared away
rather than only the coverage that was achieved. There is no wildcard: an
exception names a directory prefix, and the gate reports how many files each
one is currently excusing.

Usage
-----

    tools/scope_gate.py
    tools/scope_gate.py --root PATH

Exit 0 when every file is claimed or declared, 1 on a finding, 2 when the gate
could not establish what any analysis claims.
"""

from __future__ import annotations

import argparse
import importlib.util
import shlex
import subprocess
import sys
import tomllib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

MAKEFILE = "Makefile"
PYPROJECT = "pyproject.toml"


class GateUnavailable(Exception):
    """The gate could not establish what an analysis claims, which is not a pass."""


@dataclass(frozen=True)
class DeclaredException:
    """One tree deliberately outside one analysis, and the reason it is."""

    analysis: str
    prefix: str
    reason: str


@dataclass(frozen=True)
class Analysis:
    """One file-scoped analysis and the trees it claims to examine."""

    name: str
    claim_source: str
    roots: tuple[str, ...]


@dataclass(frozen=True)
class Finding:
    """One disagreement between what is claimed and what is here."""

    rule_id: str
    subject: str
    detail: str

    def __str__(self) -> str:
        return f"{self.rule_id}: {self.subject}: {self.detail}"


DECLARED_EXCEPTIONS: tuple[DeclaredException, ...] = (
    DeclaredException(
        "strict-typing",
        "tests/",
        "the suite is not strictly typed; `mypy --strict tests` reported 127 "
        "errors in 16 files on 2026-08-27, largely pytest fixture and Hypothesis "
        "signatures. Typing it is its own change with its own review, and this "
        "line is the declaration that it has not happened",
    ),
    DeclaredException(
        "branch-coverage",
        "tests/",
        "the suite is the measuring instrument, not the measured. Coverage of "
        "the tests by the tests would be a number that cannot fall",
    ),
)
"""Trees deliberately outside an analysis. Printed on every run."""


def _git(args: Sequence[str], cwd: Path) -> bytes:
    try:
        completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
            ["git", *args],  # noqa: S607 - `git` from PATH is the project toolchain
            cwd=cwd,
            check=True,
            capture_output=True,
        )
    except FileNotFoundError as exc:
        raise GateUnavailable(
            "git is not on PATH, so the gate could not list the files to compare "
            "the claims against"
        ) from exc
    except subprocess.CalledProcessError as exc:
        detail = (
            exc.stderr.decode("utf-8", "replace").strip() or f"exit {exc.returncode}"
        )
        raise GateUnavailable(f"`git {' '.join(args)}` failed: {detail}") from exc
    return completed.stdout


def repo_root() -> Path:
    return Path(_git(["rev-parse", "--show-toplevel"], Path.cwd()).decode().strip())


def tracked_python_files(root: Path) -> tuple[str, ...]:
    listing = _git(["ls-files", "-z", "--", "*.py"], root).decode("utf-8")
    return tuple(sorted(part for part in listing.split("\0") if part))


def _read_pyproject(root: Path) -> dict[str, object]:
    path = root / PYPROJECT
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise GateUnavailable(f"{PYPROJECT} could not be read: {exc}") from exc


def _string_list(data: dict[str, object], dotted: str) -> tuple[str, ...]:
    """Return a required list-of-strings config value, or refuse to run."""

    node: object = data
    for key in dotted.split("."):
        if not isinstance(node, dict) or key not in node:
            raise GateUnavailable(
                f"{PYPROJECT} has no `{dotted}`, so the gate cannot tell what "
                "that analysis claims to examine"
            )
        node = node[key]
    if (
        not isinstance(node, list)
        or not node
        or not all(isinstance(item, str) for item in node)
    ):
        raise GateUnavailable(
            f"`{dotted}` in {PYPROJECT} is not a non-empty list of paths"
        )
    return tuple(str(item) for item in node)


def _join_and_strip(raw: Sequence[str]) -> list[str]:
    """Return real command lines: continuations joined, recipe comments dropped.

    Both halves were holes. A recipe line ending in a backslash continues on the
    next line, and the check below read only the first line that mentioned the
    tool, so `mypy \\` / `--strict src` had its argument on a line nothing read.
    And a `#` comment inside a recipe is not a command; this repository's own
    `sync` target already has one, so a comment mentioning the tool satisfied
    the check and the real invocation below it was never examined.
    """

    joined: list[str] = []
    pending = ""
    for line in raw:
        body = pending + line.rstrip()
        pending = ""
        if body.endswith("\\"):
            pending = body[:-1].rstrip() + " "
            continue
        joined.append(body)
    if pending:
        joined.append(pending)
    return [line.strip() for line in joined if line.strip() and not _is_comment(line)]


def _is_comment(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("#") or stripped.startswith("@#")


def _makefile_recipe(root: Path, target: str) -> tuple[str, ...]:
    """Return the command lines of one Makefile target, or refuse to run."""

    try:
        text = (root / MAKEFILE).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise GateUnavailable(f"{MAKEFILE} could not be read: {exc}") from exc
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if not line.startswith(f"{target}:"):
            continue
        raw: list[str] = []
        for candidate in lines[index + 1 :]:
            if candidate.startswith("\t"):
                raw.append(candidate[1:])
            elif candidate.strip():
                break
        recipe = _join_and_strip(raw)
        if not recipe:
            raise GateUnavailable(
                f"the `{target}` target in {MAKEFILE} has no command lines"
            )
        return tuple(recipe)
    raise GateUnavailable(
        f"{MAKEFILE} has no `{target}` target, so the gate cannot tell whether "
        "the command overrides the configured scope"
    )


def _load_hygiene_marker_roots(root: Path) -> tuple[str, ...]:
    """Import the marker scan and read the tuple it actually iterates."""

    path = root / "tools" / "hygiene_gate.py"
    spec = importlib.util.spec_from_file_location("_scope_hygiene_gate", path)
    if spec is None or spec.loader is None:
        raise GateUnavailable(f"{path} could not be loaded to read MARKER_ROOTS")
    module = importlib.util.module_from_spec(spec)
    # Registered before execution because the module defines dataclasses, and
    # `dataclasses` resolves annotations through `sys.modules[cls.__module__]`.
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        # Deliberately broad. This caught `(OSError, SyntaxError)`, so a
        # `ModuleNotFoundError`, a `NameError`, a `ValueError` from a bad
        # literal, or the `UnicodeDecodeError` the sibling `hygiene_gate.py`
        # guards against escaped as a traceback and exit 1 -- "examined and
        # found something" from a gate that could not read the claim at all.
        # Executing another module's top level can raise anything it likes, and
        # every one of those is the same answer: no claim was established.
        raise GateUnavailable(f"{path} could not be loaded: {exc!r}") from exc
    finally:
        sys.modules.pop(spec.name, None)
    roots = getattr(module, "MARKER_ROOTS", None)
    if not isinstance(roots, tuple) or not roots:
        raise GateUnavailable(f"{path} does not define a non-empty MARKER_ROOTS")
    return tuple(str(item) for item in roots)


def _invokes(tokens: Sequence[str], marker: str) -> int | None:
    """Return the index of the token that runs ``marker``, or None."""

    for index, token in enumerate(tokens):
        if token == marker or token.rsplit("/", 1)[-1] == marker:
            return index
    return None


def _scan_arguments(
    args: Sequence[str],
    refuse: Callable[[str], None],
    *,
    scope_options: tuple[str, ...],
    positional_overrides: bool,
) -> None:
    """Refuse on any argument that could move the analysis's scope."""

    for position, token in enumerate(args):
        if any(fragment in token for fragment in ("$(", "${", "`")):
            refuse(f"passes `{token}`, which this gate cannot expand")
        _scan_scope_option(args, position, refuse, scope_options)
        if not positional_overrides or token.startswith("-"):
            continue
        previous = args[position - 1] if position else None
        if previous is None or not previous.startswith("-"):
            refuse(
                f"passes the path `{token}`, which overrides the scope "
                "configured in pyproject.toml"
            )
        refuse(
            f"passes `{previous} {token}`, and this gate cannot tell whether "
            f"`{token}` is that option's value or a path that overrides the "
            "configured scope"
        )


def _scan_scope_option(
    args: Sequence[str],
    position: int,
    refuse: Callable[[str], None],
    scope_options: tuple[str, ...],
) -> None:
    """Refuse on a scope-carrying option, in either the `=` or the space form."""

    token = args[position]
    for option in scope_options:
        carries_next = (
            token == option
            and position + 1 < len(args)
            and not args[position + 1].startswith("-")
        )
        if carries_next:
            refuse(
                f"passes `{option} {args[position + 1]}`, which overrides the "
                "scope configured in pyproject.toml"
            )
        elif token.startswith(f"{option}="):
            refuse(
                f"passes `{token}`, which overrides the scope configured in "
                "pyproject.toml"
            )


def _assert_command_does_not_override(
    recipe: tuple[str, ...],
    target: str,
    marker: str,
    *,
    scope_options: tuple[str, ...] = (),
    positional_overrides: bool = False,
) -> None:
    """Refuse to run if a recipe passes an argument that beats the config.

    The rule used to be a list of four string literals compared to whole tokens
    on the *first* line mentioning the tool. Nine of ten realistic spellings went
    straight through: `mypy --strict src/`, `mypy --strict "src"`,
    `mypy --strict $(SRC)`, `pytest --cov src` in the space form, an argument on
    a continuation line, and a comment line above the real one. The headline
    defence of this gate was decorative.

    It is a rule about argument *shape* now, not about spellings:

    * every line that invokes the tool is examined, not the first;
    * a token that interpolates (`$(...)`, `${...}`, a backtick) is a refusal,
      because the gate genuinely cannot tell what it expands to;
    * an option in ``scope_options`` is a refusal whether it carries its value
      with `=` or as the next word;
    * where ``positional_overrides`` is set -- mypy, where any path on the
      command line beats ``[tool.mypy] files`` -- a non-flag argument is a
      refusal, and one that could be either a positional or some flag's value is
      also a refusal, because "I cannot tell" is exit 2 here.
    """

    def refuse(detail: str) -> None:
        raise GateUnavailable(
            f"the `{target}` target {detail}, so what this gate reads is not "
            "what that command examines"
        )

    invocations = 0
    for line in recipe:
        tokens = shlex.split(line, comments=True)
        index = _invokes(tokens, marker)
        if index is None:
            continue
        invocations += 1
        _scan_arguments(
            tokens[index + 1 :],
            refuse,
            scope_options=scope_options,
            positional_overrides=positional_overrides,
        )
    if invocations == 0:
        raise GateUnavailable(
            f"no line in the `{target}` target runs `{marker}`, so the gate cannot "
            "tell what that command examines"
        )


def collect_analyses(root: Path) -> tuple[Analysis, ...]:
    """Read every analysis's claim from the configuration that makes it."""

    config = _read_pyproject(root)

    typecheck = _makefile_recipe(root, "typecheck")
    # Any path on mypy's command line beats `[tool.mypy] files`, whatever it is
    # spelled like, so the rule is "no positional argument" rather than a list
    # of the paths somebody thought of.
    _assert_command_does_not_override(
        typecheck, "typecheck", "mypy", positional_overrides=True
    )
    test = _makefile_recipe(root, "test")
    # pytest's positionals select tests, which does not move the coverage
    # source; `--cov` carrying a value does, in either spelling.
    _assert_command_does_not_override(test, "test", "pytest", scope_options=("--cov",))

    return (
        Analysis(
            "marker-scan",
            "tools/hygiene_gate.py MARKER_ROOTS",
            _load_hygiene_marker_roots(root),
        ),
        Analysis(
            "strict-typing",
            f"{PYPROJECT} [tool.mypy] files",
            _string_list(config, "tool.mypy.files"),
        ),
        Analysis(
            "branch-coverage",
            f"{PYPROJECT} [tool.coverage.run] source",
            _string_list(config, "tool.coverage.run.source"),
        ),
    )


def _root_parts(root: str) -> tuple[str, ...]:
    """Return a claimed root's path segments, refusing one that has none.

    ``""``, ``"."`` and ``"./"`` all reduce to zero segments, and a zero-segment
    prefix is true of every path, so ``MARKER_ROOTS = (".",)`` made every file
    claimed and this gate printed clean over a comparison that could not fail.
    It already refuses a comparison with no files on the same reasoning; a root
    that vacuously claims all of them is the same hole from the other side.
    A claim this gate cannot make fail is not a claim it can report on.
    """

    parts = PurePosixPath(root.strip().rstrip("/")).parts
    if not parts or parts == (".",):
        raise GateUnavailable(
            f"a claimed root of {root!r} names no path segment, so it is true of "
            "every file and no file could ever fall outside it; name the trees "
            "instead of the whole checkout"
        )
    return parts


def _under(path: str, root: str) -> bool:
    root_parts = _root_parts(root)
    return PurePosixPath(path).parts[: len(root_parts)] == root_parts


def _assert_every_claim_can_fail(
    analyses: Sequence[Analysis], exceptions: Sequence[DeclaredException]
) -> None:
    """Refuse before comparing anything if a root or a prefix claims everything."""

    for analysis in analyses:
        for claimed in analysis.roots:
            _root_parts(claimed)
    for item in exceptions:
        _root_parts(item.prefix)


def check(
    analyses: Sequence[Analysis],
    files: Sequence[str],
    exceptions: Sequence[DeclaredException] = DECLARED_EXCEPTIONS,
) -> tuple[list[Finding], dict[tuple[str, str], int]]:
    """Compare every claim against the tree, returning findings and excused counts."""

    findings: list[Finding] = []
    _assert_every_claim_can_fail(analyses, exceptions)
    excused: dict[tuple[str, str], int] = {
        (item.analysis, item.prefix): 0 for item in exceptions
    }
    for analysis in analyses:
        for root in analysis.roots:
            if not any(_under(path, root) for path in files):
                findings.append(
                    Finding(
                        "empty-claim",
                        f"{analysis.name}:{root}",
                        f"claimed in {analysis.claim_source} but no tracked Python "
                        "file is under it, so the analysis covers less than its "
                        "configuration says",
                    )
                )
        for path in files:
            if any(_under(path, root) for root in analysis.roots):
                continue
            excuse = next(
                (
                    item
                    for item in exceptions
                    if item.analysis == analysis.name and _under(path, item.prefix)
                ),
                None,
            )
            if excuse is None:
                findings.append(
                    Finding(
                        "unclaimed-file",
                        f"{analysis.name}:{path}",
                        "tracked Python outside every root the analysis claims, "
                        "and outside every declared exception",
                    )
                )
                continue
            excused[(excuse.analysis, excuse.prefix)] += 1

    for item in exceptions:
        if excused[(item.analysis, item.prefix)] == 0:
            findings.append(
                Finding(
                    "stale-exception",
                    f"{item.analysis}:{item.prefix}",
                    "declared as outside this analysis, but it excuses no tracked "
                    "Python file, so it describes a repository that is not this one",
                )
            )
    return findings, excused


def main(argv: Sequence[str] | None = None) -> int:
    """Run the gate: 0 when every file is claimed, 1 on a finding, 2 on no answer."""

    parser = argparse.ArgumentParser(
        prog="scope_gate",
        description="Fail when a tracked Python file is outside an analysis that "
        "never declared it, and fail louder when the claims cannot be read.",
    )
    parser.add_argument("--root", type=Path, default=None)
    args = parser.parse_args(argv)

    try:
        root = args.root.resolve() if args.root is not None else repo_root()
        files = tracked_python_files(root)
        if not files:
            raise GateUnavailable(
                f"git lists no tracked Python file in {root}, so every claim would "
                "hold vacuously, and a comparison against nothing is not a pass"
            )
        analyses = collect_analyses(root)
        findings, excused = check(analyses, files)
    except GateUnavailable as exc:
        print(f"scope: {exc}.", file=sys.stderr)
        print(
            "scope: this is a failure to run the gate, not a clean result.",
            file=sys.stderr,
        )
        return 2

    for item in DECLARED_EXCEPTIONS:
        count = excused[(item.analysis, item.prefix)]
        print(
            f"scope: declared {item.analysis} excludes {item.prefix} "
            f"({count} file(s)): {item.reason}"
        )

    if findings:
        print(
            f"scope: {len(findings)} finding(s) over {len(files)} file(s)",
            file=sys.stderr,
        )
        for finding in findings:
            print(f"  {finding}", file=sys.stderr)
        return 1

    claims = ", ".join(
        f"{analysis.name} [{' '.join(analysis.roots)}]" for analysis in analyses
    )
    print(
        f"scope: clean - {len(files)} tracked Python file(s) checked against "
        f"{len(analyses)} analysis claim(s): {claims}"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - module entry point
    raise SystemExit(main())
