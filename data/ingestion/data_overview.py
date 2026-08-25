"""
Data overview — a wide cross-check of every table.

Prints stats you can sanity-check against F1 knowledge:
  - Champions per season
  - Wins per driver across the dataset
  - Pole positions per driver
  - Most-used compound on dry vs mixed races
  - Famous moments: 2021 Abu Dhabi, 2022 Monaco rain, 2018 German GP rain
  - Per-team race wins, podiums
  - Fastest race lap per circuit (across all seasons)

Run:
    python -m data.ingestion.data_overview
"""
from __future__ import annotations

from .db import connect

CYAN  = "\033[36m"
YEL   = "\033[33m"
GREEN = "\033[32m"
RESET = "\033[0m"


def _h(title: str) -> None:
    print()
    print(f"{CYAN}{'=' * 72}{RESET}")
    print(f"{CYAN}{title}{RESET}")
    print(f"{CYAN}{'=' * 72}{RESET}")


def _sub(title: str) -> None:
    print(f"\n{YEL}--- {title} ---{RESET}")


def overview_dataset(conn) -> None:
    _h("Dataset shape")
    stats = {
        "seasons":      conn.execute("SELECT COUNT(DISTINCT year) FROM races").fetchone()[0],
        "races":        conn.execute("SELECT COUNT(*) FROM races").fetchone()[0],
        "circuits":     conn.execute("SELECT COUNT(*) FROM circuits").fetchone()[0],
        "drivers (total rows)":  conn.execute("SELECT COUNT(*) FROM drivers").fetchone()[0],
        "unique driver codes":   conn.execute("SELECT COUNT(DISTINCT code) FROM drivers").fetchone()[0],
        "teams (total rows)":    conn.execute("SELECT COUNT(*) FROM teams").fetchone()[0],
        "laps (all sessions)":   conn.execute("SELECT COUNT(*) FROM laps").fetchone()[0],
        "race laps":     conn.execute("SELECT COUNT(*) FROM laps WHERE session_type='R'").fetchone()[0],
        "valid race laps": conn.execute("SELECT COUNT(*) FROM laps WHERE session_type='R' AND is_valid_lap=1").fetchone()[0],
        "pit stops":     conn.execute("SELECT COUNT(*) FROM pit_stops").fetchone()[0],
        "race results":  conn.execute("SELECT COUNT(*) FROM race_results").fetchone()[0],
    }
    for k, v in stats.items():
        print(f"  {k:<28} {v:>10,}")


def overview_champions(conn) -> None:
    _h("Champions check — driver with most points per season")
    print(f"  {'season':<8}{'champion':<10}{'points':>10}{'wins':>8}{'podiums':>10}")
    for r in conn.execute("""
        WITH season_points AS (
          SELECT r.year, d.code, d.full_name,
                 SUM(rr.points_scored) AS points,
                 SUM(CASE WHEN rr.final_position = 1 THEN 1 ELSE 0 END) AS wins,
                 SUM(CASE WHEN rr.final_position <= 3 THEN 1 ELSE 0 END) AS podiums,
                 RANK() OVER (PARTITION BY r.year ORDER BY SUM(rr.points_scored) DESC) AS rk
          FROM race_results rr
          JOIN drivers d ON rr.driver_id = d.driver_id
          JOIN races   r ON rr.race_id   = r.race_id
          WHERE d.season = r.year
          GROUP BY r.year, d.code, d.full_name
        )
        SELECT year, code, full_name, points, wins, podiums
        FROM   season_points WHERE rk = 1 ORDER BY year
    """).fetchall():
        print(f"  {r['year']:<8}{r['code']:<10}{r['points']:>10.1f}{r['wins']:>8}{r['podiums']:>10}")
    print()
    print(f"  {YEL}Expected:{RESET} 2018 HAM, 2019 HAM, 2020 HAM, 2021 VER, "
          "2022 VER, 2023 VER, 2024 VER")


def overview_wins(conn) -> None:
    _h("Race winners — top 15 drivers by total wins (2018-2024)")
    print(f"  {'driver':<10}{'wins':>8}{'podiums':>10}{'first':>10}{'last':>10}")
    for r in conn.execute("""
        SELECT d.code,
               SUM(CASE WHEN rr.final_position = 1 THEN 1 ELSE 0 END) AS wins,
               SUM(CASE WHEN rr.final_position <= 3 THEN 1 ELSE 0 END) AS podiums,
               MIN(CASE WHEN rr.final_position = 1 THEN r.year END) AS first_win,
               MAX(CASE WHEN rr.final_position = 1 THEN r.year END) AS last_win
        FROM race_results rr
        JOIN drivers d ON rr.driver_id = d.driver_id
        JOIN races   r ON rr.race_id   = r.race_id
        WHERE d.season = r.year
        GROUP BY d.code
        HAVING wins > 0
        ORDER BY wins DESC LIMIT 15
    """).fetchall():
        print(f"  {r['code']:<10}{r['wins']:>8}{r['podiums']:>10}"
              f"{r['first_win'] or '-':>10}{r['last_win'] or '-':>10}")


