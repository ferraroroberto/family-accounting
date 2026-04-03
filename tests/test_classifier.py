import json
from pathlib import Path

import pytest

from src.classifier import classify_description, classify_full, classify_contribution


@pytest.fixture
def sample_config() -> dict:
    p = Path(__file__).resolve().parents[1] / "config.json"
    if not p.is_file():
        pytest.skip("config.json not present")
    with p.open(encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def minimal_config() -> dict:
    """Self-contained config for contribution tests (no real names)."""
    return {
        "partners": {
            "partner_a": {"name": "Alice Smith", "label": "A"},
            "partner_b": {"name": "Bob Jones", "label": "B"},
        },
        "income": {"partner_a_net": 10000, "partner_b_net": 10000},
        "categories": {},
        "classification_rules": {
            "contribution": {
                "trigger_keywords": ["traspaso", "transfer"],
                "round_number_multiple": 100,
                "case_sensitive": False,
            }
        },
        "accounts": {},
    }


def test_mercadona_food(sample_config: dict) -> None:
    cat, _ = classify_description("Pago MERCADONA Barcelona", sample_config)
    assert cat == "food"


def test_kids_keyword(sample_config: dict) -> None:
    cat, _ = classify_description("COMPRA DECATHLON", sample_config)
    assert cat == "kids"


def test_classify_full_direction(sample_config: dict) -> None:
    cat, direction, rule, partner = classify_full("MERCADONA", -50.0, sample_config)
    assert cat == "food"
    assert direction == "expense"
    assert rule == "mercadona"
    assert partner is None


def test_equal_keyword(sample_config: dict) -> None:
    kws = sample_config.get("classification_rules", {}).get("equal", {}).get("keywords") or []
    if not kws:
        pytest.skip("no equal keywords in config.json")
    kw = kws[0]
    cat, rule = classify_description(kw.upper(), sample_config)
    assert cat == "equal"
    assert rule == kw.lower()


def test_equal_direction(sample_config: dict) -> None:
    kws = sample_config.get("classification_rules", {}).get("equal", {}).get("keywords") or []
    if not kws:
        pytest.skip("no equal keywords in config.json")
    kw = kws[0]
    cat, direction, rule, partner = classify_full(kw, -30.0, sample_config)
    assert cat == "equal"
    assert direction == "expense"
    assert rule == kw.lower()
    assert partner is None


# --- Contribution classification ---

def test_contribution_partner_a(minimal_config: dict) -> None:
    is_c, pk = classify_contribution("TRASPASO ALICE 500", 500.0, minimal_config)
    assert is_c is True
    assert pk == "partner_a"


def test_contribution_partner_b(minimal_config: dict) -> None:
    is_c, pk = classify_contribution("transfer bob jones 300", 300.0, minimal_config)
    assert is_c is True
    assert pk == "partner_b"


def test_contribution_not_round(minimal_config: dict) -> None:
    is_c, pk = classify_contribution("TRASPASO ALICE 550", 550.0, minimal_config)
    assert is_c is False
    assert pk is None


def test_contribution_no_trigger_keyword(minimal_config: dict) -> None:
    is_c, pk = classify_contribution("pago alice 500", 500.0, minimal_config)
    assert is_c is False


def test_contribution_no_person_name(minimal_config: dict) -> None:
    is_c, pk = classify_contribution("TRASPASO DESCONOCIDO 400", 400.0, minimal_config)
    assert is_c is False


def test_contribution_classify_full_returns_category(minimal_config: dict) -> None:
    cat, direction, rule, partner = classify_full("TRASPASO ALICE 200", 200.0, minimal_config)
    assert cat == "contribution"
    assert direction == "contribution"
    assert rule == "contribution"
    assert partner == "partner_a"


def test_contribution_priority_over_other_rules(minimal_config: dict) -> None:
    """Contribution rule runs before keyword-based rules."""
    cfg = dict(minimal_config)
    cfg["classification_rules"] = dict(cfg["classification_rules"])
    cfg["classification_rules"]["food"] = {"keywords": ["alice"], "case_sensitive": False}
    cat, direction, rule, partner = classify_full("TRASPASO ALICE 300", 300.0, cfg)
    assert cat == "contribution"
    assert partner == "partner_a"


def test_contribution_case_insensitive(minimal_config: dict) -> None:
    is_c, pk = classify_contribution("TRANSFER BOB 100", 100.0, minimal_config)
    assert is_c is True
    assert pk == "partner_b"
