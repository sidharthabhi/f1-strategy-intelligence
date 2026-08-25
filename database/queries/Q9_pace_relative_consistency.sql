-- ============================================================================
-- Q9 — Most consistent driver regardless of car pace
-- ============================================================================
-- Q4b measures absolute stint stddev, but a Williams driver lapping at 95s
-- with 0.4s stddev is being held to a different standard than a Red Bull driver
-- at 91s with 0.4s stddev. This query normalises by the driver's own race pace.
--
-- Coefficient of Variation = stddev / mean. Smaller = more consistent
-- relative to that driver's own car pace.
-- ============================================================================
WITH stint_stats AS (
    SELECT
        driver_id, driver_code, race_id, year, stint,
        AVG(lap_time_sec) AS stint_mean,
        SQRT(MAX(0,
            AVG(lap_time_sec * lap_time_sec)
          - AVG(lap_time_sec) * AVG(lap_time_sec)
        )) AS stint_sd,
        COUNT(*) AS lap_count
    FROM   v_clean_laps
    GROUP  BY driver_id, driver_code, race_id, year, stint
    HAVING lap_count >= 5
),
race_cv AS (
    SELECT
        driver_id, driver_code, race_id, year,
        AVG(stint_sd / NULLIF(stint_mean, 0)) AS race_cv
    FROM   stint_stats
    GROUP  BY driver_id, driver_code, race_id, year
)
SELECT
    driver_code      AS driver,
    year             AS season,
    ROUND(AVG(race_cv) * 1000, 4) AS coeff_variation_x1000,
    COUNT(DISTINCT race_id)       AS races_counted
FROM   race_cv
GROUP  BY driver_code, year
HAVING races_counted >= 10
ORDER  BY year, coeff_variation_x1000 ASC;
