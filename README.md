# Family Expense Tracker

A local Streamlit application for tracking shared household expenses between two partners. Bank transactions are imported from exported files, classified into configurable categories, and monthly compensation balances are computed based on each partner's ideal cost-sharing formula.

All personal data (partner names, income figures, classification keywords) live in a gitignored `config.json`. The repository contains only code and a neutral example config — no personal or financial information.

---

## Features

- **Multi-source ingestion** — import CaixaBank `.xls`/`.xlsx` exports and Revolut `.csv` exports into a local SQLite database.
- **Rule-based classification** — keyword matching assigns each transaction to a category (kids, food, house, equal, contribution, or other). Rules are edited live from the UI. Contribution detection uses trigger keywords + partner names + round-number amount check.
- **Flexible share formulas** — per-category cost-sharing supports three modes: `fixed` percentage, `income_ratio` (derived from partner net incomes), and `blended` (fixed base + income-weighted variable).
- **Monthly compensation report** — computes how much each partner owes the other each month, assuming the joint account is funded 50/50. Includes a `contributions_comp` column for partner fund transfers.
- **Reclassification** — re-run classification rules on all non-manually-overridden transactions in one click.
- **Duplicate prevention** — SHA-256 hash per transaction prevents double-imports across overlapping date-range exports.

---

## Project Structure

```
family-accounting/
├── app/                        # Streamlit UI package
│   ├── streamlit_app.py        # entry point: sidebar + tabs
│   ├── dashboard.py            # Dashboard tab: charts and transaction table
│   ├── import_data.py          # Import tab: ingest bank files, reclassify
│   ├── configuration.py        # Configuration tab: edit keywords, view transactions
│   └── .streamlit/
│       └── config.toml         # theme (dark, blue accent)
│
├── src/                        # Business logic (no Streamlit)
│   ├── calculator.py           # share formulas and compensation math
│   ├── classifier.py           # keyword-based transaction classifier
│   ├── config_manager.py       # load / validate / save config.json
│   ├── data_loader.py          # Streamlit-cached config helpers
│   ├── database.py             # SQLite schema, queries, migrations
│   ├── ingest.py               # orchestrate parse → classify → insert
│   ├── logger.py               # shared logging setup
│   └── parsers/
│       ├── caixabank.py        # CaixaBank XLS/XLSX parser (auto-detects layout)
│       └── revolut.py          # Revolut CSV parser
│
├── tests/                      # pytest suite
│   ├── test_calculator.py
│   ├── test_caixabank_xlsx.py
│   ├── test_classifier.py
│   ├── test_configuration_keywords.py
│   ├── test_integration.py
│   ├── test_parsers.py
│   └── test_reports.py
│
├── config.example.json         # neutral example — committed to repo
├── config.json                 # actual config with personal data — gitignored
├── data/expenses.db            # SQLite database — gitignored
├── requirements.txt
├── launch_app.bat              # Windows launcher
└── pytest.ini
```

---

## Setup

### Prerequisites

- Python 3.11+
- A virtual environment (recommended)

### Install

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
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

