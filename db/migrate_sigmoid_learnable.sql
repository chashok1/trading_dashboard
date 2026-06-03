-- =============================================================================
-- migrate_sigmoid_learnable.sql                                     2026-06-03
--
-- PHASE 3 of the rule-engine redesign (docs/rule_engine_redesign.md).
--
-- BEHAVIOR-CHANGING (slightly). Run deliberately; re-derive and compare.
--
-- Converts cleanly-learnable atomic rules from 'jump' (a non-differentiable step
-- function) to 'sigmoid' (smooth, with tunable threshold x0 and steepness k), so
-- the ML stage can fit them with gradient methods.
--
-- SAFETY — only MONOTONIC rules are converted. eval_atomic_rule's sigmoid
-- interpolates between wt_below and wt_above and IGNORES wt_between, so a
-- non-monotonic rule (e.g. wt_below=2, wt_between=3, wt_above=1) would be
-- mis-scored. We convert only rules where wt_below <= wt_between <= wt_above or
-- wt_below >= wt_between >= wt_above, and which have a proper zone (from < to).
--
--   x0 = midpoint of the breakout zone     (the learned threshold)
--   k  = 4 / zone_width                     (sigmoid spans ~the old zone)
--
-- Rollback: db/migrate_sigmoid_learnable_rollback.sql restores scoring_mode='jump'.
-- Better still, encode tuned values as a ref_trig_param_set rather than editing
-- the base rows — see etl/ml_tune_thresholds.py.
--
-- Idempotent. Run:
--     psql -d trading -f db/migrate_sigmoid_learnable.sql
--     python -m etl.rebuild_rules
-- =============================================================================

BEGIN;

-- Snapshot the pre-migration scoring_mode so rollback is possible even if this
-- runs more than once (only capture rules still on 'jump').
CREATE TABLE IF NOT EXISTS _bak_atomic_scoring_mode (
    atomic_rule_id INTEGER PRIMARY KEY,
    scoring_mode   TEXT,
    score_params   JSONB,
    saved_at       TIMESTAMPTZ DEFAULT now()
);
INSERT INTO _bak_atomic_scoring_mode (atomic_rule_id, scoring_mode, score_params)
SELECT atomic_rule_id, scoring_mode, score_params
FROM ref_trig_atomic_rule
WHERE deprecated_at IS NULL
ON CONFLICT (atomic_rule_id) DO NOTHING;

UPDATE ref_trig_atomic_rule r
   SET scoring_mode = 'sigmoid',
       score_params = jsonb_build_object(
           'x0', (r.brkeout_from + r.brkeout_to) / 2.0,
           'k',  4.0 / (r.brkeout_to - r.brkeout_from)
       )
 WHERE r.deprecated_at IS NULL
   AND r.scoring_mode = 'jump'
   AND r.brkeout_from IS NOT NULL AND r.brkeout_to IS NOT NULL
   AND r.brkeout_to > r.brkeout_from
   AND r.wt_below IS NOT NULL AND r.wt_between IS NOT NULL AND r.wt_above IS NOT NULL
   AND (
        (r.wt_below <= r.wt_between AND r.wt_between <= r.wt_above) OR
        (r.wt_below >= r.wt_between AND r.wt_between >= r.wt_above)
   );

DO $$
DECLARE n_sig INTEGER; n_jump INTEGER;
BEGIN
    SELECT COUNT(*) INTO n_sig  FROM ref_trig_atomic_rule
        WHERE deprecated_at IS NULL AND scoring_mode = 'sigmoid';
    SELECT COUNT(*) INTO n_jump FROM ref_trig_atomic_rule
        WHERE deprecated_at IS NULL AND scoring_mode = 'jump';
    RAISE NOTICE 'scoring_mode now: % sigmoid, % jump (non-monotonic / no-zone rules left on jump)',
        n_sig, n_jump;
END $$;

COMMIT;
