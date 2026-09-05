#!/usr/bin/env python3
"""Claims gate: the figures and lists the documents state, re-derived from the repo.

Every other gate here checks the code. This one checks the prose about the code,
because nothing did, and prose is where this repository's drift actually lived.
A sweep on 2026-08-29 found, on `main`:

- a standards table declaring Performance, Accessibility and Internationalization
  "N/A" on the grounds that no HTML ships, in a README that documents the HTML
  renderer eighty lines earlier, beside a `Makefile` whose `verify` target runs
  both `i18n` and `a11y`, and a `docs/I18N.md` that records the N/A declaration
  as superseded. The repository was running the gates it declared inapplicable;
- three different, all incomplete lists of what `make verify` runs;
- `make verify` described as a "frozen sync" in the README while the `Makefile`
  and `CONTRIBUTING.md` both explain at length that `--frozen` is the wrong flag
  and `--locked` is the right one. It was accurate until 2026-08-15 and nobody
  went back;
- an ADR index listing four of the seven ADRs on disk;
- a "Last reviewed" date naming a day the file was edited on repeatedly
  afterwards.

Each of those is a sentence that was true when written. None of them had anything
tying it to what it described, so each stayed green while the thing underneath
moved. Correcting the literals alone restarts the same clock, which is why this
file exists instead of a commit that fixes the numbers.

What a claim is here
--------------------

A claim is a fact about this repository that a document states and that this
gate can re-derive from the repository without a network call, without git
history, and without a tool a clean clone does not have. The CI checkout is
shallow, so anything needing `git log` is out of reach by construction and is
named in ``UNCOVERED`` rather than silently omitted.

Every claim fails in both directions. A stated value that no longer matches the
repository is a finding, and so is a document that stopped stating it: a regex
that quietly matches nothing is how a gate becomes decoration, and this
repository has the receipts for that failure mode in ADR 0004, ADR 0005 and
`docs/18-ASSURANCE-PROGRAM.md`.

Keep the inventory small. A gate that flags ordinary prose churn trains its
readers to ignore it, and an ignored gate is worse than none because it looks
like coverage.

Checks
------

``verify-stages``
    The `verify` target's prerequisites in the `Makefile`, against the list in
    the README quickstart and the command column of the gate table in
    `CONTRIBUTING.md`. Two documents enumerate the stages; both enumerations are
    now derived from the one place that decides them.

``adr-index``
    Every file in `docs/adr/` against the ADR links in the README. Four of seven
    were listed.

``coverage-floors``
    The two floors `make test` enforces, against every sentence that quotes
    them. A number restated in three documents and enforced in a fourth place is
    the shape of the defect `tools/check`-style gates exist to catch.

``standard-not-applicable``
    A standards row may not say "N/A" for something `make verify` gates. This is
    the headline defect above, stated as a rule: the table and the `Makefile`
    have to agree about whether a standard applies, and the `Makefile` wins.

``retired-phrase``
    A phrase a document uses to describe behavior the repository no longer has,
    conditioned on the repository still not having it. `--frozen` is the case
    that exists: the check applies only while the `Makefile` says `--locked`.

``schema-contracts``
    The number of published contracts in `schemas/`, against the count and the
    table in `schemas/README.md`.

``a11y-locale-coverage``
    `tools/a11y_gate.py`'s `DEFAULT_LOCALES` against the catalogs that ship in
    `src/contextsafe/locales/`. The README says the accessibility gate audits
    every shipped locale. `tools/i18n_gate.py` discovers its locales; the
    accessibility gate does not, so a third catalog would be translated, gated
    for parity, rendered to a reader, and never audited. Nothing would have
    reported that.

``required-note``
    A correction that has to travel with the text it corrects, checked by its
    presence. `docs/PUBLICATION-READINESS.md` prints commit names that do not
    resolve in the published repository; the note saying so is not optional
    decoration on those lines.

``iteration-status``
    The README's status line against the iterations the README documents. It
    stopped at four while the file described five.

Usage
-----

::

    uv run python tools/claims_gate.py            # 0 clean, 1 findings, 2 unusable
    uv run python tools/claims_gate.py --root DIR # examine another checkout
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

NUMBER_WORDS: dict[int, str] = {
    0: "zero",
    1: "one",
    2: "two",
    3: "three",
    4: "four",
    5: "five",
    6: "six",
    7: "seven",
    8: "eight",
    9: "nine",
    10: "ten",
    11: "eleven",
    12: "twelve",
    13: "thirteen",
    14: "fourteen",
    15: "fifteen",
    16: "sixteen",
    17: "seventeen",
    18: "eighteen",
    19: "nineteen",
    20: "twenty",
    21: "twenty-one",
    22: "twenty-two",
    23: "twenty-three",
    24: "twenty-four",
    25: "twenty-five",
    26: "twenty-six",
    27: "twenty-seven",
    28: "twenty-eight",
    29: "twenty-nine",
    30: "thirty",
}
"""The counts a document may state in words rather than in digits.

