"""Tests for the runtime guard on caller-supplied write targets."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.config_manager import project_root, save_config
from src.database import connect
from src.write_guard import outside_code_folders


def test_allows_a_temp_path(tmp_path: Path) -> None:
    target = tmp_path / "x.db"
    assert outside_code_folders(target) == target.resolve()


def test_allows_gitignored_state_at_the_repo_root() -> None:
    root = project_root()
    assert outside_code_folders(root / "data" / "expenses.db") == (root / "data" / "expenses.db").resolve()
    assert outside_code_folders(root / "config.json") == (root / "config.json").resolve()


@pytest.mark.parametrize("folder", ["src", "app", "scripts"])
def test_refuses_a_code_folder(folder: str) -> None:
    with pytest.raises(ValueError, match="code folder"):
        outside_code_folders(project_root() / folder / "state.db")


def test_connect_refuses_a_db_beside_the_code() -> None:
    with pytest.raises(ValueError, match="code folder"):
        connect(project_root() / "src" / "stray.db")


def test_save_config_refuses_a_path_beside_the_code() -> None:
    with pytest.raises(ValueError, match="code folder"):
        save_config({}, project_root() / "app" / "config.json")
