"""
Data quality audit — post-backfill health check.

Produces a structured report covering:
  1. Row counts per season per table
  2. NULL percentages on critical columns
  3. Valid-lap ratio per season (regression check vs 2024 baseline ~80%)
  4. Pit-stop enrichment coverage (% with Ergast duration)
  5. Circuit metadata coverage
  6. Suspicious outlier detection

Run:
    python -m data.ingestion.quality_audit
    python -m data.ingestion.quality_audit > reports/qa_week2.txt
"""
from __future__ import annotations

from .config import setup_logging
from .db import connect

log = setup_logging("quality_audit")

# ANSI colors
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
RESET = "\033[0m"


def _header(title: str) -> None:
    print()
    print(f"{CYAN}{'=' * 70}{RESET}")
    print(f"{CYAN}{title}{RESET}")
    print(f"{CYAN}{'=' * 70}{RESET}")


def _pct(num: int, denom: int) -> str:
    if denom == 0:
        return "  N/A"
    return f"{100 * num / denom:5.1f}%"


def _badge(ok: bool) -> str:
    return f"{GREEN}✓{RESET}" if ok else f"{RED}✗{RESET}"


def audit_row_counts(conn) -> None:
    _header("1. Row counts by season")
    seasons = [r[0] for r in conn.execute(
        "SELECT DISTINCT year FROM races ORDER BY year"
    ).fetchall()]

    print(f"  {'season':<8}{'races':>8}{'drivers':>10}{'teams':>8}"
          f"{'laps':>10}{'pitstops':>10}{'results':>10}")
    for yr in seasons:
        races    = conn.execute("SELECT COUNT(*) FROM races WHERE year=?", (yr,)).fetchone()[0]
        drivers  = conn.execute("SELECT COUNT(*) FROM drivers WHERE season=?", (yr,)).fetchone()[0]
        teams    = conn.execute("SELECT COUNT(*) FROM teams WHERE season=?", (yr,)).fetchone()[0]
        laps     = conn.execute(
            "SELECT COUNT(*) FROM laps l JOIN races r ON l.race_id=r.race_id"
            " WHERE r.year=?", (yr,)).fetchone()[0]
        pits     = conn.execute(
            "SELECT COUNT(*) FROM pit_stops p JOIN races r ON p.race_id=r.race_id"
            " WHERE r.year=?", (yr,)).fetchone()[0]
        results  = conn.execute(
            "SELECT COUNT(*) FROM race_results rr JOIN races r ON rr.race_id=r.race_id"
            " WHERE r.year=?", (yr,)).fetchone()[0]
        print(f"  {yr:<8}{races:>8}{drivers:>10}{teams:>8}"
              f"{laps:>10}{pits:>10}{results:>10}")


def audit_null_rates(conn) -> None:
    _header("2. NULL rates on critical columns")

    cols_to_check = [
        ("laps", "lap_time_sec"),
        ("laps", "compound"),
        ("laps", "tyre_life"),
        ("laps", "position"),
        ("laps", "sector1_sec"),
        ("pit_stops", "stop_duration_sec"),
        ("pit_stops", "compound_in"),
        ("race_results", "grid_position"),
        ("race_results", "final_position"),
        ("race_results", "finish_status"),
    ]

    print(f"  {'table.column':<32}{'total':>10}{'null':>10}{'null %':>10}")
    for tbl, col in cols_to_check:
        total = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
        nulls = conn.execute(f"SELECT COUNT(*) FROM {tbl} WHERE {col} IS NULL").fetchone()[0]
        pct = _pct(nulls, total)
        ok = (nulls / total < 0.15) if total else True
        badge = _badge(ok)
        print(f"  {tbl}.{col:<23}{total:>10}{nulls:>10}{pct:>10}  {badge}")


def audit_valid_lap_ratio(conn) -> None:
    _header("3. is_valid_lap ratio by season (expected 0.55–0.85)")

    print(f"  {'season':<8}{'race laps':>12}{'valid':>10}{'ratio':>10}{'status':>8}")
    for yr in [r[0] for r in conn.execute(
        "SELECT DISTINCT year FROM races ORDER BY year"
    ).fetchall()]:
        total = conn.execute(
            "SELECT COUNT(*) FROM laps l JOIN races r ON l.race_id=r.race_id"
            " WHERE r.year=? AND l.session_type='R'", (yr,)).fetchone()[0]
        valid = conn.execute(
            "SELECT COUNT(*) FROM laps l JOIN races r ON l.race_id=r.race_id"
            " WHERE r.year=? AND l.session_type='R' AND l.is_valid_lap=1",
            (yr,)).fetchone()[0]
        ratio = (valid / total) if total else 0
        ok = 0.55 <= ratio <= 0.85
        print(f"  {yr:<8}{total:>12}{valid:>10}{ratio:>10.3f}  {_badge(ok):>3}")


def audit_ergast_coverage(conn) -> None:
    _header("4. Ergast pit-stop enrichment coverage")

    print(f"  {'season':<8}{'total stops':>14}{'w/ duration':>14}{'coverage':>12}")
    for yr in [r[0] for r in conn.execute(
        "SELECT DISTINCT year FROM races ORDER BY year"
    ).fetchall()]:
        total = conn.execute(
            "SELECT COUNT(*) FROM pit_stops p JOIN races r ON p.race_id=r.race_id"
            " WHERE r.year=?", (yr,)).fetchone()[0]
        filled = conn.execute(
            "SELECT COUNT(*) FROM pit_stops p JOIN races r ON p.race_id=r.race_id"
            " WHERE r.year=? AND p.stop_duration_sec IS NOT NULL",
            (yr,)).fetchone()[0]
        print(f"  {yr:<8}{total:>14}{filled:>14}{_pct(filled, total):>12}")


