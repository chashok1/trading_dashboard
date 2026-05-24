-- =============================================================================
-- 22_fix_user_action_log.sql
-- Repair user_action_log if a pre-existing table from an older schema
-- collided with 21_actionable.sql's CREATE TABLE IF NOT EXISTS.
-- Idempotent: ADD COLUMN IF NOT EXISTS for every expected column.
-- =============================================================================

ALTER TABLE user_action_log
    ADD COLUMN IF NOT EXISTS user_id                   TEXT      NOT NULL DEFAULT 'default',
    ADD COLUMN IF NOT EXISTS acted_at                  TIMESTAMP NOT NULL DEFAULT now(),
    ADD COLUMN IF NOT EXISTS as_of_date                DATE,
    ADD COLUMN IF NOT EXISTS symbol                    TEXT,
    ADD COLUMN IF NOT EXISTS user_action               TEXT,
    ADD COLUMN IF NOT EXISTS user_action_target        TEXT,
    ADD COLUMN IF NOT EXISTS snooze_until              DATE,
    ADD COLUMN IF NOT EXISTS user_notes                TEXT,
    ADD COLUMN IF NOT EXISTS consolidated_action       TEXT,
    ADD COLUMN IF NOT EXISTS winning_source            TEXT,
    ADD COLUMN IF NOT EXISTS winning_priority          INTEGER,
    ADD COLUMN IF NOT EXISTS position_category         TEXT,
    ADD COLUMN IF NOT EXISTS target_min_dollar         NUMERIC,
    ADD COLUMN IF NOT EXISTS target_max_dollar         NUMERIC,
    ADD COLUMN IF NOT EXISTS units_dollar              NUMERIC,
    ADD COLUMN IF NOT EXISTS maintain_min              BOOLEAN,
    ADD COLUMN IF NOT EXISTS suggested_target_dollar   NUMERIC,
    ADD COLUMN IF NOT EXISTS held_at_action            BOOLEAN,
    ADD COLUMN IF NOT EXISTS position_dollar_at_action NUMERIC,
    ADD COLUMN IF NOT EXISTS in_my_list                BOOLEAN,
    ADD COLUMN IF NOT EXISTS source_actions            JSONB,
    ADD COLUMN IF NOT EXISTS rules_engine_fires        JSONB,
    ADD COLUMN IF NOT EXISTS source_raw_snapshot       JSONB;

-- Drop the CHECK constraint if it was attached to a different column type, then re-add.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.constraint_column_usage
        WHERE table_name = 'user_action_log'
          AND constraint_name = 'user_action_log_user_action_check'
    ) THEN
        ALTER TABLE user_action_log DROP CONSTRAINT user_action_log_user_action_check;
    END IF;
END$$;

ALTER TABLE user_action_log
    ADD CONSTRAINT user_action_log_user_action_check
        CHECK (user_action IN ('DONE','SKIPPED','SNOOZED','OVERRIDDEN'))
        NOT VALID;  -- NOT VALID so existing rows (if any) don't block

-- Make sure indexes exist
CREATE INDEX IF NOT EXISTS ix_user_action_log_date_sym ON user_action_log(as_of_date, symbol);
CREATE INDEX IF NOT EXISTS ix_user_action_log_acted    ON user_action_log(acted_at DESC);
