"""The fresh-install gate must fail on a wrong wheel, and differently on no wheel.

Every case here drives ``tools/fresh_install_gate.py`` with a stand-in runner
in place of ``python -m venv``, ``pip`` and the installed console script, so
the three states of ADR 0008 are checked on every ``make verify`` without
building a wheel: a wheel that installs, runs and reproduces the pinned digest
is exit 0; one that was examined and found wrong is exit 1; a gate that could
not examine it - no wheel, two wheels, no pin, no Quickstart, no pip, a
working directory inside the checkout or one that already exists - is exit 2
and never a pass.

The real path, ``uv build`` then this gate's own subprocess runner against the
wheel it produced, is ``tests/test_wheel_quickstart.py``.

The other property pinned here is what the report may carry: digests, counts,
a platform name and closed-vocabulary codes. Never a path. The working
directory, the checkout and the venv all appear as strings inside the gate;
none of them may appear in what it writes.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

REPO_ROOT = Path(__file__).resolve().parents[1]
GATE_PATH = REPO_ROOT / "tools" / "fresh_install_gate.py"

CLEAN, FOUND, UNAVAILABLE = 0, 1, 2


def _load_gate() -> ModuleType:
    spec = importlib.util.spec_from_file_location("fresh_install_gate", GATE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


gate = _load_gate()

RECEIPT = b'{"envelope":{},"payload":{},"payload_sha256":"' + b"a" * 64 + b'"}\n'
PIN = hashlib.sha256(RECEIPT).hexdigest()

QUICKSTART = (
    "# ContextSafe\n\nprose\n\n## Quickstart\n\nWith uv:\n\n```sh\n"
    "make verify                       # sync lint\n"
    "uv run contextsafe fixtures export   # the packaged inputs\n"
    "uv run contextsafe evaluate \\\n"
    "  --case fixtures/reference/case.json \\\n"
    "  --output receipt.json           # unsigned receipt\n"
    "uv run contextsafe render \\\n"
    "  --receipt receipt.json \\\n"
    "  --output receipt.html\n"
    "```\n\nMore prose.\n"
)


def _pin_source(digest: str) -> str:
    return (
        '"""Determinism evidence."""\n\n'
        f'RECEIPT_DOCUMENT_SHA256 = (\n    "{digest}"\n)\n'
        '"""SHA-256 of the reference document."""\n'
    )


@dataclass
class FakeRunner:
    """Stands in for venv creation, pip and the installed console script.

    Records every argv so a test can assert what the gate asked for, and
    writes the receipt document when the ``evaluate`` command runs, the way
    the real console script would.
    """

    venv_exit: int = 0
    pip_present: bool = True
    install_exit: int = 0
    import_exit: int = 0
    import_location: Path | None = None
    command_exits: dict[str, int] = field(default_factory=dict)
    command_stderr: bytes = b""
    receipt: bytes | None = RECEIPT
    calls: list[tuple[list[str], Path | None]] = field(default_factory=list)
    venv: Path | None = None

    def __call__(self, argv: list[str], cwd: Path | None) -> gate.Completed:
        self.calls.append((list(argv), cwd))
        if argv[1:3] == ["-m", "venv"]:
            self.venv = Path(argv[-1])
            return gate.Completed(self.venv_exit, b"", b"")
        if argv[1:4] == ["-m", "pip", "--version"]:
            return gate.Completed(0 if self.pip_present else 1, b"", b"")
        if argv[1:4] == ["-m", "pip", "install"]:
            return gate.Completed(self.install_exit, b"", b"")
        if argv[1] == "-c":
            assert self.venv is not None
            located = self.import_location or (
                self.venv / "lib" / "site-packages" / "contextsafe" / "__init__.py"
            )
            return gate.Completed(self.import_exit, str(located).encode(), b"")
        return self._command(argv, cwd)

    def _command(self, argv: list[str], cwd: Path | None) -> gate.Completed:
        name = argv[1]
        code = self.command_exits.get(name, 0)
        if name == "evaluate" and code == 0 and self.receipt is not None:
            assert cwd is not None
            (cwd / argv[argv.index("--output") + 1]).write_bytes(self.receipt)
        return gate.Completed(code, b"", self.command_stderr if code else b"")


@dataclass(frozen=True)
class Scaffold:
    root: Path
    dist: Path
    workdir: Path


@pytest.fixture
def scaffold(tmp_path: Path) -> Scaffold:
    root = tmp_path / "repo"
    (root / "tests").mkdir(parents=True)
    (root / "README.md").write_text(QUICKSTART, encoding="utf-8")
    (root / "tests" / "test_determinism.py").write_text(
        _pin_source(PIN), encoding="utf-8"
    )
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "contextsafe-0.1.0-py3-none-any.whl").write_bytes(b"PK\x03\x04fake")
    return Scaffold(root=root, dist=dist, workdir=tmp_path / "work")


def _run(scaffold: Scaffold, runner: FakeRunner) -> gate.Report:
    return gate.run_gate(
        dist=scaffold.dist,
        workdir=scaffold.workdir,
        root=scaffold.root,
        python="fake-python",
        run=runner,
    )


# --- the happy path, and what it asked for ------------------------------------


def test_a_wheel_that_installs_runs_and_matches_is_clean(scaffold: Scaffold) -> None:
    runner = FakeRunner()

    report = _run(scaffold, runner)

    assert report.findings == ()
    assert report.commands_run == 3
    assert report.receipt_document_sha256 == PIN
    assert report.pinned_receipt_document_sha256 == PIN
    assert report.payload_sha256 == "a" * 64
    assert report.wheel_name == "contextsafe-0.1.0-py3-none-any.whl"
    assert report.wheel_sha256 == hashlib.sha256(b"PK\x03\x04fake").hexdigest()
    assert report.as_json()["matches_pin"] is True


def test_the_gate_installs_with_no_index_and_runs_from_outside(
    scaffold: Scaffold,
) -> None:
    """``--no-index`` is the zero-dependency claim enforced; outside is outside."""

    runner = FakeRunner()
    _run(scaffold, runner)

    install = next(argv for argv, _ in runner.calls if "install" in argv)
    assert "--no-index" in install
    assert install[-1].endswith(".whl")
    interpreter, script = gate.venv_layout(scaffold.workdir.resolve() / "venv")
    assert install[0] == str(interpreter)
    commands = [(argv, cwd) for argv, cwd in runner.calls if argv[0] == str(script)]
    assert [argv[1] for argv, _ in commands] == ["fixtures", "evaluate", "render"]
    outside = scaffold.workdir.resolve() / "outside"
    assert all(cwd == outside for _, cwd in commands)
    assert not outside.is_relative_to(scaffold.root.resolve())


def test_venv_layout_names_the_platform_paths(tmp_path: Path) -> None:
    interpreter, script = gate.venv_layout(tmp_path)
    if os.name == "nt":
        assert (interpreter.parent.name, interpreter.name) == ("Scripts", "python.exe")
        assert script.name == "contextsafe.exe"
    else:
        assert (interpreter.parent.name, interpreter.name) == ("bin", "python")
        assert script.name == "contextsafe"


# --- findings: the wheel was examined and is wrong ---------------------------


def test_a_wheel_pip_cannot_install_offline_is_a_finding(scaffold: Scaffold) -> None:
    """A runtime dependency would fail here, and that is the artifact's fault."""

    runner = FakeRunner(install_exit=1)
    report = _run(scaffold, runner)

    assert [f.check for f in report.findings] == ["install"]
    assert report.commands_run == 0
    assert not any(argv[1] == "fixtures" for argv, _ in runner.calls)


