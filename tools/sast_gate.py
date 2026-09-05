#!/usr/bin/env python3
"""SAST gate: a file the scanner could not finish reading is not a clean file.

The scanner's own summary said this out loud for as long as the construct
existed, in a line nobody was reading::

    [WARN] Syntax error at line src/contextsafe/validation.py:327:
      Partially analyzed due to parsing or internal Semgrep errors

`validation.py` is a safety module. It is in the Makefile's `SAFETY_MODULES`, it
carries the 95% coverage floor, and it is the module where a fail-open would
matter most. The SAST job was green over it anyway, because a partial parse is a
warning that `--strict` turns into a failure only sometimes: the same tree went
red on a branch whose file set was larger and stayed green on `main`. A control
whose verdict depends on how many files it happened to be given is not a gate,
and "the parser stopped here and I read the rest of the module as best I could"
is exactly this repository's named defect class -- a check reporting a clean
result over content it did not examine (`docs/18-ASSURANCE-PROGRAM.md`).

So the scanner's exit code is no longer what the job reads. This program reads
the scanner's JSON, which carries the parse errors and the list of files that
were actually scanned, and applies the same three-state contract every other
gate here uses (ADR 0008): it says what it examined, it fails on a finding, and
it fails *differently* when it could not examine what it claims to. ADR 0012
records the decision and the one syntactic constraint it puts on this codebase.

What this gate examines
-----------------------

Every tracked ``.py`` file under ``src`` and ``tools`` -- the two trees
`[tool.mypy] files` and `[tool.coverage.run] source` already claim, and the two
`make scope` already holds to the tree. Each of them must appear in the
scanner's own ``paths.scanned`` list; one that does not is a finding, because a
file the scanner never opened is not a file this gate can vouch for.

``tests`` is deliberately outside that claim. The scanner's default ignore file
drops test directories before this program sees anything, so claiming them here
would produce a gate that fails on every run for a reason that is not a defect.
It is stated rather than left to be inferred from a passing run.

The three states
----------------

* **0** -- every claimed source was scanned, every scanned file parsed, and no
  rule matched. The clean line names how many files that was.
* **1** -- the scanner reported a finding. Any finding: this gate does not read
  the registry's blocking/non-blocking classification, which is the posture
  ADR 0004 chose with ``--error`` and which moves here unchanged.
* **2** -- this gate could not examine what it claims to: the scanner is not
  installed, it is not the pinned version, it exited in a way that says it did
  not complete, it wrote no report or a report in a shape this program does not
  understand, it scanned no file at all, it could not finish parsing a file, or
  a tracked source under the declared trees is missing from what it scanned
  (one deleted from the working tree is not, since nothing could read it). A
  parse error is state 2 and not state 1 on purpose. The findings from a
  partially parsed file are an incomplete set with nothing in them saying so,
  which is the same defect as a clean line over content nobody read (ADR 0008
  made the identical call for the accessibility gate's absent engine).

Usage
-----

    tools/sast_gate.py                     # run the scanner, then judge it
    tools/sast_gate.py --report PATH       # judge a report the scanner wrote
    tools/sast_gate.py --semgrep PATH --config auto --root PATH

`make sast` runs the first form. `.github/workflows/security.yml` runs this same
program rather than a second copy of the scanner's command line: the invocation
lives in `SEMGREP_ARGV` below and nowhere else.

A shared argv is only half of what makes two runs the same scan. The other half
is which scanner ran it, and a scanner's *parser* is precisely what #114 was
about: the version this repository's CI is pinned to cannot read a PEP 695
generic function, and a newer one on a maintainer's machine reads it without
complaint. Left there, `make sast` would report clean over exactly the construct
the pinned scan cannot see. So the version is pinned here too --
``PINNED_SCANNER_VERSION`` below, read back out of the report the scan writes --
and a scanner that is not it is exit 2, with ``ALLOW_SEMGREP_VERSION_DRIFT=1``
as the deliberate local override. That is how `make secret-scan` treats a
gitleaks that is not the pinned one, for the same reason.

Deliberately outside `make verify`, exactly as `make secret-scan` is: the
scanner is not in `uv.lock`, a clean clone does not have it, and resolving
`--config auto` is a network call. `make verify` stays the byte-for-byte gate
`ci.yml` runs on a clean checkout. Stdlib only, so the CI container needs
nothing but the Python the scanner itself ships with.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# The trees this gate claims. `[tool.mypy] files` and `[tool.coverage.run]
# source` name the same two, and `make scope` holds both to the tree. This tuple
# is a fourth statement of that scope and `make scope` does not read it, so
# `tests/test_sast_gate.py::test_the_gate_claims_the_trees_the_other_analyses_do`
# reads the two configurations that do make the claim and fails when this one
# stops agreeing with them -- otherwise a third tree could be adopted by mypy
# and coverage, satisfy `make scope`, and silently fall out of this gate.
SCAN_ROOTS: tuple[str, ...] = ("src", "tools")

DEFAULT_CONFIG = "auto"
"""The rule set, unchanged from ADR 0004: the registry's `auto` configuration."""

