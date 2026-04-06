"""SQLite persistence for transactions and import metadata."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from collections import Counter
from typing import Any

from src.config_manager import project_root


def default_db_path() -> Path:
    return project_root() / "data" / "expenses.db"


SCHEMA = """
CREATE TABLE IF NOT EXISTS transactions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source          TEXT NOT NULL,
    date            TEXT NOT NULL,
    value_date      TEXT,
    description     TEXT NOT NULL,
    amount          REAL NOT NULL,
    balance         REAL,
    category        TEXT DEFAULT 'other',
    direction       TEXT DEFAULT 'expense',
    partner         TEXT,
    manual_override INTEGER DEFAULT 0,
    yyyymm          TEXT,
    rule            TEXT DEFAULT 'default',
    account_type    TEXT DEFAULT 'joint',
    extra_json      TEXT,
    cb_oficina          TEXT,
    cb_divisa           TEXT,
    cb_f_operacion      TEXT,
    cb_f_valor          TEXT,
    cb_ingreso          REAL,
    cb_gasto            REAL,
    cb_saldo_pos        REAL,
    cb_saldo_neg        REAL,
    cb_concepto_comun   TEXT,
    cb_concepto_propio  TEXT,
    cb_referencia1      TEXT,
    cb_referencia2      TEXT,
    cb_cc1              TEXT,
    cb_cc2              TEXT,
    cb_cc3              TEXT,
    cb_cc4              TEXT,
    cb_cc5              TEXT,
    cb_cc6              TEXT,
    cb_cc7              TEXT,
    cb_cc8              TEXT,
    cb_cc9              TEXT,
    cb_cc10             TEXT,
    hash            TEXT UNIQUE NOT NULL,
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS import_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT DEFAULT (datetime('now')),
    source          TEXT NOT NULL,
    filename        TEXT,
    records_added   INTEGER DEFAULT 0,
    records_skipped INTEGER DEFAULT 0,
    date_range_start TEXT,
    date_range_end   TEXT
);

CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(date);
CREATE INDEX IF NOT EXISTS idx_transactions_category ON transactions(category);
CREATE INDEX IF NOT EXISTS idx_transactions_yyyymm ON transactions(yyyymm);
CREATE INDEX IF NOT EXISTS idx_transactions_hash ON transactions(hash);
"""


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or default_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_rule_column(conn: sqlite3.Connection) -> None:
    cur = conn.execute("PRAGMA table_info(transactions)")
    cols = {row[1] for row in cur.fetchall()}
    if "rule" not in cols:
        conn.execute("ALTER TABLE transactions ADD COLUMN rule TEXT")


def _ensure_extra_json_column(conn: sqlite3.Connection) -> None:
    cur = conn.execute("PRAGMA table_info(transactions)")
    cols = {row[1] for row in cur.fetchall()}
    if "extra_json" not in cols:
        conn.execute("ALTER TABLE transactions ADD COLUMN extra_json TEXT")


def _ensure_account_type_column(conn: sqlite3.Connection) -> None:
    cur = conn.execute("PRAGMA table_info(transactions)")
    cols = {row[1] for row in cur.fetchall()}
    if "account_type" not in cols:
        conn.execute("ALTER TABLE transactions ADD COLUMN account_type TEXT DEFAULT 'joint'")
        conn.execute("UPDATE transactions SET account_type = 'joint' WHERE account_type IS NULL")


# Nullable CaixaBank-only columns (Revolut / compact layout leave NULL).
_CB_DETAIL_COLS: tuple[tuple[str, str], ...] = (
    ("cb_oficina", "TEXT"),
    ("cb_divisa", "TEXT"),
    ("cb_f_operacion", "TEXT"),
    ("cb_f_valor", "TEXT"),
    ("cb_ingreso", "REAL"),
    ("cb_gasto", "REAL"),
    ("cb_saldo_pos", "REAL"),
    ("cb_saldo_neg", "REAL"),
    ("cb_concepto_comun", "TEXT"),
    ("cb_concepto_propio", "TEXT"),
    ("cb_referencia1", "TEXT"),
    ("cb_referencia2", "TEXT"),
    *(("cb_cc%d" % i, "TEXT") for i in range(1, 11)),
)


def _ensure_caixabank_detail_columns(conn: sqlite3.Connection) -> None:
    cur = conn.execute("PRAGMA table_info(transactions)")
    cols = {row[1] for row in cur.fetchall()}
    for name, typ in _CB_DETAIL_COLS:
        if name not in cols:
            conn.execute("ALTER TABLE transactions ADD COLUMN %s %s" % (name, typ))


def _migrate_v1_lowercase_and_hashes(conn: sqlite3.Connection) -> None:
    """One-time: lowercase descriptions, recompute hashes (canonical dedup)."""
    cur = conn.execute("SELECT id, source, date, amount, description FROM transactions")
    rows = cur.fetchall()
    now = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    for row in rows:
        desc = (row["description"] or "").strip().lower()
        h = transaction_hash(row["source"], row["date"], row["amount"], desc)
        try:
            conn.execute(
                "UPDATE transactions SET description = ?, hash = ?, updated_at = ? WHERE id = ?",
                (desc, h, now, row["id"]),
            )
        except sqlite3.IntegrityError:
            conn.execute(
                "UPDATE transactions SET description = ?, updated_at = ? WHERE id = ?",
                (desc, now, row["id"]),
            )


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()
    _ensure_rule_column(conn)
    _ensure_extra_json_column(conn)
    _ensure_account_type_column(conn)
    _ensure_caixabank_detail_columns(conn)
    conn.commit()
    ver = conn.execute("PRAGMA user_version").fetchone()[0]
    if ver < 1:
        _migrate_v1_lowercase_and_hashes(conn)
        conn.commit()
        conn.execute("PRAGMA user_version = 1")
        conn.commit()
    conn.execute(
        "UPDATE transactions SET rule = 'default' WHERE rule IS NULL OR trim(coalesce(rule, '')) = ''"
    )
    conn.commit()


def transaction_hash(source: str, date_str: str, amount: float, description: str) -> str:
    import hashlib

    d = description.strip().lower()
    key = f"{source}|{date_str}|{amount:.6f}|{d}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def insert_transactions(
    conn: sqlite3.Connection,
    rows: list[dict[str, Any]],
) -> tuple[int, int]:
    """Insert rows; skip duplicates by hash. Returns (added, skipped)."""
    added = 0
    skipped = 0
    now = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    for r in rows:
        h = r["hash"]
        try:
            conn.execute(
                """
                INSERT INTO transactions (
                    source, date, value_date, description, amount, balance,
                    category, direction, partner, manual_override, yyyymm, rule, account_type, extra_json,
                    cb_oficina, cb_divisa, cb_f_operacion, cb_f_valor,
                    cb_ingreso, cb_gasto, cb_saldo_pos, cb_saldo_neg,
                    cb_concepto_comun, cb_concepto_propio, cb_referencia1, cb_referencia2,
                    cb_cc1, cb_cc2, cb_cc3, cb_cc4, cb_cc5,
                    cb_cc6, cb_cc7, cb_cc8, cb_cc9, cb_cc10,
                    hash, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    r["source"],
                    r["date"],
                    r.get("value_date"),
                    r["description"],
                    r["amount"],
                    r.get("balance"),
                    r.get("category", "other"),
                    r.get("direction", "expense"),
                    r.get("partner"),
                    r.get("manual_override", 0),
                    r.get("yyyymm"),
                    r.get("rule", "default"),
                    r.get("account_type", "joint"),
                    r.get("extra_json"),
                    r.get("cb_oficina"),
                    r.get("cb_divisa"),
                    r.get("cb_f_operacion"),
                    r.get("cb_f_valor"),
                    r.get("cb_ingreso"),
                    r.get("cb_gasto"),
                    r.get("cb_saldo_pos"),
                    r.get("cb_saldo_neg"),
                    r.get("cb_concepto_comun"),
                    r.get("cb_concepto_propio"),
                    r.get("cb_referencia1"),
                    r.get("cb_referencia2"),
                    r.get("cb_cc1"),
                    r.get("cb_cc2"),
                    r.get("cb_cc3"),
                    r.get("cb_cc4"),
                    r.get("cb_cc5"),
                    r.get("cb_cc6"),
                    r.get("cb_cc7"),
                    r.get("cb_cc8"),
                    r.get("cb_cc9"),
                    r.get("cb_cc10"),
                    h,
                    now,
                ),
            )
            added += 1
        except sqlite3.IntegrityError:
            skipped += 1
    conn.commit()
    return added, skipped


