# Family Expense Tracker

A local Streamlit application for tracking shared household expenses between two partners. Bank transactions are imported from exported files, classified into configurable categories, and monthly compensation balances are computed based on each partner's ideal cost-sharing formula.

All personal data (partner names, income figures, classification keywords) live in a gitignored `config.json`. The repository contains only code and a neutral example config — no personal or financial information.

---

## Features

- **Multi-source ingestion** — import CaixaBank `.xls`/`.xlsx` exports and Revolut `.csv` exports into a local SQLite database. Supports joint and personal account sources simultaneously.
- **Joint / Personal account separation** — transactions carry an `account_type` dimension (`joint` or `personal`). Compensation and share logic applies only to joint accounts. Personal transactions are classified by a separate rule set (`personal_classification_rules`).
- **Rule-based classification** — keyword matching assigns each transaction to a category (kids, food, health, house, equal, contribution, or other). Rules are edited live from the UI via dedicated **Joint** and **Personal** sub-tabs. Contribution detection supports two strategies: explicit `description_keywords` (positive amounts, partner declared in config) or trigger keywords + partner name + round-number amount check.
- **Flexible share formulas** — per-category cost-sharing supports three modes: `fixed` percentage, `income_ratio` (derived from partner net incomes), and `blended` (fixed base + income-weighted variable).
- **Monthly compensation report** — computes how much each partner owes the other each month, assuming the joint account is funded 50/50. Includes a `contributions_comp` column for partner fund transfers.
- **Reclassification** — re-run classification rules on all non-manually-overridden transactions in one click (account-type-aware). Individual rows can be **pinned** to a category from the UI so a correction the keywords cannot express survives every future keyword edit.
- **Refunds net against spend** — a `devolucion compra`, direct-debit reversal, or insurance reimbursement reduces the category it was credited back to, rather than being ignored.
- **Duplicate prevention** — SHA-256 hash per transaction prevents double-imports across overlapping date-range exports. Re-running an import with the same files is a no-op, so exporting a wider date range than strictly needed is always safe.

> **Operators:** the deployment-specific runbook — which bank export format to download, what to name the files, and how previous exports are archived — lives as `HANDOFF.md` beside the bank exports themselves, not in this repo (it contains local paths and account detail). This README documents the application; that file documents one installation of it.

---

## Project Structure

```
family-accounting/
├── app/                        # Streamlit UI package
│   ├── streamlit_app.py        # entry point: sidebar + tabs
│   ├── dashboard.py            # Dashboard tab: charts and transaction table
│   ├── import_data.py          # Import tab: ingest bank files, reclassify
│   ├── configuration.py        # Configuration tab: edit keywords, view transactions
│   ├── data_loader.py          # Streamlit-cached config helpers
│   └── .streamlit/
│       └── config.toml         # theme (dark, blue accent)
│
├── src/                        # Business logic (no Streamlit)
│   ├── calculator.py           # share formulas and compensation math
│   ├── classifier.py           # keyword-based transaction classifier
│   ├── config_manager.py       # load / validate / save config.json
│   ├── database.py             # SQLite schema, queries, migrations
│   ├── ingest.py               # orchestrate parse → classify → insert
│   ├── logger.py               # shared logging setup
│   └── parsers/
│       ├── caixabank.py        # CaixaBank XLS/XLSX parser (auto-detects layout)
│       └── revolut.py          # Revolut CSV parser
│
├── scripts/                    # CLI entry points (no Streamlit)
│   ├── import_bank_files.py    # run the configured imports; --dry-run
│   └── classify_triage.py      # unclassified report, keyword vetting, balance
│
├── tests/                      # pytest suite
│   ├── test_calculator.py
│   ├── test_caixabank_xlsx.py
│   ├── test_classifier.py
│   ├── test_configuration_keywords.py
│   ├── test_database.py
│   ├── test_integration.py
│   ├── test_parsers.py
│   ├── test_reports.py
│   └── test_source_resolution.py
│
├── config.example.json         # neutral example — committed to repo
├── config.json                 # actual config with personal data — gitignored
├── data/expenses.db            # SQLite database — gitignored
├── requirements.txt
├── launch_app.bat              # Windows launcher
└── pytest.ini
```

Where new code goes, and the structure ratchet that guards it: [`docs/layout.md`](docs/layout.md).

---

## Setup

### Prerequisites

- Python 3.11+
- A virtual environment (recommended)

### Install

```bash
python -m venv .venv

# Windows
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# macOS / Linux
./.venv/bin/python -m pip install -r requirements.txt
```

### Configure

Copy the example config and edit it with your actual data:

```bash
cp config.example.json config.json
```

