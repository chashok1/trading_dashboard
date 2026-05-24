-- =============================================================================
-- ROLLED BACK 2026-05-10
--
-- This file previously added 113 atomic-input columns (JG..NO range from MA tab)
-- to the drv_ma table.  That was an anti-goal violation: the design called for
-- those columns to live in drv_cat_atomic_input only, NOT in drv_ma.
--
-- Worse, _derive_ma_impl never INSERTed into the new columns, so they were
-- guaranteed-NULL dead schema.  See verification report B2 (2026-05-10).
--
-- The columns are dropped here so future schema diffs don't show phantom
-- columns.  drv_cat_atomic_input (created by 14_drv_cat_tables.sql from the
-- ref_ma_columns registry) is the canonical home.
-- =============================================================================

DO $$
DECLARE
    cols TEXT[] := ARRAY[
        'bb_threshold','bbthresh_co_days','bbthresh_co_days2',
        'trade_rule','trend_rule','trtn_relation','not_trtn_relation','trade_trend_sd_rule',
        'brrpct_rule','brrpct_lrr','brrpct_r2','brrpct_lrr2','brrpct_trr',
        'brrpct_puts','brrpct_trr_puts','brrpct_dir',
        'high_trr','low_lrr','trr_idx','mrr_idx','lrr_idx',
        'hvabsolute','ivabsolute','ivpercentile','ivpercentile_puts',
        'hvpercentile','hvpercentile_puts','ivhv','ivhv_puts',
        'rsi_rule','rsi_top','rsi_puts',
        '3m_low_rule','3m_low_days_rule','3mn_high_rule','3mn_high_days_rule','3m_long',
        'perf3mn_sd_rule','perf2m_sd_rule','perf3wk_sd_rule','perf2wk_sd_rule',
        'perf3d_sd_rule','perf1d_sd_rule','not_perf1d_sd','perf3d_sd_1off',
        'bbhighlow_sd_rule','bbhighlow_days_rule',
        'bbstreak_rule','bbstreakrule1','bbstreak_rule2','bbstreak_days_rule',
        'bbstreak_days_rule2','bbstreak_days_rule3','bbstreak_days_rule4',
        'bbhighdays','bblowdays',
        'macd_rule','macdh_rule','macd_brr_puts','macdh_brr_puts','macdh_days','macdh_days2',
        '3mn_outlook','3mn_outlook_days','3wk_outlook','3wk_outlook_days',
        'not_3wk_ol','not_3wk_ol_days','bull','not_bull','perforbull','not_perforbull',
        '50_dma_rule','50_dma_crossover','200_dma_rule','200_dma_crossover',
        '52_wk_low_rule','52_wk_high_rule','brrtrade','trrtrade','earnings',
        'vs_price','vs_volume_spike','vs_volatility','vs_days',
        'current_price_sd_rule','current_volume_rule','current_volatility_rule',
        'short_term_oulook_if_lt_bullish','short_term_oulook_if_lt_bearish'
    ];
    c TEXT;
BEGIN
    FOREACH c IN ARRAY cols LOOP
        EXECUTE format('ALTER TABLE drv_ma DROP COLUMN IF EXISTS %I', c);
    END LOOP;
END $$;
