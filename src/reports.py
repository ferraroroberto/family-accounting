"""Monthly compensation report (kids, food, house, equal outflows + contributions)."""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.calculator import monthly_category_compensation

COMPENSATION_CATEGORIES = ("kids", "food", "house", "equal")


def _contributions_comp_for_month(contrib: pd.DataFrame, ym: str) -> float:
    """
    Net compensation impact of contribution transactions for a given month.

    Convention (partner_a perspective, same as expense compensation):
      - partner_a contributes → A funded more → reduces A's debt → negative
      - partner_b contributes → B funded more → increases A's debt → positive
    """
    if contrib.empty or "yyyymm" not in contrib.columns:
        return 0.0
    m = contrib[contrib["yyyymm"] == ym]
    if m.empty:
        return 0.0
    has_partner = "partner" in m.columns
    comp = 0.0
    for _, tx in m.iterrows():
        partner = str(tx["partner"]) if has_partner and not pd.isna(tx.get("partner")) else ""
        amt = float(tx["amount"])
        if partner == "partner_a":
            comp -= amt
        elif partner == "partner_b":
            comp += amt
    return comp


def monthly_compensation_report(
    df: pd.DataFrame,
    config: dict[str, Any],
) -> pd.DataFrame:
    """
    One row per calendar month:
    - Expense compensation for kids, food, house, equal (negative outflows only)
    - contributions_comp: net impact of partner fund transfers
    - total_comp: sum of all category compensations + contributions_comp
    - total_comp_cumulative: running total of total_comp

    Sign convention (partner_a perspective):
      positive total_comp → partner_a owes partner_b
      negative total_comp → partner_b owes partner_a
    """
    if df.empty:
        return pd.DataFrame()

    d = df.copy()
    d["yyyymm"] = pd.to_datetime(d["date"], errors="coerce").dt.strftime("%Y%m")
    d = d.dropna(subset=["yyyymm"])

    # Expense rows: exclude contributions
    is_contribution = (
        (d["category"] == "contribution")
        if "category" in d.columns
        else pd.Series(False, index=d.index)
    )
    dir_ok = (
        d["direction"].fillna("expense").astype(str) != "contribution"
        if "direction" in d.columns
        else pd.Series(True, index=d.index)
    )
    exp = d[(d["amount"] < 0) & dir_ok & ~is_contribution]

    # Contribution rows
    contrib = d[is_contribution].copy() if "category" in d.columns else pd.DataFrame()

    months = sorted(d["yyyymm"].dropna().unique())

    rows: list[dict[str, Any]] = []
    pa_name = config.get("partners", {}).get("partner_a", {}).get("name", "Partner A")
    pb_name = config.get("partners", {}).get("partner_b", {}).get("name", "Partner B")

    for ym in months:
        row: dict[str, Any] = {"month": ym}
        total = 0.0
        for cat in COMPENSATION_CATEGORIES:
            t = float(exp[(exp["yyyymm"] == ym) & (exp["category"] == cat)]["amount"].sum())
            comp = monthly_category_compensation(t, config, cat)
            row[f"{cat}_comp"] = comp
            total += comp

        contributions_comp = _contributions_comp_for_month(contrib, ym)
        row["contributions_comp"] = contributions_comp
        total += contributions_comp

        row["total_comp"] = total
        if total > 1e-9:
            row["balance_note"] = f"{pa_name} owes {pb_name}"
        elif total < -1e-9:
            row["balance_note"] = f"{pb_name} owes {pa_name}"
        else:
            row["balance_note"] = "Balanced"
        rows.append(row)

    out = pd.DataFrame(rows)
    if not out.empty:
        out["total_comp_cumulative"] = out["total_comp"].cumsum()
    return out
