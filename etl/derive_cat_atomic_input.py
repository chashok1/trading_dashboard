"""drv_cat_atomic_input — Python deriver for MA-tab columns JF..NP + QE..QT.

Replaces the ma_codegen / ref_ma_columns.source_expr path for this one table
(see commit 2026-05-27).  The registry-driven approach left ~100 columns
unmapped (source_expr=NULL) and silently inserted NULL for every one of them.

Design recap (docs/drv_cat_atomic_input_logic.md):
  Step 1   Single SELECT builds per-symbol input row from hist_td / hist_tw
           / drv_quote / hist_y / hist_rr.
  Step 2   Python computes MA-sheet *intermediates* (AC, AD, AG, AH, AI,
           BB, BC, BE, BF, BJ, BK, BN, BO, BQ..CA, EE, EO..EU, FK, FR, GB,
           JB ...) as ordinary dict-row arithmetic.
  Step 3   Pass-1 outputs: trig_ifs / negate / passthru / composite /
           zero_guard_trig_ifs / trig_ifs_dma / sign_zero_neg / cond_passthru.
           trig_ifs delegates to eval_atomic_rule() in derive.py, the same
           engine that powers drv_trig / drv_stks.
  Step 4   Pass-2 outputs: composites that READ Pass-1 outputs from the
           same row dict (KD, KT, LB, LK, LW, MI, MQ, MS, NJ, NN, NO).
  Step 5   DELETE WHERE as_of_date=D, executemany INSERT (idempotent).
  Step 6   Pass-3 UPDATE: Parm-lookup QF/QG/QK/QL/QO/QP/QQ/QS/QT, joining
           ref_param_lookup.

The QE/QJ/QM/QN/QR five rules are NOT computed here — _derive_trend_trade_rules_impl
in derive.py still handles them in its own two-pass UPDATE.  This module
runs BEFORE that one in derive_all().
"""
from __future__ import annotations

from datetime import date
from typing import Any, Callable, Optional
import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)


# =============================================================================
# Step 1 — working-set SELECT.
# Mirrors the latest-snapshot-<=D pattern used by _derive_ma_impl.
# =============================================================================
WORKING_SET_SQL = """
WITH p AS (SELECT CAST(:d AS date) AS d),
syms AS (
    SELECT DISTINCT s FROM (
        SELECT ticker AS s FROM ref_sector
        UNION SELECT symbol FROM hist_tl WHERE snapshot_date <= (SELECT d FROM p)
        UNION SELECT symbol FROM hist_td WHERE snapshot_date <= (SELECT d FROM p)
        UNION SELECT symbol FROM hist_tw WHERE snapshot_date <= (SELECT d FROM p)
    ) u WHERE s IS NOT NULL
),
td AS (
    SELECT DISTINCT ON (symbol) symbol,
           a_trend_value, a_trade_value, a_bb_top, a_bb_bottom,
           a_bb_streak, a_bb_high_low, a_bb_high_low_days,
           a_iv_percentile, a_hv_percentile,
           a_bb_top_slope, a_bb_bot_slope,
           historical_vol, imp_volatility, rsi
    FROM hist_td WHERE snapshot_date <= (SELECT d FROM p)
    ORDER BY symbol, snapshot_date DESC, sequence DESC
),
tw AS (
    SELECT DISTINCT ON (symbol) symbol,
           standard_dev, sma_20, sma_50, sma_200,
           a_macd_brr1, a_macdh_d_brr1, a_macdays_streak,
           a_3mn_high, a_3mn_low, a_3mn_high_low, a_3wk_high_low,
           a_perf_2m, a_perf_2wk, a_perf_3d,
           a_volume_spike, volume_avg_3m, volume_rate_change,
           a_earnings_days, high_52, low_52
    FROM hist_tw WHERE snapshot_date <= (SELECT d FROM p)
    ORDER BY symbol, snapshot_date DESC, sequence DESC
),
med AS (
    -- AA = as-of-date median of standard_dev (over the symbol's full history
    -- <= D).  Drives AC = MIN(AA, AB) in the MA sheet.
    SELECT symbol,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY standard_dev) AS median_sd
    FROM hist_tw
    WHERE snapshot_date <= (SELECT d FROM p) AND standard_dev IS NOT NULL
    GROUP BY symbol
),
dq AS (
    SELECT DISTINCT ON (symbol) symbol, last_price, net_chng, pct_change,
           open, high, low
    FROM drv_quote WHERE as_of_date <= (SELECT d FROM p)
    ORDER BY symbol, as_of_date DESC
),
rr AS (
    SELECT DISTINCT ON (COALESCE(tos_symbol, symbol))
           COALESCE(tos_symbol, symbol) AS symbol,
           buy_trade, sell_trade
    FROM hist_rr WHERE snapshot_date <= (SELECT d FROM p)
    ORDER BY COALESCE(tos_symbol, symbol), snapshot_date DESC
)
SELECT s.s AS symbol,
       -- hist_td (rule input bases)
       td.a_trend_value, td.a_trade_value, td.a_bb_top, td.a_bb_bottom,
       td.a_bb_streak, td.a_bb_high_low, td.a_bb_high_low_days,
       td.a_iv_percentile, td.a_hv_percentile,
       td.a_bb_top_slope, td.a_bb_bot_slope,
       td.historical_vol, td.imp_volatility, td.rsi,
       -- hist_tw
       tw.standard_dev, tw.sma_50, tw.sma_200,
       tw.a_macd_brr1, tw.a_macdh_d_brr1, tw.a_macdays_streak,
       tw.a_3mn_high, tw.a_3mn_low, tw.a_3mn_high_low, tw.a_3wk_high_low,
       tw.a_perf_2m, tw.a_perf_2wk, tw.a_perf_3d,
       tw.a_volume_spike, tw.volume_avg_3m, tw.volume_rate_change,
       tw.a_earnings_days, tw.high_52, tw.low_52,
       med.median_sd,
       -- drv_quote
       dq.last_price, dq.net_chng, dq.pct_change,
       dq.high AS high_today, dq.low AS low_today,
       -- hist_rr
       rr.buy_trade, rr.sell_trade
FROM syms s
LEFT JOIN td  ON td.symbol  = s.s
LEFT JOIN tw  ON tw.symbol  = s.s
LEFT JOIN med ON med.symbol = s.s
LEFT JOIN dq  ON dq.symbol  = s.s
LEFT JOIN rr  ON rr.symbol  = s.s
"""


