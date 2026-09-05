"""One exit-code contract, asserted of every gate in this repository.

Three states, and they are three because two is how a gate lies:

* ``0`` the gate examined what it claims to and found nothing;
* ``1`` it examined and found something;
* ``2`` it did not examine, so it has no answer.

`make hygiene`, `make publication-sweep` and `make scope` were built this way.
The three gates that depend on a tool a clean clone does not have were not, and
those are exactly the three where the distinction matters most: an absent
scanner is the failure most easily mistaken for a clean one. Before this
module, `tools/secret-scan-full-history.sh` exited 127 for an absent gitleaks
and 1 for a damaged object database, putting the latter at the same code as a
leaked credential; `tools/a11y_gate.py` exited 1 whether node was missing or a
page failed contrast; and `tools/i18n_gate.py` exited 1 for "no catalog was
examined".

The secret scan had no test at all. It has three here, driven by a stand-in
gitleaks, so its three states are checked on every run of `make verify` on a
machine that has no gitleaks installed.
"""

from __future__ import annotations

import ast
import importlib.util
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SECRET_SCAN = REPO_ROOT / "tools" / "secret-scan-full-history.sh"
PINNED = "8.30.1"

CLEAN, FOUND, UNAVAILABLE = 0, 1, 2


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        f"_contract_{name}", REPO_ROOT / "tools" / f"{name}.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],  # noqa: S607 - `git` from PATH is the project's own toolchain
        cwd=root,
        check=True,
        capture_output=True,
    )


# --- the shell script, which had no test at all -----------------------------


def _fake_gitleaks(directory: Path, *, version: str, detect_exit: int) -> Path:
    """Write a stand-in gitleaks, so the three states are testable without one.

    The real binary is not in `uv.lock` and a clean clone does not carry it,
    which is the whole reason this gate sits outside `make verify`. Driving the
    script with a stand-in is what lets its three states be checked anyway.

    It records its argv beside itself. Without that, deleting phases 1 and 3
    from the script -- so it no longer scanned reachable history or the working
    tree at all -- left every test in this file green, because nothing asserted
    that three scans happen or what each one is pointed at.
    """

    path = directory / "gitleaks"
    log = directory / "gitleaks-argv.log"
    path.write_text(
        "#!/usr/bin/env bash\n"
        f'printf "%s\\n" "$*" >>"{log}"\n'
        'if [ "$1" = "version" ]; then\n'
        f'  echo "{version}"\n'
        "  exit 0\n"
        "fi\n"
        f"exit {detect_exit}\n",
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


def _detect_invocations(binary: Path) -> list[str]:
    """The argv of every `detect` the stand-in was asked to run, in order."""

    log = binary.parent / "gitleaks-argv.log"
    if not log.is_file():
        return []
    return [
        line
        for line in log.read_text(encoding="utf-8").splitlines()
        if line.startswith("detect")
    ]


def _stub_git(directory: Path, batch_check_body: str) -> Path:
    """A `git` that forwards everything but the object enumeration.

    The enumeration's own failure modes are not reachable from a healthy
    repository, and they are the ones the phase-2 `case` used to drop on the
    floor. Real git does the rest of the work.
    """

    real = shutil.which("git")
    assert real is not None
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "git"
    path.write_text(
        "#!/usr/bin/env bash\n"
        'if [ "$1" = "cat-file" ] && [ "$2" = "--batch-all-objects" ]; then\n'
        f"{batch_check_body}\n"
        "fi\n"
        f'exec "{real}" "$@"\n',
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


def _scan(repo: Path, **env: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SECRET_SCAN)],  # noqa: S607 - bash from PATH, fixed argv
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, **env},
    )


@pytest.fixture
def scannable_repo(tmp_path: Path) -> Path:
    """A repository with one commit, so the object database is not empty."""

    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "README.md").write_text("nothing secret here\n", encoding="utf-8")
    (repo / ".gitleaks.toml").write_text(
        "[extend]\nuseDefault = true\n", encoding="utf-8"
    )
    _git(repo, "add", "--", "README.md", ".gitleaks.toml")
    _git(
        repo,
        "-c",
        "user.email=t@contextsafe.invalid",
        "-c",
        "user.name=t",
        "commit",
        "-q",
        "-m",
        "one",
    )
    return repo


def test_the_secret_scan_is_clean_when_the_scanner_finds_nothing(
    scannable_repo: Path, tmp_path: Path
) -> None:
    binary = _fake_gitleaks(tmp_path, version=PINNED, detect_exit=CLEAN)
    result = _scan(scannable_repo, GITLEAKS_BIN=str(binary))
    assert result.returncode == CLEAN, result.stderr
    assert "materialized" in result.stdout
    assert "clean" in result.stdout


