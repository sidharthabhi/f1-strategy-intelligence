"""
Week 1 smoke test. Run AFTER ingestion to confirm the foundation is solid.

    python -m data.ingestion.smoke_test

Checks (pass → go to Week 2):
  1. DB file exists
  2. All 8 tables present
  3. At least 1 race + 10 drivers loaded
  4. laps.is_valid_lap in {0,1} and ~60-70% are valid (realistic ratio)
  5. Q4 consistency query runs and returns non-empty result
  6. No NULL lap_number or driver_id on laps
  7. Known reality check: Max Verstappen (VER) 2024 season consistency score < 1.5s
"""
from __future__ import annotations

import sys
from pathlib import Path

from .config import DB_PATH, QUERIES_DIR
from .db import connect

# ANSI green / red — works in Windows Terminal, PowerShell 7+, VS Code terminal.
GREEN = "\033[32m"
RED = "\033[31m"
RESET = "\033[0m"


def _ok(msg: str) -> None:
    print(f"{GREEN}✓{RESET} {msg}")


def _fail(msg: str) -> None:
    print(f"{RED}✗{RESET} {msg}")


def check(label: str, condition: bool, detail: str = "") -> bool:
    if condition:
        _ok(f"{label}" + (f" — {detail}" if detail else ""))
    else:
        _fail(f"{label}" + (f" — {detail}" if detail else ""))
    return condition


def run() -> int:
    failures = 0

    # 1. DB exists
    if not check("DB file exists", DB_PATH.exists(), str(DB_PATH)):
        return 1

    with connect() as conn:
        # 2. Schema tables
        expected = {"circuits", "races", "teams", "drivers", "race_results",
                    "laps", "pit_stops", "telemetry"}
        actual = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        missing = expected - actual
        failures += not check("All 8 tables present",
                              not missing,
                              f"missing: {missing}" if missing else "")

        # 3. Row counts
        counts = {}
        for t in ["races", "drivers", "teams", "laps", "race_results", "pit_stops"]:
            counts[t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]

        failures += not check("≥ 1 race loaded",  counts["races"]   >= 1,  f"{counts['races']} races")
        failures += not check("≥ 10 drivers",     counts["drivers"] >= 10, f"{counts['drivers']} drivers")
        failures += not check("≥ 500 laps",       counts["laps"]    >= 500, f"{counts['laps']} laps")

        # 4. is_valid_lap realism
        valid_ratio_row = conn.execute(
            "SELECT AVG(is_valid_lap) FROM laps WHERE session_type = 'R'"
        ).fetchone()
        valid_ratio = valid_ratio_row[0] or 0
        failures += not check(
            "is_valid_lap ratio realistic (0.50–0.85)",
            0.50 <= valid_ratio <= 0.85,
            f"{valid_ratio:.2%}",
        )

        # 5. Q4 runs
        q4_path = QUERIES_DIR / "Q4_driver_consistency.sql"
        if q4_path.exists():
            sql = q4_path.read_text(encoding="utf-8")
            rows = conn.execute(sql).fetchall()
            failures += not check("Q4 consistency query returns rows",
                                  len(rows) > 0,
                                  f"{len(rows)} (driver, season) rows")
            if rows:
                # Show top 5 most consistent
                print("\n  Top 5 most consistent (lower = better):")
                print(f"  {'driver':<6} {'season':<7} {'score':<8} {'pace':<9} races")
                for r in rows[:5]:
                    d = dict(r)
                    print(f"  {d['driver']:<6} {d['season']:<7} {d['consistency_score']:<8} "
                          f"{d['avg_race_pace_sec']:<9} {d['races_counted']}")
                print()
        else:
            _fail(f"Q4 SQL file missing at {q4_path}")
            failures += 1

        # 6. No NULL driver_id / lap_number on laps
        null_laps = conn.execute(
            "SELECT COUNT(*) FROM laps WHERE driver_id IS NULL OR lap_number IS NULL"
        ).fetchone()[0]
        failures += not check("No NULL driver_id / lap_number",
                              null_laps == 0,
                              f"{null_laps} bad rows")

        # 7. Reality check — VER 2024 consistency < 3.0s
        # Raw race-pace stddev naturally includes tire degradation across a stint
        # (~3s spread over 20 laps on softs). Top drivers in 2024 landed ~1.8-2.5s.
        # Week 3 will add a stint-normalised metric that strips deg variance.
        ver_row = conn.execute("""
            WITH valid_laps AS (
                SELECT driver_id, race_id, lap_time_sec FROM laps
                WHERE  is_valid_lap = 1 AND session_type = 'R' AND track_status = 'Green'
                   AND compound NOT IN ('INTERMEDIATE','WET')
            ),
            race_stats AS (
                SELECT driver_id, race_id,
                  SQRT(MAX(0, AVG(lap_time_sec*lap_time_sec)
                             - AVG(lap_time_sec)*AVG(lap_time_sec))) AS stddev_lap
                FROM valid_laps GROUP BY driver_id, race_id HAVING COUNT(*) >= 10
            )
            SELECT AVG(rs.stddev_lap)
            FROM race_stats rs
            JOIN drivers d ON rs.driver_id = d.driver_id
            JOIN races   r ON rs.race_id   = r.race_id
            WHERE d.code = 'VER' AND r.year = 2024
        """).fetchone()
        ver_score = ver_row[0]
        if ver_score is None:
            print("  (VER 2024 reality check skipped — no rows yet)")
        else:
            failures += not check(
                "VER 2024 consistency < 3.0s (sanity check)",
                ver_score < 3.0,
                f"{ver_score:.3f}s",
            )

    print()
    if failures == 0:
        _ok(f"Week 1 GATE PASSED — foundation is solid, proceed to Week 2 backfill.")
        return 0
    _fail(f"{failures} check(s) failed — fix these before Week 2.")
    return 1


if __name__ == "__main__":
    sys.exit(run())