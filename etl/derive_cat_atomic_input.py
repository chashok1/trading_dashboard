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

from etl._derive_common import _safe_div  # TASK_56: consolidated

log = logging.getLogger(__name__)

# =============================================================================
# TASK_67: revertible bull-gate threshold cache.
# Populated at derive time by load_bull_gate_thresholds(session) from
# ref_threshold_override.  Falls back to hardcoded Excel-relic values when the
# table is absent or when active_source='original'.
# The expr functions (_bull_expr etc.) read from this dict; never import it
# externally — use load_bull_gate_thresholds() to refresh before a derive run.
# =============================================================================
_BULL_GATE_THRESHOLDS: dict = {}

# Hardcoded fallback values (Excel originals).
_BULL_GATE_DEFAULTS: dict = {
    "bull.pos_hi.JN": 3.0,
    "bull.pos_hi.JQ": 2.0,
    "bull.pos_hi.JV": 2.0,
    "bull.pos_hi.LZ": 3.0,
    "bull.pos_lo.JN": 2.0,
    "bull.pos_lo.JQ": 2.0,
    "bull.pos_lo.JV": 2.0,
    "bull.pos_lo.LZ": 2.0,
    "bull.neg_hi.JN": -3.0,
    "bull.neg_hi.JQ": -2.0,
    "bull.neg_hi.JV": -2.0,
    "bull.neg_hi.LY": 3.0,
    "bull.neg_lo.JN": -2.0,
    "bull.neg_lo.JQ": -2.0,
    "bull.neg_lo.JV": -2.0,
    "bull.neg_lo.LY": 2.0,
    "perforbull.hi": 3.0,
    "perforbull.lo": 3.0,
    "bb_bull.hi.LP": 3.0,
    "bb_bull.hi.LS": 3.0,
    "bb_bull.lo.LP": 3.0,
    "bb_bull.lo.LS": 3.0,
}


def _thr(key: str) -> float:
    """Return the active threshold for key, falling back to the hardcoded default."""
    v = _BULL_GATE_THRESHOLDS.get(key)
    if v is None:
        return _BULL_GATE_DEFAULTS.get(key, 0.0)
    return float(v)


def load_bull_gate_thresholds(session: Session) -> None:
    """Refresh the module-level _BULL_GATE_THRESHOLDS dict from ref_threshold_override.

    Reads the active value (original_value or calculated_value per active_source).
    Safe to call even if the table does not exist — leaves the dict unchanged.
    """
    global _BULL_GATE_THRESHOLDS
    try:
        rows = session.execute(text("""
            SELECT rule_key,
                   CASE WHEN active_source = 'calculated' AND calculated_value IS NOT NULL
                        THEN calculated_value
                        ELSE original_value
                   END AS active_value
            FROM ref_threshold_override
        """)).all()
        _BULL_GATE_THRESHOLDS = {r[0]: float(r[1]) for r in rows if r[1] is not None}
        log.debug("load_bull_gate_thresholds: loaded %d keys", len(_BULL_GATE_THRESHOLDS))
    except Exception as e:
        log.debug("load_bull_gate_thresholds: table unavailable (%s), using defaults", e)


# =============================================================================
# Step 1 — working-set SELECT.
# Mirrors the latest-snapshot-<=D pattern used by the component derive functions.
# Accepts bind params :d (date) and :win (interval string, e.g. '30 days').
# =============================================================================
WORKING_SET_SQL = """
WITH p AS (SELECT CAST(:d AS date) AS d),
syms AS (
    -- Gate: symbol must have a current price in hist_tl (TOS Level, daily intraday feed)
    -- within the last 7 days. This excludes symbols removed from the TOS watchlist —
    -- their hist_tl rows go stale within a week and they naturally drop out.
    -- hist_tl is preferred over drv_quote because drv_quote can carry stale prices
    -- derived from months-old hist_td/hist_tl rows.
    SELECT DISTINCT s FROM (
        SELECT ticker AS s FROM ref_sector
        UNION SELECT tos_symbol AS s FROM hist_tl WHERE snapshot_date <= (SELECT d FROM p)
        UNION SELECT tos_symbol AS s FROM hist_td WHERE snapshot_date <= (SELECT d FROM p)
        UNION SELECT tos_symbol AS s FROM hist_tw WHERE snapshot_date <= (SELECT d FROM p)
    ) u WHERE s IS NOT NULL
      AND EXISTS (
          SELECT 1 FROM hist_tl tl
          WHERE tl.tos_symbol = u.s
            AND tl.snapshot_date = (SELECT MAX(snapshot_date) FROM hist_tl
                                     WHERE snapshot_date <= (SELECT d FROM p))
      )
),
td AS (
    -- 7-day recency gate: only use TOSD data loaded within the last 7 days.
    -- Symbols removed from the TOS watchlist have stale rows (months old);
    -- using old trend/trade line values against today's price is meaningless.
    SELECT DISTINCT ON (tos_symbol) tos_symbol,
           a_trend_value, a_trade_value, a_bb_top, a_bb_bottom,
           a_bb_streak, a_bb_high_low, a_bb_high_low_days,
           a_iv_percentile, a_hv_percentile,
           a_bb_top_slope, a_bb_bot_slope,
           historical_vol,
           high_price  AS td_high,  -- EK: prior session high for MAX(EH,EK) in EO/EP
           low_price   AS td_low,   -- EL: prior session low  for MIN(EI,EL) in EP
           rsi         AS td_rsi,   -- closing RSI from TOSD (preferred over intraday TOSL RSI)
           last_price  AS td_last   -- EF: prior session close (CN = D_Last in MA sheet)
    FROM hist_td WHERE snapshot_date <= (SELECT d FROM p)
      AND snapshot_date >= (SELECT d FROM p) - INTERVAL '7 days'
    ORDER BY tos_symbol, snapshot_date DESC, sequence DESC
),
td_fb_trend AS (
    -- Fallback: latest non-null a_trend_value within 7 days (handles single-day NaN exports).
    -- Separate from trade fallback because one column can be NaN on a date where the other is valid.
    SELECT DISTINCT ON (tos_symbol) tos_symbol, a_trend_value AS fb_trend
    FROM hist_td WHERE snapshot_date <= (SELECT d FROM p)
      AND snapshot_date >= (SELECT d FROM p) - INTERVAL '7 days'
      AND a_trend_value IS NOT NULL
    ORDER BY tos_symbol, snapshot_date DESC, sequence DESC
),
td_fb_trade AS (
    -- Fallback: latest non-null a_trade_value within 7 days.
    SELECT DISTINCT ON (tos_symbol) tos_symbol, a_trade_value AS fb_trade
    FROM hist_td WHERE snapshot_date <= (SELECT d FROM p)
      AND snapshot_date >= (SELECT d FROM p) - INTERVAL '7 days'
      AND a_trade_value IS NOT NULL
    ORDER BY tos_symbol, snapshot_date DESC, sequence DESC
),
td_prior AS (
    -- Prior snapshot's a_bb_bottom and a_bb_top for DU/DV fallback in EC/ED
    SELECT DISTINCT ON (tos_symbol) tos_symbol,
           a_bb_bottom AS bb_bot_prev, a_bb_top AS bb_top_prev
    FROM hist_td WHERE snapshot_date < (SELECT d FROM p)
    ORDER BY tos_symbol, snapshot_date DESC, sequence DESC
),
tw AS (
    -- 14-day recency gate: TOSW is weekly so legitimate gap can be up to 10 days.
    -- Symbols removed from the weekly watchlist have stale rows (months old); exclude them.
    SELECT DISTINCT ON (tos_symbol) tos_symbol, snapshot_date AS tw_snap,
           standard_dev, sma_20, sma_50, sma_200,
           a_macd_brr, a_macdh_d_brr, a_macdays_streak,
           a_3mn_high, a_3mn_low, a_3mn_high_low, a_3wk_high_low,
           a_perf_2m, a_perf_2wk, a_perf_3d,
           a_volume_spike, volume, volume_avg_3m, volume_rate_change,
           a_earnings_days, high_52, low_52
    FROM hist_tw WHERE snapshot_date <= (SELECT d FROM p)
      AND snapshot_date >= (SELECT d FROM p) - INTERVAL '14 days'
    ORDER BY tos_symbol, snapshot_date DESC, sequence DESC
),
tw_fb AS (
    -- Fallback: latest non-null a_macdays_streak within 14 days.
    SELECT DISTINCT ON (tos_symbol) tos_symbol,
           a_macdays_streak AS fb_streak
    FROM hist_tw WHERE snapshot_date <= (SELECT d FROM p)
      AND snapshot_date >= (SELECT d FROM p) - INTERVAL '14 days'
      AND a_macdays_streak IS NOT NULL
    ORDER BY tos_symbol, snapshot_date DESC
),
med AS (
    -- True rolling median of standard_dev over the trailing :win calendar days.
    -- percentile_cont(0.5) gives the statistical median used as the AC cap:
    --   AC = LEAST(standard_dev, median_sd) = MIN(latest SD, rolling-median SD).
    -- Window size is read from ref_settings.sd_median_window_days (default 30).
    SELECT tos_symbol,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY standard_dev) AS median_sd
    FROM hist_tw
    WHERE snapshot_date <= (SELECT d FROM p)
      AND snapshot_date >= (SELECT d FROM p) - CAST(:win AS INTERVAL)
      AND standard_dev IS NOT NULL
    GROUP BY tos_symbol
),
dq AS (
    SELECT DISTINCT ON (tos_symbol) tos_symbol, last_price, net_chng, pct_change,
           open_price, high_price, low_price, rsi, imp_volatility
    FROM drv_quote WHERE as_of_date <= (SELECT d FROM p)
    ORDER BY tos_symbol, as_of_date DESC
),
tl AS (
    -- Current day volume from TOSL — used as wv for GB (Current Volume Rule).
    -- Reflects today's actual trading volume vs the 3M weekly average from TOSW.
    SELECT DISTINCT ON (tos_symbol) tos_symbol, volume AS tl_volume
    FROM hist_tl WHERE snapshot_date = (SELECT d FROM p)
    ORDER BY tos_symbol, loaded_at DESC
),
rr AS (
    SELECT tos_symbol, lrr, trr
    FROM drv_rr WHERE as_of_date = (SELECT d FROM p)
)
SELECT s.s AS tos_symbol,
       -- hist_td (rule input bases); COALESCE falls back to latest non-null row
       -- for columns that can be null on the most-recent export date (NaN → NULL).
       COALESCE(td.a_trend_value, td_fb_trend.fb_trend) AS a_trend_value,
       COALESCE(td.a_trade_value, td_fb_trade.fb_trade) AS a_trade_value,
       td.a_bb_top, td.a_bb_bottom,
       td.a_bb_streak, td.a_bb_high_low, td.a_bb_high_low_days,
       td.a_iv_percentile, td.a_hv_percentile,
       td.a_bb_top_slope, td.a_bb_bot_slope,
       td.historical_vol, td.td_high, td.td_low, td.td_rsi, td.td_last,
       dq.imp_volatility, dq.rsi,
       -- prior BB values for slope calculations (EY/FC)
       td_prior.bb_bot_prev, td_prior.bb_top_prev,
       -- hist_tw
       tw.standard_dev, tw.sma_50, tw.sma_200,
       tw.a_macd_brr, tw.a_macdh_d_brr,
       COALESCE(tw.a_macdays_streak, tw_fb.fb_streak) AS a_macdays_streak,
       tw.a_3mn_high, tw.a_3mn_low, tw.a_3mn_high_low, tw.a_3wk_high_low,
       tw.a_perf_2m, tw.a_perf_2wk, tw.a_perf_3d,
       tw.a_volume_spike, tw.volume, tw.volume_avg_3m, tw.volume_rate_change,
       -- earnings_days is a TOSW days-COUNT (no date); a carried-forward weekly
       -- snapshot must be decremented by elapsed days to stay current. NULL passes through.
       CASE WHEN tw.a_earnings_days IS NULL THEN NULL
            ELSE tw.a_earnings_days - ((SELECT d FROM p) - tw.tw_snap)
       END AS a_earnings_days,
       tw.high_52, tw.low_52,
       med.median_sd,
       -- hist_tl current volume (for GB = Current Volume Rule numerator)
       tl.tl_volume,
       -- drv_quote
       dq.last_price, dq.net_chng, dq.pct_change,
       dq.high_price AS high_today, dq.low_price AS low_today,
       -- drv_rr (lrr/trr already have RR→BB fallback baked in)
       rr.lrr, rr.trr
FROM syms s
LEFT JOIN td           ON td.tos_symbol           = s.s
LEFT JOIN td_fb_trend  ON td_fb_trend.tos_symbol  = s.s
LEFT JOIN td_fb_trade  ON td_fb_trade.tos_symbol  = s.s
LEFT JOIN td_prior ON td_prior.tos_symbol = s.s
LEFT JOIN tw     ON tw.tos_symbol     = s.s
LEFT JOIN tw_fb  ON tw_fb.tos_symbol  = s.s
LEFT JOIN med ON med.tos_symbol = s.s
LEFT JOIN tl  ON tl.tos_symbol  = s.s
LEFT JOIN dq  ON dq.tos_symbol  = s.s
LEFT JOIN rr  ON rr.tos_symbol  = s.s
"""


