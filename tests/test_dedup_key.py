"""The dedup hash keeps two real same-day identical payments and still dedups overlapping exports."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from src.database import (
    connect,
    init_db,
    insert_transactions,
    transaction_hash,
)
from src.ingest import load_and_parse_source

_HEADER = "Type,Product,Started Date,Completed Date,Description,Amount,Fee,Currency,State,Balance\n"


def _csv_line(day: str, desc: str, amount: float, balance: float) -> str:
    return f"CARD_PAYMENT,Current,{day} 08:00:00,{day} 08:01:00,{desc},{amount},0.00,EUR,COMPLETED,{balance}\n"


def _import(tmp_path: Path, name: str, lines: list[str], conn: sqlite3.Connection) -> tuple[int, int]:
    (tmp_path / name).write_text(_HEADER + "".join(lines), encoding="utf-8")
    cfg = {"bank_imports": {"base_directory": str(tmp_path)}, "accounts": {"rev": {"type": "shared"}}}
    spec = {"id": "revolut_joint", "account_key": "rev", "file": name, "parser": "revolut"}
    return insert_transactions(conn, load_and_parse_source(cfg, spec))


def test_two_identical_same_day_payments_are_both_kept(tmp_path: Path) -> None:
    conn = connect(tmp_path / "t.db")
    init_db(conn)
    added, skipped = _import(
        tmp_path, "a.csv",
        [_csv_line("2026-05-02", "Parking", -2.5, 100.0), _csv_line("2026-05-02", "Parking", -2.5, 97.5)],
        conn,
    )
    assert (added, skipped) == (2, 0)
    conn.close()


def test_overlapping_export_adds_nothing(tmp_path: Path) -> None:
    conn = connect(tmp_path / "t.db")
    init_db(conn)
    first = [
        _csv_line("2026-05-02", "Parking", -2.5, 100.0),
        _csv_line("2026-05-02", "Parking", -2.5, 97.5),
        _csv_line("2026-05-03", "Shop", -9.0, 88.5),
    ]
    _import(tmp_path, "a.csv", first, conn)
    added, skipped = _import(tmp_path, "b.csv", first + [_csv_line("2026-05-04", "Cafe", -3.0, 85.5)], conn)
    assert (added, skipped) == (1, 3)
    conn.close()


def test_rows_without_balance_are_told_apart_by_occurrence() -> None:
    from src.database import assign_hashes

    def rows() -> list[dict]:
        return [
            {"source": "s", "date": "2026-05-02", "amount": -2.5, "description": "parking", "balance": None},
            {"source": "s", "date": "2026-05-02", "amount": -2.5, "description": "parking", "balance": None},
        ]

    first, again = rows(), rows()
    assign_hashes(first)
    assign_hashes(again)
    assert first[0]["hash"] != first[1]["hash"]
    assert [r["hash"] for r in first] == [r["hash"] for r in again]


def test_migration_rehashes_old_rows_so_reimport_adds_nothing(tmp_path: Path) -> None:
    db = tmp_path / "t.db"
    conn = connect(db)
    init_db(conn)
    lines = [_csv_line("2026-05-02", "Parking", -2.5, 100.0), _csv_line("2026-05-03", "Shop", -9.0, 91.0)]
    _import(tmp_path, "a.csv", lines, conn)
    # Put the DB back in its pre-migration state: day-level hash, version 1.
    legacy = "{}|{}|{:.6f}|{}"
    for row in conn.execute("SELECT id, source, date, amount, description FROM transactions").fetchall():
        key = legacy.format(row["source"], row["date"], row["amount"], row["description"])
        conn.execute("UPDATE transactions SET hash = ? WHERE id = ?", (hashlib.sha256(key.encode()).hexdigest(), row["id"]))
    conn.execute("PRAGMA user_version = 1")
    conn.commit()
    conn.close()

    conn = connect(db)
    init_db(conn)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
    added, skipped = _import(tmp_path, "a.csv", lines, conn)
    assert (added, skipped) == (0, 2)
    conn.close()


def test_rows_sharing_a_balance_are_still_both_kept(tmp_path: Path) -> None:
    """A bank can report one balance for a batch of identical postings."""
    conn = connect(tmp_path / "t.db")
    init_db(conn)
    batch = [_csv_line("2026-05-02", "Refund", 8.0, 958.24), _csv_line("2026-05-02", "Refund", 8.0, 958.24)]
    assert _import(tmp_path, "a.csv", batch, conn) == (2, 0)
    assert _import(tmp_path, "b.csv", batch + [_csv_line("2026-05-03", "Shop", -9.0, 949.24)], conn) == (1, 2)
    conn.close()


def test_hash_depends_on_the_discriminator() -> None:
    a = transaction_hash("s", "2026-05-02", -2.5, "parking", "b100.00")
    b = transaction_hash("s", "2026-05-02", -2.5, "parking", "b97.50")
    assert a != b
