"""The documented quickstart, run from an installed wheel outside the repository.

Every other test in this suite runs against the checkout: ``uv sync`` installs
the package in editable mode, so a file that exists in the tree is found
whether or not the wheel carries it. That is the one path no other test can
observe, and it is exactly where the reference fixtures were missing until
2026-09-02: ``uv build`` shipped ``src/contextsafe`` and its locale catalogs,
``fixtures/`` stayed a repository directory, and the README's own quickstart
failed closed with ``input_io_error`` from any install.

So this test builds the wheel, installs it into a fresh virtual environment,
and runs the README's Quickstart block -- parsed from the README itself, so
the text and the behaviour cannot drift apart silently -- from a directory that
is not the repository. It then checks the wheel's receipt against one produced
in process from the checkout, so the two paths are shown to agree.

It states its denominator, per ``docs/18-ASSURANCE-PROGRAM.md``. Every step of
the harness that cannot run -- no ``uv`` on PATH, a build or install that
fails, a README with no Quickstart to run -- fails the test with a message
that says the wheel path was **not examined**, which reads differently from
the quickstart failing. It never skips: a skipped test here would be a green
mark over the one path nobody looked at.
"""

import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from contextsafe.cli import EXIT_SUCCESS, main
from contextsafe.reference_fixtures import REFERENCE_FILES, REFERENCE_ROOT

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"

NOT_EXAMINED = "the installed-wheel path was NOT examined"
"""Marks a harness failure, so it reads differently from a quickstart failure."""

HARNESS_TIMEOUT_SECONDS = 600


def _uv() -> str:
    found = shutil.which("uv")
    if found is None:
        pytest.fail(f"uv is not on PATH; {NOT_EXAMINED}")
    return found


def _clean_env() -> dict[str, str]:
    """The environment for the build and the fresh venv: none of this checkout's.

    ``uv run`` exports the project environment to its children; left in place,
    the nested ``uv`` calls would resolve against this checkout's ``.venv`` and
    the quickstart would run the editable install this test exists to avoid.
    """

    dropped = {"VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT", "PYTHONPATH", "PYTHONHOME"}
    return {key: value for key, value in os.environ.items() if key not in dropped}


def _harness(argv: list[str], cwd: Path | None = None) -> str:
    """Run one harness step; a non-zero exit is the not-examined state."""

    result = subprocess.run(
        argv,
        cwd=cwd,
        env=_clean_env(),
        capture_output=True,
        text=True,
        timeout=HARNESS_TIMEOUT_SECONDS,
        check=False,
    )
    if result.returncode != 0:
        pytest.fail(
            f"`{' '.join(argv[:2])} ...` exited {result.returncode}; {NOT_EXAMINED}\n"
            f"{result.stderr}"
        )
    return result.stdout


def quickstart_commands(readme_text: str) -> list[list[str]]:
    """The ``contextsafe`` invocations in the README's Quickstart, as argv tails.

    Reads the first ``sh`` block under ``## Quickstart``, joins backslash
    continuations, drops ``#`` comments and the ``make`` line, and requires
    every remaining line to be ``uv run contextsafe ...``: a line this test
    cannot run from a wheel is a failure, not a silent omission.
    """

    heading = readme_text.find("\n## Quickstart\n")
    if heading < 0:
        pytest.fail(f"README.md has no `## Quickstart` section; {NOT_EXAMINED}")
    fence = "```sh\n"
    start = readme_text.find(fence, heading)
    end = readme_text.find("```", start + len(fence)) if start >= 0 else -1
    if start < 0 or end < 0:
        pytest.fail(f"README.md Quickstart has no closed ```sh block; {NOT_EXAMINED}")
    logical: list[str] = []
    pending = ""
    for line in readme_text[start + len(fence) : end].splitlines():
        stripped = line.rstrip()
        if stripped.endswith("\\"):
            pending += stripped[:-1] + " "
            continue
        logical.append(pending + stripped)
        pending = ""
    commands: list[list[str]] = []
    for text in logical:
        tokens = shlex.split(text, comments=True)
        if not tokens or tokens[0] == "make":
            continue
        if tokens[:3] != ["uv", "run", "contextsafe"]:
            pytest.fail(
                f"Quickstart line is not a `uv run contextsafe` command, so this "
                f"test cannot run it from a wheel: {text!r}"
            )
        commands.append(tokens[3:])
    if not commands:
        pytest.fail(
            f"README.md Quickstart names no contextsafe command; {NOT_EXAMINED}"
        )
    return commands


