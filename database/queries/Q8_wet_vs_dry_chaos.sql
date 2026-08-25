-- ============================================================================
-- Q8 — Does rain increase randomness in finishing order?
-- ============================================================================
-- "Randomness" = how much finishing order deviates from grid order.
-- We approximate weather condition per race by checking whether INTERMEDIATE
-- or WET tires were used: if either compound has >5% of total laps in that
-- race, we classify it as a "wet" or "mixed" race.
--
-- Metric: avg(|grid_position - final_position|) per race, then averaged
-- across the wet vs dry buckets.
-- ============================================================================
WITH race_weather AS (
    SELECT
        l.race_id,
        SUM(CASE WHEN l.compound IN ('INTERMEDIATE','WET') THEN 1 ELSE 0 END) * 1.0
          / NULLIF(COUNT(*),0) AS wet_lap_share
    FROM   laps l
    WHERE  l.session_type = 'R'
    GROUP  BY l.race_id
),
race_classified AS (
    SELECT
        race_id,
        CASE WHEN wet_lap_share >= 0.05 THEN 'wet/mixed' ELSE 'dry' END AS condition
    FROM   race_weather
),
race_chaos AS (
    SELECT
        rc.condition,
        rr.race_id,
        AVG(ABS(rr.grid_position - rr.final_position)) AS avg_position_change
    FROM   race_results rr
    JOIN   race_classified rc ON rr.race_id = rc.race_id
    WHERE  rr.grid_position  IS NOT NULL AND rr.grid_position > 0
      AND  rr.final_position IS NOT NULL AND rr.final_position > 0
    GROUP  BY rc.condition, rr.race_id
)
SELECT
    condition,
    COUNT(DISTINCT race_id) AS races,
    ROUND(AVG(avg_position_change), 3) AS avg_chaos_score
FROM   race_chaos
GROUP  BY condition
ORDER  BY avg_chaos_score DESC;
