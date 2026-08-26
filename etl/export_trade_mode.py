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
option -- not an oversight. If you change any of the following in
web/actionable.js, mirror the change here too:
  _isTradeModeQualifyingBuy / _isTradeModeHeldSaSell / _isTradeModeStopBreach
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
# _TRADABILITY_BADGE_MIN exactly -- see module docstring.
_ENTRY_RIPE_TECH = ("BS", "BM", "BMN")
_TECH_GATE_EXEMPT_SRC = ("RTA", "SSSCHG", "TOP5")
_MACRO_BUY = {"BM", "BS"}
_MACRO_SELL = {"STM", "SA"}
_SRC_BUY = {"ADD", "INCREASE"}
_SRC_SELL = {"REDUCE", "REMOVE"}
_TECH_SELL = {"SA", "STM", "SS", "SO"}
_TRADABILITY_BADGE_MIN = 12


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
    base = max(0, 1 - raw_pos / 40)
    return base * (1 if turning_up else 0.7)


def _source_track_record_score(row, source_scorecard, factor_scorecard):
    src = str(row.get("winning_source") or "").upper()
    sc = (source_scorecard.get(src) or {}).get("buy")
    base = factor_scorecard.get("Baseline|All stocks")
    if (not sc or sc.get("win_rate_20d") is None or (sc.get("n") or 0) < 5
            or not base or base.get("win_rate") is None):
        return 0
    delta = (float(sc["win_rate_20d"]) - float(base["win_rate"])) * 100
    return max(-3, min(6, delta))


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
    tech = str(row.get("rr_action") or "").upper()
    tech_pts = 1 if tech in _ENTRY_RIPE_TECH else 0
    lrr_pts = _lrr_proximity_score(row)
    rsi_delta = _factor_win_rate_delta(
        factor_scorecard, "RSI", _rsi_bucket(row.get("rsi"), rsi_overbought, rsi_oversold))
    rvol_delta = _factor_win_rate_delta(
        factor_scorecard, "RVOL + direction",
        _rvol_bucket(row.get("rvol"), row.get("pct_change"), rvol_threshold))

    def clamp(v):
        return 0 if v is None else max(-3, min(6, v))

    factor_pts = (clamp(rsi_delta) + _iv_ratio_score(row.get("iv_ratio")) + clamp(rvol_delta)
                  + _source_track_record_score(row, source_scorecard, factor_scorecard))
    secondary_pts = max(-6, min(8, tech_pts * 2 + factor_pts))
    agreement_pts = _buy_agreement_sub_tier(row) * 3
    return lrr_pts * 10 + secondary_pts + agreement_pts


def _is_true(v) -> bool:
    return v is True or v == "true"


def _is_qualifying_buy(row, strict, rsi_overbought, rsi_oversold, rvol_threshold,
                        factor_scorecard, source_scorecard):
    code = str(row.get("final_code") or "").upper()
    if code not in ("BM", "BMN"):
        return False
    if not _is_true(row.get("fc_feasible")):
        return False
    src = str(row.get("winning_source") or "").upper()
    tech = str(row.get("rr_action") or "").upper()
    if src not in _TECH_GATE_EXEMPT_SRC and tech not in _ENTRY_RIPE_TECH:
        return False
    if row.get("stop_breached"):
        return False
    mv = str(row.get("macro_value") or "").upper()
    if mv in ("SA", "STM"):
        return False
    if strict:
        if _is_true(row.get("is_macro_instrument")):
            return False
        score = _buy_tradability_score(row, rsi_overbought, rsi_oversold, rvol_threshold,
                                        factor_scorecard, source_scorecard)
        if score < _TRADABILITY_BADGE_MIN:
            return False
    return True


def _is_held_sa_sell(row) -> bool:
    return bool(row.get("held_today")) and str(row.get("final_code") or "").upper() == "SA"


def _is_stop_breach(row) -> bool:
    return bool(row.get("held_today")) and bool(row.get("stop_breached"))


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
    list of row dicts (buys sorted by Tradability Score, descending, same
    ranking the on-screen Strict view uses). Raises on a network/API
    failure -- caller (run()) is the one that swallows exceptions, so a
    failure here surfaces clearly to anyone calling this directly."""
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

    buys.sort(key=lambda r: r.get("_tradability_score", 0), reverse=True)
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