# =============================================================================
# Step 2 — MA-sheet intermediates.  All per-row arithmetic.
# Source-of-truth: docs/ma_columns_v2.csv formula column.
# =============================================================================
# _safe_div imported from etl._derive_common (TASK_56).


def _f(v) -> Optional[float]:
    """Numeric coercion -> Optional[float]."""
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _days_from_frac(x: Optional[float], *, negate: bool = False) -> Optional[float]:
    """Excel pattern: 100 * MOD(x, TRUNC(x)) — extract fractional-days from
    composite-encoded source.  If |x|<1, treat the whole thing as fraction.
    `negate=True` for the BH/BL variants which Excel prefixes with -100.
    """
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    sign = -1.0 if negate else 1.0
    if -1.0 < v < 1.0:
        return sign * 100.0 * v
    import math
    tr = math.trunc(v)
    if tr == 0:
        return 0.0
    # Excel MOD(x, n) returns x - n*INT(x/n).  For negative x and negative n
    # this matches Python's fmod behaviour (same-sign-as-dividend).
    frac = math.fmod(v, tr)
    return sign * 100.0 * frac


def _decode_bb_streak(a_bb_streak: Optional[float]) -> dict:
    """Decode the BB_Streak composite numeric (TD!BC = MA!AS).

    Excel pattern:
      AS = a_bb_streak                      (e.g. 8213.01)
      AT = TRUNC(AS)                        (8213)
      AU = AT - AY*1000                     (213)
      AV = ABS(TRUNC(AU/100))               (2 — current threshold state)
      AW = IF(AV=1, -1, 1)                  (1 — threshold-crossover flag)
      AX = NUMBERVALUE(RIGHT(AU, 2))        (13 — BBThresh CO Days)
      AY = TRUNC(AT/1000)                   (8 — BB Streak count)
      AZ = ROUND((ABS(AS)-ABS(AT))*100, 0)  (1 — BB Streak Days)

    Also derives AQ (BBHighDays = TRUNC(AP)) and AR (BBLowDays = 100*(AP-AQ))
    where AP = a_bb_high_low_days (sibling field).
    """
    import math
    AS_ = _f(a_bb_streak)
    if AS_ is None:
        return dict(AS=None, AT=None, AU=None, AV=None, AW=None, AX=None,
                    AX2=None, AY=None, AZ=None)
    AT_ = math.trunc(AS_)
    AY_ = math.trunc(AT_ / 1000)
    AU_ = AT_ - AY_ * 1000
    AV_ = abs(math.trunc(AU_ / 100))
    AW_ = -1.0 if AV_ == 1 else 1.0
    # RIGHT(AU, 2) = last two digits of |AU|.  Use abs to mirror Excel's NUMBERVALUE.
    AX_ = abs(AU_) % 100
    # AX2 = signed version used by BBThresh_CO_Days2.
    # Excel IFS: AX>=hi→wa; AX>=lo→wbt; AY>=0→wb; AY<0→-wb
    # (AX<-hi and AX<-lo never fire since AX=abs(AU)%100 >= 0 always)
    # So: in/above zone (AX>=2) → always positive; below zone (AX<2) → sign from AY.
    AX2_ = AX_ if AX_ >= 2 else AX_ * (1.0 if AY_ >= 0 else -1.0)
    AZ_ = round((abs(AS_) - abs(AT_)) * 100, 0)
    return dict(AS=AS_, AT=AT_, AU=AU_, AV=AV_, AW=AW_, AX=AX_, AX2=AX2_, AY=AY_, AZ=AZ_)