Extended past twenty on 2026-09-04, when the laboratory result family took
the published contracts to twenty-one: past the end of this table the gate
asks for the digits instead, which is a correct check and a document that
reads as if a machine wrote it. Widening the table changes nothing the gate
decides -- a wrong count is a finding either way.
"""


class GateUnavailable(Exception):
    """The gate could not examine what it exists to examine.

    Exit 2, never a clean line. A missing document is not an absent claim; it is
    an unchecked one, and the difference is the whole point of this file.
    """


@dataclass(frozen=True)
class Finding:
    """One claim that does not match the repository, named by check and document."""

    check: str
    where: str
    detail: str

    def __str__(self) -> str:
        return f"{self.check}: {self.where}: {self.detail}"


@dataclass(frozen=True)
class Uncovered:
    """A load-bearing claim this gate cannot reach, printed on every run.

    A gate that does not publish its own boundary invites the reader to assume
    the boundary is the edge of the document.
    """

    claim: str
    why: str

    def __str__(self) -> str:
        return f"{self.claim} - {self.why}"


UNCOVERED: tuple[Uncovered, ...] = (
    Uncovered(
        "whether a commit name printed in a document still serves its content",
        "two different questions, and this gate can answer neither. The CI checkout "
        "is shallow, so no commit but the tip is present locally. And whether GitHub "
        "still serves an unreachable commit is a fact about the host, not the tree: "
        "on 2026-08-29 every name in docs/PUBLICATION-READINESS.md was unreachable "
        "from any branch and every one of them still resolved over the API and the "
        "web, unauthenticated. Answering it needs a network call this gate does not "
        "make; required-note pins the dated finding instead",
    ),
    Uncovered(
        "whether a review or a declaration is current",
        "review is a fact about people and dates, not about the tree. The README's "
        "standards table carries no review date for this reason rather than a date "
        "nothing re-derives",
    ),
    Uncovered(
        "whether the GitHub repository description still matches the README",
        "the description is repository metadata, not a tracked file, and reading it "
        "needs a network call this gate does not make",
    ),
    Uncovered(
        "whether B-042 (human translation review) or B-044 (assistive-technology "
        "evaluation) has happened",
        "both need a person, and both are disclosed as not done in the README, "
        "docs/I18N.md and docs/08-ACCESSIBILITY-I18N.md",
    ),
    Uncovered(
        "the figures in docs/PUBLICATION-READINESS.md section 7",
        "they are measurements of one run at the commit that section names, correct "
        "for that run; re-running the command is the only thing that answers them",
    ),
    Uncovered(
        "whether a document's prose describes the behavior it names accurately",
        "this gate compares values and lists. A sentence that names the right stage "
        "and describes it wrongly passes every check here",
    ),
)


# --- deriving from the repository -------------------------------------------


def read(root: Path, name: str) -> str:
    """Return a tracked document's text, or fail the gate if it is not there."""

    path = root / name
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise GateUnavailable(f"cannot read {name}: {exc}") from exc


