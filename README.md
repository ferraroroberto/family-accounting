# family-accounting

A Python library for tracking shared family expenses, computing per-person balances, and calculating the minimal set of money transfers (compensations) needed to settle all debts.

## Features

- Record expenses with a **category** (food, rent, utilities, transport, entertainment, health, education, other)
- Expenses can be **paid by one person** but **shared among any subset** of family members
- Compute each person's **net balance** (positive = is owed money, negative = owes money)
- Calculate the **minimal compensations** (who pays what to whom) to fully settle all debts

## Installation

```bash
pip install -e .
```

For development (includes `pytest` and `ruff`):

```bash
pip install -e ".[dev]"
```

## Quick start

```python
from family_accounting import FamilyAccounting, Expense, Category

fa = FamilyAccounting()

# Alice pays the rent for all three family members
fa.add_expense(Expense("Rent", 900.0, Category.RENT, paid_by="Alice", shared_by=["Alice", "Bob", "Carol"]))

# Bob buys groceries
fa.add_expense(Expense("Groceries", 60.0, Category.FOOD, paid_by="Bob", shared_by=["Alice", "Bob", "Carol"]))

# Carol pays the electricity bill
fa.add_expense(Expense("Electricity", 90.0, Category.UTILITIES, paid_by="Carol", shared_by=["Alice", "Bob", "Carol"]))

# Totals per category
print(fa.get_totals_by_category())
# {<Category.RENT: 'rent'>: 900.0, <Category.FOOD: 'food'>: 60.0, <Category.UTILITIES: 'utilities'>: 90.0}

# Net balance per person
print(fa.compute_balances())
# {'Alice': 550.0, 'Bob': -290.0, 'Carol': -260.0}

# Transfers needed to settle all debts
print(fa.compute_compensations())
# [{'from': 'Bob', 'to': 'Alice', 'amount': 290.0},
#  {'from': 'Carol', 'to': 'Alice', 'amount': 260.0}]
```

## API

### `Category` (enum)

Available expense categories: `FOOD`, `RENT`, `UTILITIES`, `TRANSPORT`, `ENTERTAINMENT`, `HEALTH`, `EDUCATION`, `OTHER`.

### `Expense`

| Field | Type | Description |
|-------|------|-------------|
| `description` | `str` | Short description of the expense |
| `amount` | `float` | Total amount paid (must be positive) |
| `category` | `Category` | Expense category |
| `paid_by` | `str` | Name of the person who paid |
| `shared_by` | `list[str]` | Names of everyone sharing the expense (must include `paid_by`) |

The `share_per_person` property returns `amount / len(shared_by)`.

### `FamilyAccounting`

| Method | Returns | Description |
|--------|---------|-------------|
| `add_expense(expense)` | `None` | Add an expense to the ledger |
| `expenses` | `list[Expense]` | All recorded expenses (read-only copy) |
| `get_expenses_by_category(category)` | `list[Expense]` | Filter expenses by category |
| `get_totals_by_category()` | `dict[Category, float]` | Total amount per category |
| `compute_balances()` | `dict[str, float]` | Net balance per person |
| `compute_compensations()` | `list[dict]` | Minimal transfers to settle debts |

## Development

Run the test suite:

```bash
pytest
```

Lint the code:

```bash
ruff check .
```