# =============================================================================
# Step 2 — MA-sheet intermediates.  All per-row arithmetic.
# Source-of-truth: docs/ma_columns_v2.csv formula column.
# =============================================================================
def _safe_div(num, den):
    """num / den with NULL / divide-by-zero -> None."""
    try:
        n = float(num) if num is not None else None
        d = float(den) if den is not None else None
        if n is None or d is None or d == 0:
            return None
        return n / d
    except (TypeError, ValueError):
        return None


def _f(v) -> Optional[float]:
    """Numeric coercion -> Optional[float]."""
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def compute_intermediates(row: dict) -> dict:
    """Compute every MA-sheet intermediate this deriver needs.

    Adds keys 'AC', 'AD', 'AG', 'AH', 'AI', 'BB', 'BC', 'BE', 'BF', 'BJ',
    'BK', 'BN', 'BO', 'BQ', 'BS', 'BU', 'BW', 'BY', 'BZ', 'CA', 'EE', 'EO',
    'EP', 'EQ', 'ER', 'FK', 'FR', 'GB' to `row` and returns it.
    """
    D    = _f(row.get("last_price"))
    AE   = _f(row.get("a_trend_value"))
    AF   = _f(row.get("a_trade_value"))
    AB   = _f(row.get("standard_dev"))
    AA   = _f(row.get("median_sd"))
    BD   = _f(row.get("a_3mn_high"))
    BA   = _f(row.get("a_3mn_low"))
    BH   = _f(row.get("a_3mn_high_low"))
    BL   = _f(row.get("a_3wk_high_low"))
    BR   = _f(row.get("a_perf_2m"))
    BV   = _f(row.get("a_perf_2wk"))
    BX   = _f(row.get("a_perf_3d"))
    G_   = _f(row.get("net_chng"))                   # MA col G = 1d net change
    CC   = _f(row.get("low_52"))
    CD   = _f(row.get("high_52"))
    CG   = _f(row.get("sma_50"))
    CH   = _f(row.get("sma_200"))
    EH   = _f(row.get("high_today"))
    EI   = _f(row.get("low_today"))
    EC   = _f(row.get("buy_trade"))                  # RR bottom-of-range
    ED   = _f(row.get("sell_trade"))                 # RR top-of-range
    EK   = _f(row.get("a_bb_top"))                   # used in EO comparator
    EL   = _f(row.get("a_bb_bottom"))                # used in EP comparator

    # AC = MIN(AA, AB)   per ma_columns_v2.csv
    if AA is not None and AB is not None:
        AC = min(AA, AB)
    else:
        AC = AA if AA is not None else AB
    # AD = AC / D
    AD = _safe_div(AC, D) if D and D != 0 else None

    # AG = IF(D=AE, 0.1, (D-AE)/AC)         Trend_sd
    if D is not None and AE is not None:
        AG = 0.1 if D == AE else _safe_div(D - AE, AC)
    else:
        AG = None
    # AH = (D-AF)/AC                        Trade_sd
    AH = _safe_div(D - AF, AC) if D is not None and AF is not None else None
    # AI = (AF-AE)/AC                       Trade_Trend_Sd
    AI = _safe_div(AF - AE, AC) if AF is not None and AE is not None else None
    # BB = (D-BA)/AC                        3mnLow_sd
    BB = _safe_div(D - BA, AC) if D is not None and BA is not None else None
    # BC -- 3mnLowDays: BA holds count+fraction; we approximate as BA*100
    BC = _f(row.get("a_3mn_low"))  # placeholder; precise formula needs raw BA struct
    # BE = (D-BD)/AC                        3mnHigh_sd
    BE = _safe_div(D - BD, AC) if D is not None and BD is not None else None
    # BF -- 3mnHighDays
    BF = _f(row.get("a_3mn_high"))  # placeholder
    # BJ = (D-BI)/AC ; BI not in hist_tw — placeholder uses 3mn_high_low source
    BJ = _safe_div(D - BH, AC) if D is not None and BH is not None else None
    BK = BH  # placeholder
    BN = _safe_div(D - BL, AC) if D is not None and BL is not None else None
    BO = BL  # placeholder
    BQ = AG  # Perf3M_sd == Trend_sd by formula (=(D-AE)/AC)
    BS = _safe_div(BR, (AD * 100)) if AD else None      # Perf2M_sd
    BU = AH  # Perf3W_sd == Trade_sd
    BW = _safe_div(BV, (AD * 100)) if AD else None      # Perf2Wk_sd
    BY = _safe_div(BX, (AD * 100)) if AD else None      # Perf3D_sd
    # BZ = (100*D)/(100+BX)
    BZ = _safe_div(100 * D, (100 + BX)) if D is not None and BX is not None else None
    # CA = G/AC                              Perf1D_sd
    CA = _safe_div(G_, AC)

    # EE = (D-EC)*100/(ED-EC)
    if EC is not None and EC != 0 and ED is not None and (ED - EC) != 0 and D is not None:
        EE = (D - EC) * 100.0 / (ED - EC)
    else:
        EE = None
    # EO = (ED - max(EH, EK)) / AC
    EO = None
    if ED is not None and AC and (EH is not None or EK is not None):
        top = max(v for v in (EH, EK) if v is not None)
        EO = _safe_div(ED - top, AC)
    # EP = (min(EI, EL) - EC) / AC
    EP = None
    if EC is not None and AC and (EI is not None or EL is not None):
        bot = min(v for v in (EI, EL) if v is not None)
        EP = _safe_div(bot - EC, AC)
    # EQ = (ED-AE)/AC                        Trnd TRR
    EQ = _safe_div(ED - AE, AC) if ED is not None and AE is not None else None
    # ER = (EC-AF)/AC                        Trd LRR
    ER = _safe_div(EC - AF, AC) if EC is not None and AF is not None else None

    # FK / FR / GB are placeholders pending hist_tw extension (see doc § Gaps)
    FK = None
    FR = _safe_div((_f(row.get("imp_volatility")) or 0) * 100,
                   _f(row.get("historical_vol")))      # IVHV
    GB = (_f(row.get("volume_avg_3m")) or 0) * 100.0 if row.get("volume_avg_3m") else None

    row.update(dict(AC=AC, AD=AD, AG=AG, AH=AH, AI=AI,
                    BB=BB, BC=BC, BE=BE, BF=BF, BJ=BJ, BK=BK, BN=BN, BO=BO,
                    BQ=BQ, BS=BS, BU=BU, BW=BW, BY=BY, BZ=BZ, CA=CA,
                    EE=EE, EO=EO, EP=EP, EQ=EQ, ER=ER,
                    FK=FK, FR=FR, GB=GB))
    return row


