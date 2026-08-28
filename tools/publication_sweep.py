#!/usr/bin/env python3
"""Publication sweep: fail if anything unpublishable is in the repository.

The publication-readiness audit swept this repository by hand for references a
public reader must not see or cannot follow — a private sibling repository, an
internal hostname, a path out of somebody's home directory. A sweep run by hand
is true for exactly as long as the commit it was run against. This script is
that sweep, so that the claim keeps being true as commits land.

It runs inside ``make verify``, which means it runs in CI on every push and
pull request and again at a release tag.

What it looks for
-----------------

``personal-path``
    An absolute path out of a developer's machine — ``/Users/<name>``,
    ``/home/<name>``, ``C:\\Users\\<name>``, ``/Volumes/<name>``. These leak a
    username, tell a reader nothing reproducible, and are the usual residue of
    pasting a local command into a document.

``internal-host``
    A hostname a public reader cannot resolve or must not probe: a corporate
    suffix such as ``.internal``, ``.corp``, ``.intranet``, ``.lan``, an mDNS
    ``.local`` name, a ``vpn.`` host, or a tenant on a corporate SaaS host
    (Atlassian, Okta, SharePoint). Reserved names (``.invalid``, ``.example``,
    ``.test``, ``localhost``) are fine and are not flagged: this repository
    uses ``*.contextsafe.invalid`` deliberately, in fixtures and tests.

``cross-repo-pointer``
    A reference to another repository under this owner that is not on the
    published allowlist below. A pointer to a repository a reader cannot open
    is at best a dead end and at worst discloses that a private project exists
    and what it is called.

``escaping-relative-link``
    A relative path in a tracked file that resolves outside this repository —
    the ``../STANDARDS`` class of link. Resolved against the containing file's
    directory, so a legitimate ``../DEFINITION_OF_DONE.md`` from ``.github/``
    is correctly not flagged. This rule needs to know where the file sits, so
    it applies to tracked files only and is skipped in ``--history`` mode,
    where a blob has content but no path.

``unexaminable-source``
    A source the sweep listed and then did not read: a tracked path that is not
    a regular file, one larger than the scan bound, or one that is not valid
    UTF-8. Each of those was a bare ``continue`` until 2026-08-27, so the clean
    line counted the files the sweep managed to read — the one number that
    cannot reveal a file it failed to read. A skipped file still gets published.
    This matches the hygiene gate's ``unreadable`` rule: a file the gate could
    not read is not a file it can vouch for.

``denylist-term``
    A term from an out-of-tree denylist file. Some strings must never appear in
    this repository and must also never appear *in this script*, because this
    script is published with the repository: a former employer's name is the
    obvious case. Those live in a file outside version control, passed with
    ``--denylist`` or ``PUBLICATION_SWEEP_DENYLIST``. Matches are reported by
    rule, file, and line only — never by content — so running the sweep can
    never be the thing that publishes the term.

Exemptions
----------

One mechanism, and it is visible: put ``publication-sweep: allow`` on the same
line. Every exemption is therefore greppable, and there is no allowlist of
files that quietly exempts a whole path — including this file, whose own rule
patterns are exempted line by line.

Usage
-----

    tools/publication_sweep.py                 # tracked files in the working tree
    tools/publication_sweep.py --history       # every blob in the object database
    tools/publication_sweep.py --denylist FILE

Only tracked files are scanned, because only tracked files get published. A
brand-new file is invisible to the sweep until it is `git add`-ed, which is why
CI — where everything is tracked — is the authoritative run.

Exit 0 when clean, 1 when anything is found, 2 on a usage error or when the
sweep could not examine what it claims to cover: nothing listed at all, or an
object it enumerated and git then refused to output. A sweep of nothing is not
clean, and the clean line prints sources read over sources listed, so a pass
that covered less than it should is visible rather than indistinguishable.

A listed source that could not be read is a finding rather than a refusal,
because the sweep knows exactly which one it is and can say so; a listing that
is empty is a refusal, because there is nothing to name.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

ALLOW_MARKER = "publication-sweep: allow"

# Repositories under this owner that a public reader can actually open. A
# pointer to anything else is flagged. Add a name here only once its repository
# is public.
PUBLIC_REPOS: frozenset[str] = frozenset({"contextsafe"})

# Hostname suffixes that are reserved for documentation and testing by RFC 2606
# and RFC 6761. They resolve nowhere by design, which is the point of using
# them, so they are never findings.
RESERVED_SUFFIXES: tuple[str, ...] = (".invalid", ".example", ".test", ".localhost")

MAX_BYTES = 4_000_000


@dataclass(frozen=True)
class Rule:
    """One built-in pattern, and how to explain a match of it."""

    rule_id: str
    pattern: re.Pattern[str]
    explanation: str


@dataclass(frozen=True)
class Finding:
    """One thing that must not be published, and where it is."""

    rule_id: str
    location: str
    line_number: int
    detail: str


BUILTIN_RULES: tuple[Rule, ...] = (
    Rule(
        "personal-path",
        re.compile(  # publication-sweep: allow
            r"(?:/Users/|/home/|/Volumes/|[A-Za-z]:\\Users\\)[A-Za-z0-9._-]+"
        ),
        "an absolute path out of somebody's machine",
    ),
    Rule(
        "internal-host",
        re.compile(  # publication-sweep: allow
            r"\b(?:[A-Za-z0-9-]+\.)+(?:internal|corp|intranet|lan|local)\b"
            r"|\bvpn\.[A-Za-z0-9.-]+\b"
            r"|\b[A-Za-z0-9-]+\.(?:atlassian\.net|okta\.com|sharepoint\.com)\b"
        ),
        "a hostname a public reader cannot resolve or should not probe",
    ),
)

CROSS_REPO = re.compile(r"\bChelseaKR/([A-Za-z0-9._-]+)")
RELATIVE_LINK = re.compile(r"(?<![A-Za-z0-9._~/-])(\.\./[A-Za-z0-9._/-]+)")


@dataclass(frozen=True)
class Sources:
    """What the sweep read, and what it listed and then could not read."""

    readable: list[tuple[str, str]]
    unexaminable: list[Finding]
    listed: int


def _unexaminable(location: str, reason: str) -> Finding:
    return Finding(
        "unexaminable-source",
        location,
        0,
        f"listed for the sweep and then not read ({reason}); it is published "
        "either way, so a clean line that counted only what was read would be "
        "reporting on a different set of files than the one being published",
    )


class SweepUnavailable(Exception):
    """The sweep could not examine what it claims to cover, which is not a pass."""


def _run_git(args: Sequence[str], repo_root: Path) -> bytes:
    completed = subprocess.run(  # noqa: S603 — fixed argv, no shell, trusted binary
        ["git", *args],  # noqa: S607 — `git` from PATH is the project's own toolchain
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    return completed.stdout


def repo_root() -> Path:
    out = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],  # noqa: S607
        check=True,
        capture_output=True,
        text=True,
    )
    return Path(out.stdout.strip())


def tracked_sources(root: Path) -> Sources:
    """Read every tracked file, and name every one that could not be read."""
    listing = [raw for raw in _run_git(["ls-files", "-z"], root).split(b"\0") if raw]
    readable: list[tuple[str, str]] = []
    unexaminable: list[Finding] = []
    for raw in listing:
        rel = raw.decode("utf-8")
        path = root / rel
        if not path.is_file():
            unexaminable.append(_unexaminable(rel, "tracked but not a regular file"))
            continue
        size = path.stat().st_size
        if size > MAX_BYTES:
            unexaminable.append(
                _unexaminable(rel, f"{size} bytes, over the {MAX_BYTES}-byte bound")
            )
            continue
        try:
            readable.append((rel, path.read_text(encoding="utf-8")))
        except UnicodeDecodeError:
            unexaminable.append(_unexaminable(rel, "not valid UTF-8"))
    return Sources(readable, unexaminable, len(listing))


def history_sources(root: Path) -> Sources:
    """Read every blob in the object database, and name every one that was not.

    This includes unreachable blobs, which `git log -p --all` cannot reach and
    which remain recoverable from a published repository until they are
    garbage-collected.
    """
    listing = _run_git(
        [
            "cat-file",
            "--batch-all-objects",
            "--batch-check=%(objectname) %(objecttype)",
        ],
        root,
    ).decode("utf-8", "replace")
    readable: list[tuple[str, str]] = []
    unexaminable: list[Finding] = []
    blobs = 0
    for line in listing.splitlines():
        oid, _, otype = line.partition(" ")
        if otype != "blob":
            continue
        blobs += 1
        location = f"blob {oid[:12]}"
        try:
            blob = _run_git(["cat-file", "blob", oid], root)
        except subprocess.CalledProcessError as exc:
            # git enumerated this object and then refused to output it. That is
            # a damaged object database, not one unreadable file, so it is a
            # refusal to run rather than a finding the sweep can name and move on.
            raise SweepUnavailable(
                f"could not read blob {oid[:12]} from the object database; "
                "a sweep that skipped an object it enumerated cannot report clean"
            ) from exc
        if len(blob) > MAX_BYTES:
            unexaminable.append(
                _unexaminable(
                    location, f"{len(blob)} bytes, over the {MAX_BYTES}-byte bound"
                )
            )
            continue
        try:
            readable.append((location, blob.decode("utf-8")))
        except UnicodeDecodeError:
            unexaminable.append(_unexaminable(location, "not valid UTF-8"))
    return Sources(readable, unexaminable, blobs)


def _is_reserved(host: str) -> bool:
    return any(host.lower().endswith(suffix) for suffix in RESERVED_SUFFIXES)


def _check_builtin_rules(location: str, number: int, line: str) -> Iterator[Finding]:
    for rule in BUILTIN_RULES:
        for match in rule.pattern.finditer(line):
            text = match.group(0)
            if rule.rule_id == "internal-host" and _is_reserved(text):
                continue
            detail = f"{rule.explanation}: {text}"
            yield Finding(rule.rule_id, location, number, detail)


def _check_cross_repo(location: str, number: int, line: str) -> Iterator[Finding]:
    for match in CROSS_REPO.finditer(line):
        name = match.group(1).removesuffix(".git")
        if name in PUBLIC_REPOS:
            continue
        yield Finding(
            "cross-repo-pointer",
            location,
            number,
            f"points at a repository that is not on the public allowlist: {name}",
        )


def _check_relative_links(location: str, number: int, line: str) -> Iterator[Finding]:
    containing = PurePosixPath(location).parent
    for match in RELATIVE_LINK.finditer(line):
        target = match.group(1)
        resolved = os.path.normpath(str(containing / target))
        if not resolved.startswith(".."):
            continue
        yield Finding(
            "escaping-relative-link",
            location,
            number,
            f"resolves outside the repository, so a reader cannot follow it: {target}",
        )


def _check_denylist(
    location: str, number: int, line: str, terms: Sequence[str]
) -> Iterator[Finding]:
    lowered = line.lower()
    for term in terms:
        if term in lowered:
            yield Finding(
                "denylist-term",
                location,
                number,
                "a denylisted term (content withheld on purpose)",
            )


def scan_text(location: str, text: str, terms: Sequence[str]) -> list[Finding]:
    findings: list[Finding] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if ALLOW_MARKER in line:
            continue
        findings.extend(_check_builtin_rules(location, number, line))
        findings.extend(_check_cross_repo(location, number, line))
        findings.extend(_check_denylist(location, number, line, terms))
        if not location.startswith("blob "):
            findings.extend(_check_relative_links(location, number, line))
    return findings


def load_denylist(path: Path | None) -> list[str]:
    if path is None:
        return []
    if not path.is_file():
        raise SystemExit(f"publication-sweep: denylist not found: {path}")
    terms: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        term = raw.strip()
        if term and not term.startswith("#"):
            terms.append(term.lower())
    return terms


def sweep(sources: Iterable[tuple[str, str]], terms: Sequence[str]) -> list[Finding]:
    findings: list[Finding] = []
    for location, text in sources:
        findings.extend(scan_text(location, text, terms))
    return findings


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="publication_sweep",
        description="Fail if anything unpublishable is in the repository.",
    )
    parser.add_argument(
        "--history",
        action="store_true",
        help="also scan every blob in the object database, including unreachable ones",
    )
    parser.add_argument(
        "--denylist",
        type=Path,
        default=None,
        help="file of terms that must not appear; defaults to $PUBLICATION_SWEEP_DENYLIST",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    root = repo_root()

    denylist_path = args.denylist
    if denylist_path is None:
        from_env = os.environ.get("PUBLICATION_SWEEP_DENYLIST")
        denylist_path = Path(from_env) if from_env else None
    terms = load_denylist(denylist_path)

    scope = "tracked files"
    try:
        tracked = tracked_sources(root)
        readable = tracked.readable
        unexaminable = list(tracked.unexaminable)
        listed = tracked.listed
        if args.history:
            history = history_sources(root)
            readable = readable + history.readable
            unexaminable.extend(history.unexaminable)
            listed += history.listed
            scope = "tracked files and every blob in the object database"
        if not listed:
            raise SweepUnavailable(
                f"no source was listed in {root}, so the sweep examined nothing, "
                "and a sweep of nothing is not a clean result"
            )
        findings = unexaminable + sweep(readable, terms)
    except SweepUnavailable as exc:
        print(f"publication-sweep: {exc}.", file=sys.stderr)
        print(
            "publication-sweep: this is a failure to run the sweep, not a clean result.",
            file=sys.stderr,
        )
        return 2

    if findings:
        print(
            f"publication-sweep: {len(findings)} finding(s) over {scope}",
            file=sys.stderr,
        )
        for finding in findings:
            print(
                f"  {finding.rule_id}: {finding.location}:{finding.line_number}: {finding.detail}",
                file=sys.stderr,
            )
        print(
            "\nFix the reference, or mark the line with "
            f"`{ALLOW_MARKER}` and say in review why it is safe to publish.",
            file=sys.stderr,
        )
        if any(finding.rule_id == "unexaminable-source" for finding in findings):
            # There is no line to mark in a source the sweep could not read, so
            # the exemption mechanism is not the answer for this rule.
            print(
                "An unexaminable source has no line to mark: make it readable, "
                "raise the bound, or stop tracking it.",
                file=sys.stderr,
            )
        return 1

    denylist_note = (
        f", {len(terms)} denylisted term(s)" if terms else ", no denylist supplied"
    )
    print(
        f"publication-sweep: clean over {len(readable)} of {listed} source(s), "
        f"{scope}{denylist_note}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
