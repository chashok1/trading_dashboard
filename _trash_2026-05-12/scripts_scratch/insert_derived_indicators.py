#!/usr/bin/env python
"""Insert 41 derived indicator rules into ref_trig_atomic_rule."""
from sqlalchemy import text
from etl.db import session_scope

# List of derived indicator rules with inferred MA column mappings
rules = [
    ('MACDH Direction', 'a_macdh'),
    ('MACD Direction', 'a_macd'),
    ('BB Direction', 'a_bb_direction'),
    ('BBThresh Crossover', 'a_bb_thresh'),
    ('Trade Cross Over', 'a_trade'),
    ('!Trade Rule', 'a_trade'),
    ('Trend Cross Over', 'a_trend'),
    ('!Trend Rule', 'a_trend'),
    ('Trend Trade Dep Rule', 'a_trend_trade'),
    ('Trade Trend Relation', 'a_trade_trend'),
    ('!Trade Trend Relation', 'a_trade_trend'),
    ('BRR% Dir Rule', 'a_brr_pct'),
    ('Trend below TRR', 'a_trend'),
    ('LRR above Trade', 'a_lrr'),
    ('IVRule', 'iv_percentile'),
    ('3mn Long Rule', 'a_3mn_long'),
    ('!Perf1D SD Rule', 'a_perf_1d'),
    ('Perf SD Rule', 'a_perf'),
    ('!Perf SD Rule', 'a_perf'),
    ('!Perf3D Rule', 'a_perf_3d'),
    ('BB Bull Rule', 'a_bb'),
    ('BB Bull Puts', 'a_bb'),
    ('MACD and H Rule', 'a_macdh'),
    ('MACD and H Rule Puts', 'a_macdh'),
    ('Overbought', 'rsi'),
    ('!Overbought', 'rsi'),
    ('!3wk Outlook', 'a_outlook_3wk'),
    ('!3wk Outlook Days', 'a_outlook_3wk'),
    ('Bull Rule', 'a_bull'),
    ('!Bull Rule', 'a_bull'),
    ('PerfOrBull Rule', 'a_perf_bull'),
    ('!PerfOrBull Rule', 'a_perf_bull'),
    ('50-DMA-Crossover', 'a_dma_50'),
    ('200-DMA-Crossover', 'a_dma_200'),
    ('Trade Close to BRR', 'a_trade'),
    ('Trade Close to TRR', 'a_trade'),
    ('Up Resistance', 'a_resistance_up'),
    ('Down Resistance', 'a_resistance_down'),
    ('VS LT Outlook Rule', 'a_macd_brr'),
    ('Short Term Oulook (If LT Bullish)', 'a_macd_brr'),
    ('Short Term Oulook (If LT Bearish)', 'a_macd_brr'),
]

with session_scope() as s:
    # Get max atomic_rule_id to start new IDs from there
    max_id = s.execute(text("SELECT MAX(atomic_rule_id) FROM ref_trig_atomic_rule")).scalar() or 0
    next_id = max_id + 1

    print(f"Starting with atomic_rule_id: {next_id}\n")
    print(f"Inserting {len(rules)} derived indicator rules:\n")

    inserted = 0
    existing = 0

    for rule_name, ma_column in rules:
        # Check if rule already exists
        existing_rule = s.execute(text("""
            SELECT atomic_rule_id FROM ref_trig_atomic_rule
            WHERE deprecated_at IS NULL AND rule_name = :name
        """), {"name": rule_name}).scalar()

        if existing_rule:
            print(f"  SKIP: {rule_name} (already exists as ID {existing_rule})")
            existing += 1
            continue

        # Insert the rule
        s.execute(text("""
            INSERT INTO ref_trig_atomic_rule (
                atomic_rule_id, rule_name, ma_column_name,
                brkeout_from, brkeout_to, wt_below, wt_between, wt_above
            ) VALUES (:id, :name, :col, NULL, NULL, NULL, NULL, NULL)
        """), {
            "id": next_id,
            "name": rule_name,
            "col": ma_column
        })

        print(f"  OK: {next_id:3d} {rule_name:40s} -> {ma_column}")
        inserted += 1
        next_id += 1

    s.commit()

    print(f"\nSummary:")
    print(f"  Inserted: {inserted}")
    print(f"  Existing: {existing}")
    print(f"  Total: {inserted + existing}")

    # Verify count
    total = s.execute(text("""
        SELECT COUNT(*) FROM ref_trig_atomic_rule
        WHERE deprecated_at IS NULL AND brkeout_from IS NULL
    """)).scalar()

    print(f"\nDerived indicators in DB: {total}")