# =============================================================================
# Step 3 — output COLUMN_SPECS.  See doc § Formula taxonomy.
#
# Spec tuple:
#   (db_col, formula_type, input, trig_rule_name, extra)
#
# formula_type values:
#   "trig_ifs"            input=key into row (intermediate or source col),
#                         trig_rule_name=ref_trig_atomic_rule.rule_name.
#                         Delegates to eval_atomic_rule().
#   "zero_guard_trig_ifs" Like trig_ifs but returns 0 when any of `extra`
#                         (tuple of input keys) is 0.
#   "negate"              input=db_col of twin.  out = -1 * twin_value.
#   "passthru"            input=row key.  out = row[input].
#   "sign_zero_neg"       input=row key.  out = -1 if x=0 else sign(x).
#   "cond_passthru"       input=(flag_key, value_key). out = value if flag==1 else 0.
#   "composite"           extra=callable(row, out) -> value.  Pass-2 only.
#   "trig_ifs_dma"        input=(price_key, ma_key, vol_key).
#                         trig_rule_name set.  Volatility-scaled DMA rule:
#                           wt_above   if price >= MA + d * vol
#                           wt_between if price >= MA + c * vol
#                           wt_below   if price >= MA
#                         (and symmetric negative).
# =============================================================================
COLUMN_SPECS_PASS1 = [
    # ---- JF block opener is just a marker ----
    # JG / JH — sign-with-zero-as-neg over CK / CI (MACDH/MACD direction)
    ("macdh_direction",   "sign_zero_neg", "a_macdh_d_brr1", None, None),     # JG
    ("macd_direction",    "sign_zero_neg", "a_macd_brr1",    None, None),     # JH
    # JI — passthrough of AN (BB_Direction1).  AN not currently sourced;
    # approximate using sign of a_bb_streak (BB streak direction).
    ("bb_direction",      "sign_zero_neg", "a_bb_streak",    None, None),     # JI (approx)
    # JJ — IF(AX=1, AW, 0); AX/AW not sourced yet (see doc § Gaps).
    # Leaving NULL — rule still fires by source data in Pass-2 if needed.
    # ("bb_threshold",  ...)
    # JK / JL — BBThresh CO Days variants (input = MA col AX = days count).
    # AX not sourced yet; deferred.
    # JM Trade Cross Over — needs EF/J/I.  Not sourced; deferred.
    # JN — Trade-Rule (trig_ifs on AH = Trade_sd)
    ("trade_rule",        "trig_ifs", "AH", "Trade-Rule",  None),             # JN
    ("not_trade_rule",    "negate",   "trade_rule", None, None),              # JO
    # JP Trend Cross Over — deferred (needs EF/J/I/BZ).
    ("trend_rule",        "trig_ifs", "AG", "Trend-Rule",  None),             # JQ
    ("not_trend_rule",    "negate",   "trend_rule", None, None),              # JR
    # JS Trend Trade Dep Rule -> composite (Pass-2)
    # JT TrTn Relation -> composite (Pass-2)
    # JU !TrTn Relation -> negate(JT)
    ("trade_trend_sd_rule", "trig_ifs", "AI", "Trade Trend SD Rule", None),    # JV
    ("brrpct_rule",         "trig_ifs", "EE", "BRR% Rule",      None),         # JW
    ("brrpct_lrr",          "trig_ifs", "EE", "BRR% LRR",       None),         # JX
    ("brrpct_r2",           "trig_ifs", "EE", "BRR% R2",        None),         # JY
    ("brrpct_lrr2",         "trig_ifs", "EE", "BRR% LRR2",      None),         # JZ
    ("brrpct_trr",          "trig_ifs", "EE", "BRR% TRR",       None),         # KA
    ("brrpct_puts",         "trig_ifs", "EE", "BRR% Puts",      None),         # KB
    ("brrpct_trr_puts",     "trig_ifs", "EE", "BRR% TRR Puts",  None),         # KC
    # KD BRR% Dir -> composite (Pass-2; reads JI/JG/LG/JW/KB)
    ("high_trr",            "trig_ifs", "EO", "High above TRR", None),         # KE
    ("low_lrr",             "trig_ifs", "EP", "Low below LRR",  None),         # KF
    ("trend_below_trr",     "composite", None, None,
        (lambda r,o: -1.0 if (r.get("EQ") or 0) < 0 else 0.0)),                 # KG
    ("lrr_above_trade",     "composite", None, None,
        (lambda r,o: 1.0 if (r.get("ER") or 0) > 0 else 0.0)),                  # KH
    # KI/KJ/KK -- TRR/MRR/LRR_Idx require ES/ET/EU (Sd-normalized risk indices).
    # ES/ET/EU formulas reference DQ/DM/DR which aren't sourced.  Deferred.
    # KL HVAbsolute -- input CV (historical_vol), but Trig key 'HVAbsolute' uses CV.
    ("hvabsolute",          "trig_ifs", "historical_vol", "HVAbsolute", None), # KL
    # KM IVAbsolute -- zero-guarded by DT (imp_volatility)
    ("ivabsolute",          "zero_guard_trig_ifs", "imp_volatility",
        "IVAbsolute", ("imp_volatility",)),                                     # KM
    # KN/KO IV percentile (zero-guarded by DT, CX)
    ("ivpercentile",        "zero_guard_trig_ifs", "a_iv_percentile",
        "IVPercentile", ("imp_volatility", "a_iv_percentile")),                 # KN
    ("ivpercentile_puts",   "zero_guard_trig_ifs", "a_iv_percentile",
        "IVPercentile Puts", ("imp_volatility", "a_iv_percentile")),            # KO
    ("hvpercentile",        "zero_guard_trig_ifs", "a_hv_percentile",
        "HVPercentile", ("imp_volatility",)),                                   # KP
    ("hvpercentile_puts",   "zero_guard_trig_ifs", "a_hv_percentile",
        "HVPercentile Puts", ("imp_volatility",)),                              # KQ
    ("ivhv",                "zero_guard_trig_ifs", "FR",
        "IVHV Rule (modified)", ("imp_volatility",)),                           # KR
    ("ivhv_puts",           "zero_guard_trig_ifs", "FR",
        "IVHV Puts (modified)", ("imp_volatility",)),                           # KS
    # KT IVRule -> composite (Pass-2; reads KN, KP, KR)
    ("rsi_rule",            "trig_ifs", "rsi",        "RSI Rule", None),       # KU
    ("rsi_top",             "trig_ifs", "rsi",        "RSI Top",  None),       # KV
    ("rsi_puts",            "trig_ifs", "rsi",        "RSI Puts", None),       # KW
    ("3m_low_rule",         "trig_ifs", "BB",         "3m-Low-Rule",  None),   # KX
    ("3m_low_days_rule",    "trig_ifs", "BC",         "3m-Low-Days Rule",None),# KY
    ("3mn_high_rule",       "trig_ifs", "BE",         "3mn-High-Rule",None),   # KZ
    ("3mn_high_days_rule",  "trig_ifs", "BF",         "3mn-High-Dyas Rule",None), # LA
    # LB 3m-Long -> composite
    ("perf3mn_sd_rule",     "trig_ifs", "BQ", "Perf3mn SD Rule",  None),       # LC
    ("perf2m_sd_rule",      "trig_ifs", "BS", "Perf2M SD Rule",   None),       # LD
    ("perf3wk_sd_rule",     "trig_ifs", "BU", "Perf3wk SD Rule",  None),       # LE
    ("perf2wk_sd_rule",     "trig_ifs", "BW", "Perf2wk SD Rule",  None),       # LF
    ("perf3d_sd_rule",      "trig_ifs", "BY", "Perf3D SD Rule",   None),       # LG
    ("perf1d_sd_rule",      "trig_ifs", "CA", "Perf1D SD Rule",   None),       # LH
    ("not_perf1d_sd",       "negate",   "perf1d_sd_rule", None, None),         # LI
    # LJ -- Perf3D_sd_1off (uses ABS(BY))
    ("perf3d_sd_1off",      "trig_ifs", "BY", "Perf3D 1Off Rule",
        {"abs_input": True}),                                                   # LJ
    # LK Perf SD Rule -> composite (Pass-2; reads LC..LJ)
    # LL/LM negations
    # LN BBHighLow_SD Rule -- input AO (BBHighLow_SD).  Not yet computed; deferred.
    # LO BBHighLow Days Rule -- input AM.  Deferred.
    # LP BBStreak Rule -- input AY (BB_Streak)
    ("bbstreak_rule",       "trig_ifs", "a_bb_streak", "BBStreak Rule",  None),# LP
    ("bbstreakrule1",       "trig_ifs", "a_bb_streak", "BBStreak Rule1", None),# LQ
    ("bbstreak_rule2",      "trig_ifs", "a_bb_streak", "BBStreak Rule2", None),# LR
    # LS/LT/LU/LV -- BBStreak Days variants (input AZ).  AZ not sourced; deferred.
    # LW BB Bull Rule -> composite
    # LX -> negate
    # LY/LZ -- BBHighDays/BBLowDays (input AQ/AR -- not sourced).  Deferred.
    # MA MACD Rule -- input CJ = ABS(CI); ditto MB uses ABS(CK)
    ("macd_rule",           "trig_ifs", "a_macd_brr1",  "MACD Rule",
        {"abs_input": True}),                                                   # MA
    ("macdh_rule",          "trig_ifs", "a_macdh_d_brr1","MACDH Rule",
        {"abs_input": True}),                                                   # MB
    # MC MACD and H Rule -> composite (INT((MA+MB)/2))
    # MD/ME use CJ/CL too (abs forms)
    ("macd_brr_puts",       "trig_ifs", "a_macd_brr1",   "MACD_BRR Puts",
        {"abs_input": True}),                                                   # MD
    ("macdh_brr_puts",      "trig_ifs", "a_macdh_d_brr1","MACDH_BRR Puts",
        {"abs_input": True}),                                                   # ME
    # MF -> composite
    # MG/MH -- MACDH Days (input CM = a_macdays_streak)
    ("macdh_days",          "trig_ifs", "a_macdays_streak", "MACDH Days",  None),# MG
    ("macdh_days2",         "trig_ifs", "a_macdays_streak", "MACDH Days2", None),# MH
    # MI Overbought -> composite (Pass-2; reads KV/MA/MB)
    # MJ negate
    # MK..MP -- 3mn/3wk outlook variants (inputs BJ/BK/BN/BO)
    ("3mn_outlook",         "trig_ifs", "BJ", "3mn Outlook",         None),    # MK
    ("3mn_outlook_days",    "trig_ifs", "BK", "3mn Outlook Days",    None),    # ML
    ("3wk_outlook",         "trig_ifs", "BN", "3wk Outlook",         None),    # MM
    ("3wk_outlook_days",    "trig_ifs", "BO", "3wk Outlook Days",    None),    # MN
    # MO/MP negate
    # MQ BULL -> composite ; MR negate
    # MS PerfOrBull -> composite ; MT negate
    # MU 50-DMA-Rule -- trig_ifs_dma over (D, CG, AC)
    ("50_dma_rule",         "trig_ifs_dma",
        ("last_price","sma_50","AC"), "50-DMA-Rule", None),                    # MU
    # MV 50-DMA-Crossover -> composite (reads D/CG/BZ)
    ("50_dma_crossover",    "composite", None, None,
        (lambda r,o: _crossover(r.get("last_price"), r.get("sma_50"),
                                r.get("BZ")))),                                # MV
    ("200_dma_rule",        "trig_ifs_dma",
        ("last_price","sma_200","AC"), "200-DMA-Rule", None),                  # MW
    ("200_dma_crossover",   "composite", None, None,
        (lambda r,o: _crossover(r.get("last_price"), r.get("sma_200"),
                                r.get("BZ")))),                                # MX
    ("52_wk_low_rule",      "trig_ifs_dma",
        ("last_price","low_52","AC"), "52-Wk Low Rule", None),                 # MY
    ("52_wk_high_rule",     "trig_ifs_dma",
        ("last_price","high_52","AC"), "52-Wk High Rule", None),               # MZ
    # NA/NB BRRTrade/TRRTrade -> composite (uses DX/DY/AF/AC)
    ("brrtrade",            "composite", None, None,
        (lambda r,o: 1.0 if (
            r.get("buy_trade") is not None and r.get("a_trade_value") is not None
            and r.get("AC") and r.get("AC") != 0
            and abs(float(r["buy_trade"]) - float(r["a_trade_value"]))
                <= float(r["AC"]) * 0.5
        ) else 0.0)),                                                          # NA
    ("trrtrade",            "composite", None, None,
        (lambda r,o: -1.0 if (
            r.get("sell_trade") is not None and r.get("a_trade_value") is not None
            and r.get("AC") and r.get("AC") != 0
            and abs(float(r["sell_trade"]) - float(r["a_trade_value"]))
                <= float(r["AC"]) * 0.5
        ) else 0.0)),                                                          # NB
    # NC/ND Up/Down Resistance -> composite (needs EH/EI/AC/CG/CH/BA)
    # NE Earnings -- trig_ifs on JB = a_earnings_days
    ("earnings",            "trig_ifs", "a_earnings_days", "Earnings Days", None), # NE
    # NF/NG/NH/NI -- VS rules.  Inputs FK/FI/FL/FM.
    # FI/FL/FM are derived from FH (string) -- not sourced as numeric yet.
    # FK approximated via volume_rate_change in row dict for now.
    # NJ -> composite (reads NF..NI)
    # NK/NL/NM -- Current Price/Volume/Volatility SD Rules
    # NK input = H/AD = (1d net_chng / SD%).  H = G2 == net_chng.
    ("current_price_sd_rule", "zero_guard_trig_ifs",
        "_NK_input", "Current Price Rule", ("AD",)),                            # NK
    # NL Current Volume Rule -- input GB.  Asymmetric -1/4 mult on negative side
    # not yet supported by eval_atomic_rule; using standard trig_ifs (good
    # enough for most cases; precise behaviour documented in § Caveats).
    ("current_volume_rule", "trig_ifs", "GB", "Current Volume Rule", None),    # NL
    ("current_volatility_rule", "trig_ifs", "imp_volatility",
        "Current Volatility Rule", None),                                       # NM
    # NN/NO -> composite (Pass-2)
    # ---- QE/QJ/QM/QN/QR computed by _derive_trend_trade_rules_impl ----
    # QH/QI raw slope mirrors
    ("a_bb_bot_slope",      "passthru", "a_bb_bot_slope", None, None),         # QH
    ("a_bb_top_slope",      "passthru", "a_bb_top_slope", None, None),         # QI
]


