#!/usr/bin/env python3
"""Dependency audit gate: "no advisory" and "no answer" are not the same result.

`make audit` was one line, `uv run pip-audit ...`, and pip-audit answers with two
exit codes where this repository's gates answer with three. Everything that is
not a clean audit is exit 1: a real advisory, a malformed argument, and — the
case that brought this file into existence — a PyPI request that never
completed. #74 records the observation on pull request #61 (2026-09-05):

    requests.exceptions.ConnectionError: ('Connection aborted.',
    ConnectionResetError(104, 'Connection reset by peer'))
    make: *** [Makefile:32: audit] Error 1

The same commit passed on a re-run. Nothing about the change was wrong, and
nothing in the failure said so. That is the shape ADR 0008 exists to refuse:
a gate that cannot tell "I looked and found nothing" from "I could not look"
has two states where it needs three.

So the audit stays inside `make verify` — a merge gate that cannot fail on a
real advisory is not a merge gate — and it learns the third state:

* **0** every non-editable distribution in the locked environment was audited
  and carried no advisory;
* **1** at least one carried one;
* **2** the advisory service did not answer, the report was unreadable, or the
  run audited nothing. Exit 2 fails `make verify` exactly as exit 1 does. What
  changes is that the reader can tell which failure they have, and CI's log
  says which without anybody guessing from a traceback.

What decides the state
----------------------

Not the auditor's exit code, and not a string match on its stderr. pip-audit
writes its JSON report when the audit completes and writes nothing when it does
not: the observed ConnectionError path raises out of the process with no report
on disk. So the report is the evidence, and the exit code only breaks ties:

* a report that parses, names at least one audited distribution, and lists a
  vulnerability is exit 1, whatever the auditor exited with;
* a report that parses and names at least one audited distribution with no
  vulnerability is exit 0 **only if the auditor also exited 0**. A non-zero exit
  over a clean-looking report is an unexplained disagreement, and the fail-closed
  reading of an unexplained disagreement is that nothing was established;
* anything else — no report, unparseable report, a report whose every entry was
  skipped, a report holding an entry whose ``vulns`` field is not a list — is
  exit 2. An empty ``vulns`` list is an answer; a ``vulns`` that cannot be read
  is a distribution whose advisory status was never established, and a gate
  that counted it as audited would put it behind a "clean" line.

Retries, and what they are for
------------------------------

A transient reset is retried (three attempts, doubling backoff) before the gate
answers 2, because a single dropped connection is not news and re-running the
whole gate by hand to find out is how a flake trains people to re-run gates.
Retries apply **only** to the "did not examine" state: an advisory is not
retried, since a second opinion from the same service is the same opinion.

This does not make `make verify` runnable offline. That was the other half of
#74 and it is not fixed here: an audit needs the advisory service, and a gate
that answered 0 without reaching it would be the exact lie this file is about.
Offline, `make verify` now fails at `audit` with exit 2 and a sentence saying
the advisory service was not reached, instead of a traceback and exit 1.

Usage
-----

::

    uv run python tools/audit_gate.py              # 0 clean, 1 advisory, 2 unusable
    uv run python tools/audit_gate.py --attempts 1 # no retry
    uv run python tools/audit_gate.py --auditor P  # drive it with a stand-in

``--auditor`` exists so the three states can be asserted without a network call,
the way ``GITLEAKS_BIN`` lets `tests/test_gate_exit_contract.py` drive the secret
scan without gitleaks installed. `make audit` passes no such flag.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

CACHE_DIR = REPO_ROOT / ".cache" / "pip-audit"
"""Where pip-audit keeps its HTTP cache, as `make audit` always pointed it."""

AUDITOR_ARGUMENTS: tuple[str, ...] = (
    "--skip-editable",
    "--progress-spinner",
    "off",
    "--format",
    "json",
)
"""The invariant half of the auditor's argv.

``--skip-editable`` is the pre-existing behaviour: the editable install of this
package is not a distribution any advisory service knows about. ``--format
json`` is what makes the report readable rather than a table this gate would
have to scrape.
"""

DEFAULT_ATTEMPTS = 3
DEFAULT_BACKOFF = 2.0

CLEAN, FOUND, UNAVAILABLE = 0, 1, 2

STDERR_TAIL_LINES = 20
"""How much of the auditor's own stderr to reprint when it could not answer.

