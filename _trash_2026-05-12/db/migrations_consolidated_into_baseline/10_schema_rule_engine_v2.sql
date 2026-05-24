-- ============================================================
-- Rule Engine v2 Schema Migrations
-- Backward compatible: all new columns have safe defaults
-- ============================================================

-- Section 2.1: Extend ref_trig_atomic_rule
ALTER TABLE ref_trig_atomic_rule
  ADD COLUMN IF NOT EXISTS category        text,
  ADD COLUMN IF NOT EXISTS intent_text     text,
  ADD COLUMN IF NOT EXISTS scoring_mode    text NOT NULL DEFAULT 'jump',
  ADD COLUMN IF NOT EXISTS score_params    jsonb,
  ADD COLUMN IF NOT EXISTS deprecated_at   timestamptz;

-- Section 2.2: Extend ref_trig_composite_mapping
ALTER TABLE ref_trig_composite_mapping
  ADD COLUMN IF NOT EXISTS category          text,
  ADD COLUMN IF NOT EXISTS intent_text       text,
  ADD COLUMN IF NOT EXISTS precondition_expr text,
  ADD COLUMN IF NOT EXISTS deprecated_at     timestamptz;

-- Section 2.3: New table — user_action_log
CREATE TABLE IF NOT EXISTS user_action_log (
  id                bigserial PRIMARY KEY,
  as_of_date        date        NOT NULL,
  symbol            text        NOT NULL,
  action_code       text        NOT NULL,
  triggered_rules   jsonb       NOT NULL,
  notes             text,
  created_at        timestamptz NOT NULL DEFAULT now(),
  user_email        text
);
CREATE INDEX IF NOT EXISTS ix_user_action_log_symbol_date ON user_action_log(symbol, as_of_date);
CREATE INDEX IF NOT EXISTS ix_user_action_log_date ON user_action_log(as_of_date);

-- Section 2.4: New table — drv_rule_outcome
CREATE TABLE IF NOT EXISTS drv_rule_outcome (
  rule_id        text       NOT NULL,
  rule_kind      text       NOT NULL,
  as_of_date     date       NOT NULL,
  symbol         text       NOT NULL,
  action_code    text,
  fwd_5d_pct     numeric,
  fwd_20d_pct    numeric,
  hit            boolean,
  computed_at    timestamptz DEFAULT now(),
  PRIMARY KEY (rule_id, as_of_date, symbol)
);
CREATE INDEX IF NOT EXISTS ix_drv_rule_outcome_date ON drv_rule_outcome(as_of_date);
CREATE INDEX IF NOT EXISTS ix_drv_rule_outcome_rule_id ON drv_rule_outcome(rule_id);

-- Section 3.2: Extend drv_stks for traceability
ALTER TABLE drv_stks
  ADD COLUMN IF NOT EXISTS triggered_atomic_ids  jsonb,
  ADD COLUMN IF NOT EXISTS triggered_composite_ids jsonb,
  ADD COLUMN IF NOT EXISTS triggered_group_ids jsonb;

-- Section 2.5: New view — v_rule_performance
CREATE OR REPLACE VIEW v_rule_performance AS
SELECT
  rule_id,
  rule_kind,
  COUNT(*)                              AS sample_size,
  ROUND(AVG(CASE WHEN hit THEN 1 ELSE 0 END)::numeric, 4)  AS hit_rate,
  ROUND(AVG(CASE WHEN NOT hit THEN 1 ELSE 0 END)::numeric, 4) AS false_positive_rate,
  ROUND(AVG(fwd_5d_pct)::numeric, 4)                       AS avg_fwd_5d,
  ROUND(AVG(fwd_20d_pct)::numeric, 4)                      AS avg_fwd_20d,
  MIN(as_of_date)                       AS first_seen,
  MAX(as_of_date)                       AS last_seen
FROM drv_rule_outcome
WHERE as_of_date >= CURRENT_DATE - INTERVAL '180 days'
GROUP BY rule_id, rule_kind;

-- New settings table for outcome ETL configuration
CREATE TABLE IF NOT EXISTS ref_settings (
  setting_name   text PRIMARY KEY,
  setting_value  text NOT NULL,
  description    text,
  updated_at     timestamptz DEFAULT now()
);

-- Seed default settings
INSERT INTO ref_settings (setting_name, setting_value, description)
VALUES
  ('outcome_fwd_window_5d', '5', 'Days forward for 5-day outcome window'),
  ('outcome_fwd_window_20d', '20', 'Days forward for 20-day outcome window'),
  ('outcome_hit_threshold_buy', '0.5', 'Minimum % return to count as hit for BM actions'),
  ('outcome_hit_threshold_sell', '-0.5', 'Maximum % return to count as hit for SA/STM/SS actions'),
  ('outcome_hold_threshold', '1.0', 'Maximum abs % return to count as hit for HOLD actions')
ON CONFLICT DO NOTHING;