def _decode_vs(a_volume_spike: Optional[float], AD: Optional[float]) -> dict:
    """Decode the FH packed string for VS rules.

    Excel pattern:
      FF = a_volume_spike (signed, e.g. -200443.44)
      FG = ABS(NUMBERVALUE(SUBSTITUTE(FF, "NaN", 0)))                (200443.44)
      FH = RIGHT("0000000000"&FG&REPT("0",9-LEN(FG)), 10)           ("0200443.44")
      FI = NUMBERVALUE(LEFT(FH, 2))         VS Volume Spike   (chars 1-2)
      FJ = NUMBERVALUE(MID(FH, 3, 3))       VS Price Change   (chars 3-5)
      FK = SIGN(FF) * FJ / (AD * 100)       VS Price Change SD
      FL = NUMBERVALUE(MID(FH, 6, 2))       VS Volatility     (chars 6-7)
      FM = NUMBERVALUE(RIGHT(FH, 2))        VS Days           (chars 9-10)
    """
    FF = _f(a_volume_spike)
    if FF is None or FF == 0:
        return dict(FF=FF, FH=None, FI=0, FJ=0, FK=0, FL=0, FM=0)
    FG = abs(FF)
    fg_str = f"{FG:.2f}"  # numeric->string with 2 decimals
    # Faithfully reproduces Excel:
    #   FH = RIGHT("0000000000" & FG & REPT("0", 9-LEN(FG)), 10)
    # Step 1: right-pad fg_str to at least 9 chars with trailing zeros.
    # Step 2: prepend 10 leading zeros.
    # Step 3: take the last 10 chars.
    # This differs from the previous implementation when len(fg_str) < 9;
    # for fg_str >= 9 chars the REPT term is "" and the result is identical.
    rept_pad = max(0, 9 - len(fg_str))
    padded = "0000000000" + fg_str + ("0" * rept_pad)
    FH = padded[-10:]
    def _nv(s: str) -> int:
        try: return int(s)
        except ValueError:
            try: return int(float(s))
            except ValueError: return 0
    FI = _nv(FH[0:2])
    FJ = _nv(FH[2:5])
    FL = _nv(FH[5:7])
    FM = _nv(FH[8:10])
    sign_ff = 1.0 if FF > 0 else (-1.0 if FF < 0 else 0.0)
    FK = (sign_ff * FJ / (AD * 100.0)) if (AD and AD != 0) else None
    return dict(FF=FF, FH=FH, FI=FI, FJ=FJ, FK=FK, FL=FL, FM=FM)