Edit `config.json` to set:
- Partner names and labels
- Net income values (used for income-ratio share formulas)
- Category share formulas and fixed percentages
- Classification keywords per category
- Account definitions and bank import file paths

See [`config.example.json`](config.example.json) for the full schema with annotations.

### Run

```bash
# Windows — double-click or run:
launch_app.bat

# macOS / Linux:
PYTHONPATH=. ./.venv/bin/python -m streamlit run app/streamlit_app.py --browser.gatherUsageStats=false
```

---

## Configuration Schema

`config.json` (and `config.example.json`) has six top-level sections:

### `partners`

```json
"partners": {
  "partner_a": { "name": "Partner A", "label": "A" },
  "partner_b": { "name": "Partner B", "label": "B" }
}
```

### `income`

Net annual income per partner. Used to compute income-ratio shares:

```json
"income": {
  "partner_a_net": 100000,
  "partner_b_net": 40000
}
```

### `categories`

Each category defines a share formula:

| Formula | Description |
|---------|-------------|
| `income_ratio` | `share_a = income_a / (income_a + income_b)` |
| `blended` | `share_a = fixed_base + variable_weight × income_ratio_a` |
| `fixed` | explicit `share.partner_a` and `share.partner_b` values |

```json
"categories": {
  "kids":   { "share_formula": "income_ratio" },
  "food":   { "share_formula": "blended", "share_blended_fixed_base": 0.25, "share_blended_variable_weight": 0.5 },
  "health": { "share_formula": "blended", "share_blended_fixed_base": 0.25, "share_blended_variable_weight": 0.5 },
  "house":  { "share_formula": "fixed", "share": { "partner_a": 0.7, "partner_b": 0.3 } },
  "equal":  { "share_formula": "fixed", "share": { "partner_a": 0.5, "partner_b": 0.5 } },
  "contribution": { "share_formula": "fixed", "share": { "partner_a": 0.5, "partner_b": 0.5 } },
  "other":  { "share_formula": "fixed", "share": { "partner_a": 0.5, "partner_b": 0.5 } }
}
```

The `contribution` category is special: it is excluded from the spending pie chart and from expense compensation. Its impact on the monthly balance is tracked separately via `contributions_comp`.

### `classification_rules`

Keyword lists per category for **joint account** transactions. Matching is substring-based. Priority order: `contribution → kids → food → health → house → equal → other`.

```json
"classification_rules": {
  "kids":   { "keywords": ["SCHOOL_NAME", "TOY_STORE"], "case_sensitive": false },
  "food":   { "keywords": ["SUPERMARKET_A"], "case_sensitive": false },
  "health": { "keywords": ["farmacia", "isdin", "naturitas", "parafarmacia"], "case_sensitive": false },
  "house":  { "keywords": ["UTILITY_CO"], "case_sensitive": false },
  "equal":  { "keywords": ["STREAMING_SERVICE"], "case_sensitive": false },
  "contribution": {
    "description_keywords": [
      { "keyword": "top-up by *0573", "partner": "partner_a" }
    ],
    "trigger_keywords": ["traspaso", "transfer"],
    "round_number_multiple": 100,
    "case_sensitive": false
  }
}
```

The `contribution` rule supports two match strategies (checked in order):

**1. `description_keywords` — description + positive amount (partner explicit):**
Each entry maps a description substring to a partner key. Applied only when `amount > 0`. Use this for bank top-ups or transfers where the partner is identifiable by a card number or fixed text rather than by name.

**2. `trigger_keywords` + partner name + round amount:**
A transaction matches when **all three** conditions hold:
1. Description contains at least one `trigger_keyword` (e.g. `traspaso`, `transfer`).
2. Description contains a word from a partner's name (derived from `partners.partner_a.name` / `partners.partner_b.name`).
3. The amount is a round multiple of `round_number_multiple` (default 100, e.g. 100, 200, 500).

The matched partner determines the compensation sign: partner A contributing → `contributions_comp` is negative (A funded more); partner B contributing → positive (B funded more).

Other keyword rules (`kids`, `food`, `house`, `equal`) can be edited live from the **Configuration** tab in the UI.

### `personal_classification_rules`

Same structure as `classification_rules` but applied **only to personal account transactions**. Compensation and share logic is never computed for personal transactions. Edit via the **Configuration → Personal** tab.

```json
"personal_classification_rules": {
  "kids":   { "keywords": [], "case_sensitive": false },
  "food":   { "keywords": ["example_cafeteria"], "case_sensitive": false },
  "health": { "keywords": ["example_pharmacy"], "case_sensitive": false },
  "house":  { "keywords": ["example_community_fees", "example_mortgage"], "case_sensitive": false },
  "equal":  { "keywords": ["example_saas", "example_transport"], "case_sensitive": false }
}
```

