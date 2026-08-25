"""
Query runner CLI.

Usage:
    python -m data.ingestion.run_query Q1            # run a single query
    python -m data.ingestion.run_query Q4b
    python -m data.ingestion.run_query --all         # run every Q, summary mode
    python -m data.ingestion.run_query Q1 --limit 5  # limit rows printed
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import QUERIES_DIR, setup_logging
from .db import connect

log = setup_logging("run_query")


def list_queries() -> list[Path]:
    return sorted(QUERIES_DIR.glob("Q*.sql"))


def find_query(qname: str) -> Path | None:
    """Match Q1, Q4b, etc. — case-insensitive prefix match."""
    target = qname.lower()
    for p in list_queries():
        # Q1 should match Q1_xxx but not Q10_xxx
        stem_lower = p.stem.lower()
        prefix = stem_lower.split("_", 1)[0]
        if prefix == target:
            return p
    return None


def _format_rows(rows: list, cols: list[str], limit: int) -> None:
    if not rows:
        print("  (no rows)")
        return
    widths = [max(len(c), max(len(str(r[i])) if r[i] is not None else 4 for r in rows[:limit]))
              for i, c in enumerate(cols)]
    widths = [min(w, 24) for w in widths]  # cap column width
    header = "  ".join(c[:w].ljust(w) for c, w in zip(cols, widths))
    print(f"  {header}")
    print("  " + "  ".join("-" * w for w in widths))
    for r in rows[:limit]:
        row_str = "  ".join(
            (str(v) if v is not None else "—")[:w].ljust(w)
            for v, w in zip(r, widths)
        )
        print(f"  {row_str}")
    if len(rows) > limit:
        print(f"  ... ({len(rows) - limit} more rows)")


def run_query(path: Path, limit: int = 10) -> None:
    print(f"\n{'=' * 72}")
    print(f"  {path.name}")
    print(f"{'=' * 72}")

    sql = path.read_text(encoding="utf-8")
    with connect() as conn:
        cur = conn.execute(sql)
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]

    print(f"  rows: {len(rows)}")
    print()
    _format_rows([tuple(r) for r in rows], cols, limit)


def run_all_summary() -> None:
    """Run every query and print just (name, row count) — quick health check."""
    print(f"\n{'name':<45}{'rows':>10}")
    print("-" * 56)
    with connect() as conn:
        for path in list_queries():
            sql = path.read_text(encoding="utf-8")
            try:
                rows = conn.execute(sql).fetchall()
                print(f"  {path.stem:<43}{len(rows):>10}")
            except Exception as exc:
                print(f"  {path.stem:<43}{'ERROR':>10}  -- {exc}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run any Q-query against f1_analytics.db")
    parser.add_argument("query", nargs="?", help="Query name (e.g., Q1, Q4b, Q15)")
    parser.add_argument("--all", action="store_true", help="Run every Q and show row counts")
    parser.add_argument("--limit", type=int, default=15, help="Max rows to print")
    parser.add_argument("--list", action="store_true", help="List all available queries")
    args = parser.parse_args()

    if args.list:
        for p in list_queries():
            print(p.stem)
        return 0

    if args.all:
        run_all_summary()
        return 0

    if not args.query:
        parser.print_help()
        return 1

    path = find_query(args.query)
    if path is None:
        print(f"Query '{args.query}' not found. Try --list.")
        return 1

    run_query(path, limit=args.limit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
