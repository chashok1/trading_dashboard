-- =============================================================================
-- fix_source_expr_typos.sql
-- One-shot mechanical renames for ref_ma_columns.source_expr where the column
-- name in the registry doesn't match the actual drv_*/hist_* schema.
--
-- Run after `python -m etl.execute_build` to repair Excel-derived column
-- names that snake-cased differently from how the schema spells them.
--
-- Idempotent — safe to re-run.
--
--   psql -h localhost -p 5432 -U postgres -d trading -f db/fix_source_expr_typos.sql
-- =============================================================================

-- \echo '=== Before ==='   (psql meta-command — comment out for psycopg)
SELECT COUNT(*) AS total,
       COUNT(*) FILTER (WHERE source_expr IS NOT NULL AND source_expr <> '') AS with_expr
FROM ref_ma_columns;

-- ----------------------------------------------------------------------------
-- TD column renames (drv_td / hist_td)
-- ----------------------------------------------------------------------------
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'td.a_bbhighlow', 'td.a_bb_high_low')          WHERE source_expr LIKE '%td.a_bbhighlow%';
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'td.a_trendvalue', 'td.a_trend_value')         WHERE source_expr LIKE '%td.a_trendvalue%';
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'td.a_tradevalue', 'td.a_trade_value')         WHERE source_expr LIKE '%td.a_tradevalue%';

-- ----------------------------------------------------------------------------
-- TW column renames (drv_tw / hist_tw)
-- ----------------------------------------------------------------------------
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'tw.standarddeviation', 'tw.standard_dev')     WHERE source_expr LIKE '%tw.standarddeviation%';
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'tw.a_perf2m',  'tw.a_perf_2m')                WHERE source_expr LIKE '%tw.a_perf2m%';
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'tw.a_perf2wk', 'tw.a_perf_2wk')               WHERE source_expr LIKE '%tw.a_perf2wk%';
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'tw.a_perf3d',  'tw.a_perf_3d')                WHERE source_expr LIKE '%tw.a_perf3d%';
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'tw.a_volumespike', 'tw.a_volume_spike')       WHERE source_expr LIKE '%tw.a_volumespike%';
-- a_macd_brr -> a_macd_brr1 (only if not already a number suffix)
UPDATE ref_ma_columns SET source_expr = REGEXP_REPLACE(source_expr, 'tw\.a_macd_brr(\W|$)', 'tw.a_macd_brr1\1', 'g')
   WHERE source_expr ~ 'tw\.a_macd_brr(\W|$)';
UPDATE ref_ma_columns SET source_expr = REGEXP_REPLACE(source_expr, 'tw\.a_macdh_d_brr(\W|$)', 'tw.a_macdh_d_brr1\1', 'g')
   WHERE source_expr ~ 'tw\.a_macdh_d_brr(\W|$)';
-- 20_dma / 50_dma / 200_dma -> sma_20 / sma_50 / sma_200
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'tw."20_dma"',  'tw.sma_20')   WHERE source_expr LIKE '%tw."20_dma"%';
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'tw.20_dma',    'tw.sma_20')   WHERE source_expr LIKE '%tw.20_dma%';
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'tw."50_dma"',  'tw.sma_50')   WHERE source_expr LIKE '%tw."50_dma"%';
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'tw.50_dma',    'tw.sma_50')   WHERE source_expr LIKE '%tw.50_dma%';
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'tw."200_dma"', 'tw.sma_200')  WHERE source_expr LIKE '%tw."200_dma"%';
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'tw.200_dma',   'tw.sma_200')  WHERE source_expr LIKE '%tw.200_dma%';
-- fcf -> fcf_per_share (avoid double-rename)
UPDATE ref_ma_columns SET source_expr = REGEXP_REPLACE(source_expr, 'tw\.fcf(\W|$)', 'tw.fcf_per_share\1', 'g')
   WHERE source_expr ~ 'tw\.fcf(\W|$)' AND source_expr NOT LIKE '%fcf_per_share%';