Bounded rather than whole: the interesting part of a Python traceback is its
last lines, and a gate that reprints an unbounded subprocess log is a gate
nobody reads.
"""


class GateUnavailable(Exception):
    """The gate did not examine what it exists to examine.

    Exit 2, never a clean line, and never mistaken for an advisory. Every
    construction site is a state where no dependency's advisory status was
    established. ``stderr`` carries whatever the auditor said on its way out,
    because on this path that text is the only account of what went wrong.
    """

    def __init__(self, message: str, stderr: str = "") -> None:
        super().__init__(message)
        self.stderr = stderr


@dataclass(frozen=True)
class Vulnerable:
    """One audited distribution and the advisory ids reported against it."""

    package: str
    version: str
    ids: tuple[str, ...]

    def __str__(self) -> str:
        return f"{self.package} {self.version}: {', '.join(self.ids)}"


@dataclass(frozen=True)
class Report:
    """What one completed audit established, as counts and advisory ids.

    ``examined`` is the number of distributions the service answered for.
    ``skipped`` is the number it was asked about and declined to audit, which
    pip-audit records with a ``skip_reason``. A report whose every entry was
    skipped established nothing, and this gate refuses it.
    """

    examined: int
    skipped: int
    vulnerable: tuple[Vulnerable, ...]


def _advisory_ids(vulnerabilities: list[object]) -> tuple[str, ...]:
    """Every advisory id in one dependency's ``vulns`` list, in report order."""

    ids: list[str] = []
    for entry in vulnerabilities:
        if isinstance(entry, dict):
            identifier = entry.get("id")
            ids.append(identifier if isinstance(identifier, str) else "unnamed")
    return tuple(ids)


def _advisory_list(dependency: dict[str, object]) -> list[object]:
    """One audited dependency's ``vulns`` list, or a refusal.

    An empty list is an answer: the service was asked about this distribution
    and reported nothing against it. Anything that is not a list is not an
    answer -- an absent key, ``null``, a string, an object -- and the
    distribution's advisory status was therefore never established. Counting
    that as audited is the fail-open reading, and it would put an unexamined
    distribution behind a "clean" line, which is the one thing this gate exists
    to prevent.
    """

    vulnerabilities = dependency.get("vulns")
    if not isinstance(vulnerabilities, list):
        raise GateUnavailable(
            "the auditor's report holds a dependency whose advisory list cannot be read"
        )
    return vulnerabilities


