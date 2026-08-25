"""
Export dashboard data → embedded JSON in single-file dashboard.

The race replay page can browse ANY race in the dataset; lap data is included
for every race in compact form to keep the file under ~3 MB.

Run:
    python -m data.ingestion.export_dashboard_data
"""
from __future__ import annotations

import json
from pathlib import Path

from .config import setup_logging
from .db import connect

log = setup_logging("export_dashboard")

OUTPUT_DIR = Path(__file__).resolve().parents[2] / "dashboard"


def fetch_all(conn, sql: str, params: tuple = ()) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def build_payload(conn) -> dict:
    log.info("Building dashboard payload...")

    headline = fetch_all(conn, """
        SELECT
          (SELECT COUNT(DISTINCT year) FROM races) AS seasons,
          (SELECT COUNT(*) FROM races) AS races,
          (SELECT COUNT(*) FROM circuits) AS circuits,
          (SELECT COUNT(DISTINCT code) FROM drivers) AS unique_drivers,
          (SELECT COUNT(*) FROM laps) AS total_laps,
          (SELECT COUNT(*) FROM laps WHERE is_valid_lap=1 AND session_type='R') AS valid_race_laps,
          (SELECT COUNT(*) FROM pit_stops) AS total_pit_stops
    """)[0]

    season_summary = fetch_all(conn, """
        WITH champ AS (
          SELECT r.year, d.code AS champion,
                 SUM(rr.points_scored) AS pts,
                 RANK() OVER (PARTITION BY r.year ORDER BY SUM(rr.points_scored) DESC) AS rk
          FROM race_results rr
          JOIN drivers d ON rr.driver_id = d.driver_id
          JOIN races r ON rr.race_id = r.race_id AND r.year = d.season
          GROUP BY r.year, d.code
        ),
        team_champ AS (
          SELECT r.year, t.constructor_name AS team,
                 SUM(rr.points_scored) AS pts,
                 RANK() OVER (PARTITION BY r.year ORDER BY SUM(rr.points_scored) DESC) AS rk
          FROM race_results rr
          JOIN drivers d ON rr.driver_id = d.driver_id
          JOIN teams t ON d.team_id = t.team_id
          JOIN races r ON rr.race_id = r.race_id AND r.year = d.season
          GROUP BY r.year, t.constructor_name
        )
        SELECT c.year,
               c.champion AS driver_champion, c.pts AS driver_points,
               tc.team AS team_champion, tc.pts AS team_points,
               (SELECT COUNT(*) FROM races WHERE year = c.year) AS races,
               (SELECT COUNT(DISTINCT circuit_id) FROM races WHERE year = c.year) AS circuits
        FROM champ c
        JOIN team_champ tc ON c.year = tc.year AND tc.rk = 1
        WHERE c.rk = 1 ORDER BY c.year
    """)

    driver_standings = fetch_all(conn, """
        SELECT r.year AS season, d.code AS driver, t.constructor_name AS team,
               SUM(rr.points_scored) AS points,
               SUM(CASE WHEN rr.final_position = 1 THEN 1 ELSE 0 END) AS wins,
               SUM(CASE WHEN rr.final_position <= 3 THEN 1 ELSE 0 END) AS podiums,
               SUM(CASE WHEN rr.grid_position = 1 THEN 1 ELSE 0 END) AS poles
        FROM race_results rr
        JOIN drivers d ON rr.driver_id = d.driver_id
        JOIN teams t ON d.team_id = t.team_id
        JOIN races r ON rr.race_id = r.race_id AND r.year = d.season
        GROUP BY r.year, d.code, t.constructor_name
        ORDER BY r.year, points DESC
    """)

    constructor_standings = fetch_all(conn, """
        SELECT r.year AS season, t.constructor_name AS team,
               SUM(rr.points_scored) AS points,
               SUM(CASE WHEN rr.final_position = 1 THEN 1 ELSE 0 END) AS wins,
               SUM(CASE WHEN rr.final_position <= 3 THEN 1 ELSE 0 END) AS podiums
        FROM race_results rr
        JOIN drivers d ON rr.driver_id = d.driver_id
        JOIN teams t ON d.team_id = t.team_id
        JOIN races r ON rr.race_id = r.race_id AND r.year = d.season
        GROUP BY r.year, t.constructor_name
        ORDER BY r.year, points DESC
    """)

    championship_evo = fetch_all(conn, """
        WITH per_race AS (
          SELECT r.year, r.round, t.constructor_name AS team,
                 SUM(rr.points_scored) AS race_pts
          FROM race_results rr
          JOIN drivers d ON rr.driver_id = d.driver_id
          JOIN teams t ON d.team_id = t.team_id
          JOIN races r ON rr.race_id = r.race_id AND r.year = d.season
          GROUP BY r.year, r.round, t.constructor_name
        )
        SELECT year, round, team,
               SUM(race_pts) OVER (PARTITION BY year, team ORDER BY round
                 ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cum_pts
        FROM per_race
        ORDER BY year, round, cum_pts DESC
    """)

    fingerprints = fetch_all(conn, """
        SELECT driver_code, season, constructor_name,
               score_race_pace, score_consistency, score_quali_pace,
               score_racecraft, score_tire_mgmt, score_wet_perf, score_overall,
               races_counted
        FROM driver_fingerprints
        ORDER BY season, score_overall DESC
    """)

    consistency = fetch_all(conn, """
        WITH stint_stats AS (
            SELECT cl.driver_id, cl.race_id, cl.year, cl.driver_code,
                   cl.constructor_name, cl.stint,
                   COUNT(*) AS n,
                   SQRT(MAX(0,
                       AVG(cl.lap_time_sec*cl.lap_time_sec)
                     - AVG(cl.lap_time_sec)*AVG(cl.lap_time_sec)
                   )) AS sd
            FROM v_clean_laps cl
            GROUP BY cl.driver_id, cl.race_id, cl.year, cl.driver_code,
                     cl.constructor_name, cl.stint
            HAVING n >= 5
        )
        SELECT driver_code AS driver, year AS season, constructor_name AS team,
               ROUND(AVG(sd), 3) AS score,
               COUNT(DISTINCT race_id) AS races
        FROM stint_stats
        GROUP BY driver_code, year, constructor_name HAVING races >= 10
        ORDER BY year, score ASC
    """)

    reliability = fetch_all(conn, """
        WITH classified AS (
          SELECT t.constructor_name AS team, d.season AS season,
                 CASE WHEN rr.finish_status IN ('Finished','+1 Lap','+2 Laps','+3 Laps','+4 Laps','+5 Laps')
                   THEN 0 ELSE 1 END AS is_dnf
          FROM race_results rr
          JOIN drivers d ON rr.driver_id = d.driver_id
          JOIN teams t ON d.team_id = t.team_id
          JOIN races r ON rr.race_id = r.race_id AND r.year = d.season
          WHERE rr.finish_status IS NOT NULL
        )
        SELECT team, season, COUNT(*) AS entries, SUM(is_dnf) AS dnfs,
               ROUND(100.0 * SUM(is_dnf) / COUNT(*), 2) AS dnf_rate
        FROM classified GROUP BY team, season HAVING entries >= 10
        ORDER BY season, dnf_rate ASC
    """)

    circuits = fetch_all(conn, """
        SELECT c.circuit_id, c.name, c.country, c.length_km, c.corners,
               c.drs_zones, c.surface_type, c.first_gp_year,
               COUNT(r.race_id) AS races_in_data
        FROM circuits c LEFT JOIN races r ON c.circuit_id = r.circuit_id
        GROUP BY c.circuit_id ORDER BY c.name
    """)

    tire_deg = fetch_all(conn, """
        WITH stint_laps AS (
            SELECT circuit_id, circuit_name, tyre_life, lap_time_sec
            FROM v_compound_normalised
            WHERE compound_norm = 'MEDIUM' AND tyre_life BETWEEN 3 AND 25
        ),
        sums AS (
            SELECT circuit_id, circuit_name, COUNT(*) AS n,
                   SUM(tyre_life) AS sx, SUM(lap_time_sec) AS sy,
                   SUM(tyre_life * lap_time_sec) AS sxy,
                   SUM(tyre_life * tyre_life) AS sxx
            FROM stint_laps GROUP BY circuit_id, circuit_name HAVING n >= 200
        )
        SELECT circuit_name,
               ROUND((n*sxy - sx*sy)*1.0 / NULLIF(n*sxx - sx*sx, 0), 4) AS deg_per_lap
        FROM sums ORDER BY deg_per_lap DESC
    """)

    # Race catalog — every race in the dataset for the replay picker
    race_catalog = fetch_all(conn, """
        SELECT r.race_id, r.year, r.round, r.event_name, r.total_laps,
               c.name AS circuit_name, r.date
        FROM   races r
        JOIN   circuits c ON r.circuit_id = c.circuit_id
        WHERE  EXISTS (
          SELECT 1 FROM laps l
          WHERE l.race_id = r.race_id AND l.session_type = 'R'
            AND l.position IS NOT NULL
        )
        ORDER BY r.year DESC, r.round
    """)

    # Driver-team mapping per season — for colour-coding in the replay page
    driver_team_map = fetch_all(conn, """
        SELECT d.season, d.code AS driver, t.constructor_name AS team
        FROM   drivers d JOIN teams t ON d.team_id = t.team_id
    """)

    # Compact lap-position matrix: race_id → driver → [position per lap]
    # Stored as tuples of (race_id, driver_code, list-of-positions-by-lap)
    # which compresses ~10x compared to row-per-lap.
    log.info("Building compact race lap matrix...")
    rows = conn.execute("""
        SELECT l.race_id, l.lap_number, d.code AS driver, l.position
        FROM   laps l
        JOIN   drivers d ON l.driver_id = d.driver_id
        JOIN   races   r ON l.race_id   = r.race_id AND r.year = d.season
        WHERE  l.session_type = 'R'
          AND  l.position IS NOT NULL
        ORDER  BY l.race_id, d.code, l.lap_number
    """).fetchall()

    # Build sparse matrix race_id → driver → {lap: pos}
    race_positions: dict[int, dict[str, list]] = {}
    for r in rows:
        rid = r["race_id"]
        drv = r["driver"]
        race_positions.setdefault(rid, {}).setdefault(drv, []).append(
            [r["lap_number"], r["position"]]
        )
    # Convert to plain list of {race_id, driver, laps} for JSON
    race_positions_compact = []
    for rid, drivers in race_positions.items():
        for drv, laps in drivers.items():
            race_positions_compact.append({"race_id": rid, "driver": drv, "laps": laps})

    log.info("  race_positions_compact: %d rows", len(race_positions_compact))

    pole_to_win = fetch_all(conn, """
        WITH pole_wins AS (
          SELECT c.name AS circuit, rr.race_id,
                 SUM(CASE WHEN rr.grid_position=1 AND rr.final_position=1 THEN 1 ELSE 0 END) AS pole_won,
                 SUM(CASE WHEN rr.grid_position=1 THEN 1 ELSE 0 END) AS had_pole
          FROM race_results rr JOIN races r ON rr.race_id=r.race_id
          JOIN circuits c ON r.circuit_id=c.circuit_id
          GROUP BY c.name, rr.race_id
        )
        SELECT circuit, COUNT(*) AS races,
               ROUND(100.0*SUM(pole_won)/COUNT(*), 1) AS conversion_pct
        FROM pole_wins GROUP BY circuit HAVING races >= 3
        ORDER BY conversion_pct DESC
    """)

    overtaking = fetch_all(conn, """
        WITH cr AS (
          SELECT r.race_id, r.circuit_id,
                 ABS(rr.grid_position - rr.final_position) AS chg
          FROM race_results rr JOIN races r ON rr.race_id=r.race_id
          WHERE rr.grid_position > 0 AND rr.final_position > 0
            AND rr.finish_status IN ('Finished','+1 Lap','+2 Laps','+3 Laps','+4 Laps')
        ),
        rs AS (SELECT race_id, circuit_id, SUM(chg) AS swing FROM cr GROUP BY race_id, circuit_id)
        SELECT c.name AS circuit, c.drs_zones, COUNT(*) AS races,
               ROUND(AVG(rs.swing), 1) AS swing
        FROM rs JOIN circuits c ON rs.circuit_id=c.circuit_id
        GROUP BY c.name, c.drs_zones HAVING races >= 3
        ORDER BY swing DESC
    """)

    h2h = fetch_all(conn, """
        SELECT season, constructor_name, driver_a_code, driver_b_code,
               races_compared, quali_a_ahead, quali_b_ahead,
               race_a_ahead, race_b_ahead, avg_race_pace_gap_a_minus_b,
               dnfs_a, dnfs_b
        FROM h2h_summary ORDER BY season, constructor_name
    """)

    payload = {
        "headline": headline,
        "season_summary": season_summary,
        "driver_standings": driver_standings,
        "constructor_standings": constructor_standings,
        "championship_evo": championship_evo,
        "fingerprints": fingerprints,
        "consistency": consistency,
        "reliability": reliability,
        "circuits": circuits,
        "tire_deg": tire_deg,
        "race_catalog": race_catalog,
        "driver_team_map": driver_team_map,
        "race_positions": race_positions_compact,
        "h2h": h2h,
        "pole_to_win": pole_to_win,
        "overtaking": overtaking,
    }

    log.info("Payload sizes:")
    for k, v in payload.items():
        size = len(v) if isinstance(v, list) else 1
        log.info("  %s: %d", k, size)

    return payload


def write_html(payload: dict) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / "dashboard_data.json"
    json_path.write_text(json.dumps(payload, default=float), encoding="utf-8")
    log.info("Wrote %s (%d KB)", json_path, json_path.stat().st_size // 1024)

    template_path = OUTPUT_DIR / "template.html"
    if not template_path.exists():
        log.warning("template.html missing — copy from /dashboard/template.html and rerun")
        return json_path

    template = template_path.read_text(encoding="utf-8")
    inlined = template.replace(
        "/* DATA_PLACEHOLDER */",
        f"const DATA = {json.dumps(payload, default=float)};"
    )
    out_path = OUTPUT_DIR / "index.html"
    out_path.write_text(inlined, encoding="utf-8")
    log.info("Wrote %s (%d KB)", out_path, out_path.stat().st_size // 1024)
    return out_path


def run() -> None:
    with connect() as conn:
        payload = build_payload(conn)
    write_html(payload)


if __name__ == "__main__":
    run()
