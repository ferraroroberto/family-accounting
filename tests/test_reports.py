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
