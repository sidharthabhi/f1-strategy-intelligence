"""
Build the driver_fingerprints rollup table.

For each (driver, season) we compute 6 dimensions, each scaled 0-100:

  1. RACE_PACE         — avg race pace vs season median (lower raw = higher score)
  2. CONSISTENCY       — stint-normalised consistency (lower raw = higher score)
  3. QUALI_PACE        — avg quali pace gap to teammate (lower raw = higher score)
  4. RACECRAFT         — avg position gain (grid → finish), positive raw = higher score
  5. TIRE_MANAGEMENT   — degradation slope on a driver's MEDIUM stints
                         (lower slope = higher score)
  6. WET_PERFORMANCE   — avg position gain in wet/mixed races (raw → score)

The radar chart on the Power BI Driver DNA page (Page 3) reads from this table.

Outputs to a new physical table `driver_fingerprints` so PBI can hit it directly
without recomputing. Re-run after every fresh ingest.

Run:
    python -m data.ingestion.build_driver_fingerprints
"""
from __future__ import annotations

import math

from .config import setup_logging
from .db import connect

log = setup_logging("driver_fingerprints")


def init_table(conn) -> None:
    conn.execute("DROP TABLE IF EXISTS driver_fingerprints")
    conn.execute("""
        CREATE TABLE driver_fingerprints (
            fingerprint_id  INTEGER PRIMARY KEY AUTOINCREMENT,
            driver_id       INTEGER NOT NULL,
            driver_code     TEXT NOT NULL,
            season          INTEGER NOT NULL,
            constructor_name TEXT,
            raw_race_pace_sec     REAL,
            raw_consistency_sec   REAL,
            raw_quali_gap_sec     REAL,
            raw_avg_pos_gain      REAL,
            raw_tire_deg_slope    REAL,
            raw_wet_pos_gain      REAL,
            score_race_pace       REAL,
            score_consistency     REAL,
            score_quali_pace      REAL,
            score_racecraft       REAL,
            score_tire_mgmt       REAL,
            score_wet_perf        REAL,
            score_overall         REAL,
            races_counted         INTEGER,
            UNIQUE (driver_id, season),
            FOREIGN KEY (driver_id) REFERENCES drivers(driver_id)
        )
    """)
    conn.execute("CREATE INDEX idx_fp_driver_season ON driver_fingerprints (driver_code, season)")


def _scale_inverse(raw_values, target):
    cleaned = [v for v in raw_values if v is not None and not (isinstance(v, float) and math.isnan(v))]
    if not cleaned or target is None or (isinstance(target, float) and math.isnan(target)):
        return None
    lo, hi = min(cleaned), max(cleaned)
    if hi - lo < 1e-9:
        return 50.0
    return round(100.0 * (hi - target) / (hi - lo), 2)


def _scale_direct(raw_values, target):
    cleaned = [v for v in raw_values if v is not None and not (isinstance(v, float) and math.isnan(v))]
    if not cleaned or target is None or (isinstance(target, float) and math.isnan(target)):
        return None
    lo, hi = min(cleaned), max(cleaned)
    if hi - lo < 1e-9:
        return 50.0
    return round(100.0 * (target - lo) / (hi - lo), 2)