### `accounts`

Defines the logical accounts. Accounts with `"type": "personal"` produce `account_type = "personal"` rows in the database; `"type": "shared"` produces `account_type = "joint"` rows.

```json
"accounts": {
  "caixabank_common":   { "label": "CaixaBank shared",   "type": "shared",   "parser": "caixabank" },
  "revolut_joint":      { "label": "Revolut joint",      "type": "shared",   "parser": "revolut" },
  "caixabank_personal": { "label": "CaixaBank Personal", "type": "personal", "owner": "partner_a", "parser": "caixabank" }
}
```

### `bank_imports`

Maps account sources to local file paths for batch import:

```json
"bank_imports": {
  "base_directory": "tmp/input",
  "sources": [
    {
      "id": "caixabank_joint",
      "account_key": "caixabank_common",
      "file": "caixabank_joint_export_2*.xls",
      "parser": "caixabank",
      "layout": { "sheet_index": 0, "transaction_date_column": "f_valor" }
    },
    {
      "id": "revolut_joint",
      "account_key": "revolut_joint",
      "file": "joint_account-statement_*.csv",
      "parser": "revolut",
      "layout": { "state_filter": "COMPLETED" }
    }
  ]
}
```

**`base_directory`** may be relative to the project root or an **absolute path** — point it at wherever your bank downloads land (a synced cloud folder, for example) and skip copying files into the repo.

**`file`** may be a plain filename or a **glob pattern**. With a glob, the newest match by modification time is used, so exports whose names carry a date range (`..._2026-04-01_2026-08-24.XLS`) can be dropped into the folder without editing the config each cycle. The Import tab shows the concrete file each source resolved to, and the import log records it. An unmatched pattern raises a clear error rather than silently importing nothing.

---

## Application Tabs

### Dashboard

- Summary metrics: total joint spending (contributions excluded), total transaction count, joint vs personal split.
- Configured share ratios for `kids`, `food`, `health`, `house` + a **Contributions** card showing net compensation impact and per-partner totals. All compensation calculated on **joint** transactions only.
- Pie chart of spending by category — joint accounts only (**contributions excluded**).
- Monthly compensation table with per-category columns, `contributions_comp`, `total_comp`, and `total_comp_cumulative`; plus bar and cumulative line charts.
- **Rule summary** — aggregated stats by rule and category, with an **Account type** selector (default: `joint`) and date range filter. Filtered transactions shown below with split columns (joint) or plain view (personal).

### Import Data

- **Configured sources** — lists each source with the concrete file it resolved to (important when `file` is a glob), and the `base_directory` it read from.
- **Import all files** — reads all configured `bank_imports.sources`, parses, classifies (using joint or personal rules per source), and inserts into the database. Skips duplicates by hash.
- **Reclassify all** — re-runs classification rules on every transaction without a manual override (account-type-aware).
- **Preview** — parse a single source in memory without writing to the database.
- Shows per-source and aggregate import statistics.

### Configuration

- **Joint** sub-tab: edit classification keywords for joint account categories. Saves `config.json` and immediately reclassifies the database.
- **Personal** sub-tab: edit classification keywords for personal account categories (stored under `personal_classification_rules`).
- **Manual override**: pin one transaction to a category (`manual_override = 1`) so reclassification leaves it alone, and release it again later. Use it where a keyword cannot express the correction — most often an internal transfer between two joint accounts, which looks exactly like a partner contribution and would otherwise be counted twice. Pinning to `contribution` with no partner marks a row explicitly neutral: excluded from expense compensation and worth zero in `contributions_comp`.
- Filterable transaction table with **Account type** selector (joint/personal), category, rule, direction, source, and date range filters. Enriched split columns shown for joint transactions only.

---

## Data Model

The SQLite database (`data/expenses.db`) contains two tables:

### `transactions`

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Auto-increment |
| `source` | TEXT | Import source ID (e.g. `caixabank_joint`) |
| `date` | TEXT | ISO date (YYYY-MM-DD) |
| `value_date` | TEXT | Value date (nullable) |
| `description` | TEXT | Lowercase, space-joined description |
| `amount` | REAL | Negative = expense, positive = income/contribution |
| `balance` | REAL | Post-transaction balance (nullable) |
| `category` | TEXT | `kids` \| `food` \| `health` \| `house` \| `equal` \| `contribution` \| `other` |
| `direction` | TEXT | `expense` \| `contribution` (joint) or `expense` \| `income` (personal) |
| `partner` | TEXT | Nullable; for contribution attribution |
| `manual_override` | INTEGER | `1` if pinned via **Configuration → Manual override** (skipped on reclassify) |
| `yyyymm` | TEXT | Pre-computed `YYYYMM` for fast grouping |
| `rule` | TEXT | Matched keyword or `default` |
| `account_type` | TEXT | `joint` or `personal` — derived from account config |
| `extra_json` | TEXT | Reserved for future parser metadata |
| `cb_*` columns | varies | CaixaBank raw fields (NULL for Revolut rows) |
| `hash` | TEXT UNIQUE | SHA-256 deduplication key |
| `created_at` / `updated_at` | TEXT | ISO timestamps |

