"""Rule-based transaction classification from config."""

from __future__ import annotations

from typing import Any


def _match_keyword(description: str, keyword: str, case_sensitive: bool) -> bool:
    if not keyword:
        return False
    if case_sensitive:
        return keyword in description
    return keyword.lower() in description.lower()


def classify_description(description: str, config: dict[str, Any]) -> tuple[str, str]:
    """
    Return (category, matched_rule_keyword_lower_or_empty).
    Priority: kids > food > house > equal > other.
    """
    desc = description or ""
    rules = config.get("classification_rules", {})
    order = ["kids", "food", "house", "equal"]
    for cat in order:
        block = rules.get(cat) or {}
        keywords = block.get("keywords") or []
        case_sensitive = bool(block.get("case_sensitive", True))
        for kw in keywords:
            if _match_keyword(desc, kw, case_sensitive):
                return cat, str(kw).strip().lower()

    return "other", ""


def classify_amount_hint(amount: float, category: str) -> str:
    """Refine direction: outflows negative for expenses; inflows may be contributions."""
    if amount < 0:
        return "expense"
    if amount > 0 and category == "other":
        return "contribution"
    return "expense"


def classify_full(description: str, amount: float, config: dict[str, Any]) -> tuple[str, str, str]:
    cat, rule = classify_description(description, config)
    direction = classify_amount_hint(amount, cat)
    if not rule:
        rule = "default"
    return cat, direction, rule
