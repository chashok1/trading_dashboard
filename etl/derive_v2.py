"""
Upgraded derive functions for TW, PS, ETF, II, SSS.
Translates the actual Excel formulas extracted from the workbook into Python.

derive_tw and derive_sss defined here are re-exported by etl/derive.py
via a top-of-file import, so derive_all() can call them directly.

Each function follows the same pattern as the originals:
  - opens a meta_derived_run row
  - DELETEs WHERE date_col = D from its target table
  - INSERTs the recomputed rows
  - closes the run row

All numeric helpers handle NaN/None gracefully (Excel-style).
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
from etl._derive_common import _open_drv_run, _close_drv_run, _wrap

# =============================================================================
# Shared cleanup helper — Excel pattern: IF("NaN"|None|"<empty>", 0, value)
# =============================================================================

def _clean(v) -> float:
    if v is None:
        return 0.0
    if isinstance(v, str):
        s = v.strip()
        if s in ("", "NaN", "<empty>", "#N/A", "#REF!", "#VALUE!"):
            return 0.0
        try:
            return float(s.replace(",", ""))
        except ValueError:
            return 0.0
    try:
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return 0.0
        return f
    except (TypeError, ValueError):
        return 0.0


def _safe_div(a, b) -> float:
    return (a / b) if b else 0.0


# =============================================================================
# Outlook → weight + weight → BuySell helpers (read from ref_param)
# =============================================================================

def _load_outlook_weight(session: Session, sheet: str = "outlook") -> dict[str, float]:
    """Load outlook→weight mapping from ref_param. sheet='outlook' or 'outlook_rr'."""
    rows = session.execute(text(
        "SELECT param_name, value FROM ref_param WHERE sheet = :s"
    ), {"s": sheet}).fetchall()
    out: dict[str, float] = {}
    for name, val in rows:
        try:
            out[name.upper()] = float(val) if val is not None else 0.0
        except (TypeError, ValueError):
            pass
    out.setdefault("BULLISH", 3.0)
    out.setdefault("BEARISH", -3.0)
    out.setdefault("NEUTRAL", 0.0)
    return out


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
      G  FCF              = clean(fcf_per_share)
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
        SELECT snapshot_date, symbol, sequence
        FROM hist_tw WHERE snapshot_date = :d
    """), {"d": as_of_date}).mappings().all()
    if not cur_rows:
        return 0

    symbols = list({r["symbol"] for r in cur_rows})
    history = session.execute(text("""
        SELECT snapshot_date, symbol, sequence,
               last_price, change_pct, sma_20, sma_50, sma_200,
               volume, volume_avg_10d, volume_avg_3m, volume_rate_change,
               a_macd_brr, a_macdh_d_brr, a_earnings_days, fcf_per_share
        FROM hist_tw
        WHERE snapshot_date <= :d AND symbol = ANY(:syms)
        ORDER BY symbol, snapshot_date ASC, sequence ASC
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

        snap = r["snapshot_date"]
        seq = r["sequence"]
        out.append({
            "snapshot_date":              snap,
            "symbol":                     sym,
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
            "source_run_id":              run_id,
        })
    return replace_for_date(session, "drv_tw", "snapshot_date", as_of_date, out)


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
# SSS — Signal Strength Summary
# =============================================================================

def _derive_sss_v2_impl(session: Session, as_of_date: date, run_id: int) -> int:
    """
    Mirrors SSS Excel formulas:
      D Rank HL    = if Unranked = "" use Rank else 0
      E Unranked   = if Anlst="KMSignal" 99, "Bench" 50, else ""
      F Signal     = pct_delta (% Delta Since Initial from raw Y col)
      G AnlstBest  = anlst_best_idea_rank raw
      H Rank       = parse "/" from G - first part as int (or 99 KMSignal, 50 Bench)
      I Total      = parse "/" from G - second part (default 9)
      J SignalSign = IFS(F>0.5,3, F>0.25,2, F>0,1, F<=0,-1)
      K Is Latest  = "Y" if this date = max(snapshot_date) globally
      L Latest     = symbol if this is max date for THIS symbol
      M Removed    = if was latest before but not this time
      N Miss MA    = symbol if missing from MA AND is_latest=Y
      O,P,Q,R     = lookup symbol against TL/MA/Y/SSS
    """
    cur_rows = session.execute(text("""
        SELECT snapshot_date, symbol, days_on, signal_date, prior_close,
               last_close, pct_delta, sector, analyst, anlst_best_idea_rank
        FROM hist_sss WHERE snapshot_date = :d
    """), {"d": as_of_date}).mappings().all()
    if not cur_rows:
        return 0

    # Global max snapshot_date in hist_sss up to as_of_date
    max_date_global = session.execute(text("""
        SELECT MAX(snapshot_date) FROM hist_sss WHERE snapshot_date <= :d
    """), {"d": as_of_date}).scalar()

    # Latest date PER symbol
    latest_per_sym = {
        row.symbol: row.max_d for row in session.execute(text("""
            SELECT symbol, MAX(snapshot_date) AS max_d
            FROM hist_sss WHERE snapshot_date <= :d GROUP BY symbol
        """), {"d": as_of_date})
    }

    # Was this symbol latest on PREVIOUS snapshot_date (for "removed" detection)
    prev_latest = {
        row.symbol: row.max_d for row in session.execute(text("""
            SELECT symbol, MAX(snapshot_date) AS max_d
            FROM hist_sss
            WHERE snapshot_date < :d
            GROUP BY symbol
        """), {"d": as_of_date})
    }

    # Lookup sets for cross-tab refs
    ma_syms  = {row[0] for row in session.execute(text(
        "SELECT symbol FROM drv_ma WHERE as_of_date = :d"
    ), {"d": as_of_date})}
    tl_syms  = {row[0] for row in session.execute(text(
        "SELECT DISTINCT symbol FROM hist_tl WHERE snapshot_date = :d"
    ), {"d": as_of_date})}
    y_syms   = {row[0] for row in session.execute(text(
        "SELECT DISTINCT COALESCE(tos_symbol, symbol) FROM hist_y WHERE snapshot_date = :d"
    ), {"d": as_of_date})}

    out: list[dict] = []
    for r in cur_rows:
        sym = r["symbol"]
        anlst_raw = (r["anlst_best_idea_rank"] or "").strip()

        # E Unranked
        if anlst_raw.lower() == "kmsignal":
            unranked = "99"
        elif anlst_raw.lower() == "bench":
            unranked = "50"
        else:
            unranked = ""

        # H Rank
        if anlst_raw.lower() == "kmsignal":
            rank = 99
        elif anlst_raw.lower() == "bench":
            rank = 50
        else:
            try:
                rank = float(anlst_raw.split("/")[0]) if "/" in anlst_raw else None
            except ValueError:
                rank = None

        # I Total
        try:
            total = float(anlst_raw.split("/")[1]) if "/" in anlst_raw else 9.0
        except (ValueError, IndexError):
            total = 9.0

        # D Rank HL
        rank_hl = (rank if rank is not None else 0) if not unranked else 0

        # F Signal
        signal = _clean(r["pct_delta"])

        # J Signal Sign
        if signal > 0.5: sig_sign = 3
        elif signal > 0.25: sig_sign = 2
        elif signal > 0: sig_sign = 1
        else: sig_sign = -1

        # K Is Latest
        is_latest = "Y" if r["snapshot_date"] == max_date_global else ""

        # L Latest (per symbol)
        latest_for_sym = "Y" if latest_per_sym.get(sym) == r["snapshot_date"] else ""

        # M Removed Date
        removed = None
        if latest_for_sym == "Y" and is_latest != "Y":
            removed = r["snapshot_date"]

        # N Miss MA
        miss_ma = sym if (is_latest == "Y" and sym not in ma_syms) else ""

        # Lookups
        tos_lookup = sym if sym in tl_syms else None
        ma_lookup = sym if sym in ma_syms else None
        y_lookup = sym if sym in y_syms else None

        out.append({
            "snapshot_date":     r["snapshot_date"],
            "symbol":            sym,
            "rank_hl":           rank_hl,
            "unranked":          unranked,
            "signal":            signal,
            "anlst_best_idea":   anlst_raw,
            "rank":              rank,
            "total":             total,
            "signal_sign":       sig_sign,
            "is_latest":         is_latest,
            "latest_symbol":     sym if latest_for_sym == "Y" else None,
            "removed_date":      removed,
            "miss_ma":           miss_ma,
            "tos_lookup":        tos_lookup,
            "ma_lookup":         ma_lookup,
            "y_lookup":          y_lookup,
            "vlkup":             None,  # would lookup against drv_sss
            "source_run_id":     run_id,
        })
    return replace_for_date(session, "drv_sss", "snapshot_date", as_of_date, out)


derive_sss = _wrap("drv_sss", _derive_sss_v2_impl)


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

