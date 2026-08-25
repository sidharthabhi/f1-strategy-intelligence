-- ============================================================================
-- Q10 — Avg position gained from undercut vs overcut by circuit
-- ============================================================================
-- "Undercut" = pitting earlier than rival, with fresh tires aiming to lap faster
--             before they pit and get out ahead. We tagged these as
--             undercut_attempt=1 in pit_stops during ingestion.
-- "Overcut"  = pitting later, leveraging warm tires while rivals struggle on
--             cold rubber. (We didn't tag these explicitly — Q10 covers undercut
--             only, with overcut as a future enhancement.)
--
-- Position gain = position_before - position_after (positive = gained).
-- pit_stops.position_after is not currently populated by FastF1 ingestion;
-- we derive it from the lap immediately after the stop.
-- ============================================================================
WITH stops_with_outcome AS (
    SELECT
        p.race_id,
        p.driver_id,
        p.lap_number AS pit_lap,
        p.position_before,
        p.undercut_attempt,
        l_after.position AS position_after_stop
    FROM   pit_stops p
    JOIN   laps l_after
           ON  l_after.race_id   = p.race_id
          AND  l_after.driver_id = p.driver_id
          AND  l_after.lap_number = p.lap_number + 2  -- skip the slow out-lap
          AND  l_after.session_type = 'R'
)
SELECT
    c.name AS circuit,
    SUM(CASE WHEN s.undercut_attempt = 1 THEN 1 ELSE 0 END) AS undercut_attempts,
    ROUND(AVG(CASE WHEN s.undercut_attempt = 1
                   THEN (s.position_before - s.position_after_stop) END), 2) AS avg_undercut_gain,
    SUM(CASE WHEN s.undercut_attempt = 0 THEN 1 ELSE 0 END) AS regular_stops,
    ROUND(AVG(CASE WHEN s.undercut_attempt = 0
                   THEN (s.position_before - s.position_after_stop) END), 2) AS avg_regular_gain
FROM   stops_with_outcome s
JOIN   races    r ON s.race_id     = r.race_id
JOIN   circuits c ON r.circuit_id  = c.circuit_id
WHERE  s.position_before IS NOT NULL
  AND  s.position_after_stop IS NOT NULL
GROUP  BY c.circuit_id, c.name
HAVING undercut_attempts >= 5
ORDER  BY avg_undercut_gain DESC;