def compute_intermediates(row: dict) -> dict:
    """Compute every MA-sheet intermediate this deriver needs.

    Source-of-truth: docs/ma_columns_v2.csv formulas.  Adds 40+ derived keys
    to `row` (AC, AD, AG, AH, AI, AS..AZ, AQ, AR, BB, BC, BE, BF, BJ, BK,
    BN, BO, BQ..CA, EC, ED, EE, EO, EP, EQ, ER, ES, ET, EU, FF..FM, FR, GB).
    """
    import math
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
    EC   = _f(row.get("lrr"))                         # drv_rr.lrr — RR bottom, BB fallback already applied
    ED   = _f(row.get("trr"))                         # drv_rr.trr — RR top
    DU   = _f(row.get("bb_bot_prev"))                # BB_Bot_Prev — for BB slope calcs (EY/FC)
    DV   = _f(row.get("bb_top_prev"))                # BB_Top_Prev — for BB slope calcs
    # EK/EL: prior session high/low from hist_td.
    # Excel EO = (ED - IF(EH>EK, EH, EK)) / AC  →  uses MAX(EH, EK).
    # EH = today's intraday high (drv_quote), EK = prior day's high (hist_td).
    # Taking MAX ensures the reference high doesn't drop early in a new session.
    EF   = _f(row.get("td_last"))                # MA!EF = CN = D_Last (prior session close)
    EK   = _f(row.get("td_high"))
    EL   = _f(row.get("td_low"))
    AP   = _f(row.get("a_bb_high_low_days"))         # MA!AP source
    AJ   = _f(row.get("a_bb_high_low"))              # MA!AJ source — TOS composite

    # ---- BB_Streak struct (AS/AT/AU/AV/AW/AX/AY/AZ) ----
    bbs = _decode_bb_streak(row.get("a_bb_streak"))
    # AQ = TRUNC(AP) BBHighDays.  AR = ABS(100*(AP-AQ)) BBLowDays.
    # round() removes IEEE-754 noise: 100*(1.05-1)=5.000...004 → 5.
    # AP's decimal always encodes a 2-digit integer count so rounding is correct.
    if AP is not None:
        AQ = math.trunc(AP)
        AR = round(abs(100.0 * (AP - AQ)))
    else:
        AQ = AR = None

    # ---- AJ/AK/AL/AM/AN decoding chain (a_bb_high_low) ----
    # Per docs/drv_cat_atomic_input_logic.md:
    #   AJ = sign(lasthighlow) * (abs(round(lasthighlow*100,0)) + bar/100)
    #   AK = TRUNC(AJ)           (sign × abs(highlow×100))
    #   AL = AK/100              (BB touched value in price units)
    #   AM = ABS(ROUND(100*(AJ-AK),0))   (days since touched)
    #   AN = IFS(AL<0 & AM>0 & |AL|<D, 1,        # bottom touched, price now above
    #            AL>0 & AM>0 & |AL|>D, -1,       # top touched, price now below
    #            TRUE, SIGN(AL))
    if AJ is not None:
        AK = math.trunc(AJ)
        AL = AK / 100.0
        AM = abs(round(100.0 * (AJ - AK), 0))
    else:
        AK = AL = AM = None
    # AN = BB_Direction1 — implements user-supplied IFS logic.
    if AL is None or AM is None or D is None:
        AN = None
    elif AL < 0 and AM > 0 and abs(AL) < D:
        AN = 1.0     # bottom touched ≥1 day back, price now above → going up
    elif AL > 0 and AM > 0 and abs(AL) > D:
        AN = -1.0    # top touched ≥1 day back, price now below → going down
    else:
        AN = 1.0 if AL > 0 else (-1.0 if AL < 0 else 0.0)  # SIGN(AL)
    # AO = (D - ABS(AL)) / AC  (BBHighLow_SD)
    AO = None  # set below once AC is known

    # AC = MIN(standard_dev, rolling_median_sd) — matches the Excel AC formula =MIN(AA,AB).
    # AB = current standard_dev (hist_tw.standard_dev for anchor date).
    # AA = rolling median_sd (true percentile_cont(0.5) over last sd_median_window_days days).
    # Null-safe: if either is None, use the other; if both None, AC is None.
    if AB is not None and AA is not None:
        AC = min(AB, AA)
    elif AB is not None:
        AC = AB
    else:
        AC = AA
    # AD = AC / D
    AD = _safe_div(AC, D) if D and D != 0 else None

    # AO = (D - ABS(AL)) / AC.  AL comes from the decoded chain above.
    if D is not None and AL is not None and AC:
        AO = _safe_div(D - abs(AL), AC)

    # AG = IF(D=AE, 0.1, (D-AE)/AC)         Trend_sd
    if D is not None and AE is not None:
        AG = 0.1 if D == AE else _safe_div(D - AE, AC)
    else:
        AG = None
    AH = _safe_div(D - AF, AC) if D is not None and AF is not None else None
    AI = _safe_div(AF - AE, AC) if AF is not None and AE is not None else None
    BB = _safe_div(D - BA, AC) if D is not None and BA is not None else None
    BC = _days_from_frac(BA)                          # 3mnLowDays
    BE = _safe_div(D - BD, AC) if D is not None and BD is not None else None
    BF = _days_from_frac(BD)                          # 3mnHighDays
    # BI = ABS(BH); BJ = (D-BI)/AC.  Likewise BM = ABS(BL); BN = (D-BM)/AC.
    BI_v = abs(BH) if BH is not None else None
    BM_v = abs(BL) if BL is not None else None
    BJ = _safe_div(D - BI_v, AC) if D is not None and BI_v is not None else None
    BK = _days_from_frac(BH, negate=True)             # 3mnHighLowDays
    BN = _safe_div(D - BM_v, AC) if D is not None and BM_v is not None else None
    BO = _days_from_frac(BL, negate=True)             # 3wkHighLowDays
    BQ = AG  # Perf3M_sd  ==  Trend_sd by formula
    BS = _safe_div(BR, (AD * 100)) if AD else None
    BU = AH  # Perf3W_sd  ==  Trade_sd
    BW = _safe_div(BV, (AD * 100)) if AD else None
    BY = _safe_div(BX, (AD * 100)) if AD else None
    BZ = _safe_div(100 * D, (100 + BX)) if D is not None and BX is not None else None
    # CA = Perf1D_sd. Python scale: net_chng/AC (~100× smaller than Excel's pct_change%×D/AC).
    # The perf1d_sd_rule thresholds in ref_trig_atomic_rule are calibrated to THIS scale —
    # do not change this formula without also re-calibrating those thresholds.
    # round() removes IEEE-754 noise at threshold boundaries (e.g. -1.000...002 → -1.0)
    _ca = _safe_div(G_, AC)
    CA = round(_ca, 10) if _ca is not None else None  # Perf1D_sd

    # EC/ED come from drv_rr which already handles RR→BB fallback
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
    EQ = _safe_div(ED - AE, AC) if ED is not None and AE is not None else None
    ER = _safe_div(EC - AF, AC) if EC is not None and AF is not None else None

    # ---- ES / ET / EU — Sd-normalized RR risk indices (KI/KJ/KK inputs) ----
    # DQ = high_today, DM = last_price, DR = low_today (from drv_quote)
    DQ = _f(row.get("high_today"))
    DM = _f(row.get("last_price"))
    DR = _f(row.get("low_today"))
    ES = _safe_div(DQ - ED, AC) if DQ is not None and ED is not None else None
    ET = _safe_div(DM - (ED + EC) / 2.0, AC) if DM is not None and EC is not None and ED is not None else None
    EU = _safe_div(DR - EC, AC) if DR is not None and EC is not None else None

    # ---- VS struct ----
    vs = _decode_vs(row.get("a_volume_spike"), AD)
    # FR IVHV = DT*100/CV  (with zero-guard)
    DT_  = _f(row.get("imp_volatility"))
    CV_  = _f(row.get("historical_vol"))
    # round to drop IEEE float noise at a threshold (e.g. 0.35*100/0.28 = 125 is
    # stored as 124.99999999999996) so IVHV / IVHV-puts grade the same band as Excel.
    FR = 0.0 if (not DT_ or not CV_) else round(DT_ * 100.0 / CV_, 9)
    # GB Vlm 3m % = (current_volume - VolumeAvg3m) / VolumeAvg3m * 100.
    # Excel Dash!AB25 flag uses TOSW (weekly) volume as numerator (FT=W_Vlm).
    # Falls back to TOSL (tl_volume) when TOSW has no data for the symbol.
    wv = _f(row.get("volume")) or _f(row.get("tl_volume"))
    av3 = _f(row.get("volume_avg_3m"))
    if wv is not None and av3 and av3 != 0:
        GB = ((wv - av3) / av3) * 100.0
    else:
        GB = 0.0

    row.update(dict(
        AC=AC, AD=AD, AG=AG, AH=AH, AI=AI,
        AJ=AJ, AK=AK, AL=AL, AM=AM, AN=AN, AO=AO, AP=AP, AQ=AQ, AR=AR,
        AS=bbs["AS"], AT=bbs["AT"], AU=bbs["AU"], AV=bbs["AV"], AW=bbs["AW"],
        AX=bbs["AX"], AX2=bbs["AX2"], AY=bbs["AY"], AZ=bbs["AZ"],
        BB=BB, BC=BC, BE=BE, BF=BF, BJ=BJ, BK=BK, BN=BN, BO=BO,
        BQ=BQ, BS=BS, BU=BU, BW=BW, BY=BY, BZ=BZ, CA=CA,
        EF=EF, EC=EC, ED=ED, EE=EE, EO=EO, EP=EP, EQ=EQ, ER=ER, ES=ES, ET=ET, EU=EU,
        FF=vs["FF"], FH=vs["FH"], FI=vs["FI"], FJ=vs["FJ"],
        FK=vs["FK"], FL=vs["FL"], FM=vs["FM"], FR=FR, GB=GB,
    ))
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
    # AC — volatility scale (MIN(standard_dev, median_sd)); stored so UI can display it
    ("ac", "passthru", "AC", None, None),
    # ---- JF block opener is just a marker ----
    # JG / JH — sign-with-zero-as-neg over CK / CI (MACDH/MACD direction)
    ("macdh_direction",   "sign_zero_neg", "a_macdh_d_brr", None, None),     # JG
    ("macd_direction",    "sign_zero_neg", "a_macd_brr",    None, None),     # JH
    # JI — passthrough of AN (BB_Direction1).  AN now properly derived from
    # a_bb_high_low composite via compute_intermediates (per user spec
    # 2026-05-27 v3).  Returns +1 if BB bottom touched and price recovered,
    # -1 if BB top touched and price fell, else SIGN(AL).
    ("bb_direction",      "passthru", "AN", None, None),                       # JI
    # JJ — IF(AX=1, AW, 0).  AX = BBThresh CO Days, AW = threshold-crossover.
    ("bb_threshold",      "composite", None, None,
        (lambda r,o: (_f(r.get("AW")) or 0) if _f(r.get("AX")) == 1 else 0.0)),# JJ
    # JK BBThresh CO Days — trig_ifs on AX
    ("bbthresh_co_days",  "trig_ifs", "AX", "bbthresh_co_days",  None),        # JK
    ("bbthresh_co_days2", "trig_ifs", "AX2", "bbthresh_co_days2", None),       # JL (signed: bearish streak negates score)
    # JM Trade Cross Over — composite (D/AF/EF/J/I).  EF=prev_close not sourced;
    # approximate via BZ (Perf3D_Value as proxy for prev_close trajectory).
    ("trade_cross_over",  "composite", None, None,
        (lambda r,o: _crossover(r.get("last_price"), r.get("a_trade_value"),
                                r.get("EF"), r.get("high_today"), r.get("low_today")))),  # JM
    ("trend_cross_over",  "composite", None, None,
        (lambda r,o: _crossover_trend(r.get("last_price"), r.get("a_trend_value"),
                                      r.get("BZ"), r.get("EF"),
                                      r.get("high_today"), r.get("low_today")))),          # JP
    # JN — Trade-Rule (trig_ifs on AH = Trade_sd)
    ("trade_rule",        "trig_ifs", "AH", "trade_rule",  None),             # JN
    ("not_trade_rule",    "negate",   "trade_rule", None, None),              # JO
    # JP Trend Cross Over — deferred (needs EF/J/I/BZ).
    ("trend_rule",        "trig_ifs", "AG", "trend_rule",  None),             # JQ
    ("not_trend_rule",    "negate",   "trend_rule", None, None),              # JR
    # JS Trend Trade Dep Rule -> composite (Pass-2)
    # JT TrTn Relation -> composite (Pass-2)
    # JU !TrTn Relation -> negate(JT)
    ("trade_trend_sd_rule", "trig_ifs", "AI", "trade_trend_sd_rule", None),    # JV
    ("brrpct_rule",         "trig_ifs", "EE", "brrpct_rule",      {"simple": True}),  # JW
    ("brrpct_lrr",          "trig_ifs", "EE", "brrpct_lrr",    {"simple": True}),  # JX
    ("brrpct_r2",           "trig_ifs", "EE", "brrpct_r2",     {"simple": True}),  # JY
    ("brrpct_lrr2",         "trig_ifs", "EE", "brrpct_lrr2",   {"simple": True}),  # JZ
    ("brrpct_trr",          "trig_ifs", "EE", "brrpct_trr",    {"simple": True}),  # KA
    ("brrpct_puts",         "trig_ifs", "EE", "brrpct_puts",      {"simple": True}),  # KB
    ("brrpct_trr_puts",     "trig_ifs", "EE", "brrpct_trr_puts",  {"simple": True}),  # KC
    # KD BRR% Dir -> composite (Pass-2; reads JI/JG/LG/JW/KB)
    ("high_trr",            "trig_ifs", "EO", "high_trr",        {"simple": True}),  # KE (zone lo=0: use 3-clause)
    ("low_lrr",             "trig_ifs", "EP", "low_lrr",         {"simple": True}),  # KF (zone lo=0: use 3-clause)
    ("trend_below_trr",     "composite", None, None,
        (lambda r,o: -1.0 if (r.get("EQ") or 0) < 0 else 0.0)),                 # KG
    ("lrr_above_trade",     "composite", None, None,
        (lambda r,o: 1.0 if (r.get("ER") or 0) > 0 else 0.0)),                  # KH
    # KI/KJ/KK TRR/MRR/LRR_Idx — 3-clause trig_ifs on ES/ET/EU.
    # DQ/DM/DR come from drv_quote (high/last/low), matching toggle="Y" behaviour.
    ("trr_idx",            "trig_ifs", "ES", "trr_idx", {"simple": True}),      # KI (asymmetric zone: use 3-clause eval_atomic_rule)
    ("mrr_idx",            "trig_ifs", "ET", "mrr_idx", None),                  # KJ (symmetric zone: 6-clause = 3-clause)
    ("lrr_idx",            "trig_ifs", "EU", "lrr_idx", {"simple": True}),     # KK (asymmetric zone: use 3-clause eval_atomic_rule)
    # KL HVAbsolute -- input CV (historical_vol), but Trig key 'HVAbsolute' uses CV.
    ("hvabsolute",          "trig_ifs", "historical_vol", "hvabsolute", None), # KL
    # KM IVAbsolute -- zero-guarded by DT (imp_volatility)
    ("ivabsolute",          "zero_guard_trig_ifs", "imp_volatility",
        "ivabsolute", ("imp_volatility",)),                                     # KM
    # KN/KO IV percentile (zero-guarded by DT, CX)
    ("ivpercentile",        "zero_guard_trig_ifs", "a_iv_percentile",
        "ivpercentile", ("imp_volatility", "a_iv_percentile")),                 # KN
    # "Puts" variants use STRICT > in Excel — note strict=True.
    ("ivpercentile_puts",   "zero_guard_trig_ifs", "a_iv_percentile",
        "ivpercentile_puts",
        {"guards": ("imp_volatility", "a_iv_percentile"), "strict": True}),    # KO
    ("hvpercentile",        "zero_guard_trig_ifs", "a_hv_percentile",
        "hvpercentile", ("imp_volatility",)),                                   # KP
    ("hvpercentile_puts",   "zero_guard_trig_ifs", "a_hv_percentile",
        "hvpercentile_puts",
        {"guards": ("imp_volatility",), "strict": True}),                       # KQ
    ("ivhv",                "zero_guard_trig_ifs", "FR",
        "ivrule", ("imp_volatility",)),                                          # KR
    # KS: Excel uses >= (not strict >). FR=100 exactly at lo=100 → wbt, not wb.
    ("ivhv_puts",           "zero_guard_trig_ifs", "FR",
        "ivhv_puts",
        {"guards": ("imp_volatility",)}),                                        # KS
    # KT IVRule -> composite (Pass-2; reads KN, KP, KR)
    ("rsi_rule",            "trig_ifs", "rsi",        "rsi_rule", None),       # KU
    ("rsi_top",             "trig_ifs", "rsi",        "rsi_top",  None),       # KV
    ("rsi_puts",            "trig_ifs", "rsi",        "rsi_puts",
        {"strict": True}),                                                      # KW
    ("3m_low_rule",         "trig_ifs", "BB",         "3m_low_rule",  None),   # KX
    ("3m_low_days_rule",    "trig_ifs", "BC",         "3m_low_days_rule",None),# KY
    ("3mn_high_rule",       "trig_ifs", "BE",         "3mn_high_rule",None),   # KZ
    ("3mn_high_days_rule",  "trig_ifs", "BF",         "3mn_high_days_rule",None), # LA
    # LB 3m-Long -> composite
    ("perf3mn_sd_rule",     "trig_ifs", "BQ", "perf3mn_sd_rule",  None),       # LC
    ("perf2m_sd_rule",      "trig_ifs", "BS", "perf2m_sd_rule",   None),       # LD
    ("perf3wk_sd_rule",     "trig_ifs", "BU", "perf3wk_sd_rule",  None),       # LE
    ("perf2wk_sd_rule",     "trig_ifs", "BW", "perf2wk_sd_rule",  None),       # LF
    ("perf3d_sd_rule",      "trig_ifs", "BY", "perf3d_sd_rule",   None),       # LG
    # LH: Excel: positive>=, negative< (strict). CA=-2 at -nhi=-2 → False → -wbt.
    ("perf1d_sd_rule",      "trig_ifs", "CA", "perf1d_sd_rule",   {"strict_neg": True}),  # LH
    ("not_perf1d_sd",       "negate",   "perf1d_sd_rule", None, None),                # LI
    # LJ -- Perf3D_sd_1off (uses ABS(BY))
    ("perf3d_sd_1off",      "trig_ifs", "BY", "perf3d_sd_1off",
        {"abs_input": True}),                                                   # LJ
    # LK Perf SD Rule -> composite (Pass-2; reads LC..LJ)
    # LL/LM negations
    # LN/LO: Excel IFS(AO>0,wb,...,TRUE,0) — AO=0 returns 0, not wb.
    # Guard on AO ensures AO=0 → 0 (matching Excel's strict AO>0 check).
    ("bbhighlow_sd_rule",   "zero_guard_trig_ifs", "AO", "bbhighlow_sd_rule",
        {"guards": ("AO",), "strict": True}),                                   # LN
    ("bbhighlow_days_rule", "zero_guard_trig_ifs", "AM", "bbhighlow_days_rule",
        {"guards": ("AM",), "strict": True}),                                   # LO
    # LP BBStreak Rule -- input AY (BB_Streak; decoded from a_bb_streak)
    ("bbstreak_rule",       "trig_ifs", "AY", "bbstreak_rule",  None),         # LP
    ("bbstreakrule1",       "trig_ifs", "AY", "bbstreakrule1", None),         # LQ
    ("bbstreak_rule2",      "trig_ifs", "AY", "bbstreak_rule2", None),         # LR
    # LS/LT/LU/LV -- BBStreak Days variants (input AZ; decoded)
    ("bbstreak_days_rule",  "trig_ifs", "AZ", "bbstreak_days_rule",     None), # LS
    ("bbstreak_days_rule2", "trig_ifs", "AZ", "bbstreak_days_rule2",  None), # LT
    ("bbstreak_days_rule3", "trig_ifs", "AZ", "bbstreak_days_rule3",    None), # LU
    ("bbstreak_days_rule4", "trig_ifs", "AZ", "bbstreak_days_rule4", None), # LV
    # LW BB Bull Rule -> composite
    # LX -> negate
    # LY/LZ -- strict > in Excel.
    ("bbhighdays",          "trig_ifs", "AQ", "bbhighdays",
        {"strict": True}),                                                      # LY
    ("bblowdays",           "trig_ifs", "AR", "bblowdays",
        {"strict": True}),                                                      # LZ
    # MA MACD Rule -- input CJ = ABS(CI); 4-clause positive-only (CJ>=hi,>=lo,>0 else 0)
    ("macd_rule",           "trig_ifs", "a_macd_brr",  "macd_rule",
        {"abs_input": True, "positive_only": True}),                            # MA
    ("macdh_rule",          "trig_ifs", "a_macdh_d_brr","macdh_rule",
        {"abs_input": True, "positive_only": True}),                            # MB
    # MC MACD and H Rule -> composite (INT((MA+MB)/2))
    # MD/ME use CJ/CL too — strict > throughout, positive-only (CJ>hi,>lo,>0 else 0)
    ("macd_brr_puts",       "trig_ifs", "a_macd_brr",   "macd_brr_puts",
        {"abs_input": True, "positive_only": True, "strict": True}),           # MD
    ("macdh_brr_puts",      "trig_ifs", "a_macdh_d_brr","macdh_brr_puts",
        {"abs_input": True, "positive_only": True, "strict": True}),           # ME
    # MF -> composite
    # MG/MH -- MACDH Days; strict > in Excel.
    ("macdh_days",          "trig_ifs", "a_macdays_streak", "macdh_days",
        {"strict": True}),                                                      # MG
    ("macdh_days2",         "trig_ifs", "a_macdays_streak", "macdh_days2",
        {"strict": True}),                                                      # MH
    # MI Overbought -> composite (Pass-2; reads KV/MA/MB)
    # MJ negate
    # MK..MP -- 3mn/3wk outlook variants (inputs BJ/BK/BN/BO)
    ("3mn_outlook",         "trig_ifs", "BJ", "3mn_outlook",         None),    # MK
    ("3mn_outlook_days",    "trig_ifs", "BK", "3mn_outlook_days",    None),    # ML
    ("3wk_outlook",         "trig_ifs", "BN", "3wk_outlook",         None),    # MM
    ("3wk_outlook_days",    "trig_ifs", "BO", "3wk_outlook_days",    None),    # MN
    # MO/MP negate
    # MQ BULL -> composite ; MR negate
    # MS PerfOrBull -> composite ; MT negate
    # MU 50-DMA-Rule -- trig_ifs_dma over (D, CG, AC)
    ("50_dma_rule",         "trig_ifs_dma",
        ("last_price","sma_50","AC"), "50_dma_rule", None),                    # MU
    # MV 50-DMA-Crossover -> composite (reads D/CG/BZ)
    ("50_dma_crossover",    "composite", None, None,
        (lambda r,o: _crossover(r.get("last_price"), r.get("sma_50"),
                                r.get("BZ")))),                                # MV
    ("200_dma_rule",        "trig_ifs_dma",
        ("last_price","sma_200","AC"), "200_dma_rule", None),                  # MW
    ("200_dma_crossover",   "composite", None, None,
        (lambda r,o: _crossover(r.get("last_price"), r.get("sma_200"),
                                r.get("BZ")))),                                # MX
    ("52_wk_low_rule",      "trig_ifs_dma",
        ("last_price","low_52","AC"), "52_wk_low_rule", None),                 # MY
    ("52_wk_high_rule",     "trig_ifs_dma",
        ("last_price","high_52","AC"), "52_wk_high_rule", None),               # MZ
    # NC/ND Up/Down Resistance -> composite (D/EH/EI/CG/CH/BA/AC)
    ("up_resistance", "composite", None, None,
        (lambda r,o: (
            ((-0.5 if ((_f(r.get("high_today")) or 0) + 0.05 * (_f(r.get("AC")) or 0)
                       > (_f(r.get("sma_50")) or 0)
                       and (_f(r.get("last_price")) or 0) < (_f(r.get("sma_50")) or 0)) else 0.0)
             + (-0.5 if ((_f(r.get("high_today")) or 0) + 0.05 * (_f(r.get("AC")) or 0)
                       > (_f(r.get("sma_200")) or 0)
                       and (_f(r.get("last_price")) or 0) < (_f(r.get("sma_200")) or 0)) else 0.0))
        ))),                                                                    # NC
    ("down_resistance", "composite", None, None,
        (lambda r,o: (
            ((1.0 if ((_f(r.get("low_today")) or 0) + 0.05 * (_f(r.get("AC")) or 0)
                      < (_f(r.get("a_3mn_low")) or 0)
                      and (_f(r.get("last_price")) or 0) > (_f(r.get("a_3mn_low")) or 0)) else 0.0)
             + (0.5 if ((_f(r.get("low_today")) or 0) + 0.05 * (_f(r.get("AC")) or 0)
                      > (_f(r.get("sma_50")) or 0)
                      and (_f(r.get("last_price")) or 0) > (_f(r.get("sma_50")) or 0)) else 0.0)
             + (0.5 if ((_f(r.get("low_today")) or 0) + 0.05 * (_f(r.get("AC")) or 0)
                      < (_f(r.get("sma_200")) or 0)
                      and (_f(r.get("last_price")) or 0) > (_f(r.get("sma_200")) or 0)) else 0.0))
        ))),                                                                    # ND
    # NA/NB BRRTrade/TRRTrade -> composite (uses derived EC/ED with DU/DV fallback, AF, AC)
    # EC = derived BRR bottom (DX=lrr, fallback DU=bb_bot_prev); ED = derived TRR top.
    # Threshold: within 0.5 SD of the trade line (a_trade_value / AF).
    ("brrtrade",            "composite", None, None,
        (lambda r,o: 1.0 if (
            r.get("EC") is not None and r.get("a_trade_value") is not None
            and r.get("AC") and r.get("AC") != 0
            and abs(float(r["EC"]) - float(r["a_trade_value"]))
                <= float(r["AC"]) * 0.5
        ) else 0.0)),                                                          # NA
    ("trrtrade",            "composite", None, None,
        (lambda r,o: -1.0 if (
            r.get("ED") is not None and r.get("a_trade_value") is not None
            and r.get("AC") and r.get("AC") != 0
            and abs(float(r["ED"]) - float(r["a_trade_value"]))
                <= float(r["AC"]) * 0.5
        ) else 0.0)),                                                          # NB
    # NC/ND Up/Down Resistance -> composite (needs EH/EI/AC/CG/CH/BA)
    # NE Earnings -- strict > for hi/lo clauses; JB=0 → wb=-3 (earnings today = signal).
    # NULL (ETFs/no data) → None → one-null in comparison (expected).
    ("earnings",            "trig_ifs", "a_earnings_days", "earnings",
        {"strict": True}),                                                      # NE
    # NF/NG/NH/NI -- VS rules use strict >.
    ("vs_price",            "zero_guard_trig_ifs", "FK", "vs_price",
        {"guards": ("a_volume_spike", "FK"), "strict": True}),                  # NF
    ("vs_volume_spike",     "zero_guard_trig_ifs", "FI", "vs_volume_spike",
        {"guards": ("a_volume_spike",), "strict": True}),                       # NG
    # NH: Excel IFS(FL=0,0,...) — guard on FL directly, not just a_volume_spike
    ("vs_volatility",       "zero_guard_trig_ifs", "FL", "vs_volatility",
        {"guards": ("a_volume_spike", "FL"), "strict": True}),                  # NH
    ("vs_days",             "zero_guard_trig_ifs", "FM", "vs_days",
        {"guards": ("a_volume_spike",), "strict": True}),                       # NI
    # NK/NL/NM -- Current Price/Volume/Volatility SD Rules — strict >.
    ("current_price_sd_rule", "zero_guard_trig_ifs",
        "_NK_input", "current_price_sd_rule",
        {"guards": ("AC",), "strict": True}),                                   # NK
    # NL Current Volume Rule — Excel: IFS(GB=0,0,...). Guard on GB.
    ("current_volume_rule", "zero_guard_trig_ifs", "GB", "current_volume_rule",
        {"guards": ("GB",), "strict": True}),                                   # NL
    ("current_volatility_rule", "zero_guard_trig_ifs", "imp_volatility",
        "current_volatility_rule", {"guards": ("imp_volatility",), "strict": True}),  # NM (NULL IV → 0)
    # NN/NO -> composite (Pass-2)
    # QE/QJ/QM/QN/QR/QH/QI + parm-lookup columns now live in drv_tn_td_bb_rr
]


