"""
etl/export_trade_mode.py — nightly Trade Mode digest, emailed after the
nightly job finishes processing the day's exports.

2026-08-25, user-directed: "i want to send a trade mode export to that
[Gmail] email every night after processing all exports" -- full parity
with the on-screen Trade Mode + Strict view (AskUserQuestion, same date).

Trade Mode's Strict view (web/actionable.js) exists ONLY as client-side JS,
including a live-computed Tradability Score with no server-side equivalent.
Rather than re-derive drv_actionable/drv_technicals/etc. from scratch in
SQL, this calls the SAME endpoints the browser calls (GET /api/actionable,
source-scorecard, factor-scorecard, settings) against the locally-running
FastAPI app, then re-implements the identical filter + score logic in
Python below. This is a deliberate, documented duplication -- one side is
browser JS, the other a headless nightly job, so there's no shared-module
option -- not an oversight. 2026-08-28: web/actionable.js's Trade Mode
button now ALWAYS applies the (formerly opt-in) Strict criteria -- this
module's `strict` parameter/build_trade_mode_export(strict=True) default
already matched that, no behavior change needed here beyond the BMN rule
below. If you change any of the following in web/actionable.js, mirror the
change here too:
  _isTradeModeQualifyingBuy / _isTradeModeQualifyingBuyLoose /
  _isTradeModeHeldSaSell / _isTradeModeStopBreach
  _buyTradabilityScore and its helpers (_lrrProximityScore, _rawRrPos,
  _factorWinRateDelta, _rsiBucket, _rvolBucket, _ivRatioScore,
  _sourceTrackRecordScore, _buyAgreementSubTier)
  _MACRO_BUY/_MACRO_SELL/_SRC_BUY/_SRC_SELL/_TECH_SELL/_ENTRY_RIPE_TECH/
  _TECH_GATE_EXEMPT_SRC/_TRADABILITY_BADGE_MIN

Never raises -- every step is best-effort so a broken export can't take
down the rest of the nightly job. Skips (logs + returns) if NOTIFY_EMAIL
isn't on, if the local API isn't reachable, or if there's nothing to send.

Usage: python -m etl.export_trade_mode   (manual trigger / testing)
"""
from __future__ import annotations

import html
import json
import logging
import urllib.parse
import urllib.request
from typing import Optional

from config.settings import settings

log = logging.getLogger(__name__)

# Mirrors web/actionable.js's _ENTRY_RIPE_TECH / _TECH_GATE_EXEMPT_SRC /
# _MACRO_BUY / _MACRO_SELL / _SRC_BUY / _SRC_SELL / _TECH_SELL /
# _TRADABILITY_BADGE_MIN / _PVV_BUY_SIDE exactly -- see module docstring.
_ENTRY_RIPE_TECH = ("BS", "BM", "BMN")
_TECH_GATE_EXEMPT_SRC = ("RTA",)  # SSSCHG/TOP5 lost this exemption 2026-09-12
_MACRO_BUY = {"BM", "BS"}
_MACRO_SELL = {"STM", "SA"}
_SRC_BUY = {"ADD", "INCREASE"}
_SRC_SELL = {"REDUCE", "REMOVE"}
_TECH_SELL = {"SA", "STM", "SS", "SO"}
_TRADABILITY_BADGE_MIN = 9  # 2026-10-28: re-cut for the +-3 scale (was 12)
_PVV_BUY_SIDE = ("BUY_LRR", "BUY_DIP", "BUY_WATCH")


def _api_base() -> str:
    return f"http://{settings.api_host}:{settings.api_port}"


def _get_json(path: str):
    url = _api_base() + path
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ---------------------------------------------------------------------------
# Ported scoring helpers -- see web/actionable.js for the JS originals.
# ---------------------------------------------------------------------------

def _rsi_bucket(rsi, overbought, oversold):
    if rsi is None:
        return None
    rv = float(rsi)
    if rv <= oversold:
        return f"Oversold (<={oversold:g})"
    if rv >= overbought:
        return f"Overbought (>={overbought:g})"
    return "Neutral"


def _rvol_bucket(rvol, pct_change, threshold):
    if rvol is None:
        return None
    rv = float(rvol)
    if rv >= threshold and pct_change is not None and float(pct_change) > 0:
        return "High RVOL + up day"
    if rv >= threshold and pct_change is not None and float(pct_change) < 0:
        return "High RVOL + down day"
    return "Normal/low RVOL"