# Any platform:
PYTHONPATH=. python -m streamlit run app/streamlit_app.py --browser.gatherUsageStats=false
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
  "kids":  { "share_formula": "income_ratio" },
  "food":  { "share_formula": "blended", "share_blended_fixed_base": 0.25, "share_blended_variable_weight": 0.5 },
  "house": { "share_formula": "fixed", "share": { "partner_a": 0.7, "partner_b": 0.3 } },
  "equal": { "share_formula": "fixed", "share": { "partner_a": 0.5, "partner_b": 0.5 } },
  "contribution": { "share_formula": "fixed", "share": { "partner_a": 0.5, "partner_b": 0.5 } },
  "other": { "share_formula": "fixed", "share": { "partner_a": 0.5, "partner_b": 0.5 } }
}
```

The `contribution` category is special: it is excluded from the spending pie chart and from expense compensation. Its impact on the monthly balance is tracked separately via `contributions_comp`.

### `classification_rules`

Keyword lists per category. Matching is substring-based. Priority order: `contribution → kids → food → house → equal → other`.

```json
"classification_rules": {
  "kids":  { "keywords": ["SCHOOL_NAME", "TOY_STORE"], "case_sensitive": false },
  "food":  { "keywords": ["SUPERMARKET_A"], "case_sensitive": false },
  "house": { "keywords": ["UTILITY_CO"], "case_sensitive": false },
  "equal": { "keywords": ["STREAMING_SERVICE"], "case_sensitive": false },
  "contribution": {
    "trigger_keywords": ["traspaso", "transfer"],
    "round_number_multiple": 100,
    "case_sensitive": false
  }
}
```

The `contribution` rule differs from keyword rules: a transaction matches when **all three** conditions hold:

1. Description contains at least one `trigger_keyword` (e.g. `traspaso`, `transfer`).
2. Description contains a word from a partner's name (derived from `partners.partner_a.name` / `partners.partner_b.name`).
3. The amount is a round multiple of `round_number_multiple` (default 100, e.g. 100, 200, 500).

The matched partner determines the compensation sign: partner A contributing → `contributions_comp` is negative (A funded more); partner B contributing → positive (B funded more).

Other keyword rules (`kids`, `food`, `house`, `equal`) can be edited live from the **Configuration** tab in the UI.

### `accounts`

Defines the logical accounts (used for labelling; parser is specified per import source):

```json
"accounts": {
  "caixabank_common": { "label": "CaixaBank shared", "type": "shared", "parser": "caixabank" },
  "revolut_joint":   { "label": "Revolut joint",    "type": "shared", "parser": "revolut" }
}
```

### `bank_imports`

Maps account sources to local file paths for batch import:

```json
"bank_imports": {
  "base_directory": "",
  "sources": [
    {
      "id": "caixabank_joint",
      "account_key": "caixabank_common",
      "file": "tmp/input/your_export.xls",
      "parser": "caixabank",
      "layout": { "sheet_index": 0, "transaction_date_column": "f_valor" }
    },
    {
      "id": "revolut_joint",
      "account_key": "revolut_joint",
      "file": "tmp/input/your_export.csv",
      "parser": "revolut",
      "layout": { "state_filter": "COMPLETED" }
    }
  ]
}
```

---

## Application Tabs

### Dashboard

- Summary metrics: total spending (contributions excluded), transaction count, number of sources.
- Configured share ratios for `kids`, `food`, `house` + a **Contributions** card showing net compensation impact and per-partner totals.
- Pie chart of spending by category (**contributions excluded**).
- Monthly compensation table with per-category columns, `contributions_comp`, `total_comp`, and `total_comp_cumulative`; plus bar and cumulative line charts.
- Transaction table (last 500, newest first) enriched with ideal split columns (`% A`, `% B`, `total A`, `total B`, `net`, `partner`).

### Import Data

- **Import all files** — reads all configured `bank_imports.sources`, parses, classifies, and inserts into the database. Skips duplicates by hash.
- **Reclassify all** — re-runs classification rules on every transaction without a manual override.
- **Preview** — parse a single source in memory without writing to the database.
- Shows per-source and aggregate import statistics.

### Configuration

- Edit classification keywords per category (comma-separated). Saves `config.json` and immediately reclassifies the database.
- Filterable transaction table with the same enriched columns as the dashboard (category, rule, direction, source, date range filters).

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
| `category` | TEXT | `kids` \| `food` \| `house` \| `equal` \| `contribution` \| `other` |
| `direction` | TEXT | `expense` \| `contribution` |
| `partner` | TEXT | Nullable; for contribution attribution |
| `manual_override` | INTEGER | `1` if manually reclassified (skipped on reclassify) |
| `yyyymm` | TEXT | Pre-computed `YYYYMM` for fast grouping |
| `rule` | TEXT | Matched keyword or `default` |
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
total_month      = sum of expenses in that category (negative amounts)
partner_a_share  = from category share formula
amount_ideal_a   = total_month × partner_a_share
amount_paid_a    = total_month / 2          (50/50 account funding)
compensation_a   = amount_paid_a − amount_ideal_a

# positive compensation_a → Partner A underpaid their share → Partner A owes Partner B
# negative compensation_a → Partner A overpaid their share → Partner B owes Partner A
```

`total_comp` per month = sum of expense compensation across tracked categories (`kids`, `food`, `house`, `equal`) **plus** `contributions_comp`.

### Contribution compensation

Transactions classified as `contribution` (partner fund transfers) are excluded from expense compensation and the spending pie chart. Instead, they add a `contributions_comp` column:

```
partner_a contributes amount → contributions_comp -= amount  (A funded more → reduces A's debt)
partner_b contributes amount → contributions_comp += amount  (B funded more → increases A's debt)
```

The matched partner is the one whose name appears in the transaction description alongside a trigger keyword (`traspaso`, `transfer`) and a round amount (multiple of 100).

---

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
