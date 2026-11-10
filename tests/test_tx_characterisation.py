"""Pins the numbers the three contribution readers produce over a fixture holding every row kind.

The fixture is built through the real write paths (classifier, insert, pin, release),
so each row kind is one the app can really store. The expected values below were
recorded from the code before the readers moved onto ``src/tx_state.py`` and must not
change when they do: the monthly compensation report, the dashboard split frames and
the per-row ideal split all keep their numbers.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from app._tx_view import enrich_transactions_split, load_transactions_df
from app.dashboard import _split_joint_frames
from src.classifier import classify_full
from src.database import (
    assign_hashes,
    clear_manual_override,
    connect,
    init_db,
    insert_transactions,
    set_manual_override,
)
from src.reports import monthly_compensation_report

CFG: dict[str, Any] = {
    "partners": {
        "partner_a": {"name": "Alice", "label": "A"},
        "partner_b": {"name": "Bob", "label": "B"},
    },
    "income": {"partner_a_net": 3000, "partner_b_net": 1000},
    "categories": {
        "kids": {"share_formula": "fixed", "share": {"partner_a": 0.7, "partner_b": 0.3}},
        "food": {"share_formula": "income_ratio"},
        "health": {"share_formula": "fixed", "share": {"partner_a": 0.5, "partner_b": 0.5}},
        "house": {"share_formula": "fixed", "share": {"partner_a": 0.6, "partner_b": 0.4}},
        "equal": {"share_formula": "fixed", "share": {"partner_a": 0.5, "partner_b": 0.5}},
        "other": {"share_formula": "fixed", "share": {"partner_a": 0.4, "partner_b": 0.6}},
    },
    "classification_rules": {
        "kids": {"keywords": ["school"]},
        "food": {"keywords": ["market"]},
        "contribution": {"trigger_keywords": ["traspaso"], "round_number_multiple": 100},
    },
    "personal_classification_rules": {"food": {"keywords": ["market"]}},
}

# (key, date, description, amount, account_type, follow-up)
# follow-up: None | ("pin", category, partner) | ("release", category, partner)
_ROWS: list[tuple[str, str, str, float, str, tuple[str, str, str | None] | None]] = [
    ("default", "2026-01-05", "random shop", -40.0, "joint", None),
    ("ruled_food", "2026-01-06", "market purchase", -60.0, "joint", None),
    ("ruled_kids", "2026-01-07", "school fees", -100.0, "joint", None),
    ("ruled_refund", "2026-01-08", "school refund", 20.0, "joint", None),
    ("contribution_a", "2026-01-10", "traspaso alice", 500.0, "joint", None),
    ("contribution_b", "2026-02-10", "traspaso bob", 300.0, "joint", None),
    ("unsorted_inflow", "2026-02-11", "mystery inflow", 250.5, "joint", None),
    ("pinned", "2026-02-12", "odd one", -75.0, "joint", ("pin", "kids", None)),
    ("pinned_contribution", "2026-02-13", "internal move", 200.0, "joint", ("pin", "contribution", "partner_a")),
    ("pinned_contribution_no_partner", "2026-02-14", "internal move two", 120.0, "joint", ("pin", "contribution", None)),
    ("pinned_unsorted_inflow", "2026-02-15", "pinned inflow", 90.0, "joint", ("pin", "other", None)),
    ("released", "2026-03-01", "released spend", -35.0, "joint", ("release", "food", None)),
    ("released_contribution", "2026-03-02", "released move", 400.0, "joint", ("release", "contribution", "partner_b")),
    ("released_contribution_no_partner", "2026-03-03", "released move two", 160.0, "joint", ("release", "contribution", None)),
    ("released_unsorted_inflow", "2026-03-04", "released inflow", 55.0, "joint", ("release", "other", None)),
    ("personal_income", "2026-03-05", "salary", 1000.0, "personal", None),
    ("personal_spend", "2026-03-06", "market personal", -30.0, "personal", None),
    ("unknown", "2026-03-07", "legacy oddity", -25.0, "joint", None),
]


def _build_fixture(path: Path) -> tuple[sqlite3.Connection, dict[str, int]]:
    conn = connect(path)
    init_db(conn)
    rows: list[dict[str, Any]] = []
    for key, date, desc, amount, acct, _follow in _ROWS:
        cat, direction, rule, partner = classify_full(desc, amount, CFG, acct)
        rows.append(
            {
                "source": "t", "date": date, "description": desc, "amount": amount,
                "category": cat, "direction": direction, "rule": rule, "partner": partner,
                "manual_override": 0, "yyyymm": date[:4] + date[5:7], "account_type": acct,
            }
        )
    assign_hashes(rows)
    insert_transactions(conn, rows)
    ids = {
        key: int(conn.execute("SELECT id FROM transactions WHERE description = ?", (desc,)).fetchone()[0])
        for key, _d, desc, _a, _t, _f in _ROWS
    }
    for key, _date, _desc, _amount, _acct, follow in _ROWS:
        if follow is None:
            continue
        kind, category, partner = follow
        assert set_manual_override(conn, ids[key], category, partner)
        if kind == "release":
            assert clear_manual_override(conn, ids[key])
    # A value no write path produces: a direction outside the vocabulary on a spend category.
    conn.execute(
        "UPDATE transactions SET direction = 'transfer', category = 'food' WHERE id = ?",
        (ids["unknown"],),
    )
    conn.commit()
    return conn, ids


@pytest.fixture
def fixture(tmp_path: Path):
    conn, ids = _build_fixture(tmp_path / "fixture.db")
    yield conn, ids
    conn.close()


def _by_key(ids: dict[str, int], id_set: Any) -> list[str]:
    inverse = {v: k for k, v in ids.items()}
    return sorted(inverse[int(i)] for i in id_set)


def test_fixture_reaches_every_row_kind(fixture) -> None:
    conn, ids = fixture
    df = load_transactions_df(conn)
    assert len(df) == len(_ROWS)
    assert set(df["id"]) == set(ids.values())


def test_monthly_report_numbers_are_pinned(fixture) -> None:
    conn, _ids = fixture
    df = load_transactions_df(conn)
    joint = df[df["account_type"] == "joint"]
    rep = monthly_compensation_report(joint, CFG)
    got = {
        r["month"]: {
            k: round(float(v), 6)
            for k, v in r.items()
            if k not in ("month", "balance_note")
        }
        for r in rep.to_dict("records")
    }
    assert got == EXPECTED_REPORT
    assert list(rep["balance_note"]) == EXPECTED_NOTES


def test_dashboard_split_frames_are_pinned(fixture) -> None:
    conn, ids = fixture
    df = load_transactions_df(conn)
    joint_df, expenses, contrib_df = _split_joint_frames(df)
    assert _by_key(ids, joint_df["id"]) == EXPECTED_JOINT
    assert _by_key(ids, expenses["id"]) == EXPECTED_EXPENSES
    assert round(float(expenses["amount_abs"].sum()), 6) == EXPECTED_EXPENSE_TOTAL
    assert _by_key(ids, contrib_df["id"]) == EXPECTED_CONTRIB
    assert round(float(contrib_df["amount"].sum()), 6) == EXPECTED_CONTRIB_TOTAL


def test_per_row_split_is_pinned(fixture) -> None:
    conn, ids = fixture
    df = load_transactions_df(conn)
    out = enrich_transactions_split(df, CFG)
    inverse = {v: k for k, v in ids.items()}
    got = {
        inverse[int(r["id"])]: (r["% A"], r["% B"], r["total A"], r["total B"], r["net"])
        for r in out.to_dict("records")
    }
    assert got == EXPECTED_SPLIT


def test_report_frame_without_direction_column_matches_full_frame(fixture) -> None:
    """The report accepts frames lacking direction, partner and rule; contributions still count."""
    conn, _ids = fixture
    df = load_transactions_df(conn)
    joint = df[df["account_type"] == "joint"]
    slim = joint[["date", "amount", "category", "partner"]]
    full = monthly_compensation_report(joint, CFG)
    lean = monthly_compensation_report(slim, CFG)
    pd.testing.assert_series_equal(
        full["contributions_comp"], lean["contributions_comp"], check_names=False
    )


EXPECTED_REPORT: dict[str, dict[str, float]] = {
    "202601": {
        "kids_comp": 16.0, "food_comp": 15.0, "health_comp": 0.0, "house_comp": 0.0,
        "equal_comp": 0.0, "contributions_comp": -250.0, "total_comp": -219.0,
        "total_comp_cumulative": -219.0,
    },
    "202602": {
        "kids_comp": 15.0, "food_comp": 0.0, "health_comp": 0.0, "house_comp": 0.0,
        "equal_comp": 0.0, "contributions_comp": 50.0, "total_comp": 65.0,
        "total_comp_cumulative": -154.0,
    },
    "202603": {
        "kids_comp": 0.0, "food_comp": 15.0, "health_comp": 0.0, "house_comp": 0.0,
        "equal_comp": 0.0, "contributions_comp": 200.0, "total_comp": 215.0,
        "total_comp_cumulative": 61.0,
    },
}
EXPECTED_NOTES: list[str] = ["Bob owes Alice", "Alice owes Bob", "Alice owes Bob"]
EXPECTED_JOINT: list[str] = sorted(
    [
        "contribution_a", "contribution_b", "default", "pinned", "pinned_contribution",
        "pinned_contribution_no_partner", "pinned_unsorted_inflow", "released",
        "released_contribution", "released_contribution_no_partner",
        "released_unsorted_inflow", "ruled_food", "ruled_kids", "ruled_refund", "unknown",
        "unsorted_inflow",
    ]
)
EXPECTED_EXPENSES: list[str] = ["default", "pinned", "released", "ruled_food", "ruled_kids", "unknown"]
EXPECTED_EXPENSE_TOTAL = 335.0
EXPECTED_CONTRIB: list[str] = [
    "contribution_a", "contribution_b", "pinned_contribution",
    "pinned_contribution_no_partner", "released_contribution",
    "released_contribution_no_partner",
]
EXPECTED_CONTRIB_TOTAL = 1680.0
EXPECTED_SPLIT: dict[str, tuple[str, str, float, float, float]] = {
    "default": ("40.0%", "60.0%", 16.0, 24.0, -4.0),
    "ruled_food": ("75.0%", "25.0%", 45.0, 15.0, 15.0),
    "ruled_kids": ("70.0%", "30.0%", 70.0, 30.0, 20.0),
    "ruled_refund": ("70.0%", "30.0%", 14.0, 6.0, -4.0),
    "contribution_a": ("50.0%", "50.0%", 250.0, 250.0, 0.0),
    "contribution_b": ("50.0%", "50.0%", 150.0, 150.0, 0.0),
    "unsorted_inflow": ("50.0%", "50.0%", 125.25, 125.25, 0.0),
    "pinned": ("70.0%", "30.0%", 52.5, 22.5, 15.0),
    "pinned_contribution": ("50.0%", "50.0%", 100.0, 100.0, 0.0),
    "pinned_contribution_no_partner": ("50.0%", "50.0%", 60.0, 60.0, 0.0),
    "pinned_unsorted_inflow": ("50.0%", "50.0%", 45.0, 45.0, 0.0),
    "released": ("75.0%", "25.0%", 26.25, 8.75, 8.75),
    "released_contribution": ("50.0%", "50.0%", 200.0, 200.0, 0.0),
    "released_contribution_no_partner": ("50.0%", "50.0%", 80.0, 80.0, 0.0),
    "released_unsorted_inflow": ("50.0%", "50.0%", 27.5, 27.5, 0.0),
    "personal_income": ("40.0%", "60.0%", 400.0, 600.0, 100.0),
    "personal_spend": ("75.0%", "25.0%", 22.5, 7.5, 7.5),
    "unknown": ("75.0%", "25.0%", 18.75, 6.25, 6.25),
}
