#!/usr/bin/env python
"""Re-insert 41 derived indicator rules with corrected ma_column_name mappings."""
from sqlalchemy import text
from etl.db import session_scope

# Mapping of derived indicator names to actual drv_ma columns
# Based on what exists in the schema
corrected_mappings = {
    'MACDH Direction': 'a_macdh_d_brr',        # MACD Histogram delta from drv_tw
    'MACD Direction': 'a_macd_brr',            # MACD from drv_tw
    'BB Direction': 'a_bb_top',                # Bollinger Band top
    'BBThresh Crossover': 'a_bb_streak',       # Already exists (ID 8)
    'Trade Cross Over': 'a_trade_value',       # Trade value
    '!Trade Rule': 'a_trade_value',
    'Trend Cross Over': 'a_trend_value',       # Trend value
    '!Trend Rule': 'a_trend_value',
    'Trend Trade Dep Rule': 'a_trend_value',   # Trend-focused
    'Trade Trend Relation': 'a_trade_value',   # Trade-focused
    '!Trade Trend Relation': 'a_trade_value',
    'BRR% Dir Rule': 'pct_brr',                # BRR percentage
    'Trend below TRR': 'a_trend_value',
    'LRR above Trade': 'a_trade_value',
    'IVRule': 'iv_percentile',                 # Already exists with same name
    '3mn Long Rule': 'range_compression',      # Volume/range based
    '!Perf1D SD Rule': 'd_iv_to_hv',          # IV to HV ratio (performance indicator)
    'Perf SD Rule': 'd_iv_to_hv',
    '!Perf SD Rule': 'd_iv_to_hv',
    '!Perf3D Rule': 'range_compression',
    'BB Bull Rule': 'a_bb_bottom',             # Bollinger Band bottom
    'BB Bull Puts': 'a_bb_top',
    'MACD and H Rule': 'a_macdh_d_brr',
    'MACD and H Rule Puts': 'a_macdh_d_brr',
    'Overbought': 'rsi',                       # Already exists (ID 85)
    '!Overbought': 'rsi',
    '!3wk Outlook': 'rr_outlook',              # RR outlook as proxy for 3wk
    '!3wk Outlook Days': 'rr_outlook',
    'Bull Rule': 'a_trade_value',              # Trade value indicates bullish
    '!Bull Rule': 'a_trend_value',
    'PerfOrBull Rule': 'a_trade_value',
    '!PerfOrBull Rule': 'a_trend_value',
    '50-DMA-Crossover': 'sma_50',              # SMA 50
    '200-DMA-Crossover': 'sma_200',            # SMA 200
    'Trade Close to BRR': 'a_trade_value',
    'Trade Close to TRR': 'a_trend_value',
    'Up Resistance': 'a_bb_top',               # BB top as resistance
    'Down Resistance': 'a_bb_bottom',          # BB bottom as resistance
    'VS LT Outlook Rule': 'rr_outlook',        # Already exists (ID 112)
    'Short Term Oulook (If LT Bullish)': 'a_trade_value',  # Already exists (ID 116)
    'Short Term Oulook (If LT Bearish)': 'a_trend_value',   # Already exists (ID 117)
}

with session_scope() as s:
    # Delete the incorrectly mapped derived indicators (IDs 118-153)
    s.execute(text('''
        DELETE FROM ref_trig_atomic_rule
        WHERE atomic_rule_id >= 118 AND atomic_rule_id <= 153
    '''))
    s.commit()
    print("Deleted incorrectly mapped rules (IDs 118-153)")

    # Get max atomic_rule_id to start new IDs
    max_id = s.execute(text("SELECT MAX(atomic_rule_id) FROM ref_trig_atomic_rule")).scalar() or 0
    next_id = max_id + 1

    print(f"\nRe-inserting with corrected mappings, starting from ID {next_id}:\n")

    inserted = 0
    skipped = 0

    for rule_name, ma_column in corrected_mappings.items():
        # Check if rule already exists
        existing_rule = s.execute(text("""
            SELECT atomic_rule_id FROM ref_trig_atomic_rule
            WHERE deprecated_at IS NULL AND rule_name = :name
        """), {"name": rule_name}).scalar()

        if existing_rule:
            print(f"  SKIP: {rule_name:45s} (already exists as ID {existing_rule})")
            skipped += 1
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

        print(f"  OK: {next_id:3d} {rule_name:45s} -> {ma_column}")
        inserted += 1
        next_id += 1

    s.commit()

    print(f"\nSummary:")
    print(f"  Inserted: {inserted}")
    print(f"  Existing: {skipped}")
    print(f"  Total: {inserted + skipped}")

    # Verify derived indicator count
    total = s.execute(text("""
        SELECT COUNT(*) FROM ref_trig_atomic_rule
        WHERE deprecated_at IS NULL AND brkeout_from IS NULL
    """)).scalar()

    print(f"\nDerived indicators in DB: {total}")