def verify_stages(root: Path) -> tuple[str, ...]:
    """The prerequisites of the `verify` target, in the order the Makefile lists."""

    makefile = read(root, "Makefile")
    match = re.search(r"^verify:[ \t]*(.*)$", makefile, re.MULTILINE)
    if match is None:
        raise GateUnavailable("the Makefile has no `verify` target to derive from")
    stages = tuple(match.group(1).split())
    if not stages:
        raise GateUnavailable("the Makefile's `verify` target has no prerequisites")
    return stages


def makefile_targets(root: Path) -> frozenset[str]:
    """Every target the Makefile defines, so a documented `make X` can be checked."""

    makefile = read(root, "Makefile")
    targets = frozenset(re.findall(r"^([a-z][a-z0-9-]*):", makefile, re.MULTILINE))
    if not targets:
        raise GateUnavailable("the Makefile defines no target to compare against")
    return targets


def coverage_floors(root: Path) -> tuple[int, int]:
    """The overall and safety-module branch-coverage floors `make test` enforces."""

    makefile = read(root, "Makefile")
    found = re.findall(r"--(?:cov-)?fail-under=([0-9]+)", makefile)
    if len(found) != 2:
        raise GateUnavailable(
            f"expected two coverage floors in the Makefile, found {len(found)}"
        )
    return int(found[0]), int(found[1])


def adr_files(root: Path) -> tuple[str, ...]:
    """Every ADR on disk, as repository-relative POSIX paths."""

    adr_dir = root / "docs" / "adr"
    if not adr_dir.is_dir():
        raise GateUnavailable("docs/adr is not a directory")
    files = tuple(sorted(p.name for p in adr_dir.glob("*.md")))
    if not files:
        raise GateUnavailable("docs/adr holds no ADR to check the index against")
    return tuple(f"docs/adr/{name}" for name in files)


def schema_contracts(root: Path) -> tuple[str, ...]:
    """Every published JSON Schema contract, by filename."""

    schema_dir = root / "schemas"
    if not schema_dir.is_dir():
        raise GateUnavailable("schemas is not a directory")
    files = tuple(sorted(p.name for p in schema_dir.glob("*.json")))
    if not files:
        raise GateUnavailable("schemas holds no contract to count")
    return files


def shipped_locales(root: Path) -> tuple[str, ...]:
    """Every locale catalog that ships inside the package."""

    catalogs = root / "src" / "contextsafe" / "locales"
    if not catalogs.is_dir():
        raise GateUnavailable("src/contextsafe/locales is not a directory")
    found = tuple(sorted(p.stem for p in catalogs.glob("*.json")))
    if not found:
        raise GateUnavailable("no locale catalog ships, so there is nothing to audit")
    return found


def a11y_default_locales(root: Path) -> tuple[str, ...]:
    """`DEFAULT_LOCALES` as `tools/a11y_gate.py` declares it.

    Read as text rather than imported: importing the accessibility gate pulls in
    the package and renders pages, and this gate reads a literal.
    """

    source = read(root, "tools/a11y_gate.py")
    match = re.search(r"^DEFAULT_LOCALES:[^=]*=\s*\(([^)]*)\)", source, re.MULTILINE)
    if match is None:
        raise GateUnavailable("tools/a11y_gate.py declares no DEFAULT_LOCALES")
    return tuple(re.findall(r'"([^"]+)"', match.group(1)))


def documented_iterations(readme: str) -> tuple[int, ...]:
    """Every iteration the README describes, by number."""

    return tuple(
        sorted({int(n) for n in re.findall(r"^Iteration ([0-9]+) ", readme, re.M)})
    )


# --- checks -----------------------------------------------------------------


