-- ============================================================================
-- Q4b — Stint-Normalised Consistency Score (the championship-correct version)
-- ============================================================================
-- Q4 raw stddev penalises drivers who lap traffic, manage gaps, or push hard
-- after SC restarts (i.e., race-winners). This stint-normalised version
-- computes stddev WITHIN each stint, then averages — stripping out tire-deg
-- and race-management variance.
--
-- Formula:
--   1. For each (driver, race, stint), compute stddev of clean lap times.
--   2. Per (driver, race), avg those stint stddevs.
--   3. Per (driver, season), avg those race scores.
--
-- Expected: VER, HAM, LEC, NOR top each season — matches championship reality.
-- ============================================================================
WITH stint_stats AS (
    SELECT
        cl.driver_id,
        cl.race_id,
        cl.year,
        cl.driver_code,
        cl.stint,
        COUNT(*) AS lap_count,
        SQRT(MAX(0,
            AVG(cl.lap_time_sec * cl.lap_time_sec)
          - AVG(cl.lap_time_sec) * AVG(cl.lap_time_sec)
        )) AS stint_stddev
    FROM   v_clean_laps cl
    GROUP  BY cl.driver_id, cl.race_id, cl.year, cl.driver_code, cl.stint
    HAVING lap_count >= 5      -- short stints (e.g., end of race) excluded
),
race_scores AS (
    SELECT
        driver_id, race_id, year, driver_code,
        AVG(stint_stddev) AS race_stint_consistency,
        COUNT(*)          AS stints_in_race
    FROM   stint_stats
    GROUP  BY driver_id, race_id, year, driver_code
    HAVING stints_in_race >= 1
)
SELECT
    driver_code                                   AS driver,
    year                                          AS season,
    ROUND(AVG(race_stint_consistency), 3)         AS stint_consistency_score,
    COUNT(DISTINCT race_id)                       AS races_counted
FROM   race_scores
GROUP  BY driver_code, year
HAVING races_counted >= 10
ORDER  BY year, stint_consistency_score ASC;