# =============================================================================
# Pass-2 composites (read Pass-1 outputs from the same row).
# =============================================================================
def _crossover(price, ma, prev_close, high=None, low=None) -> Optional[float]:
    """Excel IFS crossover used by Trade (JM), Trend (JP), and DMA crossovers.

    Full 5-arg form (Trade/Trend — MA!JM formula):
      =IFS(AND(D>MA, MA>MIN(EF,J)),  1,   -- crossed up
           AND(MAX(EF,I)>MA, MA>D), -1,   -- crossed down
           TRUE,                      0)
      D=price, MA=line, EF=prev_close(td_last), I=high_today, J=low_today

    3-arg form (high/low=None — DMA crossovers until their formulas are verified):
      falls back to simple: +1 if D>MA>prev, -1 if prev>MA>D
    """
    p  = _f(price);  m  = _f(ma)
    if p is None or m is None:
        return 0.0
    if high is None or low is None:
        # Simple 3-way fallback for callers that don't supply high/low
        pp = _f(prev_close) or 0.0
        if p > m and m > pp:  return 1.0
        if pp > m and m > p:  return -1.0
        return 0.0
    ef = _f(prev_close) or 0.0
    hi = _f(high) or p or 0.0
    lo = _f(low)  or p or 0.0
    if p > m and m > min(ef, lo):   return 1.0
    if max(ef, hi) > m and m > p:   return -1.0
    return 0.0