def audit_circuit_metadata(conn) -> None:
    _header("5. Circuit metadata coverage")

    rows = conn.execute(
        "SELECT fastf1_key, name, length_km, corners, drs_zones FROM circuits"
        " ORDER BY name"
    ).fetchall()

    filled = sum(1 for r in rows if r["length_km"] is not None)
    total = len(rows)
    print(f"  Circuits with metadata: {filled}/{total}  ({_pct(filled, total)})\n")

    missing = [r for r in rows if r["length_km"] is None]
    if missing:
        print(f"  {RED}Missing metadata:{RESET}")
        for r in missing:
            print(f"    - {r['fastf1_key']} ({r['name']})")


def audit_outliers(conn) -> None:
    _header("6. Outlier detection")

    # Check: any valid lap >200s (post-fix sanity)
    slow = conn.execute(
        "SELECT COUNT(*) FROM laps WHERE is_valid_lap=1 AND lap_time_sec > 200"
    ).fetchone()[0]
    print(f"  Valid laps over 200s: {slow}  {_badge(slow == 0)}")

    # Check: any valid lap <50s
    fast = conn.execute(
        "SELECT COUNT(*) FROM laps WHERE is_valid_lap=1 AND lap_time_sec < 50"
    ).fetchone()[0]
    print(f"  Valid laps under 50s: {fast}  {_badge(fast == 0)}")

    # Check: duplicate (race_id, driver_id, lap_number, session_type) tuples
    dup = conn.execute("""
        SELECT COUNT(*) FROM (
            SELECT race_id, driver_id, lap_number, session_type, COUNT(*) AS n
            FROM laps GROUP BY race_id, driver_id, lap_number, session_type
            HAVING n > 1
        )
    """).fetchone()[0]
    print(f"  Duplicate (race, driver, lap, session) tuples: {dup}  {_badge(dup == 0)}")

    # Check: races with zero valid laps
    empty = conn.execute("""
        SELECT r.year, r.round, r.event_name FROM races r
        LEFT JOIN laps l ON r.race_id = l.race_id AND l.is_valid_lap = 1
                                                  AND l.session_type = 'R'
        GROUP BY r.race_id HAVING COUNT(l.lap_id) = 0
    """).fetchall()
    print(f"  Races with zero valid R laps: {len(empty)}  {_badge(len(empty) == 0)}")
    for r in empty[:5]:
        print(f"    - {r['year']} R{r['round']}: {r['event_name']}")


def audit_q4_cross_season(conn) -> None:
    _header("7. Q4 consistency — cross-season top-3 per year")

    q = """
    WITH valid_laps AS (
        SELECT l.driver_id, l.race_id, l.lap_time_sec, r.year
        FROM laps l JOIN races r ON l.race_id = r.race_id
        WHERE l.is_valid_lap = 1 AND l.session_type = 'R'
          AND l.track_status = 'Green' AND l.compound NOT IN ('INTERMEDIATE','WET')
    ),
    race_stats AS (
        SELECT driver_id, race_id, year,
               SQRT(MAX(0, AVG(lap_time_sec*lap_time_sec)
                          - AVG(lap_time_sec)*AVG(lap_time_sec))) AS sd
        FROM valid_laps GROUP BY driver_id, race_id, year HAVING COUNT(*) >= 10
    ),
    season_scores AS (
        SELECT rs.year, d.code AS driver, ROUND(AVG(rs.sd), 3) AS score,
               COUNT(DISTINCT rs.race_id) AS races
        FROM race_stats rs JOIN drivers d ON rs.driver_id = d.driver_id
                                         AND d.season = rs.year
        GROUP BY rs.year, d.code HAVING races >= 3
    ),
    ranked AS (
        SELECT year, driver, score,
               RANK() OVER (PARTITION BY year ORDER BY score ASC) AS rnk
        FROM season_scores
    )
    SELECT year, driver, score FROM ranked WHERE rnk <= 3 ORDER BY year, rnk
    """
    print(f"  {'season':<8}{'#1':<14}{'#2':<14}{'#3':<14}")
    current_year = None
    top3: list = []
    for r in conn.execute(q).fetchall():
        if r["year"] != current_year:
            if top3:
                row_str = "".join(f"{t:<14}" for t in top3)
                print(f"  {current_year:<8}{row_str}")
            current_year = r["year"]
            top3 = []
        top3.append(f"{r['driver']} ({r['score']})")
    if top3:
        row_str = "".join(f"{t:<14}" for t in top3)
        print(f"  {current_year:<8}{row_str}")

    print()
    print("  Expected champions by season:")
    print("    2018 HAM · 2019 HAM · 2020 HAM · 2021 VER · 2022 VER · 2023 VER · 2024 VER")
    print("  The champion usually appears in the top 3 for consistency too.")


def run() -> None:
    with connect() as conn:
        audit_row_counts(conn)
        audit_null_rates(conn)
        audit_valid_lap_ratio(conn)
        audit_ergast_coverage(conn)
        audit_circuit_metadata(conn)
        audit_outliers(conn)
        audit_q4_cross_season(conn)
    print()


if __name__ == "__main__":
    run()
