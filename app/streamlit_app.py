"""Family expense tracker — Streamlit entry."""

from __future__ import annotations

import streamlit as st

from app import configuration, dashboard, import_data
from src.config_manager import default_config_path
from src.data_loader import get_config
from src.database import (
    connect,
    default_db_path,
    init_db,
    last_data_update_iso,
    per_source_date_counts,
)


def _render_sidebar() -> None:
    st.sidebar.title("Family Expense Tracker")

    cfg_path = default_config_path()
    st.session_state["cfg_path_exists"] = cfg_path.is_file()

    if cfg_path.is_file():
        try:
            cfg = get_config()
            pa = cfg.get("partners", {}).get("partner_a", {}).get("name", "Partner A")
            pb = cfg.get("partners", {}).get("partner_b", {}).get("name", "Partner B")
            st.sidebar.caption(f"{pa} · {pb}")
        except Exception:
            pass

    st.sidebar.divider()
    st.sidebar.subheader("Status")

    dbp = default_db_path()
    if not dbp.is_file():
        st.sidebar.caption("Database not created yet.")
        return

    conn = connect(dbp)
    init_db(conn)
    updated = last_data_update_iso(conn)
    if updated:
        day = str(updated)[:10] if len(str(updated)) >= 10 else str(updated)
        st.sidebar.write("**Last data update (UTC)**")
        st.sidebar.write(day)
    else:
        st.sidebar.caption("No activity timestamp yet.")

    st.sidebar.subheader("By source")
    for row in per_source_date_counts(conn):
        src = row["source_id"]
        n = row["transaction_count"]
        d0 = row["date_from"] or "—"
        d1 = row["date_to"] or "—"
        st.sidebar.write(f"**{src}**")
        st.sidebar.caption(f"{n} transactions · {d0} → {d1}")

    conn.close()


def main() -> None:
    st.set_page_config(
        page_title="Family Expense Tracker",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    _render_sidebar()

    tab_dash, tab_imp, tab_cfg = st.tabs(["dashboard", "import_data", "configuration"])

    with tab_dash:
        dashboard.render()

    with tab_imp:
        import_data.render()

    with tab_cfg:
        configuration.render()


if __name__ == "__main__":
    main()
