"""Run the configured bank imports from the command line.

Equivalent to the Streamlit **Import data → Import all files** button, for use in a
runbook or by an agent that is not driving the UI. Importing is idempotent: rows are
deduplicated by hash, so re-running with the same files adds nothing.

    & .\\.venv\\Scripts\\python.exe -m scripts.import_bank_files
    & .\\.venv\\Scripts\\python.exe -m scripts.import_bank_files --dry-run
"""

from __future__ import annotations

import argparse
import sys

from src.config_manager import load_config, resolve_source_file
from src.ingest import import_all_configured, load_and_parse_source


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="parse and classify in memory, report counts, write nothing",
    )
    args = ap.parse_args()

    cfg = load_config()
    sources = (cfg.get("bank_imports") or {}).get("sources") or []
    base = (cfg.get("bank_imports") or {}).get("base_directory") or "<project root>"
    print(f"reading from {base}\n")

    # Resolve every source first: a missing file should stop the run before any
    # partial import, not surface halfway through.
    resolved = {}
    missing = False
    for spec in sources:
        try:
            path = resolve_source_file(cfg, spec["file"])
        except FileNotFoundError as e:
            print(f"  {spec['id']:<20} MISSING — {e}")
            missing = True
            continue
        resolved[spec["id"]] = path
        print(f"  {spec['id']:<20} {path.name}")
    if missing:
        print("\nAborted: resolve the missing export(s) first.", file=sys.stderr)
        return 1

    if args.dry_run:
        print("\n--dry-run: parsing only, nothing written")
        for spec in sources:
            rows = load_and_parse_source(cfg, spec)
            dates = sorted(r["date"] for r in rows)
            cats: dict[str, int] = {}
            for r in rows:
                cats[r["category"]] = cats.get(r["category"], 0) + 1
            span = f"{dates[0]}..{dates[-1]}" if dates else "empty"
            print(f"  {spec['id']:<20} {len(rows):>5} rows  {span}  {dict(sorted(cats.items()))}")
        return 0

    res = import_all_configured(cfg=cfg)
    print(f"\nadded {res['added']} · skipped {res['skipped']} (already present)")
    for d in res["sources"]:
        print(f"  {d['source_id']:<20} added {d['added']:>5}  skipped {d['skipped']:>5}  ({d['file']})")
    if res["added"] == 0:
        print("\nNothing new — these exports were already imported. That is the expected"
              "\nresult of re-running an import, not a failure.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
