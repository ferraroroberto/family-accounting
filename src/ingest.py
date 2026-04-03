"""Load bank files from config and import into SQLite."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from src.classifier import classify_full
from src.config_manager import load_config, resolve_path
from src.database import connect, init_db, insert_transactions, log_import, transaction_hash
from src.parsers.caixabank import parse_caixabank_file
from src.parsers.revolut import parse_revolut_csv

from src.logger import get_logger

log = get_logger(__name__)


PARSERS = {
    "caixabank": parse_caixabank_file,
    "revolut": parse_revolut_csv,
}


def load_and_parse_source(
    cfg: dict[str, Any],
    source_spec: dict[str, Any],
) -> list[dict[str, Any]]:
    rel = source_spec["file"]
    path = resolve_path(cfg, rel)
    if not path.is_file():
        raise FileNotFoundError(f"Bank file not found: {path}")
    parser_name = source_spec["parser"]
    parser = PARSERS[parser_name]
    source_id = source_spec["id"]
    layout = source_spec.get("layout") or {}
    rows = parser(path, source_id, layout)
    for r in rows:
        desc = (r["description"] or "").strip().lower()
        r["description"] = desc
        r["hash"] = transaction_hash(source_id, r["date"], r["amount"], desc)
        cat, direction, rule, partner = classify_full(desc, r["amount"], cfg)
        r["category"] = cat
        r["direction"] = direction
        r["rule"] = rule
        r["partner"] = partner
        r["manual_override"] = 0
    return rows


def import_all_configured(
    cfg: dict[str, Any] | None = None,
    db_path: Path | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config()
    bi = cfg.get("bank_imports") or {}
    sources = bi.get("sources") or []
    conn = connect(db_path)
    init_db(conn)
    total_added = 0
    total_skipped = 0
    details: list[dict[str, Any]] = []
    categories_total: Counter[str] = Counter()
    directions_total: Counter[str] = Counter()
    for spec in sources:
        rows = load_and_parse_source(cfg, spec)
        added, skipped = insert_transactions(conn, rows)
        total_added += added
        total_skipped += skipped
        dates = [r["date"] for r in rows] if rows else []
        dr_start = min(dates) if dates else None
        dr_end = max(dates) if dates else None
        log_import(conn, spec["id"], spec.get("file"), added, skipped, dr_start, dr_end)
        cat_counts = Counter(r.get("category", "other") for r in rows)
        dir_counts = Counter(r.get("direction", "expense") for r in rows)
        categories_total.update(cat_counts)
        directions_total.update(dir_counts)
        details.append(
            {
                "source_id": spec["id"],
                "added": added,
                "skipped": skipped,
                "parsed": len(rows),
                "categories": dict(sorted(cat_counts.items())),
                "directions": dict(sorted(dir_counts.items())),
            }
        )
    conn.close()
    return {
        "added": total_added,
        "skipped": total_skipped,
        "sources": details,
        "categories_total": dict(sorted(categories_total.items())),
        "directions_total": dict(sorted(directions_total.items())),
    }
