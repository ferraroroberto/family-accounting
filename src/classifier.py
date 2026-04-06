"""Rule-based transaction classification from config."""

from __future__ import annotations

from typing import Any


def _match_keyword(description: str, keyword: str, case_sensitive: bool) -> bool:
    if not keyword:
        return False
    if case_sensitive:
        return keyword in description
    return keyword.lower() in description.lower()


def _person_keywords_for_partner(partner_cfg: dict) -> list[str]:
    """Full name + each word ≥ 3 chars as match tokens for a partner's name."""
    name = (partner_cfg.get("name") or "").strip()
    if not name:
        return []
    tokens: list[str] = [name]
    for word in name.split():
        if len(word) >= 3 and word not in tokens:
            tokens.append(word)
    return tokens


def _is_round_number(amount: float, multiple: int = 100) -> bool:
    """True if abs(amount) > 0 and is divisible by multiple (within float tolerance)."""
    abs_amt = abs(amount)
    return abs_amt > 0 and (abs_amt % multiple) < 0.01


def classify_contribution(
    description: str, amount: float, config: dict[str, Any]
) -> tuple[bool, str | None]:
    """
    Check if a transaction is a partner contribution (traspaso / transfer).
    Returns (is_contribution, partner_key) where partner_key is 'partner_a' or 'partner_b'.

    Conditions (all must hold):
    - amount is a round multiple of round_number_multiple (default 100)
    - description contains at least one trigger_keyword (e.g. 'traspaso', 'transfer')
    - description contains a word from one of the partner names
    """
    rules = config.get("classification_rules", {})
    rule = rules.get("contribution") or {}
    if not rule:
        return False, None

    case_sensitive = bool(rule.get("case_sensitive", False))

    # description_keywords: positive-amount, description-only match → partner explicit in rule
    if amount > 0:
        for entry in rule.get("description_keywords") or []:
            kw = entry.get("keyword") or ""
            pk = entry.get("partner") or ""
            if kw and pk and _match_keyword(description, kw, case_sensitive):
                return True, pk

    trigger_kws = rule.get("trigger_keywords") or []
    multiple = int(rule.get("round_number_multiple", 100))

    if not _is_round_number(amount, multiple):
        return False, None

    has_trigger = any(_match_keyword(description, kw, case_sensitive) for kw in trigger_kws)
    if not has_trigger:
        return False, None

    partners = config.get("partners", {})
    for pk in ("partner_a", "partner_b"):
        p = partners.get(pk) or {}
        for token in _person_keywords_for_partner(p):
            if _match_keyword(description, token, case_sensitive):
                return True, pk

    return False, None


def classify_description(
    description: str, config: dict[str, Any], rules_key: str = "classification_rules"
) -> tuple[str, str]:
    """
    Return (category, matched_rule_keyword_lower_or_empty).
    Priority: kids > food > health > house > equal > other.
    Contribution detection (which needs amount) is handled in classify_full.
    """
    desc = description or ""
    rules = config.get(rules_key, {})
    order = ["kids", "food", "health", "house", "equal"]
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
    if category == "contribution":
        return "contribution"
    if amount < 0:
        return "expense"
    if amount > 0 and category == "other":
        return "contribution"
    return "expense"


def classify_full(
    description: str, amount: float, config: dict[str, Any], account_type: str = "joint"
) -> tuple[str, str, str, str | None]:
    """
    Return (category, direction, rule, partner_key).

    For personal accounts: uses personal_classification_rules, no contribution detection,
    direction is 'expense' (outflow) or 'income' (inflow).

    For joint accounts: contribution check runs first (highest priority), then
    classification_rules. partner_key is 'partner_a' or 'partner_b' for contributions, None otherwise.
    """
    if account_type == "personal":
        cat, rule = classify_description(description, config, "personal_classification_rules")
        direction = "expense" if amount < 0 else "income"
        return cat, direction, rule or "default", None

    # Joint account logic
    is_contrib, partner_key = classify_contribution(description, amount, config)
    if is_contrib:
        return "contribution", "contribution", "contribution", partner_key

    cat, rule = classify_description(description, config, "classification_rules")
    direction = classify_amount_hint(amount, cat)
    if not rule:
        rule = "default"
    return cat, direction, rule, None