def test_a_package_that_cannot_be_imported_is_a_finding(scaffold: Scaffold) -> None:
    report = _run(scaffold, FakeRunner(import_exit=1))

    assert [f.check for f in report.findings] == ["import"]
    assert report.commands_run == 0


def test_an_import_from_outside_the_venv_is_a_finding(
    scaffold: Scaffold, tmp_path: Path
) -> None:
    """If the fresh interpreter found the checkout, nothing about the wheel ran."""

    elsewhere = tmp_path / "src" / "contextsafe" / "__init__.py"
    report = _run(scaffold, FakeRunner(import_location=elsewhere))

    assert [f.check for f in report.findings] == ["import"]
    assert "outside itself" in report.findings[0].detail
    assert report.commands_run == 0


def test_a_failing_quickstart_command_is_a_finding_with_its_code(
    scaffold: Scaffold,
) -> None:
    stderr = b'{"error":{"code":"input_io_error","path":"$","message":"m"}}\n'
    runner = FakeRunner(command_exits={"fixtures": 2}, command_stderr=stderr)
    report = _run(scaffold, runner)

    command = [f for f in report.findings if f.check == "command"]
    assert len(command) == 1
    assert command[0].where == "contextsafe fixtures"
    assert "exited 2" in command[0].detail
    assert "input_io_error" in command[0].detail
    assert '"message"' not in command[0].detail


