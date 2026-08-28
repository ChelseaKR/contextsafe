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
    """

    path = directory / "gitleaks"
    path.write_text(
        "#!/usr/bin/env bash\n"
        'if [ "$1" = "version" ]; then\n'
        f'  echo "{version}"\n'
        "  exit 0\n"
        "fi\n"
        f"exit {detect_exit}\n",
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
    _git(repo, "add", "--", "README.md")
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


UNAVAILABLE_CASES: tuple[tuple[str, Callable[[Path], int]], ...] = (
    ("hygiene_gate", _hygiene_unavailable),
    ("publication_sweep", _sweep_unavailable),
    ("scope_gate", _scope_unavailable),
    ("i18n_gate", _i18n_unavailable),
    ("a11y_gate", _a11y_unavailable),
    ("mutation_gate", _mutation_unavailable),
)


@pytest.mark.parametrize(
    ("name", "drive"), UNAVAILABLE_CASES, ids=[c[0] for c in UNAVAILABLE_CASES]
)
def test_every_gate_exits_two_when_it_examined_nothing(
    tmp_path: Path, name: str, drive: Callable[[Path], int]
) -> None:
    """One contract, asserted of all five gate programs at once.

    Each is driven into the state where it could not examine what it claims to:
    a repository with nothing in the trees it scans, a locale with no catalog,
    an engine whose runtime is absent.
    """

    assert drive(tmp_path) == UNAVAILABLE, name


def test_every_gate_program_is_covered_by_this_contract() -> None:
    """A gate added later must appear here, or this test is a lie about coverage."""

    programs = {
        path.stem
        for path in (REPO_ROOT / "tools").glob("*.py")
        if not path.stem.startswith("_")
    }
    assert programs == {name for name, _ in UNAVAILABLE_CASES}


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


def test_the_unavailable_rules_are_the_ones_that_name_a_failure_to_run() -> None:
    gate = _load("a11y_gate")
    expected = frozenset(
        {
            "check-examined-nothing",
            "engine-examined-nothing",
            "engine-not-executed",
            "engine-unavailable",
        }
    )
    assert expected == gate.UNAVAILABLE_RULES
