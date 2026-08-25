-- ============================================================================
-- Q6 — How much has each team's lap time evolved over the dataset window?
-- ============================================================================
-- For each (team, season), compute the avg clean race lap time normalised by
-- circuit. Returns each team-season relative to the same team's 2018 baseline,
-- so the "evolution" number is comparable across teams.
--
-- "% improvement" = positive means faster than 2018, negative = slower.
-- Methodology: for each circuit, compute the team's avg lap. Then for each
-- season, average those circuit-deltas vs 2018.
-- ============================================================================
WITH team_circuit_pace AS (
    SELECT
        constructor_name,
        year,
        circuit_id,
        AVG(lap_time_sec) AS avg_lap
    FROM   v_clean_laps
    GROUP  BY constructor_name, year, circuit_id
),
baseline_2018 AS (
    SELECT constructor_name, circuit_id, avg_lap AS baseline_lap
    FROM   team_circuit_pace
    WHERE  year = 2018
)
SELECT
    tcp.constructor_name AS team,
    tcp.year             AS season,
    ROUND(AVG(tcp.avg_lap - b.baseline_lap), 3) AS avg_delta_vs_2018_sec,
    ROUND(100.0 * AVG((tcp.avg_lap - b.baseline_lap) / b.baseline_lap), 3) AS pct_change_vs_2018,
    COUNT(DISTINCT tcp.circuit_id) AS circuits_compared
FROM   team_circuit_pace tcp
JOIN   baseline_2018 b
       ON tcp.constructor_name = b.constructor_name
      AND tcp.circuit_id       = b.circuit_id
WHERE  tcp.year >= 2019
GROUP  BY tcp.constructor_name, tcp.year
HAVING circuits_compared >= 3
ORDER  BY tcp.year, avg_delta_vs_2018_sec ASC;