def compute_metrics(conn):
    race_pace = conn.execute("""
        SELECT cl.driver_id, cl.driver_code, cl.year AS season,
               cl.constructor_name,
               AVG(cl.lap_time_sec) AS avg_pace,
               COUNT(DISTINCT cl.race_id) AS races
        FROM   v_clean_laps cl
        GROUP  BY cl.driver_id, cl.driver_code, cl.year, cl.constructor_name
        HAVING races >= 8
    """).fetchall()

    consistency = conn.execute("""
        WITH stint_stats AS (
            SELECT cl.driver_id, cl.race_id, cl.year, cl.stint,
                   COUNT(*) AS n,
                   SQRT(MAX(0,
                       AVG(cl.lap_time_sec*cl.lap_time_sec)
                     - AVG(cl.lap_time_sec)*AVG(cl.lap_time_sec)
                   )) AS sd
            FROM v_clean_laps cl
            GROUP BY cl.driver_id, cl.race_id, cl.year, cl.stint
            HAVING n >= 5
        )
        SELECT driver_id, year AS season, AVG(sd) AS avg_stint_sd
        FROM   stint_stats GROUP BY driver_id, year
    """).fetchall()

    quali = conn.execute("""
        WITH driver_race_pace AS (
            SELECT cl.year, cl.race_id, cl.constructor_name, cl.driver_id, cl.driver_code,
                   AVG(cl.lap_time_sec) AS d_avg, MIN(cl.lap_time_sec) AS d_best
            FROM v_clean_laps cl GROUP BY cl.year, cl.race_id, cl.constructor_name,
                                          cl.driver_id, cl.driver_code
            HAVING COUNT(*) >= 10
        ),
        team_best AS (
            SELECT year, race_id, constructor_name, MIN(d_best) AS team_best_lap
            FROM driver_race_pace GROUP BY year, race_id, constructor_name
            HAVING COUNT(DISTINCT driver_id) = 2
        )
        SELECT drp.driver_id, drp.year AS season,
               AVG(drp.d_avg - tb.team_best_lap) AS avg_gap_to_team_best
        FROM driver_race_pace drp
        JOIN team_best tb
             ON drp.year = tb.year AND drp.race_id = tb.race_id
            AND drp.constructor_name = tb.constructor_name
        GROUP BY drp.driver_id, drp.year
    """).fetchall()

    racecraft = conn.execute("""
        SELECT d.driver_id, d.season,
               AVG(rr.grid_position - rr.final_position) AS avg_gain
        FROM   race_results rr
        JOIN   drivers d ON rr.driver_id = d.driver_id
        JOIN   races   r ON rr.race_id   = r.race_id AND r.year = d.season
        WHERE  rr.grid_position  IS NOT NULL AND rr.grid_position > 0
          AND  rr.final_position IS NOT NULL AND rr.final_position > 0
          AND  rr.finish_status IN ('Finished','+1 Lap','+2 Laps','+3 Laps','+4 Laps')
        GROUP  BY d.driver_id, d.season
    """).fetchall()

    tire = conn.execute("""
        WITH stint_laps AS (
            SELECT cn.driver_id, cn.year AS season, cn.tyre_life, cn.lap_time_sec
            FROM   v_compound_normalised cn
            WHERE  cn.compound_norm = 'MEDIUM' AND cn.tyre_life BETWEEN 3 AND 25
        )
        SELECT driver_id, season,
               COUNT(*) AS n,
               SUM(tyre_life)                AS sx,
               SUM(lap_time_sec)             AS sy,
               SUM(tyre_life * lap_time_sec) AS sxy,
               SUM(tyre_life * tyre_life)    AS sxx
        FROM   stint_laps GROUP BY driver_id, season HAVING n >= 50
    """).fetchall()

    wet = conn.execute("""
        WITH race_weather AS (
            SELECT race_id,
                   SUM(CASE WHEN compound IN ('INTERMEDIATE','WET') THEN 1 ELSE 0 END)*1.0
                     / NULLIF(COUNT(*), 0) AS wet_share
            FROM   laps WHERE session_type = 'R' GROUP BY race_id
        )
        SELECT d.driver_id, d.season,
               AVG(rr.grid_position - rr.final_position) AS avg_wet_gain,
               COUNT(*) AS wet_races
        FROM   race_results rr
        JOIN   drivers d ON rr.driver_id = d.driver_id
        JOIN   races   r ON rr.race_id   = r.race_id AND r.year = d.season
        JOIN   race_weather rw ON rr.race_id = rw.race_id
        WHERE  rw.wet_share >= 0.05
          AND  rr.grid_position  IS NOT NULL AND rr.grid_position > 0
          AND  rr.final_position IS NOT NULL AND rr.final_position > 0
          AND  rr.finish_status IN ('Finished','+1 Lap','+2 Laps','+3 Laps')
        GROUP  BY d.driver_id, d.season
        HAVING wet_races >= 2
    """).fetchall()

    cons_lookup  = {(r["driver_id"], r["season"]): r["avg_stint_sd"]   for r in consistency}
    quali_lookup = {(r["driver_id"], r["season"]): r["avg_gap_to_team_best"] for r in quali}
    rc_lookup    = {(r["driver_id"], r["season"]): r["avg_gain"]      for r in racecraft}
    tire_lookup  = {}
    for r in tire:
        denom = r["n"] * r["sxx"] - r["sx"] * r["sx"]
        if denom and denom != 0:
            slope = (r["n"] * r["sxy"] - r["sx"] * r["sy"]) / denom
            tire_lookup[(r["driver_id"], r["season"])] = slope
    wet_lookup   = {(r["driver_id"], r["season"]): r["avg_wet_gain"]   for r in wet}

    fingerprints = []
    for r in race_pace:
        key = (r["driver_id"], r["season"])
        fingerprints.append({
            "driver_id": r["driver_id"],
            "driver_code": r["driver_code"],
            "season": r["season"],
            "constructor_name": r["constructor_name"],
            "races_counted": r["races"],
            "raw_race_pace_sec":   r["avg_pace"],
            "raw_consistency_sec": cons_lookup.get(key),
            "raw_quali_gap_sec":   quali_lookup.get(key),
            "raw_avg_pos_gain":    rc_lookup.get(key),
            "raw_tire_deg_slope":  tire_lookup.get(key),
            "raw_wet_pos_gain":    wet_lookup.get(key),
        })
    return fingerprints