def test_the_secret_scan_fails_when_the_scanner_finds_something(
    scannable_repo: Path, tmp_path: Path
) -> None:
    binary = _fake_gitleaks(tmp_path, version=PINNED, detect_exit=FOUND)
    assert _scan(scannable_repo, GITLEAKS_BIN=str(binary)).returncode == FOUND


def test_the_secret_scan_refuses_when_the_scanner_is_not_installed(
    scannable_repo: Path,
) -> None:
    """The failure most easily mistaken for a clean one."""

    result = _scan(scannable_repo, GITLEAKS_BIN=str(scannable_repo / "absent"))
    assert result.returncode == UNAVAILABLE
    assert "gitleaks not found" in result.stderr
    assert "not a clean result" in result.stderr


def test_the_secret_scan_refuses_an_unpinned_scanner(
    scannable_repo: Path, tmp_path: Path
) -> None:
    """A scanner whose ruleset can change underneath the gate is not a gate."""

    binary = _fake_gitleaks(tmp_path, version="8.0.0", detect_exit=CLEAN)
    result = _scan(scannable_repo, GITLEAKS_BIN=str(binary))
    assert result.returncode == UNAVAILABLE
    assert "pinned to" in result.stderr


def test_an_unpinned_scanner_may_be_allowed_explicitly_and_says_so(
    scannable_repo: Path, tmp_path: Path
) -> None:
    binary = _fake_gitleaks(tmp_path, version="8.0.0", detect_exit=CLEAN)
    result = _scan(
        scannable_repo,
        GITLEAKS_BIN=str(binary),
        ALLOW_GITLEAKS_VERSION_DRIFT="1",
    )
    assert result.returncode == CLEAN
    assert "WARNING" in result.stderr


def test_the_secret_scan_refuses_a_repository_with_no_objects(
    tmp_path: Path,
) -> None:
    """Zero blobs enumerated is not a history with no secrets in it."""

    repo = tmp_path / "empty"
    repo.mkdir()
    _git(repo, "init", "-q")
    # The config check precedes the enumeration; this test is about the latter.
    (repo / ".gitleaks.toml").write_text(
        "[extend]\nuseDefault = true\n", encoding="utf-8"
    )
    binary = _fake_gitleaks(tmp_path, version=PINNED, detect_exit=CLEAN)
    result = _scan(repo, GITLEAKS_BIN=str(binary))
    assert result.returncode == UNAVAILABLE
    assert "zero blobs" in result.stderr


def test_the_secret_scan_never_maps_an_absent_scanner_onto_a_finding(
    scannable_repo: Path, tmp_path: Path
) -> None:
    """The three states must be three distinct codes, not two."""

    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    found = _fake_gitleaks(tmp_path / "a", version=PINNED, detect_exit=FOUND)
    absent = scannable_repo / "absent"
    codes = {
        _scan(scannable_repo, GITLEAKS_BIN=str(found)).returncode,
        _scan(scannable_repo, GITLEAKS_BIN=str(absent)).returncode,
        _scan(
            scannable_repo,
            GITLEAKS_BIN=str(
                _fake_gitleaks(tmp_path / "b", version=PINNED, detect_exit=CLEAN)
            ),
        ).returncode,
    }
    assert codes == {CLEAN, FOUND, UNAVAILABLE}


def test_a_clean_scan_is_three_scans_pointed_at_three_different_things(
    scannable_repo: Path, tmp_path: Path
) -> None:
    """The phases are the gate. Losing one is not a smaller pass, it is a lie.

    Deleting phase 1 and phase 3 from the script left every other test here
    green: the stand-in recorded nothing, and nothing asserted the count or the
    `--source` each scan was handed.
    """

    binary = _fake_gitleaks(tmp_path, version=PINNED, detect_exit=CLEAN)
    assert _scan(scannable_repo, GITLEAKS_BIN=str(binary)).returncode == CLEAN
    calls = _detect_invocations(binary)
    assert len(calls) == 3, calls

    history, objects, worktree = calls
    # 1: every reachable commit on every ref, through git rather than the tree.
    assert "--source ." in history
    assert "--log-opts=--all --full-history" in history
    assert "--no-git" not in history
    # 2: the materialised object database, which is not the working tree.
    assert "--no-git" in objects
    assert "--source ." not in objects
    # 3: the working tree, including files no commit covers.
    assert "--source ." in worktree
    assert "--no-git" in worktree
    assert all("--redact" in call for call in calls)
    assert all("--config " in call for call in calls), calls


