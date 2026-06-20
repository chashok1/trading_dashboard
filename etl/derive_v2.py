"""
etl/derive_v2.py — SINGLE-PURPOSE TW OVERRIDE (2026-06-17, TASK_59).

This module now provides ONLY derive_tw (formula-faithful TW deriver).

History:
  - Originally contained upgraded derives for TW, PS, ETF, II, SSS.
  - ETF/II/PS archived 2026-05-12 (v2 equivalents adopted into main derive.py).
  - SSS retired 2026-06-13 (drv_sss dropped; SSS moved to drv_source_standing).
  - Only derive_tw remains; it is re-exported by etl/derive.py at module load.

Do NOT add general v2 derives here — extend etl/derive.py directly or create
a dedicated etl/derive_<topic>.py instead.
"""
from __future__ import annotations

import math
from datetime import date
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from etl.db import get_table, replace_for_date

# Shared meta_derived_run helpers — see etl/_derive_common.py.
# These used to be inlined here to break a circular import with derive.py;
# both modules now share the canonical definitions in _derive_common.
from etl._derive_common import (
    _open_drv_run, _close_drv_run, _wrap,
    _clean,                   # TASK_56: consolidated (includes "<empty>" sentinel)
    _load_outlook_weights,    # TASK_56: canonical name with sheet= param
)

# Alias for callers in this module that still use the old name.
_load_outlook_weight = _load_outlook_weights

# _safe_div here returns 0.0 on missing inputs, differing from the
# None-returning version in _derive_common.  Keep the local copy.
def _safe_div(a, b) -> float:
    """a / b; returns 0.0 when b is falsy (0 or None)."""
    return (a / b) if b else 0.0


def _load_buysell_lookup(session: Session) -> dict[str, tuple[str, float]]:
    """Returns {action_name → (action_name, weight)} from ref_param_lookup buysell."""
    rows = session.execute(text("""
        SELECT code, action, extra1 FROM ref_param_lookup
        WHERE table_name = 'buysell'
    """)).fetchall()
    out: dict[str, tuple[str, float]] = {}
    for code, action, weight_str in rows:
        try:
            wt = float(weight_str) if weight_str is not None else 0.0
        except (TypeError, ValueError):
            wt = 0.0
        if action:
            out[action] = (action, wt)
        if code and code != action:
            out[code] = (action or code, wt)
    return out


def _action_to_weight(action_name: Optional[str],
                      lookup: dict[str, tuple[str, float]]) -> Optional[float]:
    if not action_name:
        return None
    entry = lookup.get(action_name) or lookup.get(action_name.lower())
    return entry[1] if entry else None


# =============================================================================
# TW — derived columns A-X (per-row formulas + weekly lookups)
# =============================================================================

