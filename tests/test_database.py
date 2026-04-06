"""Tests for database migration and backfill helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.database import (
    backfill_account_type_from_config,
    connect,
    init_db,
    insert_transactions,
    transaction_hash,
)
from src.ingest import _build_source_account_type_map


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_row(source: str, date: str = "2024-01-01", amount: float = -10.0, desc: str = "test") -> dict:
    return {
        "source": source,
        "date": date,
        "description": desc,
        "amount": amount,
        "hash": transaction_hash(source, date, amount, desc),
    }


# ---------------------------------------------------------------------------
# backfill_account_type_from_config
# ---------------------------------------------------------------------------

def test_backfill_sets_joint_for_joint_source(tmp_path: Path) -> None:
    """Historical joint rows (defaulted to 'joint') stay 'joint' after backfill."""
    conn = connect(tmp_path / "test.db")
    init_db(conn)
    insert_transactions(conn, [_make_row("caixabank_joint")])

    n = backfill_account_type_from_config(conn, {"caixabank_joint": "joint"})
    assert n == 0  # already correct — no rows needed updating

    row = conn.execute("SELECT account_type FROM transactions").fetchone()
    assert row["account_type"] == "joint"
    conn.close()


def test_backfill_corrects_personal_source(tmp_path: Path) -> None:
    """Rows from a source now configured as personal must be updated."""
    conn = connect(tmp_path / "test.db")
    init_db(conn)
    # Simulate historical import: row was inserted with account_type='joint' (the default)
    insert_transactions(conn, [_make_row("caixabank_personal")])

    row_before = conn.execute("SELECT account_type FROM transactions").fetchone()
    assert row_before["account_type"] == "joint"

    n = backfill_account_type_from_config(conn, {"caixabank_personal": "personal"})
    assert n == 1

    row_after = conn.execute("SELECT account_type FROM transactions").fetchone()
    assert row_after["account_type"] == "personal"
    conn.close()


def test_backfill_handles_multiple_sources(tmp_path: Path) -> None:
    """Mixed joint/personal sources are each backfilled correctly."""
    conn = connect(tmp_path / "test.db")
    init_db(conn)
    rows = [
        _make_row("caixabank_joint", desc="joint tx"),
        _make_row("caixabank_personal", date="2024-01-02", desc="personal tx"),
    ]
    insert_transactions(conn, rows)

    source_map = {"caixabank_joint": "joint", "caixabank_personal": "personal"}
    n = backfill_account_type_from_config(conn, source_map)
    # joint row already correct (0 updates), personal row needs correction (1 update)
    assert n == 1

    joint_row = conn.execute(
        "SELECT account_type FROM transactions WHERE source = 'caixabank_joint'"
    ).fetchone()
    personal_row = conn.execute(
        "SELECT account_type FROM transactions WHERE source = 'caixabank_personal'"
    ).fetchone()
    assert joint_row["account_type"] == "joint"
    assert personal_row["account_type"] == "personal"
    conn.close()


def test_backfill_empty_map_returns_zero(tmp_path: Path) -> None:
    """An empty source map is a no-op."""
    conn = connect(tmp_path / "test.db")
    init_db(conn)
    insert_transactions(conn, [_make_row("some_source")])
    assert backfill_account_type_from_config(conn, {}) == 0
    conn.close()


def test_backfill_idempotent(tmp_path: Path) -> None:
    """Calling backfill twice with the same map only updates rows once."""
    conn = connect(tmp_path / "test.db")
    init_db(conn)
    insert_transactions(conn, [_make_row("caixabank_personal")])

    n1 = backfill_account_type_from_config(conn, {"caixabank_personal": "personal"})
    n2 = backfill_account_type_from_config(conn, {"caixabank_personal": "personal"})
    assert n1 == 1
    assert n2 == 0  # second call: already correct, nothing to update
    conn.close()


# ---------------------------------------------------------------------------
# _build_source_account_type_map
# ---------------------------------------------------------------------------

def test_build_source_map_joint() -> None:
    cfg = {
        "accounts": {"acct_joint": {"type": "shared"}},
        "bank_imports": {
            "sources": [{"id": "caixabank_joint", "account_key": "acct_joint", "file": "f.xls", "parser": "caixabank"}]
        },
    }
    m = _build_source_account_type_map(cfg)
    assert m == {"caixabank_joint": "joint"}


def test_build_source_map_personal() -> None:
    cfg = {
        "accounts": {"acct_personal": {"type": "personal"}},
        "bank_imports": {
            "sources": [{"id": "caixabank_personal", "account_key": "acct_personal", "file": "f.xls", "parser": "caixabank"}]
        },
    }
    m = _build_source_account_type_map(cfg)
    assert m == {"caixabank_personal": "personal"}


def test_build_source_map_mixed() -> None:
    cfg = {
        "accounts": {
            "acct_joint": {"type": "shared"},
            "acct_personal": {"type": "personal"},
        },
        "bank_imports": {
            "sources": [
                {"id": "src_joint", "account_key": "acct_joint", "file": "j.xls", "parser": "caixabank"},
                {"id": "src_personal", "account_key": "acct_personal", "file": "p.xls", "parser": "caixabank"},
            ]
        },
    }
    m = _build_source_account_type_map(cfg)
    assert m == {"src_joint": "joint", "src_personal": "personal"}


def test_build_source_map_no_sources() -> None:
    cfg = {"accounts": {}, "bank_imports": {}}
    assert _build_source_account_type_map(cfg) == {}


def test_build_source_map_missing_account_key_defaults_to_joint() -> None:
    """Source without account_key or with unknown key defaults to 'joint'."""
    cfg = {
        "accounts": {},
        "bank_imports": {
            "sources": [{"id": "unknown_src", "file": "f.xls", "parser": "caixabank"}]
        },
    }
    m = _build_source_account_type_map(cfg)
    assert m == {"unknown_src": "joint"}
