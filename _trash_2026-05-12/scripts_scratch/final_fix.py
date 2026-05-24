#!/usr/bin/env python
"""Insert exactly the 41 derived indicators the user specified."""
from sqlalchemy import text
from etl.db import session_scope

# Exactly 41 derived indicators from user's list
derived_41 = [
    ('MACDH Direction', 'MACDH Direction'),
    ('MACD Direction', 'MACD Direction'),
    ('BB Direction', 'BB Direction'),
    ('Trade Cross Over', 'Trade Cross Over'),
    ('!Trade Rule', '!Trade Rule'),
    ('Trend Cross Over', 'Trend Cross Over'),
    ('!Trend Rule', '!Trend Rule'),
    ('Trend Trade Dep Rule', 'Trend Trade Dep Rule'),
    ('Trade Trend Relation', 'Trade Trend Relation'),
    ('!Trade Trend Relation', '!Trade Trend Relation'),
    ('BRR% Dir Rule', 'BRR% Dir Rule'),
    ('Trend below TRR', 'Trend below TRR'),
    ('LRR above Trade', 'LRR above Trade'),
    ('IVRule', 'IVRule'),
    ('3mn Long Rule', '3mn Long Rule'),
    ('!Perf1D SD Rule', '!Perf1D SD Rule'),
    ('Perf SD Rule', 'Perf SD Rule'),
    ('!Perf SD Rule', '!Perf SD Rule'),
    ('!Perf3D Rule', '!Perf3D Rule'),
    ('BB Bull Rule', 'BB Bull Rule'),
    ('BB Bull Puts', 'BB Bull Puts'),
    ('MACD and H Rule', 'MACD and H Rule'),
    ('MACD and H Rule Puts', 'MACD and H Rule Puts'),
    ('!Overbought', '!Overbought'),
    ('!3wk Outlook', '!3wk Outlook'),
    ('!3wk Outlook Days', '!3wk Outlook Days'),
    ('Bull Rule', 'Bull Rule'),
    ('!Bull Rule', '!Bull Rule'),
    ('PerfOrBull Rule', 'PerfOrBull Rule'),
    ('!PerfOrBull Rule', '!PerfOrBull Rule'),
    ('50-DMA-Crossover', '50-DMA-Crossover'),
    ('200-DMA-Crossover', '200-DMA-Crossover'),
    ('Trade Close to BRR', 'Trade Close to BRR'),
    ('Trade Close to TRR', 'Trade Close to TRR'),
    ('Up Resistance', 'Up Resistance'),
    ('Down Resistance', 'Down Resistance'),
    ('VS LT Outlook Rule', 'VS LT Outlook Rule'),
    ('Short Term Oulook (If LT Bullish)', 'Short Term Oulook (If LT Bullish)'),
    ('Short Term Oulook (If LT Bearish)', 'Short Term Oulook (If LT Bearish)'),
    ('Overbought', 'Overbought'),
    ('Trade-Rule', 'Trade-Rule'),
]

with session_scope() as s:
    # Delete all derived indicators (no From/To)
    s.execute(text('''
        DELETE FROM ref_trig_atomic_rule
        WHERE deprecated_at IS NULL AND brkeout_from IS NULL
    '''))
    s.commit()
    print("Cleared all derived indicators")

    # Get max ID
    max_id = s.execute(text("SELECT MAX(atomic_rule_id) FROM ref_trig_atomic_rule")).scalar() or 0
    next_id = max_id + 1

    print(f"\nInserting exactly {len(derived_41)} derived indicators:\n")

    for ma_col, rule_name in derived_41:
        # Check if already exists with From/To (atomic)
        existing = s.execute(text("""
            SELECT atomic_rule_id FROM ref_trig_atomic_rule
            WHERE rule_name = :name
        """), {"name": rule_name}).scalar()

        if existing:
            print(f"  SKIP: {rule_name:50s} (ID {existing})")
            continue

        s.execute(text("""
            INSERT INTO ref_trig_atomic_rule (
                atomic_rule_id, rule_name, ma_column_name,
                brkeout_from, brkeout_to
            ) VALUES (:id, :name, :col, NULL, NULL)
        """), {
            "id": next_id,
            "name": rule_name,
            "col": ma_col
        })

        print(f"  OK: {next_id:3d} {rule_name:50s} -> {ma_col}")
        next_id += 1

    s.commit()
    print(f"\nTotal inserted/existing: {len(derived_41)}")

    # Verify
    total = s.execute(text("""
        SELECT COUNT(*) FROM ref_trig_atomic_rule
        WHERE deprecated_at IS NULL AND brkeout_from IS NULL
    """)).scalar()

    print(f"Derived indicators in DB: {total}")
