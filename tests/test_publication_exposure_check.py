"""The exposure checker's states, driven with a stand-in curl.

`tools/publication-exposure-check.sh` answers one question — is the document
`docs/PUBLICATION-READINESS.md` section 6 records still served by the host? —
and the reason it exists is that the question was once answered from a clone and
written down as closed while the content was live. A checker with that failure
mode would be worse than none, so its three states are tested here rather than
observed once by hand.

Every test drives it through a stand-in `curl` on `PATH`, so nothing in this
file reaches the network: the states that matter are the ones a live host will
not produce on demand, and a suite that needed GitHub to be reachable and
rate-limit-free would be a suite that fails for reasons unrelated to the code.

The cases with teeth are the negative ones. A 404 from the subject is also what
a private repository, a renamed owner, a deleted repository, a rate limit, and a
mistyped path all look like, so each of those is exercised and each must come
back as "could not establish", never as "gone".
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKER = REPO_ROOT / "tools" / "publication-exposure-check.sh"

# Resolved from this process's own PATH, because a test that removes `curl` from
# the child's PATH would otherwise remove the interpreter with it and fail for
# the wrong reason.
BASH = shutil.which("bash") or "/bin/bash"

CLEAN, FOUND, UNAVAILABLE, USAGE = 0, 1, 2, 64

REPO = "owner/name"
SUBJECT_REF = "subject-ref"
SUBJECT_PATH = "docs/subject.md"
CONTROL_REF = "control-ref"
CONTROL_PATH = "control.md"

# A stand-in curl. It answers a status probe (`-w`) with the code the test asked
# for, keyed by which URL it was handed, and answers the one metadata request
# with a body. It also logs every argv, so a test can assert what the checker
# asked for rather than only what it did with the answer.
STUB_CURL = """#!/usr/bin/env bash
url="${*: -1}"
printf '%s\\n' "$*" >>"$STUB_LOG"
case " $* " in
  *" -w "*) ;;
  *) printf '%s' "$STUB_METADATA"; exit 0 ;;
esac
code=""
case "$url" in
  *api.github.com*/contents/docs/subject.md*) code="$STUB_SUBJECT_API" ;;
  *api.github.com*/commits/*) code="$STUB_SUBJECT_COMMIT" ;;
  *raw.githubusercontent.com*/docs/subject.md*) code="$STUB_SUBJECT_RAW" ;;
  *//github.com/*/blob/*/docs/subject.md*) code="$STUB_SUBJECT_WEB" ;;
  *api.github.com*/contents/control.md*) code="$STUB_CONTROL_API" ;;
  *raw.githubusercontent.com*/control.md*) code="$STUB_CONTROL_RAW" ;;
  *//github.com/*/blob/*/control.md*) code="$STUB_CONTROL_WEB" ;;
esac
if [ -z "$code" ]; then
  exit 7
