-- ============================================================================
-- Q17 — Which teams show the steepest in-season development curve?
-- ============================================================================
-- Method: split each season into first half and second half by race round.
-- Compare avg pace at shared circuits (the same circuit must appear in both
-- halves — rare in F1 since rounds are unique, so we compare against the
-- season's overall avg lap on that circuit using all teams as baseline).
--
-- Simpler & robust approach used here: compute the team's avg lap time
-- normalised against the field median, separately for first half (rounds 1-12)
-- and second half (rounds 13+). Compare gap to median across the two halves.
-- Negative delta = team gained pace relative to field.
-- ============================================================================
WITH race_team_pace AS (
    SELECT
        cl.year,
        cl.round,
        cl.constructor_name,
        cl.circuit_id,
        AVG(cl.lap_time_sec) AS team_lap
    FROM   v_clean_laps cl
    GROUP  BY cl.year, cl.round, cl.constructor_name, cl.circuit_id
),
race_field_median AS (
    -- Per (year, round, circuit), the AVG of all team paces is our "field reference"
    SELECT year, round, circuit_id, AVG(team_lap) AS field_lap
    FROM   race_team_pace GROUP BY year, round, circuit_id
),
half_pace AS (
    SELECT
        rtp.year,
        rtp.constructor_name,
        CASE WHEN rtp.round <= 12 THEN 'H1' ELSE 'H2' END AS half,
        AVG(rtp.team_lap - rfm.field_lap) AS avg_gap_to_field
    FROM   race_team_pace rtp
    JOIN   race_field_median rfm
           ON rtp.year = rfm.year AND rtp.round = rfm.round
          AND rtp.circuit_id = rfm.circuit_id
    GROUP  BY rtp.year, rtp.constructor_name, half
)
SELECT
    h1.year                                        AS season,
    h1.constructor_name                            AS team,
    ROUND(h1.avg_gap_to_field, 3)                  AS h1_gap_sec,
    ROUND(h2.avg_gap_to_field, 3)                  AS h2_gap_sec,
    ROUND(h1.avg_gap_to_field - h2.avg_gap_to_field, 3) AS development_gain_sec
FROM   half_pace h1
JOIN   half_pace h2
       ON h1.year = h2.year AND h1.constructor_name = h2.constructor_name
WHERE  h1.half = 'H1' AND h2.half = 'H2'
ORDER  BY h1.year, development_gain_sec DESC;