def scale_per_season(rows):
    by_season = {}
    for r in rows:
        by_season.setdefault(r["season"], []).append(r)

    for season, season_rows in by_season.items():
        race_paces    = [r["raw_race_pace_sec"]   for r in season_rows]
        consistencies = [r["raw_consistency_sec"] for r in season_rows]
        quali_gaps    = [r["raw_quali_gap_sec"]   for r in season_rows]
        pos_gains     = [r["raw_avg_pos_gain"]    for r in season_rows]
        tire_slopes   = [r["raw_tire_deg_slope"]  for r in season_rows]
        wet_gains     = [r["raw_wet_pos_gain"]    for r in season_rows]

        for r in season_rows:
            r["score_race_pace"]   = _scale_inverse(race_paces,    r["raw_race_pace_sec"])
            r["score_consistency"] = _scale_inverse(consistencies, r["raw_consistency_sec"])
            r["score_quali_pace"]  = _scale_inverse(quali_gaps,    r["raw_quali_gap_sec"])
            r["score_racecraft"]   = _scale_direct( pos_gains,     r["raw_avg_pos_gain"])
            r["score_tire_mgmt"]   = _scale_inverse(tire_slopes,   r["raw_tire_deg_slope"])
            r["score_wet_perf"]    = _scale_direct( wet_gains,     r["raw_wet_pos_gain"])

            scores = [r[k] for k in ("score_race_pace","score_consistency","score_quali_pace",
                                      "score_racecraft","score_tire_mgmt","score_wet_perf")
                      if r[k] is not None]
            r["score_overall"] = round(sum(scores) / len(scores), 2) if scores else None


def write_table(conn, rows):
    cols = ["driver_id", "driver_code", "season", "constructor_name",
            "raw_race_pace_sec", "raw_consistency_sec", "raw_quali_gap_sec",
            "raw_avg_pos_gain", "raw_tire_deg_slope", "raw_wet_pos_gain",
            "score_race_pace", "score_consistency", "score_quali_pace",
            "score_racecraft", "score_tire_mgmt", "score_wet_perf",
            "score_overall", "races_counted"]
    placeholders = ",".join("?" * len(cols))
    rows_to_insert = [tuple(r.get(c) for c in cols) for r in rows]
    conn.executemany(
        f"INSERT INTO driver_fingerprints ({','.join(cols)}) VALUES ({placeholders})",
        rows_to_insert,
    )
    return len(rows_to_insert)


def run():
    with connect() as conn:
        init_table(conn)
        rows = compute_metrics(conn)
        log.info("Computed metrics for %d (driver, season) combos", len(rows))
        scale_per_season(rows)
        n = write_table(conn, rows)
        log.info("Wrote %d fingerprint rows to driver_fingerprints", n)

        for yr in (2023, 2024):
            log.info("--- Top 5 by overall score, %s ---", yr)
            for r in conn.execute("""
                SELECT driver_code, ROUND(score_overall, 1) AS overall,
                       ROUND(score_race_pace,1) AS pace,
                       ROUND(score_consistency,1) AS cons,
                       ROUND(score_racecraft,1) AS rc,
                       ROUND(score_tire_mgmt,1) AS tire
                FROM   driver_fingerprints
                WHERE  season = ? ORDER BY score_overall DESC LIMIT 5
            """, (yr,)).fetchall():
                log.info("  %s overall=%s pace=%s cons=%s rc=%s tire=%s",
                         r["driver_code"], r["overall"], r["pace"], r["cons"],
                         r["rc"], r["tire"])


if __name__ == "__main__":
    run()
