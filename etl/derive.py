"""
Step 2 of the two-step ETL: populate drv_* tables.

Each function:
  - opens a meta_derived_run row (status=running)
  - DELETEs WHERE as_of_date = D from its target table
  - computes & INSERTs rebuilt rows
  - closes the meta_derived_run row (success / error)

All public functions have signature (session, as_of_date, parent_run_id=None).
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from etl.db import get_table, replace_for_date
from etl.rule_groups import eval_rule_group
from etl import ma_codegen
from etl.warnings import clear_screen_warnings, add_warning

# Shared meta_derived_run helpers + the _wrap decorator. Extracted to
# etl/_derive_common.py so derive.py and derive_v2.py can both use them
# without a circular import.
from etl._derive_common import _open_drv_run, _close_drv_run, _wrap

# derive_tw and derive_sss have formula-faithful implementations in
# derive_v2.py — import them here so derive_all() can call them like any
# other deriver. (Previously a bottom-of-file rebind handled this.)
from etl.derive_v2 import derive_tw, derive_sss

log = logging.getLogger(__name__)


# =============================================================================
# Symbol mapping helper (using RRT table)
# =============================================================================

def _get_tos_symbol(session: Session, symbol: str, lookup_column: str) -> Optional[str]:
    """
    Map a source symbol to its TOS ticker using ref_rrt table.

    lookup_column: 'y_ticker' for Y symbols, 'rr_name' for RR symbols
    Returns tos_ticker if found in RRT, otherwise returns original symbol.
    """
    if not symbol:
        return None

    try:
        row = session.execute(text(f"""
            SELECT tos_ticker FROM ref_rrt
            WHERE {lookup_column} = :sym LIMIT 1
        """), {"sym": symbol}).first()

        if row and row[0]:
            return row[0]
    except Exception:
        pass

    # Fallback: return original symbol if not found
    return symbol


# =============================================================================
# (a) Per-row derived
# =============================================================================



def _td_clean(v) -> float:
    """Clean a raw TD value: NaN/None -> 0.0; otherwise float."""
    if v is None:
        return 0.0
    try:
        f = float(v)
        # NaN check
        if f != f:
            return 0.0
        return f
    except (TypeError, ValueError):
        return 0.0


def _td_avg_last_n(history: list, attr: str, n: int) -> float:
    """Average the last n values of `attr` across history rows. Mirrors
    Excel  =AVERAGE(TAKE(FILTER(col, sym=cur_sym), -n))."""
    if not history:
        return 0.0
    vals = []
    for row in history[-n:]:
        v = getattr(row, attr, None)
        if v is None:
            continue
        try:
            f = float(v)
            if f != f:  # NaN
                continue
            vals.append(f)
        except (TypeError, ValueError):
            continue
    return (sum(vals) / len(vals)) if vals else 0.0


def _td_at_offset(history: list, attr: str, offset: int) -> float:
    """
    Mirror Excel: XLOOKUP((H2-N) & C2, G$1:G1, BA$1:BA1, 0, 0, -1)
    Returns the value of `attr` from the row that is `offset` positions
    BEFORE the current (last) one. 0 if not enough history. The current
    row is at index len(history)-1; offset N looks back N positions.
    """
    idx = len(history) - 1 - offset
    if idx < 0 or idx >= len(history):
        return 0.0
    return _td_clean(getattr(history[idx], attr, None))


def _td_rsi_direction(short: float, long_: float) -> int:
    """W: IFS(OR(U=0,V=0),0, (U-V)>1,1, (U-V)<-1,-1, TRUE,0)."""
    if short == 0 or long_ == 0:
        return 0
    diff = short - long_
    if diff > 1:
        return 1
    if diff < -1:
        return -1
    return 0


def _td_pct_direction(short: float, long_: float) -> int:
    """AA / AE: IFS(OR(0),0, (s-l)/l>0.03,1, /l<-0.03,-1, TRUE,0)."""
    if short == 0 or long_ == 0:
        return 0
    ratio = (short - long_) / long_
    if ratio > 0.03:
        return 1
    if ratio < -0.03:
        return -1
    return 0


def _td_ivp_direction(short: float, long_: float) -> int:
    """AH: IFS(OR(0),0, (s-l)>1,1, <-1,-1, TRUE,0)."""
    if short == 0 or long_ == 0:
        return 0
    diff = short - long_
    if diff > 1:
        return 1
    if diff < -1:
        return -1
    return 0


def _td_vlt_rule_code(iv_pctile, d_hv, d_iv, d_rsi_dir, d_iv_dir, d_hv_dir,
                      d_iv_to_hv, hv_pctile, d_ivp_dir, range_comp,
                      d_iv3, d_iv7, d_hv3, d_hv7,
                      d_rsi, d_rsi3, d_rsi7, d_ivp_max10) -> Optional[int]:
    """
    AK column:
      IFS(OR(Q=0,X=0,AB=0), "",
          AND(Q>90, W<=0, OR(X/Z>1.25, Y/Z>1.1, AC/AD>1.1)), 1,
          AND(Q>60, AJ>2, AE<0), 2,
          AND(Q<60, AA<0, AE>0, W<0), 3,
          AND(Q>40, Y/Z>1.25, AA<=0), 4,
          AND(Q>25, AA<0, AE<0, W<0), 5,
          AND(Q<50, AA<0, AE<=0, W<=0), 6,
          AND(Q<10, R<=10, AH<=0, S<0.03), 7,
          AND(Q>60, AI>=80, (AI-Q)>10, W>0, AE<0), 8,
          AND(Q<25, AA>0, AE>0, W>0, AH>0), 9,
          AND(Q<60, W>0, AA>=0, AE>=0, T>U, T>V), 10,
          TRUE, "")
    Where Q=iv_pctile, X=d_hv, AB=d_iv, W=d_rsi_dir, Y=d_hv3, Z=d_hv7,
    AC=d_iv3, AD=d_iv7, AJ=d_iv_to_hv, AE=d_iv_dir, AA=d_hv_dir,
    R=hv_pctile, AH=d_ivp_dir, S=range_comp, AI=d_ivp_max10,
    T=d_rsi, U=d_rsi3, V=d_rsi7
    """
    if iv_pctile == 0 or d_hv == 0 or d_iv == 0:
        return None

    def safe_div(a, b):
        return (a / b) if b else 0.0

    if iv_pctile > 90 and d_rsi_dir <= 0 and (
        safe_div(d_hv, d_hv7) > 1.25
        or safe_div(d_hv3, d_hv7) > 1.1
        or safe_div(d_iv3, d_iv7) > 1.1
    ):
        return 1
    if iv_pctile > 60 and d_iv_to_hv > 2 and d_iv_dir < 0:
        return 2
    if iv_pctile < 60 and d_hv_dir < 0 and d_iv_dir > 0 and d_rsi_dir < 0:
        return 3
    if iv_pctile > 40 and safe_div(d_hv3, d_hv7) > 1.25 and d_hv_dir <= 0:
        return 4
    if iv_pctile > 25 and d_hv_dir < 0 and d_iv_dir < 0 and d_rsi_dir < 0:
        return 5
    if iv_pctile < 50 and d_hv_dir < 0 and d_iv_dir <= 0 and d_rsi_dir <= 0:
        return 6
    if iv_pctile < 10 and hv_pctile <= 10 and d_ivp_dir <= 0 and range_comp < 0.03:
        return 7
    if iv_pctile > 60 and d_ivp_max10 >= 80 and (d_ivp_max10 - iv_pctile) > 10 \
       and d_rsi_dir > 0 and d_iv_dir < 0:
        return 8
    if iv_pctile < 25 and d_hv_dir > 0 and d_iv_dir > 0 and d_rsi_dir > 0 and d_ivp_dir > 0:
        return 9
    if iv_pctile < 60 and d_rsi_dir > 0 and d_hv_dir >= 0 and d_iv_dir >= 0 \
       and d_rsi > d_rsi3 and d_rsi > d_rsi7:
        return 10
    return None


def _td_vlt_caution(iv_pctile, d_hv, d_iv, d_iv3, d_hv3, d_iv7, d_hv7,
                    d_iv_to_hv, range_comp) -> Optional[str]:
    """
    AL column:
      IFS(OR(Q=0,X=0,AB=0), "",
          Q>90,                              "IVPXtrm",
          X/Z > 1.25,                        "HV1Spke",
          Y/Z > 1.25,                        "HV3Spke",
          AB/AD > 1.25,                      "IV1Spke",
          AC/AD > 1.25,                      "IV3Spke",
          AJ > 2,                            "HiIV2HV",
          AND(S < 0.03, X/Z > 1.25),         "IVExpn",
          TRUE, "")
    """
    if iv_pctile == 0 or d_hv == 0 or d_iv == 0:
        return None

    def safe_div(a, b):
        return (a / b) if b else 0.0

    if iv_pctile > 90:
        return "IVPXtrm"
    if safe_div(d_hv, d_hv7) > 1.25:
        return "HV1Spke"
    if safe_div(d_hv3, d_hv7) > 1.25:
        return "HV3Spke"
    if safe_div(d_iv, d_iv7) > 1.25:
        return "IV1Spke"
    if safe_div(d_iv3, d_iv7) > 1.25:
        return "IV3Spke"
    if d_iv_to_hv > 2:
        return "HiIV2HV"
    if range_comp < 0.03 and safe_div(d_hv, d_hv7) > 1.25:
        return "IVExpn"
    return None


def _derive_td_impl(session: Session, as_of_date: date, run_id: int) -> int:
    """
    drv_td: per-row Excel-derived columns from the TD tab.

    Implements every formula in TD cols A-AL using the actual workbook formulas:
      - I-P  (BB_Bot/Top 15d/7d/3d/Prev): XLOOKUP from N records ago
      - Q,R  (IVPercentile, HVPercentile): cleaned BF, BG (NaN -> 0)
      - S    (RangeCompression): (max(last10 high) - min(last10 low)) / last_price
      - T-W  (D_RSI / D_RSI3 / D_RSI7 / D_RSIDirection): rolling avg + direction
      - X-AA (D_HV family): same as RSI but for historical_vol
      - AB-AE (D_IV family): same for imp_volatility
      - AF-AH (D_IVP3, D_IVP7, D_IVPDirection): rolling avg of cleaned IVPercentile
      - AI   (D_IVPMax10): max IVPercentile of last 10 records
      - AJ   (D_IV_to_HV): D_IV / D_HV
      - AK   (D_Vlt_RuleCode): rule code 1-10 from compound IFS
      - AL   (D_Vlt_Caution): caution label
    """
    cur_rows = session.execute(text("""
        SELECT snapshot_date, symbol, sequence
        FROM hist_td WHERE snapshot_date = :d
    """), {"d": as_of_date}).mappings().all()

    if not cur_rows:
        return 0

    symbols = list({r["symbol"] for r in cur_rows})

    # Bulk-fetch all hist_td records for these symbols up to as_of_date,
    # ordered ASC so the last row in each symbol's slice is the current row.
    all_hist_rows = session.execute(text("""
        SELECT snapshot_date, symbol, sequence,
               last_price, high_price, low_price,
               rsi, historical_vol, imp_volatility,
               a_iv_percentile, a_hv_percentile,
               a_bb_top, a_bb_bottom
        FROM hist_td
        WHERE snapshot_date <= :d AND symbol = ANY(:syms)
        ORDER BY symbol, snapshot_date ASC, sequence ASC
    """), {"d": as_of_date, "syms": symbols}).fetchall()

    by_symbol: dict[str, list] = {}
    for row in all_hist_rows:
        by_symbol.setdefault(row.symbol, []).append(row)

    out: list[dict] = []
    for r in cur_rows:
        sym = r["symbol"]
        history = by_symbol.get(sym, [])
        if not history:
            continue

        # Current row is the last in `history`
        cur = history[-1]

        # --- per-row clean-ups (Q, R, AB, X, T) -----------------------------
        iv_pctile = _td_clean(cur.a_iv_percentile)        # Q
        hv_pctile = _td_clean(cur.a_hv_percentile)        # R
        d_rsi    = _td_clean(cur.rsi)                     # T
        d_hv     = _td_clean(cur.historical_vol)          # X
        d_iv     = _td_clean(cur.imp_volatility)          # AB

        # --- BB lookups (I-P) ------------------------------------------------
        bb_bot_15d  = _td_at_offset(history, "a_bb_bottom", 15)
        bb_bot_7d   = _td_at_offset(history, "a_bb_bottom", 7)
        bb_bot_3d   = _td_at_offset(history, "a_bb_bottom", 3)
        bb_top_15d  = _td_at_offset(history, "a_bb_top", 15)
        bb_top_7d   = _td_at_offset(history, "a_bb_top", 7)
        bb_top_3d   = _td_at_offset(history, "a_bb_top", 3)

        # --- range compression (S) -------------------------------------------
        last10 = history[-10:]
        highs = [_td_clean(h.high_price) for h in last10
                 if h.high_price is not None and _td_clean(h.high_price) > 0]
        lows  = [_td_clean(h.low_price) for h in last10
                 if h.low_price is not None and _td_clean(h.low_price) > 0]
        last_price = _td_clean(cur.last_price)
        if highs and lows and last_price > 0:
            range_comp = (max(highs) - min(lows)) / last_price
        else:
            range_comp = 0.0

        # --- rolling averages (U,V, Y,Z, AC,AD) ------------------------------
        d_rsi3 = _td_avg_last_n(history, "rsi", 3)
        d_rsi7 = _td_avg_last_n(history, "rsi", 7)
        d_hv3  = _td_avg_last_n(history, "historical_vol", 3)
        d_hv7  = _td_avg_last_n(history, "historical_vol", 7)
        d_iv3  = _td_avg_last_n(history, "imp_volatility", 3)
        d_iv7  = _td_avg_last_n(history, "imp_volatility", 7)

        # --- IVPercentile rolling: needs the CLEANED column (Q-equivalent) ---
        cleaned_ivp = [_td_clean(h.a_iv_percentile) for h in history]
        last3_ivp  = [v for v in cleaned_ivp[-3:]  if v is not None]
        last7_ivp  = [v for v in cleaned_ivp[-7:]  if v is not None]
        last10_ivp = [v for v in cleaned_ivp[-10:] if v is not None]
        d_ivp3 = (sum(last3_ivp) / len(last3_ivp)) if last3_ivp else 0.0
        d_ivp7 = (sum(last7_ivp) / len(last7_ivp)) if last7_ivp else 0.0
        d_ivp_max10 = max(last10_ivp) if last10_ivp else 0.0

        # --- direction signals (W, AA, AE, AH) -------------------------------
        d_rsi_dir = _td_rsi_direction(d_rsi3, d_rsi7)
        d_hv_dir  = _td_pct_direction(d_hv3, d_hv7)
        d_iv_dir  = _td_pct_direction(d_iv3, d_iv7)
        d_ivp_dir = _td_ivp_direction(d_ivp3, d_ivp7)

        # --- IV/HV ratio (AJ) -----------------------------------------------
        d_iv_to_hv = (d_iv / d_hv) if d_hv else 0.0

        # --- volatility rule code + caution (AK, AL) -------------------------
        d_vlt_rule_code = _td_vlt_rule_code(
            iv_pctile, d_hv, d_iv, d_rsi_dir, d_iv_dir, d_hv_dir,
            d_iv_to_hv, hv_pctile, d_ivp_dir, range_comp,
            d_iv3, d_iv7, d_hv3, d_hv7,
            d_rsi, d_rsi3, d_rsi7, d_ivp_max10,
        )
        d_vlt_caution = _td_vlt_caution(
            iv_pctile, d_hv, d_iv, d_iv3, d_hv3, d_iv7, d_hv7,
            d_iv_to_hv, range_comp,
        )

        out.append({
            "snapshot_date":     r["snapshot_date"],
            "tos_symbol":        sym,
            "sequence":          r["sequence"],
            "bb_bot_15d":        bb_bot_15d,
            "bb_bot_7d":         bb_bot_7d,
            "bb_bot_3d":         bb_bot_3d,
            "bb_top_15d":        bb_top_15d,
            "bb_top_7d":         bb_top_7d,
            "bb_top_3d":         bb_top_3d,
            "iv_percentile":     iv_pctile,
            "hv_percentile":     hv_pctile,
            "range_compression": range_comp,
            "d_rsi":             d_rsi,
            "d_rsi3":            d_rsi3,
            "d_rsi7":            d_rsi7,
            "d_rsi_direction":   d_rsi_dir,
            "d_hv":              d_hv,
            "d_hv3":             d_hv3,
            "d_hv7":             d_hv7,
            "d_hv_direction":    d_hv_dir,
            "d_iv":              d_iv,
            "d_iv3":             d_iv3,
            "d_iv7":             d_iv7,
            "d_iv_direction":    d_iv_dir,
            "d_ivp3":            d_ivp3,
            "d_ivp7":            d_ivp7,
            "d_ivp_direction":   d_ivp_dir,
            "d_ivp_max10":       d_ivp_max10,
            "d_iv_to_hv":        d_iv_to_hv,
            "d_vlt_rule_code":   str(d_vlt_rule_code) if d_vlt_rule_code is not None else None,
            "d_vlt_caution":     d_vlt_caution,
            "source_run_id":     run_id,
        })

    return replace_for_date(session, "drv_td", "snapshot_date", as_of_date, out)


derive_td = _wrap("drv_td", _derive_td_impl)


def _derive_to_impl(session: Session, as_of_date: date, run_id: int) -> int:
    """
    drv_to: per-row derivations from hist_to (TOS Other - fundamentals).

    Computes market_cap_num by parsing hist_to.market_cap_str.
    Format: "71,783 M" → 71,783,000,000 (value in dollars).
    """
    sql = text("""
    INSERT INTO drv_to (snapshot_date, tos_symbol, sequence, market_cap_num, source_run_id)
    SELECT
        snapshot_date,
        tos_symbol,
        COALESCE(sequence, 0),
        CASE
            WHEN market_cap_str IS NOT NULL
                 AND market_cap_str ~ '^[0-9,]+\\s*[MBK]$'
            THEN (
                CAST(
                    REGEXP_REPLACE(market_cap_str, '[^0-9.]', '', 'g')
                    AS NUMERIC
                ) * CASE WHEN market_cap_str ~ 'B$' THEN 1000000000
                         WHEN market_cap_str ~ 'M$' THEN 1000000
                         WHEN market_cap_str ~ 'K$' THEN 1000
                         ELSE 1
                    END
            )
            ELSE NULL
        END,
        :run
    FROM hist_to
    WHERE snapshot_date = :d
    """)

    session.execute(text("DELETE FROM drv_to WHERE snapshot_date = :d"), {"d": as_of_date})
    result = session.execute(sql, {"d": as_of_date, "run": run_id})
    return result.rowcount or 0


derive_to = _wrap("drv_to", _derive_to_impl)


# =============================================================================
# (b) Cross-table aggregates
# =============================================================================

def _derive_ma_impl(session: Session, as_of_date: date, run_id: int) -> int:
    """
    drv_ma: master aggregation. For each symbol, take the latest record from
    each source where snapshot_date <= as_of_date.
    Symbols come from union of ref_sector + every hist source seen.
    """
    sql = text("""
    INSERT INTO drv_ma (
        as_of_date, tos_symbol, description, sector, asset_class, sub_asset_class, equity_sector,
        tl_date, last_price, rsi, imp_volatility, volume, vlm_projected,
        td_date, iv_percentile, hv_percentile, range_compression, d_iv_to_hv, d_vlt_caution,
        a_trend_value, a_trade_value, a_bb_top, a_bb_bottom, a_bb_streak,
        tw_date, a_macd_brr, a_macdh_d_brr, earnings_days, sma_20, sma_50, sma_200,
        market_cap_str, beta,
        pe_ratio, eps, div_yield,
        rr_date, rr_buy_trade, rr_sell_trade, rr_outlook,
        call_outlook, call_modifier, call_weight,
        etf_outlook, etf_brr, etf_trr,
        ii_outlook, ii_weight,
        SSS_signal, SSS_signal_sign, SSS_rank_hl,
        held_qty_fid, held_qty_cs,
        pct_brr,
        source_run_id
    )
    WITH p AS (SELECT CAST(:d AS date) AS d, CAST(:run AS bigint) AS run),
    syms AS (
        SELECT DISTINCT s FROM (
            SELECT ticker AS s FROM ref_sector
            UNION SELECT tos_symbol FROM hist_tl WHERE snapshot_date <= (SELECT d FROM p)
            UNION SELECT tos_symbol FROM hist_rr WHERE snapshot_date <= (SELECT d FROM p)
            UNION SELECT tos_symbol FROM hist_y  WHERE snapshot_date <= (SELECT d FROM p)
            UNION SELECT tos_symbol FROM hist_call WHERE snapshot_date <= (SELECT d FROM p)
            UNION SELECT tos_symbol FROM hist_etf  WHERE snapshot_date <= (SELECT d FROM p)
            UNION SELECT tos_symbol FROM hist_ii   WHERE snapshot_date <= (SELECT d FROM p)
        ) u WHERE s IS NOT NULL
    ),
    tl AS (
        -- vlm_projected + imp_volatility cleaning inlined here:
        --   imp_volatility = COALESCE(imp_volatility_raw, 0)
        --   vlm_projected  = intraday volume projected to the full session,
        --                    a pure per-row function of volume + sequence (HHMM)
        SELECT DISTINCT ON (h.tos_symbol) h.tos_symbol, h.snapshot_date AS tl_date,
               h.last_price, h.rsi,
               COALESCE(h.imp_volatility_raw, 0) AS imp_volatility,
               h.volume,
               CASE
                   WHEN h.volume IS NULL OR h.sequence < 930 THEN NULL
                   WHEN h.sequence >= 1600 THEN h.volume::numeric
                   WHEN ((h.sequence / 100) * 60 + (h.sequence % 100) - 570) > 0
                       THEN h.volume::numeric * 390.0
                            / ((h.sequence / 100) * 60 + (h.sequence % 100) - 570)
                   ELSE NULL
               END AS vlm_projected
        FROM hist_tl h
        WHERE h.snapshot_date <= (SELECT d FROM p)
        ORDER BY h.tos_symbol, h.snapshot_date DESC, h.sequence DESC
    ),
    -- drv_quote: consolidated latest-loaded-wins values across hist_y/tl/td.
    -- drv_ma reads price/rsi/imp_volatility from here first, falling back to
    -- the legacy hist_tl-based `tl` CTE so missing drv_quote rows don't
    -- regress the data.
    dq AS (
        SELECT DISTINCT ON (tos_symbol) tos_symbol, last_price, rsi, imp_volatility
        FROM drv_quote
        WHERE as_of_date <= (SELECT d FROM p)
        ORDER BY tos_symbol, as_of_date DESC
    ),
    td AS (
        SELECT DISTINCT ON (h.tos_symbol) h.tos_symbol, h.snapshot_date AS td_date,
               COALESCE(dr.iv_percentile, h.a_iv_percentile)  AS iv_percentile,
               COALESCE(dr.hv_percentile, h.a_hv_percentile)  AS hv_percentile,
               dr.range_compression, dr.d_iv_to_hv, dr.d_vlt_caution,
               h.a_trend_value, h.a_trade_value, h.a_bb_top, h.a_bb_bottom, h.a_bb_streak
        FROM hist_td h
        LEFT JOIN drv_td dr USING (snapshot_date, tos_symbol, sequence)
        WHERE h.snapshot_date <= (SELECT d FROM p)
        ORDER BY h.tos_symbol, h.snapshot_date DESC, h.sequence DESC
    ),
    tw AS (
        SELECT DISTINCT ON (h.tos_symbol) h.tos_symbol, h.snapshot_date AS tw_date,
               dr.a_macd_brr, dr.a_macdh_d_brr, dr.earnings_days_d AS earnings_days,
               dr.sma_20_d AS sma_20, dr.sma_50_d AS sma_50, dr.sma_200_d AS sma_200
        FROM hist_tw h
        LEFT JOIN drv_tw dr USING (snapshot_date, tos_symbol, sequence)
        WHERE h.snapshot_date <= (SELECT d FROM p)
        ORDER BY h.tos_symbol, h.snapshot_date DESC, h.sequence DESC
    ),
    too AS (
        SELECT DISTINCT ON (h.tos_symbol) h.tos_symbol, h.beta,
               COALESCE(dr.market_cap_num::text, h.market_cap_str) AS market_cap_str,
               h.pe_ratio, h.eps, h.div_yield, h.sector
        FROM hist_to h
        LEFT JOIN drv_to dr USING (snapshot_date, tos_symbol, sequence)
        WHERE h.snapshot_date <= (SELECT d FROM p)
        ORDER BY h.tos_symbol, h.snapshot_date DESC, h.sequence DESC
    ),
    rr AS (
        SELECT r.tos_symbol,
               (SELECT MAX(snapshot_date) FROM hist_rr
                WHERE tos_symbol=r.tos_symbol AND snapshot_date<=(SELECT d FROM p)) AS rr_date,
               r.lrr AS buy_trade, r.trr AS sell_trade,
               h.outlook
        FROM drv_rr r
        LEFT JOIN LATERAL (
            SELECT outlook FROM hist_rr
            WHERE tos_symbol=r.tos_symbol AND snapshot_date<=(SELECT d FROM p)
            ORDER BY snapshot_date DESC LIMIT 1
        ) h ON TRUE
        WHERE r.as_of_date = (SELECT d FROM p)
    ),
    cl AS (
        SELECT DISTINCT ON (h.tos_symbol) h.tos_symbol,
               h.outlook AS call_outlook,
               h.outlook_modifier AS call_modifier,
               CAST(rp.value AS NUMERIC) AS call_weight
        FROM hist_call h
        LEFT JOIN ref_param rp
               ON rp.sheet = 'outlook'
              AND UPPER(rp.param_name) = UPPER(COALESCE(h.outlook,''))
        WHERE h.snapshot_date <= (SELECT d FROM p)
        ORDER BY h.tos_symbol, h.snapshot_date DESC
    ),
    ef AS (
        SELECT DISTINCT ON (h.tos_symbol) h.tos_symbol,
               h.brr AS etf_brr, h.trr AS etf_trr,
               COALESCE(h.outlook,
                  CASE WHEN h.brr > 0 THEN 'BULLISH'
                       WHEN h.brr < 0 THEN 'BEARISH'
                       ELSE 'NEUTRAL' END) AS etf_outlook
        FROM hist_etf h
        WHERE h.snapshot_date <= (SELECT d FROM p)
        ORDER BY h.tos_symbol, h.snapshot_date DESC
    ),
    ii AS (
        SELECT DISTINCT ON (h.tos_symbol) h.tos_symbol,
               h.outlook AS ii_outlook,
               CAST(rp.value AS NUMERIC) AS ii_weight
        FROM hist_ii h
        LEFT JOIN ref_param rp
               ON rp.sheet = 'outlook'
              AND UPPER(rp.param_name) = UPPER(COALESCE(h.outlook,''))
        WHERE h.snapshot_date <= (SELECT d FROM p)
        ORDER BY h.tos_symbol, h.snapshot_date DESC
    ),
    sh AS (
        SELECT DISTINCT ON (h.tos_symbol) h.tos_symbol,
               dr.signal AS SSS_signal,
               dr.signal_sign AS SSS_signal_sign,
               dr.rank_hl AS SSS_rank_hl
        FROM hist_sss h
        LEFT JOIN drv_sss dr USING (snapshot_date, tos_symbol)
        WHERE h.snapshot_date <= (SELECT d FROM p)
        ORDER BY h.tos_symbol, h.snapshot_date DESC
    ),
    fid AS (
        SELECT tos_symbol, SUM(qty) AS held_qty FROM hist_f
        WHERE snapshot_date = (
            SELECT MAX(snapshot_date) FROM hist_f WHERE snapshot_date <= (SELECT d FROM p)
        )
        GROUP BY tos_symbol
    ),
    cs AS (
        SELECT tos_symbol, SUM(qty) AS held_qty FROM hist_cs
        WHERE snapshot_date = (
            SELECT MAX(snapshot_date) FROM hist_cs WHERE snapshot_date <= (SELECT d FROM p)
        )
        GROUP BY tos_symbol
    )
    SELECT (SELECT d FROM p) AS as_of_date, s.s AS tos_symbol,
        rs.description,
        rs.equity_sector,
        rs.asset_class, rs.sub_asset_class, rs.equity_sector,
        tl.tl_date,
        COALESCE(dq.last_price,     tl.last_price)     AS last_price,
        COALESCE(dq.rsi,            tl.rsi)            AS rsi,
        COALESCE(dq.imp_volatility, tl.imp_volatility) AS imp_volatility,
        tl.volume, tl.vlm_projected,
        td.td_date, td.iv_percentile, td.hv_percentile, td.range_compression,
        td.d_iv_to_hv, td.d_vlt_caution,
        td.a_trend_value, td.a_trade_value, td.a_bb_top, td.a_bb_bottom, td.a_bb_streak,
        tw.tw_date, tw.a_macd_brr, tw.a_macdh_d_brr, tw.earnings_days,
        tw.sma_20, tw.sma_50, tw.sma_200,
        too.market_cap_str, too.beta,
        too.pe_ratio, too.eps, too.div_yield,
        rr.rr_date, rr.buy_trade AS rr_buy_trade, rr.sell_trade AS rr_sell_trade, rr.outlook AS rr_outlook,
        cl.call_outlook, cl.call_modifier, cl.call_weight,
        ef.etf_outlook, ef.etf_brr, ef.etf_trr,
        ii.ii_outlook, ii.ii_weight,
        sh.SSS_signal, sh.SSS_signal_sign, sh.SSS_rank_hl,
        fid.held_qty AS held_qty_fid, cs.held_qty AS held_qty_cs,
        -- pct_brr uses the consolidated last_price (drv_quote first, then tl).
        CASE WHEN td.a_trend_value IS NOT NULL AND td.a_trade_value IS NOT NULL
              AND (td.a_trend_value - td.a_trade_value) <> 0
             THEN (td.a_trend_value - COALESCE(dq.last_price, tl.last_price)) * 100.0
                  / (td.a_trend_value - td.a_trade_value)
        END AS pct_brr,
        (SELECT run FROM p)
    FROM syms s
    LEFT JOIN ref_sector rs ON rs.ticker = s.s
    LEFT JOIN tl  ON tl.tos_symbol  = s.s
    LEFT JOIN dq  ON dq.tos_symbol  = s.s
    LEFT JOIN td  ON td.tos_symbol  = s.s
    LEFT JOIN tw  ON tw.tos_symbol  = s.s
    LEFT JOIN too ON too.tos_symbol = s.s
    LEFT JOIN rr  ON rr.tos_symbol  = s.s
    LEFT JOIN cl  ON cl.tos_symbol  = s.s
    LEFT JOIN ef  ON ef.tos_symbol  = s.s
    LEFT JOIN ii  ON ii.tos_symbol  = s.s
    LEFT JOIN sh  ON sh.tos_symbol  = s.s
    LEFT JOIN fid ON fid.tos_symbol = s.s
    LEFT JOIN cs  ON cs.tos_symbol  = s.s
    """)

    # First wipe existing for this date
    session.execute(text("DELETE FROM drv_ma WHERE as_of_date = :d"),
                    {"d": as_of_date})
    result = session.execute(sql, {"d": as_of_date, "run": run_id})
    return result.rowcount or 0



# =============================================================================
# drv_symbols — master ticker universe for a date (2026-05-31)
# =============================================================================

def _derive_symbols_impl(session: Session, as_of_date: date, run_id: int) -> int:
    """Build drv_symbols: master ticker universe for as_of_date."""
    session.execute(
        text("DELETE FROM drv_symbols WHERE as_of_date = :d"),
        {"d": as_of_date},
    )
    result = session.execute(text("""
        INSERT INTO drv_symbols (as_of_date, tos_symbol)
        SELECT :d, s FROM (
            SELECT ticker AS s FROM ref_sector
            UNION SELECT tos_symbol FROM hist_tl
                  WHERE snapshot_date <= :d
            UNION SELECT tos_symbol FROM hist_rr
                  WHERE snapshot_date <= :d
            UNION SELECT tos_symbol FROM hist_y
                  WHERE snapshot_date <= :d
            UNION SELECT tos_symbol FROM hist_call
                  WHERE snapshot_date <= :d
            UNION SELECT tos_symbol FROM hist_etf
                  WHERE snapshot_date <= :d
            UNION SELECT tos_symbol FROM hist_ii
                  WHERE snapshot_date <= :d
        ) u WHERE s IS NOT NULL
        ON CONFLICT (as_of_date, tos_symbol) DO NOTHING
    """), {"d": as_of_date})
    return result.rowcount or 0


derive_symbols = _wrap("drv_symbols", _derive_symbols_impl)


# =============================================================================
# drv_technicals — price, technicals, MACD, SMAs (2026-05-31)
# =============================================================================

def _derive_technicals_impl(session: Session, as_of_date: date, run_id: int) -> int:
    """Populate drv_technicals for as_of_date from drv_symbols + hist sources."""
    session.execute(
        text("DELETE FROM drv_technicals WHERE as_of_date = :d"),
        {"d": as_of_date},
    )
    # Step 1: tl + dq CTEs (price/rsi/IV)
    session.execute(text("""
        CREATE TEMP TABLE _t_tech_tl ON COMMIT DROP AS
        SELECT DISTINCT ON (h.tos_symbol)
            h.tos_symbol,
            h.snapshot_date  AS tl_date,
            h.last_price, h.rsi,
            COALESCE(h.imp_volatility_raw,0) AS imp_volatility,
            h.volume,
            CASE
                WHEN h.volume IS NULL OR h.sequence < 930 THEN NULL
                WHEN h.sequence >= 1600 THEN h.volume::numeric
                WHEN ((h.sequence/100)*60+(h.sequence%100)-570) > 0
                    THEN h.volume::numeric*390.0
                         /((h.sequence/100)*60+(h.sequence%100)-570)
                ELSE NULL
            END AS vlm_projected
        FROM hist_tl h
        WHERE h.snapshot_date <= :d
        ORDER BY h.tos_symbol, h.snapshot_date DESC, h.sequence DESC
    """), {"d": as_of_date})

    session.execute(text("""
        CREATE TEMP TABLE _t_tech_dq ON COMMIT DROP AS
        SELECT DISTINCT ON (tos_symbol)
            tos_symbol, last_price, rsi, imp_volatility
        FROM drv_quote
        WHERE as_of_date <= :d
        ORDER BY tos_symbol, as_of_date DESC
    """), {"d": as_of_date})

    # Step 2: td + tw CTEs
    session.execute(text("""
        CREATE TEMP TABLE _t_tech_td ON COMMIT DROP AS
        SELECT DISTINCT ON (h.tos_symbol)
            h.tos_symbol,
            h.snapshot_date AS td_date,
            COALESCE(dr.iv_percentile, h.a_iv_percentile) AS iv_percentile,
            COALESCE(dr.hv_percentile, h.a_hv_percentile) AS hv_percentile,
            dr.range_compression, dr.d_iv_to_hv, dr.d_vlt_caution,
            h.a_trend_value, h.a_trade_value,
            h.a_bb_top, h.a_bb_bottom, h.a_bb_streak
        FROM hist_td h
        LEFT JOIN drv_td dr
               ON dr.snapshot_date = h.snapshot_date
              AND dr.tos_symbol    = h.tos_symbol
              AND dr.sequence      = h.sequence
        WHERE h.snapshot_date <= :d
        ORDER BY h.tos_symbol, h.snapshot_date DESC, h.sequence DESC
    """), {"d": as_of_date})

    session.execute(text("""
        CREATE TEMP TABLE _t_tech_tw ON COMMIT DROP AS
        SELECT DISTINCT ON (h.tos_symbol)
            h.tos_symbol,
            h.snapshot_date AS tw_date,
            dr.a_macd_brr, dr.a_macdh_d_brr,
            dr.earnings_days_d  AS earnings_days,
            dr.sma_20_d         AS sma_20,
            dr.sma_50_d         AS sma_50,
            dr.sma_200_d        AS sma_200
        FROM hist_tw h
        LEFT JOIN drv_tw dr
               ON dr.snapshot_date = h.snapshot_date
              AND dr.tos_symbol    = h.tos_symbol
              AND dr.sequence      = h.sequence
        WHERE h.snapshot_date <= :d
        ORDER BY h.tos_symbol, h.snapshot_date DESC, h.sequence DESC
    """), {"d": as_of_date})

    # Step 3a: stage ref+price cols (split to stay ≤965 bytes each)
    session.execute(text("""
        CREATE TEMP TABLE _t_tech_s1 ON COMMIT DROP AS
        SELECT s.tos_symbol,
            rs.description, rs.equity_sector,
            rs.asset_class, rs.sub_asset_class,
            tl.tl_date, tl.volume, tl.vlm_projected,
            COALESCE(dq.last_price,tl.last_price) AS last_price,
            COALESCE(dq.rsi,tl.rsi) AS rsi,
            COALESCE(dq.imp_volatility,tl.imp_volatility) AS imp_volatility
        FROM drv_symbols s
        LEFT JOIN ref_sector rs ON rs.ticker    =s.tos_symbol
        LEFT JOIN _t_tech_tl tl ON tl.tos_symbol=s.tos_symbol
        LEFT JOIN _t_tech_dq dq ON dq.tos_symbol=s.tos_symbol
        WHERE s.as_of_date=:d
    """), {"d": as_of_date})

    # Step 3b: stage technical indicator cols
    session.execute(text("""
        CREATE TEMP TABLE _t_tech_s2 ON COMMIT DROP AS
        SELECT s.tos_symbol,
            td.td_date, td.iv_percentile, td.hv_percentile,
            td.range_compression, td.d_iv_to_hv, td.d_vlt_caution,
            td.a_trend_value, td.a_trade_value,
            td.a_bb_top, td.a_bb_bottom, td.a_bb_streak,
            tw.tw_date, tw.a_macd_brr, tw.a_macdh_d_brr,
            tw.earnings_days, tw.sma_20, tw.sma_50, tw.sma_200
        FROM drv_symbols s
        LEFT JOIN _t_tech_td td ON td.tos_symbol=s.tos_symbol
        LEFT JOIN _t_tech_tw tw ON tw.tos_symbol=s.tos_symbol
        WHERE s.as_of_date=:d
    """), {"d": as_of_date})

    # Step 3c: combine stages into final INSERT-ready temp table
    # Column order MUST match drv_technicals definition exactly.
    session.execute(text("""
        CREATE TEMP TABLE _t_tech_final ON COMMIT DROP AS
        SELECT CAST(:d AS date) AS as_of_date, a.tos_symbol,
            a.description, a.equity_sector AS sector,
            a.asset_class, a.sub_asset_class, a.equity_sector,
            a.tl_date, a.last_price, a.rsi, a.imp_volatility,
            a.volume, a.vlm_projected,
            b.td_date, b.iv_percentile, b.hv_percentile,
            b.range_compression, b.d_iv_to_hv, b.d_vlt_caution,
            b.a_trend_value, b.a_trade_value, b.a_bb_top,
            b.a_bb_bottom, b.a_bb_streak,
            b.tw_date, b.a_macd_brr, b.a_macdh_d_brr, b.earnings_days,
            b.sma_20, b.sma_50, b.sma_200,
            CAST(:run AS bigint) AS source_run_id
        FROM _t_tech_s1 a
        LEFT JOIN _t_tech_s2 b USING (tos_symbol)
    """), {"d": as_of_date, "run": run_id})

    # Step 3d: insert from final stage (no explicit column list needed)
    result = session.execute(text(
        "INSERT INTO drv_technicals SELECT * FROM _t_tech_final"
    ))
    return result.rowcount or 0


derive_technicals = _wrap("drv_technicals", _derive_technicals_impl)


# =============================================================================
# drv_fundamentals — fundamental data (2026-05-31)
# =============================================================================

def _derive_fundamentals_impl(session: Session, as_of_date: date, run_id: int) -> int:
    """Populate drv_fundamentals for as_of_date."""
    session.execute(
        text("DELETE FROM drv_fundamentals WHERE as_of_date = :d"),
        {"d": as_of_date},
    )
    session.execute(text("""
        CREATE TEMP TABLE _t_fund_to ON COMMIT DROP AS
        SELECT DISTINCT ON (h.tos_symbol)
            h.tos_symbol, h.beta,
            COALESCE(dr.market_cap_num::text, h.market_cap_str) AS market_cap_str,
            h.pe_ratio, h.eps, h.div_yield
        FROM hist_to h
        LEFT JOIN drv_to dr
               ON dr.snapshot_date = h.snapshot_date
              AND dr.tos_symbol    = h.tos_symbol
              AND dr.sequence      = h.sequence
        WHERE h.snapshot_date <= :d
        ORDER BY h.tos_symbol, h.snapshot_date DESC, h.sequence DESC
    """), {"d": as_of_date})

    result = session.execute(text("""
        INSERT INTO drv_fundamentals (
            as_of_date, tos_symbol,
            market_cap_str, beta, pe_ratio, eps, div_yield,
            source_run_id
        )
        SELECT :d, s.tos_symbol,
            f.market_cap_str, f.beta, f.pe_ratio, f.eps, f.div_yield,
            :run
        FROM drv_symbols s
        LEFT JOIN _t_fund_to f ON f.tos_symbol = s.tos_symbol
        WHERE s.as_of_date = :d
    """), {"d": as_of_date, "run": run_id})
    return result.rowcount or 0


derive_fundamentals = _wrap("drv_fundamentals", _derive_fundamentals_impl)


# =============================================================================
# drv_outlooks — all outlook source signals (2026-05-31)
# =============================================================================

def _derive_outlooks_impl(session: Session, as_of_date: date, run_id: int) -> int:
    """Populate drv_outlooks for as_of_date."""
    session.execute(
        text("DELETE FROM drv_outlooks WHERE as_of_date = :d"),
        {"d": as_of_date},
    )
    # rr CTE
    session.execute(text("""
        CREATE TEMP TABLE _t_out_rr ON COMMIT DROP AS
        SELECT r.tos_symbol,
            (SELECT MAX(snapshot_date) FROM hist_rr
             WHERE tos_symbol = r.tos_symbol
               AND snapshot_date <= :d) AS rr_date,
            r.lrr AS rr_buy_trade,
            r.trr AS rr_sell_trade,
            h.outlook  AS rr_outlook
        FROM drv_rr r
        LEFT JOIN LATERAL (
            SELECT outlook FROM hist_rr
            WHERE tos_symbol = r.tos_symbol
              AND snapshot_date <= :d
            ORDER BY snapshot_date DESC LIMIT 1
        ) h ON TRUE
        WHERE r.as_of_date = :d
    """), {"d": as_of_date})

    # call CTE
    session.execute(text("""
        CREATE TEMP TABLE _t_out_cl ON COMMIT DROP AS
        SELECT DISTINCT ON (h.tos_symbol)
            h.tos_symbol,
            h.outlook           AS call_outlook,
            h.outlook_modifier  AS call_modifier,
            CAST(rp.value AS NUMERIC) AS call_weight
        FROM hist_call h
        LEFT JOIN ref_param rp
               ON rp.sheet = 'outlook'
              AND UPPER(rp.param_name) = UPPER(COALESCE(h.outlook,''))
        WHERE h.snapshot_date <= :d
        ORDER BY h.tos_symbol, h.snapshot_date DESC
    """), {"d": as_of_date})

    # etf CTE
    session.execute(text("""
        CREATE TEMP TABLE _t_out_ef ON COMMIT DROP AS
        SELECT DISTINCT ON (h.tos_symbol)
            h.tos_symbol,
            h.brr AS etf_brr, h.trr AS etf_trr,
            COALESCE(h.outlook,
                CASE WHEN h.brr > 0 THEN 'BULLISH'
                     WHEN h.brr < 0 THEN 'BEARISH'
                     ELSE 'NEUTRAL' END) AS etf_outlook
        FROM hist_etf h
        WHERE h.snapshot_date <= :d
        ORDER BY h.tos_symbol, h.snapshot_date DESC
    """), {"d": as_of_date})

    # ii CTE
    session.execute(text("""
        CREATE TEMP TABLE _t_out_ii ON COMMIT DROP AS
        SELECT DISTINCT ON (h.tos_symbol)
            h.tos_symbol,
            h.outlook AS ii_outlook,
            CAST(rp.value AS NUMERIC) AS ii_weight
        FROM hist_ii h
        LEFT JOIN ref_param rp
               ON rp.sheet = 'outlook'
              AND UPPER(rp.param_name) = UPPER(COALESCE(h.outlook,''))
        WHERE h.snapshot_date <= :d
        ORDER BY h.tos_symbol, h.snapshot_date DESC
    """), {"d": as_of_date})

    # sss CTE
    session.execute(text("""
        CREATE TEMP TABLE _t_out_sh ON COMMIT DROP AS
        SELECT DISTINCT ON (h.tos_symbol)
            h.tos_symbol,
            dr.signal       AS SSS_signal,
            dr.signal_sign  AS SSS_signal_sign,
            dr.rank_hl      AS SSS_rank_hl
        FROM hist_sss h
        LEFT JOIN drv_sss dr
               ON dr.snapshot_date = h.snapshot_date
              AND dr.tos_symbol    = h.tos_symbol
        WHERE h.snapshot_date <= :d
        ORDER BY h.tos_symbol, h.snapshot_date DESC
    """), {"d": as_of_date})

    # Stage latest drv_quote price for pct_brr calc
    session.execute(text("""
        CREATE TEMP TABLE _t_out_dq ON COMMIT DROP AS
        SELECT DISTINCT ON (tos_symbol) tos_symbol, last_price
        FROM drv_quote WHERE as_of_date <= :d
        ORDER BY tos_symbol, as_of_date DESC
    """), {"d": as_of_date})

    # Stage outlook signals part 1: rr+call+etf+ii+sss (split ≤965 bytes)
    session.execute(text("""
        CREATE TEMP TABLE _t_out_s1 ON COMMIT DROP AS
        SELECT s.tos_symbol,
            rr.rr_date, rr.rr_buy_trade, rr.rr_sell_trade, rr.rr_outlook,
            cl.call_outlook, cl.call_modifier, cl.call_weight,
            ef.etf_outlook, ef.etf_brr, ef.etf_trr,
            ii.ii_outlook, ii.ii_weight,
            sh.SSS_signal, sh.SSS_signal_sign, sh.SSS_rank_hl
        FROM drv_symbols s
        LEFT JOIN _t_out_rr rr ON rr.tos_symbol=s.tos_symbol
        LEFT JOIN _t_out_cl cl ON cl.tos_symbol=s.tos_symbol
        LEFT JOIN _t_out_ef ef ON ef.tos_symbol=s.tos_symbol
        LEFT JOIN _t_out_ii ii ON ii.tos_symbol=s.tos_symbol
        LEFT JOIN _t_out_sh sh ON sh.tos_symbol=s.tos_symbol
        WHERE s.as_of_date=:d
    """), {"d": as_of_date})

    # Stage outlook part 2: pct_brr computation (needs drv_technicals)
    session.execute(text("""
        CREATE TEMP TABLE _t_out_stage ON COMMIT DROP AS
        SELECT a.*,
            CASE
                WHEN t.a_trend_value IS NOT NULL
                 AND t.a_trade_value IS NOT NULL
                 AND (t.a_trend_value-t.a_trade_value)<>0
                THEN (t.a_trend_value
                      -COALESCE(dq.last_price,t.last_price))*100.0
                     /(t.a_trend_value-t.a_trade_value)
            END AS pct_brr
        FROM _t_out_s1 a
        LEFT JOIN drv_technicals t
               ON t.as_of_date=:d AND t.tos_symbol=a.tos_symbol
        LEFT JOIN _t_out_dq dq ON dq.tos_symbol=a.tos_symbol
    """), {"d": as_of_date})

    result = session.execute(text("""
        INSERT INTO drv_outlooks (
            as_of_date, tos_symbol,
            rr_date, rr_buy_trade, rr_sell_trade, rr_outlook,
            call_outlook, call_modifier, call_weight,
            etf_outlook, etf_brr, etf_trr,
            ii_outlook, ii_weight,
            SSS_signal, SSS_signal_sign, SSS_rank_hl,
            pct_brr, source_run_id
        )
        SELECT :d, tos_symbol,
            rr_date, rr_buy_trade, rr_sell_trade, rr_outlook,
            call_outlook, call_modifier, call_weight,
            etf_outlook, etf_brr, etf_trr,
            ii_outlook, ii_weight,
            SSS_signal, SSS_signal_sign, SSS_rank_hl,
            pct_brr, :run
        FROM _t_out_stage
    """), {"d": as_of_date, "run": run_id})
    return result.rowcount or 0


derive_outlooks = _wrap("drv_outlooks", _derive_outlooks_impl)


# =============================================================================
# drv_portfolio — holdings snapshot (2026-05-31)
# =============================================================================

def _derive_portfolio_impl(session: Session, as_of_date: date, run_id: int) -> int:
    """Populate drv_portfolio for as_of_date."""
    session.execute(
        text("DELETE FROM drv_portfolio WHERE as_of_date = :d"),
        {"d": as_of_date},
    )
    session.execute(text("""
        CREATE TEMP TABLE _t_port_fid ON COMMIT DROP AS
        SELECT tos_symbol, SUM(qty) AS held_qty
        FROM hist_f
        WHERE snapshot_date = (
            SELECT MAX(snapshot_date) FROM hist_f
            WHERE snapshot_date <= :d
        )
        GROUP BY tos_symbol
    """), {"d": as_of_date})

    session.execute(text("""
        CREATE TEMP TABLE _t_port_cs ON COMMIT DROP AS
        SELECT tos_symbol, SUM(qty) AS held_qty
        FROM hist_cs
        WHERE snapshot_date = (
            SELECT MAX(snapshot_date) FROM hist_cs
            WHERE snapshot_date <= :d
        )
        GROUP BY tos_symbol
    """), {"d": as_of_date})

    result = session.execute(text("""
        INSERT INTO drv_portfolio (
            as_of_date, tos_symbol,
            held_qty_fid, held_qty_cs,
            source_run_id
        )
        SELECT
            :d, s.tos_symbol,
            fid.held_qty AS held_qty_fid,
            cs.held_qty  AS held_qty_cs,
            :run
        FROM drv_symbols s
        LEFT JOIN _t_port_fid fid ON fid.tos_symbol = s.tos_symbol
        LEFT JOIN _t_port_cs  cs  ON cs.tos_symbol  = s.tos_symbol
        WHERE s.as_of_date = :d
    """), {"d": as_of_date, "run": run_id})
    return result.rowcount or 0


derive_portfolio = _wrap("drv_portfolio", _derive_portfolio_impl)


derive_ma = _wrap("drv_ma", _derive_ma_impl)


# ─────────────────────────────────────────────────────────────────────────────
# drv_quote — latest-source-wins consolidation of shared quote fields.
#
# Sources: hist_y, hist_tl, hist_td.
# Fields:  last_price, net_chng, pct_change, open_price, high_price, low_price,
#          rsi, imp_volatility.
#
# For each (as_of_date, symbol) we pick, for each field, the row across the
# three sources with the highest loaded_at AND non-NULL value. If the highest
# loaded_at row has a NULL for that field, we fall through to the next-latest
# source's row. Each source contributes one row per symbol — its latest
# snapshot ≤ as_of_date, with same-day ties broken by (loaded_at DESC,
# sequence DESC).
#
# imp_volatility: hist_td has `imp_volatility`, hist_tl has `imp_volatility_raw`.
# Per design decision Option A, we unify under the single drv_quote column; TD
# wins if non-NULL, else TL's _raw, else NULL.
# ─────────────────────────────────────────────────────────────────────────────

# Order matters only for stable iteration; the merge picks by loaded_at, not
# by this list. Fields per source (None = source doesn't have the field).
_QUOTE_FIELDS = (
    'last_price', 'net_chng', 'pct_change',
    'open_price', 'high_price', 'low_price',
    'rsi',        'imp_volatility',
)


def _latest_per_symbol(session: Session, table: str, as_of_date: date,
                       column_map: dict) -> dict:
    """Return {tos_symbol: {drv_field: value, ..., 'loaded_at': ts, 'snapshot_date': d, 'export_date': d, 'export_time': t}} for the latest
    snapshot ≤ as_of_date in `table`. Per source PK is (snapshot_date, tos_symbol,
    sequence); within the latest snapshot_date we order by loaded_at DESC,
    sequence DESC so the topmost row wins.

    `column_map` maps drv_quote field name -> source-table column name (or
    None if the source doesn't expose that field).
    """
    # Build SELECT list aliased to drv_quote field names so downstream code
    # can use a single shape. Columns the source doesn't have are selected as
    # NULL literals.
    select_parts = ['tos_symbol AS symbol', 'snapshot_date', 'loaded_at', 'export_date', 'export_time']
    for drv_field, src_col in column_map.items():
        if src_col is None:
            select_parts.append(f'NULL::NUMERIC AS {drv_field}')
        else:
            select_parts.append(f'{src_col} AS {drv_field}')
    sel = ', '.join(select_parts)

    sql = text(f"""
        SELECT DISTINCT ON (tos_symbol) {sel}
          FROM {table}
         WHERE snapshot_date <= :d
         ORDER BY tos_symbol, snapshot_date DESC, loaded_at DESC, sequence DESC
    """)
    out = {}
    for r in session.execute(sql, {"d": as_of_date}).mappings():
        out[r['symbol']] = dict(r)
    return out


def _derive_y_impl(session: Session, as_of_date: date, run_id: int) -> int:
    """Convert hist_y float_str and shares_out_str to NUMERIC in drv_y.

    Idempotent: DELETE WHERE snapshot_date=D then INSERT.
    Handles "--" (missing) and M/K suffixes (million/thousand multipliers).
    """
    rows = session.execute(text("""
        SELECT DISTINCT ON (tos_symbol) tos_symbol, snapshot_date,
               CASE WHEN float_str IS NULL OR float_str = '--' THEN NULL
                    WHEN RIGHT(UPPER(TRIM(float_str)), 1) = 'B'
                      THEN REGEXP_REPLACE(REPLACE(float_str, ',', ''), '[^0-9.]', '', 'g')::NUMERIC * 1000000000
                    WHEN RIGHT(UPPER(TRIM(float_str)), 1) = 'M'
                      THEN REGEXP_REPLACE(REPLACE(float_str, ',', ''), '[^0-9.]', '', 'g')::NUMERIC * 1000000
                    WHEN RIGHT(UPPER(TRIM(float_str)), 1) = 'K'
                      THEN REGEXP_REPLACE(REPLACE(float_str, ',', ''), '[^0-9.]', '', 'g')::NUMERIC * 1000
                    ELSE REGEXP_REPLACE(REPLACE(float_str, ',', ''), '[^0-9.]', '', 'g')::NUMERIC
               END AS float,
               CASE WHEN shares_out_str IS NULL OR shares_out_str = '--' THEN NULL
                    WHEN RIGHT(UPPER(TRIM(shares_out_str)), 1) = 'B'
                      THEN REGEXP_REPLACE(REPLACE(shares_out_str, ',', ''), '[^0-9.]', '', 'g')::NUMERIC * 1000000000
                    WHEN RIGHT(UPPER(TRIM(shares_out_str)), 1) = 'M'
                      THEN REGEXP_REPLACE(REPLACE(shares_out_str, ',', ''), '[^0-9.]', '', 'g')::NUMERIC * 1000000
                    WHEN RIGHT(UPPER(TRIM(shares_out_str)), 1) = 'K'
                      THEN REGEXP_REPLACE(REPLACE(shares_out_str, ',', ''), '[^0-9.]', '', 'g')::NUMERIC * 1000
                    ELSE REGEXP_REPLACE(REPLACE(shares_out_str, ',', ''), '[^0-9.]', '', 'g')::NUMERIC
               END AS shares_out
          FROM hist_y
         WHERE snapshot_date = :d
         ORDER BY tos_symbol, loaded_at DESC, sequence DESC
    """), {"d": as_of_date}).mappings().all()

    out = [
        {
            "snapshot_date": r["snapshot_date"],
            "tos_symbol": r["tos_symbol"],
            "float": r["float"],
            "shares_out": r["shares_out"],
            "source_run_id": run_id,
        }
        for r in rows
    ]
    return replace_for_date(session, "drv_y", "snapshot_date", as_of_date, out)


derive_y = _wrap("drv_y", _derive_y_impl)


def _derive_quote_impl(session: Session, as_of_date: date, run_id: int) -> int:
    """Build drv_quote rows for as_of_date. Idempotent: DELETE then INSERT."""

    # Field name → source-table column name. None = field not present in source.
    cmap_y = {
        'last_price':      'last_price',
        'net_chng':        'change_amt',   # different name in hist_y
        'pct_change':      'change_pct',
        'open_price':      'open_price',
        'high_price':      'high_price',
        'low_price':       'low_price',
        'rsi':             None,           # hist_y doesn't track RSI
        'imp_volatility':  None,           # hist_y doesn't track IV
    }
    cmap_tl = {
        'last_price':      'last_price',
        'net_chng':        'net_chng',
        'pct_change':      'change_pct',
        'open_price':      'open_price',
        'high_price':      'high_price',
        'low_price':       'low_price',
        'rsi':             'rsi',
        'imp_volatility':  'imp_volatility_raw',
    }
    cmap_td = {
        'last_price':      'last_price',
        'net_chng':        'net_chng',
        'pct_change':      'change_pct',
        'open_price':      'open_price',
        'high_price':      'high_price',
        'low_price':       'low_price',
        'rsi':             'rsi',
        'imp_volatility':  'imp_volatility',
    }

    rows_y  = _latest_per_symbol(session, 'hist_y',  as_of_date, cmap_y)
    rows_tl = _latest_per_symbol(session, 'hist_tl', as_of_date, cmap_tl)
    rows_td = _latest_per_symbol(session, 'hist_td', as_of_date, cmap_td)

    # Union of all symbols seen across the three sources.
    all_symbols = set(rows_y) | set(rows_tl) | set(rows_td)
    if not all_symbols:
        return 0

    merged: list[dict] = []
    for sym in all_symbols:
        tl_row = rows_tl.get(sym)
        y_row  = rows_y.get(sym)
        td_row = rows_td.get(sym)

        # Prefer TL over Y only when both are from the same snapshot_date
        # (same trading session — matches Excel "L" flag / Dash!AB24).
        # When sessions differ, fall back to latest-loaded-at across all sources.
        same_session = (
            tl_row is not None and y_row is not None
            and tl_row.get('snapshot_date') == y_row.get('snapshot_date')
        )
        if same_session:
            # TL → TD → Y priority (TL is preferred for the current session)
            candidates = [r for r in (tl_row, td_row, y_row) if r is not None]
        else:
            # Different sessions: latest loaded_at wins
            candidates = [r for r in (tl_row, td_row, y_row) if r is not None]
            candidates.sort(key=lambda r: r.get('loaded_at') or 0, reverse=True)

        rec = {'as_of_date': as_of_date, 'tos_symbol': sym, 'export_date': None, 'export_time': None, 'loaded_at': None}
        for f in _QUOTE_FIELDS:
            val = None
            for cand in candidates:
                v = cand.get(f)
                if v is not None:
                    val = v
                    # Capture export_date and export_time from the first non-null field's source
                    if rec['export_date'] is None:
                        rec['export_date'] = cand.get('export_date')
                        rec['export_time'] = cand.get('export_time')
                    # Capture loaded_at from the latest candidate (highest loaded_at)
                    if rec['loaded_at'] is None:
                        rec['loaded_at'] = cand.get('loaded_at')
                    break
            rec[f] = val
        merged.append(rec)

    # Idempotent rebuild for as_of_date.
    session.execute(text("DELETE FROM drv_quote WHERE as_of_date = :d"),
                    {"d": as_of_date})

    if merged:
        session.execute(
            text("""
                INSERT INTO drv_quote
                    (as_of_date, tos_symbol,
                     last_price, net_chng, pct_change,
                     open_price, high_price, low_price,
                     rsi, imp_volatility, export_date, export_time, loaded_at)
                VALUES (:as_of_date, :tos_symbol,
                        :last_price, :net_chng, :pct_change,
                        :open_price, :high_price, :low_price,
                        :rsi, :imp_volatility, :export_date, :export_time, :loaded_at)
            """),
            merged,
        )

    return len(merged)


derive_quote = _wrap("drv_quote", _derive_quote_impl)


def backfill_drv_quote(d_start: date, d_end: date) -> dict:
    """Populate drv_quote for every weekday in [d_start, d_end] that has no entry yet.

    Safe to re-run: skips dates already present. Each date picks the latest
    loaded source data (snapshot_date <= as_of_date) so prices repeat between
    file loads — correct behaviour for a latest-loaded-wins merge.
    """
    from datetime import timedelta
    from etl.db import session_scope

    with session_scope() as s:
        existing = {
            r[0] for r in s.execute(text(
                "SELECT DISTINCT as_of_date FROM drv_quote "
                "WHERE as_of_date >= :s AND as_of_date <= :e"
            ), {"s": d_start, "e": d_end}).fetchall()
        }

    missing = []
    d = d_start
    while d <= d_end:
        if d.weekday() < 5 and d not in existing:
            missing.append(d)
        d += timedelta(days=1)

    log.info("backfill_drv_quote: %d weekdays to fill (%s → %s)",
             len(missing), d_start, d_end)

    rows_total = 0
    errors = 0
    for d in missing:
        try:
            with session_scope() as s:
                n = derive_quote(s, d)
                rows_total += n
        except Exception:
            log.exception("backfill_drv_quote: %s failed", d)
            errors += 1

    log.info("backfill_drv_quote: done — %d rows across %d dates (%d errors)",
             rows_total, len(missing), errors)
    return {"dates_processed": len(missing), "rows_inserted": rows_total, "errors": errors}


def _derive_rr_impl(session: Session, as_of_date: date, run_id: int) -> int:
    """Derive risk range (LRR/TRR) per symbol: hist_rr preferred, hist_td BB bands fallback.

    Idempotent: DELETE WHERE as_of_date=D then INSERT.
    source='RR' when hist_rr has data, 'BB' when falling back to a_bb_bottom/a_bb_top.
    """
    session.execute(text(
        "DELETE FROM drv_rr WHERE as_of_date = :d"), {"d": as_of_date})

    result = session.execute(text("""
        INSERT INTO drv_rr (as_of_date, tos_symbol, lrr, trr, mrr, source, source_run_id)
        SELECT
            :d AS as_of_date,
            s.tos_symbol,
            -- reverse='Y' symbols (yield-quoted, e.g. TNX:CGI): hist_rr stores yield %
            -- but TOS displays yield×10.  Scale by 10 when sourced from hist_rr only.
            -- BB fallback (hist_td) is already in TOS display units — no scaling.
            CASE WHEN rrt.reverse = 'Y' AND NULLIF(rr.buy_trade, 0) IS NOT NULL
                 THEN rr.buy_trade * 10
                 ELSE COALESCE(NULLIF(rr.buy_trade, 0), td.a_bb_bottom)
                 END                              AS lrr,
            CASE WHEN rrt.reverse = 'Y' AND NULLIF(rr.sell_trade, 0) IS NOT NULL
                 THEN rr.sell_trade * 10
                 ELSE COALESCE(NULLIF(rr.sell_trade, 0), td.a_bb_top)
                 END                              AS trr,
            CASE WHEN NULLIF(rr.buy_trade, 0) IS NOT NULL
                  AND NULLIF(rr.sell_trade, 0) IS NOT NULL
                 THEN (rr.buy_trade + rr.sell_trade)
                      * CASE WHEN rrt.reverse = 'Y' THEN 5.0 ELSE 0.5 END
                 WHEN td.a_bb_bottom IS NOT NULL AND td.a_bb_top IS NOT NULL
                 THEN (td.a_bb_bottom + td.a_bb_top) / 2.0
                 ELSE NULL END                    AS mrr,
            CASE WHEN NULLIF(rr.buy_trade, 0) IS NOT NULL THEN 'RR' ELSE 'BB' END AS source,
            :run AS source_run_id
        FROM (
            SELECT DISTINCT tos_symbol FROM hist_td WHERE snapshot_date <= :d
            UNION
            SELECT DISTINCT tos_symbol FROM hist_rr WHERE snapshot_date <= :d
        ) s
        LEFT JOIN (
            SELECT DISTINCT ON (tos_ticker) tos_ticker, reverse
            FROM ref_rrt ORDER BY tos_ticker, loaded_at DESC
        ) rrt ON rrt.tos_ticker = s.tos_symbol
        LEFT JOIN LATERAL (
            SELECT buy_trade, sell_trade
            FROM hist_rr
            WHERE tos_symbol = s.tos_symbol AND snapshot_date <= :d
            ORDER BY snapshot_date DESC LIMIT 1
        ) rr ON TRUE
        LEFT JOIN LATERAL (
            -- DU/DV in Excel = BB_Bot/Top_Prev = PRIOR session's BB bands.
            -- Use snapshot_date < :d (strictly less) to match Excel's "Prev" semantics.
            SELECT a_bb_bottom, a_bb_top
            FROM hist_td
            WHERE tos_symbol = s.tos_symbol AND snapshot_date < :d
            ORDER BY snapshot_date DESC, sequence DESC LIMIT 1
        ) td ON TRUE
        WHERE COALESCE(rr.buy_trade, td.a_bb_bottom) IS NOT NULL
           OR COALESCE(rr.sell_trade, td.a_bb_top) IS NOT NULL
    """), {"d": as_of_date, "run": run_id})
    return result.rowcount or 0


derive_rr = _wrap("drv_rr", _derive_rr_impl)


def backfill_drv_rr(d_start: date, d_end: date) -> dict:
    """Populate drv_rr for every weekday in [d_start, d_end] that has no entry yet.

    Safe to re-run: skips dates already present. Values between file loads are
    flat (repeating last loaded RR via snapshot_date <= as_of_date laterals),
    which is correct — RR bands only change when a new file is loaded.
    """
    from datetime import timedelta
    from etl.db import session_scope

    with session_scope() as s:
        existing = {
            r[0] for r in s.execute(text(
                "SELECT DISTINCT as_of_date FROM drv_rr "
                "WHERE as_of_date >= :s AND as_of_date <= :e"
            ), {"s": d_start, "e": d_end}).fetchall()
        }

    missing = []
    d = d_start
    while d <= d_end:
        if d.weekday() < 5 and d not in existing:
            missing.append(d)
        d += timedelta(days=1)

    log.info("backfill_drv_rr: %d weekdays to fill (%s → %s)",
             len(missing), d_start, d_end)

    rows_total = 0
    errors = 0
    for d in missing:
        try:
            with session_scope() as s:
                n = derive_rr(s, d)
                rows_total += n
        except Exception:
            log.exception("backfill_drv_rr: %s failed", d)
            errors += 1

    log.info("backfill_drv_rr: done — %d rows across %d dates (%d errors)",
             rows_total, len(missing), errors)
    return {"dates_processed": len(missing), "rows_inserted": rows_total, "errors": errors}


# Section classification used by drv_dash
_VOLATILITY = {"^VIX","^VVIX","^RVX","^VXN","^GVZ","^OVX","^MOVE","^VXD"}
_INDEX = {"^SPX","^IXIC","^RUT","HYG","LQD","^GDAXI","^N225"}
_TREASURY = {"^TYX","^TNX","2YY=F"}
_FX = {"EURUSD=X","JPYUSD=X","GBPUSD=X","CADUSD=X","^NYICDX"}
_COMMODITY = {"CL=F","BZ=F","NG=F","GC=F","HG=F","SI=F","PPLT"}
_SECTOR_PFX = ("XL",)
_SECTOR_OTHER = {"PINK","IAK","GDX","URA","ITA","SPMO"}


def _classify_section(symbol: str) -> str:
    if symbol in _VOLATILITY: return "Volatility"
    if symbol in _INDEX:      return "Index"
    if symbol in _TREASURY:   return "Treasury"
    if symbol in _FX:         return "FX"
    if symbol in _COMMODITY:  return "Commodity"
    if symbol in _SECTOR_OTHER or any(symbol.startswith(p) for p in _SECTOR_PFX):
        return "Sector"
    return "Stock"


def _derive_dash_impl(session: Session, as_of_date: date, run_id: int) -> int:
    """
    drv_dash: project drv_ma rows into the Dash layout, classifying section.

    threshold_low / threshold_high are read from ref_settings
    (`dash_threshold_low_pct`, `dash_threshold_high_pct`) and applied against
    each row's `pct_brr` to compute zone_signal:
        'Y' (Yes — accumulate / below low band) when pct_brr <= threshold_low
        'N' (No  — exit / above high band)      when pct_brr >= threshold_high
        'W' (Watch — between)                   otherwise
        NULL                                    when pct_brr is NULL
    Defaults are -10 and +10 percent. Tune in ref_settings (no code change).
    """
    # Read configurable bands.  Anything unparseable falls back to defaults.
    settings = dict(session.execute(text(
        "SELECT setting_name, setting_value FROM ref_settings "
        "WHERE setting_name IN ('dash_threshold_low_pct', 'dash_threshold_high_pct')"
    )).fetchall())
    def _f(key, default):
        try:
            return float(settings.get(key, default))
        except (TypeError, ValueError):
            return float(default)
    th_low  = _f("dash_threshold_low_pct",  -10.0)
    th_high = _f("dash_threshold_high_pct",  10.0)

    rows = session.execute(text("""
        SELECT tos_symbol, description, last_price,
               a_trend_value, a_trade_value, pct_brr,
               rr_outlook, rr_brr, call_outlook, sector, asset_class
        FROM drv_ma WHERE as_of_date = :d
    """), {"d": as_of_date}).mappings().all()

    out = []
    for r in rows:
        pct = r["pct_brr"]
        if pct is None:
            zone = None
        else:
            try:
                p = float(pct)
                if p <= th_low:
                    zone = "Y"
                elif p >= th_high:
                    zone = "N"
                else:
                    zone = "W"
            except (TypeError, ValueError):
                zone = None
        out.append({
            "as_of_date": as_of_date,
            "section": _classify_section(r["tos_symbol"] or ""),
            "tos_symbol": r["tos_symbol"],
            "description": r["description"],
            "last_price": r["last_price"],
            "a_trend_value": r["a_trend_value"],
            "a_trade_value": r["a_trade_value"],
            "pct_brr": pct,
            "rr_outlook": r["rr_outlook"],
            "rr_brr": r["rr_brr"],
            "call_outlook": r["call_outlook"],
            "sector": r["sector"],
            "asset_class": r["asset_class"],
            "threshold_low": th_low,
            "threshold_high": th_high,
            "zone_signal": zone,
            "source_run_id": run_id,
        })
    return replace_for_date(session, "drv_dash", "as_of_date", as_of_date, out)


derive_dash = _wrap("drv_dash", _derive_dash_impl)


def _composite_outlook(rr_brr, call_outlook, etf_outlook, ii_outlook, sss_signal_sign):
    """
    Simple ensemble: each source contributes -1/0/+1, sum then normalize.
    """
    score = 0
    contributions = 0
    if rr_brr is not None:
        score += 1 if rr_brr > 0 else (-1 if rr_brr < 0 else 0)
        contributions += 1
    for o in (call_outlook, etf_outlook, ii_outlook):
        if not o:
            continue
        u = o.upper()
        if "BULL" in u: score += 1; contributions += 1
        elif "BEAR" in u: score -= 1; contributions += 1
        else: contributions += 1
    if sss_signal_sign is not None:
        score += 1 if sss_signal_sign > 0 else (-1 if sss_signal_sign < 0 else 0)
        contributions += 1
    if contributions == 0:
        return None, None
    label = "BULLISH" if score > 0 else ("BEARISH" if score < 0 else "NEUTRAL")
    return score, label


_BUY_PREFIXES  = {'B','BS','BR','BW','BM','BMN'}
_SELL_PREFIXES = {'SA','SS','STM','SW','SH'}

def _composite_operator(code: str, threshold) -> str:
    """Return '>=' for BUY rules, '<=' for SELL rules, else derive from threshold sign."""
    import re
    m = re.match(r'^\d+-([A-Z]+)-', code or '')
    if m:
        p = m.group(1)
        if p in _BUY_PREFIXES:  return '>='
        if p in _SELL_PREFIXES: return '<='
    # fallback: positive threshold → >=, negative → <=
    try:
        return '>=' if float(threshold) >= 0 else '<='
    except (TypeError, ValueError):
        return '>='


def _eval_precondition(expr: str, row: dict) -> bool:
    """
    Safely evaluate a compound precondition expression against a drv_ma row.

    Supports:
      - Names: any column on the row (case-sensitive), plus a few derived aliases
        listed in DERIVED_PRECOND_ALIASES below.
      - Literals: int / float / str ('quoted') / True / False / None
      - Comparisons:  ==  !=  <  <=  >  >=  in  not in
      - Boolean ops:  and  or  not
      - Parentheses for grouping
      - SQL-style synonyms: =, <>, AND, OR, NOT, IS NULL, IS NOT NULL
        (lowercased before parsing for AST compatibility)

    Derived aliases (computed from the row before evaluation):
      is_held       — True when held_today is truthy
      is_etf        — True when sector == 'ETF' or asset_class == 'ETF'
      is_equity     — True when asset_class == 'Equity'
      has_position  — True when current_position_dollar > 0

    Examples:
      sector != 'ETF'
      is_held and last_price > 5
      sector in ('Information Technology', 'Health Care')
      rsi is not None and rsi > 30
      is_equity and not is_held

    Fails-OPEN by design: returns True on any parse / type / lookup error,
    so an unparseable precondition never silently kills a composite.  The
    error is logged so the rule manager UI can surface it.
    """
    if not expr or not expr.strip():
        return True

    src = expr.strip()
    # SQL-isms → Python-isms (case-insensitive replace, careful with word boundaries)
    import re as _re
    repls = [
        (r"\bAND\b", "and"), (r"\bOR\b", "or"),  (r"\bNOT\b", "not"),
        (r"\bIS\s+NOT\s+NULL\b", "is not None"), (r"\bIS\s+NULL\b", "is None"),
        (r"\bIN\b", "in"),
        (r"<>", "!="), (r"(?<![<>!=])=(?!=)", "=="),
    ]
    for pat, sub in repls:
        src = _re.sub(pat, sub, src, flags=_re.IGNORECASE)

    import ast
    ALLOWED = (
        ast.Expression, ast.BoolOp, ast.UnaryOp, ast.Compare, ast.Name, ast.Load,
        ast.Constant, ast.Tuple, ast.List, ast.And, ast.Or, ast.Not,
        ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn,
        ast.Is, ast.IsNot,
    )
    try:
        tree = ast.parse(src, mode="eval")
        for node in ast.walk(tree):
            if not isinstance(node, ALLOWED):
                log.warning("precondition_expr disallowed node %s in %r — failing open",
                            type(node).__name__, expr)
                return True
        # Compute derived aliases from the row so users can write natural
        # expressions like "is_held and last_price > 5".
        sector_v = row.get("sector")
        asset_class_v = row.get("asset_class")
        pos_dollar = row.get("current_position_dollar") or row.get("position_dollar")
        try:
            pos_num = float(pos_dollar) if pos_dollar is not None else 0.0
        except (TypeError, ValueError):
            pos_num = 0.0
        derived = {
            "is_held":      bool(row.get("held_today")),
            "is_etf":       (sector_v == "ETF") or (asset_class_v == "ETF"),
            "is_equity":    (asset_class_v == "Equity"),
            "has_position": pos_num > 0,
        }
        # Build a name namespace from the row + derived aliases.  Row keys win
        # over derived names so a column literally named `is_held` (if added
        # later) would shadow the alias.
        ns_data = {**derived, **row}
        class _Namespace(dict):
            def __missing__(self, k):
                return None  # undefined names eval to None
        ns = _Namespace(ns_data)
        result = eval(compile(tree, "<precond>", "eval"), {"__builtins__": {}}, ns)
        return bool(result)
    except Exception as e:
        log.warning("precondition_expr eval failed for %r (%s) — failing open", expr, e)
        return True


def _resolve_atomic_input_column(session: Session) -> dict:
    """Build {atomic_rule_id: drv_cat_atomic_input_column_name}.

    Resolution order (first match wins):
      1. ref_ma_columns where excel_header = rule_name AND drv_cat_table = 'drv_cat_atomic_input'
      2. ref_ma_columns where excel_header = rule_name (any drv_cat_table — for cross-stage reads)
      3. _MA_COL_MAP[rule_name] — legacy fallback against drv_ma columns
      4. ma_column_name parsed as 'drv_ma.<col>' or 'drv_cat_atomic_input.<col>' — modern FQN
    Returns {atomic_rule_id: (table_name, column_name)} so the caller knows where to read.
    """
    out: dict = {}
    rules = session.execute(text("""
        SELECT atomic_rule_id, rule_name, ma_column_name
        FROM ref_trig_atomic_rule
        WHERE deprecated_at IS NULL
    """)).mappings().all()
    if not rules:
        return out

    # Pre-fetch registry lookups for every rule_name AND every ma_column_name.
    # We union both so step 5 (ma_column_name fallback) can hit the cache too.
    names_set: set[str] = set()
    for r in rules:
        if r.get("rule_name"):
            names_set.add(r["rule_name"])
        if r.get("ma_column_name"):
            names_set.add(r["ma_column_name"])
    names = sorted(names_set)
    reg: dict = {}
    if names:
        reg_rows = session.execute(
            text("""
                SELECT excel_header, column_name, drv_cat_table
                FROM ref_ma_columns
                WHERE excel_header = ANY(:names)
                ORDER BY CASE WHEN drv_cat_table = 'drv_cat_atomic_input' THEN 0 ELSE 1 END
            """),
            {"names": names},
        ).mappings().all()
        for row in reg_rows:
            # First (preferred) hit per excel_header wins because of the ORDER BY
            reg.setdefault(row["excel_header"], (row["drv_cat_table"], row["column_name"]))

    for r in rules:
        rid = r["atomic_rule_id"]
        rule_name = r.get("rule_name") or ""
        ma_col = r.get("ma_column_name") or ""

        # 1+2. Registry lookup by rule_name
        hit = reg.get(rule_name)
        if hit:
            out[rid] = hit
            continue
        # 3. Legacy _MA_COL_MAP keyed on rule_name
        legacy_col = _MA_COL_MAP.get(rule_name)
        if legacy_col:
            out[rid] = ("drv_ma", legacy_col)
            continue
        # 4. ma_column_name as FQN  ('drv_ma.x' or 'drv_cat_atomic_input.x')
        if "." in ma_col:
            tbl, _, col = ma_col.partition(".")
            out[rid] = (tbl, col)
            continue
        # 5. NEW (2026-05-12): try ma_column_name as a bare excel_header against
        #    ref_ma_columns. Defends against rows where rule_name was never
        #    populated (older DB state) — the loader now mirrors col L into
        #    both rule_name and ma_column_name, but this fallback keeps an
        #    older DB from going dark until reloaded.
        hit = reg.get(ma_col)
        if hit:
            out[rid] = hit
            continue
        # 6. Legacy _MA_COL_MAP keyed on ma_column_name
        legacy_col = _MA_COL_MAP.get(ma_col)
        if legacy_col:
            out[rid] = ("drv_ma", legacy_col)
            continue
        # Unresolvable — leave out so eval falls through to None/0
        log.warning(
            "atomic rule %s ('%s') has no resolvable ma column "
            "(ma_column_name=%r) — will evaluate to 0",
            rid, rule_name, ma_col,
        )
    return out


def _fetch_eval_rows(session: Session, as_of_date: date,
                     atomic_col_map: dict) -> list:
    """Read drv_ma JOIN drv_cat_atomic_input → one wide dict per symbol.

    Returns rows that contain every column referenced by atomic_col_map plus
    drv_ma's identity / display columns.  Reading via a single LEFT JOIN keeps
    the per-symbol Python loop ignorant of which physical table holds the value.
    """
    # Distinct (table, column) pairs we need to project
    needed = set(atomic_col_map.values())
    drv_ma_cols = {col for (tbl, col) in needed if tbl == "drv_ma"}
    cat_cols    = {col for (tbl, col) in needed if tbl == "drv_cat_atomic_input"}

    # Always include drv_ma display columns _derive_stks_impl needs
    # Note: drv_ma uses tos_symbol only (symbol was dropped in migration)
    base_cols = {
        "tos_symbol","description","sector","asset_class","last_price",
        "a_trend_value","a_trade_value","pct_brr","rr_outlook","rr_brr",
        "call_outlook","call_modifier","etf_outlook","ii_outlook",
        "sss_signal_sign","iv_percentile","rsi","earnings_days","market_cap_str",
    }
    drv_ma_cols |= base_cols

    # Build select list with prefixes
    ma_select = ", ".join(f"m.{c}" for c in sorted(drv_ma_cols))
    if cat_cols:
        cat_select = ", " + ", ".join(
            f'a."{c}" AS "ai_{c}"' if not c.replace("_","").isalnum() or c[:1].isdigit()
            else f"a.{c} AS ai_{c}"
            for c in sorted(cat_cols)
        )
    else:
        cat_select = ""

    sql = text(f"""
        SELECT {ma_select}{cat_select}
        FROM drv_ma m
        LEFT JOIN drv_cat_atomic_input a
          ON a.as_of_date = m.as_of_date AND a.tos_symbol = m.tos_symbol
        WHERE m.as_of_date = :d
    """)
    rows = []
    try:
        for r in session.execute(sql, {"d": as_of_date}).mappings().all():
            rows.append(dict(r))
    except Exception as e:
        # drv_cat_atomic_input may not exist yet on a fresh DB — fall back to drv_ma only
        log.warning("drv_cat_atomic_input read failed (%s); falling back to drv_ma only", e)
        rows = [dict(r) for r in session.execute(
            text(f"SELECT {ma_select} FROM drv_ma m WHERE m.as_of_date = :d"),
            {"d": as_of_date},
        ).mappings().all()]
    return rows


def _read_atomic_value(row: dict, src: tuple):
    """Read a column from the eval row, handling table prefix routing."""
    tbl, col = src
    if tbl == "drv_cat_atomic_input":
        return row.get(f"ai_{col}")
    return row.get(col)  # drv_ma or any other table joined into the SELECT


def _derive_stks_impl(session: Session, as_of_date: date, run_id: int) -> int:
    # Fetch atomic rules with scoring mode info
    atomic_rules = session.execute(text("""
        SELECT atomic_rule_id, scoring_mode, score_params, brkeout_from, brkeout_to,
               wt_below, wt_between, wt_above, ma_column_name
        FROM ref_trig_atomic_rule
        WHERE deprecated_at IS NULL
    """)).mappings().all()

    # Fetch composite rule mappings.  After db/baseline.sql
    # is applied, members can be one of three kinds: 'atomic' | 'data' | 'composite'.
    # We try the extended schema first, fall back to the legacy atomic-only one.
    try:
        composite_mappings = session.execute(text("""
            SELECT composite_rule_code, COALESCE(member_kind, 'atomic') AS member_kind,
                   atomic_rule_id, weight_override,
                   data_column, data_brkeout_from, data_brkeout_to,
                   data_wt_below, data_wt_between, data_wt_above,
                   data_scoring_mode, data_score_params,
                   nested_composite_code, member_multiplier,
                   category, intent_text, precondition_expr,
                   COALESCE(active, TRUE) AS active,
                   condition_operator,
                   COALESCE(member_role, 'gate') AS member_role,
                   evidence_cutoff
            FROM ref_trig_composite_mapping
            WHERE deprecated_at IS NULL
        """)).mappings().all()
        _composite_extended = True
    except Exception:
        composite_mappings = session.execute(text("""
            SELECT composite_rule_code, atomic_rule_id, weight_override,
                   category, intent_text, precondition_expr
            FROM ref_trig_composite_mapping
            WHERE deprecated_at IS NULL
        """)).mappings().all()
        _composite_extended = False

    # Index composite rules by code with typed members
    composite_index: dict = {}
    for m in composite_mappings:
        code = m["composite_rule_code"]
        if code not in composite_index:
            composite_index[code] = {
                "precondition": m.get("precondition_expr"),
                "active":       bool(m.get("active", True)),
                # composite-level watch evidence cutoff (NULL = watch never blocks).
                # Stored on every member row; take the first non-NULL we see.
                "watch_cutoff": None,
                "members": []
            }
        # evidence_cutoff is composite-level metadata duplicated on member rows
        if composite_index[code]["watch_cutoff"] is None and m.get("evidence_cutoff") is not None:
            composite_index[code]["watch_cutoff"] = m.get("evidence_cutoff")
        role = m.get("member_role") or "gate"
        kind = m.get("member_kind") or "atomic"
        if kind == "atomic":
            composite_index[code]["members"].append({
                "kind":               "atomic",
                "role":               role,
                "atom_id":            m["atomic_rule_id"],
                "threshold":          m.get("data_brkeout_from"),
                "condition_operator": m.get("condition_operator"),
                "override":           m.get("weight_override"),
            })
        elif kind == "data":
            composite_index[code]["members"].append({
                "kind": "data",
                "role":         role,
                "column":      m.get("data_column"),
                "brkeout_from": m.get("data_brkeout_from"),
                "brkeout_to":   m.get("data_brkeout_to"),
                "wt_below":     m.get("data_wt_below"),
                "wt_between":   m.get("data_wt_between"),
                "wt_above":     m.get("data_wt_above"),
                "scoring_mode": m.get("data_scoring_mode") or "jump",
                "score_params": m.get("data_score_params"),
                "override":     m.get("weight_override"),
            })
        elif kind == "composite":
            composite_index[code]["members"].append({
                "kind":     "composite",
                "role":     role,
                "child":    m.get("nested_composite_code"),
                "override": m.get("weight_override"),
            })

    # Topologically order composites so nested children are scored before parents.
    # Cycles are detected and broken: any composite caught in a cycle is logged
    # and gets a single-pass evaluation with child_scores defaulting to 0.
    def _topo_order(comp_idx: dict) -> list:
        deps = {code: {m["child"] for m in info["members"]
                       if m["kind"] == "composite" and m["child"] in comp_idx}
                for code, info in comp_idx.items()}
        order = []
        visited = set()
        in_progress = set()
        def visit(code):
            if code in visited: return
            if code in in_progress:
                log.warning("composite cycle detected at %r — breaking", code)
                return
            in_progress.add(code)
            for d in deps.get(code, ()):
                visit(d)
            in_progress.discard(code)
            visited.add(code)
            order.append(code)
        for code in sorted(comp_idx.keys()):
            visit(code)
        return order
    composite_eval_order = _topo_order(composite_index)

    # Fetch all active rule groups for evaluation
    rule_groups = session.execute(text("""
        SELECT rule_group_code, action_label, priority
        FROM ref_trig_rule_group
        WHERE deprecated_at IS NULL
    """)).mappings().all()

    # Pre-fetch group definitions + members ONCE for the in-memory walker.
    # Without this, the per-symbol loop below would call eval_rule_group()
    # (which does 2 DB round-trips per group) for every (symbol, group)
    # pair — 1000 symbols × 10 groups = 20 000 round-trips. The walker
    # below uses these pre-loaded structures and never touches the DB.
    group_defs: dict = {}
    if rule_groups:
        codes = [g["rule_group_code"] for g in rule_groups]
        for gr in session.execute(text("""
            SELECT rule_group_code, group_type, action_label, priority
            FROM ref_trig_rule_group
            WHERE rule_group_code = ANY(:codes) AND deprecated_at IS NULL
        """), {"codes": codes}).mappings().all():
            group_defs[gr["rule_group_code"]] = {
                "action_label": gr["action_label"],
                "priority":     gr["priority"],
                "members":      [],   # filled below
            }
        for m in session.execute(text("""
            SELECT rule_group_code, member_code, member_type, logic_operator, sequence
            FROM ref_trig_group_member
            WHERE rule_group_code = ANY(:codes)
            ORDER BY rule_group_code, sequence
        """), {"codes": codes}).mappings().all():
            if m["rule_group_code"] in group_defs:
                group_defs[m["rule_group_code"]]["members"].append({
                    "member_code":    m["member_code"],
                    "member_type":    m["member_type"],
                    "logic_operator": m["logic_operator"] or "AND",
                })

    def _eval_group_inline(code: str, composite_results: dict,
                           visited: set) -> tuple[bool, str | None, int | None]:
        """In-memory recursive group evaluation. Composite members look up
        composite_results; nested-group members recurse on group_defs.
        Cycles default the offending node to False.
        """
        if code in visited:
            log.warning("rule-group cycle at %r — defaulting to False", code)
            return False, None, None
        g = group_defs.get(code)
        if not g or not g["members"]:
            return False, None, None
        visited = visited | {code}
        ops, vals = [], []
        for m in g["members"]:
            if m["member_type"] == "composite":
                v = bool(composite_results.get(m["member_code"]))
            else:  # nested group
                v, _, _ = _eval_group_inline(m["member_code"], composite_results, visited)
            ops.append(m["logic_operator"])
            vals.append(v)
            # Short-circuit on AND chain
            if m["logic_operator"] == "AND" and not v:
                return False, None, None
        triggered = any(vals) if "OR" in ops else all(vals)
        if triggered:
            return True, g["action_label"], g["priority"]
        return False, None, None

    # B1 fix (2026-05-10): resolve atomic rule columns via ref_ma_columns registry
    # so the rules engine reads from drv_cat_atomic_input where available.
    atomic_col_map = _resolve_atomic_input_column(session)
    ma_rows = _fetch_eval_rows(session, as_of_date, atomic_col_map)

    out = []
    for r in ma_rows:
        co, cl = _composite_outlook(
            r["rr_brr"], r["call_outlook"], r["etf_outlook"],
            r["ii_outlook"], r["sss_signal_sign"]
        )

        # Evaluate all atomic rules and track which triggered
        triggered_atomics = []
        atomic_scores = {}

        for rule in atomic_rules:
            src = atomic_col_map.get(rule["atomic_rule_id"])
            value = _read_atomic_value(r, src) if src else None
            # drv_cat_atomic_input stores pre-evaluated weights (trig_ifs already
            # called eval_atomic_rule during derive_cat_atomic_input). All active
            # atomic rules now source from there — pass through directly.
            try:
                weight = float(value) if value is not None else 0.0
            except (TypeError, ValueError):
                weight = 0.0
            atomic_scores[rule["atomic_rule_id"]] = weight

            if weight != 0:
                # Preserve original value type. TEXT-direction columns ('+', '-',
                # 'BULLISH') used to crash on float(); store as-is. Numeric values
                # cast for consistent JSON downstream.
                try:
                    val_out = float(value) if value is not None else None
                except (TypeError, ValueError):
                    val_out = str(value)
                triggered_atomics.append({
                    "rule_id": rule["atomic_rule_id"],
                    "weight":  float(weight),
                    "value":   val_out,
                    "applied": value is not None,   # distinguishes "no data" from "zero"
                })

        # Evaluate all composite rules and track which triggered.
        # Three member kinds (post db/baseline.sql):
        #   atomic    — read pre-scored atomic_scores[atom_id]
        #   data      — inline scoring against any drv_cat / drv_ma column
        #   composite — pull score from already-evaluated composite_scores[child]
        # Composites are walked in topological order so children are scored
        # before their parents.
        triggered_composites = []
        composite_results = {}
        composite_scores = {}     # code -> numeric score (for nested lookups)

        for code in composite_eval_order:
            comp_info = composite_index[code]
            # Skip inactive composites
            if not comp_info.get("active", True):
                composite_results[code] = False
                composite_scores[code] = 0.0
                continue
            # Precondition gate
            if comp_info["precondition"]:
                if not _eval_precondition(comp_info["precondition"], dict(r)):
                    composite_results[code] = False
                    composite_scores[code] = None   # NULL — distinguishable from 0
                    continue

            score = 0.0
            n_member_hit = 0   # member-level hit count (any non-zero contribution)
            # Gate / WATCH partition (2026-06-03). Gates are mandatory (strict
            # AND); watch members are corroborating evidence that contribute to
            # score but do not by themselves block the fire.
            n_gate = 0
            n_gate_hit = 0
            n_watch = 0
            n_watch_hit = 0
            watch_score = 0.0
            for member in comp_info["members"]:
                kind = member["kind"]
                role = member.get("role", "gate")
                w = 0.0
                if kind == "atomic":
                    atom_id   = member["atom_id"]
                    threshold = member.get("threshold")   # condition threshold
                    ovr       = member.get("override")    # assigned weight
                    # Read the pre-computed value from drv_cat_atomic_input
                    val = atomic_scores.get(atom_id, 0.0)
                    if threshold is None:
                        # No threshold set — any non-zero value meets condition
                        condition_met = (val != 0)
                    else:
                        thr = float(threshold)
                        # Explicit operator stored on member takes priority;
                        # fall back to rule-code-derived operator
                        op = member.get("condition_operator") or _composite_operator(code, thr)
                        condition_met = (
                            val >= thr if op == '>='
                            else val <= thr if op == '<='
                            else val >  thr if op == '>'
                            else val <  thr if op == '<'
                            else val == thr   # '='
                        )
                    w = float(ovr) if (condition_met and ovr is not None) else (val if condition_met else 0.0)
                elif kind == "data":
                    # Inline rule against the row.  data_column may be
                    # 'drv_cat_atomic_input.col', 'drv_ma.col', or bare 'col'.
                    col = member.get("column") or ""
                    tbl_part, _, col_part = col.partition(".") if "." in col else ("", "", col)
                    src = (tbl_part or "drv_cat_atomic_input", col_part or col)
                    value = _read_atomic_value(r, src)
                    inline_rule = {
                        "brkeout_from":  member.get("brkeout_from"),
                        "brkeout_to":    member.get("brkeout_to"),
                        "wt_below":      member.get("wt_below"),
                        "wt_between":    member.get("wt_between"),
                        "wt_above":      member.get("wt_above"),
                        "scoring_mode":  member.get("scoring_mode") or "jump",
                        "score_params":  member.get("score_params"),
                    }
                    w = eval_atomic_rule(value, inline_rule)
                    ovr = member.get("override")
                    if ovr is not None and w != 0:
                        w = float(ovr)
                elif kind == "composite":
                    child = member.get("child")
                    child_score = composite_scores.get(child)
                    if child_score is None:
                        # Child either doesn't exist, was skipped by its own
                        # precondition, or hasn't been evaluated (cycle).  Skip.
                        w = 0.0
                    else:
                        mult = member.get("override")
                        w = float(mult) * child_score if mult is not None else child_score
                hit = (w != 0)
                if hit:
                    n_member_hit += 1
                if role == "watch":
                    n_watch += 1
                    if hit:
                        n_watch_hit += 1
                        watch_score += w
                else:
                    n_gate += 1
                    if hit:
                        n_gate_hit += 1
                score += w

            # Firing rule (gate / WATCH):
            #   - ALL gates must hit (strict AND; legacy behavior when every
            #     member is a gate, which is the default).
            #   - Watch evidence must clear evidence_cutoff. NULL cutoff = watch
            #     never blocks (purely informational).
            #   - A composite with NO gates falls back to strict all-members-hit
            #     unless an explicit cutoff is set, so pure-watch composites can
            #     never fire on every symbol.
            n_total_members = len(comp_info["members"])
            cutoff = comp_info.get("watch_cutoff")
            gates_pass = (n_gate_hit == n_gate)   # vacuously True when n_gate == 0
            if n_gate == 0:
                watch_ok = (watch_score >= float(cutoff)) if cutoff is not None \
                    else (n_watch_hit == n_watch)
            else:
                watch_ok = (cutoff is None) or (watch_score >= float(cutoff))
            fired = n_total_members > 0 and gates_pass and watch_ok
            composite_results[code] = fired
            composite_scores[code] = float(score)
            if fired:
                triggered_composites.append({
                    "rule_id":      code,
                    "score":        float(score),
                    "n_member_hit": n_member_hit,
                })

        # Evaluate all rule groups and track which triggered. Uses the
        # in-memory walker built above — no DB round-trips inside this loop.
        triggered_groups = []
        for group in rule_groups:
            code = group["rule_group_code"]
            triggered, action, priority = _eval_group_inline(
                code, composite_results, set()
            )
            if triggered:
                triggered_groups.append({
                    "rule_group_code": code,
                    "action": action,
                    "priority": priority,
                })

        out.append({
            "as_of_date": as_of_date,
            "tos_symbol": r["tos_symbol"],
            "description": r["description"],
            "sector": r["sector"],
            "asset_class": r["asset_class"],
            "last_price": r["last_price"],
            "a_trend_value": r["a_trend_value"],
            "a_trade_value": r["a_trade_value"],
            "pct_brr": r["pct_brr"],
            "rr_outlook": r["rr_outlook"],
            "rr_brr": r["rr_brr"],
            "call_outlook": r["call_outlook"],
            "call_modifier": r["call_modifier"],
            "etf_outlook": r["etf_outlook"],
            "ii_outlook": r["ii_outlook"],
            "sss_signal_sign": r["sss_signal_sign"],
            "iv_percentile": r["iv_percentile"],
            "rsi": r["rsi"],
            "earnings_days": r["earnings_days"],
            "market_cap_str": r["market_cap_str"],
            "composite_outlook": co,
            "composite_label": cl,
            "triggered_atomic_ids": triggered_atomics,
            "triggered_composite_ids": triggered_composites,
            "triggered_group_ids": triggered_groups,
            "source_run_id": run_id,
        })
    return replace_for_date(session, "drv_stks", "as_of_date", as_of_date, out)


derive_stks = _wrap("drv_stks", _derive_stks_impl)


def _derive_cs_realized_gain_impl(session: Session, as_of_date: date, run_id: int) -> int:
    """
    For sales on as_of_date, compute realized gain using prior-day avg cost from hist_cs.
    Realized gain = proceeds - (qty sold * avg_cost_per_share_from_prior_day)
    """
    session.execute(text("DELETE FROM drv_cs_realized_gain WHERE as_of_date = :d"), {"d": as_of_date})

    # Find prior snapshot date (most recent hist_cs date strictly before as_of_date)
    prior = session.execute(text("""
        SELECT MAX(snapshot_date) FROM hist_cs WHERE snapshot_date < :d
    """), {"d": as_of_date}).scalar()

    if prior is None:
        return 0

    # Get all sells on as_of_date with their prior-day cost basis
    rows = session.execute(text("""
        SELECT t.account, t.symbol, t.tos_symbol, t.quantity, t.amount,
               c.cost_basis, c.qty AS held_qty
        FROM hist_cst t
        LEFT JOIN hist_cs c
               ON c.account = t.account
              AND c.tos_symbol = t.tos_symbol
              AND c.snapshot_date = :prior
        WHERE t.trade_date = :d
          AND LOWER(t.action) = 'sell'
          AND t.symbol <> ''
    """), {"d": as_of_date, "prior": prior}).fetchall()

    records = []
    for account, symbol, tos_symbol, qty, amount, cost_basis, held_qty in rows:
        if qty and cost_basis and held_qty and float(held_qty) != 0:
            avg_cost = float(cost_basis) / float(held_qty)
            proceeds = float(amount) if amount else 0.0
            realized = proceeds - (float(qty) * avg_cost)
        else:
            avg_cost = None
            proceeds = float(amount) if amount else 0.0
            realized = None  # can't compute without cost basis

        records.append({
            "as_of_date":         as_of_date,
            "account":            account,
            "tos_symbol":         tos_symbol,
            "realized_gain":      realized,
            "shares_sold":        float(qty) if qty else None,
            "avg_cost_per_share": avg_cost,
            "proceeds":           proceeds,
        })

    if records:
        session.execute(
            text("""
                INSERT INTO drv_cs_realized_gain
                    (as_of_date, account, tos_symbol, realized_gain, shares_sold, avg_cost_per_share, proceeds)
                VALUES (:as_of_date, :account, :tos_symbol, :realized_gain, :shares_sold, :avg_cost_per_share, :proceeds)
                ON CONFLICT (as_of_date, account, tos_symbol) DO UPDATE SET
                    realized_gain      = EXCLUDED.realized_gain,
                    shares_sold        = EXCLUDED.shares_sold,
                    avg_cost_per_share = EXCLUDED.avg_cost_per_share,
                    proceeds           = EXCLUDED.proceeds,
                    computed_at        = now()
            """),
            records,
        )
    session.commit()
    return len(records)


derive_cs_realized_gain = _wrap("drv_cs_realized_gain", _derive_cs_realized_gain_impl)


def _derive_dash_summary_impl(session: Session, as_of_date: date, run_id: int) -> int:
    row = session.execute(text("""
        SELECT
            COUNT(*) AS total_symbols,
            SUM(CASE WHEN UPPER(rr_outlook) LIKE 'BULL%' THEN 1 ELSE 0 END) AS n_bullish,
            SUM(CASE WHEN UPPER(rr_outlook) LIKE 'BEAR%' THEN 1 ELSE 0 END) AS n_bearish,
            SUM(CASE WHEN COALESCE(UPPER(rr_outlook),'') NOT LIKE 'BULL%'
                      AND COALESCE(UPPER(rr_outlook),'') NOT LIKE 'BEAR%' THEN 1 ELSE 0 END) AS n_neutral,
            AVG(rr_brr) AS avg_brr,
            SUM(CASE WHEN pct_brr BETWEEN 0 AND 100 THEN 1 ELSE 0 END) AS n_in_zone,
            SUM(CASE WHEN pct_brr IS NOT NULL AND (pct_brr<0 OR pct_brr>100) THEN 1 ELSE 0 END) AS n_out,
            SUM(CASE WHEN last_price > a_trend_value THEN 1 ELSE 0 END) AS n_above,
            SUM(CASE WHEN last_price < a_trade_value THEN 1 ELSE 0 END) AS n_below
        FROM drv_ma WHERE as_of_date = :d
    """), {"d": as_of_date}).mappings().first()

    nx_econ = session.execute(text("""
        SELECT indicator, indicator_date FROM ref_econ_indicator
        WHERE indicator_date >= :d ORDER BY indicator_date ASC LIMIT 1
    """), {"d": as_of_date}).mappings().first()

    nx_hol = session.execute(text("""
        SELECT description, holiday_date FROM ref_holiday
        WHERE holiday_date >= :d ORDER BY holiday_date ASC LIMIT 1
    """), {"d": as_of_date}).mappings().first()

    rec = {
        "as_of_date": as_of_date,
        "total_symbols": (row or {}).get("total_symbols") or 0,
        "n_bullish": (row or {}).get("n_bullish") or 0,
        "n_bearish": (row or {}).get("n_bearish") or 0,
        "n_neutral": (row or {}).get("n_neutral") or 0,
        "avg_brr": (row or {}).get("avg_brr"),
        "n_in_zone": (row or {}).get("n_in_zone") or 0,
        "n_out_of_zone": (row or {}).get("n_out") or 0,
        "n_above_trend": (row or {}).get("n_above") or 0,
        "n_below_trend": (row or {}).get("n_below") or 0,
        "next_econ_event": nx_econ["indicator"] if nx_econ else None,
        "next_econ_event_dt": nx_econ["indicator_date"] if nx_econ else None,
        "next_holiday": nx_hol["description"] if nx_hol else None,
        "next_holiday_dt": nx_hol["holiday_date"] if nx_hol else None,
        "source_run_id": run_id,
    }
    return replace_for_date(session, "drv_dash_summary", "as_of_date", as_of_date, [rec])


derive_dash_summary = _wrap("drv_dash_summary", _derive_dash_summary_impl)


# =============================================================================
# Helpers - outlook -> weight, weight -> buysell action
# These read from ref_param + ref_param_lookup (loaded from Parm tab).
# =============================================================================

def _load_outlook_weights(session: Session) -> dict[str, float]:
    """Returns {OUTLOOK_TEXT_UPPER: weight} from ref_param sheet='outlook'."""
    rows = session.execute(text("""
        SELECT param_name, value FROM ref_param WHERE sheet = 'outlook'
    """)).fetchall()
    out: dict[str, float] = {}
    for name, val in rows:
        try:
            out[name.upper()] = float(val) if val is not None else 0.0
        except (TypeError, ValueError):
            continue
    # Sensible fallbacks if the Parm tab hasn't been loaded yet
    out.setdefault("BULLISH", 3.0)
    out.setdefault("BEARISH", -3.0)
    out.setdefault("NEUTRAL", 0.0)
    return out


def _load_buysell_lookup(session: Session) -> dict[float, tuple[str, float]]:
    """
    Returns {weight_value: (action_code, action_weight)}.
    From ref_param_lookup table_name='buysell':
      code=AM (e.g. 'BS','SA'), action=AN (e.g. 'BuySome','SellAll'), extra1=AO weight.
    Indexed by AO (the 'weight' bucket key like -10..+10).
    """
    rows = session.execute(text("""
        SELECT code, action, extra1, seq FROM ref_param_lookup
        WHERE table_name = 'buysell'
    """)).fetchall()
    out: dict[float, tuple[str, float]] = {}
    for code, action, weight_str, seq in rows:
        try:
            wt = float(weight_str) if weight_str is not None else 0.0
            out[wt] = (action or code, wt)
        except (TypeError, ValueError):
            continue
    return out


def _outlook_to_weight(outlook: Optional[str], modifier: Optional[str],
                       wt_map: dict[str, float]) -> Optional[float]:
    if not outlook:
        return None
    base = wt_map.get(str(outlook).upper())
    if base is None:
        return 0.0
    # Modifier adjustments would go here if we had the rule (e.g. Bench halves)
    if modifier and "bench" in str(modifier).lower():
        return base / 3.0
    return base


def _weight_to_buysell(weight: Optional[float],
                       lookup: dict[float, tuple[str, float]]) -> tuple[Optional[str], Optional[float]]:
    if weight is None:
        return None, None
    # Find the buysell entry whose weight matches (or nearest match)
    if not lookup:
        return None, None
    if weight in lookup:
        return lookup[weight]
    # Nearest match by absolute weight, same sign; prefer values closer to 0 on tie
    same_sign = [w for w in lookup if (w >= 0) == (weight >= 0)]
    if not same_sign:
        return None, None
    nearest = min(same_sign, key=lambda w: (abs(w - weight), abs(w)))
    return lookup[nearest]


def _get_continuation_action(entry_wt: Optional[float],
                             lookup: dict[float, tuple[str, float]]) -> tuple[Optional[str], Optional[float]]:
    """Derive continuation action from entry weight: reduce by 2 (towards 0) to get less aggressive action."""
    if entry_wt is None:
        return None, None
    # Continuation weight is 2 steps less aggressive (closer to 0)
    if entry_wt > 0:
        cont_wt = max(0, entry_wt - 2)
    elif entry_wt < 0:
        cont_wt = min(0, entry_wt + 2)
    else:
        cont_wt = 0
    return _weight_to_buysell(cont_wt, lookup)


# =============================================================================
# call / etf / II / ssH per-row derivations
# =============================================================================

# _derive_call_impl + derive_call ARCHIVED 2026-05-12 — archived 2026-05-12 (see _trash_2026-05-12/etl/_archived/)

# Signal Strength derivations: ARCHIVED — archived 2026-05-12 (see _trash_2026-05-12/etl/_archived/)

# =============================================================================
# Missing symbols
# =============================================================================

def _derive_missing_symbols_impl(session: Session, as_of_date: date, run_id: int) -> int:
    rows = session.execute(text("""
        WITH ma AS (SELECT tos_symbol FROM drv_ma WHERE as_of_date = :d),
        seen AS (
            SELECT tos_symbol, 'tl'   AS src FROM hist_tl   WHERE snapshot_date = :d
            UNION SELECT tos_symbol, 'rr'   FROM hist_rr   WHERE snapshot_date = :d
            UNION SELECT tos_symbol, 'call' FROM hist_call WHERE snapshot_date = :d
            UNION SELECT tos_symbol, 'etf'  FROM hist_etf  WHERE snapshot_date = :d
            UNION SELECT tos_symbol, 'ii'   FROM hist_ii   WHERE snapshot_date = :d
            UNION SELECT tos_symbol, 'sss'  FROM hist_sss  WHERE snapshot_date = :d
            UNION SELECT tos_symbol, 'y'    FROM hist_y    WHERE snapshot_date = :d
        )
        SELECT s.tos_symbol AS symbol, string_agg(DISTINCT s.src, ',' ORDER BY s.src) AS found_in
        FROM seen s
        WHERE NOT EXISTS (SELECT 1 FROM ma WHERE ma.tos_symbol = s.tos_symbol)
        GROUP BY s.tos_symbol
    """), {"d": as_of_date}).mappings().all()
    out = [{
        "as_of_date":    as_of_date,
        "tos_symbol":    r["symbol"],
        "found_in":      r["found_in"],
        "source_run_id": run_id,
    } for r in rows]
    return replace_for_date(session, "drv_missing_symbols", "as_of_date", as_of_date, out)


derive_missing_symbols = _wrap("drv_missing_symbols", _derive_missing_symbols_impl)


# =============================================================================
# Trig - per-stock per-composite-rule scoring
# =============================================================================

_MA_COL_MAP = {
    # MACD family — shadowed by ref_ma_columns for active rules; kept for legacy dryruns
    "MACDH Direction":        "a_macdh_d_brr",
    "MACD Direction":         "a_macd_brr",
    "MACD Rule":              "a_macd_brr",
    "MACDH Rule":             "a_macdh_d_brr",
    "MACDH Days":             "a_macdh_d_brr",
    "MACDH Days2":            "a_macdh_d_brr",
    "MACD_BRR Puts":          "a_macd_brr",
    "MACDH_BRR Puts":         "a_macdh_d_brr",
    # BB family — active rules resolved via ref_ma_columns; kept for legacy
    "BB Direction":           "a_bb_streak",
    "BBThresh CO Days":       "a_bb_streak",
    "BBStreak Rule":          "a_bb_streak",
    "BBStreak Rule2":         "a_bb_streak",
    "BBStreak Days Rule":     "a_bb_streak",
    "BBStreak Days Rule2":    "a_bb_streak",
    "BBHighDays":             "a_bb_streak",
    "BBLowDays":              "a_bb_streak",
    "BBHighLow Days Rule":    "a_bb_streak",
    "BBHighLow_SD Rule":      "a_bb_streak",
    "Trade Cross Over":       "pct_brr",
    "RSI":                    "rsi",
    "Overbought":             "rsi",
    "IV":                     "imp_volatility",
    "IVAbsolute":             "imp_volatility",
    "TrendValue":             "a_trend_value",
    "TradeValue":             "a_trade_value",
    "Trend-Rule":             "a_trend_value",
    "Trade-Rule":             "a_trade_value",
    "Trade Trend SD Rule":    "a_trend_value",
    "BB Top":                 "a_bb_top",
    "BB Bottom":              "a_bb_bottom",
    "BRR":                    "rr_brr",
    "Last":                   "last_price",
    "Last Price":             "last_price",
    "Volume":                 "volume",
    "Current Volume Rule":    "vlm_projected",
    "52-Wk High Rule":        "sma_200",
    "52-Wk Low Rule":         "sma_200",
    "200-DMA-Rule":           "sma_200",
    "50-DMA-Rule":            "sma_50",
    "3m-High-Rule":           "sma_200",
    "3m-Low-Rule":            "sma_200",
    "3mn-High-Rule":          "sma_200",
    "3mn-Low-Rule":           "sma_200",
    "3wk Outlook":            "a_macd_brr",
    "3wk Outlook Days":       "a_macd_brr",
    "3m-Low-Days Rule":       "a_bb_streak",
    "3mn Outlook":            "a_macd_brr",
    "3mn Outlook Days":       "a_macd_brr",
    "Perf1D SD Rule":         "last_price",
    "Perf2M SD Rule":         "volume",
    "Perf3D SD Rule":         "range_compression",
    "Perf3mn SD Rule":        "range_compression",
    "LRR_Idx":                "a_trend_value",
    "MRR_Idx":                "a_trade_value",
    "TRR_Idx":                "a_bb_top",
    "Short Term Oulook (If LT Bearish)": "a_macd_brr",
    "Short Term Oulook (If LT Bullish)": "a_macd_brr",
    "VS Days":                "earnings_days",
    "VS LT Outlook Rule":     "a_macd_brr",
}


# Legacy _bucket_weight() removed 2026-05-17. It only handled scoring_mode='jump'
# and was the source of the drv_trig vs. drv_stks discrepancy on linear/sigmoid
# rules. All atomic-rule scoring now flows through eval_atomic_rule() below, so
# every consumer (drv_stks, drv_trig, rule dry-runs) produces identical scores.


def eval_atomic_rule(value, rule):
    """
    Evaluate an atomic rule using the configured scoring_mode.

    Args:
        value: The measured value from drv_ma
        rule: Dict with keys:
          - scoring_mode: 'jump' | 'linear' | 'sigmoid'
          - brkeout_from, brkeout_to: threshold boundaries
          - wt_below, wt_between, wt_above: weight assignments
          - score_params: optional JSONB with {'k': float, 'x0': float} for sigmoid

    Returns:
        float: the computed weight
    """
    if value is None:
        return 0.0

    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.0

    lo_val = rule.get('brkeout_from')
    hi_val = rule.get('brkeout_to')
    wb     = rule.get('wt_below')
    wbt    = rule.get('wt_between')
    wa     = rule.get('wt_above')

    # Pass-through: no thresholds or weights configured — column value IS the score.
    # Applies to direction/flag indicators pre-computed on a -3..3 scale.
    if lo_val is None and hi_val is None and wb is None and wbt is None and wa is None:
        return v

    try:
        lo = float(lo_val) if lo_val is not None else 0.0
    except (TypeError, ValueError):
        lo = 0.0

    try:
        hi = float(hi_val) if hi_val is not None else 100.0
    except (TypeError, ValueError):
        hi = 100.0

    try:
        wt_below = float(wb) if wb is not None else 0.0
    except (TypeError, ValueError):
        wt_below = 0.0

    try:
        wt_between = float(wbt) if wbt is not None else 0.0
    except (TypeError, ValueError):
        wt_between = 0.0

    try:
        wt_above = float(wa) if wa is not None else 0.0
    except (TypeError, ValueError):
        wt_above = 0.0

    mode = rule.get('scoring_mode', 'jump')

    if mode == 'jump':
        if v < lo:
            return wt_below
        elif v > hi:
            return wt_above
        else:
            return wt_between

    elif mode == 'linear':
        # Linear interpolation from wt_below to wt_above across [lo, hi]
        if v <= lo:
            return wt_below
        elif v >= hi:
            return wt_above
        else:
            t = (v - lo) / (hi - lo) if hi != lo else 0.5
            return wt_below + t * (wt_above - wt_below)

    elif mode == 'sigmoid':
        import math
        params = rule.get('score_params') or {}
        k = float(params.get('k', 0.1)) if params else 0.1
        x0 = float(params.get('x0', (lo + hi) / 2)) if params else (lo + hi) / 2
        try:
            s = 1.0 / (1.0 + math.exp(-k * (v - x0)))
            return wt_below + s * (wt_above - wt_below)
        except (OverflowError, ValueError):
            return wt_above if v > x0 else wt_below

    return 0.0


def _derive_trig_impl(session: Session, as_of_date: date, run_id: int) -> int:
    """drv_trig: per (date, symbol, composite_rule_code) score / triggered.
    Reads via _resolve_atomic_input_column so it agrees with _derive_stks_impl.
    Note: drv_trig only carries scores from atomic-kind members today (no nested
    composite or data inline scoring is recorded here per row — see drv_stks
    triggered_composite_ids for the authoritative composite scores).
    """
    rules = session.execute(text("""
        SELECT atomic_rule_id, rule_name, brkeout_from, brkeout_to,
               wt_below, wt_between, wt_above, ma_column_name,
               scoring_mode, score_params
        FROM ref_trig_atomic_rule
        WHERE deprecated_at IS NULL
    """)).mappings().all()
    if not rules:
        log.warning("drv_trig: no atomic rules; skipping")
        return 0
    mappings = session.execute(text("""
        SELECT composite_rule_code, atomic_rule_id, weight_override
        FROM ref_trig_composite_mapping
        WHERE deprecated_at IS NULL AND atomic_rule_id IS NOT NULL
    """)).mappings().all()
    if not mappings:
        log.warning("drv_trig: no composite mappings; skipping")
        return 0
    composite_index: dict = {}
    for m in mappings:
        composite_index.setdefault(m["composite_rule_code"], []).append(
            (m["atomic_rule_id"], m["weight_override"]))

    atomic_col_map = _resolve_atomic_input_column(session)
    ma_rows = _fetch_eval_rows(session, as_of_date, atomic_col_map)
    if not ma_rows:
        log.warning("drv_trig: no rows for %s; skipping", as_of_date)
        return 0

    out_rows = []
    for ma in ma_rows:
        atomic_weights = {}
        for r in rules:
            src = atomic_col_map.get(r["atomic_rule_id"])
            v = _read_atomic_value(ma, src) if src else None
            atomic_weights[r["atomic_rule_id"]] = eval_atomic_rule(v, r)

        for code, parts in composite_index.items():
            score = 0.0
            n_hit = 0
            for (atom_id, override) in parts:
                w = atomic_weights.get(atom_id, 0)
                if override is not None and w != 0:
                    w = float(override)
                if w != 0:
                    n_hit += 1
                score += w
            out_rows.append({
                "as_of_date":          as_of_date,
                "tos_symbol":          ma["tos_symbol"],
                "composite_rule_code": code,
                "score":               float(score),
                # triggered = any member contributed, not "net score non-zero".
                # Matches drv_stks semantics post 2026-05-17 fix.
                "triggered":           n_hit > 0,
                "n_atomic_hit":        n_hit,
                "source_run_id":       run_id,
            })
    return replace_for_date(session, "drv_trig", "as_of_date", as_of_date, out_rows)


derive_trig = _wrap("drv_trig", _derive_trig_impl)


def _derive_cat_table_impl(session: Session, as_of_date: date, run_id: int, cat_table: str) -> int:
    """Generic per-category table deriver (registry-driven).

    Each drv_cat_* table follows the same pattern:
      1. DELETE rows for this as_of_date
      2. Generate INSERT...SELECT from ref_ma_columns via ma_codegen.build_dml
      3. Execute and return row count
    """
    from etl import ma_codegen
    session.execute(
        text(f"DELETE FROM {cat_table} WHERE as_of_date = :d"),
        {"d": as_of_date},
    )
    dml = ma_codegen.build_dml(session, cat_table)
    if not dml:
        return 0
    result = session.execute(text(dml), {"d": as_of_date, "run_id": run_id})
    return result.rowcount or 0


def _populate_y_tos_symbol(session: Session, as_of_date: date) -> int:
    """Populate tos_symbol in hist_y by mapping y_ticker via RRT (all dates)."""
    rows = session.execute(text("""
        SELECT DISTINCT symbol FROM hist_y WHERE tos_symbol IS NULL
    """)).fetchall()

    updated = 0
    for (symbol,) in rows:
        tos_sym = _get_tos_symbol(session, symbol, "y_ticker")
        session.execute(text("""
            UPDATE hist_y SET tos_symbol = :tos WHERE symbol = :sym AND tos_symbol IS NULL
        """), {"tos": tos_sym, "sym": symbol})
        updated += 1

    return updated


def _populate_rr_tos_symbol(session: Session, as_of_date: date) -> int:
    """Populate tos_symbol in hist_rr by mapping rr_name via RRT.

    Unlike other tables, RR does NOT fallback to original symbol if not found.
    Instead, keeps tos_symbol NULL and creates a warning for manual intervention.
    """
    # Clear previous warnings for this date
    clear_screen_warnings(session, "data-quality", as_of_date)

    # Find all distinct RR symbols with NULL tos_symbol (across all dates)
    rows = session.execute(text("""
        SELECT DISTINCT symbol FROM hist_rr WHERE tos_symbol IS NULL
    """)).fetchall()

    unmapped_count = 0
    for (symbol,) in rows:
        # Try to find the RR name in ref_rrt
        row = session.execute(text("""
            SELECT tos_ticker FROM ref_rrt WHERE rr_name = :sym LIMIT 1
        """), {"sym": symbol}).first()

        if row and row[0]:
            # Found in ref_rrt - update all rows for this symbol
            tos_sym = row[0]
            session.execute(text("""
                UPDATE hist_rr SET tos_symbol = :tos WHERE symbol = :sym
            """), {"tos": tos_sym, "sym": symbol})
        else:
            # NOT found in ref_rrt - keep tos_symbol NULL and create warning
            unmapped_count += 1
            add_warning(
                session,
                screen="data-quality",
                message=f"RR symbol '{symbol}' not found in ref_rrt - tos_symbol is NULL",
                as_of_date=as_of_date,
                symbol=symbol,
                severity="error",
                code="rr_symbol_unmapped"
            )

    if unmapped_count > 0:
        # Summary warning
        add_warning(
            session,
            screen="data-quality",
            message=f"RR: {unmapped_count} symbol(s) not found in ref_rrt mapping",
            as_of_date=as_of_date,
            severity="error",
            code="rr_unmapped_count"
        )
        log.warning(f"hist_rr: {unmapped_count} symbols not mapped to tos_symbol")

    return unmapped_count


def _populate_ps_tos_symbol(session: Session, as_of_date: date) -> int:
    """Populate tos_symbol in hist_ps by matching ticker against ref_rrt.

    hist_ps uses 'ticker' instead of 'symbol'. Try to match ticker against
    tos_ticker, y_ticker, rr_name in that order.
    """
    rows = session.execute(text("""
        SELECT DISTINCT ticker FROM hist_ps WHERE tos_symbol IS NULL
    """)).fetchall()

    updated = 0
    for (ticker,) in rows:
        tos_sym = None

        # Try tos_ticker
        row = session.execute(text("""
            SELECT tos_ticker FROM ref_rrt WHERE tos_ticker = :sym LIMIT 1
        """), {"sym": ticker}).first()
        if row and row[0]:
            tos_sym = row[0]

        # Try y_ticker
        if not tos_sym:
            row = session.execute(text("""
                SELECT tos_ticker FROM ref_rrt WHERE y_ticker = :sym LIMIT 1
            """), {"sym": ticker}).first()
            if row and row[0]:
                tos_sym = row[0]

        # Try rr_name
        if not tos_sym:
            row = session.execute(text("""
                SELECT tos_ticker FROM ref_rrt WHERE rr_name = :sym LIMIT 1
            """), {"sym": ticker}).first()
            if row and row[0]:
                tos_sym = row[0]

        # Fallback to ticker itself
        if not tos_sym:
            tos_sym = ticker

        session.execute(text("""
            UPDATE hist_ps SET tos_symbol = :tos WHERE ticker = :sym AND tos_symbol IS NULL
        """), {"tos": tos_sym, "sym": ticker})
        updated += 1

    return updated


def _populate_tos_table_tos_symbol(session: Session, table: str, as_of_date: date) -> int:
    """Populate tos_symbol for TOS tables (hist_tl, hist_td, hist_to, hist_tw).

    For TOS workbook sources, symbol IS already the tos_symbol.
    Just copy symbol → tos_symbol directly (all dates).
    """
    updated = session.execute(text(f"""
        UPDATE {table} SET tos_symbol = symbol WHERE tos_symbol IS NULL
    """)).rowcount
    return updated


def _populate_generic_tos_symbol(session: Session, table: str, as_of_date: date) -> int:
    """Populate tos_symbol for other hist_* tables by matching against ref_rrt (all dates).

    Try to match symbol against tos_ticker, y_ticker, rr_name in that order.
    Return tos_ticker if matched, otherwise use original symbol.
    """
    rows = session.execute(text(f"""
        SELECT DISTINCT symbol FROM {table} WHERE tos_symbol IS NULL
    """)).fetchall()

    updated = 0
    for (symbol,) in rows:
        # Try matching in order: tos_ticker, y_ticker, rr_name
        tos_sym = None

        # Try tos_ticker
        row = session.execute(text("""
            SELECT tos_ticker FROM ref_rrt WHERE tos_ticker = :sym LIMIT 1
        """), {"sym": symbol}).first()
        if row and row[0]:
            tos_sym = row[0]

        # Try y_ticker
        if not tos_sym:
            row = session.execute(text("""
                SELECT tos_ticker FROM ref_rrt WHERE y_ticker = :sym LIMIT 1
            """), {"sym": symbol}).first()
            if row and row[0]:
                tos_sym = row[0]

        # Try rr_name
        if not tos_sym:
            row = session.execute(text("""
                SELECT tos_ticker FROM ref_rrt WHERE rr_name = :sym LIMIT 1
            """), {"sym": symbol}).first()
            if row and row[0]:
                tos_sym = row[0]

        # Fallback to original symbol if no match
        if not tos_sym:
            tos_sym = symbol

        session.execute(text(f"""
            UPDATE {table} SET tos_symbol = :tos WHERE symbol = :sym AND tos_symbol IS NULL
        """), {"tos": tos_sym, "sym": symbol})
        updated += 1

    return updated


def _derive_trend_trade_rules_impl(session: Session, as_of_date: date, run_id: int) -> int:
    """Populate MA-tab rule columns QE, QJ, QM, QN, QR in drv_cat_atomic_input.

    Two-pass UPDATE (idempotent):
      Pass 1: QE (trade_trend_sd_rule), QJ (bb_rng_strk_rule),
              QM (bull_rr_action), QN (not_bull_rr_action).
              Inputs: drv_quote (Close), hist_td (a_trend_value,
              a_trade_value, a_bb_top/bot_slope), hist_tw (standard_dev
              for AA and as-of-date median AB), and drv_cat_atomic_input
              itself (macdh_direction, trade_rule, trend_rule,
              perf1d_sd_rule, lrr_idx, mrr_idx, trr_idx).
      Pass 2: QR (td_tn_bb_rr_action) joins ref_param_lookup four times
              (tn_td_rule, bb_range, bull_rr_rule, nbull_rr_rule) to
              translate QE/QJ/QM/QN into action sequences, then evaluates
              the QR conditional.

    Requires derive_cat_atomic_input to have run first for the date
    (the inputs in Pass 1 read its columns, and Pass 2 reads QE/QJ/QM/QN
    that Pass 1 just wrote).
    """
    # Idempotent: wipe and rebuild drv_tn_td_bb_rr for this date
    session.execute(text("DELETE FROM drv_tn_td_bb_rr WHERE as_of_date = :d"), {"d": as_of_date})

    # Pass 1: INSERT QE/QH/QI/QJ/QM/QN into drv_tn_td_bb_rr
    result = session.execute(text("""
        WITH inputs AS (
            SELECT
                q.as_of_date,
                q.tos_symbol,
                q.last_price                       AS close,
                td.a_trend_value,
                td.a_trade_value,
                td.a_bb_top_slope,
                td.a_bb_bot_slope,
                tw.standard_dev                    AS sd,
                med.median_sd,
                a.macdh_direction,
                a.trade_rule,
                a.trend_rule,
                a.perf1d_sd_rule,
                a.trr_idx,
                a.mrr_idx,
                a.lrr_idx
            FROM drv_quote q
            LEFT JOIN LATERAL (
                SELECT a_trend_value, a_trade_value, a_bb_top_slope, a_bb_bot_slope
                FROM hist_td
                WHERE tos_symbol = q.tos_symbol AND snapshot_date <= q.as_of_date
                ORDER BY snapshot_date DESC, sequence DESC LIMIT 1
            ) td ON TRUE
            LEFT JOIN LATERAL (
                SELECT standard_dev
                FROM hist_tw
                WHERE tos_symbol = q.tos_symbol AND snapshot_date <= q.as_of_date
                ORDER BY snapshot_date DESC, sequence DESC LIMIT 1
            ) tw ON TRUE
            LEFT JOIN LATERAL (
                SELECT percentile_cont(0.5) WITHIN GROUP (
                    ORDER BY standard_dev
                ) AS median_sd
                FROM hist_tw
                WHERE tos_symbol = q.tos_symbol
                  AND snapshot_date <= q.as_of_date
                  AND standard_dev IS NOT NULL
            ) med ON TRUE
            LEFT JOIN drv_cat_atomic_input a
              ON a.as_of_date = q.as_of_date AND a.tos_symbol = q.tos_symbol
            WHERE q.as_of_date = :d
        ),
        computed AS (
            SELECT
                i.*,
                LEAST(i.sd, i.median_sd) AS sd_or_median,
                CASE WHEN i.close = i.a_trend_value THEN 0.1
                     WHEN LEAST(i.sd, i.median_sd) IS NULL
                          OR LEAST(i.sd, i.median_sd) = 0 THEN NULL
                     ELSE (i.close - i.a_trend_value)
                          / LEAST(i.sd, i.median_sd)
                END AS trend_sd,
                CASE WHEN LEAST(i.sd, i.median_sd) IS NULL
                          OR LEAST(i.sd, i.median_sd) = 0 THEN NULL
                     ELSE (i.close - i.a_trade_value)
                          / LEAST(i.sd, i.median_sd)
                END AS trade_sd,
                CASE WHEN LEAST(i.sd, i.median_sd) IS NULL
                          OR LEAST(i.sd, i.median_sd) = 0 THEN NULL
                     ELSE (i.a_trade_value - i.a_trend_value)
                          / LEAST(i.sd, i.median_sd)
                END AS trade_trend_sd
            FROM inputs i
        )
        INSERT INTO drv_tn_td_bb_rr
            (as_of_date, tos_symbol,
             a_bb_top_slope, a_bb_bot_slope,
             trend_trade_rule, bb_rng_strk_rule,
             bull_rr_action, not_bull_rr_action)
        SELECT
            c.as_of_date, c.tos_symbol,
            c.a_bb_top_slope, c.a_bb_bot_slope,
            CASE
                WHEN c.trend_sd < 0 AND c.trade_sd < 0 THEN -2
                WHEN c.trade_trend_sd < 0 AND c.trade_sd < 1 THEN -1
                WHEN c.trend_sd > 0 AND c.trade_sd > 0
                     AND (c.trade_trend_sd > 2
                          OR GREATEST(c.trend_sd, c.trade_sd) > 4) THEN 4
                WHEN c.trend_sd > 0 AND c.trade_sd > 0 THEN 3
                WHEN c.trend_sd < 0 AND c.trade_sd > 0 THEN 2
                ELSE 1
            END,
            CASE
                WHEN c.a_bb_top_slope >= 3 AND c.a_bb_bot_slope >= 3 THEN 4
                WHEN c.a_bb_top_slope <= -3 AND c.a_bb_bot_slope <= -3 THEN -4
                WHEN c.a_bb_top_slope >= 2 AND c.a_bb_bot_slope >= 2 THEN 3
                WHEN c.a_bb_top_slope <= -2 AND c.a_bb_bot_slope <= -2 THEN -3
                WHEN c.a_bb_bot_slope >= 2 AND c.a_bb_top_slope <  2 THEN 1
                WHEN c.a_bb_top_slope <= -3 AND c.a_bb_bot_slope > -2 THEN -1
                WHEN c.a_bb_top_slope >= 3
                     AND c.a_bb_top_slope > c.a_bb_bot_slope THEN 2
                WHEN c.a_bb_bot_slope <= -2
                     AND c.a_bb_bot_slope < c.a_bb_top_slope THEN -2
                ELSE 0
            END,
            CASE
                WHEN c.perf1d_sd_rule >  0 AND c.lrr_idx = 1
                     AND c.mrr_idx = -1 AND c.macdh_direction > 0 THEN 6
                WHEN c.perf1d_sd_rule = -1 AND c.mrr_idx = 1 THEN 5
                WHEN c.perf1d_sd_rule >  0 AND c.lrr_idx = 0 THEN 4
                WHEN c.perf1d_sd_rule >  0 AND c.lrr_idx = 1
                     AND c.mrr_idx = -1 AND c.macdh_direction < 0 THEN 3
                WHEN c.perf1d_sd_rule <  0 AND c.lrr_idx = 0
                     AND c.trade_rule > 0 THEN 2
                WHEN c.perf1d_sd_rule >= 0 AND c.mrr_idx = 0 THEN 1
                WHEN c.perf1d_sd_rule <= -1 AND c.mrr_idx = -1
                     AND c.lrr_idx = 1 THEN -1
                ELSE NULL
            END,
            CASE
                WHEN c.perf1d_sd_rule >  0 AND c.lrr_idx = 1
                     AND c.mrr_idx <= 0 AND c.macdh_direction > 0 THEN 5
                WHEN c.perf1d_sd_rule >  0 AND c.lrr_idx = 0 THEN 4
                WHEN c.perf1d_sd_rule <  0 AND c.lrr_idx = 0
                     AND c.trade_rule > 0 AND c.trend_rule > 0 THEN 3
                WHEN c.perf1d_sd_rule >  0 AND c.lrr_idx = 1
                     AND c.mrr_idx <= 0 AND c.macdh_direction < 0 THEN 2
                WHEN c.trr_idx >= 0 THEN -1
                ELSE NULL
            END
        FROM computed c
        WHERE c.tos_symbol IS NOT NULL
    """), {"d": as_of_date})

    rows_pass1 = result.rowcount or 0

    # Pass 2: QR = td_tn_bb_rr_action
    # Excel: IFS(QF<0, QF, QF>0, IF(QK<0, QK, QO), TRUE, "")
    #   QF = ref_param_lookup.seq @ ('tn_td_rule',    QE::text)
    #   QK = ref_param_lookup.seq @ ('bb_range',      QJ::text)
    #   QO = if QJ >= 2: ref_param_lookup.seq @ ('bull_rr_rule',  QM::text)
    #        if QJ >= 0: ref_param_lookup.seq @ ('nbull_rr_rule', QN::text)
    #        else: NULL
    # ref_param_lookup.code is TEXT; QE/QJ/QM/QN are NUMERIC integer values,
    # cast via ::INTEGER::TEXT so '4' matches the seed row code '4' (no decimal).
    session.execute(text("""
        WITH base AS (
            -- QE (trade_trend_sd_rule) stays in drv_cat_atomic_input (JV column).
            -- QJ/QM/QN are now in drv_tn_td_bb_rr (inserted in Pass 1 above).
            SELECT
                r.as_of_date,
                r.tos_symbol,
                a.trade_trend_sd_rule AS qe,
                r.bb_rng_strk_rule    AS qj,
                r.bull_rr_action      AS qm_val,
                r.not_bull_rr_action  AS qn_val
            FROM drv_tn_td_bb_rr r
            LEFT JOIN drv_cat_atomic_input a
              ON a.as_of_date = r.as_of_date AND a.tos_symbol = r.tos_symbol
            WHERE r.as_of_date = :d
        ),
        looked_up AS (
            SELECT
                b.as_of_date,
                b.tos_symbol,
                b.qj,
                l_qf.seq AS qf_seq,
                l_qk.seq AS qk_seq,
                CASE
                    WHEN b.qj >= 2 THEN l_qm.seq
                    WHEN b.qj >= 0 THEN l_qn.seq
                    ELSE NULL
                END AS qo_seq
            FROM base b
            LEFT JOIN ref_param_lookup l_qf
              ON l_qf.table_name = 'tn_td_rule'
             AND l_qf.code = (b.qe)::INTEGER::TEXT
            LEFT JOIN ref_param_lookup l_qk
              ON l_qk.table_name = 'bb_range'
             AND l_qk.code = (b.qj)::INTEGER::TEXT
            LEFT JOIN ref_param_lookup l_qm
              ON l_qm.table_name = 'bull_rr_rule'
             AND l_qm.code = (b.qm_val)::INTEGER::TEXT
            LEFT JOIN ref_param_lookup l_qn
              ON l_qn.table_name = 'nbull_rr_rule'
             AND l_qn.code = (b.qn_val)::INTEGER::TEXT
        )
        UPDATE drv_tn_td_bb_rr dst
        SET td_tn_bb_rr_action = CASE
            WHEN l.qf_seq < 0 THEN l.qf_seq
            WHEN l.qf_seq > 0 THEN
                CASE WHEN l.qk_seq < 0 THEN l.qk_seq
                     ELSE l.qo_seq END
            ELSE NULL
        END
        FROM looked_up l
        WHERE dst.as_of_date = l.as_of_date AND dst.tos_symbol = l.tos_symbol
    """), {"d": as_of_date})

    return rows_pass1

def derive_all(session: Session, as_of_date: date,
               parent_run_id: Optional[int] = None) -> dict:
    """Run every derive_* in dependency order. Returns {table: rows_built}."""
    counts: dict = {}

    # Populate tos_symbol in all hist_* tables
    # hist_y, hist_rr: Use RRT mapping
    counts["hist_y_tos_symbol"] = _populate_y_tos_symbol(session, as_of_date)
    counts["hist_rr_tos_symbol"] = _populate_rr_tos_symbol(session, as_of_date)

    # hist_tl, hist_td, hist_to, hist_tw: Symbol IS tos_symbol (TOS workbook)
    counts["hist_tl_tos_symbol"] = _populate_tos_table_tos_symbol(session, "hist_tl", as_of_date)
    counts["hist_td_tos_symbol"] = _populate_tos_table_tos_symbol(session, "hist_td", as_of_date)
    counts["hist_to_tos_symbol"] = _populate_tos_table_tos_symbol(session, "hist_to", as_of_date)
    counts["hist_tw_tos_symbol"] = _populate_tos_table_tos_symbol(session, "hist_tw", as_of_date)

    # Others: Match against ref_rrt (tos_ticker, y_ticker, rr_name in order)
    counts["hist_call_tos_symbol"] = _populate_generic_tos_symbol(session, "hist_call", as_of_date)
    counts["hist_etf_tos_symbol"] = _populate_generic_tos_symbol(session, "hist_etf", as_of_date)
    counts["hist_ii_tos_symbol"] = _populate_generic_tos_symbol(session, "hist_ii", as_of_date)
    counts["hist_sss_tos_symbol"] = _populate_generic_tos_symbol(session, "hist_sss", as_of_date)
    counts["hist_cs_tos_symbol"] = _populate_generic_tos_symbol(session, "hist_cs", as_of_date)
    counts["hist_cst_tos_symbol"] = _populate_generic_tos_symbol(session, "hist_cst", as_of_date)
    counts["hist_f_tos_symbol"] = _populate_generic_tos_symbol(session, "hist_f", as_of_date)
    counts["hist_ft_tos_symbol"] = _populate_generic_tos_symbol(session, "hist_ft", as_of_date)

    # hist_ps: Uses 'ticker' column instead of 'symbol'
    counts["hist_ps_tos_symbol"] = _populate_ps_tos_symbol(session, as_of_date)

    # hist_etfchg, hist_iichg: Event-based change tables
    counts["hist_etfchg_tos_symbol"] = _populate_generic_tos_symbol(session, "hist_etfchg", as_of_date)
    counts["hist_iichg_tos_symbol"] = _populate_generic_tos_symbol(session, "hist_iichg", as_of_date)

    # Each derive wrapped so one failing/crashing call doesn't kill the rest
    # AND the calling process. Uses BaseException to also catch SystemExit
    # (some libraries call sys.exit() on internal assertion failure).
    def _safe(name, fn):
        try:
            log.info("derive_all: %s starting", name)
            n = fn(session, as_of_date, parent_run_id)
            log.info("derive_all: %s done (%s rows)", name, n)
            return n
        except BaseException as e:
            try:
                log.exception("derive_all: %s FAILED (continuing): %s", name, e)
            except Exception:
                pass
            try:
                session.rollback()
            except Exception:
                pass
            return 0

    counts["drv_td"]  = _safe("drv_td",  derive_td)
    counts["drv_to"]  = _safe("drv_to",  derive_to)
    counts["drv_tw"]  = _safe("drv_tw",  derive_tw)
    counts["drv_sss"] = _safe("drv_sss", derive_sss)

    # drv_cat_atomic_input is now computed by etl/derive_cat_atomic_input.py
    # (Python deriver, see docs/drv_cat_atomic_input_logic.md).  It depends on
    # drv_quote, so we run it AFTER drv_quote+drv_ma below.  The legacy
    # registry path (ma_codegen + ref_ma_columns.source_expr) silently
    # produced all-NULL rows for ~100 columns — retired 2026-05-27.

    # ---- drv2_* layer RETIRED 2026-05-12 — archived 2026-05-12 (see _trash_2026-05-12/etl/_archived/) ----

    # drv_y converts hist_y string columns to numeric
    counts["drv_y"]                   = _safe("drv_y",                 derive_y)

    # drv_quote merges hist_y / hist_tl / hist_td quote fields by latest loaded_at
    counts["drv_quote"]               = _safe("drv_quote",             derive_quote)
    counts["drv_rr"]                  = _safe("drv_rr",                derive_rr)
    # Component tables replacing drv_ma (2026-05-31)
    counts["drv_symbols"]      = _safe("drv_symbols",      derive_symbols)
    counts["drv_technicals"]   = _safe("drv_technicals",   derive_technicals)
    counts["drv_fundamentals"] = _safe("drv_fundamentals", derive_fundamentals)
    counts["drv_outlooks"]     = _safe("drv_outlooks",     derive_outlooks)
    counts["drv_portfolio"]    = _safe("drv_portfolio",    derive_portfolio)
    # drv_ma is now a VIEW — no direct write needed
    # drv_cat_atomic_input — Python deriver (JF..NP + QH/QI).
    # Must run AFTER drv_quote (Step-1 SELECT pulls last_price from there).
    def _drv_cat_atomic_input_runner(session, as_of_date, parent_run_id=None):
        from etl.derive_cat_atomic_input import derive_cat_atomic_input
        return derive_cat_atomic_input(session, as_of_date, parent_run_id)
    counts["drv_cat_atomic_input"]    = _safe(
        "drv_cat_atomic_input", _drv_cat_atomic_input_runner)
    # MA-tab rule columns (QE/QJ/QM/QN/QR) — must run AFTER drv_cat_atomic_input
    # (Pass-1 reads its perf1d_sd_rule / trade_rule / trend_rule / etc.).
    counts["trend_trade_rules"]       = _safe("trend_trade_rules",     _derive_trend_trade_rules_impl)
    # Parm-lookup Pass-3 (QF/QG/QK/QL/QO/QP/QQ/QS/QT) — runs AFTER
    # trend_trade_rules has populated QE/QJ/QM/QN/QR.
    def _drv_cat_atomic_input_pass3(session, as_of_date, parent_run_id=None):
        from etl.derive_cat_atomic_input import run_parm_lookup_pass3
        return run_parm_lookup_pass3(session, as_of_date)
    counts["drv_cat_atomic_input_pass3"] = _safe(
        "drv_cat_atomic_input_pass3", _drv_cat_atomic_input_pass3)
    counts["drv_dash"]                = _safe("drv_dash",              derive_dash)
    counts["drv_stks"]                = _safe("drv_stks",              derive_stks)
    counts["drv_cs_realized_gain"]    = _safe("drv_cs_realized_gain",  derive_cs_realized_gain)
    counts["drv_dash_summary"]        = _safe("drv_dash_summary",      derive_dash_summary)

    # ---- Actionable Stocks pipeline (outlook-weight + resolver) ----
    try:
        from etl.derive_outlook_action import derive_outlook_action
        counts["drv_outlook_action"] = _safe("drv_outlook_action", derive_outlook_action)
    except Exception:
        log.exception("drv_outlook_action import/run failed (continuing)")
        counts["drv_outlook_action"] = 0
        try: session.rollback()
        except Exception: pass

    try:
        from etl.derive_actionable import derive_actionable
        counts["drv_actionable"] = _safe("drv_actionable", derive_actionable)
    except Exception:
        log.exception("drv_actionable import/run failed (continuing)")
        counts["drv_actionable"] = 0
        try: session.rollback()
        except Exception: pass

    counts["drv_missing_symbols"] = _safe("drv_missing_symbols", derive_missing_symbols)
    counts["drv_trig"]            = _safe("drv_trig",            derive_trig)

    return counts