SEMGREP_BIN_ENV = "SEMGREP_BIN"
DEFAULT_SEMGREP = "semgrep"

PINNED_SCANNER_VERSION = "1.168.0"
"""The scanner whose verdict this gate reports, pinned like the secret scan's.

`.github/workflows/security.yml` pins the SAST container to this version by
digest, and this is the version whose parser stops at a PEP 695 generic function
-- the defect in #114. A newer scanner parses that construct, so a maintainer
running an unpinned `semgrep` would be told "clean" about a file the pinned CI
scan cannot finish reading, which is the same false green one layer over. The
version is read from the report the scan writes (semgrep puts it at the top
level) rather than from a second `--version` call, so what is checked is the
scanner that produced the result being judged.
`tests/test_sast_gate.py::test_the_pinned_scanner_is_the_one_the_workflow_runs`
re-derives this string from the workflow instead of trusting the copy here.
"""

VERSION_DRIFT_ENV = "ALLOW_SEMGREP_VERSION_DRIFT"
"""Set to ``1`` to run a scanner that is not the pinned one, warning and going on.

The same escape hatch, spelled the same way, as the secret scan's
``ALLOW_GITLEAKS_VERSION_DRIFT``: a maintainer with another semgrep can still
get a scan out of it, and the run says on every line what it actually ran.
"""

# The scan, in one place. `--json` and `--output` are what make the report
# readable; there is no `--error` and no `--strict`, because the exit code is no
# longer the verdict -- this program is. Adding `--metrics off` here would break
# the run rather than harden it: the registry `auto` configuration is resolved
# through the same channel and the scanner refuses the combination.
#
# `--timeout 0` removes the per-rule time limit, and it is the difference
# between a gate and a coin toss. By default a rule that runs long on a file is
# abandoned and reported as a `warn`-level Timeout error: that rule did not
# examine that file, which is precisely the state this gate refuses to call
# clean, and whether it happens depends on how loaded the machine is. Measured
# here on 2026-09-05 against the registry `auto` configuration: 16 such errors
# across 6 files with the default limit, 0 with none, and the same wall time to
# the second, because the run is dominated by fetching the rules. So the rules
# are given as long as they need and any error at all means something. A rule
# that genuinely hangs is bounded by the CI job's own `timeout-minutes`, which
# fails the job -- the right direction for this to be wrong in.
SEMGREP_ARGV: tuple[str, ...] = (
    "scan",
    "--config",
    "{config}",
    "--timeout",
    "0",
    "--json",
    "--output",
    "{report}",
)

# A completed scan. Any other code is the scanner saying it did not finish, and
# this gate does not translate that into a result about the code.
SEMGREP_COMPLETED: frozenset[int] = frozenset({0, 1})

PARTIAL_PARSE = "partial-parse"
ANALYSIS_ERROR = "analysis-error"
UNSCANNED_SOURCE = "unscanned-source"
SCANNER_FINDING = "scanner-finding"

UNAVAILABLE_RULES: frozenset[str] = frozenset(
    {PARTIAL_PARSE, ANALYSIS_ERROR, UNSCANNED_SOURCE}
)
"""Rules that name a failure to examine rather than a defect in the code."""

DEFECT_RULES: frozenset[str] = frozenset({SCANNER_FINDING})

DETAIL_WIDTH = 200
"""How much of a scanner message to echo: enough to act on, bounded."""

CLEAN, FOUND, UNAVAILABLE = 0, 1, 2


class GateUnavailable(Exception):
    """The gate could not run the scan it claims to, which is never a pass."""


@dataclass(frozen=True)
class Finding:
    """One thing the gate found, located precisely enough to act on."""

    rule_id: str
    location: str
    detail: str

    def __str__(self) -> str:
        return f"{self.rule_id}: {self.location}: {self.detail}"


def _flatten(text: str) -> str:
    """One line, bounded. Scanner messages carry newlines and a source snippet."""

    return " ".join(text.split())[:DETAIL_WIDTH]


