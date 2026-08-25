-- ============================================================================
-- v_compound_normalised — cross-season tire compound mapping
-- ============================================================================
-- 2018 ran 7 compounds (HYPERSOFT, ULTRASOFT, SUPERSOFT, SOFT, MEDIUM, HARD,
-- SUPERHARD). 2019+ collapsed to 5 (SOFT, MEDIUM, HARD, INTERMEDIATE, WET).
-- For cross-season comparisons (Q12 first-stint compound choice, Q14 fastest
-- lap by compound) we need a unified mapping.
--
-- Mapping rationale:
--   HYPERSOFT  → SOFT      (was the softest, most grip)
--   ULTRASOFT  → SOFT      (one step harder than HYPERSOFT)
--   SUPERSOFT  → SOFT      (renamed to SOFT in 2019)
--   SOFT       → SOFT
--   MEDIUM     → MEDIUM
--   HARD       → HARD
--   SUPERHARD  → HARD      (very rare, used at high-deg circuits)
--   INTERMEDIATE → INTERMEDIATE
--   WET        → WET
-- ============================================================================
DROP VIEW IF EXISTS v_compound_normalised;
CREATE VIEW v_compound_normalised AS
SELECT
    cl.*,
    CASE cl.compound
      WHEN 'HYPERSOFT'    THEN 'SOFT'
      WHEN 'ULTRASOFT'    THEN 'SOFT'
      WHEN 'SUPERSOFT'    THEN 'SOFT'
      WHEN 'SOFT'         THEN 'SOFT'
      WHEN 'MEDIUM'       THEN 'MEDIUM'
      WHEN 'HARD'         THEN 'HARD'
      WHEN 'SUPERHARD'    THEN 'HARD'
      WHEN 'INTERMEDIATE' THEN 'INTERMEDIATE'
      WHEN 'WET'          THEN 'WET'
      ELSE cl.compound
    END AS compound_norm
FROM v_clean_laps cl;