def _difference(
    check: str, where: str, stated: set[str], actual: set[str]
) -> list[Finding]:
    """Report a set that should have matched, naming both directions."""

    findings: list[Finding] = []
    for missing in sorted(actual - stated):
        findings.append(Finding(check, where, f"does not state {missing!r}"))
    for extra in sorted(stated - actual):
        findings.append(Finding(check, where, f"states {extra!r}, which is not here"))
    return findings


_TABLE_ROW = re.compile(r"^\|[^|]*\|\s*`make ([a-z0-9-]+)`\s*\|", re.MULTILINE)

_OUTSIDE_VERIFY = re.compile(
    r"^(?P<count>[A-Za-z]+) gates? sit outside `make verify`", re.MULTILINE
)
"""The structural divider between the gate table and the gates outside `verify`.

The exceptions used to be a literal set in this file. A second gate moved out of
`verify` and the set did not, which is this gate's own subject: a list restated
in one place and decided in another. The document already draws the line in a
sentence, so the sentence is what gets read, and its absence is a finding rather
than a silent merge of the two tables.
"""


def _table_targets(section: str) -> set[str]:
    """Every `make <target>` in the command column of one section's tables."""

    return set(_TABLE_ROW.findall(section))


def check_verify_stages(root: Path) -> list[Finding]:
    """The README quickstart and the CONTRIBUTING table against the Makefile."""

    stages = set(verify_stages(root))
    findings: list[Finding] = []

    readme = read(root, "README.md")
    quickstart = re.search(r"^make verify\s+#\s*(.+)$", readme, re.MULTILINE)
    if quickstart is None:
        findings.append(
            Finding(
                "verify-stages",
                "README.md",
                "the quickstart no longer names the stages beside `make verify`; "
                "restate them or drop this claim from the gate rather than leaving "
                "a check that verifies nothing",
            )
        )
    else:
        stated = set(quickstart.group(1).split())
        findings += _difference("verify-stages", "README.md", stated, stages)

    contributing = read(root, "CONTRIBUTING.md")
    if not _TABLE_ROW.search(contributing):
        findings.append(
            Finding(
                "verify-stages",
                "CONTRIBUTING.md",
                "the gate table has no `make <target>` command column to compare",
            )
        )
        return findings

    divider = _OUTSIDE_VERIFY.search(contributing)
    if divider is None:
        findings.append(
            Finding(
                "verify-stages",
                "CONTRIBUTING.md",
                "the sentence that divides the gate table from the gates outside "
                "`make verify` is gone, so this check cannot tell which rows claim "
                "to be stages; it used to carry a hard-coded list of the exceptions "
                "instead, which is the drift shape this gate exists to catch",
            )
        )
        return findings

    inside = _table_targets(contributing[: divider.start()])
    outside = _table_targets(contributing[divider.start() :])
    findings += _difference("verify-stages", "CONTRIBUTING.md", inside, stages)

    targets = makefile_targets(root)
    for target in sorted(outside):
        if target not in targets:
            findings.append(
                Finding(
                    "verify-stages",
                    "CONTRIBUTING.md",
                    f"documents `make {target}`, which the Makefile has no target for",
                )
            )
        elif target in stages:
            findings.append(
                Finding(
                    "verify-stages",
                    "CONTRIBUTING.md",
                    f"lists `make {target}` as sitting outside `make verify`, which "
                    "runs it",
                )
            )
    stated_count = divider.group("count").lower()
    if NUMBER_WORDS.get(len(outside)) != stated_count:
        findings.append(
            Finding(
                "verify-stages",
                "CONTRIBUTING.md",
                f"says {stated_count} gate(s) sit outside `make verify` and then "
                f"tables {len(outside)}",
            )
        )
    return findings


def check_adr_index(root: Path) -> list[Finding]:
    """Every ADR on disk must be linked from the README."""

    on_disk = set(adr_files(root))
    readme = read(root, "README.md")
    listed = set(re.findall(r"\((docs/adr/[0-9]{4}-[a-z0-9-]+\.md)\)", readme))
    if not listed:
        return [
            Finding(
                "adr-index",
                "README.md",
                "no ADR link found, so the index this gate re-derives is gone",
            )
        ]
    return _difference("adr-index", "README.md", listed, on_disk)


