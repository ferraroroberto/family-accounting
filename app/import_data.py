"""Import data tab."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.data_loader import clear_data_caches, get_config
from src.classifier import classify_full
from src.config_manager import default_config_path, load_config, resolve_path
from src.database import connect, default_db_path, init_db, reclassify_all
from src.ingest import import_all_configured, load_and_parse_source


def _show_import_summary(res: dict) -> None:
    st.write(
        f"Inserted **{res['added']}** rows · skipped **{res['skipped']}** duplicates "
        f"(parsed from files, before dedup)."
    )
    if res.get("categories_total"):
        st.caption("Classified category counts (all parsed rows)")
        st.dataframe(
            pd.DataFrame(
                [
                    {"category": k, "rows": v}
                    for k, v in res["categories_total"].items()
                ]
            ),
            width="stretch",
            hide_index=True,
        )
    if res.get("directions_total"):
        st.caption("Direction (expense vs contribution)")
        st.write(res["directions_total"])
    rows = []
    for d in res.get("sources", []):
        row = {
            "source": d["source_id"],
            "added": d["added"],
            "skipped": d["skipped"],
            "parsed": d["parsed"],
        }
        if d.get("categories"):
            row["categories"] = ", ".join(f"{k}:{v}" for k, v in d["categories"].items())
        rows.append(row)
    if rows:
        st.caption("Per source")
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)


def _show_reclass_summary(res: dict) -> None:
    st.write(
        f"Touched **{res['rows_touched']}** rows without manual override · "
        f"**{res['rows_changed']}** had category or direction changes."
    )
    tr = res.get("transitions") or {}
    if tr:
        st.caption("Changes (old category/direction → new, count)")
        lines = sorted(f"`{k}`: **{n}**" for k, n in tr.items())
        st.markdown("\n".join(lines))
    if res.get("category_counts"):
        st.caption("Resulting category distribution")
        st.write(res["category_counts"])


def render() -> None:
    st.header("Import data")

    cfg_path = default_config_path()
    if not cfg_path.is_file():
        st.error("Missing `config.json` in the project root.")
        return

    cfg = get_config()
    bi = cfg.get("bank_imports") or {}
    sources = bi.get("sources") or []
    if not sources:
        st.warning("No `bank_imports.sources` in configuration.")
        return

    st.subheader("Configured sources")
    for s in sources:
        p = resolve_path(cfg, s["file"])
        ok = p.is_file()
        st.write(f"- **{s['id']}** → `{s['file']}` {'OK' if ok else 'file not found'}")

    st.subheader("Import from configuration")
    if st.button("Import all files", type="primary", key="btn_import_all"):
        with st.spinner("Importing…"):
            try:
                res = import_all_configured(cfg=load_config(cfg_path))
            except Exception as e:
                st.error(str(e))
                return
        clear_data_caches()
        st.session_state.last_import_summary = res
        st.success(
            f"Inserted: **{res['added']}** · Skipped (duplicate): **{res['skipped']}**"
        )
        st.toast("Import finished", icon="✅")
        st.rerun()

    if st.session_state.get("last_import_summary"):
        st.subheader("Last import summary")
        _show_import_summary(st.session_state.last_import_summary)

    st.subheader("Reclassify")
    st.caption("Apply `config.json` rules to rows without a manual override.")
    if st.button("Reclassify all", key="btn_reclass"):
        cfg = load_config(cfg_path)
        dbp = default_db_path()

        def _fn(desc: str, amt: float, account_type: str = "joint"):
            return classify_full(desc, amt, cfg, account_type)

        conn = connect(dbp)
        init_db(conn)
        res = reclassify_all(conn, _fn)
        conn.close()
        clear_data_caches()
        st.session_state.last_reclass_summary = res
        st.success(
            f"Touched **{res['rows_touched']}** rows · "
            f"**{res['rows_changed']}** category/direction changes."
        )
        st.toast("Reclassification done", icon="✅")
        st.rerun()

    if st.session_state.get("last_reclass_summary"):
        st.subheader("Last reclassify summary")
        _show_reclass_summary(st.session_state.last_reclass_summary)

    st.subheader("Preview (local file)")
    which = st.selectbox("Source", options=[s["id"] for s in sources], key="prev_src")
    spec = next(x for x in sources if x["id"] == which)
    p = resolve_path(cfg, spec["file"])
    if p.is_file() and st.button("Preview", key="btn_preview"):
        with st.spinner("Parsing…"):
            rows = load_and_parse_source(cfg, spec)
        st.write(f"{len(rows)} rows (classified in memory).")
        st.dataframe(
            [
                {
                    "date": r["date"],
                    "amount": r["amount"],
                    "category": r["category"],
                    "description": r["description"][:80],
                }
                for r in rows[:50]
            ],
            width="stretch",
        )

