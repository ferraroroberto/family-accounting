# Layout

Where code goes in this repo. The root folders match the `streamlit` shape declared in `.fleet.toml`; `scripts/structure_ratchet.py` checks that on every gate run.

```
family-accounting/
├── app/                        # Streamlit UI — the only place that imports streamlit
│   ├── streamlit_app.py        # entry point: page config, sidebar, tab routing
│   ├── dashboard.py            # Dashboard tab: charts and transaction table
│   ├── import_data.py          # Import tab: ingest bank files, reclassify
│   ├── configuration.py        # Configuration tab: keywords and transactions
│   ├── data_loader.py          # Streamlit-cached config helpers
│   └── _tx_view.py             # transaction-view helpers shared by the Dashboard and Configuration tabs
│
├── src/                        # business logic — never imports streamlit or app
│   ├── calculator.py           # share formulas and compensation math
│   ├── classifier.py           # keyword-based transaction classifier
│   ├── config_manager.py       # load / validate / save config.json
│   ├── database.py             # SQLite schema, queries, migrations
│   ├── ingest.py               # orchestrate parse → classify → insert
│   ├── reports.py              # monthly compensation report
│   ├── logger.py               # shared logging setup
│   └── parsers/                # one module per bank export format (caixabank, revolut)
│
├── scripts/                    # CLI entry points, the gate and the vendored ratchet
│   ├── import_bank_files.py    # run the configured imports
│   ├── classify_triage.py      # unclassified report and keyword vetting
│   ├── verify-before-ship.ps1  # the verification gate
│   ├── structure_ratchet.py    # vendored from project-scaffolding; re-vendor, never edit
│   └── instruction_ratchet.py  # vendored likewise; lints CLAUDE.md / AGENTS.md against .instruction-ratchet-baseline.json
│
├── tests/                      # pytest suite, one test module per src/ or app/ concern
└── docs/                       # durable reference: this file and architecture.mmd
```

## Rules

- A new UI tab is a new `app/<tab>.py` exposing `render(...)`, routed from `app/streamlit_app.py`. A helper two tabs share goes in a neutral module next to `app/_tx_view.py`, not in either tab.
- Anything that is not rendering goes in `src/`. `src` never imports `app`; the ratchet fails on it.
- A new bank format is one module in `src/parsers/`.
- A new command-line entry point goes in `scripts/` and imports from `src/` only.
- Data files (`config.json`, `data/expenses.db`) are gitignored and never appear in the tree.

## Exceptions

None declared: `extra_roots` in `.fleet.toml` is empty because every tracked root folder is in the `streamlit` preset.

## Baselined offenders

Four functions are over the 100-line limit and recorded at their current length in `.structure-ratchet-baseline.json`: `render` and `_render_rule_summary` in `app/dashboard.py`, and `render` and `_render_keyword_editor` in `app/configuration.py`. They may not grow; splitting one lowers the baseline with `--update-baseline`.

## Verify

```powershell
.\.venv\Scripts\python.exe scripts\structure_ratchet.py
.\.venv\Scripts\python.exe scripts\instruction_ratchet.py
powershell -File scripts/verify-before-ship.ps1
```
