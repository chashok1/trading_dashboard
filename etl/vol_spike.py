"""IV / HV spike detector (the user's TOS A_IV_Spikes / A_HV_Spike studies) -> drv_vol_spike.

One row per (as_of_date, tos_symbol): where each volatility series stands in the study (spiked / normalized, ratio, days since
the last arrow), plus a "stress" flag (IV spike while the price is falling). Informational: it annotates the Actionable grid and
feeds the factor scorecard; it never changes consolidated_action / the Final Call.

The study logic is a line-for-line translation of the user's thinkscript (see spike_series). It is causal (each day only uses
that day and earlier), so one pass over a symbol's history gives the correct as-of value for every past day -- backfill() uses
that. Alerts (derive only, never backfill): a HELD symbol with a fresh IV spike or fresh stress gets an auto-created, already
triggered ref_watch row, which the existing Watch email digest picks up.

Run:  python -m etl.vol_spike [--date YYYY-MM-DD]          # derive one date (default: latest anchor), no alerts
      python -m etl.vol_spike --backfill 2026-03-01        # (re)build history from that date, no alerts
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from etl._derive_common import _wrap  # noqa: E402

log = logging.getLogger("etl.vol_spike")

# Tunables. The study inputs are the user's own (A_IV_Spikes(63, 1.15, 1, 4, 5); A_HV_Spike(63, 1.15, 0.95, 3, 5)).
VOL_SPIKE_CONFIG = {
    "length": 63, "spike_thr": 1.15, "exclude": 5,
    "iv_normal_thr": 1.0, "iv_smooth": 4,
    "hv_normal_thr": 0.95, "hv_smooth": 3,
    "stress_px_days": 5,          # price change window for "falling"
    "stress_px_drop_pct": -3.0,   # <= this % over the window counts as falling
    "stress_recent_event_days": 5,  # a fresh IV spike arrow this many trading days old still counts as "spiked"
    "history_days": 260,          # calendar days of history fetched per symbol (needs ~75 trading days of warm-up)
}


# ── The study (pure, unit-tested) ────────────────────────────────────────────────────────────────────────────────────
def _mean_full(xs, n):
    """Mean of the last n values; None unless the window is full and has no gaps (thinkscript Average over NaN data)."""
    w = xs[-n:]
    return sum(w) / n if len(w) == n and None not in w else None


def spike_series(vals, length=63, spike_thr=1.15, normal_thr=1.0, smooth_len=4, exclude=5):
    """The user's TOS "Implied Volatility Spike & Normalization Detector", translated line for line:
      ivSmooth = Average(v, smoothLen); avgExcl = Average(ivSmooth[excludeDays], length); avgNormal = Average(ivSmooth, length)
      spike = preSpikeRatio[1] <= spikeThr and preSpikeRatio > spikeThr   (preSpikeRatio = ivSmooth / avgExcl)
      wasSpiked: set by a spike, cleared when ivSmooth / avgNormal crosses below normalThr
      avgIV = avgNormal while wasSpiked else avgExcl;  ratio = ivSmooth / avgIV
      normalize = wasSpiked[1] and ratio[1] >= normalThr and ratio < normalThr
    Plots: grey = ivSmooth, white dashed = avgIV * normalThr, red dashed = avgIV * spikeThr, up/down arrows at ivSmooth.
    Returns dict of equal-length lists: sm, white, red, ratio, mk ('up'|'down'|None), was (bool)."""
    n = len(vals)
    sm = [_mean_full(vals[:i + 1], smooth_len) for i in range(n)]
    avg_norm = [_mean_full(sm[:i + 1], length) for i in range(n)]
    avg_excl = [avg_norm[i - exclude] if i >= exclude else None for i in range(n)]
    pre = [sm[i] / avg_excl[i] if sm[i] is not None and avg_excl[i] else None for i in range(n)]
    nrm = [sm[i] / avg_norm[i] if sm[i] is not None and avg_norm[i] else None for i in range(n)]
    was, ratio_prev = False, None
    out = {"sm": sm, "white": [], "red": [], "ratio": [], "mk": [], "was": []}
    for i in range(n):
        spike = i > 0 and pre[i - 1] is not None and pre[i] is not None and pre[i - 1] <= spike_thr < pre[i]
        cross_dn = i > 0 and nrm[i - 1] is not None and nrm[i] is not None and nrm[i - 1] >= normal_thr > nrm[i]
        was_prev = was
        was = True if spike else (False if cross_dn else was)
        a = avg_norm[i] if was else avg_excl[i]
        out["white"].append(a * normal_thr if a is not None else None)
        out["red"].append(a * spike_thr if a is not None else None)
        r = sm[i] / a if sm[i] is not None and a else None
        out["ratio"].append(r)
        normalize = was_prev and ratio_prev is not None and r is not None and ratio_prev >= normal_thr > r
        out["mk"].append("up" if spike else "down" if normalize else None)
        out["was"].append(was)
        ratio_prev = r
    return out


def spike_study(vals, length=63, spike_thr=1.15, normal_thr=1.0, smooth_len=4, exclude=5):
    """spike_series as the (smoothed, white, red, ratio, markers) tuple the Action popup uses."""
    s = spike_series(vals, length, spike_thr, normal_thr, smooth_len, exclude)
    return s["sm"], s["white"], s["red"], s["ratio"], s["mk"]


def _carry_forward(vals):
    """A day missing from the TOS export carries the previous value forward (the 63-day averages need gap-free data)."""
    out, last = [], None
    for v in vals:
        last = v if v is not None else last
        out.append(last)
    return out


def _last_event(mk, i):
    """(kind, trading days ago) of the most recent arrow at or before index i, else (None, None)."""
    for j in range(i, -1, -1):
        if mk[j]:
            return mk[j], i - j
    return None, None


def is_stress(was, last_up_ago, px_chg_pct, cfg=VOL_SPIKE_CONFIG):
    """IV spike (still active, or a fresh arrow within a few days) while the price is falling."""
    spiked = bool(was) or (last_up_ago is not None and last_up_ago <= cfg["stress_recent_event_days"])
    return bool(spiked and px_chg_pct is not None and px_chg_pct <= cfg["stress_px_drop_pct"])


def build_rows(dates, prices, ivs, hvs, cfg=VOL_SPIKE_CONFIG):
    """One output dict per date for ONE symbol (inputs ascending, equal length). Pure."""
    px = _carry_forward(prices)
    iv = _carry_forward(ivs)
    hv = _carry_forward(hvs)
    s_iv = spike_series(iv, cfg["length"], cfg["spike_thr"], cfg["iv_normal_thr"], cfg["iv_smooth"], cfg["exclude"])
    s_hv = spike_series(hv, cfg["length"], cfg["spike_thr"], cfg["hv_normal_thr"], cfg["hv_smooth"], cfg["exclude"])
    k = cfg["stress_px_days"]
    rows = []
    for i, d in enumerate(dates):
        ev_iv = _last_event([m if m == "up" else None for m in s_iv["mk"]], i)     # last SPIKE arrow
        ev_hv = _last_event([m if m == "up" else None for m in s_hv["mk"]], i)
        nm_iv = _last_event([m if m == "down" else None for m in s_iv["mk"]], i)   # last NORMALIZED arrow
        chg = (px[i] / px[i - k] - 1.0) * 100.0 if i >= k and px[i] and px[i - k] else None
        rows.append({
            "as_of_date": d, "iv": iv[i], "iv_ratio": s_iv["ratio"][i], "iv_spiked": s_iv["was"][i],
            "iv_event": s_iv["mk"][i], "iv_spike_days_ago": ev_iv[1], "iv_norm_days_ago": nm_iv[1],
            "hv": hv[i], "hv_ratio": s_hv["ratio"][i], "hv_spiked": s_hv["was"][i], "hv_event": s_hv["mk"][i],
            "hv_spike_days_ago": ev_hv[1],
            "px_chg_5d": chg, "stress": is_stress(s_iv["was"][i], ev_iv[1], chg, cfg),
        })
    return rows


# ── Data access ──────────────────────────────────────────────────────────────────────────────────────────────────────
def _fetch_series(session: Session, symbols: list, start: date, end: date) -> dict:
    """{tos_symbol: [(export_date, last_price, imp_volatility, historical_vol), ...]} ascending, one row per day (last sequence)."""
    if not symbols:
        return {}
    rows = session.execute(text("""
        SELECT tos_symbol, export_date, last_price, imp_volatility, historical_vol
          FROM (SELECT tos_symbol, export_date, last_price, imp_volatility, historical_vol,
                       ROW_NUMBER() OVER (PARTITION BY tos_symbol, export_date ORDER BY sequence DESC) AS rn
                  FROM hist_td
                 WHERE export_date BETWEEN :s AND :e AND tos_symbol = ANY(:syms)) x
         WHERE rn = 1 ORDER BY tos_symbol, export_date
    """), {"s": start, "e": end, "syms": symbols}).fetchall()
    out: dict = {}
    for sym, d, lp, iv, hv in rows:
        out.setdefault(sym, []).append((d, _f(lp), _f(iv), _f(hv)))
    return out


def _f(v):
    return float(v) if v is not None else None


_COLS = ("as_of_date", "tos_symbol", "iv", "iv_ratio", "iv_spiked", "iv_event", "iv_spike_days_ago", "iv_norm_days_ago",
         "hv", "hv_ratio", "hv_spiked", "hv_event", "hv_spike_days_ago", "px_chg_5d", "stress")
_INSERT = text(f"INSERT INTO drv_vol_spike ({', '.join(_COLS)}) VALUES ({', '.join(':' + c for c in _COLS)})")


def _symbol_rows(session, symbols, start, end, keep_from, keep_to, cfg):
    """Build output rows for dates in [keep_from, keep_to] (history before keep_from is only warm-up)."""
    data = _fetch_series(session, symbols, start, end)
    out = []
    for sym, pts in data.items():
        rows = build_rows([p[0] for p in pts], [p[1] for p in pts], [p[2] for p in pts], [p[3] for p in pts], cfg)
        for r in rows:
            if keep_from <= r["as_of_date"] <= keep_to:
                r["tos_symbol"] = sym
                out.append(r)
    return out


def _write(session, rows, d_from, d_to):
    session.execute(text("DELETE FROM drv_vol_spike WHERE as_of_date BETWEEN :a AND :b"), {"a": d_from, "b": d_to})
    for i in range(0, len(rows), 2000):
        session.execute(_INSERT, rows[i:i + 2000])
    return len(rows)


# ── Alerts: held symbol + fresh IV spike / fresh stress -> triggered ref_watch row (the Watch email digest picks it up) ──
def _alert_for(row, prev_stress):
    """(note, reason) when this day deserves an alert, else None. Pure."""
    d = row["as_of_date"]
    if row["stress"] and not prev_stress:
        return (f"Auto: IV stress {d}",
                f"IV spike while price fell {abs(row['px_chg_5d'] or 0):.1f}% in {VOL_SPIKE_CONFIG['stress_px_days']} days "
                f"(IV ratio {row['iv_ratio']:.2f})" if row["iv_ratio"] is not None else "IV spike while price fell")
    if row["iv_event"] == "up":
        return (f"Auto: IV spike {d}", f"IV spiked (ratio {row['iv_ratio']:.2f})" if row["iv_ratio"] is not None else "IV spiked")
    return None


def _create_watch_alerts(session: Session, as_of_date: date, today_rows: dict, prev_stress: dict, price: dict) -> int:
    from etl.derive_outlook_action import _load_holdings
    held = _load_holdings(session, as_of_date)
    n = 0
    for sym in sorted(held & today_rows.keys()):
        alert = _alert_for(today_rows[sym], prev_stress.get(sym, False))
        if not alert:
            continue
        note, reason = alert
        if session.execute(text("SELECT 1 FROM ref_watch WHERE tos_symbol = :s AND (note = :n OR status = 'ACTIVE') LIMIT 1"),
                           {"s": sym, "n": note}).first():
            continue        # already alerted for this event, or the user has their own live watch on it (left untouched)
        session.execute(text("""
            INSERT INTO ref_watch (tos_symbol, note, baseline_price, status, triggered_at, triggered_reason)
            VALUES (:s, :n, :p, 'ACTIVE', now(), :r)
        """), {"s": sym, "n": note, "p": price.get(sym), "r": reason})
        n += 1
    if n:
        log.info("vol_spike: %d watch alert(s) created for held symbols", n)
    return n


# ── Entry points ─────────────────────────────────────────────────────────────────────────────────────────────────────
def _derive_vol_spike_impl(session: Session, as_of_date: date, run_id: int, alerts: bool = True) -> int:
    cfg = VOL_SPIKE_CONFIG
    universe = [r[0] for r in session.execute(
        text("SELECT tos_symbol FROM drv_symbols WHERE as_of_date = :d"), {"d": as_of_date}).fetchall()]
    start = as_of_date - timedelta(days=cfg["history_days"])
    # keep yesterday too (for "fresh stress" detection); only today's rows are written.
    rows = _symbol_rows(session, universe, start, as_of_date, as_of_date - timedelta(days=10), as_of_date, cfg)
    today = {r["tos_symbol"]: r for r in rows if r["as_of_date"] == as_of_date}
    prev = {}
    for r in sorted((r for r in rows if r["as_of_date"] < as_of_date), key=lambda r: r["as_of_date"]):
        prev[r["tos_symbol"]] = r["stress"]
    n = _write(session, list(today.values()), as_of_date, as_of_date)
    # Alerts only for the live anchor day -- re-deriving an older date must never raise them.
    anchor = session.execute(text("SELECT MAX(export_date) FROM hist_td")).scalar()
    if alerts and today and as_of_date == anchor:
        px = {s: _f(v) for s, v in session.execute(text(
            "SELECT tos_symbol, last_price FROM drv_quote WHERE as_of_date = :d"), {"d": as_of_date}).fetchall()}
        _create_watch_alerts(session, as_of_date, today, prev, px)
    return n


derive_vol_spike = _wrap("drv_vol_spike", _derive_vol_spike_impl)


def backfill(session: Session, start: date, end: Optional[date] = None) -> int:
    """Rebuild drv_vol_spike for [start, end] for every symbol that has hist_td data. No alerts."""
    cfg = VOL_SPIKE_CONFIG
    end = end or session.execute(text("SELECT MAX(export_date) FROM hist_td")).scalar()
    syms = [r[0] for r in session.execute(text(
        "SELECT DISTINCT tos_symbol FROM hist_td WHERE export_date BETWEEN :s AND :e AND tos_symbol IS NOT NULL"),
        {"s": start - timedelta(days=cfg["history_days"]), "e": end}).fetchall()]
    rows = _symbol_rows(session, syms, start - timedelta(days=cfg["history_days"]), end, start, end, cfg)
    n = _write(session, rows, start, end)
    log.info("vol_spike backfill %s..%s: %d rows, %d symbols", start, end, n, len(syms))
    return n


def main() -> int:
    from etl._logging import setup_logging
    from etl.db import session_scope
    setup_logging()
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--date", help="derive this date (default: latest anchor); no alerts")
    p.add_argument("--backfill", metavar="START", help="rebuild history from START (YYYY-MM-DD); no alerts")
    a = p.parse_args()
    with session_scope() as s:
        if a.backfill:
            backfill(s, date.fromisoformat(a.backfill))
        else:
            d = date.fromisoformat(a.date) if a.date else s.execute(text("SELECT MAX(export_date) FROM hist_td")).scalar()
            from etl._derive_common import _open_drv_run, _close_drv_run
            rid = _open_drv_run(s, "drv_vol_spike", d, None)
            n = _derive_vol_spike_impl(s, d, rid, alerts=False)
            _close_drv_run(s, rid, rows_built=n)
            log.info("drv_vol_spike @ %s: %d rows", d, n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