fi
printf '%s' "$code"
"""


def _stub_environment(
    tmp_path: Path,
    *,
    subject: str,
    commit: str,
    control: str,
    metadata: str,
    with_curl: bool,
) -> dict[str, str]:
    """A `PATH` whose `curl` is the stand-in, and the answers it will give."""

    bindir = tmp_path / "bin"
    bindir.mkdir(parents=True, exist_ok=True)
    if with_curl:
        stub = bindir / "curl"
        stub.write_text(STUB_CURL, encoding="utf-8")
        stub.chmod(0o755)
    return {
        **os.environ,
        "PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}"
        if with_curl
        else str(bindir),
        "STUB_LOG": str(tmp_path / "curl-argv.log"),
        "STUB_METADATA": metadata,
        "STUB_SUBJECT_API": subject,
        "STUB_SUBJECT_WEB": subject,
        "STUB_SUBJECT_RAW": subject,
        "STUB_SUBJECT_COMMIT": commit,
        "STUB_CONTROL_API": control,
        "STUB_CONTROL_WEB": control,
        "STUB_CONTROL_RAW": control,
    }


def _run(
    tmp_path: Path,
    *extra: str,
    subject: str = "404",
    commit: str = "404",
    control: str = "200",
    metadata: str = '{"forks_count": 3}',
    with_curl: bool = True,
    overrides: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the checker against the stand-in, with the standard subject/control."""

    environment = _stub_environment(
        tmp_path,
        subject=subject,
        commit=commit,
        control=control,
        metadata=metadata,
        with_curl=with_curl,
    )
    environment.update(overrides or {})
    return subprocess.run(
        [
            BASH,
            str(CHECKER),
            "--repo",
            REPO,
            "--ref",
            SUBJECT_REF,
            "--path",
            SUBJECT_PATH,
            "--control-ref",
            CONTROL_REF,
            "--control-path",
            CONTROL_PATH,
            *extra,
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )


def test_a_served_document_is_a_finding(tmp_path: Path) -> None:
    result = _run(tmp_path, subject="200", commit="200")
    assert result.returncode == FOUND, result.stderr
    assert "verdict:          STILL SERVED" in result.stdout
    assert "STILL SERVED" in result.stderr


def test_an_absent_document_with_served_controls_is_clean(tmp_path: Path) -> None:
    """The only shape that may read as gone: absent, and proven to be looking."""

    result = _run(tmp_path)
    assert result.returncode == CLEAN, result.stderr
    assert "verdict:          NOT SERVED" in result.stdout
    assert "does not reach" in result.stderr


def test_a_control_that_did_not_answer_is_never_a_clean_result(tmp_path: Path) -> None:
    """A private, renamed, or deleted repository 404s exactly like a purge."""

    result = _run(tmp_path, control="404")
    assert result.returncode == UNAVAILABLE, result.stdout
    assert "verdict:          INCONCLUSIVE" in result.stdout
    assert "positive control" in result.stderr


def test_a_commit_that_outlived_the_path_is_not_a_clean_result(tmp_path: Path) -> None:
    """The mistyped path: three 404s from a repository serving everything else."""

    result = _run(tmp_path, commit="200")
    assert result.returncode == UNAVAILABLE, result.stdout
    assert "the commit still resolves while the path does not" in result.stderr


@pytest.mark.parametrize("code", ["403", "429", "500", "000", "301"])
def test_a_status_it_will_not_classify_is_not_absence(
    tmp_path: Path, code: str
) -> None:
    """A rate limit, an outage, and a redirect are each "no answer", not "gone"."""

    result = _run(tmp_path, overrides={"STUB_SUBJECT_API": code})
    assert result.returncode == UNAVAILABLE, result.stdout
    assert f"subject_api:      {code}" in result.stdout
    assert "(unknown)" in result.stdout


def test_a_served_surface_outranks_every_other_confusion(tmp_path: Path) -> None:
    """One 200 settles it: nothing later in the run talks the verdict back down."""

    result = _run(tmp_path, subject="200", commit="200", control="500")
    assert result.returncode == FOUND, result.stdout
    assert "verdict:          STILL SERVED" in result.stdout


def test_no_probe_at_all_is_not_a_clean_result(tmp_path: Path) -> None:
    """The failure most easily mistaken for a clean one."""

    result = _run(tmp_path, with_curl=False)
    assert result.returncode == UNAVAILABLE
    assert "curl not found" in result.stderr
    assert "not evidence the content is gone" in result.stderr


def test_the_probe_never_asks_for_a_response_body(tmp_path: Path) -> None:
    """Running the checker may not be the thing that copies the content."""

    _run(tmp_path)
    argv = (tmp_path / "curl-argv.log").read_text(encoding="utf-8").splitlines()
    status_probes = [line for line in argv if " -w " in f" {line} "]
    assert len(status_probes) == 7
    for line in status_probes:
        assert "-o /dev/null" in line
        assert " -L" not in f" {line} "


def test_the_record_is_dated_and_appends(tmp_path: Path) -> None:
    """An answer nobody can date is the answer that went wrong last time."""

    record = tmp_path / "record.txt"
    first = _run(tmp_path, "--output", str(record))
    assert first.returncode == CLEAN, first.stderr
    _run(tmp_path, "--output", str(record), subject="200", commit="200")
    written = record.read_text(encoding="utf-8")
    assert written.count("checked_at_utc:") == 2
    assert "NOT SERVED" in written
    assert "STILL SERVED" in written
    assert SUBJECT_REF in written
    assert SUBJECT_PATH in written


def test_a_record_that_could_not_be_written_is_not_a_result(tmp_path: Path) -> None:
    unwritable = tmp_path / "no-such-directory" / "record.txt"
    result = _run(tmp_path, "--output", str(unwritable))
    assert result.returncode == UNAVAILABLE
    assert "nothing here is citable" in result.stderr


def test_the_fork_count_is_reported_and_never_decides(tmp_path: Path) -> None:
    """The half neither option can reach, counted but never in the verdict."""

    served = _run(tmp_path)
    assert "forks_count:      3" in served.stdout
    assert served.returncode == CLEAN

    silent = _run(tmp_path, metadata="")
    assert "forks_count:      unknown" in silent.stdout
    assert silent.returncode == CLEAN


@pytest.mark.parametrize(
    "argv",
    [
        ["--path", SUBJECT_PATH],
        ["--ref", SUBJECT_REF],
        ["--ref", SUBJECT_REF, "--path", SUBJECT_PATH, "--repo", "not-owner-name"],
        ["--ref", SUBJECT_REF, "--path", SUBJECT_PATH, "--nonsense"],
        ["--ref"],
    ],
)
def test_a_usage_error_is_its_own_exit_code(tmp_path: Path, argv: list[str]) -> None:
    """64 is not 2: "you asked wrongly" is not "the host would not say"."""

    environment = _stub_environment(
        tmp_path,
        subject="404",
        commit="404",
        control="200",
        metadata="",
        with_curl=True,
    )
    result = subprocess.run(
        [BASH, str(CHECKER), "--repo", REPO, *argv],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )
    assert result.returncode == USAGE, result.stdout


def test_the_ref_and_path_have_no_defaults(tmp_path: Path) -> None:
    """The checker adds no second pointer to what the audit already prints."""

    source = CHECKER.read_text(encoding="utf-8")
    assert 'ref=""' in source
    assert 'path=""' in source
    assert "11-GTM" not in source