def _factor_win_rate_delta(factor_scorecard, factor, bucket):
    if not bucket:
        return None
    r = factor_scorecard.get(f"{factor}|{bucket}")
    base = factor_scorecard.get("Baseline|All stocks")
    if not r or r.get("win_rate") is None or not base or base.get("win_rate") is None:
        return None
    return (float(r["win_rate"]) - float(base["win_rate"])) * 100


def _iv_ratio_score(ratio):
    if ratio is None:
        return 0
    r = float(ratio)
    if r > 1.15:
        return -3
    if r < 1:
        return 3
    return 0


def _raw_rr_pos(row):
    lrr, trr, last = row.get("lrr"), row.get("trr"), row.get("last_price")
    if lrr is None or trr is None or last is None:
        return None
    lrr, trr, last = float(lrr), float(trr), float(last)
    if trr == lrr:
        return None
    return (last - lrr) / (trr - lrr) * 100


def _lrr_proximity_score(row):
    raw_pos = _raw_rr_pos(row)
    if raw_pos is None:
        return 0
    pct_change = row.get("pct_change")
    turning_up = pct_change is not None and float(pct_change) >= 0
    if raw_pos < 0:
        if not turning_up:
            return -1
        return max(0, 0.3 - abs(raw_pos) / 100)
    # Rules engine brrpct_lrr breakpoints (35% / 75%): +1 at or below 35%, -1 at or above 75%.
    return max(-1, min(1, 1 - 2 * (raw_pos - 35) / 40))


def _rsi_pts(row, overbought, oversold):
    """Rules engine rsi_rule breakpoints (45 / 70): +3 at or below 45, -3 at or above 70,
    straight line between. overbought/oversold args kept for call-site compatibility."""
    if row.get("rsi") is None:
        return 0
    return max(-3, min(3, 3 - 6 * (float(row["rsi"]) - 45) / (70 - 45)))


def _vol_pts(row, threshold):
    """The Vlm column's own label (vlm_action): Accumulate +3, Watch 0, Avoid -3, no label 0.
    `threshold` kept for call-site compatibility (the old RVOL ramp)."""
    a = str(row.get("vlm_action") or "").upper()
    return 3 if a == "ACCUMULATE" else -3 if a == "AVOID" else 0


def _iv_premium_pts(row):
    """IV / HV - 1 in % (the grid's rich / cheap labels): very cheap +3, cheap +1.5, fair 0,
    rich -1.5, very rich -3. Historical vol of 10% or less is rounding noise -> 0."""
    if row.get("iv_to_hv_discount") is not None:
        pr = -float(row["iv_to_hv_discount"])
    else:
        ratio = row.get("d_iv_to_hv")
        if ratio is None or float(ratio) <= 0:
            return 0
        pr = (float(ratio) - 1) * 100
    if row.get("hv") is not None and float(row["hv"]) * 100 <= 10:
        return 0
    return -3 if pr >= 30 else -1.5 if pr >= 10 else 3 if pr <= -30 else 1.5 if pr <= -10 else 0


def _as_list(v):
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except ValueError:
            return []
    return v if isinstance(v, list) else []


def _support_oppose_pts(row, factor_scorecard):
    """Server-side subset of web/actionable_pops.js::_supportOpposePts: +1 per supporting line, -1 per
    opposing line, net capped at +-3. Lines already scored (RSI, IV, volume, TRR) and Rules are left out,
    same as the screen. NOT mirrored here (need browser-only state): the 'not investable' volatility-zone
    lines and the inverting yield curve line for Financials."""
    sup = opp = 0
    for f in _as_list(row.get("driver_flags")):
        v = f.get("verdict")
        if v in ("headwind", "stretched"):
            opp += 1
        elif v == "tailwind":
            sup += 1
    if row.get("warn_added_this_leg"):
        opp += 1
    sector = row.get("sector")
    if row.get("sector_stance") is not None and float(row["sector_stance"]) < 0 and sector and sector != "N/A":
        opp += 1
    base = factor_scorecard.get("Baseline|All stocks")

    def gated_delta(factor, bucket):
        r = factor_scorecard.get(f"{factor}|{bucket}")
        if not r or r.get("win_rate") is None or not base or base.get("win_rate") is None:
            return None
        if (r.get("n_symbols") or 0) < 5:
            return None
        return (float(r["win_rate"]) - float(base["win_rate"])) * 100

    src = str(row.get("winning_source") or "").upper()
    d = gated_delta("Winning source", src) if src else None
    if d is not None and d < -3:
        opp += 1
    d = gated_delta("Sector", sector) if sector and sector != "N/A" else None
    if d is not None and d < -3:
        opp += 1
    opp += sum(1 for e in _as_list(row.get("source_actions")) if e.get("warning_only"))
    wc = row.get("why_card")
    if isinstance(wc, str):
        try:
            wc = json.loads(wc)
        except ValueError:
            wc = None
    if isinstance(wc, dict):
        for step in wc.get("steps") or []:
            if step.get("key") == "technical":
                opp += sum(1 for ln in step.get("lines") or [] if ln.get("warn"))
    return max(-3, min(3, sup - opp))


