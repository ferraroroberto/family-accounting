"""End-to-end: parse both bank files, import into temp DB, classification run."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.classifier import classify_full
from src.config_manager import load_config
from src.database import connect, count_transactions, init_db, reclassify_all
from src.ingest import import_all_configured


ROOT = Path(__file__).resolve().parents[1]


def test_import_and_classify_run(tmp_path: Path) -> None:
    cfg_path = ROOT / "config.json"
    if not cfg_path.is_file():
        pytest.skip("config.json missing")
    cfg = load_config(cfg_path)
    if not (cfg.get("bank_imports") or {}).get("sources"):
        pytest.skip("no bank_imports")

    xls = ROOT / "tmp" / "input" / "caixabank_joint.xls"
    csv = ROOT / "tmp" / "input" / "revolut_joint.csv"
    if not xls.is_file() or not csv.is_file():
        pytest.skip("input fixtures missing")

    db = tmp_path / "test_expenses.db"
    res = import_all_configured(cfg=cfg, db_path=db)
    assert res["added"] > 0

    conn = connect(db)
    init_db(conn)
    n = count_transactions(conn)

    def _fn(desc: str, amt: float):
        return classify_full(desc, amt, cfg)

    updated = reclassify_all(conn, _fn)
    conn.close()

    assert n > 0
    assert updated["rows_touched"] == n
