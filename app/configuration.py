"""Configuration tab: edit classification keywords and save to config.json."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from app.dashboard import _enrich_transactions_split, _load_df
from src.classifier import classify_full
from src.config_manager import default_config_path, load_config, save_config
from src.data_loader import clear_data_caches, get_config
from src.database import connect, default_db_path, init_db, reclassify_all

_RULE_KEYS = ("kids", "food", "health", "house", "equal")


def _keywords_to_text(keywords: list[str] | None) -> str:
    if not keywords:
        return ""
    return ", ".join(str(k) for k in keywords)


def _parse_keywords(text: str) -> list[str]:
    out: list[str] = []
    for part in text.replace("\n", ",").split(","):
        s = part.strip()
        if s:
            out.append(s)
    return out


def _dedupe_keywords_casefold(parsed: list[str]) -> tuple[list[str], list[str]]:
    """Keep first spelling per case-insensitive key; return (unique_in_order, skipped occurrences)."""
    seen: set[str] = set()
    unique: list[str] = []
    skipped: list[str] = []
    for k in parsed:
        lk = k.lower()
        if lk in seen:
            skipped.append(k)
        else:
            seen.add(lk)
            unique.append(k)
    return unique, skipped


def _count_new_keywords(prev: list[str] | None, normalized: list[str]) -> int:
    prev_lower = {str(x).lower() for x in (prev or []) if str(x).strip()}
    return sum(1 for k in normalized if k.lower() not in prev_lower)


def _finalize_keywords_with_stats(
    text: str, prev_keywords: list[str] | None
) -> tuple[list[str], list[str], int]:
    parsed = _parse_keywords(text)
    unique, skipped_dupes = _dedupe_keywords_casefold(parsed)
    sorted_kws = sorted(unique, key=str.lower)
    new_n = _count_new_keywords(prev_keywords, sorted_kws)
    return sorted_kws, skipped_dupes, new_n


def render() -> None:
    st.header("Configuration")

    cfg_path = default_config_path()
    if not cfg_path.is_file():
        st.error("`config.json` not found.")
        return

    cfg = get_config()
    rules = cfg.get("classification_rules") or {}

    st.subheader("Classification keywords")
    st.caption("Comma-separated keywords per rule. Save writes `config.json`, reclassifies the database, and refreshes cached config.")

    defaults: dict[str, str] = {}
    for key in _RULE_KEYS:
        block = rules.get(key) or {}
        kws = block.get("keywords") or []
        defaults[key] = _keywords_to_text(kws if isinstance(kws, list) else [])

    widgets: dict[str, str] = {}
    for key in _RULE_KEYS:
        label = cfg.get("categories", {}).get(key, {}).get("label", key)
        widgets[key] = st.text_area(
            f"{label} (`{key}`)",
            value=defaults[key],
            height=120,
            key=f"cfg_keywords_{key}",
        )

    if st.button("Save and reclassify", type="primary", key="btn_cfg_save"):
        base = load_config(cfg_path)
        cr = base.setdefault("classification_rules", {})
        stats: dict[str, dict[str, object]] = {}
        for key in _RULE_KEYS:
            prev_block = cr.get(key) or {}
            raw_prev = prev_block.get("keywords")
            prev_kws = raw_prev if isinstance(raw_prev, list) else []
            block = dict(prev_block)
            kws, skipped_dupes, new_n = _finalize_keywords_with_stats(widgets[key], prev_kws)
            block["keywords"] = kws
            if "case_sensitive" not in block:
                block["case_sensitive"] = False
            cr[key] = block
            stats[key] = {"new": new_n, "duplicates_skipped": skipped_dupes}
        try:
            save_config(base, cfg_path)
        except Exception as e:
            st.error(str(e))
            return
        st.session_state.last_keyword_save_stats = stats
        clear_data_caches()

        dbp = default_db_path()
        if dbp.is_file():
            fresh = load_config(cfg_path)

            def _fn(desc: str, amt: float):
                return classify_full(desc, amt, fresh)

            conn = connect(dbp)
            init_db(conn)
            res = reclassify_all(conn, _fn)
            conn.close()
            st.session_state.last_config_reclass = res
        else:
            st.session_state.last_config_reclass = None

        st.success("Saved and reclassified.")
        st.rerun()

    if st.session_state.get("last_keyword_save_stats"):
        kw_stats = st.session_state.last_keyword_save_stats
        cfg_labels = get_config()
        st.caption("Last save: keyword changes")
        for key in _RULE_KEYS:
            label = cfg_labels.get("categories", {}).get(key, {}).get("label", key)
            d = kw_stats[key]
            dup_list = d["duplicates_skipped"]
            if not isinstance(dup_list, list):
                dup_list = []
            n_dup = len(dup_list)
            if n_dup == 0:
                dup_phrase = "no duplicates skipped"
            elif n_dup == 1:
                dup_phrase = f"1 duplicate skipped: `{dup_list[0]}`"
            else:
                shown = ", ".join(f"`{t}`" for t in dup_list)
                dup_phrase = f"{n_dup} duplicates skipped: {shown}"
            st.markdown(
                f"- **{label}** (`{key}`): **{d['new']}** new · {dup_phrase}"
            )

    if st.session_state.get("last_config_reclass"):
        r = st.session_state.last_config_reclass
        st.caption("Last save: reclassify summary")
        st.write(
            f"Touched **{r['rows_touched']}** rows · **{r['rows_changed']}** category/direction changes."
        )
        transitions: dict[str, int] = r.get("transitions") or {}
        transition_rows: dict[str, list[dict]] = r.get("transition_rows") or {}
        if transitions:
            st.caption("Changes by transition")
            rows_sorted = sorted(transitions.items(), key=lambda x: -x[1])
            for label, count in rows_sorted:
                with st.expander(f"`{label}` — **{count}** row{'s' if count != 1 else ''}"):
                    detail = transition_rows.get(label) or []
                    for item in detail:
                        amt = item["amount"]
                        amt_str = f"{amt:+.2f}" if amt is not None else "—"
                        st.markdown(f"- `{amt_str}` &nbsp; {item['description']}")
        category_counts: dict[str, int] = r.get("category_counts") or {}
        if category_counts:
            st.caption("Final category distribution")
            for cat, count in sorted(category_counts.items(), key=lambda x: -x[1]):
                st.markdown(f"- **{cat}**: {count}")

    st.divider()
    st.subheader("Transactions")
    st.caption(
        "Filter by category, rule, direction, source, "
        "date range, and description. Up to 500 rows after filters (newest first)."
    )

    dbp_tx = default_db_path()
    if not dbp_tx.is_file():
        st.info("No database yet. Use **Import data** to load bank exports.")
    else:
        conn_tx = connect(dbp_tx)
        init_db(conn_tx)
        df_tx = _load_df(conn_tx)
        df_raw = pd.read_sql_query(
            "SELECT * FROM transactions ORDER BY date DESC, id DESC", conn_tx
        )
        conn_tx.close()

        if df_tx.empty:
            st.info("No transactions. Import data first.")
        else:
            cfg_tx = get_config()
            pa = cfg_tx.get("partners", {}).get("partner_a", {}).get("name", "Partner A")
            pb = cfg_tx.get("partners", {}).get("partner_b", {}).get("name", "Partner B")
            st.caption(
                f"**net**: joint account is funded 50/50; ideal share uses category rules for expenses "
                f"(contributions are neutral). Positive **net** ⇒ **{pa}** owes **{pb}**; "
                f"negative **net** ⇒ **{pb}** owes **{pa}**."
            )

            def _opt_all(values: pd.Series) -> list[str]:
                u = sorted(
                    {str(x) for x in values.dropna().unique() if str(x).strip()},
                    key=str.lower,
                )
                return ["(All)"] + u

            d_parsed = pd.to_datetime(df_tx["date"], errors="coerce")
            valid_dates = d_parsed.dropna()
            if valid_dates.empty:
                d_min = d_max = pd.Timestamp.now().normalize()
            else:
                d_min = valid_dates.min().normalize()
                d_max = valid_dates.max().normalize()

            fc1, fc2, fc3, fc4 = st.columns(4)
            with fc1:
                cat_opts = _opt_all(df_tx["category"])
                cat_sel = st.selectbox("Category", cat_opts, key="cfg_tx_category")
            with fc2:
                rule_opts = _opt_all(df_tx["rule"].fillna("default"))
                rule_sel = st.selectbox("Rule", rule_opts, key="cfg_tx_rule")
            with fc3:
                dir_opts = _opt_all(df_tx["direction"])
                dir_sel = st.selectbox("Direction", dir_opts, key="cfg_tx_direction")
            with fc4:
                src_opts = _opt_all(df_tx["source"])
                src_sel = st.selectbox("Source", src_opts, key="cfg_tx_source")

            fd0, fd1, fdesc = st.columns([1, 1, 2])
            with fd0:
                d_start = st.date_input(
                    "From date",
                    value=d_min.date(),
                    min_value=d_min.date(),
                    max_value=d_max.date(),
                    key="cfg_tx_date_from",
                )
            with fd1:
                d_end = st.date_input(
                    "To date",
                    value=d_max.date(),
                    min_value=d_min.date(),
                    max_value=d_max.date(),
                    key="cfg_tx_date_to",
                )
            with fdesc:
                desc_filter = st.text_input(
                    "Description contains",
                    value="",
                    key="cfg_tx_description",
                    placeholder="Substring match (case-insensitive)",
                )

            d0, d1 = (d_start, d_end) if d_start <= d_end else (d_end, d_start)

            filtered = df_tx
            if cat_sel != "(All)":
                filtered = filtered[filtered["category"].astype(str) == cat_sel]
            if rule_sel != "(All)":
                filtered = filtered[
                    filtered["rule"].fillna("default").astype(str) == rule_sel
                ]
            if dir_sel != "(All)":
                filtered = filtered[filtered["direction"].astype(str) == dir_sel]
            if src_sel != "(All)":
                filtered = filtered[filtered["source"].astype(str) == src_sel]
            q = desc_filter.strip()
            if q:
                filtered = filtered[
                    filtered["description"]
                    .astype(str)
                    .str.contains(q, case=False, na=False, regex=False)
                ]

            fd = pd.to_datetime(filtered["date"], errors="coerce").dt.date
            filtered = filtered[(fd >= d0) & (fd <= d1)]

            tx_disp = _enrich_transactions_split(
                filtered.sort_values(["date", "id"], ascending=[False, False]).head(500),
                cfg_tx,
            )
            st.dataframe(tx_disp, width="stretch", height=400)

            st.divider()
            st.subheader("Raw data explorer")
            st.caption(
                "All database columns for the same filtered selection above. "
                "Includes CaixaBank raw fields (`cb_*`), hash, and timestamps."
            )

            raw_filtered = df_raw
            if cat_sel != "(All)":
                raw_filtered = raw_filtered[raw_filtered["category"].astype(str) == cat_sel]
            if rule_sel != "(All)":
                raw_filtered = raw_filtered[
                    raw_filtered["rule"].fillna("default").astype(str) == rule_sel
                ]
            if dir_sel != "(All)":
                raw_filtered = raw_filtered[raw_filtered["direction"].astype(str) == dir_sel]
            if src_sel != "(All)":
                raw_filtered = raw_filtered[raw_filtered["source"].astype(str) == src_sel]
            if q:
                raw_filtered = raw_filtered[
                    raw_filtered["description"]
                    .astype(str)
                    .str.contains(q, case=False, na=False, regex=False)
                ]
            fd_raw = pd.to_datetime(raw_filtered["date"], errors="coerce").dt.date
            raw_filtered = raw_filtered[(fd_raw >= d0) & (fd_raw <= d1)]

            st.dataframe(raw_filtered.head(500), width="stretch", height=400)
