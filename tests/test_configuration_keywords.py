"""Keyword normalize/dedupe helpers used by configuration tab."""

from app.configuration import (
    _dedupe_keywords_casefold,
    _finalize_keywords_with_stats,
)


def test_dedupe_case_insensitive_lists_skipped():
    u, skipped = _dedupe_keywords_casefold(["a", "A", "b", "a"])
    assert skipped == ["A", "a"]
    assert u == ["a", "b"]


def test_finalize_sorts_dedupes_and_counts_new():
    kws, dupes, new_n = _finalize_keywords_with_stats("z, a, a, beta", ["z", "a"])
    assert kws == ["a", "beta", "z"]
    assert dupes == ["a"]
    assert new_n == 1  # beta vs prior list


def test_finalize_all_new_when_prev_empty():
    kws, dupes, new_n = _finalize_keywords_with_stats("x, y", [])
    assert set(kws) == {"x", "y"}
    assert dupes == []
    assert new_n == 2
