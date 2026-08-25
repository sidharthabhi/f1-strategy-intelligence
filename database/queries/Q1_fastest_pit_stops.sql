-- ============================================================================
-- Q1 — Which team has the fastest avg pit stop?
-- ============================================================================
-- Returns one row per team-season with their avg "normal" pit stop duration.
-- Filters: only Ergast-enriched stops (duration NOT NULL), only normal stops
-- (no drive-throughs, double-stacks, or no-tire-change stops).
--
-- IMPORTANT: this measures total pit-lane time (in-lap + stationary + out-lap),
-- not just the tire-change duration. ~21s avg = ~3s tire change + ~18s pit lane.
-- The relative ranking is meaningful; the absolute number is "pit-lane lap time
-- delta", not "tire change time".
-- ============================================================================
SELECT
    t.constructor_name                AS team,
    t.season                          AS season,
    ROUND(AVG(p.stop_duration_sec), 3) AS avg_stop_sec,
    COUNT(*)                          AS n_stops,
    ROUND(MIN(p.stop_duration_sec), 3) AS fastest_stop_sec
FROM   pit_stops p
JOIN   drivers d ON p.driver_id = d.driver_id
JOIN   teams   t ON d.team_id   = t.team_id
WHERE  p.stop_duration_sec IS NOT NULL
  AND  p.stop_duration_sec BETWEEN 1.8 AND 60
  AND  p.stop_type = 'normal'
GROUP  BY t.constructor_name, t.season
HAVING n_stops >= 10
ORDER  BY avg_stop_sec ASC;
