#!/usr/bin/env python
"""Update derived indicator mappings to actual drv_ma columns."""
from sqlalchemy import text
from etl.db import session_scope

# Map derived indicator names to actual drv_ma columns
correct_mappings = {
    'MACDH Direction': 'a_macdh_d_brr',
    'MACD Direction': 'a_macd_brr',
    'BB Direction': 'a_bb_top',
    'BBThresh Crossover': 'a_bb_streak',
    'Trade Cross Over': 'a_trade_value',
    '!Trade Rule': 'a_trade_value',
    'Trend Cross Over': 'a_trend_value',
    '!Trend Rule': 'a_trend_value',
    'Trend Trade Dep Rule': 'a_trend_value',
    'Trade Trend Relation': 'a_trade_value',
    '!Trade Trend Relation': 'a_trade_value',
    'BRR% Dir Rule': 'pct_brr',
    'Trend below TRR': 'a_trend_value',
    'LRR above Trade': 'a_trade_value',
    'IVRule': 'iv_percentile',
    '3mn Long Rule': 'sma_50',
    '!Perf1D SD Rule': 'd_iv_to_hv',
    'Perf SD Rule': 'd_iv_to_hv',
    '!Perf SD Rule': 'd_iv_to_hv',
    '!Perf3D Rule': 'range_compression',
    'BB Bull Rule': 'a_bb_bottom',
    'BB Bull Puts': 'a_bb_top',
    'MACD and H Rule': 'a_macdh_d_brr',
    'MACD and H Rule Puts': 'a_macdh_d_brr',
    '!Overbought': 'rsi',
    '!3wk Outlook': 'rr_outlook',
    '!3wk Outlook Days': 'rr_outlook',
    'Bull Rule': 'a_trade_value',
    '!Bull Rule': 'a_trend_value',
    'PerfOrBull Rule': 'a_trade_value',
    '!PerfOrBull Rule': 'a_trend_value',
    '50-DMA-Crossover': 'sma_50',
    '200-DMA-Crossover': 'sma_200',
    'Trade Close to BRR': 'a_trade_value',
    'Trade Close to TRR': 'a_trade_value',
    'Up Resistance': 'a_bb_top',
    'Down Resistance': 'a_bb_bottom',
    'VS LT Outlook Rule': 'rr_outlook',
    'Short Term Oulook (If LT Bullish)': 'a_trade_value',
    'Short Term Oulook (If LT Bearish)': 'a_trend_value',
    'Overbought': 'rsi',
}

with session_scope() as s:
    updated = 0
    for rule_name, ma_col in correct_mappings.items():
        result = s.execute(text("""
            UPDATE ref_trig_atomic_rule
            SET ma_column_name = :col
            WHERE rule_name = :name AND deprecated_at IS NULL AND brkeout_from IS NULL
        """), {"col": ma_col, "name": rule_name})

        if result.rowcount > 0:
            updated += 1
            print(f"  {rule_name:45s} -> {ma_col}")

    s.commit()
    print(f"\nUpdated {updated} derived indicator column mappings")
