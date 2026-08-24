"""Triage unclassified transactions, vet candidate keywords, and read the balance.

Unclassified joint rows are excluded from the compensation maths, so they silently
understate what is owed — ``--summary`` quantifies that, ``--compensation`` shows the
resulting balance.

Classification is plain case-insensitive **substring** matching, so a short keyword
can capture unrelated rows (``bp`` matches ``stripe…bppqydx``; ``365`` matches account
reference ``…58737396``). Always run ``--check`` before editing the keyword lists.

Usage (from the repo root):

    & .\\.venv\\Scripts\\python.exe -m scripts.classify_triage --summary
    & .\\.venv\\Scripts\\python.exe -m scripts.classify_triage --unclassified --since 2026-04-03
    & .\\.venv\\Scripts\\python.exe -m scripts.classify_triage --check "sorli,cepsa,bp"
    & .\\.venv\\Scripts\\python.exe -m scripts.classify_triage --compensation
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from typing import Any

from src.database import connect, default_db_path

COMPENSATION_CATEGORIES = ("kids", "food", "health", "house", "equal")


def _rows(conn: sqlite3.Connection) -> list[tuple[str, str, float, str]]:
    return [
        (r["description"], r["category"], float(r["amount"]), r["account_type"] or "joint")
        for r in conn.execute(
            "SELECT description, category, amount, account_type FROM transactions"
        )
    ]


def summary(conn: sqlite3.Connection, account: str, since: str | None) -> None:
    """Category totals plus the share of spending sitting in 'other'."""
    where = "account_type = ?"
    params: list[Any] = [account]
    if since:
        where += " AND date > ?"
        params.append(since)

    print(f"category totals — account_type={account}" + (f", date > {since}" if since else ""))
    for row in conn.execute(
        f"SELECT category, COUNT(*) n, ROUND(SUM(amount), 2) t FROM transactions"
        f" WHERE {where} GROUP BY category ORDER BY t",
        params,
    ):
        print(f"  {row['category']:<13} {row['n']:>5} rows {row['t']:>14,.2f}")

    unc = conn.execute(
        f"SELECT COUNT(*) n, COALESCE(ROUND(SUM(amount), 2), 0) t FROM transactions"
        f" WHERE {where} AND category = 'other' AND amount < 0",
        params,
    ).fetchone()
    cls = conn.execute(
        f"SELECT COALESCE(ROUND(SUM(amount), 2), 0) t FROM transactions"
        f" WHERE {where} AND category IN {COMPENSATION_CATEGORIES} AND amount < 0",
        params,
    ).fetchone()["t"]

    total = unc["t"] + cls
    pct = (100 * unc["t"] / total) if total else 0.0
    print(f"\nunclassified outflow: {unc['n']} rows {unc['t']:,.2f} EUR = {pct:.1f}% of spending")
    if account == "joint":
        print("(joint 'other' is excluded from compensation — this is money the report misses)")


def unclassified(conn: sqlite3.Connection, account: str, since: str | None, limit: int) -> None:
    """Outflows stuck in 'other', grouped by description, biggest first."""
    where = "account_type = ? AND category = 'other' AND amount < 0"
    params: list[Any] = [account]
    if since:
        where += " AND date > ?"
        params.append(since)
    params.append(limit)

    print(f"unclassified outflows — account_type={account}" + (f", date > {since}" if since else ""))
    for row in conn.execute(
        f"SELECT description, COUNT(*) n, ROUND(SUM(amount), 2) t FROM transactions"
        f" WHERE {where} GROUP BY description ORDER BY t ASC LIMIT ?",
        params,
    ):
        print(f"  {row['n']:>3}x {row['t']:>10,.2f}  {row['description'][:64]}")


def check(conn: sqlite3.Connection, keywords: list[str]) -> None:
    """Report every row a candidate keyword would match, grouped by current category.

    A keyword whose matches are all currently 'other' is safe. Matches already in
    another category mean the keyword will *move* those rows — fine when it is a
    correction, a bug when the match is incidental.
    """
    rows = _rows(conn)
    verdicts: list[tuple[str, str]] = []

    for kw in keywords:
        kw = kw.strip().lower()
        if not kw:
            continue
        hits = [r for r in rows if kw in r[0]]
        by_cat: dict[str, int] = {}
        for _, cat, _, _ in hits:
            by_cat[cat] = by_cat.get(cat, 0) + 1
        moved = {c: n for c, n in by_cat.items() if c != "other"}

        print(f"\n'{kw}' — {len(hits)} matches  {by_cat or '{}'}")
        if not hits:
            verdicts.append((kw, "NO MATCH — typo, or the row is not in the DB yet"))
            continue

        shown: set[str] = set()
        for desc, cat, amt, _ in hits:
            key = desc[:46]
            if key in shown:
                continue
            shown.add(key)
            print(f"    [{cat:<12}] {desc[:70]}")
            if len(shown) >= 6:
                break

        if moved:
            verdicts.append((kw, f"MOVES {sum(moved.values())} row(s) out of {sorted(moved)}"))
        else:
            verdicts.append((kw, "safe — only touches 'other'"))

    print("\n" + "=" * 60)
    for kw, v in verdicts:
        print(f"  {kw:<28} {v}")
    print(
        "\nReview every 'MOVES' line by hand. Moving a merchant out of the\n"
        "'compra con tarjeta' catch-all in `equal` is usually a correction;\n"
        "an incidental substring hit is not."
    )


def compensation(conn: sqlite3.Connection, months: int) -> None:
    """Last *months* rows of the monthly compensation report, plus the running balance."""
    import pandas as pd

    from src.config_manager import load_config, partner_names
    from src.reports import monthly_compensation_report

    cfg = load_config()
    df = pd.read_sql("SELECT * FROM transactions WHERE account_type = 'joint'", conn)
    rep = monthly_compensation_report(df, cfg)
    if rep.empty:
        print("No joint transactions yet.")
        return

    cols = [
        "month", "kids_comp", "food_comp", "health_comp", "house_comp",
        "contributions_comp", "total_comp", "total_comp_cumulative",
    ]
    fmt = {c: (lambda v: f"{v:,.2f}") for c in cols[1:]}
    pd.set_option("display.width", 250)
    print(rep.tail(months)[cols].to_string(index=False, formatters=fmt))
    print("(equal_comp omitted — always 0.00, a 50/50 category cannot produce a gap)")

    balance = float(rep["total_comp_cumulative"].iloc[-1])
    pa, pb = partner_names(cfg)
    owes = f"{pa} owes {pb}" if balance > 0 else f"{pb} owes {pa}"
    print(f"\ncumulative balance: {balance:,.2f}  ->  {owes} {abs(balance):,.2f} EUR")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--summary", action="store_true", help="category totals + unclassified share")
    ap.add_argument("--unclassified", action="store_true", help="list 'other' outflows by description")
    ap.add_argument("--check", metavar="KW,KW", help="comma-separated candidate keywords to vet")
    ap.add_argument("--compensation", action="store_true", help="monthly compensation table + balance")
    ap.add_argument("--account", default="joint", choices=("joint", "personal"))
    ap.add_argument("--since", metavar="YYYY-MM-DD", help="only rows after this date")
    ap.add_argument("--limit", type=int, default=60)
    ap.add_argument("--months", type=int, default=6, help="rows of history for --compensation")
    args = ap.parse_args()

    if not (args.summary or args.unclassified or args.check or args.compensation):
        ap.print_help()
        return 1

    db = default_db_path()
    if not db.is_file():
        print(f"No database at {db} — run an import first.", file=sys.stderr)
        return 1

    conn = connect(db)
    try:
        if args.summary:
            summary(conn, args.account, args.since)
        if args.unclassified:
            if args.summary:
                print()
            unclassified(conn, args.account, args.since, args.limit)
        if args.check:
            check(conn, args.check.split(","))
        if args.compensation:
            if args.summary or args.unclassified or args.check:
                print()
            compensation(conn, args.months)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
