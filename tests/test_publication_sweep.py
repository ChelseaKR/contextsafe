"""The publication sweep must actually fail on the things it claims to catch.

A gate nobody has watched fail is a gate nobody should trust. Every rule here
gets a positive case that must be caught and a negative case that must not be,
because both halves are load-bearing: a sweep that flags
``staging.contextsafe.invalid`` or ``../DEFINITION_OF_DONE.md`` would be turned
off within a week, and then it would be protecting nothing.

Literal offending strings appear below, so the lines carrying them are marked
with the sweep's own allow marker — which is also the exemption mechanism's
test.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SWEEP_PATH = REPO_ROOT / "tools" / "publication_sweep.py"


def _load_sweep() -> ModuleType:
    spec = importlib.util.spec_from_file_location("publication_sweep", SWEEP_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


sweep = _load_sweep()


def scan(location: str, text: str, terms: list[str] | None = None) -> list[object]:
    return sweep.scan_text(location, text, terms or [])


def rule_ids(location: str, text: str, terms: list[str] | None = None) -> list[str]:
    return [finding.rule_id for finding in scan(location, text, terms)]


# --- personal filesystem paths ---------------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        "run it from /Users/someone/code/thing",  # publication-sweep: allow
        "the log is under /home/someone/logs",  # publication-sweep: allow
        "cd C:\\Users\\someone\\project",  # publication-sweep: allow
        "mounted at /Volumes/Backup/archive",  # publication-sweep: allow
    ],
)
def test_personal_paths_are_caught(line: str) -> None:
    assert rule_ids("docs/x.md", line) == ["personal-path"]


def test_home_relative_paths_are_not_personal_paths() -> None:
    assert rule_ids("docs/x.md", 'install to "$HOME/.local/bin"') == []
    assert rule_ids("docs/x.md", "write to ~/.config/thing") == []


# --- internal hostnames -----------------------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        "reachable at build01.eng.internal",  # publication-sweep: allow
        "see wiki.acme.corp for the runbook",  # publication-sweep: allow
        "printer.office.lan is on the same subnet",  # publication-sweep: allow
        "connect through vpn.acme.com first",  # publication-sweep: allow
        "the ticket is on acme.atlassian.net",  # publication-sweep: allow
        "sign in via acme.okta.com",  # publication-sweep: allow
        "the deck lives on acme.sharepoint.com",  # publication-sweep: allow
    ],
)
def test_internal_hosts_are_caught(line: str) -> None:
    assert rule_ids("docs/x.md", line) == ["internal-host"]


@pytest.mark.parametrize(
    "line",
    [
        "target_hosts includes staging.contextsafe.invalid",
        "the fixture uses lis.contextsafe.invalid",
        "documentation uses host.example for illustration",
        "http://localhost:8000 during development",
    ],
)
def test_reserved_and_local_names_are_not_flagged(line: str) -> None:
    assert rule_ids("docs/x.md", line) == []


# --- cross-repository pointers ---------------------------------------------


def test_pointer_to_a_repository_off_the_allowlist_is_caught() -> None:
    line = "see https://github.com/ChelseaKR/some-other-project for details"  # publication-sweep: allow
    findings = scan("README.md", line)
    assert [f.rule_id for f in findings] == ["cross-repo-pointer"]
    assert "some-other-project" in findings[0].detail


def test_pointer_to_this_repository_is_fine() -> None:
    assert rule_ids("README.md", "https://github.com/ChelseaKR/contextsafe") == []


# --- relative links that escape the repository ------------------------------


def test_link_escaping_the_repository_is_caught() -> None:
    line = "inherit the portfolio standards in ../STANDARDS"
    findings = scan("README.md", line)
    assert [f.rule_id for f in findings] == ["escaping-relative-link"]


def test_relative_link_that_stays_inside_the_repository_is_fine() -> None:
    line = "see the [definition of done](../DEFINITION_OF_DONE.md)"
    assert rule_ids(".github/PULL_REQUEST_TEMPLATE.md", line) == []


def test_escaping_link_from_a_nested_file_is_caught() -> None:
    line = "compare with ../../elsewhere/notes.md"  # publication-sweep: allow
    assert rule_ids(".github/PULL_REQUEST_TEMPLATE.md", line) == [
        "escaping-relative-link"
    ]


# --- out-of-tree denylist ---------------------------------------------------


def test_denylist_term_is_caught_and_never_echoed() -> None:
    findings = scan("docs/x.md", "a note about Northwind Health", ["northwind health"])
    assert [f.rule_id for f in findings] == ["denylist-term"]
    assert "northwind" not in findings[0].detail.lower()


def test_denylist_matching_is_case_insensitive() -> None:
    assert rule_ids("docs/x.md", "NORTHWIND HEALTH", ["northwind health"]) == [
        "denylist-term"
    ]


def test_denylist_file_parsing_skips_comments_and_blanks(tmp_path: Path) -> None:
    listing = tmp_path / "denylist.txt"
    listing.write_text("# a comment\n\nOne Term\n  Another  \n", encoding="utf-8")
    assert sweep.load_denylist(listing) == ["one term", "another"]


def test_missing_denylist_file_is_a_hard_error(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        sweep.load_denylist(tmp_path / "nope.txt")


def test_no_denylist_means_no_terms() -> None:
    assert sweep.load_denylist(None) == []


# --- the exemption mechanism ------------------------------------------------


def test_allow_marker_suppresses_a_finding() -> None:
    marked = (
        f"path /Users/someone/x  # {sweep.ALLOW_MARKER}"  # publication-sweep: allow
    )
    assert scan("docs/x.md", marked) == []


# --- reporting --------------------------------------------------------------


def test_findings_carry_the_line_number() -> None:
    text = "clean line\nanother clean line\nsee build01.eng.internal\n"  # publication-sweep: allow
    findings = scan("docs/x.md", text)
    assert len(findings) == 1
    assert findings[0].line_number == 3


# --- the repository itself --------------------------------------------------


@pytest.mark.smoke
def test_this_repository_sweeps_clean() -> None:
    """The claim the audit made by hand, asserted on every test run."""
    assert sweep.main([]) == 0
