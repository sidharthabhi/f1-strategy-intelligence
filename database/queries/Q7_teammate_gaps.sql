-- ============================================================================
-- Q7 — Which teammate pairing had the closest performance gap?
-- ============================================================================
-- For each team-season, find the two drivers and compute the avg lap time gap
-- between them across all races. Lower = closer pairing.
--
-- Method:
--   1. Per (team, season, race), compute each driver's median clean lap time.
--   2. Per race, compute the absolute gap between the team's two drivers.
--   3. Avg those gaps over the season.
--
-- SQLite has no MEDIAN — we approximate with AVG (mean) which is fine here
-- because we already filter to clean valid laps (no outliers).
-- ============================================================================
WITH driver_race_pace AS (
    SELECT
        constructor_name,
        year,
        race_id,
        driver_code,
        AVG(lap_time_sec) AS avg_lap
    FROM   v_clean_laps
    GROUP  BY constructor_name, year, race_id, driver_code
    HAVING COUNT(*) >= 10
),
team_race_pairs AS (
    SELECT
        a.constructor_name,
        a.year,
        a.race_id,
        a.driver_code AS driver_a,
        b.driver_code AS driver_b,
        ABS(a.avg_lap - b.avg_lap) AS race_gap_sec
    FROM   driver_race_pace a
    JOIN   driver_race_pace b
           ON a.constructor_name = b.constructor_name
          AND a.year             = b.year
          AND a.race_id          = b.race_id
          AND a.driver_code      < b.driver_code
)
SELECT
    constructor_name AS team,
    year             AS season,
    driver_a         AS teammate_1,
    driver_b         AS teammate_2,
    ROUND(AVG(race_gap_sec), 3) AS avg_gap_sec,
    COUNT(*)         AS races_compared
FROM   team_race_pairs
GROUP  BY constructor_name, year, driver_a, driver_b
HAVING races_compared >= 8
ORDER  BY avg_gap_sec ASC;
