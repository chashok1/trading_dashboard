#!/usr/bin/env python
"""Update ma_column_name mappings for all atomic rules from user's mapping list."""

excel_cols = """MACDH Direction MACD Direction BB Direction BB Threshold BBThresh CO Days BBThresh_CO_Days2
Trade Cross Over Trade-Rule !Trade Rule Trend Cross Over Trend-Rule !Trend Rule Trend Trade Dep Rule
TrTn Relation !TrTn Relation Trade Trend SD Rule BRR% Rule BRR% LRR BRR% R2 BRR% LRR2 BRR% TRR
BRR% Puts BRR% TRR Puts BRR% Dir High TRR Low LRR Trend below TRR LRR above Trade TRR_Idx MRR_Idx
LRR_Idx HVAbsolute IVAbsolute IVPercentile IVPercentile Puts HVPercentile HVPercentile Puts IVHV IVHV Puts
IVRule RSI Rule RSI Top RSI Puts 3m-Low-Rule 3m-Low-Days Rule 3mn-High-Rule 3mn-High-Days Rule 3m-Long
Perf3mn SD Rule Perf2M SD Rule Perf3WK SD Rule Perf2WK SD Rule Perf3D SD Rule Perf1D SD Rule
!Perf1D_sd Perf3D_sd_1off Perf SD Rule !Perf SD Rule !Perf3D Rule BBHighLow_SD Rule BBHighLow Days Rule
BBStreak Rule BBStreakRule1 BBStreak Rule2 BBStreak Days Rule BBStreak Days Rule2 BBStreak Days Rule3
BBStreak Days Rule4 BB Bull Rule BB Bull Puts BBHighDays BBLowDays MACD Rule MACDH Rule MACD and H Rule
MACD_BRR Puts MACDH_BRR Puts MACD and H Rule Puts MACDH Days MACDH Days2 Overbought !Overbought
3mn Outlook 3mn Outlook Days 3wk Outlook 3wk Outlook Days !3wk ol !3wk ol days BULL !BULL
PerfOrBull !PerfOrBull 50-DMA-Rule 50-DMA-Crossover 200-DMA-Rule 200-DMA-Crossover 52-Wk Low Rule
52-Wk High Rule BRRTrade TRRTrade Up Resistance Down Resistance Earnings VS Price VS Volume Spike
VS Volatility VS Days VS LT Outlook Rule Current Price SD Rule Current Volume Rule Current Volatility Rule
Short Term Oulook If LT Bullish Short Term Oulook If LT Bearish""".split()

db_cols = """MACDH Direction MACD Direction BB Direction BBThresh Crossover BBThresh CO Days
BBThresh CO Days2 Trade Cross Over Trade-Rule !Trade Rule Trend Cross Over Trend-Rule !Trend Rule
Trend Trade Dep Rule Trade Trend Relation !Trade Trend Relation Trade Trend SD Rule BRR% Rule BRR% LRR
BRR% R2 BRR% LRR2 BRR% TRR BRR% Puts BRR% TRR Puts BRR% Dir Rule High above TRR Low below LRR
Trend below TRR LRR above Trade TRR_Idx MRR_Idx LRR_Idx HVAbsolute IVAbsolute IVPercentile
IVPercentile Puts HVPercentile HVPercentile Puts IVHV Rule modified IVHV Puts modified IVRule
RSI Rule RSI Top RSI Puts 3m-Low-Rule 3m-Low-Days Rule 3mn-High-Rule 3mn-High-Dyas Rule 3mn Long Rule
Perf3mn SD Rule Perf2M SD Rule Perf3wk SD Rule Perf2wk SD Rule Perf3D SD Rule Perf1D SD Rule
!Perf1D SD Rule Perf3D 1Off Rule Perf SD Rule !Perf SD Rule !Perf3D Rule BBHighLow_SD Rule
BBHighLow Days Rule BBStreak Rule BBStreak Rule1 BBStreak Rule2 BBStreak Days Rule BBStreak Days Up Rule
BBStreak Days Rule2 BBStreak Days Up Rule2 BB Bull Rule BB Bull Puts BBHighDays BBLowDays MACD Rule
MACDH Rule MACD and H Rule MACD_BRR Puts MACDH_BRR Puts MACD and H Rule Puts MACDH Days MACDH Days2
Overbought !Overbought 3mn Outlook 3mn Outlook Days 3wk Outlook 3wk Outlook Days !3wk Outlook
!3wk Outlook Days Bull Rule !Bull Rule PerfOrBull Rule !PerfOrBull Rule 50-DMA-Rule 50-DMA-Crossover
200-DMA-Rule 200-DMA-Crossover 52-Wk Low Rule 52-Wk High Rule Trade Close to BRR Trade Close to TRR
Up Resistance Down Resistance Earnings Days VS Price Rule VS Volume Spike Rule VS Volatility Rule
VS Days VS LT Outlook Rule Current Price Rule Current Volume Rule Current Volatility Rule
Short Term Oulook If LT Bullish Short Term Oulook If LT Bearish""".split()

# Blank = derivative indicator, Number = atomic rule
rule_types = "1 1 1 -1 -1 1 3 3 3 3 1 -1 -1 1 3 3 -1 -1 -1 2 3 3 -1 3 -1 3 -1 3 1 -1 1 1 3 3 1 1 1 1 1 1 3 1 1 1 3 -1 3 1 3 1 1 1 1 1 -1 -1 1 3 1 1 1 1 1 1 -3 1 1 3 3 1 1 1".split()

print(f"Excel cols: {len(excel_cols)}")
print(f"DB cols: {len(db_cols)}")
print(f"Rule types: {len(rule_types)}")
print()

# Create mapping
mappings = []
for i in range(len(excel_cols)):
    if i < len(db_cols) and i < len(rule_types):
        excel_name = excel_cols[i]
        db_name = db_cols[i]
        rule_type = rule_types[i] if rule_types[i] else None
        is_atomic = rule_type is not None
        mappings.append({
            'excel': excel_name,
            'db': db_name,
            'type': rule_type,
            'is_atomic': is_atomic
        })

print("Derivative indicators (blank type):")
derivatives = [m for m in mappings if not m['is_atomic']]
for m in derivatives:
    print(f"  {m['excel']:40s} → drv_ma.{m['db'].lower().replace(' ', '_').replace('-', '_')}")

print(f"\nTotal derivative indicators: {len(derivatives)}")

print(f"\nAtomic rules (with type number): {len([m for m in mappings if m['is_atomic']])}")
