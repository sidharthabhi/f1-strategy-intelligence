"""
Build pre-computed rollup tables.

Tables produced:
  - pit_window_model: per-circuit optimal one-stop window (median pit lap
                      across past races, with min/max range). Drives the
                      pit-strategy Gantt chart on Page 2.
  - h2h_summary:     per teammate pairing per season, head-to-head record
                      across qualifying, race finishes, and DNFs. Drives the
                      Page 7 Head-to-Head viz.

Run:
    python -m data.ingestion.build_rollups
"""
from __future__ import annotations

from .config import setup_logging
from .db import connect

log = setup_logging("build_rollups")


def init_pit_window_model(conn) -> None:
    conn.execute("DROP TABLE IF EXISTS pit_window_model")
    conn.execute("""
        CREATE TABLE pit_window_model (
            circuit_id      INTEGER PRIMARY KEY,
            circuit_name    TEXT NOT NULL,
            races_in_sample INTEGER NOT NULL,
            median_one_stop_lap   REAL,
            avg_one_stop_lap      REAL,
            min_one_stop_lap      INTEGER,
            max_one_stop_lap      INTEGER,
            avg_total_laps        REAL,
            FOREIGN KEY (circuit_id) REFERENCES circuits(circuit_id)
        )
    """)


def build_pit_window_model(conn) -> int:
    rows = conn.execute("""
        WITH stop_counts AS (
            SELECT race_id, driver_id, COUNT(*) AS n_stops
            FROM   pit_stops GROUP BY race_id, driver_id HAVING n_stops = 1
        ),
        one_stop_laps AS (
            SELECT p.race_id, p.driver_id, p.lap_number AS stop_lap, r.circuit_id,
                   r.total_laps
            FROM   pit_stops p
            JOIN   stop_counts sc ON p.race_id = sc.race_id AND p.driver_id = sc.driver_id
            JOIN   races r ON p.race_id = r.race_id
        )
        SELECT circuit_id, stop_lap, total_laps FROM one_stop_laps
    """).fetchall()

    by_circuit = {}
    total_laps_by_circuit = {}
    for r in rows:
        by_circuit.setdefault(r["circuit_id"], []).append(r["stop_lap"])
        if r["total_laps"]:
            total_laps_by_circuit.setdefault(r["circuit_id"], []).append(r["total_laps"])

    inserted = 0
    for circuit_id, stops in by_circuit.items():
        if len(stops) < 5:
            continue
        sorted_stops = sorted(stops)
        median = sorted_stops[len(sorted_stops)//2]
        avg = sum(stops) / len(stops)
        avg_total = (sum(total_laps_by_circuit.get(circuit_id, [])) /
                     max(len(total_laps_by_circuit.get(circuit_id, [])), 1)
                     if total_laps_by_circuit.get(circuit_id) else None)

        circuit_name = conn.execute(
            "SELECT name FROM circuits WHERE circuit_id = ?", (circuit_id,)
        ).fetchone()["name"]

        conn.execute("""
            INSERT INTO pit_window_model
              (circuit_id, circuit_name, races_in_sample, median_one_stop_lap,
               avg_one_stop_lap, min_one_stop_lap, max_one_stop_lap, avg_total_laps)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (circuit_id, circuit_name, len(stops), median,
              round(avg, 2), min(stops), max(stops),
              round(avg_total, 2) if avg_total else None))
        inserted += 1
    return inserted


def init_h2h_summary(conn) -> None:
    conn.execute("DROP TABLE IF EXISTS h2h_summary")
    conn.execute("""
        CREATE TABLE h2h_summary (
            h2h_id          INTEGER PRIMARY KEY AUTOINCREMENT,
            season          INTEGER NOT NULL,
            constructor_name TEXT NOT NULL,
            driver_a_code   TEXT NOT NULL,
            driver_b_code   TEXT NOT NULL,
            races_compared           INTEGER,
            quali_a_ahead            INTEGER,
            quali_b_ahead            INTEGER,
            race_a_ahead             INTEGER,
            race_b_ahead             INTEGER,
            avg_quali_gap_a_minus_b  REAL,
            avg_race_pace_gap_a_minus_b REAL,
            dnfs_a   INTEGER,
            dnfs_b   INTEGER,
            UNIQUE (season, constructor_name, driver_a_code, driver_b_code)
        )
    """)


def build_h2h_summary(conn) -> int:
    teams = conn.execute("""
        SELECT d.season, t.constructor_name,
               GROUP_CONCAT(DISTINCT d.code) AS codes
        FROM   drivers d
        JOIN   teams   t ON d.team_id = t.team_id
        GROUP  BY d.season, t.constructor_name
        HAVING COUNT(DISTINCT d.code) = 2
    """).fetchall()

    inserted = 0
    for tm in teams:
        season = tm["season"]
        team_name = tm["constructor_name"]
        codes = sorted(tm["codes"].split(","))
        a_code, b_code = codes[0], codes[1]

        results = conn.execute("""
            SELECT rr.race_id, d.code, rr.grid_position, rr.final_position,
                   rr.finish_status
            FROM   race_results rr
            JOIN   drivers d ON rr.driver_id = d.driver_id
            JOIN   teams   t ON d.team_id    = t.team_id
            JOIN   races   r ON rr.race_id   = r.race_id AND r.year = d.season
            WHERE  d.season = ? AND t.constructor_name = ?
        """, (season, team_name)).fetchall()

        by_race = {}
        for r in results:
            by_race.setdefault(r["race_id"], {})[r["code"]] = r

        races_compared = 0
        quali_a = quali_b = 0
        race_a = race_b = 0
        dnfs_a = dnfs_b = 0
        for race_id, pair in by_race.items():
            a = pair.get(a_code); b = pair.get(b_code)
            if not (a and b):
                continue
            races_compared += 1
            if a["grid_position"] and b["grid_position"]:
                if a["grid_position"] < b["grid_position"]: quali_a += 1
                elif b["grid_position"] < a["grid_position"]: quali_b += 1
            finished = ('Finished','+1 Lap','+2 Laps','+3 Laps','+4 Laps')
            if a["finish_status"] in finished and b["finish_status"] in finished:
                if a["final_position"] is not None and b["final_position"] is not None:
                    if a["final_position"] < b["final_position"]: race_a += 1
                    elif b["final_position"] < a["final_position"]: race_b += 1
            if a["finish_status"] not in finished and a["finish_status"] is not None:
                dnfs_a += 1
            if b["finish_status"] not in finished and b["finish_status"] is not None:
                dnfs_b += 1

        gap_row = conn.execute("""
            WITH driver_pace AS (
                SELECT cl.race_id, cl.driver_code, AVG(cl.lap_time_sec) AS pace
                FROM   v_clean_laps cl
                WHERE  cl.year = ? AND cl.constructor_name = ?
                GROUP  BY cl.race_id, cl.driver_code HAVING COUNT(*) >= 10
            )
            SELECT AVG(a.pace - b.pace) AS gap
            FROM   driver_pace a JOIN driver_pace b ON a.race_id = b.race_id
            WHERE  a.driver_code = ? AND b.driver_code = ?
        """, (season, team_name, a_code, b_code)).fetchone()
        avg_pace_gap = gap_row["gap"]

        conn.execute("""
            INSERT INTO h2h_summary
              (season, constructor_name, driver_a_code, driver_b_code,
               races_compared, quali_a_ahead, quali_b_ahead,
               race_a_ahead, race_b_ahead, avg_quali_gap_a_minus_b,
               avg_race_pace_gap_a_minus_b, dnfs_a, dnfs_b)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)
        """, (season, team_name, a_code, b_code, races_compared,
              quali_a, quali_b, race_a, race_b,
              round(avg_pace_gap, 4) if avg_pace_gap is not None else None,
              dnfs_a, dnfs_b))
        inserted += 1
    return inserted


def run():
    with connect() as conn:
        init_pit_window_model(conn)
        n_pit = build_pit_window_model(conn)
        log.info("pit_window_model: %d circuits", n_pit)

        init_h2h_summary(conn)
        n_h2h = build_h2h_summary(conn)
        log.info("h2h_summary: %d (season, team) pairings", n_h2h)

        log.info("--- Pit window model sample ---")
        for r in conn.execute("""
            SELECT circuit_name, races_in_sample, median_one_stop_lap,
                   min_one_stop_lap, max_one_stop_lap, avg_total_laps
            FROM pit_window_model
            ORDER BY median_one_stop_lap LIMIT 5
        """).fetchall():
            log.info("  %s: median=%s (range %s-%s of %s laps, n=%d)",
                     r["circuit_name"], r["median_one_stop_lap"],
                     r["min_one_stop_lap"], r["max_one_stop_lap"],
                     r["avg_total_laps"], r["races_in_sample"])

        log.info("--- H2H sample (lopsided pairings) ---")
        for r in conn.execute("""
            SELECT season, constructor_name, driver_a_code, driver_b_code,
                   race_a_ahead, race_b_ahead,
                   ROUND(avg_race_pace_gap_a_minus_b, 3) AS pace_gap
            FROM h2h_summary
            WHERE races_compared >= 15
            ORDER BY ABS(race_a_ahead - race_b_ahead) DESC LIMIT 5
        """).fetchall():
            log.info("  %s %s: %s %d-%d %s  (pace_gap A-B = %s)",
                     r["season"], r["constructor_name"],
                     r["driver_a_code"], r["race_a_ahead"], r["race_b_ahead"],
                     r["driver_b_code"], r["pace_gap"])


if __name__ == "__main__":
    run()
