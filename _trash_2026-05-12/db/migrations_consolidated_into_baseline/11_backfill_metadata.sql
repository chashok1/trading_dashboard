-- ============================================================
-- Backfill metadata for Rule Engine v2
-- Tags categories, sets default scoring modes
-- ============================================================

-- Default all categories to Mixed if not set
UPDATE ref_trig_atomic_rule
SET category = 'Mixed'
WHERE category IS NULL;

-- Default all scoring modes to jump
UPDATE ref_trig_atomic_rule
SET scoring_mode = 'jump'
WHERE scoring_mode IS NULL;

-- Add default intents
UPDATE ref_trig_atomic_rule
SET intent_text = 'Trading rule evaluation'
WHERE intent_text IS NULL;

-- Backfill composite mappings with categories
UPDATE ref_trig_composite_mapping
SET category = 'Mixed'
WHERE category IS NULL;

UPDATE ref_trig_composite_mapping
SET intent_text = 'Composite rule evaluation'
WHERE intent_text IS NULL;
