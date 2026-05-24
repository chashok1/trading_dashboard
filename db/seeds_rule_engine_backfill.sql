-- =============================================================================
-- seeds_rule_engine_backfill.sql                        2026-05-12
--
-- One-shot backfill for two pre-existing bugs in the rule-engine plumbing:
--
--   1) ref_trig_atomic_rule.rule_name was never written by the workbook
--      loader. The atomic-rule resolver in etl/derive.py keys on rule_name,
--      so rules silently evaluated to 0. Mirror ma_column_name into
--      rule_name for any row that's missing it.
--
--   2) The loader's "skip if col A and col B are both empty" check filtered
--      out atomic rules whose only meaningful field was col L. Those rules
--      never reached the DB. The loader is fixed in etl/load_raw.py
--      (2026-05-12) — running tickers_initial_load or scheduler against
--      the current workbook will re-insert the missing rows.
--
-- Idempotent. Safe to run multiple times. Run with:
--     psql -d trading -f db/seeds_rule_engine_backfill.sql
-- or:
--     python -m db.init_db
-- (init_db picks it up via the db/*.sql glob.)
-- =============================================================================

BEGIN;

-- 1) Mirror ma_column_name into rule_name for any row that doesn't have it.
UPDATE ref_trig_atomic_rule
   SET rule_name = ma_column_name
 WHERE rule_name IS NULL
   AND ma_column_name IS NOT NULL;

-- 2) Optional: report how many rows we just touched.
DO $$
DECLARE
    n_total INTEGER;
    n_no_rule_name INTEGER;
    n_no_ma_column INTEGER;
BEGIN
    SELECT COUNT(*) INTO n_total FROM ref_trig_atomic_rule WHERE deprecated_at IS NULL;
    SELECT COUNT(*) INTO n_no_rule_name FROM ref_trig_atomic_rule
        WHERE deprecated_at IS NULL AND rule_name IS NULL;
    SELECT COUNT(*) INTO n_no_ma_column FROM ref_trig_atomic_rule
        WHERE deprecated_at IS NULL AND ma_column_name IS NULL;
    RAISE NOTICE 'ref_trig_atomic_rule: % active rows, % still missing rule_name, % still missing ma_column_name',
        n_total, n_no_rule_name, n_no_ma_column;
END $$;

COMMIT;
