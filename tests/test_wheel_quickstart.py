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

Since B-045 the install-and-run half is ``tools/fresh_install_gate.py``, the
same gate ``.github/workflows/package.yml`` runs on Ubuntu, macOS and Windows:
``python -m venv``, ``pip install --no-index``, the Quickstart parsed from the
README, and the receipt document checked against the digest
``tests/test_determinism.py`` pins. This test builds the wheel, drives that
gate through its real subprocess runner, and then makes the two comparisons
only a checkout can make: the exported fixtures against the tree's bytes, and
the wheel's receipt payload against one produced in process.

It then runs the README's second block, the walkthrough that starts at a
synthetic FHIR Patient and ends at a rendered receipt, from the same wheel in
the same directory. That block is deliberately outside ``run_gate``:
``import`` needs descriptor-relative no-follow reads and fails closed where the
platform has none, and ``package.yml`` runs the gate on Windows. So the reader
path is proved from a wheel on the platforms ``make verify`` runs on, and the
gate keeps to the one block every platform can run.
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from contextsafe.cli import EXIT_SUCCESS, main
from contextsafe.reference_fixtures import REFERENCE_FILES, REFERENCE_ROOT

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"


def _load_gate() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "fresh_install_gate_for_wheel", ROOT / "tools" / "fresh_install_gate.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


gate = _load_gate()

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


def test_the_readme_quickstart_still_names_the_commands_this_test_runs() -> None:
    commands = gate.quickstart_commands(README.read_text(encoding="utf-8"))

    assert [argv[0] for argv in commands] == ["fixtures", "evaluate", "render"]


def test_the_readme_walkthrough_still_starts_at_a_source_file() -> None:
    """The walkthrough is the reader path, so it has to contain a reader.

    The Quickstart above evaluates observations somebody already authored,
    which is the one path that exercises no importer. If the walkthrough ever
    stops naming ``import``, the block below runs a second copy of the
    Quickstart and this file's claim to cover a reader from a wheel is false.
    """

    commands = gate.walkthrough_commands(README.read_text(encoding="utf-8"))

    assert [argv[0] for argv in commands] == [
        "fixtures",
        "import",
        "evaluate",
        "render",
    ]
    source = commands[1][commands[1].index("--source") + 1]
    assert Path(source).name in REFERENCE_FILES


def _output_of(argv: list[str]) -> str:
    """The ``--output`` operand of one quickstart command."""

    return argv[argv.index("--output") + 1]


@pytest.mark.smoke
def test_the_documented_quickstart_runs_from_an_installed_wheel(
    tmp_path: Path,
) -> None:
    uv = _uv()
    dist = tmp_path / "dist"
    workdir = tmp_path / "fresh-install"

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

    # The gate's real path: python -m venv, pip install --no-index, the
    # Quickstart from the README, the receipt document against the pin. It
    # raises, rather than reporting, for every state in which the wheel was
    # not examined, so a harness failure still reads as NOT examined.
    try:
        report = gate.run_gate(dist=dist, workdir=workdir, root=ROOT)
    except gate.GateUnavailable as exc:
        pytest.fail(f"{exc}; {NOT_EXAMINED}")
    assert report.findings == (), [str(f) for f in report.findings]
    assert report.commands_run == 3
    assert report.receipt_document_sha256 == report.pinned_receipt_document_sha256

    # The denominator: the interpreter that ran the quickstart imports the
    # wheel's package, not this checkout's. The gate checks this too; this is
    # the same fact asserted from outside it.
    venv = workdir / "venv"
    python, script = gate.venv_layout(venv)
    located = Path(
        _harness(
            [str(python), "-c", "import contextsafe; print(contextsafe.__file__)"],
            cwd=workdir / "outside",
        ).strip()
    ).resolve()
    assert located.is_relative_to(venv.resolve()), (
        f"the fresh venv imported {located}, not the installed wheel; {NOT_EXAMINED}"
    )

    # What the wheel exported is what the tree carries, byte for byte.
    outside = workdir / "outside"
    for name in REFERENCE_FILES:
        assert (outside / "fixtures" / "reference" / name).read_bytes() == (
            REFERENCE_ROOT / name
        ).read_bytes()

    # And the wheel's receipt payload is the checkout's receipt payload.
    commands = gate.quickstart_commands(README.read_text(encoding="utf-8"))
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
    assert produced["payload_sha256"] == report.payload_sha256
    rendered = (outside / _output_of(by_command["render"])).read_text(encoding="utf-8")
    assert "<html" in rendered

    # And the reader path, from the same wheel in the same directory outside
    # the checkout: a synthetic FHIR Patient through import, evaluate, and
    # render. It is not part of `run_gate`, because `import` fails closed with
    # `input_path_unsupported` where the platform has no descriptor-relative
    # no-follow read, and that gate also runs on Windows.
    walkthrough = gate.walkthrough_commands(README.read_text(encoding="utf-8"))
    for argv in walkthrough:
        completed = subprocess.run(
            [str(script), *argv],
            cwd=outside,
            env=_clean_env(),
            capture_output=True,
            text=True,
            timeout=HARNESS_TIMEOUT_SECONDS,
            check=False,
        )
        assert completed.returncode == EXIT_SUCCESS, (
            f"`contextsafe {argv[0]}` from the walkthrough exited "
            f"{completed.returncode} from the installed wheel: {completed.stderr}"
        )

    by_walkthrough = {argv[0]: argv for argv in walkthrough}
    imported = json.loads(
        (outside / _output_of(by_walkthrough["import"])).read_text(encoding="utf-8")
    )
    assert len(imported["observations"]) == 4
    assert {o["checkpoint"] for o in imported["observations"]} == {"ehr"}

    # The receipt the reader path produces is the one the README describes:
    # three passes at the EHR, and two boundaries nobody observed left
    # indeterminate rather than passed.
    reader_receipt = json.loads(
        (outside / _output_of(by_walkthrough["evaluate"])).read_text(encoding="utf-8")
    )
    summary = reader_receipt["payload"]["summary"]
    assert summary == {
        "blocked": 0,
        "fail": 0,
        "indeterminate": 2,
        "not_applicable": 0,
        "pass": 3,
    }
    assert {
        r["reason"]
        for r in reader_receipt["payload"]["results"]
        if r["status"] == "indeterminate"
    } == {"missing_evidence"}
    reader_page = (outside / _output_of(by_walkthrough["render"])).read_text(
        encoding="utf-8"
    )
    assert "<html" in reader_page