def overview_pole_positions(conn) -> None:
    _h("Pole positions — top 10 drivers (grid_position = 1)")
    print(f"  {'driver':<10}{'poles':>8}")
    for r in conn.execute("""
        SELECT d.code, COUNT(*) AS poles
        FROM   race_results rr
        JOIN   drivers d ON rr.driver_id = d.driver_id
        JOIN   races   r ON rr.race_id   = r.race_id
        WHERE  d.season = r.year AND rr.grid_position = 1
        GROUP  BY d.code ORDER BY poles DESC LIMIT 10
    """).fetchall():
        print(f"  {r['code']:<10}{r['poles']:>8}")


def overview_constructor_wins(conn) -> None:
    _h("Constructor wins — top 10 teams")
    print(f"  {'team':<25}{'wins':>8}{'podiums':>10}{'1-2 finishes':>14}")
    for r in conn.execute("""
        WITH per_race AS (
          SELECT t.constructor_name, rr.race_id,
                 SUM(CASE WHEN rr.final_position = 1 THEN 1 ELSE 0 END) AS race_wins,
                 SUM(CASE WHEN rr.final_position <= 2 THEN 1 ELSE 0 END) AS race_top2
          FROM race_results rr
          JOIN drivers d ON rr.driver_id = d.driver_id
          JOIN teams   t ON d.team_id    = t.team_id
          GROUP BY t.constructor_name, rr.race_id
        )
        SELECT t.constructor_name AS team,
               SUM(CASE WHEN rr.final_position = 1 THEN 1 ELSE 0 END) AS wins,
               SUM(CASE WHEN rr.final_position <= 3 THEN 1 ELSE 0 END) AS podiums,
               (SELECT COUNT(*) FROM per_race p
                WHERE p.constructor_name = t.constructor_name AND p.race_top2 = 2) AS one_twos
        FROM   race_results rr
        JOIN   drivers d ON rr.driver_id = d.driver_id
        JOIN   teams   t ON d.team_id    = t.team_id
        GROUP  BY t.constructor_name
        ORDER  BY wins DESC LIMIT 10
    """).fetchall():
        print(f"  {r['team']:<25}{r['wins']:>8}{r['podiums']:>10}{r['one_twos']:>14}")


def overview_circuit_records(conn) -> None:
    _h("Fastest valid race lap per circuit (across full dataset)")
    print(f"  {'circuit':<28}{'driver':<8}{'time':>10}{'season':>8}")
    for r in conn.execute("""
        WITH ranked AS (
          SELECT c.name AS circuit, d.code, l.lap_time_sec, r.year,
                 ROW_NUMBER() OVER (PARTITION BY c.circuit_id
                                    ORDER BY l.lap_time_sec ASC) AS rk
          FROM laps l
          JOIN races   r ON l.race_id   = r.race_id
          JOIN circuits c ON r.circuit_id = c.circuit_id
          JOIN drivers d ON l.driver_id  = d.driver_id
          WHERE l.is_valid_lap = 1 AND l.session_type = 'R'
            AND l.lap_time_sec IS NOT NULL
        )
        SELECT circuit, code, lap_time_sec, year FROM ranked WHERE rk = 1
        ORDER BY circuit
    """).fetchall():
        time_str = f"{r['lap_time_sec']:.3f}" if r['lap_time_sec'] is not None else "    -"
        code = r['code'] or "-"
        year = r['year'] if r['year'] is not None else "-"
        print(f"  {r['circuit']:<28}{code:<8}{time_str:>10}{year:>8}")


def overview_pit_stops(conn) -> None:
    _h("Pit stop performance — fastest avg by team (Ergast-enriched only)")
    print(f"  {'team':<25}{'season':>8}{'avg dur':>10}{'n stops':>10}")
    for r in conn.execute("""
        SELECT t.constructor_name AS team, t.season,
               ROUND(AVG(p.stop_duration_sec), 2) AS avg_dur,
               COUNT(*) AS n
        FROM pit_stops p
        JOIN drivers d ON p.driver_id = d.driver_id
        JOIN teams   t ON d.team_id   = t.team_id
        WHERE p.stop_duration_sec IS NOT NULL
          AND p.stop_duration_sec BETWEEN 1.8 AND 60
          AND p.stop_type = 'normal'
        GROUP BY t.constructor_name, t.season
        HAVING n >= 10
        ORDER BY avg_dur ASC LIMIT 15
    """).fetchall():
        print(f"  {r['team']:<25}{r['season']:>8}{r['avg_dur']:>10}{r['n']:>10}")


def overview_compound_usage(conn) -> None:
    _h("Tire compound usage — race laps")
    print(f"  {'compound':<15}{'laps':>10}{'% of total':>12}")
    total = conn.execute(
        "SELECT COUNT(*) FROM laps WHERE session_type='R' AND compound IS NOT NULL"
    ).fetchone()[0]
    for r in conn.execute("""
        SELECT compound, COUNT(*) AS n FROM laps
        WHERE session_type='R' AND compound IS NOT NULL
        GROUP BY compound ORDER BY n DESC
    """).fetchall():
        pct = 100 * r["n"] / total if total else 0
        print(f"  {r['compound']:<15}{r['n']:>10}{pct:>11.1f}%")


