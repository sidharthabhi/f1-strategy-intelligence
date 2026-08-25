-- ============================================================================
-- Q5 — Which circuits have the highest tire degradation?
-- ============================================================================
-- Linear regression in pure SQLite: slope of lap_time_sec ~ tyre_life
-- per (circuit, compound). Higher slope = more degradation = harder on tires.
--
-- SQLite has no LINEST. We compute slope from raw sums:
--   slope = (n*Σxy - Σx*Σy) / (n*Σx² - (Σx)²)
--
-- Filtered to MEDIUM compound only (most consistent across seasons), tyre_life
-- between 3-25 laps (excludes out-laps and end-of-stint anomalies). Aggregated
-- across all seasons — gives a single "this circuit's deg character" number.
-- ============================================================================
WITH stint_laps AS (
    SELECT
        circuit_id,
        circuit_name,
        compound,
        tyre_life,
        lap_time_sec
    FROM   v_compound_normalised
    WHERE  compound_norm = 'MEDIUM'
      AND  tyre_life BETWEEN 3 AND 25
),
sums AS (
    SELECT
        circuit_id,
        circuit_name,
        COUNT(*) AS n,
        SUM(tyre_life)                  AS sx,
        SUM(lap_time_sec)               AS sy,
        SUM(tyre_life * lap_time_sec)   AS sxy,
        SUM(tyre_life * tyre_life)      AS sxx
    FROM   stint_laps
    GROUP  BY circuit_id, circuit_name
    HAVING n >= 200
)
SELECT
    circuit_name,
    n AS samples,
    ROUND(
        (n * sxy - sx * sy) * 1.0
      / NULLIF(n * sxx - sx * sx, 0),
        4
    ) AS deg_sec_per_lap,
    ROUND(sy * 1.0 / n, 3) AS avg_lap_sec
FROM   sums
ORDER  BY deg_sec_per_lap DESC;