def test_stderr_that_is_not_the_tools_error_object_is_reduced_to_a_code(
    scaffold: Scaffold,
) -> None:
    """A traceback could carry a path; the report gets the exit code only."""

    stderr = b"Traceback (most recent call last):\n  File fixture-workstation/x.py\n"
    runner = FakeRunner(command_exits={"render": 1}, command_stderr=stderr)
    report = _run(scaffold, runner)

    finding = next(f for f in report.findings if f.check == "command")
    assert "fixture-workstation" not in finding.detail
    assert "Traceback" not in finding.detail
    assert "error code" not in finding.detail


@pytest.mark.parametrize(
    "stderr",
    [b"not json", b"[]", b'{"error":"flat"}', b'{"error":{"code":7}}', b"\xff"],
)
def test_error_code_extraction_accepts_only_the_closed_shape(stderr: bytes) -> None:
    assert gate._error_code(stderr) is None


def test_a_receipt_that_does_not_reproduce_the_pin_is_a_finding(
    scaffold: Scaffold,
) -> None:
    other = RECEIPT.replace(b"a" * 64, b"b" * 64)
    report = _run(scaffold, FakeRunner(receipt=other))

    assert [f.check for f in report.findings] == ["digest"]
    assert report.receipt_document_sha256 == hashlib.sha256(other).hexdigest()
    assert report.receipt_document_sha256 != report.pinned_receipt_document_sha256
    assert report.as_json()["matches_pin"] is False


def test_a_missing_receipt_document_is_a_finding(scaffold: Scaffold) -> None:
    report = _run(scaffold, FakeRunner(receipt=None))

    assert [f.check for f in report.findings] == ["receipt"]
    assert report.receipt_document_sha256 is None


def test_a_receipt_that_is_not_a_document_is_a_finding(scaffold: Scaffold) -> None:
    report = _run(scaffold, FakeRunner(receipt=b"[]\n"))

    assert [(f.check, f.where) for f in report.findings] == [
        ("receipt", "$.payload_sha256")
    ]
    assert report.payload_sha256 is None


def test_a_document_whose_payload_digest_is_not_a_string_reports_none(
    scaffold: Scaffold,
) -> None:
    receipt = b'{"payload_sha256": 7}\n'
    (scaffold.root / "tests" / "test_determinism.py").write_text(
        _pin_source(hashlib.sha256(receipt).hexdigest()), encoding="utf-8"
    )
    report = _run(scaffold, FakeRunner(receipt=receipt))

    assert report.findings == ()
    assert report.payload_sha256 is None


# --- unavailable: the wheel was not examined ---------------------------------


def test_no_wheel_is_not_examined(scaffold: Scaffold) -> None:
    for wheel in scaffold.dist.glob("*.whl"):
        wheel.unlink()
    with pytest.raises(gate.GateUnavailable, match="found 0"):
        _run(scaffold, FakeRunner())


def test_two_wheels_is_not_examined(scaffold: Scaffold) -> None:
    """The gate never picks; two artifacts is nobody's artifact."""

    (scaffold.dist / "contextsafe-0.2.0-py3-none-any.whl").write_bytes(b"x")
    with pytest.raises(gate.GateUnavailable, match="found 2"):
        _run(scaffold, FakeRunner())


def test_a_dist_that_is_not_a_directory_is_not_examined(scaffold: Scaffold) -> None:
    with pytest.raises(gate.GateUnavailable, match="found 0"):
        gate.run_gate(
            dist=scaffold.dist / "missing",
            workdir=scaffold.workdir,
            root=scaffold.root,
            run=FakeRunner(),
        )


def test_a_working_directory_inside_the_checkout_is_not_examined(
    scaffold: Scaffold,
) -> None:
    runner = FakeRunner()
    with pytest.raises(gate.GateUnavailable, match="inside the repository"):
        gate.run_gate(
            dist=scaffold.dist,
            workdir=scaffold.root / "build",
            root=scaffold.root,
            run=runner,
        )
    with pytest.raises(gate.GateUnavailable, match="inside the repository"):
        gate.run_gate(
            dist=scaffold.dist, workdir=scaffold.root, root=scaffold.root, run=runner
        )
    assert runner.calls == []