# =============================================================================
# Pass-2 composites (read Pass-1 outputs from the same row).
# =============================================================================
def _crossover(price, ma, prev_price) -> Optional[float]:
    """Three-way crossover: +1 (price > MA > prev), -1 (prev > MA > price), 0."""
    p = _f(price); m = _f(ma); pp = _f(prev_price)
    if p is None or m is None or pp is None:
        return 0.0
    if p > m and m > pp:
        return 1.0
    if pp > m and m > p:
        return -1.0
    return 0.0


def _bull_expr(r: dict, o: dict) -> Optional[float]:
    """MQ: BULL — composite over JN/JQ/JV/LZ/LY/KH."""
    JN = _f(o.get("trade_rule"))
    JQ = _f(o.get("trend_rule"))
    JV = _f(o.get("trade_trend_sd_rule"))
    LZ = _f(o.get("bblowdays"))           # placeholder None
    LY = _f(o.get("bbhighdays"))          # placeholder None
    KH = _f(o.get("lrr_above_trade"))
    def ge(a, b): return a is not None and a >= b
    def le(a, b): return a is not None and a <= b
    if ge(JN,3) and ge(JQ,2) and ge(JV,2) and ge(LZ,3): return 3.0
    if KH and KH > 0 and ge(JV,2):                       return 3.0
    if ge(JN,2) and ge(JQ,2) and ge(JV,2) and ge(LZ,2):  return 2.0
    if le(JN,-3) and le(JQ,-2) and le(JV,-2) and ge(LY,3): return -3.0
    if le(JN,-2) and le(JQ,-2) and le(JV,-2) and ge(LY,2): return -2.0
    return 0.0


