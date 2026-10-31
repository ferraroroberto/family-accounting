"""The nullable CaixaBank-only ``cb_*`` columns, defined once.

The schema DDL, the migration, the INSERT statement and the parser's null
skeleton all derive from this tuple, so adding or renaming a raw field is a
one-line change here.
"""

from __future__ import annotations

from typing import Any

# (column name, SQLite type). Revolut and the compact CaixaBank layout leave these NULL.
CB_DETAIL_COLS: tuple[tuple[str, str], ...] = (
    ("cb_oficina", "TEXT"),
    ("cb_divisa", "TEXT"),
    ("cb_f_operacion", "TEXT"),
    ("cb_f_valor", "TEXT"),
    ("cb_ingreso", "REAL"),
    ("cb_gasto", "REAL"),
    ("cb_saldo_pos", "REAL"),
    ("cb_saldo_neg", "REAL"),
    ("cb_concepto_comun", "TEXT"),
    ("cb_concepto_propio", "TEXT"),
    ("cb_referencia1", "TEXT"),
    ("cb_referencia2", "TEXT"),
    *((f"cb_cc{i}", "TEXT") for i in range(1, 11)),
)

CB_COLUMN_NAMES: tuple[str, ...] = tuple(name for name, _ in CB_DETAIL_COLS)


def cb_null_row() -> dict[str, Any]:
    """A fresh ``cb_*`` mapping with every column NULL."""
    return dict.fromkeys(CB_COLUMN_NAMES)
