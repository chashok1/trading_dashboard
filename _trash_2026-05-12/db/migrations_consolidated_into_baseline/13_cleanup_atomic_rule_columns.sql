-- ============================================================
-- Clean up unused atomic rule columns
-- Drop name_a, name_b, ma_source_sheet (no longer needed)
-- ============================================================

ALTER TABLE ref_trig_atomic_rule
  DROP COLUMN IF EXISTS name_a,
  DROP COLUMN IF EXISTS name_b,
  DROP COLUMN IF EXISTS ma_source_sheet;
