-- ============================================================================
-- Q18 — DNF rate by team — has reliability improved over the dataset?
-- ============================================================================
-- DNF = finish_status NOT IN ('Finished','+1 Lap','+2 Laps','+3 Laps','+4 Laps').
-- Reasons include: Engine, Gearbox, Hydraulics, Accident, Collision, Suspension, ...
-- Returns one row per team-season with DNF rate.
-- ============================================================================
WITH classified AS (
    SELECT
        t.constructor_name AS team,
        d.season,
        rr.race_id,
        CASE
          WHEN rr.finish_status IN ('Finished','+1 Lap','+2 Laps','+3 Laps','+4 Laps','+5 Laps')
            THEN 0 ELSE 1
        END AS is_dnf
    FROM   race_results rr
    JOIN   drivers d ON rr.driver_id = d.driver_id
    JOIN   teams   t ON d.team_id    = t.team_id
    JOIN   races   r ON rr.race_id   = r.race_id AND r.year = d.season
    WHERE  rr.finish_status IS NOT NULL
)
SELECT
    team,
    season,
    COUNT(*)         AS entries,
    SUM(is_dnf)      AS dnfs,
    ROUND(100.0 * SUM(is_dnf) / COUNT(*), 2) AS dnf_rate_pct
FROM   classified
GROUP  BY team, season
HAVING entries >= 10
ORDER  BY season, dnf_rate_pct ASC;