### `import_log`

Records each import run: source, filename, records added/skipped, date range.

---

## Parsers

### CaixaBank (`.xls` / `.xlsx`)

Auto-detects the header row by scanning up to 50 rows. Supports two layouts:

- **Wide export** (CaixaBankNow full detail): columns `F. Valor`, `F. Operación`, `Ingreso (+)`, `Gasto (-)`, plus `Concepto complementario 1–10` for description.
- **Compact export** (older format): columns `Fecha`, `Movimiento`, `Importe`.

European number format (`1.234,56`) is handled automatically. All raw CaixaBank fields are stored in `cb_*` columns.

### Revolut (`.csv`)

Standard Revolut CSV export. Filters to `State == COMPLETED` by default. Falls back to `Started Date` when `Completed Date` is missing. Column mapping is configurable via `layout.columns`.

---

## Compensation Logic

The joint account is assumed to be **funded 50/50** by both partners. For each category and each calendar month:

```
total_month      = net of that category (outflows less any refunds credited back)
partner_a_share  = from category share formula
amount_ideal_a   = total_month × partner_a_share
amount_paid_a    = total_month / 2          (50/50 account funding)
compensation_a   = amount_paid_a − amount_ideal_a

# positive compensation_a → Partner A underpaid their share → Partner A owes Partner B
# negative compensation_a → Partner A overpaid their share → Partner B owes Partner A
```

`total_comp` per month = sum of expense compensation across tracked categories (`kids`, `food`, `health`, `house`, `equal`) **plus** `contributions_comp`.

### Contribution compensation

Transactions classified as `contribution` (partner fund transfers) are excluded from expense compensation and the spending pie chart. Instead, they add a `contributions_comp` column:

```
partner_a contributes amount → contributions_comp -= amount / 2  (A overpaid by half → reduces A's debt)
partner_b contributes amount → contributions_comp += amount / 2  (B overpaid by half → increases A's debt)
```

Only the excess above each partner's ideal 50 % share counts (the joint account is funded 50/50, so a contribution of X means each partner "should" have paid X/2; the contributing partner actually paid X, overpaying by X/2).

The matched partner is the one whose name appears in the transaction description alongside a trigger keyword (`traspaso`, `transfer`) and a round amount (multiple of 100).

---

## Command line

Everything the UI does to the data is also reachable headlessly, for runbooks and scripted updates. Run from the project root so `src/` is importable.

```bash
# Import the configured sources (same as "Import all files"). Idempotent.
python -m scripts.import_bank_files
python -m scripts.import_bank_files --dry-run     # parse + classify, write nothing

# How much spending is unclassified, and what it costs the report
python -m scripts.classify_triage --summary --since 2026-04-03
python -m scripts.classify_triage --unclassified

# Vet candidate keywords BEFORE adding them — matching is plain substring,
# so short keywords capture unrelated rows ("bp" matches "stripe…bppqydx")
python -m scripts.classify_triage --check "sorli,cepsa,bp"

# Monthly compensation table + running balance
python -m scripts.classify_triage --compensation
```

Unclassified **joint** rows are excluded from the compensation maths, so they understate what is owed — `--summary` reports that share explicitly rather than letting it pass as a clean run.

## Testing

```bash
pytest
```

Several tests require `config.json` to be present and skip automatically when it is absent. Tests that depend on local bank files in `tmp/input/` also skip if the files are not present.

---

## Security Notes

- No network calls. No credentials. All data is local.
- `config.json` (personal rules and income) is gitignored.
- `data/*.db` (transaction database) is gitignored.
- `tmp/` (local input files and working notes) is gitignored.

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| UI | [Streamlit](https://streamlit.io) ≥ 1.30 |
| Data | [pandas](https://pandas.pydata.org) ≥ 2.0 |
| Charts | [Plotly](https://plotly.com/python/) ≥ 5.18 |
| Database | SQLite (stdlib `sqlite3`) |
| XLS parsing | [xlrd](https://xlrd.readthedocs.io) ≥ 2.0, [openpyxl](https://openpyxl.readthedocs.io) ≥ 3.1 |
| Config validation | [jsonschema](https://python-jsonschema.readthedocs.io) ≥ 4.20 |
| Testing | [pytest](https://pytest.org) ≥ 8.0 |
