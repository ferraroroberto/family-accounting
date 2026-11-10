"""The transaction classification state: the derive table, the reader predicates and the transitions."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from src.database import (
    assign_hashes,
    clear_manual_override,
    connect,
    init_db,
    insert_transactions,
    reclassify_all,
    set_manual_override,
)
from src.tx_state import (
    TxState,
    count_ambiguous,
    derive_tx_state,
    is_contribution_direction,
    is_partner_contribution,
    tx_states,
)


def _row(
    category: str = "other",
    direction: str = "expense",
    rule: str = "default",
    partner: str | None = None,
    manual_override: int = 0,
) -> dict[str, Any]:
    return {
        "category": category,
        "direction": direction,
        "rule": rule,
        "partner": partner,
        "manual_override": manual_override,
    }


# One row per column combination the app can store, and what it must derive to.
REACHABLE: list[tuple[str, dict[str, Any], TxState]] = [
    ("no rule matched", _row(), TxState.DEFAULT),
    ("keyword rule", _row("kids", rule="school"), TxState.RULED),
    ("keyword rule on a refund", _row("food", rule="market"), TxState.RULED),
    ("personal inflow", _row(direction="income"), TxState.PERSONAL_INCOME),
    ("personal inflow with a rule", _row("food", "income", "market"), TxState.PERSONAL_INCOME),
    ("partner a contribution", _row("contribution", "contribution", "contribution", "partner_a"), TxState.CONTRIBUTION),
    ("partner b contribution", _row("contribution", "contribution", "contribution", "partner_b"), TxState.CONTRIBUTION),
    ("contribution, partner missing", _row("contribution", "contribution", "contribution"), TxState.CONTRIBUTION_NO_PARTNER),
    ("contribution, partner key unknown", _row("contribution", "contribution", "contribution", "partner_c"), TxState.CONTRIBUTION_NO_PARTNER),
    ("unsorted joint inflow", _row(direction="contribution"), TxState.UNSORTED_JOINT_INFLOW),
    ("pinned to a category", _row("kids", rule="manual", manual_override=1), TxState.PINNED),
    ("pinned personal income", _row("other", "income", "manual", manual_override=1), TxState.PINNED),
    ("pinned contribution", _row("contribution", "contribution", "manual", "partner_a", 1), TxState.PINNED_CONTRIBUTION),
    ("pinned contribution, partner (none)", _row("contribution", "contribution", "manual", None, 1), TxState.PINNED_CONTRIBUTION_NO_PARTNER),
    ("pinned to other on an inflow", _row("other", "contribution", "manual", None, 1), TxState.PINNED_UNSORTED_JOINT_INFLOW),
    ("released, still the pinned category", _row("food", rule="manual"), TxState.RELEASED),
    ("released contribution", _row("contribution", "contribution", "manual", "partner_b"), TxState.RELEASED_CONTRIBUTION),
    ("released contribution without partner", _row("contribution", "contribution", "manual"), TxState.RELEASED_CONTRIBUTION_NO_PARTNER),
    ("released unsorted inflow", _row("other", "contribution", "manual"), TxState.RELEASED_UNSORTED_JOINT_INFLOW),
]

# Combinations no write path produces; each must surface as unknown with its reason.
UNREACHABLE: list[tuple[str, dict[str, Any], str]] = [
    ("direction outside the vocabulary", _row("food", "transfer"), "direction"),
    ("contribution category, expense direction", _row("contribution", "expense", "contribution", "partner_a"), "category is contribution"),
    ("contribution direction on a spend category", _row("kids", "contribution", "school"), "on the kids category"),
    ("partner on a spend row", _row("kids", rule="school", partner="partner_a"), "partner partner_a is set"),
    ("pin flag outside 0 and 1", _row(manual_override=2), "manual_override"),
]


@pytest.mark.parametrize(("label", "row", "expected"), REACHABLE, ids=[r[0] for r in REACHABLE])
def test_reachable_row_derives_its_state(label: str, row: dict[str, Any], expected: TxState) -> None:
    reading = derive_tx_state(row)
    assert reading.state is expected, label
    assert reading.reason == ""


@pytest.mark.parametrize(("label", "row", "fragment"), UNREACHABLE, ids=[r[0] for r in UNREACHABLE])
def test_unreachable_row_is_unknown_with_a_reason(label: str, row: dict[str, Any], fragment: str) -> None:
    reading = derive_tx_state(row)
    assert reading.state is TxState.UNKNOWN, label
    assert fragment in reading.reason


def test_every_state_but_unknown_is_derived_by_the_table() -> None:
    assert {r[2] for r in REACHABLE} == set(TxState) - {TxState.UNKNOWN}


def test_absent_and_blank_columns_take_the_stored_defaults() -> None:
    assert derive_tx_state({}).state is TxState.DEFAULT
    assert derive_tx_state({"rule": None, "partner": float("nan"), "manual_override": None}).state is TxState.DEFAULT
    assert derive_tx_state({"category": "contribution"}).state is TxState.CONTRIBUTION_NO_PARTNER
    assert derive_tx_state({"category": "contribution", "partner": "partner_a"}).state is TxState.CONTRIBUTION


def test_derive_reads_a_sqlite_row_and_a_pandas_row(tmp_path: Path) -> None:
    conn = connect(tmp_path / "s.db")
    init_db(conn)
    rows = [
        {"source": "t", "date": "2026-01-01", "description": "x", "amount": 100.0,
         "category": "contribution", "direction": "contribution", "rule": "contribution",
         "partner": "partner_a", "manual_override": 0, "yyyymm": "202601"},
    ]
    assign_hashes(rows)
    insert_transactions(conn, rows)
    sql_row = conn.execute("SELECT * FROM transactions").fetchone()
    assert derive_tx_state(sql_row).state is TxState.CONTRIBUTION
    frame = pd.read_sql_query("SELECT * FROM transactions", conn)
    assert derive_tx_state(frame.iloc[0]).state is TxState.CONTRIBUTION
    conn.close()


def test_reader_predicates_match_each_states_columns() -> None:
    partner_contribution = {s for s in TxState if is_partner_contribution(s)}
    contribution_direction = {s for s in TxState if is_contribution_direction(s)}
    assert partner_contribution == {
        TxState.CONTRIBUTION, TxState.CONTRIBUTION_NO_PARTNER,
        TxState.PINNED_CONTRIBUTION, TxState.PINNED_CONTRIBUTION_NO_PARTNER,
        TxState.RELEASED_CONTRIBUTION, TxState.RELEASED_CONTRIBUTION_NO_PARTNER,
    }
    assert contribution_direction - partner_contribution == {
        TxState.UNSORTED_JOINT_INFLOW, TxState.PINNED_UNSORTED_JOINT_INFLOW,
        TxState.RELEASED_UNSORTED_JOINT_INFLOW,
    }
    assert TxState.UNKNOWN not in contribution_direction


def test_unsorted_inflow_is_neutral_but_not_a_contribution() -> None:
    state = derive_tx_state(_row(direction="contribution")).state
    assert is_contribution_direction(state)
    assert not is_partner_contribution(state)


def test_tx_states_keeps_the_frame_index() -> None:
    df = pd.DataFrame([_row(), _row("contribution", "contribution", "contribution", "partner_a")], index=[7, 9])
    states = tx_states(df)
    assert list(states.index) == [7, 9]
    assert list(states) == [TxState.DEFAULT, TxState.CONTRIBUTION]
    assert tx_states(df.iloc[0:0]).empty


def test_count_ambiguous_counts_each_ambiguity_once_per_row() -> None:
    counts = count_ambiguous(
        [
            TxState.DEFAULT,
            TxState.CONTRIBUTION,
            TxState.CONTRIBUTION_NO_PARTNER,
            TxState.PINNED_CONTRIBUTION_NO_PARTNER,
            TxState.RELEASED,
            TxState.RELEASED_CONTRIBUTION_NO_PARTNER,
            TxState.UNKNOWN,
        ]
    )
    assert counts.contribution_without_partner == 3
    assert counts.released_not_reclassified == 2
    assert counts.unknown == 1


# ---------------------------------------------------------------------------
# Transitions: a row only moves between states through the four writers.
# ---------------------------------------------------------------------------

def _stored_row(conn: sqlite3.Connection, **overrides: Any) -> int:
    row: dict[str, Any] = {
        "source": "t", "date": "2026-01-01", "description": "x", "amount": -10.0,
        "category": "other", "direction": "expense", "rule": "default", "partner": None,
        "manual_override": 0, "yyyymm": "202601", "account_type": "joint",
    }
    row.update(overrides)
    rows = [row]
    assign_hashes(rows)
    insert_transactions(conn, rows)
    return int(conn.execute("SELECT MAX(id) FROM transactions").fetchone()[0])


def _state_of(conn: sqlite3.Connection, tx_id: int) -> TxState:
    return derive_tx_state(conn.execute("SELECT * FROM transactions WHERE id = ?", (tx_id,)).fetchone()).state


def _reclassify_as_food(description: str, amount: float, account_type: str = "joint"):
    return "food", "expense", "market", None


@pytest.fixture
def conn(tmp_path: Path):
    c = connect(tmp_path / "t.db")
    init_db(c)
    yield c
    c.close()


# state-machine-proof: tx_classification
def test_reclassify_refuses_to_move_a_pinned_row(conn: sqlite3.Connection) -> None:
    tx = _stored_row(conn)
    assert set_manual_override(conn, tx, "kids")
    assert _state_of(conn, tx) is TxState.PINNED
    reclassify_all(conn, _reclassify_as_food)
    assert _state_of(conn, tx) is TxState.PINNED
    assert conn.execute("SELECT category FROM transactions WHERE id = ?", (tx,)).fetchone()[0] == "kids"


# state-machine-proof: tx_classification
def test_release_refuses_a_row_that_is_not_pinned(conn: sqlite3.Connection) -> None:
    tx = _stored_row(conn)
    before = _state_of(conn, tx)
    assert clear_manual_override(conn, tx) is False
    assert _state_of(conn, tx) is before is TxState.DEFAULT


# state-machine-proof: tx_classification
def test_pin_refuses_a_row_that_does_not_exist(conn: sqlite3.Connection) -> None:
    assert set_manual_override(conn, 999, "kids") is False


def test_release_leaves_the_pinned_columns_until_the_next_reclassify(conn: sqlite3.Connection) -> None:
    tx = _stored_row(conn)
    assert set_manual_override(conn, tx, "contribution", "partner_a")
    assert _state_of(conn, tx) is TxState.PINNED_CONTRIBUTION
    assert clear_manual_override(conn, tx)
    assert _state_of(conn, tx) is TxState.RELEASED_CONTRIBUTION
    reclassify_all(conn, _reclassify_as_food)
    assert _state_of(conn, tx) is TxState.RULED


def test_pinning_a_contribution_without_a_partner_is_its_own_state(conn: sqlite3.Connection) -> None:
    tx = _stored_row(conn, amount=250.0, direction="contribution")
    assert _state_of(conn, tx) is TxState.UNSORTED_JOINT_INFLOW
    assert set_manual_override(conn, tx, "contribution", None)
    assert _state_of(conn, tx) is TxState.PINNED_CONTRIBUTION_NO_PARTNER
