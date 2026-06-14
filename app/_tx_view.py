"""Shared transaction-view helpers used by both the dashboard and configuration tabs.

These live here (rather than as underscore-private helpers on one tab) because both
the Dashboard and Configuration tabs load the transactions frame and render the
ideal-split view. Keeping them in a neutral, public home avoids coupling the two
tabs through names that advertise themselves as module-private.
"""

from __future__ import annotations

import sqlite3

import pandas as pd

from src.calculator import net_ideal_vs_joint_50_50, share_for_transaction_row


def load_transactions_df(conn: sqlite3.Connection) -> pd.DataFrame:
    """Load the standard transaction columns from *conn*, ordered by date then id."""
    return pd.read_sql_query(
        "SELECT id, date, description, amount, category, direction, partner, source, yyyymm, rule, account_type FROM transactions ORDER BY date, id",
        conn,
    )


def enrich_transactions_split(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Add ideal split vs 50/50 joint funding columns (same convention as monthly compensation)."""
    if df.empty:
        return df

    pct_a: list[float] = []
    pct_b: list[float] = []
    total_a: list[float] = []
    total_b: list[float] = []
    net: list[float] = []
    for _, row in df.iterrows():
        amt = float(row["amount"])
        cat = str(row.get("category") or "other")
        direction = str(row.get("direction") or "expense")
        sa, sb = share_for_transaction_row(cfg, cat, direction)
        pct_a.append(sa)
        pct_b.append(sb)
        abs_amt = abs(amt)
        if amt < 0:
            total_a.append(round(abs_amt * sa, 2))
            total_b.append(round(abs_amt * sb, 2))
        else:
            total_a.append(round(amt * sa, 2))
            total_b.append(round(amt * sb, 2))
        net.append(round(net_ideal_vs_joint_50_50(amt, sa), 2))
    out = df.copy()
    out["% A"] = [f"{x:.1%}" for x in pct_a]
    out["% B"] = [f"{x:.1%}" for x in pct_b]
    out["total A"] = total_a
    out["total B"] = total_b
    out["net"] = net
    if "description" in out.columns:
        out["description"] = out["description"].astype(str).str.lower()
    if "rule" in out.columns:
        out["rule"] = out["rule"].fillna("default").astype(str).str.lower()
    ordered = [
        "id",
        "date",
        "description",
        "amount",
        "% A",
        "% B",
        "total A",
        "total B",
        "net",
        "category",
        "rule",
        "direction",
        "partner",
        "source",
        "yyyymm",
    ]
    return out[[c for c in ordered if c in out.columns]]