_ACT_BUY = {"INCREASE", "BS", "BM", "ADD", "BMN", "BW", "BSW", "BR", "BC", "BRW", "B"}
_ACT_SELL = {"REMOVE", "SA", "REDUCE", "SS", "STM", "OVER_MAX", "SO", "SW", "SWW", "S"}


def _sources_pts(row):
    """Sources saying buy +1 / sell -1 (warning-only skipped), net capped at +-3. Mirrors
    web/actionable_pops.js::_sourcesPts (buy / sell sets mirror web/actions.js)."""
    n = 0
    for e in _as_list(row.get("source_actions")):
        if e.get("warning_only"):
            continue
        a = str(e.get("action") or "").upper()
        n += 1 if a in _ACT_BUY else -1 if a in _ACT_SELL else 0
    return max(-3, min(3, n))


def _trend_line_check(d, lo, hi):
    """-3 at or below the line, rising in a straight line to 0 at `lo` and +3 at `hi` (AC / SD units)."""
    if d <= 0:
        return -3.0
    if d < lo:
        return -3 + 3 * d / lo
    return min(3.0, 3 * (d - lo) / (hi - lo))


def _trend_structure_pts(row):
    """ONE formula for the Trade / Trend lines (mirrors web/actionable_pops.js::_trendStructurePts): the weakest
    of three checks -- price vs Trade (1..5 SD, trade_rule), price vs Trend (3..12 SD, trend_rule), and Trade vs
    Trend, the gap (3..12 SD, trade_trend_sd_rule). Any missing input = 0."""
    p, a, e, ac, g = (row.get(k) for k in ("last_price", "trade_line_value", "trend_line_value", "ac", "trade_trend_sd"))
    if None in (p, a, e, ac, g) or float(ac) <= 0:
        return 0
    p, a, e, ac, g = float(p), float(a), float(e), float(ac), float(g)
    return min(_trend_line_check((p - a) / ac, 1, 5), _trend_line_check((p - e) / ac, 3, 12),
               _trend_line_check(g, 3, 12))


def _fc_code_pts(row):
    """Final Call buy code as a score term: Buy More +3, Buy Some +1.5, Buy To Min 0."""
    code = str(row.get("final_code") or "").upper()
    return 3 if code == "BM" else 1.5 if code == "BS" else 0


def _macdh_pts(row):
    """a_macdh_d_brr = position in the 120-day MACDH range (0..1), sign = today's
    direction. Rising from low in the range scores most, falling from high scores least."""
    v = row.get("a_macdh_d_brr")
    if v is None:
        return 0
    v = float(v)
    if v > 0:
        return 3 * (1 - min(v, 1))
    if v < 0:
        return 3 * max(v, -1)
    return 0


_PVV_PTS = {"BUY_LRR": 3, "BUY_DIP": 3, "BUY_WATCH": 1.5, "TRIM": -1.5,
            "REDUCE": -3, "SELL": -3, "SELL_WATCH": -3, "AVOID": -3}


def _pvv_pts(row):
    return _PVV_PTS.get(str(row.get("pvv_decision") or "").upper(), 0)


def _agreement_pts(row):
    sub = _buy_agreement_sub_tier(row)
    if sub == 2:
        return 3
    if sub == 1:
        return 1.5
    m = str(row.get("macro_value") or "").upper()
    s = str(row.get("consolidated_action") or "").upper()
    t = str(row.get("rr_action") or "").upper()
    return -3 if (t in _TECH_SELL or s in _SRC_SELL or m in _MACRO_SELL) else 0


