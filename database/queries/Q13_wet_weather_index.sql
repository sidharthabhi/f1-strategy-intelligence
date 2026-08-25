-- ============================================================================
-- Q13 — Best wet-weather performance index per driver
-- ============================================================================
-- Wet races are rare (~5-8% of dataset). For each driver:
--   - count wet/mixed races they entered
--   - their avg position gain in those races
--   - compared to their dry-race avg position gain
-- The "wet bonus" = avg gain in wet - avg gain in dry. Higher = thrives in rain.
-- ============================================================================
WITH race_weather AS (
    SELECT
        l.race_id,
        SUM(CASE WHEN l.compound IN ('INTERMEDIATE','WET') THEN 1 ELSE 0 END) * 1.0
          / NULLIF(COUNT(*),0) AS wet_share
    FROM   laps l WHERE l.session_type = 'R' GROUP BY l.race_id
),
race_classified AS (
    SELECT race_id, CASE WHEN wet_share >= 0.05 THEN 'wet' ELSE 'dry' END AS condition
    FROM   race_weather
),
driver_gains AS (
    SELECT
        d.code      AS driver,
        rc.condition,
        (rr.grid_position - rr.final_position) AS gain
    FROM   race_results rr
    JOIN   drivers d        ON rr.driver_id = d.driver_id
    JOIN   races   r        ON rr.race_id   = r.race_id AND r.year = d.season
    JOIN   race_classified rc ON rr.race_id = rc.race_id
    WHERE  rr.grid_position  IS NOT NULL AND rr.grid_position > 0
      AND  rr.final_position IS NOT NULL AND rr.final_position > 0
      AND  rr.finish_status IN ('Finished','+1 Lap','+2 Laps','+3 Laps')
),
agg AS (
    SELECT
        driver,
        SUM(CASE WHEN condition='wet' THEN 1 ELSE 0 END) AS wet_races,
        AVG(CASE WHEN condition='wet' THEN gain END)     AS avg_wet_gain,
        AVG(CASE WHEN condition='dry' THEN gain END)     AS avg_dry_gain
    FROM   driver_gains GROUP BY driver
)
SELECT
    driver,
    wet_races,
    ROUND(avg_wet_gain, 2)                AS avg_wet_gain,
    ROUND(avg_dry_gain, 2)                AS avg_dry_gain,
    ROUND(avg_wet_gain - avg_dry_gain, 2) AS wet_bonus
FROM   agg
WHERE  wet_races >= 3
ORDER  BY wet_bonus DESC;