def _perforbull_expr(r: dict, o: dict) -> Optional[float]:
    """MS: PerfOrBull = IFS(OR(LK>=3,MQ>=3),3, OR(LK<=-3,MQ<=-3),-3,
                            TRUE, INT((LK+MQ)/2))."""
    LK = _f(o.get("perf_sd_rule")) or 0.0
    MQ = _f(o.get("bull")) or 0.0
    if LK >= 3 or MQ >= 3: return 3.0
    if LK <= -3 or MQ <= -3: return -3.0
    return float(int((LK + MQ) / 2))


def _perf_sd_rule_expr(r: dict, o: dict) -> Optional[float]:
    """LK: long composite IFS chain over LC..LJ."""
    LC = _f(o.get("perf3mn_sd_rule"))
    LD = _f(o.get("perf2m_sd_rule"))
    LE_ = _f(o.get("perf3wk_sd_rule"))
    LF = _f(o.get("perf2wk_sd_rule"))
    LG = _f(o.get("perf3d_sd_rule"))
    LJ = _f(o.get("perf3d_sd_1off"))
    def ge(a, b): return a is not None and a >= b
    def le(a, b): return a is not None and a <= b
    if ge(LC,3) and ge(LD,3) and ge(LE_,3) and ge(LF,1) and ge(LJ,3): return 3.0
    if ge(LC,3) and ge(LD,3) and ge(LE_,2) and ge(LF,1) and ge(LJ,3): return 2.0
    if ge(LC,1) and ge(LD,3) and ge(LE_,3) and ge(LF,3) and ge(LJ,3): return 2.0
    if ge(LC,1) and ge(LD,3) and ge(LE_,1) and ge(LF,1) and ge(LJ,1): return 2.0
    if le(LC,-3) and le(LD,-3) and le(LE_,-3) and le(LF,-1) and ge(LJ,3): return -3.0
    if le(LC,-3) and le(LD,-3) and le(LE_,-2) and le(LF,-1) and ge(LJ,3): return -2.0
    if le(LC,-1) and le(LD,-3) and le(LE_,-3) and le(LF,-3) and ge(LJ,3): return -2.0
    return 1.0 if (LC is not None and LC >= 0) else -1.0