def _buy_agreement_sub_tier(row):
    m = str(row.get("macro_value") or "").upper()
    s = str(row.get("consolidated_action") or "").upper()
    t = str(row.get("rr_action") or "").upper()
    tech_buy = t in _ENTRY_RIPE_TECH
    src_buy = s in _SRC_BUY
    macro_buy = m in _MACRO_BUY
    any_sell = t in _TECH_SELL or s in _SRC_SELL or m in _MACRO_SELL
    buy_votes = int(tech_buy) + int(src_buy) + int(macro_buy)
    if buy_votes == 3:
        return 2
    if buy_votes == 2 and not any_sell:
        return 1
    return 0


def _buy_tradability_score(row, rsi_overbought, rsi_oversold, rvol_threshold,
                            factor_scorecard, source_scorecard):
    # 2026-10-28, user: every condition is scaled to 0..3 (no negative numbers, so a weak condition earns
    # nothing instead of subtracting from the others). Each +-3 term is mapped by (x + 3) / 2, so the old
    # -3 / 0 / +3 become 0 / 1.5 / 3; the Final Call code is already 0..3 and is added as it is. Volume, IV,
    # supporting / opposing, Technical and Source track record are not in the score (their functions are kept).
    return (_s03(_lrr_proximity_score(row) * 3)
            + _s03(_rsi_pts(row, rsi_overbought, rsi_oversold))
            + _s03(_macdh_pts(row))
            + _s03(_agreement_pts(row))  # PVV, Final Call code and Sources removed (user, 2026-10-28); functions kept, unused
            + _s03(_trend_structure_pts(row)))


def _s03(v):
    """Map a -3..+3 term onto 0..3."""
    return (v + 3) / 2


def _is_true(v) -> bool:
    return v is True or v == "true"


def _is_qualifying_buy(row, strict, rsi_overbought, rsi_oversold, rvol_threshold,
                        factor_scorecard, source_scorecard):
    # 2026-10-28, user: Trade rules reset -- mirrors web/actionable.js::_isTradeModeQualifyingBuy(Loose).
    # BM / BMN / BS, feasible, Technical ripe (RTA skips), MACRO not SA/STM unless held; macro instruments and
    # Fixed Income excluded; PVV not AVOID; BMN only above the Trade line. No stop-breach test, no score cut-off.
    code = str(row.get("final_code") or "").upper()
    if code not in ("BM", "BMN", "BS"):
        return False
    if _is_true(row.get("is_macro_instrument")) or str(row.get("asset_class") or "").lower() == "fixed income":
        return False
    if not _is_true(row.get("fc_feasible")):
        return False
    src = str(row.get("winning_source") or "").upper()
    tech = str(row.get("rr_action") or "").upper()
    if src not in _TECH_GATE_EXEMPT_SRC and tech not in _ENTRY_RIPE_TECH:
        return False
    mv = str(row.get("macro_value") or "").upper()
    if mv in ("SA", "STM") and not row.get("held_today"):
        return False
    if strict:
        # 2026-08-27, 4th Strict-only tightening pass -- mirrors
        # web/actionable.js's own _isTradeModeQualifyingBuy change (see
        # module docstring). User: "Also remove PVV -> AVOID from strict
        # mode."
        if str(row.get("pvv_decision") or "").upper() == "AVOID":
            return False
        # 2026-10-28, user: every Buy To Min (BMN) moves to Trade2 -- Trade keeps Buy More and Buy Some only.
        # (The "BMN only above the Trade line" test stays removed.) Mirrors web/actionable.js.
        if code == "BMN":
            return False
    return True


def _is_held_sa_sell(row) -> bool:
    """Held sell (SA / SS / STM), mirrors web/actionable.js::_isTradeModeHeldSell. Macro instruments and
    Fixed Income are excluded, same as the screen."""
    if _is_true(row.get("is_macro_instrument")) or str(row.get("asset_class") or "").lower() == "fixed income":
        return False
    return bool(row.get("held_today")) and str(row.get("final_code") or "").upper() in ("SA", "SS", "STM")


def _is_stop_breach(row) -> bool:
    # 2026-10-28, user: stop-breach rows are no longer part of Trade.
    return False


