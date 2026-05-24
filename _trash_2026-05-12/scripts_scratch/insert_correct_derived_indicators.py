#!/usr/bin/env python
"""Insert 41 derived indicator rules with correct mappings from user data."""
from sqlalchemy import text
from etl.db import session_scope

# Mapping from user: (ma_column_name, rule_name)
# Based on the lists provided by user
derived_indicator_mappings = [
    ('MACDH Direction', 'MACDH Direction'),
    ('MACD Direction', 'MACD Direction'),
    ('BB Direction', 'BB Direction'),
    ('BBThresh Crossover', 'BBThresh Crossover'),
    ('BBThresh CO Days', 'BBThresh CO Days'),
    ('BBThresh_CO_Days2', 'BBThresh CO Days2'),
    ('Trade Cross Over', 'Trade Cross Over'),
    ('Trade-Rule', 'Trade-Rule'),
    ('!Trade Rule', '!Trade Rule'),
    ('Trend Cross Over', 'Trend Cross Over'),
    ('Trend-Rule', 'Trend-Rule'),
    ('!Trend Rule', '!Trend Rule'),
    ('Trend Trade Dep Rule', 'Trend Trade Dep Rule'),
    ('TrTn Relation', 'Trade Trend Relation'),
    ('!TrTn Relation', '!Trade Trend Relation'),
    ('Trade Trend SD Rule', 'Trade Trend SD Rule'),
    ('BRR% Rule', 'BRR% Rule'),
    ('BRR% LRR', 'BRR% LRR'),
    ('BRR% R2', 'BRR% R2'),
    ('BRR% LRR2', 'BRR% LRR2'),
    ('BRR% TRR', 'BRR% TRR'),
    ('BRR% Puts', 'BRR% Puts'),
    ('BRR% TRR Puts', 'BRR% TRR Puts'),
    ('BRR% Dir', 'BRR% Dir Rule'),
    ('High TRR', 'High above TRR'),
    ('Low LRR', 'Low below LRR'),
    ('Trend below TRR', 'Trend below TRR'),
    ('LRR above Trade', 'LRR above Trade'),
    ('TRR_Idx', 'TRR_Idx'),
    ('MRR_Idx', 'MRR_Idx'),
    ('LRR_Idx', 'LRR_Idx'),
    ('HVAbsolute', 'HVAbsolute'),
    ('IVAbsolute', 'IVAbsolute'),
    ('IVPercentile', 'IVPercentile'),
    ('IVPercentile Puts', 'IVPercentile Puts'),
    ('HVPercentile', 'HVPercentile'),
    ('HVPercentile Puts', 'HVPercentile Puts'),
    ('IVHV', 'IVHV Rule (modified)'),
    ('IVHV Puts', 'IVHV Puts (modified)'),
    ('IVRule', 'IVRule'),
    ('RSI Rule', 'RSI Rule'),
    ('RSI Top', 'RSI Top'),
    ('RSI Puts', 'RSI Puts'),
    ('3m-Low-Rule', '3m-Low-Rule'),
    ('3m-Low-Days Rule', '3m-Low-Days Rule'),
    ('3mn-High-Rule', '3mn-High-Rule'),
    ('3mn-High-Days Rule', '3mn-High-Dyas Rule'),
    ('3m-Long', '3mn Long Rule'),
    ('Perf3mn SD Rule', 'Perf3mn SD Rule'),
    ('Perf2M SD Rule', 'Perf2M SD Rule'),
    ('Perf3WK SD Rule', 'Perf3wk SD Rule'),
    ('Perf2WK SD Rule', 'Perf2wk SD Rule'),
    ('Perf3D SD Rule', 'Perf3D SD Rule'),
    ('Perf1D SD Rule', 'Perf1D SD Rule'),
    ('!Perf1D_sd', '!Perf1D SD Rule'),
    ('Perf3D_sd_1off', 'Perf3D 1Off Rule'),
    ('Perf SD Rule', 'Perf SD Rule'),
    ('!Perf SD Rule', '!Perf SD Rule'),
    ('!Perf3D Rule', '!Perf3D Rule'),
    ('BBHighLow_SD Rule', 'BBHighLow_SD Rule'),
    ('BBHighLow Days Rule', 'BBHighLow Days Rule'),
    ('BBStreak Rule', 'BBStreak Rule'),
    ('BBStreakRule1', 'BBStreak Rule1'),
    ('BBStreak Rule2', 'BBStreak Rule2'),
    ('BBStreak Days Rule', 'BBStreak Days Rule'),
    ('BBStreak Days Rule2', 'BBStreak Days Up Rule'),
    ('BBStreak Days Rule3', 'BBStreak Days Rule2'),
    ('BBStreak Days Rule4', 'BBStreak Days Up Rule2'),
    ('BB Bull Rule', 'BB Bull Rule'),
    ('BB Bull Puts', 'BB Bull Puts'),
    ('BBHighDays', 'BBHighDays'),
    ('BBLowDays', 'BBLowDays'),
    ('MACD Rule', 'MACD Rule'),
    ('MACDH Rule', 'MACDH Rule'),
    ('MACD and H Rule', 'MACD and H Rule'),
    ('MACD_BRR Puts', 'MACD_BRR Puts'),
    ('MACDH_BRR Puts', 'MACDH_BRR Puts'),
    ('MACD and H Rule Puts', 'MACD and H Rule Puts'),
    ('MACDH Days', 'MACDH Days'),
    ('MACDH Days2', 'MACDH Days2'),
    ('Overbought', 'Overbought'),
    ('!Overbought', '!Overbought'),
    ('3mn Outlook', '3mn Outlook'),
    ('3mn Outlook Days', '3mn Outlook Days'),
    ('3wk Outlook', '3wk Outlook'),
    ('3wk Outlook Days', '3wk Outlook Days'),
    ('!3wk ol', '!3wk Outlook'),
    ('!3wk ol days', '!3wk Outlook Days'),
    ('BULL', 'Bull Rule'),
    ('!BULL', '!Bull Rule'),
    ('PerfOrBull', 'PerfOrBull Rule'),
    ('!PerfOrBull', '!PerfOrBull Rule'),
    ('50-DMA-Rule', '50-DMA-Rule'),
    ('50-DMA-Crossover', '50-DMA-Crossover'),
    ('200-DMA-Rule', '200-DMA-Rule'),
    ('200-DMA-Crossover', '200-DMA-Crossover'),
    ('52-Wk Low Rule', '52-Wk Low Rule'),
    ('52-Wk High Rule', '52-Wk High Rule'),
    ('BRRTrade', 'Trade Close to BRR'),
    ('TRRTrade', 'Trade Close to TRR'),
    ('Up Resistance', 'Up Resistance'),
    ('Down Resistance', 'Down Resistance'),
    ('Earnings', 'Earnings Days'),
    ('VS Price', 'VS Price Rule'),
    ('VS Volume Spike', 'VS Volume Spike Rule'),
    ('VS Volatility', 'VS Volatility Rule'),
    ('VS Days', 'VS Days'),
    ('VS LT Outlook Rule', 'VS LT Outlook Rule'),
    ('Current Price SD Rule', 'Current Price Rule'),
    ('Current Volume Rule', 'Current Volume Rule'),
    ('Current Volatility Rule', 'Current Volatility Rule'),
    ('Short Term Oulook (If LT Bullish)', 'Short Term Oulook (If LT Bullish)'),
    ('Short Term Oulook (If LT Bearish)', 'Short Term Oulook (If LT Bearish)'),
]

