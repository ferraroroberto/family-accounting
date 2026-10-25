# Project Instructions

Canonical instructions for AI coding agents working in this repository. Claude Code reads this file directly as project memory. Other agents (Cursor, Codex, etc.) reach it via the one-line `AGENTS.md` pointer.

## Streamlit conventions
*Apply only if this project uses Streamlit.*

- `st.set_page_config(layout="wide", page_title="...")` MUST be the first Streamlit call.
- Use `width="stretch"` (and `width="content"` where appropriate) in new and modified code. **Never** introduce new `use_container_width=True` — it is deprecated. When you touch existing code that uses `use_container_width`, migrate it.
- All mutable state in `st.session_state`. No module-level globals.
- `@st.cache_data` for DataFrames/files; `@st.cache_resource` for DB clients/models.
- Every widget needs a stable, explicit `key=`.
- UI code only in the UI directory (e.g. `app/`). Data logic stays in the non-UI package (e.g. `src/`). Never import `streamlit` from non-UI code.
- User feedback via `st.error()` / `st.warning()` / `st.success()`, not `st.write()`.
- **App layout:** main file (e.g. `app.py`) handles only page config, shared state, sidebar, and tab/radio routing. Each tab/mode lives in its own file exposing a `main(...)` (or `render_*`) function. Default to `st.tabs()`; use a sidebar radio only when asked.

## This repository
Streamlit app for tracking shared household expenses between two partners and computing monthly compensation balances.
See `README.md` for setup, layout, and usage.

## Structure ratchet

- **A structure ratchet gates `scripts/verify-before-ship.ps1`.** It runs the vendored `scripts/structure_ratchet.py` (byte-for-byte from project-scaffolding; re-vendor with `/propagate-vendored structure_ratchet`, never edit) and fails when a file passes 1,000 lines, a function 100 lines or a flat directory 40 modules and is new or above its entry in `.structure-ratchet-baseline.json`, when `src` imports `app`, or when the root folders do not match `shape = "streamlit"` plus `extra_roots` in `.fleet.toml`. The four baselined long functions in `app/dashboard.py` and `app/configuration.py` are recorded at their real size, never excluded: they cannot grow, so new UI goes in a new function or module. Burn the baseline down with `--update-baseline`; only `--allow-additions` raises it, and that shows in the diff. Exit 3 means "not confirmed" and fails the gate. Where code goes: [`docs/layout.md`](docs/layout.md).

## Static ratchet

- **A static ratchet gates `scripts/verify-before-ship.ps1`.** It runs the vendored `scripts/static_ratchet.py` (byte-for-byte from project-scaffolding; re-vendor with `/propagate-vendored static_ratchet`, never edit) and fails on a duplicated block, an unused import or variable, or a likely-bug or security pattern that is not in `.static-ratchet-baseline.json`. The baseline is empty: fix a new finding rather than recording it. It needs Node (`npx`) and `ruff` in `.venv`; exit 3 means "not confirmed" and fails the gate.

## Docs ratchet

- **A docs ratchet gates `scripts/verify-before-ship.ps1`.** It runs the vendored `scripts/docs_ratchet.py` (byte-for-byte from project-scaffolding; re-vendor with `/propagate-vendored docs_ratchet`, never edit) and fails when the root `README.md` passes 40 KiB, or when `README.md` or a `docs/**/*.md` file carries an issue reference, a dated heading or a changelog heading that is not in `.docs-ratchet-baseline.json`. The baseline is empty: state the present-tense why in words instead of citing an issue. Exit 3 means "not confirmed" and fails the gate.

## Internal architecture

[`docs/architecture.mmd`](docs/architecture.mmd) is a hand-authored Mermaid diagram of this repo's own internal structure (the `app/` UI package, the `src/` business logic, the two bank parsers, `config.json`/`data/expenses.db` as data stores, `tests/`) — the per-repo counterpart to `ferraroroberto/fleet-config`'s fleet-wide `/system-map`. Update it in the same PR as any material structural change (a module added/moved/renamed, a new parser, a new table/column, a new UI tab) — same anti-staleness contract as a `.fleet.toml` `description` field. It is not auto-generated and not covered by the `pytest` suite.
