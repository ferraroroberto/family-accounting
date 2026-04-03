"""Compensation and share calculations."""

from __future__ import annotations

from typing import Any


def income_ratio(config: dict[str, Any]) -> tuple[float, float]:
    inc = config.get("income", {})
    a = float(inc.get("partner_a_net", 0))
    b = float(inc.get("partner_b_net", 0))
    t = a + b
    if t <= 0:
        return 0.5, 0.5
    return a / t, b / t


def share_for_category(config: dict[str, Any], category: str) -> tuple[float, float]:
    """Return (partner_a_share, partner_b_share) for a category."""
    cats = config.get("categories", {})
    c = cats.get(category) or {}
    formula = c.get("share_formula", "fixed")
    ra, rb = income_ratio(config)

    if formula == "income_ratio":
        return ra, rb
    if formula == "blended":
        base = float(c.get("share_blended_fixed_base", 0.25))
        w = float(c.get("share_blended_variable_weight", 0.5))
        sa = base + w * ra
        return sa, 1.0 - sa
    if formula == "fixed":
        sh = c.get("share") or {}
        return float(sh.get("partner_a", 0.5)), float(sh.get("partner_b", 0.5))
    return 0.5, 0.5


def net_ideal_vs_joint_50_50(amount: float, partner_a_share: float) -> float:
    """
    Per-transaction balance line for joint account funded 50/50 vs ideal share partner_a.
    Same sign convention as monthly_category_compensation for outflows: positive =>
    partner A owes partner B; negative => partner B owes partner A (joint funded 50/50).
    Magnitude is |amount| * (partner_a_share - 0.5) for expenses (A's ideal minus A's 50% share of the outflow).
    """
    return amount * (0.5 - partner_a_share)


def monthly_category_compensation(
    total_expense: float,
    config: dict[str, Any],
    category: str,
) -> float:
    """
    Compensation for partner_a: positive => partner_a owes partner_b; negative => partner_b owes partner_a.
    Excel-style: |total|*(share_a - 0.5) for outflows (same magnitude as -parte_a + pagado_a with pagado_a = total/2).
    """
    sa, _ = share_for_category(config, category)
    return net_ideal_vs_joint_50_50(total_expense, sa)


def share_for_transaction_row(
    config: dict[str, Any],
    category: str,
    direction: str,
) -> tuple[float, float]:
    """Ideal (A, B) shares for expenses by category. Contributions are neutral (50/50), not part of compensation."""
    if direction == "contribution":
        return 0.5, 0.5
    return share_for_category(config, category)