def fetch_all_transactions(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    cur = conn.execute(
        "SELECT * FROM transactions ORDER BY date ASC, id ASC"
    )
    return list(cur.fetchall())


def count_transactions(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()
    return int(row[0]) if row else 0


def reclassify_all(
    conn: sqlite3.Connection,
    classify_fn,
) -> dict[str, Any]:
    """Re-run classifier on rows without manual_override. Returns counts and category changes."""
    cur = conn.execute(
        """
        SELECT id, description, amount, manual_override, category, direction, rule, account_type
        FROM transactions WHERE manual_override = 0
        """
    )
    rows = cur.fetchall()
    updated = 0
    changed = 0
    transitions: Counter[str] = Counter()
    transition_rows: dict[str, list[dict[str, Any]]] = {}
    new_categories: Counter[str] = Counter()
    now = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    for row in rows:
        old_cat, old_dir, old_rule = row["category"], row["direction"], row["rule"]
        acct_type = row["account_type"] if row["account_type"] else "joint"
        out = classify_fn(row["description"], row["amount"], acct_type)
        if len(out) == 4:
            cat, direction, rule, partner = out
        elif len(out) == 3:
            cat, direction, rule = out  # type: ignore[misc]
            partner = None
        else:
            cat, direction = out  # type: ignore[misc]
            rule = "default"
            partner = None
        new_categories[cat] += 1
        if cat != old_cat or direction != old_dir or (old_rule or "") != (rule or ""):
            changed += 1
            key = f"{old_cat}/{old_dir} → {cat}/{direction}"
            transitions[key] += 1
            transition_rows.setdefault(key, []).append(
                {"id": row["id"], "description": row["description"], "amount": row["amount"]}
            )
        conn.execute(
            "UPDATE transactions SET category = ?, direction = ?, rule = ?, partner = ?, updated_at = ? WHERE id = ?",
            (cat, direction, rule, partner, now, row["id"]),
        )
        updated += 1
    conn.commit()
    return {
        "rows_touched": updated,
        "rows_changed": changed,
        "transitions": dict(transitions),
        "transition_rows": transition_rows,
        "category_counts": dict(new_categories),
    }


def last_data_update_iso(conn: sqlite3.Connection) -> str | None:
    """Latest activity: max of transaction updated_at and import_log timestamp."""
    u1 = conn.execute("SELECT MAX(updated_at) FROM transactions").fetchone()[0]
    u2 = conn.execute("SELECT MAX(timestamp) FROM import_log").fetchone()[0]
    candidates = [x for x in (u1, u2) if x]
    if not candidates:
        return None
    return max(candidates)


def per_source_date_counts(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    cur = conn.execute(
        """
        SELECT source AS source_id,
               MIN(date) AS date_from,
               MAX(date) AS date_to,
               COUNT(*) AS transaction_count
        FROM transactions
        GROUP BY source
        ORDER BY source
        """
    )
    return [dict(row) for row in cur.fetchall()]


def log_import(
    conn: sqlite3.Connection,
    source: str,
    filename: str | None,
    added: int,
    skipped: int,
    dr_start: str | None,
    dr_end: str | None,
) -> None:
    conn.execute(
        """
        INSERT INTO import_log (source, filename, records_added, records_skipped, date_range_start, date_range_end)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (source, filename, added, skipped, dr_start, dr_end),
    )
    conn.commit()
