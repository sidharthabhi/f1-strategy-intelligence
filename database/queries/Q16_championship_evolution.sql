-- ============================================================================
-- Q16 — How has the constructor championship gap evolved race-by-race?
-- ============================================================================
-- For each race in each season, cumulative team points to that point.
-- Output: one row per (season, race_round, team) — feeds the championship
-- animation on the Constructor Battle dashboard page.
-- ============================================================================
WITH per_race_team_points AS (
    SELECT
        r.year,
        r.round,
        r.race_id,
        t.constructor_name,
        SUM(rr.points_scored) AS race_team_points
    FROM   race_results rr
    JOIN   drivers d ON rr.driver_id = d.driver_id
    JOIN   teams   t ON d.team_id    = t.team_id
    JOIN   races   r ON rr.race_id   = r.race_id AND r.year = d.season
    GROUP  BY r.year, r.round, r.race_id, t.constructor_name
)
SELECT
    year,
    round,
    constructor_name AS team,
    race_team_points,
    SUM(race_team_points) OVER (
      PARTITION BY year, constructor_name
      ORDER BY round
      ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS cumulative_points
FROM   per_race_team_points
ORDER  BY year, round, cumulative_points DESC;