def _crossover_trend(price, ma, bz, prev_close, high=None, low=None) -> Optional[float]:
    """JP: Trend Cross Over — same IFS pattern as Trade but includes BZ in min/max.

    =IFS(AND(D>AE, AE>MIN(BZ,EF,J)),  1,
         AND(MAX(BZ,EF,I)>AE, AE>D), -1,
         TRUE, 0)
    """
    p  = _f(price); m = _f(ma)
    if p is None or m is None:
        return 0.0
    bz_ = _f(bz)  or 0.0
    ef  = _f(prev_close) or 0.0
    hi  = _f(high) or p or 0.0
    lo  = _f(low)  or p or 0.0
    if p > m and m > min(bz_, ef, lo):    return 1.0
    if max(bz_, ef, hi) > m and m > p:   return -1.0
    return 0.0


def _bull_expr(r: dict, o: dict) -> Optional[float]:
    """MQ: BULL — composite over JN/JQ/JV/LZ/LY/KH.
    Thresholds read from _BULL_GATE_THRESHOLDS (TASK_67 revertible config)
    with fallback to hardcoded Excel originals."""
    JN = _f(o.get("trade_rule"))
    JQ = _f(o.get("trend_rule"))
    JV = _f(o.get("trade_trend_sd_rule"))
    LZ = _f(o.get("bblowdays"))   # trig_ifs on AR (BBLowDays decoded from a_bb_high_low_days)
    LY = _f(o.get("bbhighdays"))  # trig_ifs on AQ (BBHighDays decoded from a_bb_high_low_days)
    KH = _f(o.get("lrr_above_trade"))
    def ge(a, b): return a is not None and a >= b
    def le(a, b): return a is not None and a <= b
    # Bullish arm — thresholds from config (TASK_67)
    ph_JN = _thr("bull.pos_hi.JN"); ph_JQ = _thr("bull.pos_hi.JQ")
    ph_JV = _thr("bull.pos_hi.JV"); ph_LZ = _thr("bull.pos_hi.LZ")
    pl_JN = _thr("bull.pos_lo.JN"); pl_JQ = _thr("bull.pos_lo.JQ")
    pl_JV = _thr("bull.pos_lo.JV"); pl_LZ = _thr("bull.pos_lo.LZ")
    # Bearish arm
    nh_JN = _thr("bull.neg_hi.JN"); nh_JQ = _thr("bull.neg_hi.JQ")
    nh_JV = _thr("bull.neg_hi.JV"); nh_LY = _thr("bull.neg_hi.LY")
    nl_JN = _thr("bull.neg_lo.JN"); nl_JQ = _thr("bull.neg_lo.JQ")
    nl_JV = _thr("bull.neg_lo.JV"); nl_LY = _thr("bull.neg_lo.LY")
    if ge(JN,ph_JN) and ge(JQ,ph_JQ) and ge(JV,ph_JV) and ge(LZ,ph_LZ): return 3.0
    if KH and KH > 0 and ge(JV,ph_JV):                                    return 3.0
    if ge(JN,pl_JN) and ge(JQ,pl_JQ) and ge(JV,pl_JV) and ge(LZ,pl_LZ): return 2.0
    if le(JN,nh_JN) and le(JQ,nh_JQ) and le(JV,nh_JV) and ge(LY,nh_LY): return -3.0
    if le(JN,nl_JN) and le(JQ,nl_JQ) and le(JV,nl_JV) and ge(LY,nl_LY): return -2.0
    return 0.0