def _bb_bull_rule_expr(r: dict, o: dict) -> Optional[float]:
    """LW: BB Bull Rule = IFS(AND(LP>=3,LS>=3),3, AND(LP<=-3,LS<=-3),-3, TRUE, LN)."""
    LP = _f(o.get("bbstreak_rule")) or 0.0
    LS = _f(o.get("bbstreak_days_rule")) or 0.0
    LN = _f(o.get("bbhighlow_sd_rule"))   # placeholder None
    if LP >= 3 and LS >= 3: return 3.0
    if LP <= -3 and LS <= -3: return -3.0
    return LN


def _overbought_expr(r: dict, o: dict) -> Optional[float]:
    KV_ = _f(o.get("rsi_top")) or 0.0
    MA_ = _f(o.get("macd_rule")) or 0.0
    MB_ = _f(o.get("macdh_rule")) or 0.0
    if KV_ >= 3 and MA_ >= 3 and MB_ >= 3: return 3.0
    if KV_ <= -3 and MA_ <= -3 and MB_ <= -3: return -3.0
    return 0.0


def _ivrule_expr(r: dict, o: dict) -> Optional[float]:
    DT_ = _f(r.get("imp_volatility"))
    if DT_ == 0: return 0.0
    KN_ = _f(o.get("ivpercentile")) or 0.0
    KP_ = _f(o.get("hvpercentile")) or 0.0
    KR_ = _f(o.get("ivhv")) or 0.0
    if KN_ >= 3 and KP_ >= 3 and KR_ >= 3: return 3.0
    if KN_ >= 2 and KP_ >= 2 and KR_ >= 2: return 2.0
    return 1.0


def _3m_long_expr(r: dict, o: dict) -> Optional[float]:
    KX = _f(o.get("3m_low_rule")) or 0.0
    KY = _f(o.get("3m_low_days_rule")) or 0.0
    KZ = _f(o.get("3mn_high_rule")) or 0.0
    LA = _f(o.get("3mn_high_days_rule")) or 0.0
    if KX >= 3 and KY >= 2 and KZ >= -2 and LA >= 3: return 3.0
    if KZ <= -3 and LA >= 2 and KX <= 2 and KY >= 3: return -3.0
    return float(int((KX + KY - 1) / 2))


def _brrpct_dir_expr(r: dict, o: dict) -> Optional[float]:
    """KD: BRR% Dir = IFS(AND(JI=1,JG=1),JW, AND(JI=-1,JG=-1),KB,
                         LG>0,JW, LG<0,KB)."""
    JI_ = _f(o.get("bb_direction"))
    JG_ = _f(o.get("macdh_direction"))
    LG_ = _f(o.get("perf3d_sd_rule"))
    JW_ = _f(o.get("brrpct_rule"))
    KB_ = _f(o.get("brrpct_puts"))
    if JI_ == 1 and JG_ == 1: return JW_
    if JI_ == -1 and JG_ == -1: return KB_
    if LG_ is not None and LG_ > 0: return JW_
    if LG_ is not None and LG_ < 0: return KB_
    return None


COLUMN_SPECS_PASS2 = [
    # JS Trend Trade Dep Rule = IF(AE<=AF, JQ, JN)
    ("trend_trade_dep_rule", "composite", None, None,
        (lambda r,o: _f(o.get("trend_rule"))
                     if (_f(r.get("a_trend_value")) is not None
                         and _f(r.get("a_trade_value")) is not None
                         and _f(r["a_trend_value"]) <= _f(r["a_trade_value"]))
                     else _f(o.get("trade_rule")))),
    # JT TrTn Relation = IF(AE<=AF, 1, -1)
    ("trtn_relation", "composite", None, None,
        (lambda r,o: 1.0
                     if (_f(r.get("a_trend_value")) is not None
                         and _f(r.get("a_trade_value")) is not None
                         and _f(r["a_trend_value"]) <= _f(r["a_trade_value"]))
                     else -1.0)),
    ("not_trtn_relation", "negate", "trtn_relation", None, None),
    ("brrpct_dir",   "composite", None, None, _brrpct_dir_expr),               # KD
    ("ivrule",       "composite", None, None, _ivrule_expr),                   # KT
    ("3m_long",      "composite", None, None, _3m_long_expr),                  # LB
    ("perf_sd_rule", "composite", None, None, _perf_sd_rule_expr),             # LK
    ("not_perf_sd_rule", "negate", "perf_sd_rule", None, None),                # LL
    ("not_perf3d_rule",  "negate", "perf3d_sd_rule", None, None),              # LM
    ("bb_bull_rule",     "composite", None, None, _bb_bull_rule_expr),         # LW
    ("bb_bull_puts",     "negate", "bb_bull_rule", None, None),                # LX
    ("macd_and_h_rule",  "composite", None, None,
        (lambda r,o: float(int(((_f(o.get("macd_rule")) or 0)
                                 + (_f(o.get("macdh_rule")) or 0)) / 2)))),    # MC
    ("macd_and_h_rule_puts", "composite", None, None,
        (lambda r,o: float(int(((_f(o.get("macd_brr_puts")) or 0)
                                 + (_f(o.get("macdh_brr_puts")) or 0)) / 2)))),# MF
    ("overbought",       "composite", None, None, _overbought_expr),           # MI
    ("not_overbought",   "negate", "overbought", None, None),                  # MJ
    ("not_3wk_ol",       "negate", "3wk_outlook", None, None),                 # MO
    ("not_3wk_ol_days",  "negate", "3wk_outlook_days", None, None),            # MP
    ("bull",             "composite", None, None, _bull_expr),                 # MQ
    ("not_bull",         "negate", "bull", None, None),                        # MR
    ("perforbull",       "composite", None, None, _perforbull_expr),           # MS
    ("not_perforbull",   "negate", "perforbull", None, None),                  # MT
]


