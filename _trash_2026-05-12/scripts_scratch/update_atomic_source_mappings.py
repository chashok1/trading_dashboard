#!/usr/bin/env python
"""Update atomic rules to map to Excel source columns."""
from etl.db import session_scope
from sqlalchemy import text

# Map atomic rules to their Excel source column references
atomic_mappings = {
    'BBThresh CO Days2': 'BBThresh_CO_Days',
    'BRR% Rule': 'BRR%',
    'BRR% LRR': 'BRR%',
    'BRR% R2': 'BRR%',
    'BRR% LRR2': 'BRR%',
    'BRR% TRR': 'BRR%',
    'BRR% Puts': 'BRR%',
    'BRR% TRR Puts': 'BRR%',
    'TRR_Idx': 'Sd TRR',
    'MRR_Idx': 'Sd MRR',
    'LRR_Idx': 'Sd LRR',
    'HVAbsolute': 'HistoricalVolatility',
    'IVAbsolute': 'ImpVolatility',
    'IVPercentile': 'IVPercentile',
    'IVPercentile Puts': 'IVPercentile',
    'HVPercentile': 'HVPercentile',
    'HVPercentile Puts': 'HVPercentile',
    'IVHV Puts (modified)': 'IVHV',
    'RSI Top': 'RSI',
    'RSI Puts': 'RSI',
    'Perf3D SD Rule': 'Perf3D_sd',
    'Perf1D SD Rule': 'Perf1D_sd',
    'Perf3D 1Off Rule': 'Perf3D_sd',
    'BBStreak Rule2': 'BB_Streak',
    'BBStreak Days Up Rule': 'BB_Streak_Days',
    'BBStreak Days Rule2': 'BB_Streak_Days',
    'BBStreak Days Up Rule2': 'BB_Streak_Days',
    'MACD_BRR Puts': 'MACD_BRR',
    'MACDH_BRR Puts': 'MACDH_BRR',
    'MACDH Days': 'A_MACDays_Streak',
    'MACDH Days2': 'A_MACDays_Streak',
}

with session_scope() as s:
    updated = 0
    for rule_name, col_ref in atomic_mappings.items():
        result = s.execute(text('''
            UPDATE ref_trig_atomic_rule
            SET ma_column_name = :col
            WHERE rule_name = :name AND deprecated_at IS NULL
        '''), {'col': col_ref, 'name': rule_name})

        if result.rowcount > 0:
            updated += 1
            print(f'  {rule_name:40s} -> {col_ref}')

    s.commit()
    print(f'\nUpdated {updated} atomic rule mappings')
