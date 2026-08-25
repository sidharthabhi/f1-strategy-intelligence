"""
Install (or reinstall) every .sql file in database/views into f1_analytics.db.

Order of installation matters because views reference other views:
  v_clean_laps → v_compound_normalised → v_driver_seasons (independent)

Run after any view-file changes:
    python -m data.ingestion.install_views
"""
from __future__ import annotations

from pathlib import Path

from .config import DATABASE_DIR, setup_logging
from .db import connect

log = setup_logging("install_views")

VIEWS_DIR = DATABASE_DIR / "views"

# Explicit order — v_compound_normalised SELECTs from v_clean_laps.
INSTALL_ORDER = [
    "v_clean_laps.sql",
    "v_compound_normalised.sql",
    "v_driver_seasons.sql",
]


def install() -> dict:
    stats = {"installed": 0, "failed": []}
    with connect() as conn:
        for fname in INSTALL_ORDER:
            path = VIEWS_DIR / fname
            if not path.exists():
                log.warning("Missing view file: %s", path)
                stats["failed"].append(fname)
                continue
            sql = path.read_text(encoding="utf-8")
            try:
                conn.executescript(sql)
                stats["installed"] += 1
                log.info("Installed %s", fname)
            except Exception as exc:
                log.error("Failed %s: %s", fname, exc)
                stats["failed"].append(fname)

        # Quick smoke test — each view should be queryable
        for view_name in ("v_clean_laps", "v_compound_normalised", "v_driver_seasons"):
            try:
                row = conn.execute(f"SELECT COUNT(*) FROM {view_name}").fetchone()
                log.info("  %s → %d rows", view_name, row[0])
            except Exception as exc:
                log.error("  %s smoke test failed: %s", view_name, exc)
                stats["failed"].append(view_name)

    return stats


if __name__ == "__main__":
    install()