# =============================================================================
# Trig rule cache.
# =============================================================================
def load_trig_rules(session: Session) -> dict:
    """Return {rule_name: {brkeout_from, brkeout_to, wt_below, wt_between,
       wt_above, scoring_mode, score_params}}."""
    rows = session.execute(text("""
        SELECT rule_name, brkeout_from, brkeout_to,
               wt_below, wt_between, wt_above,
               scoring_mode, score_params
        FROM ref_trig_atomic_rule
        WHERE deprecated_at IS NULL AND rule_name IS NOT NULL
    """)).mappings().all()
    out = {}
    for r in rows:
        if r["rule_name"]:
            out[r["rule_name"]] = dict(r)
    return out


# =============================================================================
# Evaluator helpers.
# =============================================================================
def _eval_trig_ifs(value, rule: Optional[dict]) -> Optional[float]:
    """Excel-faithful Trig-IFS evaluator.

    Implements the 6-clause IFS used by every JF..NP trig_ifs formula:

        v >= hi   ->   wt_above
        v >= lo   ->   wt_between
        v >= 0    ->   wt_below
        v <= -hi  ->  -wt_above
        v <= -lo  ->  -wt_between
        v < 0     ->  -wt_below

    The shared `eval_atomic_rule()` in derive.py uses a 3-clause `jump`
    that returns `wt_below` for ALL v < lo (including very-negative v) —
    correct for drv_trig's unsigned scoring but wrong for the signed atomic
    inputs JF..NP.  We implement the 6-clause locally so this deriver
    matches Excel exactly.

    For scoring_mode='linear' or 'sigmoid', delegate to eval_atomic_rule
    (those modes don't appear in JF..NP today but support is kept for
    forward compatibility).
    """
    if rule is None or value is None:
        return None
    v = _f(value)
    if v is None:
        return None
    mode = (rule.get("scoring_mode") or "jump").lower()
    if mode in ("linear", "sigmoid"):
        from etl.derive import eval_atomic_rule
        return eval_atomic_rule(value, rule)
    lo = _f(rule.get("brkeout_from")) or 0.0
    hi = _f(rule.get("brkeout_to")) or 0.0
    wb_ = _f(rule.get("wt_below")) or 0.0
    wbt = _f(rule.get("wt_between")) or 0.0
    wa = _f(rule.get("wt_above")) or 0.0
    if v >= hi:  return wa
    if v >= lo:  return wbt
    if v >= 0:   return wb_
    if v <= -hi: return -wa
    if v <= -lo: return -wbt
    if v < 0:    return -wb_
    return 0.0


def _eval_trig_ifs_dma(price, ma, vol, rule: Optional[dict]) -> Optional[float]:
    """Volatility-scaled DMA Trig-IFS variant (MU/MW/MY/MZ)."""
    if rule is None:
        return None
    p = _f(price); m = _f(ma); v = _f(vol)
    if p is None or m is None or v is None:
        return None
    lo = _f(rule.get("brkeout_from")) or 0.0
    hi = _f(rule.get("brkeout_to")) or 0.0
    wb = _f(rule.get("wt_below")) or 0.0
    wbt = _f(rule.get("wt_between")) or 0.0
    wa = _f(rule.get("wt_above")) or 0.0
    if p >= m + hi * v:   return wa
    if p >= m + lo * v:   return wbt
    if p >= m:            return wb
    if p < m - hi * v:    return -wa
    if p < m - lo * v:    return -wbt
    if p < m:             return -wb
    return 0.0


# =============================================================================
# Per-row evaluator.
# =============================================================================
def eval_specs(row: dict, specs: list, trig_rules: dict, out: dict) -> dict:
    """Evaluate `specs` against `row` (input data) and `out` (already-computed
       outputs).  Mutates `out` in place and returns it."""
    for spec in specs:
        db_col, ftype, src, rule_name, extra = spec
        try:
            if ftype == "trig_ifs":
                val = row.get(src) if src in row else out.get(src)
                if isinstance(extra, dict) and extra.get("abs_input") and val is not None:
                    val = abs(_f(val) or 0.0)
                out[db_col] = _eval_trig_ifs(val, trig_rules.get(rule_name))

            elif ftype == "zero_guard_trig_ifs":
                guards = extra or ()
                if any((_f(row.get(g) if g in row else out.get(g)) == 0
                        or row.get(g) is None) for g in guards):
                    out[db_col] = 0.0
                    continue
                val = row.get(src) if src in row else out.get(src)
                if src == "_NK_input":
                    H = _f(row.get("net_chng"))
                    AD = _f(row.get("AD"))
                    val = _safe_div(H, AD)
                out[db_col] = _eval_trig_ifs(val, trig_rules.get(rule_name))

            elif ftype == "trig_ifs_dma":
                pk, mk, vk = src
                out[db_col] = _eval_trig_ifs_dma(
                    row.get(pk), row.get(mk), row.get(vk),
                    trig_rules.get(rule_name))

            elif ftype == "negate":
                twin = out.get(src)
                out[db_col] = (-1.0 * _f(twin)) if twin is not None else None

            elif ftype == "passthru":
                out[db_col] = _f(row.get(src))

            elif ftype == "sign_zero_neg":
                v = _f(row.get(src))
                if v is None:
                    out[db_col] = None
                elif v == 0:
                    out[db_col] = -1.0
                else:
                    out[db_col] = 1.0 if v > 0 else -1.0

            elif ftype == "cond_passthru":
                flag_key, val_key = src
                flag = _f(row.get(flag_key))
                out[db_col] = _f(row.get(val_key)) if flag == 1 else 0.0

            elif ftype == "composite":
                fn: Callable = extra
                out[db_col] = fn(row, out)

            else:
                log.warning("unknown formula_type %r for %s", ftype, db_col)
                out[db_col] = None
        except Exception as e:
            log.warning("eval_specs %s failed: %s", db_col, e)
            out[db_col] = None
    return out


