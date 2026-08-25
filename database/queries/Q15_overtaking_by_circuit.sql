-- ============================================================================
-- Q15 — Which circuits favor overtaking? Does DRS zone count explain it?
-- ============================================================================
-- "Overtaking volume" approximation: total absolute grid-to-finish position
-- change across all drivers in a race, summed and averaged over races at the
-- circuit. This avoids lap-by-lap noise from pit windows and SC periods.
--
-- A high-overtaking circuit produces big position swings (driver started P15,
-- finished P3). A low-overtaking circuit produces small ones (started P3,
-- finished P3 — Monaco's pattern).
--
-- Caveats:
--   - DNFs are excluded (final_position NULL or non-finishing status)
--   - Pit-lane starts (grid_position 0) are excluded
-- ============================================================================
WITH classified_results AS (
    SELECT
        r.race_id,
        r.circuit_id,
        ABS(rr.grid_position - rr.final_position) AS position_change
    FROM   race_results rr
    JOIN   races r ON rr.race_id = r.race_id
    WHERE  rr.grid_position  IS NOT NULL AND rr.grid_position > 0
      AND  rr.final_position IS NOT NULL AND rr.final_position > 0
      AND  rr.finish_status IN ('Finished','+1 Lap','+2 Laps','+3 Laps','+4 Laps')
),
race_swings AS (
    SELECT race_id, circuit_id, SUM(position_change) AS total_swing
    FROM   classified_results GROUP BY race_id, circuit_id
)
SELECT
    c.name        AS circuit,
    c.drs_zones,
    COUNT(*)      AS races,
    ROUND(AVG(rs.total_swing), 1) AS avg_position_swings
FROM   race_swings rs
JOIN   circuits c ON rs.circuit_id = c.circuit_id
GROUP  BY c.circuit_id, c.name, c.drs_zones
HAVING races >= 3
ORDER  BY avg_position_swings DESC;
