"""
Week 1 diagnostic: inspect validity logic.

Run: python -m data.ingestion.diagnose
"""
from .db import connect


def run() -> None:
    with connect() as conn:
        print("\n--- Raw track_status distribution (all race laps) ---")
        for r in conn.execute("""
            SELECT track_status, COUNT(*) AS n,
                   ROUND(AVG(lap_time_sec), 2) AS avg_time,
                   SUM(is_valid_lap) AS valid_count
            FROM   laps
            WHERE  session_type = 'R' AND lap_time_sec IS NOT NULL
            GROUP  BY track_status
            ORDER  BY n DESC
        """).fetchall():
            print(" ", dict(r))

        print("\n--- VER 2024 Bahrain (R1) — first 15 race laps ---")
        for r in conn.execute("""
            SELECT l.lap_number,
                   ROUND(l.lap_time_sec, 2) AS time,
                   l.track_status,
                   l.is_valid_lap,
                   l.is_pit_lap,
                   l.compound
            FROM   laps l
            JOIN   drivers d ON l.driver_id = d.driver_id
            JOIN   races   r ON l.race_id   = r.race_id
            WHERE  d.code = 'VER' AND r.year = 2024 AND r.round = 1
              AND  l.session_type = 'R'
            ORDER  BY l.lap_number
            LIMIT  15
        """).fetchall():
            print(" ", dict(r))

        print("\n--- VER 2024: all 'valid' laps slower than 105s (suspicious) ---")
        for r in conn.execute("""
            SELECT r.event_name,
                   l.lap_number,
                   ROUND(l.lap_time_sec, 2) AS time,
                   l.track_status
            FROM   laps l
            JOIN   drivers d ON l.driver_id = d.driver_id
            JOIN   races   r ON l.race_id   = r.race_id
            WHERE  d.code = 'VER' AND r.year = 2024
              AND  l.session_type = 'R'
              AND  l.is_valid_lap = 1
              AND  l.lap_time_sec > 105
            ORDER  BY l.lap_time_sec DESC
            LIMIT  10
        """).fetchall():
            print(" ", dict(r))

        print("\n--- VER 2024 fastest valid race lap (baseline) ---")
        for r in conn.execute("""
            SELECT r.event_name, ROUND(MIN(l.lap_time_sec), 2) AS fastest
            FROM   laps l
            JOIN   drivers d ON l.driver_id = d.driver_id
            JOIN   races   r ON l.race_id   = r.race_id
            WHERE  d.code = 'VER' AND r.year = 2024
              AND  l.session_type = 'R' AND l.is_valid_lap = 1
            GROUP  BY r.event_name
            ORDER  BY fastest ASC
            LIMIT  3
        """).fetchall():
            print(" ", dict(r))


if __name__ == "__main__":
    run()