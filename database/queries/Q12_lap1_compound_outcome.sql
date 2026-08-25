-- ============================================================================
-- Q12 — Does first-lap tire compound correlate with final position?
-- ============================================================================
-- Find each driver's compound on their first race lap (after formation).
-- Bucket by normalised compound (using v_compound_normalised) and see
-- avg final position + win rate.
-- ============================================================================
WITH lap1_compounds AS (
    SELECT
        cn.race_id,
        cn.driver_id,
        cn.compound_norm AS first_compound
    FROM   v_compound_normalised cn
    WHERE  cn.lap_number = 2          -- lap 1 in F1 reckoning (lap_number 1 = formation)
)
SELECT
    lc.first_compound AS compound,
    COUNT(*)          AS samples,
    ROUND(AVG(rr.final_position), 2)                            AS avg_final_position,
    ROUND(100.0 * SUM(CASE WHEN rr.final_position = 1 THEN 1 ELSE 0 END) / COUNT(*), 2)  AS win_rate_pct,
    ROUND(100.0 * SUM(CASE WHEN rr.final_position <= 3 THEN 1 ELSE 0 END) / COUNT(*), 2) AS podium_rate_pct,
    ROUND(100.0 * SUM(CASE WHEN rr.final_position <= 10 THEN 1 ELSE 0 END) / COUNT(*), 2) AS points_rate_pct
FROM   lap1_compounds lc
JOIN   race_results rr ON lc.race_id = rr.race_id AND lc.driver_id = rr.driver_id
WHERE  rr.final_position IS NOT NULL
GROUP  BY lc.first_compound
ORDER  BY avg_final_position ASC;
