#!/usr/bin/env python3
r"""Repository hygiene gate: no unowned markers, no stray tool configuration.

Two checks, and one property that matters more than either of them: this gate
tells "I looked and found nothing" apart from "I could not look". The second is
a failure. It was not, until this file existed.

Why this replaced two shell lines
---------------------------------

`make hygiene` used to be::

    ! rg -n '(TODO|FIXME|HACK)' src tests
    ! find . -maxdepth 2 -type f \( -name 'ruff.toml' -o ... \) | grep .

Both lines report success when the tool they depend on never ran.

`rg` exits 1 when it matches nothing and 2 when it cannot run at all, including
when it is not installed, and a leading `!` maps every non-zero status to
success. Ripgrep is not in `uv.lock`, no CI step installs it, and a clean clone
does not carry it, so on any machine without it the gate passed unconditionally
over zero bytes. The `find` line has the same defect one step removed: `!`
negates the status of `grep`, the last stage of the pipe, so a `find` that
failed to run produced no output, `grep` exited 1 for an empty input, and the
negation turned that into a pass.

Measured on this repository on 2026-08-26, before the change::

    $ env PATH=/var/empty /usr/bin/make hygiene
    /bin/sh: rg: command not found
    /bin/sh: find: command not found
    EXIT=0

This gate is stdlib Python, like the publication sweep, the i18n gate, and the
built-in half of the accessibility gate, so `make verify` still needs nothing a
clean clone does not already have, and there is no undeclared binary whose
absence is indistinguishable from a clean result.

Checks
------

``marker``
    ``TODO``, ``FIXME`` or ``HACK`` in a tracked file under ``src`` or
    ``tests``. The Definition of Done bans an unowned marker in product code or
    tests; a marker is a promise with nobody's name on it, and the repository's
    answer is that the work is either done, tracked in `docs/13-BACKLOG.md`, or
    written down in an ADR.

``stray-config``
    A tracked ``ruff.toml``, ``pytest.ini``, ``mypy.ini``, ``setup.cfg``,
    ``setup.py``, ``tox.ini``, ``.flake8`` or ``requirements.txt`` within two
    path segments of the root. `pyproject.toml` and `uv.lock` are the only
    sources of tool configuration and dependency truth here; a second one makes
    a local run and a CI run disagree about what was checked.

``unreadable``
    A file git listed for scanning that could not then be read or decoded. A
    file the gate could not read is not a file the gate can vouch for, so it is
    reported rather than skipped.

What "could not look" means
---------------------------

Any of these ends the run with exit 2 and a message saying the gate did not
run, never with a clean line:

* `git` is not on PATH, or the target directory is not a git repository.
* `git ls-files` lists no tracked file under `src` or `tests`, so the marker
  scan would have examined nothing.
* `git ls-files` lists no tracked file at all, so the stray-config check would
  have examined nothing.

The clean line names how many files were read, so a pass that examined less
than it should is visible rather than indistinguishable from a real one.

Only tracked files are scanned. Only tracked files reach CI, and `git ls-files`
reads the index, so a newly `git add`-ed file counts before it is committed.

Usage
-----

    tools/hygiene_gate.py
    tools/hygiene_gate.py --root PATH

Exit 0 when clean, 1 when anything is found, 2 when the gate could not run.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

MARKERS: tuple[str, ...] = ("TODO", "FIXME", "HACK")
MARKER_PATTERN = re.compile("|".join(MARKERS))

# Where markers are banned. Kept identical to what the ripgrep line searched,
# so this change fixes the gate's failure modes without quietly widening or
# narrowing what it covers.
MARKER_ROOTS: tuple[str, ...] = ("src", "tests")

STRAY_CONFIG_NAMES: frozenset[str] = frozenset(
    {
        ".flake8",
        "mypy.ini",
        "pytest.ini",
        "requirements.txt",
        "ruff.toml",
        "setup.cfg",
        "setup.py",
        "tox.ini",
    }
)
STRAY_CONFIG_MAX_DEPTH = 2

# How much of the offending line to echo. Enough to recognise it, bounded so a
# minified or generated line cannot flood the output.
DETAIL_WIDTH = 100


class GateUnavailable(Exception):
    """The gate could not examine the repository, which is never a pass."""


@dataclass(frozen=True)
class Finding:
    """One hygiene defect, located precisely enough to fix without searching."""

    rule_id: str
    location: str
    line_number: int
    detail: str

    def __str__(self) -> str:
        where = (
            f"{self.location}:{self.line_number}" if self.line_number else self.location
        )
        return f"{self.rule_id}: {where}: {self.detail}"


def _git(args: Sequence[str], cwd: Path | None = None) -> bytes:
    """Run one git command, turning every failure into ``GateUnavailable``."""

    try:
        completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
            ["git", *args],  # noqa: S607 - `git` from PATH is the project toolchain
            cwd=cwd,
            check=True,
            capture_output=True,
        )
    except FileNotFoundError as exc:
        raise GateUnavailable(
            "git is not on PATH, so the gate could not list the files it must read"
        ) from exc
    except subprocess.CalledProcessError as exc:
        detail = (
            exc.stderr.decode("utf-8", "replace").strip() or f"exit {exc.returncode}"
        )
        raise GateUnavailable(f"`git {' '.join(args)}` failed: {detail}") from exc
    return completed.stdout


def repo_root() -> Path:
    """Return the enclosing git repository's root."""

    return Path(_git(["rev-parse", "--show-toplevel"]).decode("utf-8").strip())