def overview_famous_races(conn) -> None:
    _h("Famous moments — sanity-check by knowledge")

    # 2021 Abu Dhabi: VER won the title from HAM via SC restart drama
    _sub("2021 Abu Dhabi — VER won championship from HAM (last lap)")
    for r in conn.execute("""
        SELECT d.code, rr.grid_position, rr.final_position, rr.points_scored
        FROM   race_results rr
        JOIN   drivers d ON rr.driver_id = d.driver_id
        JOIN   races   r ON rr.race_id   = r.race_id
        WHERE  d.season = r.year AND r.year = 2021
          AND  r.event_name LIKE '%Abu Dhabi%'
          AND  d.code IN ('VER', 'HAM')
        ORDER  BY rr.final_position
    """).fetchall():
        print(f"  {r['code']:<5} grid={r['grid_position']}  finish={r['final_position']}  "
              f"points={r['points_scored']}")

    # 2018 German GP: HAM won from P14 in mixed conditions, VET crashed leading
    _sub("2018 German GP — HAM won from P14, VET crashed while leading")
    for r in conn.execute("""
        SELECT d.code, rr.grid_position, rr.final_position, rr.finish_status
        FROM   race_results rr
        JOIN   drivers d ON rr.driver_id = d.driver_id
        JOIN   races   r ON rr.race_id   = r.race_id
        WHERE  d.season = r.year AND r.year = 2018 AND r.event_name LIKE '%German%'
          AND  d.code IN ('HAM', 'VET', 'BOT', 'RAI')
        ORDER  BY rr.final_position
    """).fetchall():
        print(f"  {r['code']:<5} grid={r['grid_position']}  finish={r['final_position']}  "
              f"status={r['finish_status']}")

    # 2021 Belgian GP: 1 lap behind safety car, half points
    _sub("2021 Belgian GP — 1 timed lap behind safety car (rain)")
    row = conn.execute("""
        SELECT total_laps, sc_periods,
               (SELECT MAX(lap_number) FROM laps l WHERE l.race_id = r.race_id
                AND l.session_type='R') AS max_recorded_lap
        FROM races r WHERE year = 2021 AND event_name LIKE '%Belgian%'
    """).fetchone()
    if row:
        print(f"  total_laps recorded: {row['total_laps']}, "
              f"max lap_number: {row['max_recorded_lap']}")

    # 2024 Monaco: LEC's first home win
    _sub("2024 Monaco — LEC's first home win")
    for r in conn.execute("""
        SELECT d.code, rr.grid_position, rr.final_position
        FROM   race_results rr
        JOIN   drivers d ON rr.driver_id = d.driver_id
        JOIN   races   r ON rr.race_id   = r.race_id
        WHERE  d.season = r.year AND r.year = 2024 AND r.event_name LIKE '%Monaco%'
          AND  rr.final_position <= 3
        ORDER  BY rr.final_position
    """).fetchall():
        print(f"  P{r['final_position']}: {r['code']} (started P{r['grid_position']})")

    # 2018 Italian GP: HAM passed RAI for the win at Monza
    _sub("2018 Italian GP — HAM beat RAI's Ferrari in front of tifosi")
    for r in conn.execute("""
        SELECT d.code, rr.grid_position, rr.final_position
        FROM   race_results rr
        JOIN   drivers d ON rr.driver_id = d.driver_id
        JOIN   races   r ON rr.race_id   = r.race_id
        WHERE  d.season = r.year AND r.year = 2018 AND r.event_name LIKE '%Italian%'
          AND  rr.final_position <= 3
        ORDER  BY rr.final_position
    """).fetchall():
        print(f"  P{r['final_position']}: {r['code']} (started P{r['grid_position']})")


def overview_seasons_per_team(conn) -> None:
    _h("Constructor presence — seasons each team appeared in our data")
    rows = conn.execute("""
        SELECT constructor_name AS team,
               GROUP_CONCAT(season, ', ') AS seasons,
               COUNT(*) AS n
        FROM   teams
        GROUP  BY constructor_name
        ORDER  BY n DESC, constructor_name
    """).fetchall()
    print(f"  {'team':<28}{'#seasons':>10}  seasons")
    for r in rows:
        print(f"  {r['team']:<28}{r['n']:>10}  {r['seasons']}")


def run() -> None:
    with connect() as conn:
        overview_dataset(conn)
        overview_champions(conn)
        overview_wins(conn)
        overview_pole_positions(conn)
        overview_constructor_wins(conn)
        overview_circuit_records(conn)
        overview_pit_stops(conn)
        overview_compound_usage(conn)
        overview_famous_races(conn)
        overview_seasons_per_team(conn)
    print()


if __name__ == "__main__":
    run()
