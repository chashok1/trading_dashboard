-- =============================================================================
-- migrate_member_watch_roles.sql                                    2026-06-03
--
-- PHASE 1b of the gate/WATCH redesign (docs/rule_engine_redesign.md).
--
-- BEHAVIOR-CHANGING. Run this deliberately, then re-derive and compare fire
-- counts before relying on the result.
--
-- Phase 1a (baseline.sql) added ref_trig_composite_mapping.member_role with a
-- DEFAULT of 'gate', so applying the schema alone changes NOTHING — every member
-- stays mandatory exactly as before.
--
-- This script performs the actual reclassification: it marks weight-1 members as
-- 'watch' (corroborating evidence that no longer blocks a composite from firing),
-- mirroring how the workbook encodes them. weight-10 (and all other) members stay
-- gates. After this runs, a composite fires when ALL its gates pass AND its watch
-- evidence clears evidence_cutoff (NULL cutoff = watch never blocks).
--
-- Idempotent. Safe to run multiple times. Run with:
--     psql -d trading -f db/migrate_member_watch_roles.sql
-- then propagate to derived tables:
--     python -m etl.rebuild_rules
-- =============================================================================

BEGIN;

-- Reclassify weight-1 members as watch; everything else remains a gate.
UPDATE ref_trig_composite_mapping
   SET member_role = 'watch'
 WHERE deprecated_at IS NULL
   AND weight_override = 1
   AND member_role IS DISTINCT FROM 'watch';

-- (Optional) keep evidence_cutoff NULL — watch members are purely informational
-- and never block. Set a per-composite cutoff later if you want "at least N of
-- the watch signals must agree". Example (commented out):
--   UPDATE ref_trig_composite_mapping
--      SET evidence_cutoff = 2
--    WHERE composite_rule_code = '449-B-TN-TD-LRR-UP-MACD';

-- Report what changed.
DO $$
DECLARE
    n_watch INTEGER;
    n_gate  INTEGER;
    n_comp_with_watch INTEGER;
BEGIN
    SELECT COUNT(*) INTO n_watch FROM ref_trig_composite_mapping
        WHERE deprecated_at IS NULL AND member_role = 'watch';
    SELECT COUNT(*) INTO n_gate FROM ref_trig_composite_mapping
        WHERE deprecated_at IS NULL AND member_role = 'gate';
    SELECT COUNT(DISTINCT composite_rule_code) INTO n_comp_with_watch
        FROM ref_trig_composite_mapping
        WHERE deprecated_at IS NULL AND member_role = 'watch';
    RAISE NOTICE 'member_role: % watch / % gate members; % composites now have watch members',
        n_watch, n_gate, n_comp_with_watch;
END $$;

COMMIT;
