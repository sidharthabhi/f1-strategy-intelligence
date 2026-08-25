-- ============================================================================
-- Q11 — Which team recovers most positions after a safety car?
-- ============================================================================
-- An SC bunches up the field. Some teams use this to leapfrog (free pit stop,
-- aggressive restart) while others lose positions. We measure: position at
-- the end of the SC period vs position 5 laps after green flag returns.
--
-- We tagged SC laps via track_status = 'SC'. The SC period boundaries are
-- the first SC lap and the last SC lap before track returns to Green.
--
-- Method:
--   1. Identify SC lap windows per race
--   2. For each driver, find their position on the last SC lap
--   3. Find their position 5 laps after green flag returns
--   4. Aggregate position change by team
-- ============================================================================
WITH lap_status AS (
    SELECT race_id, lap_number, MIN(track_status) AS status
    FROM   laps
    WHERE  session_type = 'R'
    GROUP  BY race_id, lap_number
),
sc_windows AS (
    -- Find groups of consecutive SC laps per race
    SELECT
        ls.race_id,
        MAX(ls.lap_number) AS sc_end_lap
    FROM   lap_status ls
    WHERE  ls.status = 'SC'
    GROUP  BY ls.race_id
),
restart_positions AS (
    SELECT
        sc.race_id,
        sc.sc_end_lap,
        l_sc.driver_id,
        l_sc.position           AS pos_at_sc_end,
        l_after.position        AS pos_5_laps_after
    FROM   sc_windows sc
    JOIN   laps l_sc
           ON  l_sc.race_id    = sc.race_id
          AND  l_sc.lap_number = sc.sc_end_lap
          AND  l_sc.session_type = 'R'
    JOIN   laps l_after
           ON  l_after.race_id   = sc.race_id
          AND  l_after.driver_id = l_sc.driver_id
          AND  l_after.lap_number = sc.sc_end_lap + 5
          AND  l_after.session_type = 'R'
    WHERE  l_sc.position IS NOT NULL AND l_after.position IS NOT NULL
)
SELECT
    t.constructor_name AS team,
    COUNT(*) AS sc_restart_situations,
    ROUND(AVG(rp.pos_at_sc_end - rp.pos_5_laps_after), 2) AS avg_positions_gained
FROM   restart_positions rp
JOIN   drivers d ON rp.driver_id = d.driver_id
JOIN   races   r ON rp.race_id   = r.race_id AND r.year = d.season
JOIN   teams   t ON d.team_id    = t.team_id
GROUP  BY t.constructor_name
HAVING sc_restart_situations >= 5
ORDER  BY avg_positions_gained DESC;
