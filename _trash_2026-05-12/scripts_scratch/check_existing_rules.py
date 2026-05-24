#!/usr/bin/env python
"""Check if the derived indicator rules exist and their From/To values."""
from sqlalchemy import text
from etl.db import session_scope

# Rules the user expects as derived indicators
expected_derived = [
    'MACDH Direction',
    'MACD Direction',
    'BB Direction',
    'BBThresh Crossover',
    'Trade Cross Over',
    '!Trade Rule',
    'Trend Cross Over',
    '!Trend Rule',
    'Trend Trade Dep Rule',
    'Trade Trend Relation',
    '!Trade Trend Relation',
    'BRR% Dir Rule',
    'Trend below TRR',
    'LRR above Trade',
    'IVRule',
    '3mn Long Rule',
    '!Perf1D SD Rule',
    'Perf SD Rule',
    '!Perf SD Rule',
    '!Perf3D Rule',
    'BB Bull Rule',
    'BB Bull Puts',
    'MACD and H Rule',
    'MACD and H Rule Puts',
    'Overbought',
    '!Overbought',
    '!3wk Outlook',
    '!3wk Outlook Days',
    'Bull Rule',
    '!Bull Rule',
    'PerfOrBull Rule',
    '!PerfOrBull Rule',
    '50-DMA-Crossover',
    '200-DMA-Crossover',
    'Trade Close to BRR',
    'Trade Close to TRR',
    'Up Resistance',
    'Down Resistance',
    'VS LT Outlook Rule',
    'Short Term Oulook (If LT Bullish)',
    'Short Term Oulook (If LT Bearish)',
]

with session_scope() as s:
    print(f"Checking {len(expected_derived)} expected derived indicator rules:\n")

    found = []
    missing = []
    has_from_to = []

    for rule_name in expected_derived:
        # Search for rule by name
        result = s.execute(text("""
            SELECT atomic_rule_id, rule_name, brkeout_from, brkeout_to, ma_column_name
            FROM ref_trig_atomic_rule
            WHERE deprecated_at IS NULL AND rule_name = :name
        """), {"name": rule_name}).fetchone()

        if result:
            rule_id, name, from_val, to_val, col = result
            found.append((rule_id, name, from_val, to_val, col))
            if from_val is not None or to_val is not None:
                has_from_to.append((rule_id, name, from_val, to_val))
        else:
            missing.append(rule_name)

    print(f"Found: {len(found)}/41")
    print(f"Missing: {len(missing)}/41")
    print(f"Have From/To values (should be NULL): {len(has_from_to)}\n")

    if missing:
        print("Missing rules:")
        for name in missing[:10]:
            print(f"  - {name}")
        if len(missing) > 10:
            print(f"  ... and {len(missing)-10} more\n")

    if has_from_to:
        print("Rules that have From/To values but shouldn't:")
        for rule_id, name, from_val, to_val in has_from_to:
            print(f"  {rule_id}: {name} -> From={from_val}, To={to_val}")
