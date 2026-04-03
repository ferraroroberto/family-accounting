import json
from pathlib import Path

import pytest

from src.classifier import classify_description, classify_full


@pytest.fixture
def sample_config() -> dict:
    p = Path(__file__).resolve().parents[1] / "config.json"
    if not p.is_file():
        pytest.skip("config.json not present")
    with p.open(encoding="utf-8") as f:
        return json.load(f)


def test_mercadona_food(sample_config: dict) -> None:
    cat, _ = classify_description("Pago MERCADONA Barcelona", sample_config)
    assert cat == "food"


def test_kids_keyword(sample_config: dict) -> None:
    cat, _ = classify_description("COMPRA DECATHLON", sample_config)
    assert cat == "kids"


def test_classify_full_direction(sample_config: dict) -> None:
    cat, direction, rule = classify_full("MERCADONA", -50.0, sample_config)
    assert cat == "food"
    assert direction == "expense"
    assert rule == "mercadona"


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
    cat, direction, rule = classify_full(kw, -30.0, sample_config)
    assert cat == "equal"
    assert direction == "expense"
    assert rule == kw.lower()