COVERAGE_SENTENCES: tuple[tuple[str, str], ...] = (
    ("README.md", "{overall}% overall branch coverage and {safety}% safety-module"),
    ("CONTRIBUTING.md", "branch coverage ≥{overall}% overall, ≥{safety}% on"),
    (
        "DEFINITION_OF_DONE.md",
        "at least {overall}% overall branch coverage and {safety}% coverage",
    ),
)


def check_coverage_floors(root: Path) -> list[Finding]:
    """Every sentence quoting a coverage floor must quote the enforced one."""

    overall, safety = coverage_floors(root)
    findings: list[Finding] = []
    for name, template in COVERAGE_SENTENCES:
        expected = template.format(overall=overall, safety=safety)
        if expected not in read(root, name):
            findings.append(
                Finding(
                    "coverage-floors",
                    name,
                    f"does not state the enforced floors as {expected!r}; the "
                    "Makefile enforces "
                    f"{overall}% overall and {safety}% on the safety modules",
                )
            )
    return findings


GATED_STANDARDS: dict[str, str] = {
    "a11y": "Accessibility",
    "i18n": "Internationalization",
}


def standards_rows(readme: str) -> dict[str, str]:
    """The README's standards table, as standard name to declared state."""

    rows: dict[str, str] = {}
    for line in readme.splitlines():
        cells = [cell.strip() for cell in line.split("|")]
        if len(cells) >= 4 and cells[1] and cells[2]:
            rows.setdefault(cells[1], cells[2])
    return rows


def check_standard_not_applicable(root: Path) -> list[Finding]:
    """A standard `make verify` gates may not be declared not applicable."""

    stages = set(verify_stages(root))
    rows = standards_rows(read(root, "README.md"))
    findings: list[Finding] = []
    for stage, standard in sorted(GATED_STANDARDS.items()):
        if stage not in stages:
            continue
        state = rows.get(standard)
        if state is None:
            findings.append(
                Finding(
                    "standard-not-applicable",
                    "README.md",
                    f"the standards table has no {standard!r} row, and "
                    f"`make verify` runs `{stage}`",
                )
            )
        elif state.startswith("N/A"):
            findings.append(
                Finding(
                    "standard-not-applicable",
                    "README.md",
                    f"declares {standard} not applicable while `make verify` "
                    f"runs `{stage}`. The table and the Makefile disagree, and "
                    "the Makefile is what happens",
                )
            )
    return findings


RETIRED_PHRASES: tuple[tuple[str, str, str, str], ...] = (
    (
        "README.md",
        "frozen sync",
        "uv sync --locked",
        "`verify` syncs with `--locked`; `--frozen` installs a drifted lock and "
        "still exits 0, which is why the Makefile and CONTRIBUTING.md both say so",
    ),
    (
        "README.md",
        "frozen lockfile",
        "uv sync --locked",
        "same flag, same reason: the lockfile is locked against drift, not frozen "
        "in place",
    ),
)


def check_retired_phrase(root: Path) -> list[Finding]:
    """A phrase describing behavior the Makefile no longer has may not come back."""

    makefile = read(root, "Makefile")
    findings: list[Finding] = []
    for name, phrase, still_true, why in RETIRED_PHRASES:
        if still_true not in makefile:
            continue
        if phrase in read(root, name):
            findings.append(
                Finding(
                    "retired-phrase",
                    name,
                    f"says {phrase!r} while the Makefile says {still_true!r} - {why}",
                )
            )
    return findings