def parse_report(text: str) -> Report:
    """Read one pip-audit JSON report, or refuse.

    Every refusal here is a report that cannot answer the question the gate was
    asked, which is exit 2 and not a clean audit.
    """

    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        raise GateUnavailable(f"the auditor's report is not JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise GateUnavailable("the auditor's report is not a JSON object")
    dependencies = document.get("dependencies")
    if not isinstance(dependencies, list):
        raise GateUnavailable("the auditor's report lists no dependencies")

    examined = 0
    skipped = 0
    vulnerable: list[Vulnerable] = []
    for dependency in dependencies:
        if not isinstance(dependency, dict):
            raise GateUnavailable("the auditor's report holds a malformed entry")
        if dependency.get("skip_reason") is not None:
            skipped += 1
            continue
        vulnerabilities = _advisory_list(dependency)
        examined += 1
        if not vulnerabilities:
            continue
        vulnerable.append(
            Vulnerable(
                package=str(dependency.get("name", "unnamed")),
                version=str(dependency.get("version", "unknown")),
                ids=_advisory_ids(vulnerabilities),
            )
        )
    if examined == 0:
        raise GateUnavailable(
            f"the auditor examined no distribution ({skipped} skipped), so it "
            "established nothing about any of them"
        )
    return Report(examined=examined, skipped=skipped, vulnerable=tuple(vulnerable))


def auditor_command(auditor: Path | None, output: Path) -> list[str]:
    """The argv of one audit run, writing its report to ``output``."""

    head = (
        [str(auditor)] if auditor is not None else [sys.executable, "-m", "pip_audit"]
    )
    return [
        *head,
        *AUDITOR_ARGUMENTS,
        "--cache-dir",
        str(CACHE_DIR),
        "--output",
        str(output),
    ]


def run_auditor(auditor: Path | None) -> tuple[int, str, str | None]:
    """Run the auditor once. Returns its exit code, its stderr, and its report.

    The report is ``None`` when the auditor wrote none, which is what a failed
    advisory lookup leaves behind.
    """

    with tempfile.TemporaryDirectory() as scratch:
        output = Path(scratch) / "audit.json"
        try:
            completed = subprocess.run(  # noqa: S603 - resolved argv, no shell
                auditor_command(auditor, output),
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as exc:
            raise GateUnavailable(f"the auditor could not be run: {exc}") from exc
        report = output.read_text(encoding="utf-8") if output.is_file() else None
    return completed.returncode, completed.stderr, report


def audit_once(auditor: Path | None) -> Report:
    """One audit, classified.

    Raises :class:`GateUnavailable` for every state in which the run
    established nothing about any dependency's advisory status.
    """

    code, stderr, text = run_auditor(auditor)
    if text is None:
        raise GateUnavailable(
            f"the auditor exited {code} and wrote no report, so no advisory "
            "service was reached",
            stderr,
        )
    try:
        report = parse_report(text)
    except GateUnavailable as exc:
        raise GateUnavailable(str(exc), stderr) from exc
    if report.vulnerable or code == CLEAN:
        return report
    raise GateUnavailable(
        f"the auditor exited {code} over a report naming no advisory; that "
        "disagreement is not a clean audit",
        stderr,
    )


def _print_tail(stderr: str) -> None:
    """Reprint the bounded tail of the auditor's own stderr, when it has one."""

    lines = [line for line in stderr.splitlines() if line.strip()]
    if not lines:
        return
    print("audit: the auditor said:", file=sys.stderr)
    for line in lines[-STDERR_TAIL_LINES:]:
        print(f"  {line}", file=sys.stderr)


def audit_with_retries(auditor: Path | None, attempts: int, backoff: float) -> Report:
    """Audit until one run establishes something, or the attempts run out.

    Only the "did not examine" state is retried, and the last refusal is the
    one that propagates. An advisory is an answer: asking the same service
    again does not make it a different one, so a finding never gets a retry.
    """

    for attempt in range(attempts):
        try:
            return audit_once(auditor)
        except GateUnavailable as exc:
            if attempt + 1 == attempts:
                raise
            delay = backoff * (2**attempt)
            print(
                f"audit: attempt {attempt + 1} of {attempts} established nothing "
                f"({exc}); retrying in {delay:g}s",
                file=sys.stderr,
            )
            time.sleep(delay)
    raise GateUnavailable("no attempt was made")  # pragma: no cover - attempts >= 1


def _report_findings(report: Report) -> int:
    """Print the advisories and answer 1."""

    print(
        f"audit: {len(report.vulnerable)} distribution(s) with a known advisory, "
        f"of {report.examined} audited",
        file=sys.stderr,
    )
    for entry in report.vulnerable:
        print(f"  {entry}", file=sys.stderr)
    print(
        "audit: upgrade the distribution or record why the advisory does not "
        "apply; this is a finding, not a failure to look.",
        file=sys.stderr,
    )
    return FOUND


def _refuse(failure: GateUnavailable) -> int:
    """Print the refusal and answer 2."""

    print(f"audit: {failure}.", file=sys.stderr)
    print(
        "audit: this is a failure to run the gate, not a clean result. The "
        "advisory status of every dependency is unknown, which is not the same "
        "as no advisory.",
        file=sys.stderr,
    )
    return UNAVAILABLE


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="audit_gate",
        description="Audit the locked environment against the advisory service, "
        "and answer separately when the service could not be reached.",
    )
    parser.add_argument(
        "--auditor",
        type=Path,
        default=None,
        help="the pip-audit executable to run; defaults to the one in this "
        "environment. The tests drive the gate's three states with a stand-in.",
    )
    parser.add_argument(
        "--attempts",
        type=int,
        default=DEFAULT_ATTEMPTS,
        help="how many times to try before answering 'did not examine'",
    )
    parser.add_argument(
        "--backoff",
        type=float,
        default=DEFAULT_BACKOFF,
        help="seconds before the second attempt; doubles after each",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the gate: 0 clean, 1 on an advisory, 2 when it could not examine."""

    args = _parser().parse_args(argv)
    if args.attempts < 1:
        print("audit: --attempts must be at least 1.", file=sys.stderr)
        return UNAVAILABLE

    try:
        report = audit_with_retries(args.auditor, args.attempts, args.backoff)
    except GateUnavailable as failure:
        _print_tail(failure.stderr)
        return _refuse(failure)
    if report.vulnerable:
        return _report_findings(report)
    print(
        f"audit: clean - {report.examined} distribution(s) audited against the "
        f"advisory service, {report.skipped} skipped as editable"
    )
    return CLEAN


if __name__ == "__main__":  # pragma: no cover - module entry point
    raise SystemExit(main())