def _get_ac_for_symbol(tos_symbol: str, as_of_date) -> "float | None":
    """AC = volatility scale (MIN(standard_dev, median_sd), $ terms) --
    etl/derive_cat_atomic_input.py::compute_intermediates. Not exposed by
    /api/actionable (that query deliberately excludes drv_cat_atomic_input
    joins -- see its own SQL comment on GEQO threshold), so fetched
    per-symbol from the Rule Flow intermediates endpoint instead -- same
    data the Data Flow panel uses. 2026-08-25, user-directed: Trade column
    shows standard deviations above the Trade line, not a plain % diff."""
    if not tos_symbol:
        return None
    try:
        date_str = as_of_date.isoformat() if hasattr(as_of_date, "isoformat") else str(as_of_date)
        data = _get_json(f"/api/rule-flow/{urllib.parse.quote(str(tos_symbol))}/intermediates?date={date_str}")
        ac = data.get("AC")
        return float(ac) if ac is not None else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Build the three Trade Mode buckets from the live app
# ---------------------------------------------------------------------------

def build_trade_mode_export(strict: bool = True) -> dict:
    """Fetch the same data the browser fetches and apply the same Trade
    Mode filters. Returns {buys, sells, breaches, as_of_date} -- each a
    list of row dicts (buys sorted BUY_DIP-first, then by Tradability Score
    descending within each group). Raises on a network/API failure --
    caller (run()) is the one that swallows exceptions, so a failure here
    surfaces clearly to anyone calling this directly."""
    rows = _get_json("/api/actionable?show_suppressed=true")
    settings_ = _get_json("/api/actionable/settings")
    source_scorecard = _get_json("/api/actionable/source-scorecard")
    factor_rows = _get_json("/api/rules/factor-scorecard?min_n=30")
    factor_scorecard = {f"{r['factor']}|{r['bucket']}": r for r in factor_rows if r.get("factor")}

    rsi_overbought = float(settings_.get("rsi_overbought", 70))
    rsi_oversold = float(settings_.get("rsi_oversold", 30))
    rvol_threshold = float(settings_.get("vlm_rvol_avoid_threshold", 1.5))

    buys, sells, breaches = [], [], []
    for row in rows:
        if _is_qualifying_buy(row, strict, rsi_overbought, rsi_oversold, rvol_threshold,
                               factor_scorecard, source_scorecard):
            row["_tradability_score"] = _buy_tradability_score(
                row, rsi_overbought, rsi_oversold, rvol_threshold,
                factor_scorecard, source_scorecard)
            row["_ac"] = _get_ac_for_symbol(row.get("tos_symbol"), row.get("as_of_date"))
            buys.append(row)
        elif _is_held_sa_sell(row):
            sells.append(row)
        elif _is_stop_breach(row):
            breaches.append(row)

    # 2026-08-27 -- BUY_DIP (PVV's own dip-buy signal) sorted to the top,
    # then any other confirmed-bullish PVV decision (_PVV_BUY_SIDE), then
    # everyone else (NO_ACTION, no PVV read at all, or -- non-strict mode
    # only, Strict already excludes AVOID -- a leftover sell-tilted PVV
    # read on a row that still qualified as a buy via final_code). First
    # cut was a 2-tier (BUY_DIP vs not) key, sorted by score alone within
    # the "not" bucket -- that let a high-score NO_ACTION row rank ABOVE a
    # lower-score BUY_LRR row, i.e. an unconfirmed row outranking a
    # PVV-confirmed one. This 3-tier key fixes that: NO_ACTION now always
    # sorts below every PVV-confirmed buy, regardless of score. Ties within
    # each tier still broken by Tradability Score descending. User: "Bring
    # BUY_DIP stocks to the top in Buys." -> "NO ACTION ones are coming in
    # the middle."
    # 2026-10-28, user: within the same Final Call action, sort by Tradability Score descending (the PVV
    # grouping is gone -- PVV is already a +-3 term in the score). Action order: Buy More, Buy Some, Buy To Min.
    def _buy_sort_key(r):
        code = str(r.get("final_code") or "").upper()
        return ({"BM": 2, "BS": 1}.get(code, 0), r.get("_tradability_score", 0))
    buys.sort(key=_buy_sort_key, reverse=True)
    as_of_date = rows[0].get("as_of_date") if rows else None
    return {"buys": buys, "sells": sells, "breaches": breaches, "as_of_date": as_of_date}