def exit_code(findings: Sequence[Finding]) -> int:
    """0 clean, 1 for a defect, 2 when something was not examined.

    A run that has both is 2. The finding list gathered beside an unparsed file
    is incomplete and nothing in it says so, so the refusal wins -- the same
    call ADR 0008 made for an accessibility run with an absent engine.
    """

    if any(finding.rule_id in UNAVAILABLE_RULES for finding in findings):
        return UNAVAILABLE
    return FOUND if findings else CLEAN


# --- running the scanner ----------------------------------------------------


def resolve_scanner(name: str) -> str:
    """Find the scanner, or refuse. An absent scanner is not a clean scan."""

    resolved = shutil.which(name)
    if resolved is None:
        raise GateUnavailable(
            f"the scanner was not found (looked for {name!r}); install semgrep or "
            f"set {SEMGREP_BIN_ENV}, because a scan that did not run has no result"
        )
    return resolved


def run_scanner(binary: str, config: str, root: Path, report: Path) -> int:
    """Run one scan, writing its JSON to ``report``. Returns the scanner's code.

    Output is not captured: the scanner's own summary in the job log is evidence
    of what it did, and this gate's verdict comes from the report rather than
    from that text.
    """

    argv = [
        binary,
        *(part.format(config=config, report=report) for part in SEMGREP_ARGV),
    ]
    try:
        completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
            argv, cwd=root, check=False
        )
    except OSError as exc:  # pragma: no cover - resolve_scanner ran first
        raise GateUnavailable(f"the scanner could not be started: {exc}") from exc
    if completed.returncode not in SEMGREP_COMPLETED:
        raise GateUnavailable(
            f"the scanner exited {completed.returncode}, which is not a completed "
            "scan; a scan that stopped has no result to report"
        )
    return completed.returncode


# --- reading the report -----------------------------------------------------

REQUIRED_KEYS: tuple[tuple[str, type], ...] = (
    ("results", list),
    ("errors", list),
    ("paths", dict),
)


def load_report(path: Path) -> dict[str, Any]:
    """Read the scanner's JSON, refusing any shape this gate cannot judge.

    Fail closed on the report itself. A key that is missing or of another type
    would otherwise be read as an empty list -- no errors, no findings, no
    scanned files -- which is a clean verdict derived from a document this
    program did not understand.
    """

    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise GateUnavailable(
            f"the scanner's report at {path} could not be read "
            f"({type(exc).__name__}), so nothing was judged"
        ) from exc
    try:
        report = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise GateUnavailable(
            f"the scanner's report at {path} is not JSON ({exc.msg}), so nothing "
            "was judged"
        ) from exc
    if not isinstance(report, dict):
        raise GateUnavailable(
            f"the scanner's report at {path} is not a JSON object, so this gate "
            "cannot tell what was scanned"
        )
    for key, kind in REQUIRED_KEYS:
        if not isinstance(report.get(key), kind):
            raise GateUnavailable(
                f"the scanner's report at {path} carries no {key!r} "
                f"{kind.__name__}; refusing to read a report shape this gate does "
                "not understand as a clean one"
            )
    return report


def scanner_version(report: dict[str, Any], *, allow_drift: bool) -> str:
    """Return the version that produced this report, or refuse to judge it.

    A report that does not name its scanner cannot be held to the pin, and a
    report from a scanner that is not the pinned one is a scan of a different
    parser than the one CI runs -- which is the whole subject of this gate.
    Both are state 2 rather than a verdict about the code.
    """

    version = report.get("version")
    if not isinstance(version, str) or not version.strip():
        raise GateUnavailable(
            "the scanner's report does not name the version that produced it, so "
            f"this gate cannot tell whether the pinned {PINNED_SCANNER_VERSION} "
            "parser read the tree"
        )
    version = version.strip()
    if version == PINNED_SCANNER_VERSION:
        return version
    if allow_drift:
        print(
            f"sast: WARNING - semgrep {version} is not the pinned "
            f"{PINNED_SCANNER_VERSION}; continuing because {VERSION_DRIFT_ENV}=1, "
            "and this run's verdict is about that parser, not the pinned one.",
            file=sys.stderr,
        )
        return version
    raise GateUnavailable(
        f"semgrep {version} produced this report and this gate is pinned to "
        f"{PINNED_SCANNER_VERSION}, the version "
        "`.github/workflows/security.yml` runs; different parsers read different "
        f"files, so install the pinned version or set {VERSION_DRIFT_ENV}=1 to "
        "accept a verdict about a scanner CI does not run"
    )