def tracked_files(root: Path, pathspecs: Sequence[str] = ()) -> tuple[str, ...]:
    """Return every tracked path under ``pathspecs``, repository-relative."""

    raw = _git(["ls-files", "-z", "--", *pathspecs], cwd=root)
    try:
        listing = raw.decode("utf-8")
    except UnicodeDecodeError as exc:  # pragma: no cover - needs a non-UTF-8 path
        raise GateUnavailable(
            "a tracked path is not valid UTF-8, so the file list could not be read"
        ) from exc
    return tuple(sorted(part for part in listing.split("\0") if part))


def find_markers(location: str, text: str) -> list[Finding]:
    """Return one finding per line carrying a marker, in file order."""

    findings: list[Finding] = []
    for number, line in enumerate(text.splitlines(), start=1):
        match = MARKER_PATTERN.search(line)
        if match is None:
            continue
        findings.append(
            Finding(
                "marker",
                location,
                number,
                f"{match.group(0)}: {line.strip()[:DETAIL_WIDTH]}",
            )
        )
    return findings


def scan_markers(root: Path, files: Sequence[str]) -> tuple[list[Finding], int]:
    """Search ``files`` for markers, returning the findings and the files read."""

    findings: list[Finding] = []
    examined = 0
    for rel in files:
        try:
            text = (root / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            findings.append(
                Finding(
                    "unreadable",
                    rel,
                    0,
                    f"listed for scanning but could not be read ({type(exc).__name__}); "
                    "a file the gate could not read is not a file it can vouch for",
                )
            )
            continue
        examined += 1
        findings.extend(find_markers(rel, text))
    return findings, examined


def find_stray_configs(paths: Iterable[str]) -> list[Finding]:
    """Return a finding for every tracked second source of tool configuration."""

    findings: list[Finding] = []
    for rel in sorted(paths):
        parts = PurePosixPath(rel).parts
        if len(parts) > STRAY_CONFIG_MAX_DEPTH or parts[-1] not in STRAY_CONFIG_NAMES:
            continue
        findings.append(
            Finding(
                "stray-config",
                rel,
                0,
                "a second source of tool configuration; pyproject.toml and uv.lock "
                "are the only ones, so that a local run and a CI run cannot disagree",
            )
        )
    return findings


def run_gate(root: Path) -> tuple[list[Finding], int, int]:
    """Run both checks, returning findings, files read, and paths listed.

    Raises ``GateUnavailable`` rather than returning a clean result whenever a
    check would have examined nothing.
    """

    all_files = tracked_files(root)
    if not all_files:
        raise GateUnavailable(
            f"git lists no tracked file in {root}, so the stray-config check "
            "examined nothing, and a check of nothing is not a pass"
        )
    marker_files = tracked_files(root, MARKER_ROOTS)
    if not marker_files:
        raise GateUnavailable(
            f"git lists no tracked file under {', '.join(MARKER_ROOTS)} in {root}, "
            "so the marker scan examined nothing, and a scan of nothing is not a pass"
        )
    findings, examined = scan_markers(root, marker_files)
    findings.extend(find_stray_configs(all_files))
    return findings, examined, len(all_files)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the gate: 0 clean, 1 with findings, 2 when it could not run."""

    parser = argparse.ArgumentParser(
        prog="hygiene_gate",
        description="Fail on an unowned marker or a stray tool config, and fail "
        "louder when the gate could not examine anything.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="repository to examine; defaults to the enclosing git repository",
    )
    args = parser.parse_args(argv)

    try:
        root = args.root.resolve() if args.root is not None else repo_root()
        findings, examined, listed = run_gate(root)
    except GateUnavailable as exc:
        print(f"hygiene: {exc}.", file=sys.stderr)
        print(
            "hygiene: this is a failure to run the gate, not a clean result.",
            file=sys.stderr,
        )
        return 2

    if findings:
        print(
            f"hygiene: {len(findings)} finding(s) over {examined} file(s)",
            file=sys.stderr,
        )
        for finding in findings:
            print(f"  {finding}", file=sys.stderr)
        return 1

    print(
        f"hygiene: clean - {examined} tracked file(s) under "
        f"{', '.join(MARKER_ROOTS)} read and searched for "
        f"{'/'.join(MARKERS)}, {listed} tracked path(s) checked for stray tool config"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - module entry point
    raise SystemExit(main())