def _perforbull_expr(r: dict, o: dict) -> Optional[float]:
    """MS: PerfOrBull = IFS(OR(LK>=3,MQ>=3),3, OR(LK<=-3,MQ<=-3),-3,
                            TRUE, INT((LK+MQ)/2)).
    Thresholds from _BULL_GATE_THRESHOLDS (TASK_67 revertible config)."""
    LK = _f(o.get("perf_sd_rule")) or 0.0
    MQ = _f(o.get("bull")) or 0.0
    hi = _thr("perforbull.hi")
    lo = _thr("perforbull.lo")
    if LK >= hi or MQ >= hi: return 3.0
    if LK <= -lo or MQ <= -lo: return -3.0
    # Excel INT() = floor() (toward -inf); Python int() truncates toward 0.
    import math
    return float(math.floor((LK + MQ) / 2))


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
    """LW: BB Bull Rule = IFS(AND(LP>=3,LS>=3),3, AND(LP<=-3,LS<=-3),-3, TRUE, LN).
    Thresholds from _BULL_GATE_THRESHOLDS (TASK_67 revertible config)."""
    LP = _f(o.get("bbstreak_rule")) or 0.0
    LS = _f(o.get("bbstreak_days_rule")) or 0.0
    LN = _f(o.get("bbhighlow_sd_rule"))   # zero_guard_trig_ifs on AO (BBHighLow_SD)
    hi_LP = _thr("bb_bull.hi.LP"); hi_LS = _thr("bb_bull.hi.LS")
    lo_LP = _thr("bb_bull.lo.LP"); lo_LS = _thr("bb_bull.lo.LS")
    if LP >= hi_LP and LS >= hi_LS: return 3.0
    if LP <= -lo_LP and LS <= -lo_LS: return -3.0
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
    if not DT_: return 0.0   # Excel: IF(DT=0,0,...) — None treated same as 0
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
    import math
    return float(math.floor((KX + KY - 1) / 2))


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


def _vs_lt_outlook_expr(r: dict, o: dict) -> Optional[float]:
    """NJ: VS LT Outlook Rule = IFS(NF>2 & NG>0 & NH>2 & NI>2, 3,
        NF>2 & NG>0 & NH<=2 & NI>=2, 2,
        NF<-2 & NG>0 & NH>2 & NI>2, -3,
        NF<-2 & NG>0 & NH<=2 & NI>=2, -2, TRUE, 0)."""
    NF = _f(o.get("vs_price")) or 0.0
    NG = _f(o.get("vs_volume_spike")) or 0.0
    NH = _f(o.get("vs_volatility")) or 0.0
    NI = _f(o.get("vs_days")) or 0.0
    if NF > 2 and NG > 0 and NH > 2 and NI > 2:  return 3.0
    if NF > 2 and NG > 0 and NH <= 2 and NI >= 2: return 2.0
    if NF < -2 and NG > 0 and NH > 2 and NI > 2:  return -3.0
    if NF < -2 and NG > 0 and NH <= 2 and NI >= 2: return -2.0
    return 0.0


def _short_term_outlook(r: dict, o: dict, *, lt_bullish: bool) -> Optional[float]:
    """NN/NO: short-term outlook table over NK/NL/NM."""
    NK = _f(o.get("current_price_sd_rule")) or 0.0
    NL = _f(o.get("current_volume_rule")) or 0.0
    NM = _f(o.get("current_volatility_rule")) or 0.0
    if NK > 2 and NL > 2 and NM < 2: return 3.0
    if NK > 2 and NL > 2:             return 2.0
    if NK < -2 and NL > 2 and NM < 2: return -3.0
    if NK < -2 and NL > 2:            return -2.0
    if lt_bullish:
        if NK > 2 and NL < -2 and NM < 2: return 1.0
        if NK > 2 and NL < -2:            return 1.0
        if NK < -2 and NL < -2 and NM > 2: return 2.0
        if NK < -2 and NL < -2:           return 3.0
    else:  # lt_bearish
        if NK > 2 and NL < -2 and NM < 2: return -3.0
        if NK > 2 and NL < -2:            return -2.0
        if NK < -2 and NL < -2 and NM > 2: return -2.0
        if NK < -2 and NL < -2:           return -1.0
    return 0.0


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
        (lambda r,o: float(__import__('math').floor(
            ((_f(o.get("macd_rule")) or 0) + (_f(o.get("macdh_rule")) or 0)) / 2)))), # MC
    ("macd_and_h_rule_puts", "composite", None, None,
        (lambda r,o: float(__import__('math').floor(
            ((_f(o.get("macd_brr_puts")) or 0) + (_f(o.get("macdh_brr_puts")) or 0)) / 2)))), # MF
    ("overbought",       "composite", None, None, _overbought_expr),           # MI
    ("not_overbought",   "negate", "overbought", None, None),                  # MJ
    ("not_3wk_ol",       "negate", "3wk_outlook", None, None),                 # MO
    ("not_3wk_ol_days",  "negate", "3wk_outlook_days", None, None),            # MP
    ("bull",             "composite", None, None, _bull_expr),                 # MQ
    ("not_bull",         "negate", "bull", None, None),                        # MR
    ("perforbull",       "composite", None, None, _perforbull_expr),           # MS
    ("not_perforbull",   "negate", "perforbull", None, None),                  # MT
    ("vs_lt_outlook_rule", "composite", None, None, _vs_lt_outlook_expr),      # NJ
    ("short_term_oulook_if_lt_bullish", "composite", None, None,
        (lambda r,o: _short_term_outlook(r, o, lt_bullish=True))),             # NN
    ("short_term_oulook_if_lt_bearish", "composite", None, None,
        (lambda r,o: _short_term_outlook(r, o, lt_bullish=False))),            # NO
]


# =============================================================================
# Dashboard scalar reader.  See docs § Dashboard scalars.
# =============================================================================
def get_dash_scalar(session: Session, param_name: str,
                    default: Optional[str] = None) -> Optional[str]:
    """Read a single-cell dashboard variable from ref_param sheet='dash'.

    Maps Excel cells like `Dash!$AB$24` to (sheet='dash', param_name=X).
    Seed values live in db/baseline.sql under the 2026-05-27 v3 block.
    """
    row = session.execute(text(
        "SELECT value FROM ref_param WHERE sheet='dash' AND param_name=:n"
    ), {"n": param_name}).first()
    return row[0] if row else default


# =============================================================================
# Trig rule cache.
# =============================================================================
def load_trig_rules(session: Session) -> dict:
    """Return {rule_name: {brkeout_from, brkeout_to, wt_below, wt_between,
       wt_above, scoring_mode, score_params}}."""
    rows = session.execute(text("""
        SELECT rule_name, brkeout_from, brkeout_to,
               wt_below, wt_between, wt_above,
               scoring_mode, score_params, neg_multiplier,
               neg_brkeout_from, neg_brkeout_to
        FROM ref_trig_atomic_rule
        WHERE deprecated_at IS NULL AND rule_name IS NOT NULL
    """)).mappings().all()
    out = {}
    for r in rows:
        name = r["rule_name"]
        if not name:
            continue
        # If a rule name appears twice (e.g. one with thresholds, one without),
        # keep the entry that has actual threshold data. Null-threshold entries are
        # placeholder rows used only for composite-member column resolution.
        existing = out.get(name)
        has_thresholds = r["brkeout_from"] is not None or r["wt_below"] is not None
        if existing is None or has_thresholds:
            out[name] = dict(r)
    # Overlay the active parameter set (Phase 3). No-op when no set is active,
    # so the engine keeps using the base ref_trig_atomic_rule values.
    try:
        from etl.param_sets import apply_active_param_set
        apply_active_param_set(session, out)
    except Exception:
        pass
    return out


