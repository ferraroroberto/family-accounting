"""Monthly compensation report (kids, food, house outflows only)."""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.calculator import monthly_category_compensation

COMPENSATION_CATEGORIES = ("kids", "food", "house", "equal")


def monthly_compensation_report(
    df: pd.DataFrame,
    config: dict[str, Any],
) -> pd.DataFrame:
    """
    One row per calendar month: compensation for kids, food, and house only
    (negative amounts / outflows). Total is the sum of the three category compensations.
    """
    if df.empty:
        return pd.DataFrame()

    d = df.copy()
    d["yyyymm"] = pd.to_datetime(d["date"], errors="coerce").dt.strftime("%Y%m")
    d = d.dropna(subset=["yyyymm"])

    dir_ok = (
        d["direction"].fillna("expense").astype(str) != "contribution"
        if "direction" in d.columns
        else pd.Series(True, index=d.index)
    )
    exp = d[(d["amount"] < 0) & dir_ok]
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
