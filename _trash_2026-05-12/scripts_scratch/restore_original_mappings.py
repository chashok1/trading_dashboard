#!/usr/bin/env python
"""Restore original ma_column_name mappings from user's Excel data."""
from sqlalchemy import text
from etl.db import session_scope

# Original mappings exactly as user provided
original_mappings = [
    ('MACDH Direction', 'MACDH Direction'),
    ('MACD Direction', 'MACD Direction'),
    ('BB Direction', 'BB Direction'),
    ('BBThresh Crossover', 'BBThresh Crossover'),
    ('Trade Cross Over', 'Trade Cross Over'),
    ('!Trade Rule', '!Trade Rule'),
    ('Trend Cross Over', 'Trend Cross Over'),
    ('!Trend Rule', '!Trend Rule'),
    ('Trend Trade Dep Rule', 'Trend Trade Dep Rule'),
    ('Trade Trend Relation', 'Trade Trend Relation'),
    ('!Trade Trend Relation', '!Trade Trend Relation'),
    ('BRR% Dir Rule', 'BRR% Dir'),
    ('Trend below TRR', 'Trend below TRR'),
    ('LRR above Trade', 'LRR above Trade'),
    ('IVRule', 'IVRule'),
    ('3mn Long Rule', '3m-Long'),
    ('!Perf1D SD Rule', '!Perf1D_sd'),
    ('Perf SD Rule', 'Perf SD Rule'),
    ('!Perf SD Rule', '!Perf SD Rule'),
    ('!Perf3D Rule', '!Perf3D Rule'),
    ('BB Bull Rule', 'BB Bull Rule'),
    ('BB Bull Puts', 'BB Bull Puts'),
    ('MACD and H Rule', 'MACD and H Rule'),
    ('MACD and H Rule Puts', 'MACD and H Rule Puts'),
    ('!Overbought', '!Overbought'),
    ('!3wk Outlook', '!3wk ol'),
    ('!3wk Outlook Days', '!3wk ol days'),
    ('Bull Rule', 'BULL'),
    ('!Bull Rule', '!BULL'),
    ('PerfOrBull Rule', 'PerfOrBull'),
    ('!PerfOrBull Rule', '!PerfOrBull'),
    ('50-DMA-Crossover', '50-DMA-Crossover'),
    ('200-DMA-Crossover', '200-DMA-Crossover'),
    ('Trade Close to BRR', 'BRRTrade'),
    ('Trade Close to TRR', 'TRRTrade'),
    ('Up Resistance', 'Up Resistance'),
    ('Down Resistance', 'Down Resistance'),
    ('VS LT Outlook Rule', 'VS LT Outlook Rule'),
    ('Short Term Oulook (If LT Bullish)', 'Short Term Oulook (If LT Bullish)'),
    ('Short Term Oulook (If LT Bearish)', 'Short Term Oulook (If LT Bearish)'),
    ('Overbought', 'Overbought'),
    ('Trade-Rule', 'Trade-Rule'),
]

with session_scope() as s:
    updated = 0
    for rule_name, ma_col in original_mappings:
        result = s.execute(text("""
            UPDATE ref_trig_atomic_rule
            SET ma_column_name = :col
            WHERE rule_name = :name AND deprecated_at IS NULL AND brkeout_from IS NULL
        """), {"col": ma_col, "name": rule_name})

        if result.rowcount > 0:
            updated += 1
            print(f"  {rule_name:45s} -> {ma_col}")

    s.commit()
    print(f"\nRestored {updated} original mappings")