-- ----------------------------------------------------------------------------
-- TO column renames (hist_to)
-- ----------------------------------------------------------------------------
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, '"to".price_earnings_ratio_current',  '"to".pe_ratio')   WHERE source_expr LIKE '%price_earnings_ratio_current%';
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, '"to".price_book_value_ratio_current','"to".pb_ratio')   WHERE source_expr LIKE '%price_book_value_ratio_current%';
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, '"to".price_/_earnings_ratio_current','"to".pe_ratio')   WHERE source_expr LIKE '%price_/_earnings_ratio_current%';
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, '"to".price_/_book_value_ratio_current','"to".pb_ratio') WHERE source_expr LIKE '%price_/_book_value_ratio_current%';
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, '"to".long_term_debt_to_capital_current_ltm', '"to".ltd_to_capital') WHERE source_expr LIKE '%long_term_debt_to_capital_current_ltm%';
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, '"to".return_on_equity_roe_current_ltm',     '"to".roe')           WHERE source_expr LIKE '%return_on_equity_roe_current_ltm%';
-- market_cap -> market_cap_num (numeric form; market_cap_str is the text form)
UPDATE ref_ma_columns SET source_expr = REGEXP_REPLACE(source_expr, '"to"\.market_cap(\W|$)', '"to".market_cap_num\1', 'g')
   WHERE source_expr ~ '"to"\.market_cap(\W|$)' AND source_expr NOT LIKE '%market_cap_num%' AND source_expr NOT LIKE '%market_cap_str%';

-- ----------------------------------------------------------------------------
-- Call column renames (hist_call)
-- ----------------------------------------------------------------------------
-- 'hcall.call' is ambiguous; the schema column is 'outlook'
UPDATE ref_ma_columns SET source_expr = REGEXP_REPLACE(source_expr, 'hcall\.call(\W|$)', 'hcall.outlook\1', 'g')
   WHERE source_expr ~ 'hcall\.call(\W|$)' AND source_expr NOT LIKE '%call_modifier%' AND source_expr NOT LIKE '%call_entry%' AND source_expr NOT LIKE '%call_cont%';
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'hcall.call_modifier', 'hcall.outlook_modifier') WHERE source_expr LIKE '%hcall.call_modifier%';

-- ----------------------------------------------------------------------------
-- Holdings (hist_f / hist_cs use 'qty', not 'quantity')
-- ----------------------------------------------------------------------------
UPDATE ref_ma_columns SET source_expr = REGEXP_REPLACE(source_expr, '\bquantity\b', 'qty', 'g')
   WHERE source_expr ~ '\bquantity\b';

-- ----------------------------------------------------------------------------
-- Risk Range (hist_rr has snapshot_date, not rr_date)
-- ----------------------------------------------------------------------------
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'rr.rr_date', 'rr.snapshot_date') WHERE source_expr LIKE '%rr.rr_date%';

-- ----------------------------------------------------------------------------
-- Round 2 fixes (uncovered after the first round of derives)
-- ----------------------------------------------------------------------------

-- TD: a_bb_high_lowdays should be a_bb_high_low_days (extra underscore)
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'td.a_bb_high_lowdays', 'td.a_bb_high_low_days')
   WHERE source_expr LIKE '%td.a_bb_high_lowdays%';

-- TO: '/' in column name (price_/_earnings_ratio_current) -> pe_ratio
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, '"to"."price_/_earnings_ratio_current"', '"to".pe_ratio')
   WHERE source_expr LIKE '%price_/_earnings_ratio_current%';
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, '"to"."price_/_book_value_ratio_current"', '"to".pb_ratio')
   WHERE source_expr LIKE '%price_/_book_value_ratio_current%';

-- TO: div_yield_current -> div_yield
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, '"to".div_yield_current', '"to".div_yield')
   WHERE source_expr LIKE '%div_yield_current%';

