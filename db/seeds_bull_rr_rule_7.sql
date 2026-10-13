-- 2026-10-12: bull_rr_rule code 7 = "touched TRR zone, pulled back, above midpoint, TRR rising" -> BM.
-- Copies code 6's action/seq (BM). refresh_ref's Parm refresh wipes ref_param_lookup, so re-run
-- `python -m db.init_db` (or this file) after a Parm refresh. Idempotent.
INSERT INTO ref_param_lookup (table_name, code, short_name, action, seq, description)
SELECT 'bull_rr_rule', '7', short_name, action, seq, 'Touched TRR zone, pulled back, above midpoint, TRR rising'
FROM ref_param_lookup WHERE table_name = 'bull_rr_rule' AND code = '6'
ON CONFLICT (table_name, code) DO NOTHING;