with session_scope() as s:
    # Delete previously inserted rules (IDs 118+)
    s.execute(text('''
        DELETE FROM ref_trig_atomic_rule
        WHERE atomic_rule_id >= 118
    '''))
    s.commit()
    print("Cleared previous derived indicators")

    # Get max atomic_rule_id
    max_id = s.execute(text("SELECT MAX(atomic_rule_id) FROM ref_trig_atomic_rule")).scalar() or 0
    next_id = max_id + 1

    print(f"\nInserting {len(derived_indicator_mappings)} derived indicators starting from ID {next_id}:\n")

    inserted = 0
    skipped = 0

    for ma_col, rule_name in derived_indicator_mappings:
        # Check if rule already exists
        existing = s.execute(text("""
            SELECT atomic_rule_id FROM ref_trig_atomic_rule
            WHERE deprecated_at IS NULL AND rule_name = :name
        """), {"name": rule_name}).scalar()

        if existing:
            print(f"  SKIP: {rule_name:50s} (exists as ID {existing})")
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
            "col": ma_col
        })

        print(f"  OK: {next_id:3d} {rule_name:50s} -> {ma_col}")
        inserted += 1
        next_id += 1

    s.commit()

    print(f"\nSummary:")
    print(f"  Inserted: {inserted}")
    print(f"  Existing: {skipped}")
    print(f"  Total: {inserted + skipped}")

    # Verify
    total = s.execute(text("""
        SELECT COUNT(*) FROM ref_trig_atomic_rule
        WHERE deprecated_at IS NULL AND brkeout_from IS NULL
    """)).scalar()

    print(f"\nDerived indicators in DB: {total}")