-- TW more 'c_' prefixed cols (legacy snake casing)
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'tw.c_20_dma',  'tw.sma_20')   WHERE source_expr LIKE '%tw.c_20_dma%';
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'tw.c_50_dma',  'tw.sma_50')   WHERE source_expr LIKE '%tw.c_50_dma%';
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'tw.c_200_dma', 'tw.sma_200')  WHERE source_expr LIKE '%tw.c_200_dma%';
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'tw.c_52low',   'tw.low_52')   WHERE source_expr LIKE '%tw.c_52low%';
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'tw.c_52high',  'tw.high_52')  WHERE source_expr LIKE '%tw.c_52high%';
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'tw.a_3mnlow',  'tw.a_3mn_low')  WHERE source_expr LIKE '%tw.a_3mnlow%';
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'tw.a_3mnhigh', 'tw.a_3mn_high') WHERE source_expr LIKE '%tw.a_3mnhigh%';

-- TL: l_vlm doesn't exist; the column is `volume`
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'tl.l_vlm', 'tl.volume') WHERE source_expr LIKE '%tl.l_vlm%';

-- RR: 'rr.rr' -> 'rr.brr' (the derived column for buy/sell trade)
UPDATE ref_ma_columns SET source_expr = REGEXP_REPLACE(source_expr, 'rr\.rr(\W|$)', 'rr.brr\1', 'g')
   WHERE source_expr ~ 'rr\.rr(\W|$)';
-- rr.rr_entry -> rr.entry
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'rr.rr_entry', 'rr.entry')         WHERE source_expr LIKE '%rr.rr_entry%';
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'rr.rr_cont',  'rr.cont')          WHERE source_expr LIKE '%rr.rr_cont%';
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'rr.rr_modifier', 'rr.modifier')   WHERE source_expr LIKE '%rr.rr_modifier%';
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'rr.rr_outlook',  'rr.outlook')    WHERE source_expr LIKE '%rr.rr_outlook%';

-- ----------------------------------------------------------------------------
-- Round 3 fixes
-- ----------------------------------------------------------------------------

-- TW: earningsdays -> a_earnings_days
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'tw.earningsdays', 'tw.a_earnings_days')
   WHERE source_expr LIKE '%tw.earningsdays%';

-- TW: 52low / 52high -> low_52 / high_52
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'tw."52low"',  'tw.low_52')   WHERE source_expr LIKE '%tw."52low"%';
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'tw.52low',    'tw.low_52')   WHERE source_expr LIKE '%tw.52low%';
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'tw."52high"', 'tw.high_52')  WHERE source_expr LIKE '%tw."52high"%';
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'tw.52high',   'tw.high_52')  WHERE source_expr LIKE '%tw.52high%';

-- TW: a_3mn_highlow -> a_3mn_high_low
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'tw.a_3mn_highlow', 'tw.a_3mn_high_low') WHERE source_expr LIKE '%tw.a_3mn_highlow%';

-- TW: w_vlm -> volume
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'tw.w_vlm', 'tw.volume') WHERE source_expr LIKE '%tw.w_vlm%';

-- Y: y.float -> y.float_str
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'y.float ', 'y.float_str ')   WHERE source_expr LIKE '%y.float %';
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'y.float,', 'y.float_str,')   WHERE source_expr LIKE '%y.float,%';
UPDATE ref_ma_columns SET source_expr = REGEXP_REPLACE(source_expr, 'y\.float$', 'y.float_str')   WHERE source_expr ~ 'y\.float$';

-- Source-tab '_date' renames -> snapshot_date
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'cs.cs_date',     'cs.snapshot_date')     WHERE source_expr LIKE '%cs.cs_date%';
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'ii.ii_date',     'ii.snapshot_date')     WHERE source_expr LIKE '%ii.ii_date%';
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'hssh.ssh_date',  'hssh.snapshot_date')   WHERE source_expr LIKE '%hssh.ssh_date%';

