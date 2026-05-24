-- =============================================================================
-- seeds_action_check_constraints.sql                    2026-05-12
-- Add CHECK constraints on the action enums for an existing database.
-- Safe to run multiple times: skips if constraint already present.
--   action IN ('REMOVE','REDUCE','INCREASE','ADD','HOLD')   -- or NULL
-- Picked up automatically by db/init_db.py (db/*.sql glob).
-- =============================================================================
BEGIN;

-- drv_outlook_action.action
DO $$
BEGIN
    -- 1. Surface any rows that would violate the constraint
    PERFORM 1 FROM drv_outlook_action
        WHERE action IS NOT NULL
          AND action NOT IN ('REMOVE','REDUCE','INCREASE','ADD','HOLD');
    IF FOUND THEN
        RAISE NOTICE 'drv_outlook_action has rows with non-canonical action values; '
                     'they will fail the new CHECK. Fix them before re-running.';
    END IF;

    -- 2. Add the constraint if not already present
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ck_drv_outlook_action_action'
    ) THEN
        ALTER TABLE drv_outlook_action
            ADD CONSTRAINT ck_drv_outlook_action_action
            CHECK (action IS NULL OR action IN ('REMOVE','REDUCE','INCREASE','ADD','HOLD'));
        RAISE NOTICE 'Added ck_drv_outlook_action_action';
    ELSE
        RAISE NOTICE 'ck_drv_outlook_action_action already present, skipping';
    END IF;
END $$;

-- drv_actionable.consolidated_action
DO $$
BEGIN
    PERFORM 1 FROM drv_actionable
        WHERE consolidated_action IS NOT NULL
          AND consolidated_action NOT IN ('REMOVE','REDUCE','INCREASE','ADD','HOLD');
    IF FOUND THEN
        RAISE NOTICE 'drv_actionable has rows with non-canonical consolidated_action values; '
                     'they will fail the new CHECK. Fix them before re-running.';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ck_drv_actionable_consolidated'
    ) THEN
        ALTER TABLE drv_actionable
            ADD CONSTRAINT ck_drv_actionable_consolidated
            CHECK (consolidated_action IS NULL OR consolidated_action IN ('REMOVE','REDUCE','INCREASE','ADD','HOLD'));
        RAISE NOTICE 'Added ck_drv_actionable_consolidated';
    ELSE
        RAISE NOTICE 'ck_drv_actionable_consolidated already present, skipping';
    END IF;
END $$;

COMMIT;
