-- ============================================================================
-- F1 Strategy Intelligence Dashboard — Schema (SQLite, 3NF)
-- ============================================================================
-- Run: sqlite3 database/f1_analytics.db < database/schema.sql
-- ============================================================================

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------------
-- 1. circuits — static reference, ~25 rows
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS circuits;
CREATE TABLE circuits (
    circuit_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    fastf1_key       TEXT UNIQUE,            -- FastF1's EventName / Location key
    name             TEXT NOT NULL,
    country          TEXT,
    city             TEXT,
    length_km        REAL,
    corners          INTEGER,
    drs_zones        INTEGER,
    lap_record_sec   REAL,
    surface_type     TEXT,                   -- Smooth / Abrasive / Street
    first_gp_year    INTEGER
);

-- ---------------------------------------------------------------------------
-- 2. races — master calendar, ~161 rows
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS races;
CREATE TABLE races (
    race_id              INTEGER PRIMARY KEY AUTOINCREMENT,
    circuit_id           INTEGER NOT NULL,
    year                 INTEGER NOT NULL,
    round                INTEGER NOT NULL,
    event_name           TEXT NOT NULL,
    date                 TEXT,                -- ISO YYYY-MM-DD
    total_laps           INTEGER,
    weather_condition    TEXT,                -- Dry / Wet / Mixed
    avg_air_temp         REAL,
    avg_track_temp       REAL,
    safety_car_laps      INTEGER DEFAULT 0,
    vsc_laps             INTEGER DEFAULT 0,
    sc_periods           TEXT,                -- JSON: [{lap_start,lap_end,type}]
    UNIQUE (year, round),
    FOREIGN KEY (circuit_id) REFERENCES circuits(circuit_id)
);

-- ---------------------------------------------------------------------------
-- 3. teams — one row per team per season, ~140 rows
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS teams;
CREATE TABLE teams (
    team_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    season            INTEGER NOT NULL,
    constructor_name  TEXT NOT NULL,
    short_name        TEXT NOT NULL,
    engine_supplier   TEXT,
    team_principal    TEXT,
    base_country      TEXT,
    team_color        TEXT,                   -- hex code for viz
    UNIQUE (season, constructor_name)
);

-- ---------------------------------------------------------------------------
-- 4. drivers — one row per driver per season per team, ~280 rows
-- driver_id is person-level (stable); season+team_id capture the seat
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS drivers;
CREATE TABLE drivers (
    driver_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    season         INTEGER NOT NULL,
    team_id        INTEGER NOT NULL,
    code           TEXT NOT NULL,             -- 3-letter (VER, HAM)
    full_name      TEXT NOT NULL,
    number         INTEGER,
    nationality    TEXT,
    dob            TEXT,                      -- ISO YYYY-MM-DD
    date_from      TEXT,                      -- for mid-season changes
    date_to        TEXT,
    is_substitute  INTEGER DEFAULT 0,
    FOREIGN KEY (team_id) REFERENCES teams(team_id)
);

-- Per-race result fields (used by reliability + points queries).
-- Keeping these on drivers means one driver row can hold season-level attributes
-- AND we add a separate race_results table for per-race facts.
DROP TABLE IF EXISTS race_results;
CREATE TABLE race_results (
    result_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    race_id            INTEGER NOT NULL,
    driver_id          INTEGER NOT NULL,
    grid_position      INTEGER,
    final_position     INTEGER,
    finish_status      TEXT,                  -- Finished / +1 Lap / Engine / Accident / ...
    points_scored      REAL DEFAULT 0,
    fastest_lap        INTEGER DEFAULT 0,     -- 0/1 flag
    UNIQUE (race_id, driver_id),
    FOREIGN KEY (race_id)  REFERENCES races(race_id),
    FOREIGN KEY (driver_id) REFERENCES drivers(driver_id)
);