def _derive_tw_v2_impl(session: Session, as_of_date: date, run_id: int) -> int:
    """
    Mirrors TW Excel formulas:
      G  FCF              = clean(hist_to.fcf_per_share)
      H  20 DMA           = clean(sma_20)
      I  50 DMA           = clean(sma_50)
      J  200 DMA          = clean(sma_200)
      K  W_Vlm            = clean(volume)
      L  Avg Vlm (10d)    = clean(volume_avg_10d)
      M  Avg Vlm (3m)     = clean(volume_avg_3m)
      N  VlmRateOfChange  = clean(volume_rate_change)
      O  W_Vlm_Expn_Ratio = K / L
      P  W_Prior-DayVlmExpnRatio = lookup prior O for this symbol
      Q  %Change          = change_pct
      R  Last Price       = last_price (raw last)
      S  W_Price_WkAgo    = lookup prior last_price from ~1 week ago
      T  W_%Change_Wk     = (R - S) * 100 / S
      U  W_Vlm_RuleDesc   = 10-rule IFS based on T,O,N,K,L,M,P,Q
      V  A_MACD_BRR       = clean(a_macd_brr)
      W  A_MACDH_D_BRR    = clean(a_macdh_d_brr)
      X  EarningsDays     = a_earnings_days, NaN -> -99
    """
    cur_rows = session.execute(text("""
        SELECT snapshot_date, tos_symbol AS symbol, sequence
        FROM hist_tw WHERE snapshot_date = :d
    """), {"d": as_of_date}).mappings().all()
    if not cur_rows:
        return 0

    symbols = list({r["symbol"] for r in cur_rows})
    history = session.execute(text("""
        SELECT tw.snapshot_date, tw.tos_symbol AS symbol, tw.sequence,
               tw.last_price, tw.change_pct, tw.sma_20, tw.sma_50, tw.sma_200,
               tw.volume, tw.volume_avg_10d, tw.volume_avg_3m, tw.volume_rate_change,
               tw.a_macd_brr, tw.a_macdh_d_brr, tw.a_earnings_days,
               to_row.fcf_per_share
        FROM hist_tw tw
        LEFT JOIN (
            SELECT DISTINCT ON (tos_symbol) tos_symbol AS symbol, fcf_per_share
            FROM hist_to
            WHERE snapshot_date <= :d
            ORDER BY tos_symbol, snapshot_date DESC, sequence DESC
        ) to_row ON tw.tos_symbol = to_row.symbol
        WHERE tw.snapshot_date <= :d AND tw.tos_symbol = ANY(:syms)
        ORDER BY tw.tos_symbol, tw.snapshot_date ASC, tw.sequence ASC
    """), {"d": as_of_date, "syms": symbols}).fetchall()

    by_sym: dict[str, list] = {}
    for h in history:
        by_sym.setdefault(h.symbol, []).append(h)

    out: list[dict] = []
    for r in cur_rows:
        sym = r["symbol"]
        hist = by_sym.get(sym, [])
        if not hist:
            continue
        cur = hist[-1]

        fcf = _clean(cur.fcf_per_share)
        sma20 = _clean(cur.sma_20)
        sma50 = _clean(cur.sma_50)
        sma200 = _clean(cur.sma_200)
        w_vlm = _clean(cur.volume)
        avg10 = _clean(cur.volume_avg_10d)
        avg3m = _clean(cur.volume_avg_3m)
        v_roc = _clean(cur.volume_rate_change)
        ratio = _safe_div(w_vlm, avg10)
        change_pct = _clean(cur.change_pct)
        last_price = _clean(cur.last_price)

        # P: prior W_Vlm_Expn_Ratio (one record back for this symbol)
        prior_ratio = 0.0
        if len(hist) >= 2:
            prev = hist[-2]
            p_w_vlm = _clean(prev.volume)
            p_avg10 = _clean(prev.volume_avg_10d)
            prior_ratio = _safe_div(p_w_vlm, p_avg10)

        # S: price ~1 week ago (the most recent record at least 5 trading days back)
        cur_date = cur.snapshot_date
        wk_ago_price = 0.0
        from datetime import timedelta
        cutoff = cur_date - timedelta(days=5) if cur_date else None
        if cutoff:
            for prev in reversed(hist[:-1]):
                if prev.snapshot_date and prev.snapshot_date <= cutoff:
                    wk_ago_price = _clean(prev.last_price)
                    break

        # T: weekly % change
        wk_pct_change = ((last_price - wk_ago_price) * 100.0 / wk_ago_price) \
            if wk_ago_price else 0.0

        # U: W_Vlm_RuleDesc — 10-rule IFS
        rule_desc = _tw_vlm_rule_desc(
            wk_pct_change, ratio, v_roc, w_vlm, avg10, avg3m, prior_ratio, change_pct
        )

        macd_brr = _clean(cur.a_macd_brr)
        macdh_brr = _clean(cur.a_macdh_d_brr)
        # X: EarningsDays NaN -> -99
        ed_raw = cur.a_earnings_days
        if ed_raw is None or (isinstance(ed_raw, float) and math.isnan(ed_raw)):
            earnings_days = -99
        else:
            try:
                earnings_days = float(ed_raw)
            except (TypeError, ValueError):
                earnings_days = -99

        # GB: Vlm 3m % = ((W_Vlm - Avg_3m) / Avg_3m) * 100
        # Persisted as vlm_3m_pct (was computed transiently in compute_intermediates).
        if w_vlm and avg3m and avg3m != 0:
            vlm_3m_pct = ((w_vlm - avg3m) / avg3m) * 100.0
        else:
            vlm_3m_pct = None

        # GF: Vlm_RuleDesc — human-readable label for the rule code (Excel Parm!BS/BT).
        # GG: Vlm_Action   — buy/accumulate/avoid tag (Excel Parm!BS/BU).
        vlm_desc   = _VLM_DESC_MAP.get(rule_desc)   if rule_desc else None
        vlm_action = _VLM_ACTION_MAP.get(rule_desc) if rule_desc else None

        snap = r["snapshot_date"]
        seq = r["sequence"]
        out.append({
            "snapshot_date":              snap,
            "tos_symbol":                 sym,
            "sequence":                   seq,
            "fcf":                        fcf,
            "sma_20_d":                   sma20,
            "sma_50_d":                   sma50,
            "sma_200_d":                  sma200,
            "w_volume":                   int(w_vlm) if w_vlm else None,
            "avg_vlm_10d_d":              avg10,
            "avg_vlm_3m_d":               avg3m,
            "vlm_rate_change_d":          v_roc,
            "w_vlm_expn_ratio":           ratio,
            "w_prior_day_vlm_expn_ratio": prior_ratio,
            "change_pct_d":               change_pct,
            "last_price_d":               last_price,
            "w_price_wk_ago":             wk_ago_price,
            "w_pct_change_wk":            wk_pct_change,
            "w_vlm_rule_desc":            rule_desc,
            "a_macd_brr":                 macd_brr,
            "a_macdh_d_brr":              macdh_brr,
            "earnings_days_d":            earnings_days,
            "vlm_3m_pct":                 vlm_3m_pct,
            "vlm_desc":                   vlm_desc,
            "vlm_action":                 vlm_action,
            "source_run_id":              run_id,
        })
    return replace_for_date(session, "drv_tw", "snapshot_date", as_of_date, out)


