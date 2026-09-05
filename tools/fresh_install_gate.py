#!/usr/bin/env python3
"""Fresh-install gate: the built wheel, installed with pip, run from outside.

`make verify` runs every test against the checkout, where an editable install
finds a file in the tree whether or not the wheel carries it. That is the path
nobody looked at until 2026-09-02, and it is where the reference fixtures were
missing from the wheel while every test stayed green.
`tests/test_wheel_quickstart.py` closed that gap for one platform, from inside
the test suite, with `uv`. This gate is the same question asked the way a
customer asks it and the way RG-15 words it: the artifact a release would ship,
installed with `pip` into an empty virtual environment on a machine that has
nothing else of this repository, run from a directory that is not the
checkout, producing the receipt the repository already pins.

What it examines
----------------

1. Exactly one wheel under ``--dist``. Two is not "pick the newest"; it is exit
   2, because a gate that chose would be reporting on an artifact nobody named.
2. ``python -m venv --clear`` creates an empty environment inside a working
   directory that did not exist before the gate ran; one that did is exit 2,
   because a kept environment would install nothing and report the new wheel's
   name over an old install. ``pip`` must be present in it; a venv without pip
   is a machine this gate cannot examine, not a finding about the wheel.
3. ``pip install --no-index --force-reinstall <wheel>``. ``--no-index`` is the
   claim ``[project] dependencies = []`` makes, enforced: a wheel that needs
   anything from an index fails to install here, and that is a finding, not a
   harness error, because the artifact was examined and found wanting.
   ``--force-reinstall`` is the second guard under step 2's first.
4. The interpreter in that environment imports ``contextsafe`` from inside the
   environment, not from this checkout. Without this, ``PYTHONPATH`` or a
   ``.pth`` file could turn the whole gate into a test of the tree.
5. Every ``contextsafe`` command in the README's Quickstart block, parsed from
   the README itself so the text and the behaviour cannot drift apart, run from
   the outside directory with the installed console script.
6. The SHA-256 of the receipt document ``evaluate`` wrote, against the digest
   ``tests/test_determinism.py`` pins - read from that file, so there is one
   copy of the constant and this gate cannot agree with a stale one.

What it reports
---------------

Hashes, statuses, counts and closed-vocabulary codes. The report carries the
wheel's filename and digest, the receipt document digest, the pinned digest,
the payload digest, the number of commands run, and the platform. It carries no
path: not the working directory, not the checkout, not the venv. A rejection
names a check and a location, never content, and the stderr of a failed
command is reduced to its exit code and, where it is the tool's own JSON error
object, the closed-vocabulary error code.

Three exit codes, like every gate here (ADR 0008): ``0`` the wheel was
installed, run, and matched; ``1`` it was examined and something is wrong with
it; ``2`` the gate could not examine it, which is never a pass.

Scope
-----

This is the packaging and fresh-install evidence CI can produce (B-045). It
runs on GitHub's server images through `.github/workflows/package.yml`, not on
the Windows 11 and macOS desktop fresh installs RG-15 names, and it says
nothing about signatures: the artifact it examines is unsigned, and the build
provenance the workflow attaches beside it is not the B-035 signing path.

Usage
-----

::

    uv run python tools/fresh_install_gate.py --dist dist
    uv run python tools/fresh_install_gate.py --dist dist --workdir DIR --json out.json
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import shlex
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

README = "README.md"
"""The document whose Quickstart block is the set of commands to run."""

PIN_SOURCE = "tests/test_determinism.py"
PIN_NAME = "RECEIPT_DOCUMENT_SHA256"
"""Where the reference receipt digest lives, and the one name it lives under."""

QUICKSTART_HEADING = "\n## Quickstart\n"
QUICKSTART_PREFIX = ("uv", "run", "contextsafe")

COMMAND_TIMEOUT_SECONDS = 600

_DROPPED_ENVIRONMENT = frozenset(
    {"VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT", "PYTHONPATH", "PYTHONHOME"}
)
"""What `uv run` exports to its children, and what would point them at the tree.