def test_a_working_directory_already_used_is_not_examined(scaffold: Scaffold) -> None:
    """Fresh means fresh: a second run in the same directory could read the first."""

    _run(scaffold, FakeRunner())
    runner = FakeRunner()
    with pytest.raises(gate.GateUnavailable, match="already exists"):
        _run(scaffold, runner)
    assert runner.calls == []


def test_a_working_directory_with_a_stale_venv_is_not_examined(
    scaffold: Scaffold,
) -> None:
    """A kept ``venv/`` with ``outside/`` removed is the fail-open shape.

    ``python -m venv`` over an existing environment exits 0, and ``pip install
    --no-index`` of the same version into it exits 0 without installing
    anything, so the import-location check passes, the Quickstart runs from
    whatever was installed before, and the clean line names a wheel the gate
    never installed. The gate refuses any pre-existing working directory.
    """

    _run(scaffold, FakeRunner())
    shutil.rmtree(scaffold.workdir / "outside")
    stale = scaffold.workdir / "venv" / "lib" / "site-packages" / "contextsafe"
    stale.mkdir(parents=True, exist_ok=True)
    (stale / "__init__.py").write_bytes(b"")
    assert sorted(child.name for child in scaffold.workdir.iterdir()) == ["venv"]
    runner = FakeRunner()
    with pytest.raises(gate.GateUnavailable, match="already exists"):
        _run(scaffold, runner)
    assert runner.calls == []


def test_an_empty_pre_existing_working_directory_is_not_examined(
    scaffold: Scaffold,
) -> None:
    """Even an empty directory: the gate examines only what it created."""

    scaffold.workdir.mkdir()
    runner = FakeRunner()
    with pytest.raises(gate.GateUnavailable, match="already exists"):
        _run(scaffold, runner)
    assert runner.calls == []


def test_the_gate_clears_the_venv_and_forces_the_reinstall(scaffold: Scaffold) -> None:
    """Belt and braces under the directory guard: never a reused environment."""

    runner = FakeRunner()
    _run(scaffold, runner)

    venv = next(argv for argv, _ in runner.calls if argv[1:3] == ["-m", "venv"])
    assert "--clear" in venv
    install = next(argv for argv, _ in runner.calls if "install" in argv)
    assert "--force-reinstall" in install


def test_a_working_directory_that_cannot_be_created_is_not_examined(
    scaffold: Scaffold, tmp_path: Path
) -> None:
    """A parent that is a file: nothing existed, and nothing can be made."""

    blocker = tmp_path / "blocker"
    blocker.write_bytes(b"")
    runner = FakeRunner()
    with pytest.raises(gate.GateUnavailable, match="fresh working directory"):
        gate.run_gate(
            dist=scaffold.dist,
            workdir=blocker / "work",
            root=scaffold.root,
            python="fake-python",
            run=runner,
        )
    assert runner.calls == []


def test_a_failed_venv_creation_is_not_examined(scaffold: Scaffold) -> None:
    with pytest.raises(gate.GateUnavailable, match="python -m venv"):
        _run(scaffold, FakeRunner(venv_exit=1))


def test_a_venv_without_pip_is_not_examined(scaffold: Scaffold) -> None:
    """No pip is a fact about the machine, not about the wheel."""

    runner = FakeRunner(pip_present=False)
    with pytest.raises(gate.GateUnavailable, match="no pip"):
        _run(scaffold, runner)
    assert not any("install" in argv for argv, _ in runner.calls)


def test_a_missing_readme_or_pin_source_is_not_examined(scaffold: Scaffold) -> None:
    (scaffold.root / "README.md").unlink()
    with pytest.raises(gate.GateUnavailable, match=r"cannot read README\.md"):
        _run(scaffold, FakeRunner())
    (scaffold.root / "README.md").write_text(QUICKSTART, encoding="utf-8")
    (scaffold.root / "tests" / "test_determinism.py").unlink()
    with pytest.raises(gate.GateUnavailable, match="cannot read tests/"):
        _run(scaffold, FakeRunner())


def test_a_quickstart_without_an_evaluate_output_is_not_examined(
    scaffold: Scaffold,
) -> None:
    (scaffold.root / "README.md").write_text(
        "# T\n\n## Quickstart\n\n```sh\nuv run contextsafe fixtures export\n```\n",
        encoding="utf-8",
    )
    with pytest.raises(gate.GateUnavailable, match=r"no `evaluate \.\.\. --output`"):
        _run(scaffold, FakeRunner())