def scanned_paths(report: dict[str, Any]) -> frozenset[str]:
    """Every file the scanner says it scanned, repository-relative."""

    scanned = report["paths"].get("scanned")
    if not isinstance(scanned, list):
        raise GateUnavailable(
            "the scanner's report does not list the files it scanned, so this "
            "gate cannot say what was examined"
        )
    paths = frozenset(str(item) for item in scanned)
    if not paths:
        raise GateUnavailable(
            "the scanner reports zero scanned files; a scan of nothing is not a "
            "clean scan"
        )
    return paths


def _error_rule(entry: dict[str, Any]) -> str:
    """Tell a parse this gate cares about most from any other analysis error.

    Both are exit 2. The distinction is for the reader: a partial parse names a
    construct this codebase can stop using (ADR 0012), and any other analysis
    error is the scanner failing to run.
    """

    kind = entry.get("type")
    if isinstance(kind, list) and kind and isinstance(kind[0], str):
        kind = kind[0]
    message = entry.get("message")
    text = f"{kind if isinstance(kind, str) else ''} "
    text += message if isinstance(message, str) else ""
    return (
        PARTIAL_PARSE
        if ("Parsing" in text or "Syntax error" in text)
        else ANALYSIS_ERROR
    )


def error_findings(report: dict[str, Any]) -> list[Finding]:
    """One finding per error the scanner reported, parse errors included.

    The scanner reports a partial parse at level ``warn`` and still exits 0.
    That is the whole defect: read here, deliberately, rather than left to a
    flag whose effect depends on how many files the run was given.
    """

    findings: list[Finding] = []
    for entry in report["errors"]:
        if not isinstance(entry, dict):
            findings.append(
                Finding(
                    ANALYSIS_ERROR,
                    "(report)",
                    "the report carries an error entry this gate cannot read, so "
                    "it cannot say the scan completed",
                )
            )
            continue
        path = entry.get("path")
        message = entry.get("message")
        findings.append(
            Finding(
                _error_rule(entry),
                str(path) if isinstance(path, str) else "(no path)",
                _flatten(message if isinstance(message, str) else repr(entry)),
            )
        )
    return findings


def result_findings(report: dict[str, Any]) -> list[Finding]:
    """One finding per rule match. Any match fails, per ADR 0004's `--error`."""

    findings: list[Finding] = []
    for entry in report["results"]:
        if not isinstance(entry, dict):
            findings.append(
                Finding(SCANNER_FINDING, "(report)", "unreadable result entry")
            )
            continue
        start = entry.get("start")
        line = start.get("line") if isinstance(start, dict) else None
        where = f"{entry.get('path')}:{line}" if line is not None else entry.get("path")
        findings.append(
            Finding(SCANNER_FINDING, str(where), _flatten(str(entry.get("check_id"))))
        )
    return findings


# --- what the gate claims was scanned ---------------------------------------


def _git(args: Sequence[str], root: Path) -> bytes:
    """Run one git command, turning every failure into ``GateUnavailable``."""

    try:
        completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
            ["git", *args],  # noqa: S607 - `git` from PATH is the project toolchain
            cwd=root,
            check=True,
            capture_output=True,
        )
    except FileNotFoundError as exc:
        raise GateUnavailable(
            "git is not on PATH, so the gate could not list the sources the scan "
            "is required to cover"
        ) from exc
    except subprocess.CalledProcessError as exc:
        detail = (
            exc.stderr.decode("utf-8", "replace").strip() or f"exit {exc.returncode}"
        )
        raise GateUnavailable(f"`git {' '.join(args)}` failed: {detail}") from exc
    return completed.stdout


def tracked_sources(root: Path) -> tuple[str, ...]:
    """Every tracked ``.py`` file under the declared trees, repository-relative.

    ``git ls-files`` reads the index, which still lists a file deleted from the
    working tree and not yet staged. The scanner walks the working tree, so
    demanding that file would fail the gate by name over something that is not
    there for anything to read -- fail-closed, but a confusing failure in the
    middle of a delete, and a denominator that counts absent files is not the
    denominator this gate claims. The set is the intersection: tracked, and
    present.
    """

    raw = _git(["ls-files", "-z", "--", *SCAN_ROOTS], root)
    listing = raw.decode("utf-8", "replace")
    sources = tuple(
        sorted(
            part
            for part in listing.split("\0")
            if part.endswith(".py") and (root / part).is_file()
        )
    )
    if not sources:
        raise GateUnavailable(
            f"git lists no tracked Python present under {', '.join(SCAN_ROOTS)} in "
            f"{root}, so this gate has nothing to hold the scan to"
        )
    return sources


