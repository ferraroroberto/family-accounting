"""Resolution of ``bank_imports.sources[].file`` entries, including globs."""

from pathlib import Path

import pytest

from src.config_manager import resolve_source_file


def _cfg(base: Path) -> dict:
    return {"bank_imports": {"base_directory": str(base)}}


def test_plain_filename_resolves_unchanged(tmp_path: Path) -> None:
    (tmp_path / "export.csv").write_text("x", encoding="utf-8")
    assert resolve_source_file(_cfg(tmp_path), "export.csv") == tmp_path / "export.csv"


def test_glob_picks_the_newest_match(tmp_path: Path) -> None:
    old = tmp_path / "caixabank_joint_sepa_2026-01-01_2026-04-03.XLS"
    new = tmp_path / "caixabank_joint_sepa_2026-04-01_2026-08-24.XLS"
    for f in (old, new):
        f.write_text("x", encoding="utf-8")
    import os

    os.utime(old, (1_700_000_000, 1_700_000_000))
    os.utime(new, (1_800_000_000, 1_800_000_000))

    got = resolve_source_file(_cfg(tmp_path), "caixabank_joint_sepa_2*.XLS")
    assert got == new


def test_glob_ignores_non_matching_siblings(tmp_path: Path) -> None:
    """The archived bulk exports must not be picked up by the incremental pattern."""
    (tmp_path / "caixabank_joint_sepa_all.XLS").write_text("x", encoding="utf-8")
    (tmp_path / "caixabank_joint_sepa_history.XLS").write_text("x", encoding="utf-8")
    wanted = tmp_path / "caixabank_joint_sepa_2026-04-01_2026-08-24.XLS"
    wanted.write_text("x", encoding="utf-8")

    assert resolve_source_file(_cfg(tmp_path), "caixabank_joint_sepa_2*.XLS") == wanted


def test_unmatched_glob_raises_rather_than_importing_nothing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="No file matching"):
        resolve_source_file(_cfg(tmp_path), "missing_*.csv")


def test_joint_and_personal_revolut_patterns_do_not_cross_match(tmp_path: Path) -> None:
    joint = tmp_path / "joint_account-statement_2026-04-01_2026-08-24.csv"
    personal = tmp_path / "personal_account-statement_2026-04-01_2026-08-24.csv"
    for f in (joint, personal):
        f.write_text("x", encoding="utf-8")

    cfg = _cfg(tmp_path)
    assert resolve_source_file(cfg, "joint_account-statement_*.csv") == joint
    assert resolve_source_file(cfg, "personal_account-statement_*.csv") == personal
