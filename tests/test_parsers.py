from pathlib import Path

import pytest

from src.parsers.caixabank import _description_from_cc
from src.parsers.caixabank import _float_cell
from src.parsers.caixabank import parse_caixabank_file
from src.parsers.revolut import parse_revolut_csv


ROOT = Path(__file__).resolve().parents[1]


def test_caixabank_european_amounts() -> None:
    assert _float_cell("2.000,00") == 2000.0
    assert _float_cell("111,00") == 111.0
    assert _float_cell("5.147,11") == 5147.11
    assert _float_cell("") == 0.0


def test_caixabank_description_only_complementarios() -> None:
    cells = {
        "cc1": "  MERCHANT A  ",
        "cc2": "",
        "cc3": "ES40000…",
        "cc5": "  notes  ",
    }
    for k in range(1, 11):
        cells.setdefault(f"cc{k}", "")
    d = _description_from_cc(cells)
    assert d == "MERCHANT A ES40000… notes"


def test_caixabank_joint_parses() -> None:
    p = ROOT / "tmp" / "input" / "caixabank_joint.xls"
    if not p.is_file():
        pytest.skip("missing tmp/input/caixabank_joint.xls")
    rows = parse_caixabank_file(p, "caixabank_joint", {"type": "auto"})
    assert len(rows) > 0
    r0 = rows[0]
    assert "date" in r0 and "amount" in r0 and "hash" in r0
    assert r0["source"] == "caixabank_joint"


def test_revolut_joint_parses() -> None:
    p = ROOT / "tmp" / "input" / "revolut_joint.csv"
    if not p.is_file():
        pytest.skip("missing tmp/input/revolut_joint.csv")
    rows = parse_revolut_csv(p, "revolut_joint", {})
    assert len(rows) > 0
    assert rows[0]["source"] == "revolut_joint"
