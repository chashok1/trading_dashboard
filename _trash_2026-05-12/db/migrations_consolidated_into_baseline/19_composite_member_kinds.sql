-- =============================================================================
-- Composite member-kinds extension (2026-05-10)
--
-- Composite rules can have THREE kinds of members:
--   1. atomic    - reference an existing ref_trig_atomic_rule (legacy default)
--   2. data      - inline rule against a drv_cat column (no shared atomic def)
--   3. composite - nest another composite's score (parent ← child(score))
--
-- This migration is additive and backward-compatible. Existing rows default
-- to member_kind='atomic' and atomic_rule_id keeps its meaning.
--
-- Runtime evaluation of kinds 2 and 3 in _derive_stks_impl is a follow-up
-- (cycle-detection for nested composites + inline scoring for data members).
-- =============================================================================

ALTER TABLE ref_trig_composite_mapping
  ADD COLUMN IF NOT EXISTS member_kind TEXT NOT NULL DEFAULT 'atomic',

  -- 'data' kind columns: inline rule definition (no shared atomic_rule)
  ADD COLUMN IF NOT EXISTS data_column           TEXT,         -- e.g. 'drv_cat_atomic_input.bb_top'
  ADD COLUMN IF NOT EXISTS data_brkeout_from     NUMERIC,
  ADD COLUMN IF NOT EXISTS data_brkeout_to       NUMERIC,
  ADD COLUMN IF NOT EXISTS data_wt_below         NUMERIC,
  ADD COLUMN IF NOT EXISTS data_wt_between       NUMERIC,
  ADD COLUMN IF NOT EXISTS data_wt_above         NUMERIC,
  ADD COLUMN IF NOT EXISTS data_scoring_mode     TEXT DEFAULT 'jump',
  ADD COLUMN IF NOT EXISTS data_score_params     JSONB,

  -- 'composite' kind: nest another composite by code
  ADD COLUMN IF NOT EXISTS nested_composite_code TEXT,

  -- Scalar applied to the resolved score regardless of kind
  -- (renamed from weight_override semantics: when present, multiplies the
  --  member's contribution rather than replacing the atomic's emitted weight)
  ADD COLUMN IF NOT EXISTS member_multiplier     NUMERIC;

-- Existing rows: member_kind already defaults to 'atomic'. Make atomic_rule_id
-- nullable so data/composite members don't have to set it.
DO $$
BEGIN
  -- atomic_rule_id was previously part of the PK / NOT NULL; make it nullable
  -- but keep the existing UNIQUE constraint scoped to (composite_rule_code,
  -- atomic_rule_id) so atomic members can't double-up.
  BEGIN
    EXECUTE 'ALTER TABLE ref_trig_composite_mapping ALTER COLUMN atomic_rule_id DROP NOT NULL';
  EXCEPTION WHEN others THEN
    NULL;  -- already nullable, fine
  END;
END $$;

-- Constraint: each row must satisfy exactly one of the three kind shapes.
ALTER TABLE ref_trig_composite_mapping
  DROP CONSTRAINT IF EXISTS member_kind_shape_check;

ALTER TABLE ref_trig_composite_mapping
  ADD CONSTRAINT member_kind_shape_check CHECK (
    (member_kind = 'atomic'    AND atomic_rule_id IS NOT NULL
                               AND data_column IS NULL
                               AND nested_composite_code IS NULL) OR
    (member_kind = 'data'      AND data_column IS NOT NULL
                               AND atomic_rule_id IS NULL
                               AND nested_composite_code IS NULL) OR
    (member_kind = 'composite' AND nested_composite_code IS NOT NULL
                               AND atomic_rule_id IS NULL
                               AND data_column IS NULL)
  );

-- Sanity-check the discriminator value
ALTER TABLE ref_trig_composite_mapping
  DROP CONSTRAINT IF EXISTS member_kind_value_check;
ALTER TABLE ref_trig_composite_mapping
  ADD CONSTRAINT member_kind_value_check CHECK (
    member_kind IN ('atomic', 'data', 'composite')
  );

-- Index for nested-composite traversal during derive (follow children)
CREATE INDEX IF NOT EXISTS ix_composite_mapping_nested
  ON ref_trig_composite_mapping(nested_composite_code)
  WHERE nested_composite_code IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_composite_mapping_kind
  ON ref_trig_composite_mapping(member_kind);