# --- the pin, read from the file that declares it ----------------------------


def test_the_pin_is_read_from_the_real_determinism_module() -> None:
    """One copy of the constant: this gate reads it and never restates it."""

    path = REPO_ROOT / gate.PIN_SOURCE
    spec = importlib.util.spec_from_file_location("_pinned_determinism", path)
    assert spec is not None and spec.loader is not None
    determinism = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(determinism)

    digest = gate.pinned_digest(path.read_text(encoding="utf-8"))
    assert digest == determinism.RECEIPT_DOCUMENT_SHA256
    assert len(digest) == 64


@pytest.mark.parametrize(
    ("source", "reason"),
    [
        ("X = 1\n", "no longer assigns"),
        ('RECEIPT_DOCUMENT_SHA256 = "abc"\n', "something other than"),
        ('RECEIPT_DOCUMENT_SHA256 = "G" * 64\n', "something other than"),
        (f'RECEIPT_DOCUMENT_SHA256 = "{"Z" * 64}"\n', "something other than"),
        ("RECEIPT_DOCUMENT_SHA256 = 7\n", "something other than"),
        ("A = RECEIPT_DOCUMENT_SHA256 = 'x'\n", "no longer assigns"),
        ("def f(:\n", "does not parse"),
    ],
)
def test_a_pin_that_is_not_one_hex_digest_is_not_examined(
    source: str, reason: str
) -> None:
    with pytest.raises(gate.GateUnavailable, match=reason):
        gate.pinned_digest(source)


# --- the Quickstart parser ---------------------------------------------------


def test_quickstart_parser_reads_continuations_comments_and_the_make_line() -> None:
    assert gate.quickstart_commands(QUICKSTART) == [
        ["fixtures", "export"],
        [
            "evaluate",
            "--case",
            "fixtures/reference/case.json",
            "--output",
            "receipt.json",
        ],
        ["render", "--receipt", "receipt.json", "--output", "receipt.html"],
    ]


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("# Title\n\nno quickstart here\n", "no `## Quickstart`"),
        ("# T\n\n## Quickstart\n\nprose only\n", "no closed ```sh block"),
        (
            "# T\n\n## Quickstart\n\n```sh\nuv run contextsafe x\n",
            "no closed ```sh block",
        ),
        (
            "# T\n\n## Quickstart\n\n```sh\n# only a comment\n```\n",
            "names no contextsafe",
        ),
        ("# T\n\n## Quickstart\n\n```sh\nmake verify\n```\n", "names no contextsafe"),
        (
            "# T\n\n## Quickstart\n\n```sh\npip install contextsafe\n```\n",
            "not a `uv run",
        ),
        ("# T\n\n## Quickstart\n\n```sh\nuv run python -m x\n```\n", "not a `uv run"),
        (
            "# T\n\n## Quickstart\n\n```sh\nuv run contextsafe\n```\n",
            "names no contextsafe subcommand",
        ),
        (
            "# T\n\n## Quickstart\n\n```sh\nuv run contextsafe   # bare\n```\n",
            "names no contextsafe subcommand",
        ),
    ],
)
def test_a_quickstart_the_gate_cannot_run_is_not_examined(
    text: str, reason: str
) -> None:
    with pytest.raises(gate.GateUnavailable, match=reason):
        gate.quickstart_commands(text)


_TOKEN = st.text(
    alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz0123456789-./_="),
    min_size=1,
    max_size=12,
)
_TAILS = st.lists(st.lists(_TOKEN, min_size=1, max_size=6), min_size=1, max_size=5)


@settings(max_examples=100, deadline=None)
@given(tails=_TAILS, split=st.booleans(), comment=st.booleans())
def test_quickstart_parser_round_trips_any_command_block(
    tails: list[list[str]], split: bool, comment: bool
) -> None:
    """Rendering argv tails into a Quickstart block and parsing gives them back."""

    lines = []
    for tail in tails:
        rendered = "uv run contextsafe " + " ".join(tail)
        if split and len(tail) > 1:
            rendered = "uv run contextsafe " + " \\\n  ".join(tail)
        if comment:
            rendered += "   # comment text"
        lines.append(rendered)
    text = "# T\n\n## Quickstart\n\n```sh\nmake verify\n" + "\n".join(lines) + "\n```\n"

    assert gate.quickstart_commands(text) == tails