Left in place, the fresh environment would resolve imports against this
checkout's ``.venv`` and the gate would examine the editable install it exists
to avoid.
"""


class GateUnavailable(Exception):
    """The gate could not examine the wheel. Exit 2, never a clean line."""


@dataclass(frozen=True)
class Finding:
    """One thing wrong with the examined artifact, named by check and location."""

    check: str
    where: str
    detail: str

    def __str__(self) -> str:
        return f"{self.check}: {self.where}: {self.detail}"


@dataclass(frozen=True)
class Completed:
    """What one child process returned. Bytes, so nothing is decoded lossily."""

    returncode: int
    stdout: bytes
    stderr: bytes


Runner = Callable[[Sequence[str], Path | None], Completed]
"""Runs one fixed argv in one directory. Injectable so the three states are testable."""


@dataclass(frozen=True)
class Report:
    """The evidence a run produced: digests, counts, codes. No path, no value."""

    platform: str
    python_version: str
    wheel_name: str
    wheel_sha256: str
    commands_run: int
    receipt_document_sha256: str | None
    pinned_receipt_document_sha256: str
    payload_sha256: str | None
    findings: tuple[Finding, ...]

    def as_json(self) -> dict[str, object]:
        return {
            "platform": self.platform,
            "python_version": self.python_version,
            "wheel_name": self.wheel_name,
            "wheel_sha256": self.wheel_sha256,
            "commands_run": self.commands_run,
            "receipt_document_sha256": self.receipt_document_sha256,
            "pinned_receipt_document_sha256": self.pinned_receipt_document_sha256,
            "payload_sha256": self.payload_sha256,
            "matches_pin": self.receipt_document_sha256
            == self.pinned_receipt_document_sha256,
            "findings": [
                {"check": f.check, "where": f.where, "detail": f.detail}
                for f in self.findings
            ],
        }


# --- reading the repository --------------------------------------------------


def read(root: Path, name: str) -> str:
    """Return a tracked document's text, or fail the gate if it is not there."""

    try:
        return (root / name).read_text(encoding="utf-8")
    except OSError as exc:
        raise GateUnavailable(f"cannot read {name}: {exc}") from exc


def quickstart_commands(readme_text: str) -> list[list[str]]:
    """The ``contextsafe`` invocations in the README's Quickstart, as argv tails.

    Reads the first ``sh`` block under ``## Quickstart``, joins backslash
    continuations, drops ``#`` comments and the ``make`` line, and requires
    every remaining line to be ``uv run contextsafe ...``: a line this gate
    cannot run from a wheel is a failure to examine, not a silent omission.
    """

    heading = readme_text.find(QUICKSTART_HEADING)
    if heading < 0:
        raise GateUnavailable("README.md has no `## Quickstart` section")
    fence = "```sh\n"
    start = readme_text.find(fence, heading)
    end = readme_text.find("```", start + len(fence)) if start >= 0 else -1
    if start < 0 or end < 0:
        raise GateUnavailable("README.md Quickstart has no closed ```sh block")
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
        if tuple(tokens[:3]) != QUICKSTART_PREFIX:
            raise GateUnavailable(
                "README.md Quickstart line is not a `uv run contextsafe` command, "
                f"so it cannot be run from a wheel: {text!r}"
            )
        if len(tokens) == len(QUICKSTART_PREFIX):
            raise GateUnavailable(
                f"README.md Quickstart line names no contextsafe subcommand: {text!r}"
            )
        commands.append(tokens[3:])
    if not commands:
        raise GateUnavailable("README.md Quickstart names no contextsafe command")
    return commands


def pinned_digest(source_text: str) -> str:
    """``RECEIPT_DOCUMENT_SHA256`` as ``tests/test_determinism.py`` assigns it.

    Read with ``ast`` rather than a regex, so the value is the literal Python
    sees. One copy of the constant, in the file that pins it; this gate reads
    it and never restates it.
    """

    try:
        module = ast.parse(source_text)
    except SyntaxError as exc:
        raise GateUnavailable(f"{PIN_SOURCE} does not parse: {exc}") from exc
    for node in module.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name) or target.id != PIN_NAME:
            continue
        value = node.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            digest = value.value
            if len(digest) == 64 and all(c in "0123456789abcdef" for c in digest):
                return digest
        raise GateUnavailable(
            f"{PIN_SOURCE} assigns {PIN_NAME} something other than a SHA-256 hex digest"
        )
    raise GateUnavailable(f"{PIN_SOURCE} no longer assigns {PIN_NAME}")


def locate_wheel(dist: Path) -> Path:
    """Exactly one wheel under ``dist``. Zero or several is nothing to examine."""

    wheels = sorted(dist.glob("*.whl")) if dist.is_dir() else []
    if len(wheels) != 1:
        raise GateUnavailable(
            f"expected exactly one wheel under {dist.name}/, found {len(wheels)}"
        )
    return wheels[0]


def venv_layout(venv: Path) -> tuple[Path, Path]:
    """The interpreter and the console script a venv places, per platform."""

    scripts = venv / ("Scripts" if os.name == "nt" else "bin")
    suffix = ".exe" if os.name == "nt" else ""
    return scripts / f"python{suffix}", scripts / f"contextsafe{suffix}"


