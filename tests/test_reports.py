import json
from pathlib import Path

import pandas as pd
import pytest

from src.reports import monthly_compensation_report


@pytest.fixture
def cfg() -> dict:
    p = Path(__file__).resolve().parents[1] / "config.json"
    if not p.is_file():
        pytest.skip("config.json missing")
    with p.open(encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def minimal_cfg() -> dict:
    return {
        "partners": {
            "partner_a": {"name": "Alice", "label": "A"},
            "partner_b": {"name": "Bob", "label": "B"},
        },
        "income": {"partner_a_net": 10000, "partner_b_net": 10000},
        "categories": {
            "food": {"share_formula": "fixed", "share": {"partner_a": 0.5, "partner_b": 0.5}},
            "kids": {"share_formula": "fixed", "share": {"partner_a": 0.5, "partner_b": 0.5}},
        },
        "classification_rules": {},
        "accounts": {},
    }


def test_monthly_report_shape(cfg: dict) -> None:
    df = pd.DataFrame(
        [
            {"date": "2026-01-15", "amount": -100.0, "category": "food", "source": "t"},
            {"date": "2026-01-20", "amount": -50.0, "category": "kids", "source": "t"},
        ]
    )
    rep = monthly_compensation_report(df, cfg)
    assert not rep.empty
    assert "total_comp" in rep.columns
    assert "kids_comp" in rep.columns
    assert "contributions_comp" in rep.columns


def test_contributions_comp_partner_a(minimal_cfg: dict) -> None:
    """A contributes 500 → contributions_comp should be -250 (only excess above 50% ideal counts)."""
    df = pd.DataFrame(
        [
            {
                "date": "2026-02-01",
                "amount": 500.0,
                "category": "contribution",
                "direction": "contribution",
                "partner": "partner_a",
                "source": "t",
            }
        ]
    )
    rep = monthly_compensation_report(df, minimal_cfg)
    assert not rep.empty
    row = rep.iloc[0]
    assert row["contributions_comp"] == pytest.approx(-250.0)
    assert row["total_comp"] == pytest.approx(-250.0)


def test_contributions_comp_partner_b(minimal_cfg: dict) -> None:
    """B contributes 300 → contributions_comp should be +150 (only excess above 50% ideal counts)."""
    df = pd.DataFrame(
        [
            {
                "date": "2026-02-01",
                "amount": 300.0,
                "category": "contribution",
                "direction": "contribution",
                "partner": "partner_b",
                "source": "t",
            }
        ]
    )
    rep = monthly_compensation_report(df, minimal_cfg)
    row = rep.iloc[0]
    assert row["contributions_comp"] == pytest.approx(150.0)
    assert row["total_comp"] == pytest.approx(150.0)


def test_contributions_excluded_from_spending(minimal_cfg: dict) -> None:
    """Contribution rows must not affect expense compensation."""
    df = pd.DataFrame(
        [
            {"date": "2026-03-10", "amount": -100.0, "category": "food", "direction": "expense", "partner": None, "source": "t"},
            {"date": "2026-03-15", "amount": 500.0, "category": "contribution", "direction": "contribution", "partner": "partner_a", "source": "t"},
        ]
    )
    rep = monthly_compensation_report(df, minimal_cfg)
    row = rep.iloc[0]
    # food_comp: -100 * (0.5 - 0.5) = 0 for equal split
    assert row["food_comp"] == pytest.approx(0.0)
    # contributions_comp: -250 (partner_a contributed 500, only excess above 50% = 250)
    assert row["contributions_comp"] == pytest.approx(-250.0)
    assert "total_comp_cumulative" in rep.columns


def test_contributions_comp_mixed_month(minimal_cfg: dict) -> None:
    """A and B both contribute in the same month → net is difference."""
    df = pd.DataFrame(
        [
            {"date": "2026-04-01", "amount": 400.0, "category": "contribution", "direction": "contribution", "partner": "partner_a", "source": "t"},
            {"date": "2026-04-05", "amount": 200.0, "category": "contribution", "direction": "contribution", "partner": "partner_b", "source": "t"},
        ]
    )
    rep = monthly_compensation_report(df, minimal_cfg)
    row = rep.iloc[0]
    # -(400/2) + (200/2) = -200 + 100 = -100
    assert row["contributions_comp"] == pytest.approx(-100.0)
    assert row["total_comp"] == pytest.approx(-100.0)
