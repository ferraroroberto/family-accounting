"""Shared renderer for the ``reclassify_database`` result, used by the Import and Configuration tabs."""

from __future__ import annotations

import streamlit as st


def render_reclass_summary(r: dict) -> None:
    """Show rows touched/changed, the per-transition detail and the final category counts."""
    st.write(
        f"Touched **{r['rows_touched']}** rows without manual override · "
        f"**{r['rows_changed']}** had category or direction changes."
    )
    transitions: dict[str, int] = r.get("transitions") or {}
    transition_rows: dict[str, list[dict]] = r.get("transition_rows") or {}
    if transitions:
        st.caption("Changes by transition")
        for label, count in sorted(transitions.items(), key=lambda x: -x[1]):
            with st.expander(f"`{label}` — **{count}** row{'s' if count != 1 else ''}"):
                for item in transition_rows.get(label) or []:
                    amt = item["amount"]
                    amt_str = f"{amt:+.2f}" if amt is not None else "—"
                    st.markdown(f"- `{amt_str}` &nbsp; {item['description']}")
    category_counts: dict[str, int] = r.get("category_counts") or {}
    if category_counts:
        st.caption("Final category distribution")
        for cat, count in sorted(category_counts.items(), key=lambda x: -x[1]):
            st.markdown(f"- **{cat}**: {count}")