def _run(argv: Sequence[str], cwd: Path | None) -> Completed:
    env = {k: v for k, v in os.environ.items() if k not in _DROPPED_ENVIRONMENT}
    try:
        completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
            list(argv),
            cwd=cwd,
            env=env,
            capture_output=True,
            timeout=COMMAND_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GateUnavailable(f"could not run {Path(argv[0]).name}: {exc}") from exc
    return Completed(completed.returncode, completed.stdout, completed.stderr)


# --- the examination ---------------------------------------------------------


def _error_code(stderr: bytes) -> str | None:
    """The closed-vocabulary code from one of the tool's own JSON error objects.

    Anything else on stderr is not reported: it could be a traceback carrying
    a path, and the report carries codes, not text.
    """

    try:
        document = json.loads(stderr.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    if isinstance(document, dict) and isinstance(document.get("error"), dict):
        code = document["error"].get("code")
        return code if isinstance(code, str) else None
    return None


def _output_operand(argv: Sequence[str]) -> str | None:
    if "--output" in argv:
        index = argv.index("--output")
        if index + 1 < len(argv):
            return argv[index + 1]
    return None


def _install(
    run: Runner, python: Path, wheel: Path, outside: Path
) -> tuple[Finding | None, Path | None]:
    """Create nothing here; install the wheel and say where it imported from."""

    if run([str(python), "-m", "pip", "--version"], None).returncode != 0:
        raise GateUnavailable(
            "the fresh virtual environment has no pip, so the wheel cannot be "
            "installed the way a customer would install it"
        )
    installed = run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--no-index",
            "--force-reinstall",
            "--disable-pip-version-check",
            str(wheel),
        ],
        None,
    )
    if installed.returncode != 0:
        return (
            Finding(
                "install",
                wheel.name,
                f"pip exited {installed.returncode} installing the wheel with "
                "--no-index; the artifact needs something an index would have "
                "supplied, or is not installable",
            ),
            None,
        )
    located = run(
        [
            str(python),
            "-c",
            "import contextsafe, sys; sys.stdout.write(contextsafe.__file__)",
        ],
        outside,
    )
    if located.returncode != 0:
        return (
            Finding(
                "import",
                "contextsafe",
                f"the installed package could not be imported (exit "
                f"{located.returncode})",
            ),
            None,
        )
    return None, Path(located.stdout.decode("utf-8").strip())


def _run_commands(
    run: Runner, script: Path, commands: Sequence[Sequence[str]], outside: Path
) -> list[Finding]:
    findings: list[Finding] = []
    for argv in commands:
        completed = run([str(script), *argv], outside)
        if completed.returncode != 0:
            code = _error_code(completed.stderr)
            findings.append(
                Finding(
                    "command",
                    f"contextsafe {argv[0]}",
                    f"exited {completed.returncode} from the installed wheel, "
                    "outside the repository" + (f"; error code {code}" if code else ""),
                )
            )
    return findings


def _receipt_digests(
    outside: Path, commands: Sequence[Sequence[str]]
) -> tuple[str | None, str | None, Finding | None]:
    """SHA-256 of the receipt document ``evaluate`` wrote, and its payload digest."""

    evaluate = next((argv for argv in commands if argv[0] == "evaluate"), None)
    output = None if evaluate is None else _output_operand(evaluate)
    if output is None:
        raise GateUnavailable(
            "the Quickstart has no `evaluate ... --output` command, so there is "
            "no receipt document to check against the pin"
        )
    try:
        document = (outside / output).read_bytes()
    except OSError:
        return (
            None,
            None,
            Finding("receipt", "$", "evaluate wrote no receipt document to read"),
        )
    digest = hashlib.sha256(document).hexdigest()
    try:
        parsed = json.loads(document.decode("utf-8"))
        payload = parsed["payload_sha256"]
    except (UnicodeDecodeError, ValueError, KeyError, TypeError):
        return (
            digest,
            None,
            Finding(
                "receipt",
                "$.payload_sha256",
                "the receipt document is not a JSON object carrying payload_sha256",
            ),
        )
    return digest, payload if isinstance(payload, str) else None, None


