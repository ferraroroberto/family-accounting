"""Pins that every adopted scaffold ratchet is vendored, enabled and run by the ship gate."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# The ratchets this repo runs as gate stages beyond the structure ratchet's own tests.
RATCHETS = ["static_ratchet", "docs_ratchet", "comment_ratchet", "conventions_ratchet"]


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


def _gate_ratchets() -> list[str]:
    """Every ratchet script the ship gate runs as a stage, read from the gate itself."""
    gate = (ROOT / "scripts" / "verify-before-ship.ps1").read_text(encoding="utf-8")
    return sorted(set(re.findall(r'"scripts/(\w+_ratchet)\.py"', gate)))


@pytest.mark.parametrize("name", _gate_ratchets())
def test_docs_name_every_gate_ratchet(name: str) -> None:
    # A ship that fails on a ratchet the docs never mention is undiagnosable, so the
    # agent rubric and the layout doc must each name every stage the gate runs.
    assert f"scripts/{name}.py" in (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    layout = (ROOT / "docs" / "layout.md").read_text(encoding="utf-8")
    assert f"{name}.py " in layout, f"layout tree lacks {name}"
    assert f"scripts\\{name}.py" in layout, f"layout Verify block lacks {name}"


def test_claude_md_names_every_enabled_convention_rule(fleet: dict) -> None:
    text = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    missing = [rule for rule in fleet["conventions_ratchet"]["rules"] if f"`{rule}`" not in text]
    assert not missing, f"CLAUDE.md does not name enabled conventions rules: {missing}"


@pytest.mark.parametrize("name", RATCHETS)
def test_gate_runs_ratchet_and_fails_on_any_nonzero_exit(name: str) -> None:
    gate = (ROOT / "scripts" / "verify-before-ship.ps1").read_text(encoding="utf-8")
    assert f'"scripts/{name}.py"' in gate
    # Invoke-Stage fails the gate on every non-zero exit, so exit 3 (not confirmed) cannot pass.
    assert "$LASTEXITCODE -ne 0" in gate
