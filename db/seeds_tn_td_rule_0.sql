-- 2026-10-23: tn_td_rule code 0 = "below Trade by up to 1 SD, rising, above Trend, above the lowest of the last 5 Trade values" -> BUY SOME.
-- refresh_ref's Parm refresh wipes ref_param_lookup, so re-run `python -m db.init_db` (or this file) after a Parm refresh. Idempotent.
INSERT INTO ref_param_lookup (table_name, code, short_name, action, seq, description)
VALUES ('tn_td_rule', '0', '>Tn~Td', 'BS', 9, 'Above trend, a little below trade but rising: buy some')
ON CONFLICT (table_name, code) DO NOTHING;

-- 2026-10-23: code 5 = same dip, but MACDH not rising -> neutral (no Technical signal).
INSERT INTO ref_param_lookup (table_name, code, short_name, action, seq, description)
VALUES ('tn_td_rule', '5', '>Tn~Td N', 'N', 0, 'Above trend, a little below trade, up day but MACDH not rising: neutral')
ON CONFLICT (table_name, code) DO NOTHING;