# ---------------------------------------------------------------------------
# Email formatting
# ---------------------------------------------------------------------------

def _fmt(v, digits=2) -> str:
    if v is None:
        return "—"
    try:
        return f"{float(v):.{digits}f}"
    except (TypeError, ValueError):
        return html.escape(str(v))


def _fmt_trade_cell(row) -> str:
    """Trade line value + standard deviations above/below it in parens,
    e.g. "34.80(0.8SD)". 2026-08-25, user-directed: "instead display
    standard deviations above Trade" (not a plain % diff, unlike LRR).
    (last_price - trade_line_value) / AC -- AC fetched per-symbol, see
    _get_ac_for_symbol; row["_ac"] is set by build_trade_mode_export."""
    trade_val = row.get("trade_line_value")
    trade_str = _fmt(trade_val)
    last, ac = row.get("last_price"), row.get("_ac")
    if trade_val is None or last is None or not ac:
        return trade_str
    try:
        sd = (float(last) - float(trade_val)) / float(ac)
    except (TypeError, ValueError, ZeroDivisionError):
        return trade_str
    return f"{trade_str}({sd:.1f}SD)"


def _fmt_lrr_cell(row) -> str:
    """LRR value + risk-range position in parens, e.g. "50.00(22%)" means
    price sits 22% of the way from LRR to TRR. 2026-08-25, user-corrected:
    "LRR should have risk range % from bottom. price - LRR / (TRR-LRR)."
    -- reuses _raw_rr_pos (already ported from web/actionable.js for
    scoring) rather than a plain %-diff-from-LRR, which is what this
    showed before this fix."""
    lrr = row.get("lrr")
    lrr_str = _fmt(lrr)
    pos = _raw_rr_pos(row)
    if pos is None:
        return lrr_str
    return f"{lrr_str}({pos:.0f}%)"


def _row_html(sym, cells) -> str:
    tds = "".join(f'<td style="padding:4px 8px;border-bottom:1px solid #e5e7eb;">{c}</td>' for c in cells)
    return f'<tr><td style="padding:4px 8px;border-bottom:1px solid #e5e7eb;font-weight:600;">{html.escape(sym)}</td>{tds}</tr>'


def _section_html(title: str, header: list, rows: list) -> str:
    if not rows:
        return (f'<h3 style="margin:18px 0 4px;font-family:sans-serif;color:#111827;">{title}</h3>'
                f'<p style="margin:0 0 12px;font-family:sans-serif;color:#6b7280;font-size:13px;">None today.</p>')
    ths = "".join(f'<th style="text-align:left;padding:4px 8px;border-bottom:2px solid #d1d5db;">{h}</th>'
                  for h in header)
    body = "".join(rows)
    return (f'<h3 style="margin:18px 0 4px;font-family:sans-serif;color:#111827;">{title} ({len(rows)})</h3>'
            f'<table style="border-collapse:collapse;font-family:sans-serif;font-size:13px;width:100%;">'
            f'<thead><tr><th style="text-align:left;padding:4px 8px;border-bottom:2px solid #d1d5db;">Symbol</th>{ths}</tr></thead>'
            f'<tbody>{body}</tbody></table>')