# --- the report and the command line ------------------------------------------


def test_the_report_carries_no_path(scaffold: Scaffold, tmp_path: Path) -> None:
    """Digests, counts, codes, a platform. The directories the gate used, never."""

    report = _run(scaffold, FakeRunner(command_exits={"render": 1}))
    text = json.dumps(report.as_json())

    for fragment in (str(tmp_path), str(scaffold.workdir), str(scaffold.root)):
        assert fragment not in text
    assert set(report.as_json()) == {
        "platform",
        "python_version",
        "wheel_name",
        "wheel_sha256",
        "commands_run",
        "receipt_document_sha256",
        "pinned_receipt_document_sha256",
        "payload_sha256",
        "matches_pin",
        "findings",
    }


def test_main_exit_codes_and_report_file(
    scaffold: Scaffold,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runner = FakeRunner()
    monkeypatch.setattr(gate, "_run", runner)
    out = tmp_path / "report.json"

    code = gate.main(
        [
            "--dist",
            str(scaffold.dist),
            "--workdir",
            str(scaffold.workdir),
            "--root",
            str(scaffold.root),
            "--json",
            str(out),
        ]
    )

    assert code == CLEAN
    captured = capsys.readouterr()
    assert "fresh-install: clean" in captured.out
    assert PIN in captured.out
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["matches_pin"] is True
    assert str(tmp_path) not in out.read_text(encoding="utf-8")


def test_main_reports_a_finding_on_stderr_and_exits_one(
    scaffold: Scaffold,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(gate, "_run", FakeRunner(receipt=b"{}\n"))
    out = tmp_path / "report.json"

    code = gate.main(
        [
            "--dist",
            str(scaffold.dist),
            "--workdir",
            str(scaffold.workdir),
            "--root",
            str(scaffold.root),
            "--json",
            str(out),
        ]
    )

    assert code == FOUND
    captured = capsys.readouterr()
    assert "1 finding(s)" in captured.err
    assert "receipt: $.payload_sha256" in captured.err
    assert captured.out == ""
    assert json.loads(out.read_text(encoding="utf-8"))["matches_pin"] is False


def test_main_says_not_examined_and_exits_two(
    scaffold: Scaffold,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(gate, "_run", FakeRunner(venv_exit=1))
    out = tmp_path / "report.json"

    code = gate.main(
        [
            "--dist",
            str(scaffold.dist),
            "--workdir",
            str(scaffold.workdir),
            "--root",
            str(scaffold.root),
            "--json",
            str(out),
        ]
    )

    assert code == UNAVAILABLE
    captured = capsys.readouterr()
    assert "NOT examined" in captured.err
    assert captured.out == ""
    assert not out.exists()


def test_main_defaults_to_a_fresh_temporary_working_directory(
    scaffold: Scaffold, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runner = FakeRunner()
    monkeypatch.setattr(gate, "_run", runner)
    monkeypatch.setattr(gate.tempfile, "tempdir", str(tmp_path))

    code = gate.main(["--dist", str(scaffold.dist), "--root", str(scaffold.root)])

    assert code == CLEAN
    venv_argv = next(argv for argv, _ in runner.calls if argv[1:3] == ["-m", "venv"])
    venv = Path(venv_argv[-1])
    assert venv.is_relative_to(tmp_path.resolve())
    assert venv_argv[0] == sys.executable
    # The directory the gate worked in did not exist before the gate made it:
    # mkdtemp created only its parent, so the pre-existence guard applied here.
    assert venv.parent.parent.name.startswith("contextsafe-fresh-install-")
    assert venv.parent.name == "gate"


def test_the_real_runner_reports_an_unrunnable_argv_as_not_examined(
    tmp_path: Path,
) -> None:
    with pytest.raises(gate.GateUnavailable, match="could not run"):
        gate._run([str(tmp_path / "no-such-interpreter"), "-m", "venv"], None)


def test_the_real_runner_returns_bytes_from_a_child(tmp_path: Path) -> None:
    completed = gate._run(
        [sys.executable, "-c", "import sys; sys.stdout.write('ok'); sys.exit(3)"],
        tmp_path,
    )
    assert (completed.returncode, completed.stdout) == (3, b"ok")
