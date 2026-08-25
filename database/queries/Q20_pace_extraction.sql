-- ============================================================================
-- Q20 — Which driver extracts the most pace from their car?
-- ============================================================================
-- The "car ceiling" is approximated by the BEST clean lap any driver in that
-- team set in that race. A driver's pace extraction = how close they got to
-- that ceiling on average.
--
-- Score = (driver_avg_lap - teammate_best_lap) — lower = closer to ceiling.
-- Negative is impossible (a driver can't beat their own teammate's best).
-- Zero would mean every lap matches the teammate's qualifying-style fastest lap.
-- ============================================================================
WITH driver_race_pace AS (
    SELECT
        cl.year,
        cl.race_id,
        cl.constructor_name,
        cl.driver_id,
        cl.driver_code,
        AVG(cl.lap_time_sec) AS driver_avg,
        MIN(cl.lap_time_sec) AS driver_best
    FROM   v_clean_laps cl
    GROUP  BY cl.year, cl.race_id, cl.constructor_name, cl.driver_id, cl.driver_code
    HAVING COUNT(*) >= 10
),
team_best_per_race AS (
    SELECT
        year, race_id, constructor_name,
        MIN(driver_best) AS team_best_lap
    FROM   driver_race_pace
    GROUP  BY year, race_id, constructor_name
    HAVING COUNT(DISTINCT driver_id) = 2     -- both teammates ran the race
)
SELECT
    drp.driver_code AS driver,
    drp.year        AS season,
    ROUND(AVG(drp.driver_avg - tb.team_best_lap), 3) AS avg_gap_to_team_best,
    COUNT(DISTINCT drp.race_id)                       AS races_compared
FROM   driver_race_pace drp
JOIN   team_best_per_race tb
       ON drp.year = tb.year AND drp.race_id = tb.race_id
      AND drp.constructor_name = tb.constructor_name
GROUP  BY drp.driver_code, drp.year
HAVING races_compared >= 10
ORDER  BY drp.year, avg_gap_to_team_best ASC;
