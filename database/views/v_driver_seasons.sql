-- ============================================================================
-- v_driver_seasons — one row per driver per season with their team + summary
-- ============================================================================
-- Used by Driver DNA queries (Q3, Q9, Q13, Q20) to avoid re-joining
-- drivers + teams every time. Also exposes career-level aggregates that
-- the Power BI Driver DNA page consumes directly.
-- ============================================================================
DROP VIEW IF EXISTS v_driver_seasons;
CREATE VIEW v_driver_seasons AS
SELECT
    d.driver_id,
    d.season,
    d.code,
    d.full_name,
    d.nationality,
    d.team_id,
    t.constructor_name,
    t.short_name AS team_short_name,
    -- Per-season race count + win/podium tallies
    COUNT(DISTINCT rr.race_id) AS races_entered,
    SUM(CASE WHEN rr.final_position = 1 THEN 1 ELSE 0 END) AS wins,
    SUM(CASE WHEN rr.final_position <= 3 THEN 1 ELSE 0 END) AS podiums,
    SUM(CASE WHEN rr.grid_position = 1 THEN 1 ELSE 0 END) AS poles,
    SUM(rr.points_scored)                                        AS season_points,
    SUM(CASE WHEN rr.finish_status NOT IN ('Finished','+1 Lap','+2 Laps','+3 Laps','+4 Laps','+5 Laps','+6 Laps')
                  AND rr.finish_status IS NOT NULL THEN 1 ELSE 0 END) AS dnfs
FROM   drivers d
JOIN   teams   t ON d.team_id = t.team_id
LEFT   JOIN race_results rr ON rr.driver_id = d.driver_id
LEFT   JOIN races   r        ON rr.race_id  = r.race_id AND r.year = d.season
GROUP  BY d.driver_id, d.season, d.code, d.full_name, d.nationality,
          d.team_id, t.constructor_name, t.short_name;
