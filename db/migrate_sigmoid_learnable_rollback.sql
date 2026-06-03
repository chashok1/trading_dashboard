-- =============================================================================
-- migrate_sigmoid_learnable_rollback.sql                           2026-06-03
--
-- Reverts db/migrate_sigmoid_learnable.sql using the _bak_atomic_scoring_mode
-- snapshot it wrote. Restores each rule's original scoring_mode + score_params.
--
--     psql -d trading -f db/migrate_sigmoid_learnable_rollback.sql
--     python -m etl.rebuild_rules
-- =============================================================================

BEGIN;

UPDATE ref_trig_atomic_rule r
   SET scoring_mode = b.scoring_mode,
       score_params = b.score_params
FROM _bak_atomic_scoring_mode b
WHERE r.atomic_rule_id = b.atomic_rule_id;

DO $$
DECLARE n INTEGER;
BEGIN
    SELECT COUNT(*) INTO n FROM _bak_atomic_scoring_mode;
    RAISE NOTICE 'Restored scoring_mode/score_params for % rules', n;
END $$;

-- Optional: drop the snapshot once you're satisfied.
-- DROP TABLE _bak_atomic_scoring_mode;

COMMIT;
