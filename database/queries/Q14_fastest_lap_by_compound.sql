-- ============================================================================
-- Q14 — % of fastest race laps set on each compound
-- ============================================================================
-- Per race, the fastest valid lap is set by some driver on some compound.
-- We bucket by normalised compound across the dataset.
-- Hypothesis: SOFT dominates (fresh-tire qualifying-style laps near race end).
-- ============================================================================
WITH fastest_per_race AS (
    SELECT
        cn.race_id,
        cn.compound_norm,
        cn.lap_time_sec,
        ROW_NUMBER() OVER (PARTITION BY cn.race_id ORDER BY cn.lap_time_sec ASC) AS rk
    FROM   v_compound_normalised cn
    WHERE  cn.lap_time_sec IS NOT NULL
)
SELECT
    compound_norm AS compound,
    COUNT(*)      AS races_with_fastest,
    ROUND(100.0 * COUNT(*) /
          (SELECT COUNT(*) FROM fastest_per_race WHERE rk = 1), 2) AS pct_of_fastest_laps,
    ROUND(AVG(lap_time_sec), 3) AS avg_fastest_lap_sec
FROM   fastest_per_race
WHERE  rk = 1
GROUP  BY compound_norm
ORDER  BY races_with_fastest DESC;
