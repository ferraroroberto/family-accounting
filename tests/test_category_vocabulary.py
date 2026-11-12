"""The category vocabulary and the UTC stamp are each defined once."""

from __future__ import annotations

import re
from pathlib import Path

from src.classifier import ALL_CATEGORIES, RULE_CATEGORIES

ROOT = Path(__file__).resolve().parents[1]
CODE_FOLDERS = ("app", "src", "scripts")
# Two adjacent category names in a quoted list is a re-spelled copy of the tuple.
RESPELLED = re.compile(r"""["']kids["']\s*,\s*["']food["']""")
RAW_UTC_STAMP = '.replace("+00:00", "Z")'


def _python_files() -> list[Path]:
    return [p for folder in CODE_FOLDERS for p in (ROOT / folder).rglob("*.py")]


def test_rule_categories_stay_in_priority_order() -> None:
    assert RULE_CATEGORIES == ("kids", "food", "health", "house", "equal")
    assert ALL_CATEGORIES == (*RULE_CATEGORIES, "contribution", "other")


def test_category_list_is_spelled_out_only_in_the_classifier() -> None:
    offenders = [
        p.relative_to(ROOT).as_posix()
        for p in _python_files()
        if RESPELLED.search(p.read_text(encoding="utf-8"))
        and p.relative_to(ROOT).as_posix() != "src/classifier.py"
    ]
    assert offenders == []


def test_utc_stamp_is_built_only_by_the_database_helper() -> None:
    offenders = [
        p.relative_to(ROOT).as_posix()
        for p in _python_files()
        if RAW_UTC_STAMP in p.read_text(encoding="utf-8")
    ]
    assert offenders == ["src/database.py"]
