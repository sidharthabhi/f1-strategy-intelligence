-- ============================================================================
-- Q3 — Which driver has the highest quali-to-race position gain ratio?
-- ============================================================================
-- For each race a driver finishes (excludes DNFs), gain = grid_position - final_position.
-- Positive = gained, negative = lost. Returns drivers ranked by avg gain.
--
-- Excludes:
--   - DNFs (final_position is NULL or finish_status indicates Accident/Engine/etc.)
--   - Races where grid_position is 0 or NULL (pit lane start, DSQ, etc.)
-- ============================================================================
SELECT
    d.code                           AS driver,
    d.season                         AS season,
    COUNT(*)                         AS finishes,
    ROUND(AVG(rr.grid_position - rr.final_position), 2) AS avg_position_gain,
    SUM(CASE WHEN rr.grid_position - rr.final_position > 0 THEN 1 ELSE 0 END) AS races_gained,
    SUM(CASE WHEN rr.grid_position - rr.final_position < 0 THEN 1 ELSE 0 END) AS races_lost,
    ROUND(AVG(rr.grid_position), 2)  AS avg_grid,
    ROUND(AVG(rr.final_position), 2) AS avg_finish
FROM   race_results rr
JOIN   drivers d ON rr.driver_id = d.driver_id
JOIN   races   r ON rr.race_id   = r.race_id AND r.year = d.season
WHERE  rr.grid_position IS NOT NULL  AND rr.grid_position > 0
  AND  rr.final_position IS NOT NULL AND rr.final_position > 0
  AND  rr.finish_status IN ('Finished','+1 Lap','+2 Laps','+3 Laps','+4 Laps')
GROUP  BY d.code, d.season
HAVING finishes >= 8
ORDER  BY avg_position_gain DESC;