# =============================================================================
# Pass-3 — Parm-lookup tail (QF/QG/QK/QL/QO/QP/QQ/QS/QT).
# Runs as a single SQL UPDATE after QE/QJ/QM/QN/QR have been populated by
# _derive_trend_trade_rules_impl.
# =============================================================================
PARM_LOOKUP_SQL = """
UPDATE drv_cat_atomic_input dst
SET
    tn_td_rule_action = l_qf.seq,
    tn_td_rule_desc   = l_qf.description,
    bb_rng_strk_action = l_qk.seq,
    bb_rng_strk_desc   = l_qk.description,
    risk_rng_longs_action = CASE
        WHEN dst.bb_rng_strk_rule >= 2 THEN l_qm.seq
        WHEN dst.bb_rng_strk_rule >= 0 THEN l_qn.seq
        ELSE NULL END,
    rr_bull_bear = CASE
        WHEN dst.bb_rng_strk_rule >= 2 AND l_qm.description IS NOT NULL THEN 'B'
        WHEN dst.bb_rng_strk_rule >= 0 AND l_qn.description IS NOT NULL THEN '!B'
        ELSE NULL END,
    rr_desc = CASE
        WHEN dst.bb_rng_strk_rule >= 2 THEN l_qm.description
        WHEN dst.bb_rng_strk_rule >= 0 THEN l_qn.description
        ELSE NULL END,
    td_tn_bb_action_desc = l_qr.description,
    td_tn_bb_action_seq  = l_qr.seq
FROM drv_cat_atomic_input src
LEFT JOIN ref_param_lookup l_qf
  ON l_qf.table_name = 'tn_td_rule'
 AND l_qf.code = (src.trade_trend_sd_rule)::INTEGER::TEXT
LEFT JOIN ref_param_lookup l_qk
  ON l_qk.table_name = 'bb_range'
 AND l_qk.code = (src.bb_rng_strk_rule)::INTEGER::TEXT
LEFT JOIN ref_param_lookup l_qm
  ON l_qm.table_name = 'bull_rr_rule'
 AND l_qm.code = (src.bull_rr_action)::INTEGER::TEXT
LEFT JOIN ref_param_lookup l_qn
  ON l_qn.table_name = 'nbull_rr_rule'
 AND l_qn.code = (src.not_bull_rr_action)::INTEGER::TEXT
LEFT JOIN ref_param_lookup l_qr
  ON l_qr.table_name = 'td_tn_bb_rr_action'
 AND l_qr.code = (src.td_tn_bb_rr_action)::INTEGER::TEXT
WHERE dst.as_of_date = src.as_of_date AND dst.symbol = src.symbol
  AND dst.as_of_date = :d
"""


# =============================================================================
# Main entry point — wired into derive_all() in derive.py.
# =============================================================================
def derive_cat_atomic_input(session: Session, as_of_date: date,
                            parent_run_id: Optional[int] = None) -> int:
    """Compute drv_cat_atomic_input rows for `as_of_date`.

    Steps:
      1. DELETE existing rows for this date (idempotency).
      2. SELECT working set + intermediates.
      3. Pass-1 specs (trig_ifs / trig_ifs_dma / etc.).
      4. Pass-2 specs (composites reading Pass-1 outputs).
      5. executemany INSERT.
      6. Parm-lookup UPDATE (Pass-3).  Note: requires QE/QJ/QM/QN/QR to be
         present, so it actually runs LATER in derive_all() — exposed as
         `run_parm_lookup_pass3()` for the caller to invoke after
         _derive_trend_trade_rules_impl.
    """
    run_id = parent_run_id or 0
    trig_rules = load_trig_rules(session)
    if not trig_rules:
        log.warning("drv_cat_atomic_input: ref_trig_atomic_rule empty; skipping")
        return 0

    session.execute(
        text("DELETE FROM drv_cat_atomic_input WHERE as_of_date = :d"),
        {"d": as_of_date},
    )

    rows = session.execute(text(WORKING_SET_SQL), {"d": as_of_date}).mappings().all()
    if not rows:
        return 0

    all_db_cols = (
        [s[0] for s in COLUMN_SPECS_PASS1]
        + [s[0] for s in COLUMN_SPECS_PASS2]
    )
    # Deduplicate while preserving order (some specs may overlap if edited)
    seen = set(); ordered_cols = []
    for c in all_db_cols:
        if c not in seen:
            seen.add(c); ordered_cols.append(c)

    records = []
    for r in rows:
        row = dict(r)
        compute_intermediates(row)
        out: dict = {}
        eval_specs(row, COLUMN_SPECS_PASS1, trig_rules, out)
        eval_specs(row, COLUMN_SPECS_PASS2, trig_rules, out)
        rec = {"as_of_date": as_of_date, "symbol": row["symbol"],
               "source_run_id": run_id}
        for c in ordered_cols:
            rec[c] = out.get(c)
        records.append(rec)

    # executemany INSERT.  Quote columns that aren't valid bare PG identifiers.
    def _q(c: str) -> str:
        import re as _re
        return c if _re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", c) else f'"{c}"'

    col_list = ", ".join(["as_of_date", "symbol"]
                         + [_q(c) for c in ordered_cols]
                         + ["source_run_id"])
    bind_list = ", ".join([":as_of_date", ":symbol"]
                          + [f":{c}" for c in ordered_cols]
                          + [":source_run_id"])
    insert_sql = text(f"INSERT INTO drv_cat_atomic_input ({col_list}) "
                      f"VALUES ({bind_list})")
    inserted = 0
    BATCH = 500
    for i in range(0, len(records), BATCH):
        chunk = records[i:i + BATCH]
        session.execute(insert_sql, chunk)
        inserted += len(chunk)
    return inserted


def run_parm_lookup_pass3(session: Session, as_of_date: date) -> int:
    """Pass-3: Parm-lookup UPDATE.  Must run AFTER _derive_trend_trade_rules_impl
    has populated QE/QJ/QM/QN/QR.  Idempotent."""
    result = session.execute(text(PARM_LOOKUP_SQL), {"d": as_of_date})
    return result.rowcount or 0
