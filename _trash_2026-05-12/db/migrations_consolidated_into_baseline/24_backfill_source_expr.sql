-- =============================================================================
-- 24_backfill_source_expr.sql  (regenerated 2026-05-12 after drv_* retirement)
-- Populate ref_ma_columns.source_expr for clean cross-sheet XLOOKUP
-- passthroughs. Routes through hist_* tables wherever the equivalent drv_*
-- table has been retired (drv_etf/drv_call/drv_ii/drv_ps/drv_ssl/drv_sss).
-- Only fills rows where source_expr is still NULL/empty — never overwrites.
-- Idempotent.
-- =============================================================================

BEGIN;

-- First, NULL out any source_expr values that point at retired tables so
-- the per-row UPDATEs below can re-resolve them via the new map.
UPDATE ref_ma_columns
   SET source_expr = NULL, source_table = NULL
 WHERE source_table IN ('drv_etf','drv_call','drv_ii','drv_ps','drv_ssl','drv_sss');

UPDATE ref_ma_columns SET source_expr = 'y.company_name', source_table = COALESCE(NULLIF(source_table,''), 'hist_y') WHERE column_name = 'company_name' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'tw.standard_dev', source_table = COALESCE(NULLIF(source_table,''), 'hist_tw') WHERE column_name = 'standarddeviation' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'td.a_trend_value', source_table = COALESCE(NULLIF(source_table,''), 'hist_td') WHERE column_name = 'a_trendvalue' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'td.a_trade_value', source_table = COALESCE(NULLIF(source_table,''), 'hist_td') WHERE column_name = 'a_tradevalue' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'td.a_bb_high_low', source_table = COALESCE(NULLIF(source_table,''), 'hist_td') WHERE column_name = 'a_bbhighlow' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'td.a_bb_high_low_days', source_table = COALESCE(NULLIF(source_table,''), 'hist_td') WHERE column_name = 'a_bbhighlowdays' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'td.a_bb_streak', source_table = COALESCE(NULLIF(source_table,''), 'hist_td') WHERE column_name = 'a_bb_streak' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'tw.a_3mn_low', source_table = COALESCE(NULLIF(source_table,''), 'hist_tw') WHERE column_name = 'a_3mnlow' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'tw.a_3mn_high', source_table = COALESCE(NULLIF(source_table,''), 'hist_tw') WHERE column_name = 'a_3mnhigh' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'tw.a_3mn_high_low', source_table = COALESCE(NULLIF(source_table,''), 'hist_tw') WHERE column_name = 'a_3mnhighlow' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'tw.a_3wk_high_low', source_table = COALESCE(NULLIF(source_table,''), 'hist_tw') WHERE column_name = 'a_3wkhighlow' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'tw.a_perf_2m', source_table = COALESCE(NULLIF(source_table,''), 'hist_tw') WHERE column_name = 'a_perf2m' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'tw.a_perf_2wk', source_table = COALESCE(NULLIF(source_table,''), 'hist_tw') WHERE column_name = 'a_perf2wk' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'tw.a_perf_3d', source_table = COALESCE(NULLIF(source_table,''), 'hist_tw') WHERE column_name = 'a_perf3d' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'tw.low_52', source_table = COALESCE(NULLIF(source_table,''), 'hist_tw') WHERE column_name = 'c_52low' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'tw.high_52', source_table = COALESCE(NULLIF(source_table,''), 'hist_tw') WHERE column_name = 'c_52high' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'tw.sma_20_d', source_table = COALESCE(NULLIF(source_table,''), 'drv_tw') WHERE column_name = 'c_20_dma' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'tw.sma_50_d', source_table = COALESCE(NULLIF(source_table,''), 'drv_tw') WHERE column_name = 'c_50_dma' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'tw.sma_200_d', source_table = COALESCE(NULLIF(source_table,''), 'drv_tw') WHERE column_name = 'c_200_dma' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'tw.a_macd_brr', source_table = COALESCE(NULLIF(source_table,''), 'drv_tw') WHERE column_name = 'a_macd_brr' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'tw.a_macdh_d_brr', source_table = COALESCE(NULLIF(source_table,''), 'drv_tw') WHERE column_name = 'a_macdh_d_brr' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'tw.a_macdays_streak', source_table = COALESCE(NULLIF(source_table,''), 'hist_tw') WHERE column_name = 'a_macdays_streak' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'td.last_price', source_table = COALESCE(NULLIF(source_table,''), 'hist_td') WHERE column_name = 'd_last' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'td.change_pct', source_table = COALESCE(NULLIF(source_table,''), 'hist_td') WHERE column_name = 'd_change' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'td.net_chng', source_table = COALESCE(NULLIF(source_table,''), 'hist_td') WHERE column_name = 'd_net_chng' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'td.open_price', source_table = COALESCE(NULLIF(source_table,''), 'hist_td') WHERE column_name = 'd_open' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'td.high_price', source_table = COALESCE(NULLIF(source_table,''), 'hist_td') WHERE column_name = 'd_high' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'td.low_price', source_table = COALESCE(NULLIF(source_table,''), 'hist_td') WHERE column_name = 'd_low' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'td.d_rsi', source_table = COALESCE(NULLIF(source_table,''), 'drv_td') WHERE column_name = 'd_rsi' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'td.d_iv', source_table = COALESCE(NULLIF(source_table,''), 'drv_td') WHERE column_name = 'd_iv' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'td.d_hv', source_table = COALESCE(NULLIF(source_table,''), 'drv_td') WHERE column_name = 'd_hv' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'td.hv_percentile', source_table = COALESCE(NULLIF(source_table,''), 'drv_td') WHERE column_name = 'hvpercentile' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'td.iv_percentile', source_table = COALESCE(NULLIF(source_table,''), 'drv_td') WHERE column_name = 'ivpercentile' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'tl.last_price', source_table = COALESCE(NULLIF(source_table,''), 'hist_tl') WHERE column_name = 'l_last' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'tl.net_chng', source_table = COALESCE(NULLIF(source_table,''), 'hist_tl') WHERE column_name = 'l_net_chng' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'tl.change_pct', source_table = COALESCE(NULLIF(source_table,''), 'hist_tl') WHERE column_name = 'l_change' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'tl.open_price', source_table = COALESCE(NULLIF(source_table,''), 'hist_tl') WHERE column_name = 'l_open' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'tl.high_price', source_table = COALESCE(NULLIF(source_table,''), 'hist_tl') WHERE column_name = 'l_high' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'tl.low_price', source_table = COALESCE(NULLIF(source_table,''), 'hist_tl') WHERE column_name = 'l_low' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'tl.rsi', source_table = COALESCE(NULLIF(source_table,''), 'hist_tl') WHERE column_name = 'l_rsi' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'tl.imp_volatility_clean', source_table = COALESCE(NULLIF(source_table,''), 'drv_tl') WHERE column_name = 'l_impvolatility' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'y.last_price', source_table = COALESCE(NULLIF(source_table,''), 'hist_y') WHERE column_name = 'y_last_price' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'y.change_amt', source_table = COALESCE(NULLIF(source_table,''), 'hist_y') WHERE column_name = 'y_change' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'y.open_price', source_table = COALESCE(NULLIF(source_table,''), 'hist_y') WHERE column_name = 'y_open' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'y.high_price', source_table = COALESCE(NULLIF(source_table,''), 'hist_y') WHERE column_name = 'y_high' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'y.low_price', source_table = COALESCE(NULLIF(source_table,''), 'hist_y') WHERE column_name = 'y_low' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'td.bb_bot_prev', source_table = COALESCE(NULLIF(source_table,''), 'drv_td') WHERE column_name = 'bb_bot_prev' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'td.bb_top_prev', source_table = COALESCE(NULLIF(source_table,''), 'drv_td') WHERE column_name = 'bb_top_prev' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'rr.sell_trade', source_table = COALESCE(NULLIF(source_table,''), 'hist_rr') WHERE column_name = 'rr_bottom' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'rr.buy_trade', source_table = COALESCE(NULLIF(source_table,''), 'hist_rr') WHERE column_name = 'rr_top' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'etf.recent_price', source_table = COALESCE(NULLIF(source_table,''), 'hist_etf') WHERE column_name = 'etf_bottom' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'etf.brr', source_table = COALESCE(NULLIF(source_table,''), 'hist_etf') WHERE column_name = 'etf_top' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'td.bb_bot_15d', source_table = COALESCE(NULLIF(source_table,''), 'drv_td') WHERE column_name = 'bb_bot_15d' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'td.bb_bot_7d', source_table = COALESCE(NULLIF(source_table,''), 'drv_td') WHERE column_name = 'bb_bot_7d' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'td.bb_bot_3d', source_table = COALESCE(NULLIF(source_table,''), 'drv_td') WHERE column_name = 'bb_bot_3d' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'td.bb_top_15d', source_table = COALESCE(NULLIF(source_table,''), 'drv_td') WHERE column_name = 'bb_top_15d' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'td.bb_top_7d', source_table = COALESCE(NULLIF(source_table,''), 'drv_td') WHERE column_name = 'bb_top_7d' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'td.bb_top_3d', source_table = COALESCE(NULLIF(source_table,''), 'drv_td') WHERE column_name = 'bb_top_3d' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'tw.a_volume_spike', source_table = COALESCE(NULLIF(source_table,''), 'hist_tw') WHERE column_name = 'a_volumespike' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'tl.vlm_projected', source_table = COALESCE(NULLIF(source_table,''), 'drv_tl') WHERE column_name = 'l_vlm' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'tw.w_volume', source_table = COALESCE(NULLIF(source_table,''), 'drv_tw') WHERE column_name = 'w_vlm' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'tw.volume_rate_change', source_table = COALESCE(NULLIF(source_table,''), 'hist_tw') WHERE column_name = 'volumerateofchange' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'tw.avg_vlm_10d_d', source_table = COALESCE(NULLIF(source_table,''), 'drv_tw') WHERE column_name = 'w_avg_vlm_10day' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'tw.avg_vlm_3m_d', source_table = COALESCE(NULLIF(source_table,''), 'drv_tw') WHERE column_name = 'w_avg_vlm_3m' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'tw.w_vlm_rule_desc', source_table = COALESCE(NULLIF(source_table,''), 'drv_tw') WHERE column_name = 'w_vlm_rulecode' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = '"to".beta', source_table = COALESCE(NULLIF(source_table,''), 'hist_to') WHERE column_name = 'beta' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = '"to".market_cap_str', source_table = COALESCE(NULLIF(source_table,''), 'hist_to') WHERE column_name = 'market_cap' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = '"to".ltd_to_capital', source_table = COALESCE(NULLIF(source_table,''), 'hist_to') WHERE column_name = 'long_term_debt_to_capital_current_ltm' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = '"to".pe_ratio', source_table = COALESCE(NULLIF(source_table,''), 'hist_to') WHERE column_name = 'price_earnings_ratio_current' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = '"to".pb_ratio', source_table = COALESCE(NULLIF(source_table,''), 'hist_to') WHERE column_name = 'price_book_value_ratio_current' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = '"to".roe', source_table = COALESCE(NULLIF(source_table,''), 'hist_to') WHERE column_name = 'return_on_equity_roe_current_ltm' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = '"to".eps', source_table = COALESCE(NULLIF(source_table,''), 'hist_to') WHERE column_name = 'eps' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = '"to".div_yield', source_table = COALESCE(NULLIF(source_table,''), 'hist_to') WHERE column_name = 'div_yield_current' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = '"to".sector', source_table = COALESCE(NULLIF(source_table,''), 'hist_to') WHERE column_name = 'sector' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = '"to".fcf_per_share', source_table = COALESCE(NULLIF(source_table,''), 'hist_to') WHERE column_name = 'free_cash_flow_per_share_current_ltm' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'sctr.asset_class', source_table = COALESCE(NULLIF(source_table,''), 'ref_sector') WHERE column_name = 'asset_class' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'sctr.sector', source_table = COALESCE(NULLIF(source_table,''), 'ref_sector') WHERE column_name = 'sctr_sector' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'sctr.sub_asset_class', source_table = COALESCE(NULLIF(source_table,''), 'ref_sector') WHERE column_name = 'sub_asset_class' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'sctr.industry', source_table = COALESCE(NULLIF(source_table,''), 'ref_sector') WHERE column_name = 'industry' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'tw.fcf', source_table = COALESCE(NULLIF(source_table,''), 'drv_tw') WHERE column_name = 'fcf' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'tw.earnings_days_d', source_table = COALESCE(NULLIF(source_table,''), 'drv_tw') WHERE column_name = 'earningsdays' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'y.short_ratio', source_table = COALESCE(NULLIF(source_table,''), 'hist_y') WHERE column_name = 'short_ratio' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'y.float_str', source_table = COALESCE(NULLIF(source_table,''), 'hist_y') WHERE column_name = 'float' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'y.shares_out_str', source_table = COALESCE(NULLIF(source_table,''), 'hist_y') WHERE column_name = 'shares_out' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'td.a_bb_bot_slope', source_table = COALESCE(NULLIF(source_table,''), 'hist_td') WHERE column_name = 'a_bb_bot_slope' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'td.a_bb_top_slope', source_table = COALESCE(NULLIF(source_table,''), 'hist_td') WHERE column_name = 'a_bb_top_slope' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'psrk.rank', source_table = COALESCE(NULLIF(source_table,''), 'hist_psrk') WHERE column_name = 'ps_rk' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'psrk.wk_ago', source_table = COALESCE(NULLIF(source_table,''), 'hist_psrk') WHERE column_name = 'psrk_chg' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'etfchg.outlook', source_table = COALESCE(NULLIF(source_table,''), 'hist_etfchg') WHERE column_name = 'etf' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'ii.outlook', source_table = COALESCE(NULLIF(source_table,''), 'hist_ii') WHERE column_name = 'ii' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'iichg.outlook', source_table = COALESCE(NULLIF(source_table,''), 'hist_iichg') WHERE column_name = 'ii_chg' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'call.outlook', source_table = COALESCE(NULLIF(source_table,''), 'hist_call') WHERE column_name = 'call' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'call.outlook_modifier', source_table = COALESCE(NULLIF(source_table,''), 'hist_call') WHERE column_name = 'call_modifier' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'rr.outlook', source_table = COALESCE(NULLIF(source_table,''), 'hist_rr') WHERE column_name = 'rr' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'psrk.date_added', source_table = COALESCE(NULLIF(source_table,''), 'hist_psrk') WHERE column_name = 'ps_date' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'etfchg.event_date', source_table = COALESCE(NULLIF(source_table,''), 'hist_etfchg') WHERE column_name = 'etf_date' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'iichg.event_date', source_table = COALESCE(NULLIF(source_table,''), 'hist_iichg') WHERE column_name = 'ii_date' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'call.snapshot_date', source_table = COALESCE(NULLIF(source_table,''), 'hist_call') WHERE column_name = 'call_date' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'etfchg.action', source_table = COALESCE(NULLIF(source_table,''), 'hist_etfchg') WHERE column_name = 'etf_entry' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'iichg.action', source_table = COALESCE(NULLIF(source_table,''), 'hist_iichg') WHERE column_name = 'ii_entry' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'etfchg.action', source_table = COALESCE(NULLIF(source_table,''), 'hist_etfchg') WHERE column_name = 'etf_cont' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'f.current_value', source_table = COALESCE(NULLIF(source_table,''), 'hist_f') WHERE column_name = 'fidelity' AND (source_expr IS NULL OR source_expr = '');
UPDATE ref_ma_columns SET source_expr = 'cs.market_value', source_table = COALESCE(NULLIF(source_table,''), 'hist_cs') WHERE column_name = 'cs' AND (source_expr IS NULL OR source_expr = '');

DO $$
DECLARE total INT; filled INT;
BEGIN
  SELECT COUNT(*), COUNT(*) FILTER (WHERE source_expr IS NOT NULL AND source_expr <> '')
    INTO total, filled FROM ref_ma_columns;
  RAISE NOTICE 'ref_ma_columns: % / % rows have source_expr', filled, total;
END$$;

COMMIT;