# Excel Parm!BS/BT mapping: W_Vlm_RuleCode (1..10) → human-readable description (GF).
# Source: Parm tab columns BS:BT; hand-transcribed from audit review 2026-06-20.
_VLM_DESC_MAP: dict[str, str] = {
    "1":  "Strong Week + High RVOL + Rising",
    "2":  "High RVOL + Flat Price",
    "3":  "High ROC + Below Avg Vol",
    "4":  "Very High RVOL + Very High ROC",
    "5":  "Low RVOL + Below 3M Avg",
    "6":  "Moderate ROC + Below Avg Vol",
    "7":  "High RVOL + Above Avg + High ROC",
    "8":  "High RVOL + Near 3M Avg + Rising",
    "9":  "Below RVOL + Above Avg + Rising",
    "10": "Moderate RVOL + Above Avg + Rising",
}

# Excel Parm!BS/BU mapping: W_Vlm_RuleCode (1..10) → action tag (GG = Vlm_Action).
# Source: Parm tab columns BS:BU; derived from rule semantics 2026-06-20.
_VLM_ACTION_MAP: dict[str, str] = {
    "1":  "Accumulate",
    "2":  "Watch",
    "3":  "Avoid",
    "4":  "Accumulate",
    "5":  "Avoid",
    "6":  "Watch",
    "7":  "Accumulate",
    "8":  "Watch",
    "9":  "Watch",
    "10": "Watch",
}


def _tw_vlm_rule_desc(t, o, n, k, l, m, p, q) -> Optional[str]:
    """
    Excel U-formula:
      IFS(
        AND(T>12, O>=2.8, N>=120),                       1,
        AND(O>=1.5, ABS(Q)<0.003),                       2,
        AND(N>=60, K<L, L<=M),                           3,
        AND(O>=2.8, N>=150),                             4,
        AND(L<=1.05*M, O<1),                             5,
        AND(N>=40, K<L, L<=M),                           6,
        AND(O>=2, L>M, N>=80, N<150),                    7,
        AND(L<=1.05*M, O>=2, N>=60, Q>0),                8,
        AND(L>M, O<1, P>=1.5, N>=30, Q>0),               9,
        AND(O>=1.5, L>M, N>=40, N<140, Q>0),             10,
        TRUE, "")
    """
    if t > 12 and o >= 2.8 and n >= 120: return "1"
    if o >= 1.5 and abs(q) < 0.003: return "2"
    if n >= 60 and k < l and l <= m: return "3"
    if o >= 2.8 and n >= 150: return "4"
    if l <= 1.05 * m and o < 1: return "5"
    if n >= 40 and k < l and l <= m: return "6"
    if o >= 2 and l > m and n >= 80 and n < 150: return "7"
    if l <= 1.05 * m and o >= 2 and n >= 60 and q > 0: return "8"
    if l > m and o < 1 and p >= 1.5 and n >= 30 and q > 0: return "9"
    if o >= 1.5 and l > m and n >= 40 and n < 140 and q > 0: return "10"
    return None


derive_tw = _wrap("drv_tw", _derive_tw_v2_impl)


# =============================================================================
# ETF — outlook from BRR, plus all derived lookups
# =============================================================================

# _derive_etf_v2_impl + derive_etf ARCHIVED 2026-05-12 — archived 2026-05-12 (see _trash_2026-05-12/etl/_archived/)

# =============================================================================
# II — outlook from raw "Long/Short", same buysell flow
# =============================================================================

# _derive_ii_v2_impl + derive_ii ARCHIVED 2026-05-12 — archived 2026-05-12 (see _trash_2026-05-12/etl/_archived/)

# =============================================================================
# SSS — _derive_sss_v2_impl + derive_sss RETIRED 2026-06-13
# drv_sss table dropped; SSS data now stored in drv_source_standing.
# =============================================================================

# =============================================================================
# PS — archive note: ps tab derivation removed 2026-05 (ps5/pstn tables removed)
# =============================================================================

# Default weight multipliers (Excel cells AS$2..AS$8). Values here are
# defensible defaults; tune by editing or loading from a config table later.
_PS_WEIGHTS = {
    "two_day": 1.0,
    "three_day": 1.0,
    "four_day": 1.0,
    "five_day": 1.0,
    "one_wk": 2.0,
    "one_mth": 3.0,
    "one_mth_3mth": 4.0,
}


# _derive_ps_v2_impl + derive_ps ARCHIVED 2026-05-12 — archived 2026-05-12 (see _trash_2026-05-12/etl/_archived/)

# =============================================================================
# SSS — Signal Strength Series with proper weighted-change calculations
# =============================================================================

# Excel sss tab uses $AH$2/$AH$4/$AH$5 as weight multipliers. Defaults below.
_SSS_WK_WT = 1.0
_SSS_MTH_WT = 2.0
_SSS_3MTH_WT = 3.0


# _derive_sss_v2_impl + derive_sss ARCHIVED — archived 2026-05-12 (see _trash_2026-05-12/etl/_archived/)

