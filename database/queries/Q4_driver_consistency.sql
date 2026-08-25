-- ============================================================================
-- Q4 — Driver Lap Time Consistency Score
-- ============================================================================
-- Measures how repeatably a driver hits the same lap time on clean green-flag laps.
-- Lower = more consistent.
--
-- Formula: STDDEV(lap_time_sec) WHERE is_valid_lap=1
-- SQLite has no STDDEV — we compute it via:
--   stddev = sqrt( E[X^2] - E[X]^2 )
--
-- Output: one row per driver per season with consistency score + race pace.
-- ============================================================================

WITH valid_laps AS (
    SELECT driver_id, race_id, lap_time_sec
    FROM   laps
    WHERE  is_valid_lap   = 1
      AND  track_status   = 'Green'
      AND  session_type   = 'R'
      AND  lap_time_sec   IS NOT NULL
      AND  compound NOT IN ('INTERMEDIATE', 'WET')
),
race_stats AS (
    SELECT
        driver_id,
        race_id,
        AVG(lap_time_sec)                                              AS avg_lap,
        COUNT(*)                                                        AS lap_count,
        -- SQLite STDDEV approximation: sqrt(E[X^2] - E[X]^2)
        CASE
            WHEN AVG(lap_time_sec * lap_time_sec)
                 - AVG(lap_time_sec) * AVG(lap_time_sec) > 0
            THEN SQRT(  AVG(lap_time_sec * lap_time_sec)
                      - AVG(lap_time_sec) * AVG(lap_time_sec) )
            ELSE 0
        END                                                             AS stddev_lap
    FROM   valid_laps
    GROUP  BY driver_id, race_id
    HAVING COUNT(*) >= 10                  -- need enough clean laps for meaningful stddev
)
SELECT
    d.code                              AS driver,
    r.year                              AS season,
    ROUND(AVG(rs.stddev_lap), 3)        AS consistency_score,
    ROUND(AVG(rs.avg_lap),    3)        AS avg_race_pace_sec,
    COUNT(DISTINCT rs.race_id)          AS races_counted
FROM   race_stats rs
JOIN   drivers d ON rs.driver_id = d.driver_id
JOIN   races   r ON rs.race_id   = r.race_id
GROUP  BY d.code, r.year
HAVING COUNT(DISTINCT rs.race_id) >= 10    -- at least 10 races so substitutes can't top the chart
ORDER  BY consistency_score ASC;
