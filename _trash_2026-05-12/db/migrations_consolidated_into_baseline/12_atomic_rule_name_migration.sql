-- ============================================================
-- Atomic Rule Name Migration
-- Splits ma_column_name: description → rule_name, drv_ma column reference → ma_column_name
-- ============================================================

-- Add rule_name column to store the description (previously in ma_column_name)
ALTER TABLE ref_trig_atomic_rule
  ADD COLUMN IF NOT EXISTS rule_name TEXT;

-- Copy current ma_column_name values to rule_name
UPDATE ref_trig_atomic_rule
SET rule_name = ma_column_name
WHERE rule_name IS NULL AND ma_column_name IS NOT NULL;

-- Update ma_column_name with actual drv_ma column references using the mapping
-- This mapping comes from _MA_COL_MAP in etl/derive.py
UPDATE ref_trig_atomic_rule
SET ma_column_name = 'drv_ma.' || column_map.drv_col
FROM (
  VALUES
    ('MACDH Direction', 'a_macdh_d_brr'),
    ('MACD Direction', 'a_macd_brr'),
    ('MACD Rule', 'a_macd_brr'),
    ('MACDH Rule', 'a_macdh_d_brr'),
    ('MACDH Days', 'a_macdh_d_brr'),
    ('MACDH Days2', 'a_macdh_d_brr'),
    ('MACD_BRR Puts', 'a_macd_brr'),
    ('MACDH_BRR Puts', 'a_macdh_d_brr'),
    ('BB Direction', 'a_bb_streak'),
    ('BBThresh Crossover', 'a_bb_streak'),
    ('BBThresh CO Days', 'a_bb_streak'),
    ('BBThresh CO Days2', 'a_bb_streak'),
    ('BBStreak Rule', 'a_bb_streak'),
    ('BBStreak Rule1', 'a_bb_streak'),
    ('BBStreak Rule2', 'a_bb_streak'),
    ('BBStreak Days Rule', 'a_bb_streak'),
    ('BBStreak Days Rule2', 'a_bb_streak'),
    ('BBStreak Days Up Rule', 'a_bb_streak'),
    ('BBStreak Days Up Rule2', 'a_bb_streak'),
    ('BBHighDays', 'a_bb_streak'),
    ('BBLowDays', 'a_bb_streak'),
    ('BBHighLow Days Rule', 'a_bb_streak'),
    ('BBHighLow_SD Rule', 'a_bb_streak'),
    ('Trade Cross Over', 'pct_brr'),
    ('RSI', 'rsi'),
    ('RSI Rule', 'rsi'),
    ('RSI Top', 'rsi'),
    ('RSI Puts', 'rsi'),
    ('Overbought', 'rsi'),
    ('IV', 'imp_volatility'),
    ('IVPercentile', 'iv_percentile'),
    ('IVPercentile Puts', 'iv_percentile'),
    ('IVAbsolute', 'imp_volatility'),
    ('HVPercentile', 'hv_percentile'),
    ('HVPercentile Puts', 'hv_percentile'),
    ('HVAbsolute', 'range_compression'),
    ('IVHV Rule (modified)', 'd_iv_to_hv'),
    ('IVHV Puts (modified)', 'd_iv_to_hv'),
    ('TrendValue', 'a_trend_value'),
    ('TradeValue', 'a_trade_value'),
    ('Trend-Rule', 'a_trend_value'),
    ('Trade-Rule', 'a_trade_value'),
    ('Trade Trend SD Rule', 'a_trend_value'),
    ('BB Top', 'a_bb_top'),
    ('BB Bottom', 'a_bb_bottom'),
    ('BRR', 'rr_brr'),
    ('BRR% Rule', 'pct_brr'),
    ('BRR% LRR', 'pct_brr'),
    ('BRR% LRR2', 'pct_brr'),
    ('BRR% R2', 'pct_brr'),
    ('BRR% TRR', 'pct_brr'),
    ('BRR% TRR Puts', 'pct_brr'),
    ('BRR% Puts', 'pct_brr'),
    ('Last', 'last_price'),
    ('Last Price', 'last_price'),
    ('Current Price Rule', 'last_price'),
    ('Earnings Days', 'earnings_days'),
    ('Volume', 'volume'),
    ('Current Volume Rule', 'vlm_projected'),
    ('High above TRR', 'a_trade_value'),
    ('Low below LRR', 'a_trend_value'),
    ('52-Wk High Rule', 'sma_200'),
    ('52-Wk Low Rule', 'sma_200'),
    ('200-DMA-Rule', 'sma_200'),
    ('50-DMA-Rule', 'sma_50'),
    ('3m-High-Rule', 'sma_200'),
    ('3m-Low-Rule', 'sma_200'),
    ('3mn-High-Rule', 'sma_200'),
    ('3mn-Low-Rule', 'sma_200'),
    ('3mn-High-Dyas Rule', 'sma_200'),
    ('3wk Outlook', 'a_macd_brr'),
    ('3wk Outlook Days', 'a_macd_brr'),
    ('3m-Low-Days Rule', 'a_bb_streak'),
    ('3mn Outlook', 'a_macd_brr'),
    ('3mn Outlook Days', 'a_macd_brr'),
    ('Perf1D SD Rule', 'last_price'),
    ('Perf2wk SD Rule', 'volume'),
    ('Perf2M SD Rule', 'volume'),
    ('Perf3D SD Rule', 'range_compression'),
    ('Perf3D 1Off Rule', 'range_compression'),
    ('Perf3wk SD Rule', 'range_compression'),
    ('Perf3mn SD Rule', 'range_compression'),
    ('LRR_Idx', 'a_trend_value'),
    ('MRR_Idx', 'a_trade_value'),
    ('TRR_Idx', 'a_bb_top'),
    ('Short Term Oulook (If LT Bearish)', 'a_macd_brr'),
    ('Short Term Oulook (If LT Bullish)', 'a_macd_brr'),
    ('VS Days', 'earnings_days'),
    ('VS LT Outlook Rule', 'a_macd_brr'),
    ('VS Price Rule', 'last_price'),
    ('VS Volatility Rule', 'iv_percentile'),
    ('VS Volume Spike Rule', 'volume')
) column_map(rule_name_val, drv_col)
WHERE ref_trig_atomic_rule.rule_name = column_map.rule_name_val;
