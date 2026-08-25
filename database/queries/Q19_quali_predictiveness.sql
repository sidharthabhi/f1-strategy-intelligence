-- ============================================================================
-- Q19 — How accurately does qualifying predict top-3 by circuit?
-- ============================================================================
-- For each circuit, % of races where the actual top-3 finishers ALL came from
-- the top 3 grid positions. Higher = quali-dominant track. Lower = chaos-prone.
-- ============================================================================
WITH race_top3_match AS (
    SELECT
        r.race_id,
        r.circuit_id,
        SUM(CASE WHEN rr.grid_position <= 3 AND rr.final_position <= 3 THEN 1 ELSE 0 END) AS top3_grid_to_top3_finish
    FROM   races r
    JOIN   race_results rr ON rr.race_id = r.race_id
    WHERE  rr.grid_position  IS NOT NULL AND rr.grid_position > 0
      AND  rr.final_position IS NOT NULL AND rr.final_position > 0
    GROUP  BY r.race_id, r.circuit_id
),
race_classified AS (
    SELECT race_id, circuit_id,
           CASE WHEN top3_grid_to_top3_finish = 3 THEN 1 ELSE 0 END AS perfect_match
    FROM   race_top3_match
)
SELECT
    c.name                              AS circuit,
    COUNT(*)                            AS races,
    SUM(perfect_match)                  AS races_with_quali_top3_finish,
    ROUND(100.0 * SUM(perfect_match) / COUNT(*), 1) AS quali_predictive_pct
FROM   race_classified rc
JOIN   circuits c ON rc.circuit_id = c.circuit_id
GROUP  BY c.circuit_id, c.name
HAVING races >= 3
ORDER  BY quali_predictive_pct DESC;