-- ---------------------------------------------------------------------------
-- 5. laps — core analytical table, ~193K rows
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS laps;
CREATE TABLE laps (
    lap_id              INTEGER PRIMARY KEY AUTOINCREMENT,
    race_id             INTEGER NOT NULL,
    driver_id           INTEGER NOT NULL,
    session_type        TEXT DEFAULT 'R',       -- R / Q / FP1..3 / S / SQ
    lap_number          INTEGER NOT NULL,
    lap_time_sec        REAL,
    sector1_sec         REAL,
    sector2_sec         REAL,
    sector3_sec         REAL,
    compound            TEXT,                   -- SOFT/MEDIUM/HARD/INTERMEDIATE/WET
    tyre_life           INTEGER,
    stint               INTEGER,
    position            INTEGER,
    gap_to_leader_sec   REAL,
    track_status        TEXT,                   -- Green / SC / VSC / Yellow / Red
    is_valid_lap        INTEGER DEFAULT 0,
    is_personal_best    INTEGER DEFAULT 0,
    speed_trap_kmh      REAL,
    is_pit_lap          INTEGER DEFAULT 0,
    deleted             INTEGER DEFAULT 0,
    FOREIGN KEY (race_id)   REFERENCES races(race_id),
    FOREIGN KEY (driver_id) REFERENCES drivers(driver_id)
);

-- ---------------------------------------------------------------------------
-- 6. pit_stops — ~12K rows
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS pit_stops;
CREATE TABLE pit_stops (
    pit_id              INTEGER PRIMARY KEY AUTOINCREMENT,
    race_id             INTEGER NOT NULL,
    driver_id           INTEGER NOT NULL,
    lap_number          INTEGER NOT NULL,
    stop_number         INTEGER,
    stop_duration_sec   REAL,
    compound_in         TEXT,
    compound_out        TEXT,
    position_before     INTEGER,
    position_after      INTEGER,
    stop_type           TEXT DEFAULT 'normal',  -- normal/drive_through/double_stack/no_tire_change
    undercut_attempt    INTEGER DEFAULT 0,
    overcut_attempt     INTEGER DEFAULT 0,
    FOREIGN KEY (race_id)   REFERENCES races(race_id),
    FOREIGN KEY (driver_id) REFERENCES drivers(driver_id)
);

-- ---------------------------------------------------------------------------
-- 7. telemetry — selective load (fastest lap per driver per race)
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS telemetry;
CREATE TABLE telemetry (
    telemetry_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    lap_id         INTEGER NOT NULL,
    distance_m     REAL,
    speed_kmh      REAL,
    throttle_pct   REAL,
    brake          INTEGER,
    gear           INTEGER,
    drs            INTEGER,
    rpm            INTEGER,
    x_pos          REAL,
    y_pos          REAL,
    FOREIGN KEY (lap_id) REFERENCES laps(lap_id)
);

-- ============================================================================
-- Indexes — built after loading, but declared here for a fresh DB
-- ============================================================================
CREATE INDEX IF NOT EXISTS idx_laps_race_driver      ON laps(race_id, driver_id);
CREATE INDEX IF NOT EXISTS idx_laps_valid            ON laps(is_valid_lap, race_id);
CREATE INDEX IF NOT EXISTS idx_laps_session          ON laps(session_type, race_id);
CREATE INDEX IF NOT EXISTS idx_laps_stint            ON laps(driver_id, race_id, stint);
CREATE INDEX IF NOT EXISTS idx_pit_race_driver       ON pit_stops(race_id, driver_id);
CREATE INDEX IF NOT EXISTS idx_results_race_driver   ON race_results(race_id, driver_id);
CREATE INDEX IF NOT EXISTS idx_races_year_round      ON races(year, round);
CREATE INDEX IF NOT EXISTS idx_drivers_season_code   ON drivers(season, code);
CREATE INDEX IF NOT EXISTS idx_telemetry_lap         ON telemetry(lap_id);
