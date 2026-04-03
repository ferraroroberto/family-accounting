"""Parse Revolut account CSV exports."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from src.database import transaction_hash


def parse_revolut_csv(
    path: Path,
    source_id: str,
    layout: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """
    Parse Revolut CSV. Default: filter State == COMPLETED, use Completed Date and Amount.
    """
    layout = layout or {}
    enc = layout.get("encoding", "utf-8")
    df = pd.read_csv(path, encoding=enc)
    col_map = layout.get("columns") or {}
    # Default Revolut column names
    c_type = col_map.get("type", "Type")
    c_started = col_map.get("started_date", "Started Date")
    c_completed = col_map.get("completed_date", "Completed Date")
    c_desc = col_map.get("description", "Description")
    c_amount = col_map.get("amount", "Amount")
    c_currency = col_map.get("currency", "Currency")
    c_state = col_map.get("state", "State")
    c_balance = col_map.get("balance", "Balance")

    state_filter = layout.get("state_filter", "COMPLETED")
    rows: list[dict[str, Any]] = []

    for _, r in df.iterrows():
        if state_filter and str(r.get(c_state, "")).strip() != state_filter:
            continue
        desc = str(r.get(c_desc, "") or "").strip()
        amt = float(r[c_amount]) if pd.notna(r.get(c_amount)) else 0.0
        bal = None
        if c_balance in df.columns and pd.notna(r.get(c_balance)):
            try:
                bal = float(r[c_balance])
            except (TypeError, ValueError):
                bal = None
        completed = r.get(c_completed)
        if pd.isna(completed) or completed == "":
            started = r.get(c_started)
            if pd.isna(started) or started == "":
                continue
            completed = started
        op = _parse_revolut_datetime(completed)
        if op is None:
            continue
        ds = op.date().isoformat()
        yyyymm = op.strftime("%Y%m")
        h = transaction_hash(source_id, ds, amt, desc)
        rows.append(
            {
                "source": source_id,
                "date": ds,
                "value_date": ds,
                "description": desc,
                "amount": amt,
                "balance": bal,
                "yyyymm": yyyymm,
                "hash": h,
                "extra_json": None,
            }
        )
    return rows


def _parse_revolut_datetime(v: Any) -> datetime | None:
    if pd.isna(v):
        return None
    s = str(v).strip()
    try:
        ts = pd.to_datetime(s, dayfirst=False)
        return ts.to_pydatetime()
    except Exception:
        return None
