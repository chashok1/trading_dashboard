#!/usr/bin/env python
"""Map derived indicator rules to actual drv_ma column names."""
from sqlalchemy import text
from etl.db import session_scope

# Map Excel column names to drv_ma column names (with drv_ma. prefix)
mappings = {
    'MACDH Direction': 'drv_ma.macdh_direction',
    'MACD Direction': 'drv_ma.macd_direction',
    'BB Direction': 'drv_ma.bb_direction',
    'BBThresh Crossover': 'drv_ma.bbthresh_crossover',
    'Trade Cross Over': 'drv_ma.trade_cross_over',
    '!Trade Rule': 'drv_ma.trade_rule',
    'Trend Cross Over': 'drv_ma.trend_cross_over',
    '!Trend Rule': 'drv_ma.trend_rule',
    'Trend Trade Dep Rule': 'drv_ma.trend_trade_dep_rule',
    'Trade Trend Relation': 'drv_ma.trade_trend_relation',
    '!Trade Trend Relation': 'drv_ma.trade_trend_relation_neg',
    'BRR% Dir Rule': 'drv_ma.brr_pct_dir',
    'Trend below TRR': 'drv_ma.trend_below_trr',
    'LRR above Trade': 'drv_ma.lrr_above_trade',
    'IVRule': 'drv_ma.ivrule',
    '3mn Long Rule': 'drv_ma.three_m_long',
    '!Perf1D SD Rule': 'drv_ma.perf1d_sd_neg',
    'Perf SD Rule': 'drv_ma.perf_sd_rule',
    '!Perf SD Rule': 'drv_ma.perf_sd_rule_neg',
    '!Perf3D Rule': 'drv_ma.perf3d_rule_neg',
    'BB Bull Rule': 'drv_ma.bb_bull_rule',
    'BB Bull Puts': 'drv_ma.bb_bull_puts',
    'MACD and H Rule': 'drv_ma.macd_and_h_rule',
    'MACD and H Rule Puts': 'drv_ma.macd_and_h_rule_puts',
    '!Overbought': 'drv_ma.overbought_neg',
    '!3wk Outlook': 'drv_ma.outlook_3wk_neg',
    '!3wk Outlook Days': 'drv_ma.outlook_3wk_days_neg',
    'Bull Rule': 'drv_ma.bull_rule',
    '!Bull Rule': 'drv_ma.bull_rule_neg',
    'PerfOrBull Rule': 'drv_ma.perfourbull_rule',
    '!PerfOrBull Rule': 'drv_ma.perfourbull_rule_neg',
    '50-DMA-Crossover': 'drv_ma.dma_50_crossover',
    '200-DMA-Crossover': 'drv_ma.dma_200_crossover',
    'Trade Close to BRR': 'drv_ma.trade_close_to_brr',
    'Trade Close to TRR': 'drv_ma.trade_close_to_trr',
    'Up Resistance': 'drv_ma.up_resistance',
    'Down Resistance': 'drv_ma.down_resistance',
    'VS LT Outlook Rule': 'drv_ma.vs_lt_outlook_rule',
    'Short Term Oulook (If LT Bullish)': 'drv_ma.short_term_outlook_bullish',
    'Short Term Oulook (If LT Bearish)': 'drv_ma.short_term_outlook_bearish',
    'Overbought': 'drv_ma.overbought',
}

with session_scope() as s:
    updated = 0
    for rule_name, ma_col in mappings.items():
        result = s.execute(text("""
            UPDATE ref_trig_atomic_rule
            SET ma_column_name = :col
            WHERE rule_name = :name AND deprecated_at IS NULL AND brkeout_from IS NULL
        """), {"col": ma_col, "name": rule_name})

        if result.rowcount > 0:
            updated += 1
            print(f"  {rule_name:45s} -> {ma_col}")

    s.commit()
    print(f"\nUpdated {updated} derived indicator mappings to drv_ma columns")
