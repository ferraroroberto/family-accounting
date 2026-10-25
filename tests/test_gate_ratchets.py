"""Pins that every adopted scaffold ratchet is vendored, enabled and run by the ship gate."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# The ratchets this repo runs as gate stages beyond the structure ratchet's own tests.
RATCHETS = ["static_ratchet", "docs_ratchet", "comment_ratchet"]


@pytest.fixture(scope="module")
def fleet() -> dict:
    return tomllib.loads((ROOT / ".fleet.toml").read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", RATCHETS)
def test_ratchet_is_vendored_and_enabled(fleet: dict, name: str) -> None:
    entry = fleet["vendored"][name]
    assert (ROOT / entry["dest"]).is_file()
    assert len(entry["sha"]) == 40
    table = fleet[name]
    assert table["enabled"] is True
    assert (ROOT / table["baseline"]).is_file()


@pytest.mark.parametrize("name", RATCHETS)
def test_gate_runs_ratchet_and_fails_on_any_nonzero_exit(name: str) -> None:
    gate = (ROOT / "scripts" / "verify-before-ship.ps1").read_text(encoding="utf-8")
    assert f'"scripts/{name}.py"' in gate
    # Invoke-Stage fails the gate on every non-zero exit, so exit 3 (not confirmed) cannot pass.
    assert "$LASTEXITCODE -ne 0" in gate