-- ----------------------------------------------------------------------------
-- NULL out source_expr for columns that genuinely don't exist anywhere.
-- (Uses LIKE — Postgres regex uses \y for word boundaries, not \b. The earlier
-- attempt with \b matched literal BACKSPACE chars and silently did nothing.)
-- ----------------------------------------------------------------------------
UPDATE ref_ma_columns SET source_expr = NULL WHERE source_expr LIKE '%.call_entry%';
UPDATE ref_ma_columns SET source_expr = NULL WHERE source_expr LIKE '%.call_cont%';
UPDATE ref_ma_columns SET source_expr = NULL WHERE source_expr LIKE '%.etf_bottom%';
UPDATE ref_ma_columns SET source_expr = NULL WHERE source_expr LIKE '%.etf_top%';
UPDATE ref_ma_columns SET source_expr = NULL WHERE source_expr LIKE '%.d_rsi%';
UPDATE ref_ma_columns SET source_expr = NULL WHERE source_expr LIKE '%.d_vlt_rulecode%';
UPDATE ref_ma_columns SET source_expr = NULL WHERE source_expr LIKE '%.d_vlt_caution%';
UPDATE ref_ma_columns SET source_expr = NULL WHERE source_expr LIKE '%.d_vlt_ruledesc%';
UPDATE ref_ma_columns SET source_expr = NULL WHERE source_expr LIKE '%.d_vlt_ruleaction%';
UPDATE ref_ma_columns SET source_expr = NULL WHERE source_expr LIKE '%.tntdmax%';
UPDATE ref_ma_columns SET source_expr = NULL WHERE source_expr LIKE '%.bb_bot_prev%';
UPDATE ref_ma_columns SET source_expr = NULL WHERE source_expr LIKE '%.bb_top_prev%';

-- Type-mismatch fix: NULL out rr_date (target col is NUMERIC, source is DATE)
-- and any other date columns we mapped through that don't fit the target type.
UPDATE ref_ma_columns SET source_expr = NULL
WHERE column_name = 'rr_date' AND source_expr LIKE '%snapshot_date%';

-- ----------------------------------------------------------------------------
-- Round 4 fixes
-- ----------------------------------------------------------------------------

-- II: 'ii.ii' is the outlook column on hist_ii
UPDATE ref_ma_columns SET source_expr = REGEXP_REPLACE(source_expr, 'ii\.ii(\W|$)', 'ii.outlook\1', 'g')
   WHERE source_expr ~ 'ii\.ii(\W|$)';

-- Y: shares_out -> shares_out_str
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'y.shares_out ', 'y.shares_out_str ') WHERE source_expr LIKE '%y.shares_out %';
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'y.shares_out,', 'y.shares_out_str,') WHERE source_expr LIKE '%y.shares_out,%';
UPDATE ref_ma_columns SET source_expr = REGEXP_REPLACE(source_expr, 'y\.shares_out$', 'y.shares_out_str') WHERE source_expr ~ 'y\.shares_out$';

-- Call: call_date -> hcall.snapshot_date
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'hcall.call_date', 'hcall.snapshot_date') WHERE source_expr LIKE '%hcall.call_date%';

-- TW: a_3wkhighlow -> a_3wk_high_low
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'tw.a_3wkhighlow', 'tw.a_3wk_high_low') WHERE source_expr LIKE '%tw.a_3wkhighlow%';

-- TW: volumerateofchange -> volume_rate_change
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'tw.volumerateofchange', 'tw.volume_rate_change') WHERE source_expr LIKE '%tw.volumerateofchange%';

-- NULL out columns that the holdings subqueries can't expose. The hist_f /
-- hist_cs JOIN aliases (`fid`, `cs`) come from a GROUPed subquery that only
-- exposes `symbol` and `held_qty_*` — referencing fid.fh_date or cs.snapshot_date
-- from outside is impossible. Drop those mappings until a richer subquery is
-- defined in ma_codegen.JOIN_PATTERNS.
UPDATE ref_ma_columns SET source_expr = NULL WHERE source_expr LIKE '%fid.fh_date%';
UPDATE ref_ma_columns SET source_expr = NULL WHERE source_expr LIKE '%cs.snapshot_date%' AND source_table = 'hist_cs';
UPDATE ref_ma_columns SET source_expr = NULL WHERE source_expr LIKE '%cs.cs_date%';
UPDATE ref_ma_columns SET source_expr = NULL WHERE source_expr LIKE '%fid.snapshot_date%';

