"""Dashboard tab: charts and monthly compensation."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.data_loader import get_config
from src.calculator import share_for_category, share_for_transaction_row, net_ideal_vs_joint_50_50
from src.database import connect, default_db_path, init_db
from src.reports import COMPENSATION_CATEGORIES, monthly_compensation_report

ROOT = Path(__file__).resolve().parents[1]


def _read_accent_hex() -> str:
    p = ROOT / "app" / ".streamlit" / "config.toml"
    if not p.is_file():
        return "#1E88E5"
    text = p.read_text(encoding="utf-8")
    m = re.search(r'primaryColor\s*=\s*"([^"]+)"', text)
    return m.group(1) if m else "#1E88E5"


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.strip().lstrip("#")
    if len(h) != 6:
        return (30, 136, 229)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02x}{g:02x}{b:02x}"


def accent_gradient(n: int, base_hex: str | None = None) -> list[str]:
    """``n`` colors from strong accent toward lighter tints (for pie slices)."""
    base = base_hex or _read_accent_hex()
    r0, g0, b0 = _hex_to_rgb(base)
    out: list[str] = []
    for i in range(n):
        t = i / max(n, 1)
        # blend toward white
        r = int(r0 + (255 - r0) * t * 0.85)
        g = int(g0 + (255 - g0) * t * 0.85)
        b = int(b0 + (255 - b0) * t * 0.85)
        out.append(_rgb_to_hex(r, g, b))
    return out


def _load_df(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query(
        "SELECT id, date, description, amount, category, direction, partner, source, yyyymm, rule FROM transactions ORDER BY date, id",
        conn,
    )


def _format_yyyymm(ym: str | int | float) -> str:
    if pd.isna(ym):
        return ""
    try:
        if isinstance(ym, (int, float)) and not isinstance(ym, bool):
            s = f"{int(ym):06d}"
        else:
            t = str(ym).strip()
            s = f"{int(float(t)):06d}" if "." in t else t
    except (ValueError, TypeError):
        s = str(ym)
    if len(s) != 6 or not s.isdigit():
        return s
    try:
        dt = pd.to_datetime(s, format="%Y%m")
        return dt.strftime("%b %Y")
    except (ValueError, TypeError):
        return s


def _add_thousands_dot(int_digits: str) -> str:
    """Group digits from the right with '.' (e.g. '9047992' -> '9.047.992')."""
    if len(int_digits) <= 3:
        return int_digits
    parts: list[str] = []
    for i in range(len(int_digits), 0, -3):
        parts.append(int_digits[max(0, i - 3) : i])
    return ".".join(reversed(parts))


def _format_eu_decimal(value: object) -> str:
    """Thousands '.', decimal ',', two fractional digits (European-style)."""
    if value is None or pd.isna(value):
        return ""
    try:
        n = float(value)
    except (TypeError, ValueError):
        return str(value)
    s = f"{n:.2f}"
    neg = s.startswith("-")
    if neg:
        s = s[1:]
    int_part, dec_part = s.split(".")
    body = f"{_add_thousands_dot(int_part)},{dec_part}"
    return f"-{body}" if neg else body


def _enrich_transactions_split(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
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


def render() -> None:
    st.header("Dashboard")

    cfg_path_st = st.session_state.get("cfg_path_exists", True)
    if not cfg_path_st:
        st.error("Missing `config.json`.")
        return

    cfg = get_config()
    dbp = default_db_path()
    if not dbp.is_file():
        st.info("No database yet. Use **Import data** to load bank exports.")
        return

    conn = connect(dbp)
    init_db(conn)
    df = _load_df(conn)
    conn.close()

    if df.empty:
        st.info("No transactions. Import data first.")
        return

    # Spending = outflows excluding contributions
    contributions_mask = df["category"] == "contribution" if "category" in df.columns else pd.Series(False, index=df.index)
    expenses = df[(df["amount"] < 0) & ~contributions_mask].copy()
    expenses["amount_abs"] = -expenses["amount"]

    # Contribution rows
    contrib_df = df[contributions_mask].copy() if "category" in df.columns else pd.DataFrame()

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Total spending (outflows)", f"{expenses['amount_abs'].sum():,.2f} €")
    with c2:
        st.metric("Transactions", len(df))
    with c3:
        st.metric("Sources", df["source"].nunique())

    pa = cfg.get("partners", {}).get("partner_a", {}).get("name", "Partner A")
    pb = cfg.get("partners", {}).get("partner_b", {}).get("name", "Partner B")

    rep = monthly_compensation_report(df, cfg)

    comp_cat_labels = " · ".join(
        cfg.get("categories", {}).get(c, {}).get("label", c) for c in COMPENSATION_CATEGORIES
    )

    st.subheader("Compensation share (ideal split vs 50/50 funding)")
    st.caption(
        f"Each category uses the configured formula; expense compensation includes **{comp_cat_labels}** outflows. "
        f"Contributions are tracked separately. Shares: **{pa}** (A) vs **{pb}** (B)."
    )

    # Show kids, food, house cards + contributions card (replaces equal card)
    display_cats = [c for c in COMPENSATION_CATEGORIES if c != "equal"]
    ratio_cols = st.columns(len(display_cats) + 1)
    accent = _read_accent_hex()

    for i, cat in enumerate(display_cats):
        sa, sb = share_for_category(cfg, cat)
        label = cfg.get("categories", {}).get(cat, {}).get("label", cat)
        with ratio_cols[i]:
            st.metric(
                f"{label}",
                f"{sa:.1%} A · {sb:.1%} B",
                help=f"Ideal share of category spending for {pa} vs {pb}",
            )
            col_name = f"{cat}_comp"
            if not rep.empty and col_name in rep.columns:
                cum = float(rep[col_name].sum())
                st.caption(f"Cumulative: {_format_eu_decimal(cum)} € (all months)")
            else:
                st.caption("Cumulative: —")

    # Contributions card
    with ratio_cols[len(display_cats)]:
        contrib_cum = float(rep["contributions_comp"].sum()) if not rep.empty and "contributions_comp" in rep.columns else 0.0
        st.metric(
            "Contributions",
            _format_eu_decimal(contrib_cum) + " €",
            help="Net compensation impact of partner fund transfers (A perspective). Negative = A contributed more.",
        )
        if not contrib_df.empty and "partner" in contrib_df.columns:
            amt_a = float(contrib_df[contrib_df["partner"] == "partner_a"]["amount"].sum())
            amt_b = float(contrib_df[contrib_df["partner"] == "partner_b"]["amount"].sum())
            st.caption(f"A: {_format_eu_decimal(amt_a)} € · B: {_format_eu_decimal(amt_b)} €")
        else:
            st.caption("No contributions recorded")

    if not expenses.empty:
        cat_sum = expenses.groupby("category", as_index=False)["amount_abs"].sum()
        cat_sum = cat_sum.sort_values("amount_abs", ascending=False)
        n = len(cat_sum)
        colors = accent_gradient(n, accent)
        cmap = dict(zip(cat_sum["category"].astype(str), colors))
        fig_pie = px.pie(
            cat_sum,
            names="category",
            values="amount_abs",
            title="Spending by category (contributions excluded)",
            color="category",
            color_discrete_map=cmap,
        )
        fig_pie.update_traces(
            textposition="inside",
            textinfo="percent+label",
            marker=dict(line=dict(color="#0E1117", width=1)),
        )
        st.plotly_chart(fig_pie, width="stretch")

    st.subheader(f"Monthly compensation ({comp_cat_labels} + contributions)")
    st.caption(
        f"Positive **total** means **{pa}** owes **{pb}**; negative **total** means **{pb}** owes **{pa}** "
        f"(Partner A perspective on 50/50 account funding). "
        f"**contributions_comp**: negative = A funded more, positive = B funded more."
    )
    if not rep.empty:
        disp = rep.sort_values("month", ascending=False).copy()
        disp["month"] = disp["month"].map(_format_yyyymm)
        comp_cols_to_format = [f"{c}_comp" for c in COMPENSATION_CATEGORIES] + [
            "contributions_comp",
            "total_comp",
            "total_comp_cumulative",
        ]
        for col in comp_cols_to_format:
            if col in disp.columns:
                disp[col] = disp[col].map(_format_eu_decimal)
        comp_column_config = {
            col: st.column_config.TextColumn(alignment="right")
            for col in comp_cols_to_format
            if col in disp.columns
        }
        st.dataframe(
            disp,
            width="stretch",
            height=min(400, 40 + len(disp) * 35),
            column_config=comp_column_config,
        )
        rep_ch = rep.sort_values("month", ascending=True).copy()
        rep_ch["month_label"] = rep_ch["month"].map(_format_yyyymm)
        fig_bar = go.Figure(
            data=[
                go.Bar(
                    x=rep_ch["month_label"],
                    y=rep_ch["total_comp"],
                    name="Net compensation (A perspective)",
                    marker_color=accent,
                )
            ]
        )
        fig_bar.update_layout(
            title="Monthly net compensation",
            xaxis_title="Month",
            yaxis_title="€",
        )
        fig_bar.update_xaxes(type="category")

        st.plotly_chart(fig_bar, width="stretch")

        fig_cum = px.line(
            rep_ch,
            x="month_label",
            y="total_comp_cumulative",
            title="Cumulative compensation",
            markers=True,
            color_discrete_sequence=[accent],
        )
        fig_cum.update_xaxes(type="category", title="Month")
        fig_cum.update_traces(line=dict(color=accent), marker=dict(color=accent))
        st.plotly_chart(fig_cum, width="stretch")
    else:
        st.warning("Could not build compensation rows (check dates and categories).")