def check_schema_contracts(root: Path) -> list[Finding]:
    """The count and the table in schemas/README.md against schemas/ itself."""

    contracts = schema_contracts(root)
    doc = read(root, "schemas/README.md")
    findings: list[Finding] = []

    word = NUMBER_WORDS.get(len(contracts), str(len(contracts)))
    if f"{word} contracts" not in doc:
        findings.append(
            Finding(
                "schema-contracts",
                "schemas/README.md",
                f"does not state {word + ' contracts'!r}; schemas/ holds "
                f"{len(contracts)}",
            )
        )
    listed = set(re.findall(r"`(contextsafe-[a-z0-9.-]+\.schema\.json)`", doc))
    findings += _difference(
        "schema-contracts", "schemas/README.md", listed, set(contracts)
    )
    return findings


def check_a11y_locale_coverage(root: Path) -> list[Finding]:
    """The accessibility gate's default locales against the catalogs that ship."""

    return _difference(
        "a11y-locale-coverage",
        "tools/a11y_gate.py",
        set(a11y_default_locales(root)),
        set(shipped_locales(root)),
    )


REQUIRED_NOTES: tuple[tuple[str, str, str], ...] = (
    (
        "docs/PUBLICATION-READINESS.md",
        "Update, 2026-08-29",
        "this document prints commit names that are unreachable from any branch and "
        "that GitHub still serves by id, which keeps section 6's exposure open. The "
        "dated note saying so has to stay with them",
    ),
)


def check_required_note(root: Path) -> list[Finding]:
    """A correction that must travel with the text it corrects."""

    findings: list[Finding] = []
    for name, marker, why in REQUIRED_NOTES:
        if marker not in read(root, name):
            findings.append(
                Finding("required-note", name, f"no longer carries {marker!r} - {why}")
            )
    return findings


def check_iteration_status(root: Path) -> list[Finding]:
    """The README's status line must reach the last iteration the README describes."""

    readme = read(root, "README.md")
    iterations = documented_iterations(readme)
    if not iterations:
        raise GateUnavailable("the README describes no iteration to check against")
    latest = iterations[-1]
    if f"iteration-{latest}" not in readme:
        return [
            Finding(
                "iteration-status",
                "README.md",
                f"describes iteration {latest} but the status line stops short of "
                f"'iteration-{latest}'",
            )
        ]
    return []


CHECKS: tuple[Callable[[Path], list[Finding]], ...] = (
    check_verify_stages,
    check_adr_index,
    check_coverage_floors,
    check_standard_not_applicable,
    check_retired_phrase,
    check_schema_contracts,
    check_a11y_locale_coverage,
    check_required_note,
    check_iteration_status,
)


def run_gate(root: Path) -> list[Finding]:
    """Every check, over ``root``. Raises :class:`GateUnavailable` if it cannot look."""

    findings: list[Finding] = []
    for check in CHECKS:
        findings.extend(check(root))
    return findings


def _print_boundary() -> None:
    """Print what this gate cannot see. Always, not only when something fails."""

    print(f"claims: outside this gate ({len(UNCOVERED)}):")
    for item in UNCOVERED:
        print(f"  {item}")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the gate: 0 clean, 1 with findings, 2 when it could not examine."""

    parser = argparse.ArgumentParser(
        prog="claims_gate",
        description="Re-derive the figures and lists the documents state, and "
        "fail when a document and the repository disagree.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help="repository to examine; defaults to the enclosing checkout",
    )
    args = parser.parse_args(argv)

    try:
        findings = run_gate(args.root.resolve())
    except GateUnavailable as exc:
        print(f"claims: {exc}.", file=sys.stderr)
        print(
            "claims: this is a failure to run the gate, not a clean result.",
            file=sys.stderr,
        )
        return 2

    if findings:
        print(
            f"claims: {len(findings)} finding(s) across {len(CHECKS)} check(s)",
            file=sys.stderr,
        )
        for finding in findings:
            print(f"  {finding}", file=sys.stderr)
        print(
            "claims: correct the document, or derive the figure instead of "
            "restating it.",
            file=sys.stderr,
        )
        return 1

    print(f"claims: clean - {len(CHECKS)} check(s) re-derived from the repository")
    _print_boundary()
    return 0


if __name__ == "__main__":  # pragma: no cover - module entry point
    raise SystemExit(main())