-- More NULLs for columns that don't exist:
UPDATE ref_ma_columns SET source_expr = NULL WHERE source_expr LIKE '%td.bb_bot_15d%';
UPDATE ref_ma_columns SET source_expr = NULL WHERE source_expr LIKE '%td.bb_top_15d%';
UPDATE ref_ma_columns SET source_expr = NULL WHERE source_expr LIKE '%td.d_iv%';
UPDATE ref_ma_columns SET source_expr = NULL WHERE source_expr LIKE '%td.d_hv%';

-- Type-mismatch: rr.entry is TEXT but target column rr_entry is NUMERIC
UPDATE ref_ma_columns SET source_expr = NULL
WHERE column_name = 'rr_entry' AND source_expr LIKE '%rr.entry%';
UPDATE ref_ma_columns SET source_expr = NULL
WHERE column_name = 'rr_cont' AND source_expr LIKE '%rr.cont%';

-- ----------------------------------------------------------------------------
-- Round 5 fixes
-- ----------------------------------------------------------------------------

-- TL: l_rsi -> rsi (TL only has 'rsi', not 'l_rsi')
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'tl.l_rsi', 'tl.rsi') WHERE source_expr LIKE '%tl.l_rsi%';
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'tl.l_impvolatility', 'tl.imp_volatility') WHERE source_expr LIKE '%tl.l_impvolatility%';

-- TW: w_avg_vlm_10day -> volume_avg_10d  (similar pattern: w_avg_vlm_3mo -> volume_avg_3m)
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'tw.w_avg_vlm_10day', 'tw.volume_avg_10d') WHERE source_expr LIKE '%tw.w_avg_vlm_10day%';
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'tw.w_avg_vlm_3mo',   'tw.volume_avg_3m')  WHERE source_expr LIKE '%tw.w_avg_vlm_3mo%';

-- More NULLs for non-existent columns (pattern: bb_bot_Nd / bb_top_Nd)
UPDATE ref_ma_columns SET source_expr = NULL WHERE source_expr ~ '\.bb_bot_[0-9]+d';
UPDATE ref_ma_columns SET source_expr = NULL WHERE source_expr ~ '\.bb_top_[0-9]+d';
UPDATE ref_ma_columns SET source_expr = NULL WHERE source_expr LIKE '%td.d_last%';
UPDATE ref_ma_columns SET source_expr = NULL WHERE source_expr LIKE '%ii.ii_entry%';
UPDATE ref_ma_columns SET source_expr = NULL WHERE source_expr LIKE '%ii.ii_cont%';

-- Type mismatches: NULL out where text-type source maps to numeric-type target
UPDATE ref_ma_columns SET source_expr = NULL
WHERE column_name = 'ii' AND source_expr LIKE '%ii.outlook%';
UPDATE ref_ma_columns SET source_expr = NULL
WHERE column_name = 'float' AND source_expr LIKE '%y.float_str%';
UPDATE ref_ma_columns SET source_expr = NULL
WHERE column_name = 'ssh_date' AND source_expr LIKE '%hssh.snapshot_date%';

-- ----------------------------------------------------------------------------
-- BLANKET CLEANUP — anything still using a known-bad source column gets NULL'd.
-- This is more aggressive than the surgical fixes above. It catches anything
-- the column-by-column passes missed. Add new patterns to this list as they
-- surface in derive logs.
-- ----------------------------------------------------------------------------
UPDATE ref_ma_columns SET source_expr = NULL WHERE source_expr ~ '(?i)\.(bb_bot_prev|bb_top_prev|bb_bot_7d|bb_top_7d|bb_bot_15d|bb_top_15d|d_rsi|d_iv|d_hv|d_last|d_pctchange|d_vlt_(rulecode|ruleaction|ruledesc|caution)|tntdmax|call_entry|call_cont|call_date|etf_bottom|etf_top|fh_date|cs_date|ssh_date|ii_entry|ii_cont|fcf$)';

