-- ============================================================================
-- v_clean_laps — single source of truth for "clean race lap" filtering
-- ============================================================================
-- Every analytical Q joins through this view instead of repeating the same
-- WHERE clauses. Changes here propagate everywhere.
--
-- Filters applied:
--   - is_valid_lap = 1                    (the 7-condition flag)
--   - session_type = 'R'                  (race only — Q sessions excluded)
--   - track_status = 'Green'              (no SC/VSC/yellow/red contamination)
--   - lap_time_sec IS NOT NULL            (defensive — should never trip)
--   - compound NOT IN ('INTERMEDIATE','WET','None','UNKNOWN','nan')
--                                          (dry-track laps only)
--
-- Join targets exposed:
--   - r.year, r.round, r.event_name       (season filter)
--   - c.name AS circuit_name, c.length_km, c.surface_type
--   - d.code AS driver_code, d.full_name
--   - t.constructor_name, t.short_name
-- ============================================================================
DROP VIEW IF EXISTS v_clean_laps;
CREATE VIEW v_clean_laps AS
SELECT
    l.lap_id,
    l.race_id,
    l.driver_id,
    l.lap_number,
    l.lap_time_sec,
    l.sector1_sec,
    l.sector2_sec,
    l.sector3_sec,
    l.compound,
    l.tyre_life,
    l.stint,
    l.position,
    l.is_personal_best,
    l.speed_trap_kmh,
    -- Joined dimensions
    r.year,
    r.round,
    r.event_name,
    r.total_laps    AS race_total_laps,
    c.circuit_id,
    c.name          AS circuit_name,
    c.length_km     AS circuit_length_km,
    c.surface_type,
    d.code          AS driver_code,
    d.full_name     AS driver_name,
    t.team_id,
    t.constructor_name,
    t.short_name    AS team_short_name
FROM   laps l
JOIN   races    r ON l.race_id   = r.race_id
JOIN   circuits c ON r.circuit_id = c.circuit_id
JOIN   drivers  d ON l.driver_id  = d.driver_id AND d.season = r.year
JOIN   teams    t ON d.team_id    = t.team_id
WHERE  l.is_valid_lap   = 1
  AND  l.session_type   = 'R'
  AND  l.track_status   = 'Green'
  AND  l.lap_time_sec   IS NOT NULL
  AND  l.compound NOT IN ('INTERMEDIATE','WET','None','UNKNOWN','nan');