def test_quickstart_parser_reads_continuations_comments_and_the_make_line() -> None:
    text = (
        "# Title\n\n## Quickstart\n\nWith uv:\n\n```sh\n"
        "make verify   # stage list\n"
        "uv run contextsafe fixtures export   # into ./fixtures/reference\n"
        "uv run contextsafe evaluate \\\n"
        "  --case fixtures/reference/case.json \\\n"
        "  --output receipt.json           # unsigned\n"
        "```\n\nMore prose.\n"
    )

    assert quickstart_commands(text) == [
        ["fixtures", "export"],
        [
            "evaluate",
            "--case",
            "fixtures/reference/case.json",
            "--output",
            "receipt.json",
        ],
    ]


def test_the_readme_quickstart_still_names_the_commands_this_test_runs() -> None:
    commands = quickstart_commands(README.read_text(encoding="utf-8"))

    assert [argv[0] for argv in commands] == ["fixtures", "evaluate", "render"]


def _output_of(argv: list[str]) -> str:
    """The ``--output`` operand of one quickstart command."""

    return argv[argv.index("--output") + 1]


@pytest.mark.smoke
def test_the_documented_quickstart_runs_from_an_installed_wheel(
    tmp_path: Path,
) -> None:
    uv = _uv()
    dist = tmp_path / "dist"
    venv = tmp_path / "venv"
    outside = tmp_path / "outside"
    outside.mkdir()

    _harness(
        [
            uv,
            "build",
            "--wheel",
            "--out-dir",
            str(dist),
            "--python",
            sys.executable,
            str(ROOT),
        ]
    )
    wheels = sorted(dist.glob("contextsafe-*.whl"))
    if len(wheels) != 1:
        pytest.fail(f"expected one wheel, found {len(wheels)}; {NOT_EXAMINED}")
    _harness([uv, "venv", "--python", sys.executable, str(venv)])
    bin_dir = venv / ("Scripts" if os.name == "nt" else "bin")
    python = bin_dir / ("python.exe" if os.name == "nt" else "python")
    _harness([uv, "pip", "install", "--python", str(python), str(wheels[0])])

    # The denominator: the interpreter about to run the quickstart imports the
    # wheel's package, not this checkout's.
    located = Path(
        _harness(
            [str(python), "-c", "import contextsafe; print(contextsafe.__file__)"],
            cwd=outside,
        ).strip()
    ).resolve()
    assert located.is_relative_to(venv.resolve()), (
        f"the fresh venv imported {located}, not the installed wheel; {NOT_EXAMINED}"
    )

    contextsafe = bin_dir / ("contextsafe.exe" if os.name == "nt" else "contextsafe")
    commands = quickstart_commands(README.read_text(encoding="utf-8"))
    for argv in commands:
        result = subprocess.run(
            [str(contextsafe), *argv],
            cwd=outside,
            env=_clean_env(),
            capture_output=True,
            text=True,
            timeout=HARNESS_TIMEOUT_SECONDS,
            check=False,
        )
        assert result.returncode == EXIT_SUCCESS, (
            f"`contextsafe {' '.join(argv)}` exited {result.returncode} from an "
            f"installed wheel, outside the repository:\n{result.stderr}"
        )

    # What the wheel exported is what the tree carries, byte for byte.
    for name in REFERENCE_FILES:
        assert (outside / "fixtures" / "reference" / name).read_bytes() == (
            REFERENCE_ROOT / name
        ).read_bytes()

    # And the wheel's receipt payload is the checkout's receipt payload.
    by_command = {argv[0]: argv for argv in commands}
    produced = json.loads(
        (outside / _output_of(by_command["evaluate"])).read_text(encoding="utf-8")
    )
    expected_path = tmp_path / "expected.json"
    assert (
        main(
            [
                "evaluate",
                "--case",
                str(REFERENCE_ROOT / "case.json"),
                "--observations",
                str(REFERENCE_ROOT / "observations.json"),
                "--rules",
                str(REFERENCE_ROOT / "rules.json"),
                "--output",
                str(expected_path),
            ]
        )
        == EXIT_SUCCESS
    )
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    assert produced["payload"] == expected["payload"]
    rendered = (outside / _output_of(by_command["render"])).read_text(encoding="utf-8")
    assert "<html" in rendered
