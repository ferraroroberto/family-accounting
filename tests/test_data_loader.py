"""Tests for the Streamlit-cached transaction frames in app.data_loader."""

from __future__ import annotations

import ast
import os
from pathlib import Path

from app.data_loader import cached_raw_transactions_df, clear_data_caches
from src.database import connect, init_db, insert_transactions, transaction_hash


def _row(desc: str) -> dict:
    return {
        "source": "caixabank_joint",
        "date": "2024-01-01",
        "description": desc,
        "amount": -10.0,
        "hash": transaction_hash("caixabank_joint", "2024-01-01", -10.0, desc, "n0"),
    }


def test_out_of_app_write_busts_the_frame_cache(tmp_path: Path) -> None:
    """A write made by another process (CLI import) shows up without clearing the cache."""
    db = tmp_path / "test.db"
    clear_data_caches()
    conn = connect(db)
    init_db(conn)
    insert_transactions(conn, [_row("first")])
    conn.close()
    assert len(cached_raw_transactions_df(db)) == 1

    conn = connect(db)
    insert_transactions(conn, [_row("second")])
    conn.close()
    # Same-tick writes can share an mtime on coarse filesystems; force a distinct stamp.
    stat = db.stat()
    os.utime(db, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))

    assert len(cached_raw_transactions_df(db)) == 2
    clear_data_caches()


def _is_cache_data(dec: ast.expr) -> bool:
    target = dec.func if isinstance(dec, ast.Call) else dec
    return isinstance(target, ast.Attribute) and target.attr == "cache_data"


def test_cache_data_functions_have_no_underscore_parameters() -> None:
    """Streamlit drops underscore-prefixed parameters from the cache key, so they never bust it."""
    offenders = []
    for path in sorted(Path("app").glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.FunctionDef) and any(map(_is_cache_data, node.decorator_list)):
                offenders += [
                    f"{path}:{node.name}({a.arg})" for a in node.args.args if a.arg.startswith("_")
                ]
    assert offenders == []