def _build_email_html(export: dict) -> str:
    # 2026-08-25, user-directed: drop Score/Price columns, add Trade (the
    # stop-line reference, drv_actionable.trade_line_value -- part of a.*
    # in /api/actionable) and LRR; Source/Technical/Macro shortened to
    # Src/Tech/Mcr. Rows still SORT by Tradability Score (build_trade_mode_
    # export's buys.sort) -- only the displayed column is gone, not the
    # ranking behind it.
    buy_rows = [
        _row_html(r.get("tos_symbol", ""), [
            html.escape(str(r.get("winning_source") or "—")),
            html.escape(str(r.get("rr_action") or "—")),
            html.escape(str(r.get("macro_value") or "—")),
            _fmt_trade_cell(r),
            _fmt_lrr_cell(r),
        ])
        for r in export["buys"]
    ]
    sell_rows = [
        _row_html(r.get("tos_symbol", ""), [
            html.escape(str(r.get("winning_source") or "—")),
            html.escape(str(r.get("consolidated_action") or "—")),
            _fmt(r.get("last_price")),
        ])
        for r in export["sells"]
    ]
    breach_rows = [
        _row_html(r.get("tos_symbol", ""), [
            html.escape(str(r.get("consolidated_action") or "—")),
            _fmt(r.get("last_price")),
        ])
        for r in export["breaches"]
    ]
    as_of = export.get("as_of_date") or "—"
    parts = [
        f'<div style="font-family:sans-serif;">',
        f'<h2 style="margin:0 0 4px;color:#111827;">Trade Mode Export — {html.escape(str(as_of))}</h2>',
        f'<p style="margin:0 0 8px;color:#6b7280;font-size:13px;">Strict view, matches actionable.js Trade Mode + Strict on screen.</p>',
        _section_html("🟢 Qualifying Buys", ["Src", "Tech", "Mcr", "Trade", "LRR"], buy_rows),
        _section_html("🔴 Held SA Sells", ["Source", "Action", "Price"], sell_rows),
        _section_html("⛔ Stop Breaches", ["Action", "Price"], breach_rows),
        "</div>",
    ]
    return "".join(parts)


def _build_email_plain(export: dict) -> str:
    lines = [f"Trade Mode Export — {export.get('as_of_date') or '—'}", ""]
    lines.append(f"Qualifying Buys ({len(export['buys'])}):")
    lines += [f"  {r.get('tos_symbol')}  score={_fmt(r.get('_tradability_score'), 0)}"
              for r in export["buys"]] or ["  None today."]
    lines.append("")
    lines.append(f"Held SA Sells ({len(export['sells'])}):")
    lines += [f"  {r.get('tos_symbol')}" for r in export["sells"]] or ["  None today."]
    lines.append("")
    lines.append(f"Stop Breaches ({len(export['breaches'])}):")
    lines += [f"  {r.get('tos_symbol')}" for r in export["breaches"]] or ["  None today."]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point -- called from etl/scheduler.py's nightly job
# ---------------------------------------------------------------------------

def _todays_tosd_loaded() -> bool:
    """True if today's TOSD export has actually landed -- i.e. the derive
    anchor (MAX(export_date) FROM hist_td, see docs/derive_date_logic.md)
    equals today's calendar date. Only enforced on weekdays: TOSD never
    lands on a weekend, so a weekend/holiday run is expected to reuse the
    last real trading day's anchor, same as every other anchor-date
    consumer in this system -- that's not "unprocessed," it's normal.
    2026-08-25, user-directed: "does it stop if all files are not
    processed (like TOS exports etc.)" -- it didn't; this makes it does,
    for the trade mode export specifically (not the rest of the nightly
    job, which is anchor-agnostic by design)."""
    from datetime import date
    today = date.today()
    if today.weekday() >= 5:  # Sat/Sun -- no TOSD expected, anchor lag is normal
        return True
    from etl.db import session_scope
    from etl.derive import get_anchor_date
    with session_scope() as s:
        anchor = get_anchor_date(s)
    return anchor == today


def run() -> Optional[dict]:
    """Best-effort: builds the export and emails it. Returns the export
    dict on success, None if skipped (email disabled, today's TOSD export
    hasn't loaded yet) or on any failure -- never raises, so the nightly
    job's other steps are unaffected."""
    if not settings.notify_email:
        log.debug("trade mode export skipped -- NOTIFY_EMAIL is off")
        return None
    if not _todays_tosd_loaded():
        log.warning("trade mode export skipped -- today's TOSD export hasn't loaded yet "
                    "(derive anchor is still yesterday's date or earlier)")
        return None
    try:
        export = build_trade_mode_export(strict=True)
        from etl.notify import send_email
        subject = (f"Trade Mode — {export.get('as_of_date') or ''}: "
                   f"{len(export['buys'])} buy(s), {len(export['sells'])} sell(s), "
                   f"{len(export['breaches'])} breach(es)")
        ok = send_email(subject, _build_email_plain(export), _build_email_html(export))
        log.info("trade mode export: sent=%s buys=%d sells=%d breaches=%d",
                  ok, len(export["buys"]), len(export["sells"]), len(export["breaches"]))
        return export
    except Exception:
        log.exception("trade mode export failed")
        return None


if __name__ == "__main__":
    from etl._logging import setup_logging
    setup_logging()
    print(run())
