# Family Expense Tracker (Streamlit)

## Context
**What**: Streamlit dashboard that ingests bank exports (CaixaBank XLS, Revolut CSV), classifies transactions, calculates per-partner cost shares, and stores everything in SQLite.
**Why**: Automate fair-split accounting between two partners with configurable share formulas (fixed, income_ratio, blended).
**Stack**: Python 3.x, Streamlit, Pandas, SQLite, Pytest. Windows-first (`launch_app.bat`).

## Codebase Map
- `app/streamlit_app.py` — entry point; page config, sidebar, three tabs.
- `app/dashboard.py` — Dashboard tab (`render()`): aggregates + charts.
- `app/import_data.py` — Import tab (`render()`): file upload + ingest trigger.
- `app/configuration.py` — Config tab (`render()`): view/edit `config.json` in UI.
- `src/config_manager.py` — loads `config.json`; `default_config_path()`.
- `src/data_loader.py` — cached data helpers; `get_config()`.
- `src/database.py` — SQLite helpers; `connect()`, `init_db()`, `default_db_path()`.
- `src/ingest.py` — orchestrates parse → classify → store pipeline.
- `src/parsers/caixabank.py` / `src/parsers/revolut.py` — per-bank parsers.
- `src/classifier.py` — keyword-based transaction classifier.
- `src/calculator.py` — share formula engine (fixed / income_ratio / blended).
- `src/reports.py` — report generation helpers.
- `src/logger.py` — `get_logger(__name__)`.
- `tests/` — pytest suite.
- `data/expenses.db` — runtime SQLite DB (git-ignored).
- `tmp/input/` — drop bank export files here before import.

## Commands
```bash
# Run app
.\.venv\Scripts\python.exe -m streamlit run app\streamlit_app.py
# or
launch_app.bat

# Run tests
.\.venv\Scripts\python.exe -m pytest -v
```

## Config
- `config.json` (copy from `config.example.json`): partners, income, categories, classification_rules, accounts, bank_imports.
- No `.env` — no external API keys needed.

## Standards
- **Logging**: `src.logger.get_logger(__name__)`. No `print()`.
- **Imports order**: stdlib → third-party → local (`app.*` / `src.*`).
- **Naming**: `snake_case` files/functions, `PascalCase` classes, `UPPER_CASE` constants.
- **Errors**: raise typed exceptions; show `st.error(...)` for user-facing failures.

## Streamlit Conventions
- `app/streamlit_app.py` is orchestration only; each tab module owns its UI via `render()`.
- Business logic lives in `src/`; keep `app/` modules thin.
- `st.session_state` for UI state; use explicit widget keys (`key="..."`).
- `@st.cache_data` for IO-heavy loads (see `src/data_loader.py`).
- Use `width="stretch"` / `width="content"` — **not** `use_container_width` (deprecated).
- Long ops: `st.spinner(...)`. Outcomes: `st.info/warning/error/success`.

## Safety
- Never modify `.venv/`.
- Never commit real `config.json` values or any file under `data/` or `tmp/input/`.