-- ----------------------------------------------------------------------------
-- Round 6 fixes
-- ----------------------------------------------------------------------------

-- TW: w_avg_vlm_3m -> volume_avg_3m (the "_3m" form, distinct from the "_3mo" we already handled)
UPDATE ref_ma_columns SET source_expr = REGEXP_REPLACE(source_expr, 'tw\.w_avg_vlm_3m(\W|$)', 'tw.volume_avg_3m\1', 'g')
   WHERE source_expr ~ 'tw\.w_avg_vlm_3m(\W|$)';

-- TL: imp_volatility column doesn't exist on either hist_tl or drv_tl directly.
-- hist_tl has imp_volatility_raw; drv_tl has imp_volatility_clean.
-- Map any remaining tl.imp_volatility -> tl.imp_volatility_raw for now.
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'tl.imp_volatility ', 'tl.imp_volatility_raw ') WHERE source_expr LIKE '%tl.imp_volatility %';
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'tl.imp_volatility,', 'tl.imp_volatility_raw,') WHERE source_expr LIKE '%tl.imp_volatility,%';
UPDATE ref_ma_columns SET source_expr = REGEXP_REPLACE(source_expr, 'tl\.imp_volatility$', 'tl.imp_volatility_raw') WHERE source_expr ~ 'tl\.imp_volatility$';

-- Type mismatch fixes (TEXT source -> NUMERIC target column)
UPDATE ref_ma_columns SET source_expr = NULL
WHERE column_name = 'shares_out' AND source_expr LIKE '%y.shares_out_str%';
UPDATE ref_ma_columns SET source_expr = NULL
WHERE column_name = 'call' AND source_expr LIKE '%hcall.outlook%';

-- Final blanket NULL-out for any remaining d_pctchange / d_last / l_rsi-type misses
UPDATE ref_ma_columns SET source_expr = NULL WHERE source_expr LIKE '%td.d_pctchange%';
UPDATE ref_ma_columns SET source_expr = NULL WHERE source_expr LIKE '%tl.l_rsi%';

-- ----------------------------------------------------------------------------
-- Round 7 fixes (last batch — all NULL-outs)
-- ----------------------------------------------------------------------------

-- Type mismatch: hcall.outlook_modifier is TEXT but call_modifier is NUMERIC
UPDATE ref_ma_columns SET source_expr = NULL
WHERE column_name = 'call_modifier' AND source_expr LIKE '%hcall.outlook_modifier%';

-- Missing columns
UPDATE ref_ma_columns SET source_expr = NULL WHERE source_expr LIKE '%td.d_net_chng%';
UPDATE ref_ma_columns SET source_expr = NULL WHERE source_expr LIKE '%tw.volume_rulecode%';
UPDATE ref_ma_columns SET source_expr = NULL WHERE source_expr LIKE '%tw.w_vlm_rulecode%';

-- Round 8 (final cleanup)
-- DATE -> NUMERIC type mismatches
UPDATE ref_ma_columns SET source_expr = NULL
WHERE column_name = 'ii_date' AND source_expr LIKE '%ii.snapshot_date%';
UPDATE ref_ma_columns SET source_expr = NULL
WHERE column_name = 'call_date' AND source_expr LIKE '%hcall.snapshot_date%';
UPDATE ref_ma_columns SET source_expr = NULL
WHERE column_name = 'etf_date' AND source_expr LIKE '%hetf.snapshot_date%';

-- d_open / d_high / d_low / d_close don't exist on drv_td or hist_td.
-- Use plain LIKE — PG's regex \b means BACKSPACE, not word boundary.
UPDATE ref_ma_columns SET source_expr = NULL WHERE source_expr LIKE '%td.d_open%';
UPDATE ref_ma_columns SET source_expr = NULL WHERE source_expr LIKE '%td.d_high%';
UPDATE ref_ma_columns SET source_expr = NULL WHERE source_expr LIKE '%td.d_low%';
UPDATE ref_ma_columns SET source_expr = NULL WHERE source_expr LIKE '%td.d_close%';

