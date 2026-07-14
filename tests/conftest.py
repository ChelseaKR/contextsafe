"""Shared copies of the bundled synthetic reference inputs."""

import json
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "fixtures" / "reference"


def _read_json(name: str) -> dict[str, Any]:
    value = json.loads((REFERENCE / name).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


@pytest.fixture
def case_json() -> dict[str, Any]:
    """Return a fresh canonical case object."""

    return _read_json("case.json")


@pytest.fixture
def observations_json() -> dict[str, Any]:
    """Return a fresh canonical observation-set object."""

    return _read_json("observations.json")


@pytest.fixture
def rules_json() -> dict[str, Any]:
    """Return a fresh rule-set object."""

    return _read_json("rules.json")