def coverage_findings(sources: Sequence[str], scanned: frozenset[str]) -> list[Finding]:
    """A declared source the scanner never opened is a hole, not a clean file."""

    return [
        Finding(
            UNSCANNED_SOURCE,
            source,
            "tracked under a tree this gate claims and absent from the scanner's "
            "own list of scanned files, so nothing examined it",
        )
        for source in sources
        if source not in scanned
    ]


@dataclass(frozen=True)
class GateResult:
    """What the gate found, over how much the scanner says it read."""

    findings: list[Finding]
    scanned: int
    sources: int
    version: str


def judge(
    root: Path, report: dict[str, Any], *, allow_drift: bool = False
) -> GateResult:
    """Apply every check to one report. Raises when it cannot judge at all."""

    version = scanner_version(report, allow_drift=allow_drift)
    scanned = scanned_paths(report)
    sources = tracked_sources(root)
    findings = error_findings(report)
    findings += coverage_findings(sources, scanned)
    findings += result_findings(report)
    return GateResult(findings, len(scanned), len(sources), version)


def run_gate(
    root: Path,
    report_path: Path | None,
    binary: str,
    config: str,
    *,
    allow_drift: bool = False,
) -> GateResult:
    """Judge an existing report, or run the scanner and judge what it wrote."""

    if report_path is not None:
        return judge(root, load_report(report_path), allow_drift=allow_drift)
    scanner = resolve_scanner(binary)
    with tempfile.TemporaryDirectory(prefix="contextsafe-sast-") as workdir:
        written = Path(workdir) / "semgrep.json"
        run_scanner(scanner, config, root, written)
        if not written.is_file():
            raise GateUnavailable(
                "the scanner wrote no report, so there is nothing to judge and no "
                "evidence it scanned anything"
            )
        return judge(root, load_report(written), allow_drift=allow_drift)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the gate: 0 clean, 1 with findings, 2 when it could not examine."""

    parser = argparse.ArgumentParser(
        prog="sast_gate",
        description="Fail on a SAST finding, and fail differently on a file the "
        "scanner could not finish reading or never opened.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="repository to scan; defaults to the working directory",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="judge this JSON report instead of running the scanner",
    )
    parser.add_argument(
        "--semgrep",
        default=os.environ.get(SEMGREP_BIN_ENV, DEFAULT_SEMGREP),
        help=f"scanner executable (default: ${SEMGREP_BIN_ENV} or `semgrep`)",
    )
    parser.add_argument(
        "--config",
        default=DEFAULT_CONFIG,
        help=f"rule configuration passed to the scanner (default: {DEFAULT_CONFIG})",
    )
    parser.add_argument(
        "--allow-version-drift",
        action="store_true",
        default=os.environ.get(VERSION_DRIFT_ENV) == "1",
        help=f"judge a report from a scanner that is not the pinned "
        f"{PINNED_SCANNER_VERSION}, warning rather than refusing "
        f"(default: ${VERSION_DRIFT_ENV}=1)",
    )
    args = parser.parse_args(argv)

    try:
        result = run_gate(
            args.root.resolve(),
            args.report,
            args.semgrep,
            args.config,
            allow_drift=args.allow_version_drift,
        )
    except GateUnavailable as exc:
        print(f"sast: {exc}.", file=sys.stderr)
        print(
            "sast: this is a failure to run the gate, not a clean result.",
            file=sys.stderr,
        )
        return UNAVAILABLE

    code = exit_code(result.findings)
    if code != CLEAN:
        print(
            f"sast: {len(result.findings)} finding(s) over {result.scanned} "
            f"scanned file(s), semgrep {result.version}",
            file=sys.stderr,
        )
        for finding in sorted(result.findings, key=str):
            print(f"  {finding}", file=sys.stderr)
        if code == UNAVAILABLE:
            print(
                "sast: at least one of these says a file was not examined, which "
                "is a failure to scan and not a finding about the code.",
                file=sys.stderr,
            )
        return code

    print(
        f"sast: clean - semgrep {result.version}, {result.scanned} file(s) "
        f"scanned and fully parsed, {result.sources} tracked source(s) under "
        f"{', '.join(SCAN_ROOTS)} covered, 0 finding(s)"
    )
    return CLEAN


if __name__ == "__main__":  # pragma: no cover - module entry point
    raise SystemExit(main())