# =============================================================================
# Evaluator helpers.
# =============================================================================
def _eval_trig_ifs(value, rule: Optional[dict], *,
                   strict: bool = False,
                   positive_only: bool = False,
                   strict_neg: bool = False) -> Optional[float]:
    """Excel-faithful Trig-IFS evaluator.

    Six-clause IFS (default):
        v >= hi   ->   wt_above           (strict=True: v > hi)
        v >= lo   ->   wt_between         (strict=True: v > lo)
        v >= 0    ->   wt_below
        v <= -hi  ->  -wt_above           (strict=True or strict_neg: v < -hi)
        v <= -lo  ->  -wt_between         (strict=True or strict_neg: v < -lo)
        v <  0    ->  -wt_below

    strict_neg=True: positive uses >= (non-strict), negative uses < (strict).
    Matches Excel IFS pattern: $v>=hi, $v>=lo, v>=0, $v<-hi, $v<-lo, v<0.

    Four-clause positive-only IFS (positive_only=True — used by MACD rules).

    `strict=False` (default): positive >=, negative <=.
    `strict=True`: positive >, negative < (strict both sides).
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
    wa  = _f(rule.get("wt_above")) or 0.0
    # Negative-side thresholds: use explicit neg_brkeout_from/to when set;
    # otherwise scale by neg_multiplier (default 1.0 = symmetric).
    nlo_explicit = _f(rule.get("neg_brkeout_from"))
    nhi_explicit = _f(rule.get("neg_brkeout_to"))
    if nlo_explicit is not None and nhi_explicit is not None:
        nlo = nlo_explicit
        nhi = nhi_explicit
    else:
        nm = float(rule.get("neg_multiplier") or 1.0)
        nlo = lo * nm
        nhi = hi * nm
    if positive_only:
        # 4-clause: positive values only; zero and negative → 0.
        # Standard inclusive boundary (>=) — `strict` no longer narrows it.
        if v >= hi: return wa
        if v >= lo: return wbt
        if v > 0: return wb_
        return 0.0
    if strict_neg and not strict:
        # Standard: positive >= , negative <= (both inclusive / symmetric).
        if v >= hi:   return wa
        if v >= lo:   return wbt
        if v >= 0:    return wb_
        if v <= -nhi: return -wa
        if v <= -nlo: return -wbt
        if v <  0:    return -wb_
    else:
        # Standard: positive >= , negative <= (both inclusive / symmetric).
        # Negative was strict `<` before — an oversight; integer-input rules
        # (e.g. bbstreak) land exactly on the threshold and were mis-graded.
        if v >= hi:   return wa
        if v >= lo:   return wbt
        if v >= 0:    return wb_
        if v <= -nhi: return -wa
        if v <= -nlo: return -wbt
        if v <  0:    return -wb_
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
                strict = False
                simple = False
                positive_only = False
                strict_neg = False
                if isinstance(extra, dict):
                    if extra.get("abs_input") and val is not None:
                        val = abs(_f(val) or 0.0)
                    strict        = bool(extra.get("strict"))
                    simple        = bool(extra.get("simple"))
                    positive_only = bool(extra.get("positive_only"))
                    strict_neg    = bool(extra.get("strict_neg"))
                if simple:
                    # Use standard 3-clause jump eval (correct for asymmetric zones where lo < 0)
                    from etl.derive import eval_atomic_rule
                    out[db_col] = eval_atomic_rule(val, trig_rules.get(rule_name))
                else:
                    out[db_col] = _eval_trig_ifs(val, trig_rules.get(rule_name),
                                                  strict=strict, positive_only=positive_only,
                                                  strict_neg=strict_neg)

            elif ftype == "zero_guard_trig_ifs":
                guards = extra or ()
                # extra may be tuple-of-guards OR dict with 'guards'/'strict' keys
                strict = False
                if isinstance(extra, dict):
                    guards = extra.get("guards", ())
                    strict = bool(extra.get("strict"))
                if any((_f(row.get(g) if g in row else out.get(g)) == 0
                        or row.get(g) is None) for g in guards):
                    out[db_col] = 0.0
                    continue
                val = row.get(src) if src in row else out.get(src)
                if src == "_NK_input":
                    H = _f(row.get("net_chng"))
                    AD = _f(row.get("AC"))      # AC = standard_dev (raw SD, not price-normalized)
                    val = _safe_div(H, AD)
                out[db_col] = _eval_trig_ifs(val, trig_rules.get(rule_name),
                                              strict=strict)

            elif ftype == "trig_ifs_dma":
                pk, mk, vk = src
                out[db_col] = _eval_trig_ifs_dma(
                    row.get(pk), row.get(mk), row.get(vk),
                    trig_rules.get(rule_name))

            elif ftype == "negate":
                twin = out.get(src)
                out[db_col] = (-1.0 * _f(twin)) if twin is not None else None

            elif ftype == "passthru":
                out[db_col] = _f(row.get(src) if src in row else out.get(src))

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
UPDATE drv_tn_td_bb_rr dst
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
        WHEN dst.bb_rng_strk_rule >= 2 THEN 'B'
        WHEN dst.bb_rng_strk_rule >= 0 THEN '!B'
        ELSE NULL END,
    rr_desc = CASE
        WHEN dst.bb_rng_strk_rule >= 2 THEN l_qm.description
        WHEN dst.bb_rng_strk_rule >= 0 THEN l_qn.description
        ELSE NULL END,
    td_tn_bb_action_desc = l_qr.description,
    td_tn_bb_action_seq  = l_qr.seq
FROM drv_tn_td_bb_rr src
LEFT JOIN ref_param_lookup l_qf
  ON l_qf.table_name = 'tn_td_rule'
 AND l_qf.code = (src.trend_trade_rule)::INTEGER::TEXT
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
WHERE dst.as_of_date = src.as_of_date AND dst.tos_symbol = src.tos_symbol
  AND dst.as_of_date = :d
"""


def _get_sd_window(session: Session) -> str:
    """Return the sd_median_window_days interval string for WORKING_SET_SQL's :win param.

    Reads ref_settings.sd_median_window_days (default 30). Returns a Postgres
    INTERVAL-compatible string, e.g. '30 days'.
    """
    row = session.execute(text(
        "SELECT setting_value FROM ref_settings WHERE setting_name='sd_median_window_days'"
    )).first()
    try:
        days = int(row[0]) if row else 30
    except (TypeError, ValueError):
        days = 30
    return f"{days} days"


def derive_cat_atomic_input(session: Session, as_of_date: date,
                            parent_run_id: Optional[int] = None) -> int:
    """Compute drv_cat_atomic_input rows for `as_of_date`.  Idempotent."""
    run_id = parent_run_id or 0
    # TASK_67: load revertible bull-gate thresholds from ref_threshold_override.
    # Falls back to hardcoded defaults when table is absent or active_source='original'.
    load_bull_gate_thresholds(session)
    trig_rules = load_trig_rules(session)
    if not trig_rules:
        log.warning("drv_cat_atomic_input: ref_trig_atomic_rule empty; skipping")
        return 0
    win = _get_sd_window(session)
    session.execute(
        text("DELETE FROM drv_cat_atomic_input WHERE as_of_date = :d"),
        {"d": as_of_date})
    rows = session.execute(text(WORKING_SET_SQL), {"d": as_of_date, "win": win}).mappings().all()
    if not rows:
        return 0
    all_db_cols = ([s[0] for s in COLUMN_SPECS_PASS1]
                   + [s[0] for s in COLUMN_SPECS_PASS2])
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
        rec = {"as_of_date": as_of_date, "tos_symbol": row["tos_symbol"],
               "source_run_id": run_id}
        for c in ordered_cols:
            rec[c] = out.get(c)
        records.append(rec)
    def _q(c):
        import re as _re
        return c if _re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", c) else f'"{c}"'
    col_list = ", ".join(["as_of_date","tos_symbol"]
                         + [_q(c) for c in ordered_cols]
                         + ["source_run_id"])
    bind_list = ", ".join([":as_of_date",":tos_symbol"]
                          + [f":{c}" for c in ordered_cols]
                          + [":source_run_id"])
    insert_sql = text(f"INSERT INTO drv_cat_atomic_input ({col_list}) "
                      f"VALUES ({bind_list})")
    inserted = 0; BATCH = 500
    for i in range(0, len(records), BATCH):
        chunk = records[i:i + BATCH]
        session.execute(insert_sql, chunk)
        inserted += len(chunk)

    return inserted


def run_parm_lookup_pass3(session: Session, as_of_date: date) -> int:
    """Pass-3 Parm-lookup UPDATE.  Idempotent."""
    result = session.execute(text(PARM_LOOKUP_SQL), {"d": as_of_date})
    return result.rowcount or 0


def get_symbol_intermediates(session: Session, tos_symbol: str, as_of_date) -> dict:
    """Return compute_intermediates output for one symbol — used by the Rule Flow UI.

    Runs the working-set SQL filtered to a single symbol, calls compute_intermediates,
    and returns the full row dict (raw SQL columns + all computed intermediates).
    """
    win = _get_sd_window(session)
    filtered_sql = WORKING_SET_SQL.rstrip() + "\nWHERE s.s = :sym"
    try:
        row = session.execute(
            text(filtered_sql), {"d": as_of_date, "sym": tos_symbol, "win": win}
        ).mappings().first()
    except Exception:
        return {}
    if not row:
        return {}
    row_dict = dict(row)
    compute_intermediates(row_dict)
    return row_dict