def test_the_secret_scan_refuses_when_its_allowlist_is_absent(
    scannable_repo: Path, tmp_path: Path
) -> None:
    """A missing config is the absent-scanner failure wearing another hat.

    gitleaks discovers a config beside its ``--source``, and phase 2's source
    is a temporary directory, so a discovered config would apply to two phases
    and not to the third. The config is passed explicitly for that reason, and
    running without one would quietly widen what the gate reports on.
    """

    (scannable_repo / ".gitleaks.toml").unlink()
    binary = _fake_gitleaks(tmp_path, version=PINNED, detect_exit=CLEAN)
    result = _scan(scannable_repo, GITLEAKS_BIN=str(binary))
    assert result.returncode == UNAVAILABLE
    assert "no gitleaks config" in result.stderr
    assert _detect_invocations(binary) == []


def test_the_scan_refuses_an_object_it_cannot_classify(
    scannable_repo: Path, tmp_path: Path
) -> None:
    """`missing` is git saying it could not read an object it just listed.

    The phase-2 `case` had branches for `blob` and `commit` and no default, so
    this -- the dominant object-database corruption mode -- was never counted,
    never materialised, and never an error. The phase reported clean over it.
    """

    binary = _fake_gitleaks(tmp_path, version=PINNED, detect_exit=CLEAN)
    stub = _stub_git(
        tmp_path / "bin-missing",
        '  echo "0000000000000000000000000000000000000000 missing"\n  exit 0',
    )
    result = _scan(
        scannable_repo,
        GITLEAKS_BIN=str(binary),
        PATH=f"{stub.parent}{os.pathsep}{os.environ['PATH']}",
    )
    assert result.returncode == UNAVAILABLE
    assert "'missing'" in result.stderr
    assert "no clean result" in result.stderr


def test_the_scan_refuses_when_the_enumeration_itself_fails(
    scannable_repo: Path, tmp_path: Path
) -> None:
    """`while read` fed by process substitution takes no status from the feeder.

    Neither `set -e` nor `pipefail` covers it, so a `git cat-file` that died
    partway through simply ended the loop and the phase carried on.
    """

    binary = _fake_gitleaks(tmp_path, version=PINNED, detect_exit=CLEAN)
    stub = _stub_git(
        tmp_path / "bin-broken",
        '  echo "object database unreadable" >&2\n  exit 128',
    )
    result = _scan(
        scannable_repo,
        GITLEAKS_BIN=str(binary),
        PATH=f"{stub.parent}{os.pathsep}{os.environ['PATH']}",
    )
    assert result.returncode == UNAVAILABLE
    assert "could not enumerate" in result.stderr


def test_the_scan_materializes_an_annotated_tag_message(
    scannable_repo: Path, tmp_path: Path
) -> None:
    """A tag object's message is in no blob and no commit, and phase 1 skips it."""

    _git(
        scannable_repo,
        "-c",
        "user.email=t@contextsafe.invalid",
        "-c",
        "user.name=t",
        "tag",
        "-a",
        "v0",
        "-m",
        "an annotated tag message",
    )
    binary = _fake_gitleaks(tmp_path, version=PINNED, detect_exit=CLEAN)
    result = _scan(scannable_repo, GITLEAKS_BIN=str(binary))
    assert result.returncode == CLEAN, result.stderr
    assert "and 1 tags" in result.stdout


# --- every Python gate, in a state where it examined nothing ----------------


