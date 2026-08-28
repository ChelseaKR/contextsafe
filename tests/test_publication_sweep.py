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
import subprocess
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


# --- sources the sweep listed and then did not read -------------------------
#
# Every one of these was a bare `continue` until 2026-08-27, inside a run that
# still printed a clean line. A skipped file is published exactly like a read
# one, so the sweep now names it instead of counting only what it managed to
# read.


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],  # noqa: S607 - `git` from PATH is the project's own toolchain
        cwd=root,
        check=True,
        capture_output=True,
    )


def _repo(root: Path, files: dict[str, bytes]) -> Path:
    """Build a tracked repository at ``root`` and return it."""

    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q")
    for rel, blob in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(blob)
        _git(root, "add", "--", rel)
    return root


CLEAN = {"README.md": b"nothing unpublishable here\n"}


def test_a_source_over_the_scan_bound_is_a_finding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sweep, "MAX_BYTES", 32)
    root = _repo(tmp_path, {**CLEAN, "big.txt": b"x" * 64})
    sources = sweep.tracked_sources(root)
    assert [f.rule_id for f in sources.unexaminable] == ["unexaminable-source"]
    assert sources.unexaminable[0].location == "big.txt"
    assert "64 bytes" in sources.unexaminable[0].detail
    assert sources.listed == 2
    assert [location for location, _ in sources.readable] == ["README.md"]


def test_a_source_that_is_not_valid_utf8_is_a_finding(tmp_path: Path) -> None:
    root = _repo(tmp_path, {**CLEAN, "binary.dat": b"\xff\xfe\x00garbage"})
    sources = sweep.tracked_sources(root)
    assert [(f.rule_id, f.location) for f in sources.unexaminable] == [
        ("unexaminable-source", "binary.dat")
    ]
    assert "not valid UTF-8" in sources.unexaminable[0].detail


def test_a_tracked_path_that_is_not_a_regular_file_is_a_finding(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path, CLEAN)
    (root / "dangling").symlink_to("nowhere")
    _git(root, "add", "--", "dangling")
    sources = sweep.tracked_sources(root)
    assert [(f.rule_id, f.location) for f in sources.unexaminable] == [
        ("unexaminable-source", "dangling")
    ]
    assert "not a regular file" in sources.unexaminable[0].detail


def test_an_unread_source_fails_the_sweep_rather_than_being_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """End to end: the old code exited 0 here and said `clean`."""

    root = _repo(tmp_path, {**CLEAN, "binary.dat": b"\xff\xfe\x00garbage"})
    monkeypatch.chdir(root)
    assert sweep.main([]) == 1
    err = capsys.readouterr().err
    assert "unexaminable-source: binary.dat" in err
    # The line-marking exemption cannot apply to a source with no readable line.
    assert "has no line to mark" in err


def test_the_clean_line_prints_what_was_read_over_what_was_listed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The count of files read cannot reveal a file that was not read."""

    monkeypatch.chdir(_repo(tmp_path, {**CLEAN, "second.md": b"also fine\n"}))
    assert sweep.main([]) == 0
    assert "clean over 2 of 2 source(s)" in capsys.readouterr().out


# --- the same accounting over the object database ---------------------------


def test_a_history_blob_over_the_scan_bound_is_a_finding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path, {**CLEAN, "big.txt": b"x" * 64})
    _git(
        root,
        "-c",
        "user.email=t@contextsafe.invalid",
        "-c",
        "user.name=t",
        "commit",
        "-q",
        "-m",
        "one",
    )
    monkeypatch.setattr(sweep, "MAX_BYTES", 32)
    sources = sweep.history_sources(root)
    assert "unexaminable-source" in {f.rule_id for f in sources.unexaminable}
    assert sources.listed >= 2


def test_a_history_blob_that_is_not_valid_utf8_is_a_finding(tmp_path: Path) -> None:
    root = _repo(tmp_path, {**CLEAN, "binary.dat": b"\xff\xfe\x00garbage"})
    _git(
        root,
        "-c",
        "user.email=t@contextsafe.invalid",
        "-c",
        "user.name=t",
        "commit",
        "-q",
        "-m",
        "one",
    )
    sources = sweep.history_sources(root)
    assert [f.rule_id for f in sources.unexaminable] == ["unexaminable-source"]
    assert "not valid UTF-8" in sources.unexaminable[0].detail


def test_a_blob_git_refuses_to_output_is_a_refusal_not_a_finding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A damaged object database is no answer, not one nameable bad file."""

    root = _repo(tmp_path, CLEAN)
    _git(
        root,
        "-c",
        "user.email=t@contextsafe.invalid",
        "-c",
        "user.name=t",
        "commit",
        "-q",
        "-m",
        "one",
    )
    real = sweep._run_git

    def refuse(args: list[str], repo_root: Path) -> bytes:
        if args[:2] == ["cat-file", "blob"]:
            raise subprocess.CalledProcessError(128, ["git", *args])
        return real(args, repo_root)

    monkeypatch.setattr(sweep, "_run_git", refuse)
    monkeypatch.chdir(root)
    assert sweep.main(["--history"]) == 2
    err = capsys.readouterr().err
    assert "could not read blob" in err
    assert "not a clean result" in err


# --- the sweep did not run: exit 2, never a pass ----------------------------


def test_a_repository_with_nothing_listed_is_a_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _git(tmp_path, "init", "-q")
    monkeypatch.chdir(tmp_path)
    assert sweep.main([]) == 2
    assert "a sweep of nothing is not a clean result" in capsys.readouterr().err


def test_the_refusal_is_a_distinct_exit_code_from_a_finding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exit 1 and exit 2 must not collapse: one is a defect, one is no answer."""

    dirty = b"see build01.eng.internal\n"  # publication-sweep: allow
    found = _repo(tmp_path / "found", {"notes.md": dirty})
    monkeypatch.chdir(found)
    assert sweep.main([]) == 1
    empty = tmp_path / "empty"
    empty.mkdir()
    _git(empty, "init", "-q")
    monkeypatch.chdir(empty)
    assert sweep.main([]) == 2


def test_a_missing_denylist_file_stops_the_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(_repo(tmp_path, CLEAN))
    with pytest.raises(SystemExit):
        sweep.main(["--denylist", str(tmp_path / "absent.txt")])


def test_the_denylist_can_come_from_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    denylist = tmp_path / "terms.txt"
    denylist.write_text("forbidden\n", encoding="utf-8")
    root = _repo(tmp_path / "repo", {"notes.md": b"a forbidden word\n"})
    monkeypatch.setenv("PUBLICATION_SWEEP_DENYLIST", str(denylist))
    monkeypatch.chdir(root)
    assert sweep.main([]) == 1
    err = capsys.readouterr().err
    assert "denylist-term" in err
    assert "forbidden" not in err


# --- the repository itself --------------------------------------------------


@pytest.mark.smoke
def test_this_repository_sweeps_clean() -> None:
    """The claim the audit made by hand, asserted on every test run."""
    assert sweep.main([]) == 0


def test_this_repository_reads_every_source_it_lists() -> None:
    """A clean line is only worth as much as its denominator."""

    sources = sweep.tracked_sources(sweep.repo_root())
    assert sources.unexaminable == []
    assert len(sources.readable) == sources.listed
