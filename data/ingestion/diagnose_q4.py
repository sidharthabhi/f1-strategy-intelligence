"""
Diagnose Q4 ranking anomalies.

Expected in top-3 consistency but missing:
  - 2020: HAM (champion)
  - 2022: VER (champion), LEC
  - 2021: VER (should be #1 or #2)

Hypotheses to check:
  A. HAM/VER/LEC have multiple `drivers` rows per season (team change or
     substitute entry), inflating the row count and breaking the join.
  B. Their races pass the >=10 valid laps bar but somehow fail the >=3 races bar.
  C. Their consistency scores are actually worse than GAS/OCO/RIC (true signal).
"""
from __future__ import annotations

from .db import connect


def run() -> None:
    drivers_to_check = [
        ("HAM", 2020), ("HAM", 2022),
        ("VER", 2020), ("VER", 2022),
        ("LEC", 2022), ("PER", 2022),
        ("GAS", 2020), ("RIC", 2022),  # the surprises for comparison
    ]

    with connect() as conn:
        print("\n=== A. drivers rows per (code, season) ===")
        for code, season in drivers_to_check:
            rows = conn.execute(
                "SELECT driver_id, team_id, full_name FROM drivers"
                " WHERE code = ? AND season = ?", (code, season)
            ).fetchall()
            print(f"  {code} {season}: {len(rows)} row(s)")
            for r in rows:
                print(f"    driver_id={r['driver_id']}, team_id={r['team_id']}, "
                      f"name={r['full_name']}")

        print("\n=== B. races with >=10 valid laps (R) per (code, season) ===")
        for code, season in drivers_to_check:
            row = conn.execute("""
                SELECT COUNT(DISTINCT l.race_id) AS n_races,
                       COUNT(*) AS n_valid_laps
                FROM   laps l
                JOIN   drivers d ON l.driver_id = d.driver_id
                JOIN   races   r ON l.race_id   = r.race_id
                WHERE  d.code = ? AND r.year = ?
                  AND  l.is_valid_lap = 1 AND l.session_type = 'R'
                  AND  l.track_status = 'Green'
                  AND  l.compound NOT IN ('INTERMEDIATE','WET')
            """, (code, season)).fetchone()
            print(f"  {code} {season}: races={row['n_races']}, valid_laps={row['n_valid_laps']}")

        print("\n=== C. Actual Q4 output for these drivers (if they appear at all) ===")
        full_q4 = conn.execute("""
            WITH valid_laps AS (
                SELECT l.driver_id, l.race_id, l.lap_time_sec, r.year
                FROM   laps l JOIN races r ON l.race_id = r.race_id
                WHERE  l.is_valid_lap=1 AND l.session_type='R'
                  AND  l.track_status='Green' AND l.compound NOT IN ('INTERMEDIATE','WET')
            ),
            race_stats AS (
                SELECT driver_id, race_id, year,
                  SQRT(MAX(0, AVG(lap_time_sec*lap_time_sec)
                             - AVG(lap_time_sec)*AVG(lap_time_sec))) AS sd
                FROM valid_laps GROUP BY driver_id, race_id, year
                HAVING COUNT(*) >= 10
            )
            SELECT d.code, rs.year,
                   ROUND(AVG(rs.sd), 3) AS score,
                   COUNT(DISTINCT rs.race_id) AS races
            FROM race_stats rs JOIN drivers d ON rs.driver_id = d.driver_id
                                             AND d.season = rs.year
            GROUP BY d.code, rs.year
            ORDER BY rs.year, score ASC
        """).fetchall()

        # Filter to just the seasons of interest
        for target_year in (2020, 2021, 2022):
            print(f"\n  --- Top 10 for {target_year} ---")
            year_rows = [r for r in full_q4 if r["year"] == target_year][:10]
            for i, r in enumerate(year_rows, 1):
                print(f"  #{i:<3} {r['code']:<5} score={r['score']:<7} races={r['races']}")
            # Also look for missing drivers
            codes = {r["code"] for r in full_q4 if r["year"] == target_year}
            for target in ("HAM", "VER", "LEC", "PER"):
                if target not in codes:
                    print(f"    ! {target} NOT IN Q4 OUTPUT for {target_year}")


if __name__ == "__main__":
    run()
