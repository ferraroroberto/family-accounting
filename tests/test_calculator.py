import json
from pathlib import Path

import pytest

from src.calculator import (
    income_ratio,
    monthly_category_compensation,
    net_ideal_vs_joint_50_50,
    share_for_category,
    share_for_transaction_row,
)


def test_income_ratio_sums_one() -> None:
    cfg = {
        "income": {"partner_a_net": 80, "partner_b_net": 20},
        "categories": {},
    }
    a, b = income_ratio(cfg)
    assert abs(a + b - 1.0) < 1e-9


def test_net_matches_monthly_category_comp() -> None:
    p = Path(__file__).resolve().parents[1] / "config.json"
    if not p.is_file():
        pytest.skip("config.json missing")
    with p.open(encoding="utf-8") as f:
        cfg = json.load(f)
    total = -1000.0
    sa, _ = share_for_category(cfg, "house")
    assert abs(monthly_category_compensation(total, cfg, "house") - net_ideal_vs_joint_50_50(total, sa)) < 1e-9


def test_share_for_transaction_row_contribution_is_neutral() -> None:
    cfg = {
        "income": {"partner_a_net": 80, "partner_b_net": 20},
        "categories": {"other": {"share_formula": "fixed", "share": {"partner_a": 0.3, "partner_b": 0.7}}},
    }
    a, b = share_for_transaction_row(cfg, "other", "contribution")
    assert abs(a - 0.5) < 1e-9 and abs(b - 0.5) < 1e-9


def test_monthly_compensation_sign() -> None:
    p = Path(__file__).resolve().parents[1] / "config.json"
    if not p.is_file():
        pytest.skip("config.json missing")
    with p.open(encoding="utf-8") as f:
        cfg = json.load(f)
    total = -1000.0
    comp = monthly_category_compensation(total, cfg, "house")
    sa, _ = share_for_category(cfg, "house")
    expected = total / 2 - total * sa
    assert abs(comp - expected) < 1e-6