def _empty_repo(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q")
    (root / "README.md").write_text("nothing to examine\n", encoding="utf-8")
    _git(root, "add", "--", "README.md")
    return root


def _hygiene_unavailable(tmp_path: Path) -> int:
    gate = _load("hygiene_gate")
    return int(gate.main(["--root", str(_empty_repo(tmp_path / "hygiene"))]))


def _scope_unavailable(tmp_path: Path) -> int:
    gate = _load("scope_gate")
    return int(gate.main(["--root", str(_empty_repo(tmp_path / "scope"))]))


def _patterns_unavailable(tmp_path: Path) -> int:
    """No published contract to read: nothing was compared, so nothing is clean."""

    gate = _load("pattern_gate")
    root = tmp_path / "patterns"
    root.mkdir(parents=True, exist_ok=True)
    return int(gate.main(["--root", str(root)]))


def _sweep_unavailable(tmp_path: Path) -> int:
    gate = _load("publication_sweep")
    repo = tmp_path / "sweep"
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q")
    previous = Path.cwd()
    os.chdir(repo)
    try:
        return int(gate.main([]))
    finally:
        os.chdir(previous)


def _i18n_unavailable(tmp_path: Path) -> int:
    gate = _load("i18n_gate")
    return int(gate.main(["--locale", "xx-YY"]))


def _a11y_unavailable(tmp_path: Path) -> int:
    gate = _load("a11y_gate")
    real = shutil.which

    def without_node(name: str, *args: object, **kwargs: object) -> str | None:
        return None if name == "node" else real(name)

    shutil.which = without_node  # type: ignore[assignment]
    try:
        return int(gate.main(["--engines", "builtin,axe", "--workdir", str(tmp_path)]))
    finally:
        shutil.which = real  # type: ignore[assignment]


def _mutation_unavailable(tmp_path: Path) -> int:
    gate = _load("mutation_gate")
    root = tmp_path / "mutants"
    root.mkdir(parents=True, exist_ok=True)
    return int(gate.main(["--root", str(root)]))


def _audit_unavailable(tmp_path: Path) -> int:
    """No auditor to run: the advisory service was never reached.

    One attempt and no backoff, because the retry behaviour is
    `tests/test_audit_gate.py`'s subject and this file's subject is the code.
    """

    gate = _load("audit_gate")
    absent = tmp_path / "audit" / "no-such-auditor"
    return int(gate.main(["--auditor", str(absent), "--attempts", "1"]))


def _claims_unavailable(tmp_path: Path) -> int:
    gate = _load("claims_gate")
    root = tmp_path / "claims"
    root.mkdir(parents=True, exist_ok=True)
    return int(gate.main(["--root", str(root)]))


def _fresh_install_unavailable(tmp_path: Path) -> int:
    """No wheel to install: nothing was examined, so nothing is clean."""

    gate = _load("fresh_install_gate")
    dist = tmp_path / "fresh-install" / "dist"
    dist.mkdir(parents=True, exist_ok=True)
    workdir = tmp_path / "fresh-install" / "work"
    return int(gate.main(["--dist", str(dist), "--workdir", str(workdir)]))


def _secret_scan_unavailable(tmp_path: Path) -> int:
    """The shell gate, driven into the same state as the Python ones."""

    repo = _empty_repo(tmp_path / "secret-scan")
    return _scan(repo, GITLEAKS_BIN=str(repo / "absent")).returncode


UNAVAILABLE_CASES: tuple[tuple[str, Callable[[Path], int]], ...] = (
    ("tools/hygiene_gate.py", _hygiene_unavailable),
    ("tools/publication_sweep.py", _sweep_unavailable),
    ("tools/scope_gate.py", _scope_unavailable),
    ("tools/pattern_gate.py", _patterns_unavailable),
    ("tools/i18n_gate.py", _i18n_unavailable),
    ("tools/a11y_gate.py", _a11y_unavailable),
    ("tools/mutation_gate.py", _mutation_unavailable),
    ("tools/claims_gate.py", _claims_unavailable),
    ("tools/audit_gate.py", _audit_unavailable),
    ("tools/fresh_install_gate.py", _fresh_install_unavailable),
    ("tools/secret-scan-full-history.sh", _secret_scan_unavailable),
)


@pytest.mark.parametrize(
    ("name", "drive"), UNAVAILABLE_CASES, ids=[c[0] for c in UNAVAILABLE_CASES]
)
def test_every_gate_exits_two_when_it_examined_nothing(
    tmp_path: Path, name: str, drive: Callable[[Path], int]
) -> None:
    """One contract, asserted of every gate program at once.

    Each is driven into the state where it could not examine what it claims to:
    a repository with nothing in the trees it scans, a locale with no catalog,
    an engine whose runtime is absent.
    """

    assert drive(tmp_path) == UNAVAILABLE, name


def gate_programs() -> set[str]:
    """Every gate program under `tools/`, identified by shape rather than name.

    `glob("*.py")` with a leading-underscore exclusion was three holes at once:
    the one gate written in shell sat outside the contract exactly as it did
    before this module existed, `tools/sub/nested.py` was never walked, and
    `tools/_anything.py` opted itself out by its filename. A gate is recognised
    here by what it is -- a Python module with a `main(argv)` entry point, or an
    executable shell script -- so nothing opts out by being spelled differently.
    """

    root = REPO_ROOT / "tools"
    found: set[str] = set()
    for path in sorted(root.rglob("*")):
        if not path.is_file() or "node_modules" in path.parts:
            continue
        relative = path.relative_to(REPO_ROOT).as_posix()
        if path.suffix == ".py":
            tree = ast.parse(path.read_text(encoding="utf-8"))
            if any(
                isinstance(node, ast.FunctionDef) and node.name == "main"
                for node in tree.body
            ):
                found.add(relative)
        elif path.suffix == ".sh" and os.access(path, os.X_OK):
            found.add(relative)
    return found


def test_every_gate_program_is_covered_by_this_contract() -> None:
    """A gate added later must appear here, or this test is a lie about coverage."""

    assert gate_programs() == {name for name, _ in UNAVAILABLE_CASES}


def test_the_a11y_gate_separates_a_defect_from_an_absent_engine() -> None:
    """Exit 1 and exit 2 must not collapse where the engines live."""

    gate = _load("a11y_gate")
    defect = gate.Finding("contrast", "receipt.html", "ratio below 4.5:1")
    absent = gate.Finding("engine-unavailable", "axe", "node is missing")
    assert gate.exit_code([]) == CLEAN
    assert gate.exit_code([defect]) == FOUND
    assert gate.exit_code([absent]) == UNAVAILABLE
    # A finding set gathered without every requested engine is not a finding
    # set anybody can read as complete, so the refusal wins.
    assert gate.exit_code([defect, absent]) == UNAVAILABLE


def _constructed_rule_ids(path: Path) -> set[str]:
    """Every literal rule id the module hands to ``Finding(...)``.

    Read from the module's own syntax tree rather than from a list in this file.
    A test that restates the constant it is checking passes by construction: the
    previous version of the check below did exactly that, and stayed green while
    four rules that name a failure to run sat outside ``UNAVAILABLE_RULES`` and
    exited 1.
    """

    tree = ast.parse(path.read_text(encoding="utf-8"))
    ids: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        target = node.func
        if not isinstance(target, ast.Name) or target.id != "Finding":
            continue
        if not node.args:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            ids.add(first.value)
    return ids


def test_every_a11y_rule_is_classified_as_a_defect_or_a_failure_to_run() -> None:
    """A rule in neither list has no exit code anybody decided on."""

    gate = _load("a11y_gate")
    constructed = _constructed_rule_ids(REPO_ROOT / "tools" / "a11y_gate.py")
    assert constructed, "no Finding(...) call was found; this check reads nothing"
    declared = gate.UNAVAILABLE_RULES | gate.DEFECT_RULES
    assert constructed - declared == set(), "rule id with no declared exit code"
    assert declared - constructed == set(), "declared rule id the gate never emits"
    assert not (gate.UNAVAILABLE_RULES & gate.DEFECT_RULES)


@pytest.mark.parametrize(
    ("case", "argv"),
    [
        ("no engine requested", ["--engines", ""]),
        ("an engine that does not exist", ["--engines", "bogus"]),
        ("a locale with no published catalog", ["--locale", "zz-ZZ"]),
    ],
)
def test_the_a11y_gate_refuses_every_way_of_examining_nothing(
    tmp_path: Path, case: str, argv: list[str]
) -> None:
    """Driven, not restated: each of these answered 1 before 2026-08-31.

    The first two reported a finding and exit 1; the third left an unhandled
    ``ContextSafeError`` traceback, which the shell also reads as 1. All three
    are the gate saying it did not examine, which is exit 2.
    """

    gate = _load("a11y_gate")
    assert gate.main([*argv, "--workdir", str(tmp_path)]) == UNAVAILABLE, case


def test_the_a11y_gate_still_answers_one_for_a_real_defect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The refusals above must not have swallowed the ordinary finding path."""

    gate = _load("a11y_gate")
    monkeypatch.setattr(gate, "MINIMUM_CONTRAST", 21.5)
    assert gate.main(["--engines", "builtin", "--workdir", str(tmp_path)]) == FOUND


def test_an_axe_harness_that_returns_no_page_is_not_a_clean_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`ok: true` is the harness saying it started, not that it looked.

    A harness answering `{"ok": true, "pages": []}` produced zero findings and
    `ran=True`, so axe was recorded as executed over nothing.
    """

    gate = _load("a11y_gate")
    monkeypatch.setattr(gate.shutil, "which", lambda name: "/usr/bin/node")
    monkeypatch.setattr(gate, "HARNESS_MODULES", tmp_path)
    monkeypatch.setattr(
        gate.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(
            a[0] if a else [], 0, '{"ok": true, "pages": []}', ""
        ),
    )
    subject = gate.Subject(
        name="receipt.en-US.html",
        locale="en-US",
        html="<!DOCTYPE html><html></html>",
        payload_sha256="0" * 64,
        case_id="c",
        required_text=(),
    )
    findings, _undetermined, ran = gate.run_axe([subject], tmp_path)
    assert ran is True
    assert [f.rule for f in findings] == ["engine-examined-nothing"]
    assert gate.exit_code(findings) == UNAVAILABLE
