#!/usr/bin/env python
"""Map 41 derived indicator columns to existing drv_ma columns."""
from sqlalchemy import text
from etl.db import session_scope

# Map derived indicators to existing columns that have similar meaning
source_mappings = {
    'drv_ma.macdh_direction': 'a_macdh_d_brr',      # MACD Histogram
    'drv_ma.macd_direction': 'a_macd_brr',          # MACD
    'drv_ma.bb_direction': 'a_bb_top',              # Bollinger Band top
    'drv_ma.bbthresh_crossover': 'a_bb_streak',     # BB streak
    'drv_ma.trade_cross_over': 'a_trade_value',     # Trade value
    'drv_ma.trade_rule': 'a_trade_value',           # Trade value
    'drv_ma.trend_cross_over': 'a_trend_value',     # Trend value
    'drv_ma.trend_rule': 'a_trend_value',           # Trend value
    'drv_ma.trend_trade_dep_rule': 'a_trend_value', # Trend value
    'drv_ma.trade_trend_relation': 'a_trade_value', # Trade value
    'drv_ma.trade_trend_relation_neg': 'a_trend_value',  # Trend value
    'drv_ma.brr_pct_dir': 'pct_brr',                # BRR percentage
    'drv_ma.trend_below_trr': 'a_trend_value',      # Trend value
    'drv_ma.lrr_above_trade': 'a_trade_value',      # Trade value
    'drv_ma.ivrule': 'iv_percentile',               # IV percentile
    'drv_ma.three_m_long': 'sma_50',                # SMA 50
    'drv_ma.perf1d_sd_neg': 'd_iv_to_hv',           # IV to HV
    'drv_ma.perf_sd_rule': 'd_iv_to_hv',            # IV to HV
    'drv_ma.perf_sd_rule_neg': 'd_iv_to_hv',        # IV to HV
    'drv_ma.perf3d_rule_neg': 'range_compression',  # Range compression
    'drv_ma.bb_bull_rule': 'a_bb_bottom',           # BB bottom
    'drv_ma.bb_bull_puts': 'a_bb_top',              # BB top
    'drv_ma.macd_and_h_rule': 'a_macdh_d_brr',      # MACD Histogram
    'drv_ma.macd_and_h_rule_puts': 'a_macdh_d_brr', # MACD Histogram
    'drv_ma.overbought_neg': 'rsi',                 # RSI
    'drv_ma.outlook_3wk_neg': 'rr_outlook',         # RR outlook
    'drv_ma.outlook_3wk_days_neg': 'rr_outlook',    # RR outlook
    'drv_ma.bull_rule': 'a_trade_value',            # Trade value
    'drv_ma.bull_rule_neg': 'a_trend_value',        # Trend value
    'drv_ma.perfourbull_rule': 'a_trade_value',     # Trade value
    'drv_ma.perfourbull_rule_neg': 'a_trend_value', # Trend value
    'drv_ma.dma_50_crossover': 'sma_50',            # SMA 50
    'drv_ma.dma_200_crossover': 'sma_200',          # SMA 200
    'drv_ma.trade_close_to_brr': 'a_trade_value',   # Trade value
    'drv_ma.trade_close_to_trr': 'a_trade_value',   # Trade value
    'drv_ma.up_resistance': 'a_bb_top',              # BB top
    'drv_ma.down_resistance': 'a_bb_bottom',         # BB bottom
    'drv_ma.vs_lt_outlook_rule': 'rr_outlook',       # RR outlook
    'drv_ma.short_term_outlook_bullish': 'a_trade_value',  # Trade value
    'drv_ma.short_term_outlook_bearish': 'a_trend_value',  # Trend value
    'drv_ma.overbought': 'rsi',                      # RSI
}

print("Mappings of derived indicators to existing columns:")
print("=" * 80)

for drv_col, source_col in source_mappings.items():
    print(f"{drv_col:45s} <- {source_col}")

print(f"\nTotal: {len(source_mappings)} mappings")
