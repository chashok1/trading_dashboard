#!/usr/bin/env python
from sqlalchemy import text
from etl.db import session_scope

mappings = [
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
]

with session_scope() as s:
    s.execute(text('DELETE FROM ref_trig_atomic_rule WHERE atomic_rule_id >= 118'))
    s.commit()

    max_id = s.execute(text("SELECT MAX(atomic_rule_id) FROM ref_trig_atomic_rule")).scalar() or 0
    next_id = max_id + 1

    for ma_col, rule_name in mappings:
        s.execute(text("""
            INSERT INTO ref_trig_atomic_rule (atomic_rule_id, rule_name, ma_column_name)
            VALUES (:id, :name, :col)
        """), {"id": next_id, "name": rule_name, "col": ma_col})
        next_id += 1

    s.commit()
    print(f"Inserted {len(mappings)} derived indicators")
