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
  _MACRO_BUY/_MACRO_SELL/_SRC_BUY/_SRC_SELL/_TECH_SELL/_ENTRY_RIPE_TECH/
  _TECH_GATE_EXEMPT_SRC
  (The Tradability Score and its helpers were removed 2026-11-08.)

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
# _PVV_BUY_SIDE exactly -- see module docstring.
_ENTRY_RIPE_TECH = ("BS", "BM", "BMN")
_TECH_GATE_EXEMPT_SRC = ("RTA",)  # SSSCHG/TOP5 lost this exemption 2026-09-12
_MACRO_BUY = {"BM", "BS"}
_MACRO_SELL = {"STM", "SA"}
_SRC_BUY = {"ADD", "INCREASE"}
_SRC_SELL = {"REDUCE", "REMOVE"}
_TECH_SELL = {"SA", "STM", "SS", "SO"}
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





def _raw_rr_pos(row):
    lrr, trr, last = row.get("lrr"), row.get("trr"), row.get("last_price")
    if lrr is None or trr is None or last is None:
        return None
    lrr, trr, last = float(lrr), float(trr), float(last)
    if trr == lrr:
        return None
    return (last - lrr) / (trr - lrr) * 100




def _as_list(v):
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except ValueError:
            return []
    return v if isinstance(v, list) else []









def _is_true(v) -> bool:
    return v is True or v == "true"


def _is_qualifying_buy(row, strict):
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
        # 2026-11-08 (Spec 12 B4): the PVV AVOID veto is gone, same as web/actionable.js.
        # 2026-10-28, user: every Buy To Min (BMN) moves to Trade2 -- Trade keeps Buy More and Buy Some only.
        # (The "BMN only above the Trade line" test stays removed.) Mirrors web/actionable.js.
        # 2026-10-29, user: except a Buy To Min that PVV or the Tradability icon positively flags as a buy (stays in Trade; PVV AVOID was
        # rejected above). LIVE is not part of the nightly job (it needs the intraday live check), so only the screen applies that part.
        if code == "BMN":
            # 2026-11-08 (Spec 12 B1): the Tradability icon leg is gone -- only a PVV buy rescues a Buy To Min here.
            if str(row.get("pvv_decision") or "").upper() not in _PVV_BUY_SIDE:
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
    list of row dicts (buys sorted Buy More, Buy Some, Buy To Min, then symbol A-Z). Raises on a network/API failure --
    caller (run()) is the one that swallows exceptions, so a failure here
    surfaces clearly to anyone calling this directly."""
    rows = _get_json("/api/actionable?show_suppressed=true")

    buys, sells, breaches = [], [], []
    for row in rows:
        if _is_qualifying_buy(row, strict):
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
        return {"BM": 2, "BS": 1}.get(code, 0)
    # 2026-11-08 (Spec 12 B1/B4): no score, no PVV boost -- Buy More, Buy Some, Buy To Min; symbol A-Z inside each.
    buys.sort(key=lambda r: str(r.get("tos_symbol") or ""))
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
    lines += [f"  {r.get('tos_symbol')}"
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