-- TL: l_last -> last_price (the actual column on hist_tl / drv_tl)
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'tl.l_last', 'tl.last_price') WHERE source_expr LIKE '%tl.l_last%';
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'tl.l_volume', 'tl.volume') WHERE source_expr LIKE '%tl.l_volume%';
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'tl.l_open', 'tl.open_price') WHERE source_expr LIKE '%tl.l_open%';
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'tl.l_high', 'tl.high_price') WHERE source_expr LIKE '%tl.l_high%';
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'tl.l_low',  'tl.low_price')  WHERE source_expr LIKE '%tl.l_low%';
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'tl.l_net_chng',   'tl.net_chng')   WHERE source_expr LIKE '%tl.l_net_chng%';
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'tl.l_change_pct', 'tl.change_pct') WHERE source_expr LIKE '%tl.l_change_pct%';
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'tl.l_pctchange',  'tl.change_pct') WHERE source_expr LIKE '%tl.l_pctchange%';

-- Final safety net: NULL out anything still pointing at tl.l_* (no idea what those columns are)
UPDATE ref_ma_columns SET source_expr = NULL WHERE source_expr LIKE '%tl.l_%' AND source_expr NOT LIKE '%tl.last_price%';

-- ----------------------------------------------------------------------------
-- Y tab — column names in hist_y don't have the 'y_' prefix the registry uses
-- ----------------------------------------------------------------------------
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'y.y_last_price',  'y.last_price')   WHERE source_expr LIKE '%y.y_last_price%';
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'y.y_change_amt',  'y.change_amt')   WHERE source_expr LIKE '%y.y_change_amt%';
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'y.y_change_pct',  'y.change_pct')   WHERE source_expr LIKE '%y.y_change_pct%';
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'y.y_open_price',  'y.open_price')   WHERE source_expr LIKE '%y.y_open_price%';
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'y.y_high_price',  'y.high_price')   WHERE source_expr LIKE '%y.y_high_price%';
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'y.y_low_price',   'y.low_price')    WHERE source_expr LIKE '%y.y_low_price%';
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'y.y_short_ratio', 'y.short_ratio')  WHERE source_expr LIKE '%y.y_short_ratio%';
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'y.y_company_name','y.company_name') WHERE source_expr LIKE '%y.y_company_name%';
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'y.y_export_date', 'y.export_date')  WHERE source_expr LIKE '%y.y_export_date%';
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, 'y.y_export_time', 'y.export_time')  WHERE source_expr LIKE '%y.y_export_time%';

-- Final safety net: NULL out anything still pointing at y.y_* (no known mapping)
UPDATE ref_ma_columns SET source_expr = NULL WHERE source_expr LIKE '%y.y_%';

-- More TO column renames (long-form names from the workbook -> short DB names)
UPDATE ref_ma_columns SET source_expr = REPLACE(source_expr, '"to".free_cash_flow_per_share_current_ltm', '"to".fcf_per_share')
   WHERE source_expr LIKE '%free_cash_flow_per_share_current_ltm%';

-- \echo '=== After ==='   (psql meta-command — comment out for psycopg)
SELECT COUNT(*) AS total,
       COUNT(*) FILTER (WHERE source_expr IS NOT NULL AND source_expr <> '') AS with_expr
FROM ref_ma_columns;

-- \echo '=== Remaining problem references (need manual review) ==='   (psql meta-command — comment out for psycopg)
SELECT column_name, source_table, source_expr
FROM ref_ma_columns
WHERE source_expr ~ '(call_entry|etf_bottom|etf_top|d_rsi|d_vlt_rulecode|d_vlt_caution|tntdmax|standarddeviation|a_perf2m|a_volumespike|a_bbhighlow|a_trendvalue|a_tradevalue)'
ORDER BY source_table, column_name;