def run_gate(
    *,
    dist: Path,
    workdir: Path,
    root: Path = REPO_ROOT,
    python: str | None = None,
    run: Runner | None = None,
) -> Report:
    """Install the one wheel under ``dist`` into ``workdir`` and run the Quickstart.

    ``workdir`` must not exist yet and must not be inside ``root``: the whole
    point is a directory the checkout cannot reach and nothing else has
    touched. A directory that already exists is refused before anything runs,
    because ``python -m venv`` over an existing environment and ``pip install``
    of an already-installed version both exit 0 and would leave a stale
    install reporting as the wheel named in the clean line. ``--clear`` and
    ``--force-reinstall`` sit under that guard, not in place of it. ``python``
    creates the environment and defaults to the interpreter running this gate.
    Raises ``GateUnavailable`` for every state in which the wheel was not
    examined.
    """

    python = sys.executable if python is None else python
    run = _run if run is None else run
    root = root.resolve()
    workdir = workdir.resolve()
    if workdir == root or workdir.is_relative_to(root):
        raise GateUnavailable(
            "the working directory is inside the repository; the gate exists to "
            "run the wheel from a directory the checkout cannot reach"
        )
    wheel = locate_wheel(dist)
    commands = quickstart_commands(read(root, README))
    pinned = pinned_digest(read(root, PIN_SOURCE))
    venv = workdir / "venv"
    outside = workdir / "outside"
    if workdir.exists():
        raise GateUnavailable(
            "the working directory already exists; the gate only examines a "
            "wheel in an environment it created"
        )
    try:
        outside.mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        raise GateUnavailable(
            f"cannot create a fresh working directory: {exc}"
        ) from exc
    if run([python, "-m", "venv", "--clear", str(venv)], None).returncode != 0:
        raise GateUnavailable("python -m venv could not create an empty environment")
    interpreter, script = venv_layout(venv)

    findings: list[Finding] = []
    commands_run = 0
    document_digest: str | None = None
    payload_digest: str | None = None
    failure, located = _install(run, interpreter, wheel, outside)
    if failure is not None:
        findings.append(failure)
    elif located is not None and not located.resolve().is_relative_to(venv):
        findings.append(
            Finding(
                "import",
                "contextsafe",
                "the fresh environment imported contextsafe from outside itself, "
                "so what ran was not the wheel",
            )
        )
    else:
        findings.extend(_run_commands(run, script, commands, outside))
        commands_run = len(commands)
        document_digest, payload_digest, failure = _receipt_digests(outside, commands)
        if failure is not None:
            findings.append(failure)
        elif document_digest != pinned:
            findings.append(
                Finding(
                    "digest",
                    "receipt document",
                    "the wheel's receipt document does not reproduce the digest "
                    f"{PIN_SOURCE} pins",
                )
            )
    return Report(
        platform=sys.platform,
        python_version=".".join(str(part) for part in sys.version_info[:3]),
        wheel_name=wheel.name,
        wheel_sha256=hashlib.sha256(wheel.read_bytes()).hexdigest(),
        commands_run=commands_run,
        receipt_document_sha256=document_digest,
        pinned_receipt_document_sha256=pinned,
        payload_sha256=payload_digest,
        findings=tuple(findings),
    )


def _write_report(path: Path, report: Report) -> None:
    path.write_text(
        json.dumps(report.as_json(), sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the gate: 0 installed, ran and matched; 1 a finding; 2 not examined."""

    parser = argparse.ArgumentParser(
        prog="fresh_install_gate",
        description=(
            "Install the built wheel with pip into an empty virtual environment, "
            "run the README Quickstart from outside the checkout, and compare the "
            "receipt document with the digest tests/test_determinism.py pins."
        ),
    )
    parser.add_argument("--dist", type=Path, required=True)
    parser.add_argument("--workdir", type=Path, default=None)
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args(argv)
    root = args.root.resolve() if args.root is not None else REPO_ROOT
    workdir = args.workdir
    if workdir is None:
        # mkdtemp creates the parent, privately; the gate itself creates the
        # working directory beneath it, so the default path passes the same
        # "nothing existed here before" guard as an explicit --workdir.
        parent = Path(tempfile.mkdtemp(prefix="contextsafe-fresh-install-"))
        workdir = parent / "gate"

    try:
        report = run_gate(dist=args.dist, workdir=workdir, root=root)
    except GateUnavailable as exc:
        print(f"fresh-install: {exc}.", file=sys.stderr)
        print(
            "fresh-install: the wheel was NOT examined; this is not a clean result.",
            file=sys.stderr,
        )
        return 2

    if args.json is not None:
        _write_report(args.json, report)
    if report.findings:
        print(
            f"fresh-install: {len(report.findings)} finding(s) against "
            f"{report.wheel_name} on {report.platform}",
            file=sys.stderr,
        )
        for finding in report.findings:
            print(f"  {finding}", file=sys.stderr)
        return 1
    print(
        f"fresh-install: clean - {report.wheel_name} installed with pip --no-index "
        f"on {report.platform}, {report.commands_run} Quickstart command(s) run "
        "outside the checkout, receipt document sha256 matches "
        f"{PIN_SOURCE} ({report.pinned_receipt_document_sha256})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
