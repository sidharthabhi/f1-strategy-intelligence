-- ============================================================================
-- Q2 — Does pole guarantee a win? Conversion rate by circuit.
-- ============================================================================
-- Pole = grid_position 1. Win = final_position 1. Conversion = wins from pole
-- as a fraction of all races at that circuit.
--
-- Filters circuits with at least 3 races in the dataset (otherwise small-N noise
-- dominates — Las Vegas with 1 race would be 0% or 100%).
-- ============================================================================
WITH pole_wins AS (
    SELECT
        c.circuit_id,
        c.name AS circuit_name,
        rr.race_id,
        SUM(CASE WHEN rr.grid_position = 1 AND rr.final_position = 1 THEN 1 ELSE 0 END) AS pole_won,
        SUM(CASE WHEN rr.grid_position = 1 THEN 1 ELSE 0 END) AS had_pole
    FROM   race_results rr
    JOIN   races    r ON rr.race_id   = r.race_id
    JOIN   circuits c ON r.circuit_id = c.circuit_id
    GROUP  BY c.circuit_id, c.name, rr.race_id
)
SELECT
    circuit_name,
    COUNT(*) AS races,
    SUM(pole_won) AS poles_to_wins,
    ROUND(100.0 * SUM(pole_won) / COUNT(*), 1) AS conversion_pct
FROM   pole_wins
GROUP  BY circuit_id, circuit_name
HAVING races >= 3
ORDER  BY conversion_pct DESC;
