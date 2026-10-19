"""Quad market check (design: DESIGN_SPEC_8.md; Hedgeye Early Look 2026-10-19).

Two meters -- GROWTH and INFLATION, each -100..+100 -- are built from the market factors in ref_quad_factor. A Quad is just two
arrows (growth up/down, inflation up/down), so the meters say which Quad the DATA points to, independent of Hedgeye's declared Quad:
    Quad 1 = growth up, inflation down      Quad 2 = up, up
    Quad 3 = growth down, inflation up      Quad 4 = down, down
Compared with the dashboard's own 60-day Quad (etl.derive_risk_dial._dominant_quad) the meters also give a transition risk 0-100, a
label (HOLDING / WATCH / TRANSITION) and the Quad the market is leaning toward. A fit per Quad (the four small bars) is indicative.

Outputs (idempotent: DELETE WHERE as_of_date = D, then INSERT): drv_quad_factor (one row per factor), drv_quad_check (one row).
Advisory only -- nothing here touches consolidated_action / trig_action. tos_symbol throughout (hist_td / drv_rr / drv_technicals).
Every band / weight is a GUESS and lives in ref_quad_factor / ref_settings so it can be tuned without code changes.
"""
from __future__ import annotations

import json
import logging
import math
from datetime import date, timedelta
from typing import Optional

from dateutil.relativedelta import relativedelta
from sqlalchemy import text
from sqlalchemy.orm import Session

log = logging.getLogger("etl.derive_quad_check")

WARN_CODE = "QUAD_CHECK_STALE"
G_EXP = {1: 1, 2: 1, 3: -1, 4: -1}     # expected growth sign per Quad
I_EXP = {1: -1, 2: 1, 3: 1, 4: -1}     # expected inflation sign per Quad
QUAD_OF = {(1, -1): 1, (1, 1): 2, (-1, 1): 3, (-1, -1): 4}   # (growth sign, inflation sign) -> Quad


# --------------------------------------------------------------------------- settings
def _setting(session: Session, name: str, default: float) -> float:
    try:
        v = session.execute(text("SELECT setting_value FROM ref_settings WHERE setting_name = :n"), {"n": name}).scalar()
        return float(v) if v is not None else default
    except Exception:
        return default


# --------------------------------------------------------------------------- pure helpers (unit-testable)
def sign_by_band(move: Optional[float], band: Optional[float]) -> Optional[int]:
    """+1 / -1 when the move is beyond the flat band, 0 inside it, None when there is no move."""
    if move is None or band is None:
        return None
    return 1 if move > band else (-1 if move < -band else 0)


def factor_state(checks: list, min_checks: int) -> Optional[int]:
    """checks: list of +1/0/-1/None (already direction-adjusted). Up when at least 2 checks agree up (1 for a single-check factor),
    down likewise, else mixed (0). Fewer than min_checks available -> None (the factor does not vote)."""
    got = [c for c in checks if c is not None]
    if len(got) < max(1, min_checks):
        return None
    need = 1 if min_checks <= 1 else 2
    ups = sum(1 for c in got if c > 0)
    downs = sum(1 for c in got if c < 0)
    if ups >= need and ups > downs:
        return 1
    if downs >= need and downs > ups:
        return -1
    return 0


def meter(rows: list, min_cov: float):
    """rows: [(state, weight)]. Returns (score -100..100 | None, coverage 0..1)."""
    total_w = sum(w for _, w in rows if w and w > 0)
    voted = [(s, w) for s, w in rows if s is not None and w and w > 0]
    if total_w <= 0 or not voted:
        return None, 0.0
    vw = sum(w for _, w in voted)
    cov = vw / total_w
    if cov < min_cov:
        return None, cov
    return round(sum(s * w for s, w in voted) / vw * 100), cov


def read_vs(expected_sign: int, score: Optional[float], band: float) -> Optional[str]:
    """with / unclear / against the Quad's expected arrow."""
    if score is None:
        return None
    v = expected_sign * score
    return "with" if v >= band else ("against" if v <= -band else "unclear")


def transition_risk(ref_quad: int, g: float, i: float) -> float:
    bg = (100 - G_EXP[ref_quad] * g) / 2.0
    bi = (100 - I_EXP[ref_quad] * i) / 2.0
    return round(max(bg, bi), 1)


def label_of(risk: Optional[float]) -> str:
    if risk is None:
        return "NO_DATA"
    return "HOLDING" if risk < 40 else ("WATCH" if risk < 60 else "TRANSITION")


def target_quad(ref_quad: int, g_read: str, i_read: str) -> int:
    """Flip every meter that is not 'with' the reference Quad."""
    gs = G_EXP[ref_quad] if g_read == "with" else -G_EXP[ref_quad]
    is_ = I_EXP[ref_quad] if i_read == "with" else -I_EXP[ref_quad]
    return QUAD_OF[(gs, is_)]


def market_quads(g: float, i: float, band: float) -> list:
    """The market's own read: one Quad when both meters are clear, two when one is unclear, four when both are."""
    gs = [1 if g > 0 else -1] if abs(g) >= band else [1, -1]
    is_ = [1 if i > 0 else -1] if abs(i) >= band else [1, -1]
    return sorted({QUAD_OF[(a, b)] for a in gs for b in is_})


def quad_fit(g: float, i: float, scale: float) -> dict:
    """Indicative fit per Quad (sums to 100): probability each arrow is up, then the four combinations."""
    def up(x):
        return 1.0 / (1.0 + math.exp(-x / max(scale, 1.0)))
    pg, pi_ = up(g), up(i)
    raw = {1: pg * (1 - pi_), 2: pg * pi_, 3: (1 - pg) * pi_, 4: (1 - pg) * (1 - pi_)}
    return {str(k): round(v * 100) for k, v in raw.items()}


# --------------------------------------------------------------------------- data access
class _Prices:
    """EOD closes (hist_td, max sequence per day) and FRED series, as-of lookups."""

    def __init__(self, session: Session, d: date, syms: list, fred: list):
        lo = d - relativedelta(months=3) - timedelta(days=40)
        self.px: dict = {}
        asked = list(syms)
        syms = asked + ["$" + x for x in asked if not x.startswith("$")]   # TOS may export an index with or without the $ prefix
        for r in session.execute(text("""
            SELECT DISTINCT ON (tos_symbol, export_date) tos_symbol, export_date, last_price
              FROM hist_td
             WHERE export_date BETWEEN :lo AND :d AND last_price IS NOT NULL AND tos_symbol = ANY(:s)
             ORDER BY tos_symbol, export_date, sequence DESC"""), {"lo": lo, "d": d, "s": syms}).all():
            self.px.setdefault(r[0], []).append((r[1], float(r[2])))
        for x in asked:
            if x not in self.px and ("$" + x) in self.px:
                self.px[x] = self.px[("$" + x)]
        self.fred: dict = {}
        lo_f = d - relativedelta(months=6)
        for r in session.execute(text("""
            SELECT series_id, obs_date, value FROM hist_macro
             WHERE series_id = ANY(:s) AND obs_date BETWEEN :lo AND :d AND value IS NOT NULL
             ORDER BY series_id, obs_date"""), {"s": fred, "lo": lo_f, "d": d}).all():
            self.fred.setdefault(r[0], []).append((r[1], float(r[2])))

    @staticmethod
    def _asof(series: list, target: date):
        out = None
        for dte, v in series:
            if dte <= target:
                out = (dte, v)
            else:
                break
        return out

    def px_now(self, sym):
        s = self.px.get(sym)
        return (s[-1] if s else None)

    def px_at(self, sym, target):
        return self._asof(self.px.get(sym, []), target)

    def f_at(self, sid, target):
        return self._asof(self.fred.get(sid, []), target)


def _ret(p: _Prices, sym: str, d: date, tgt: date) -> Optional[float]:
    now, base = p.px_now(sym), p.px_at(sym, tgt)
    if not now or not base or not base[1] or base[0] >= now[0]:
        return None
    return (now[1] / base[1] - 1.0) * 100.0


def _mean(vals: list) -> Optional[float]:
    v = [x for x in vals if x is not None]
    return sum(v) / len(v) if v else None


def _outlook_sign(o) -> Optional[int]:
    if not o:
        return None
    o = str(o).upper()
    return 1 if "BULL" in o else (-1 if "BEAR" in o else 0)


# --------------------------------------------------------------------------- main
def _derive_quad_check_impl(session: Session, d: date) -> int:
    band = _setting(session, "quad_check_unclear_band", 20.0)
    min_cov = _setting(session, "quad_check_min_coverage", 0.6)
    confirm = int(_setting(session, "quad_check_confirm_days", 2))
    fit_scale = _setting(session, "quad_check_fit_scale", 40.0)

    factors = session.execute(text("SELECT * FROM ref_quad_factor WHERE enabled ORDER BY sort_order")).mappings().all()
    if not factors:
        return 0

    price_syms, fred_ids = set(), set()
    for f in factors:
        names = [x.strip() for x in (f["symbols"] or "").split(",") if x.strip()] + \
                [x.strip() for x in (f["minus_symbols"] or "").split(",") if x.strip()]
        for n in names:
            (fred_ids if f["kind"] in ("fred_change", "claims") else price_syms).add(n)
        if f["trend_source"] == "technicals" and f["trend_symbol"]:
            price_syms.add(f["trend_symbol"])
    p = _Prices(session, d, sorted(price_syms), sorted(fred_ids))

    rr = {r["tos_symbol"]: r for r in session.execute(text(
        "SELECT tos_symbol, outlook, lrr, trr FROM drv_rr WHERE as_of_date = :d"), {"d": d}).mappings().all()}
    prev_d = session.execute(text("SELECT MAX(as_of_date) FROM drv_rr WHERE as_of_date < :d"), {"d": d}).scalar()
    rr_prev = {r["tos_symbol"]: r for r in session.execute(text(
        "SELECT tos_symbol, lrr, trr FROM drv_rr WHERE as_of_date = :p"), {"p": prev_d}).mappings().all()} if prev_d else {}
    tech = {r["tos_symbol"]: r for r in session.execute(text(
        "SELECT tos_symbol, last_price, a_trend_value FROM drv_technicals WHERE as_of_date = :d"), {"d": d}).mappings().all()}

    t3w, t3m = d - timedelta(days=21), d - relativedelta(months=3)
    rows, stale = [], []
    for f in factors:
        kind = f["kind"]
        syms = [x.strip() for x in (f["symbols"] or "").split(",") if x.strip()]
        minus = [x.strip() for x in (f["minus_symbols"] or "").split(",") if x.strip()]
        r3w = r3m = None
        stale_since = None
        note = None
        checks = []
        dirn, tdir = int(f["direction"]), int(f["trend_direction"])

        if kind in ("price", "basket", "relative"):
            def one(tgt):
                if kind == "price":
                    return _ret(p, syms[0], d, tgt)
                if kind == "basket":
                    return _mean([_ret(p, s, d, tgt) for s in syms])
                a, b = _mean([_ret(p, s, d, tgt) for s in syms]), _mean([_ret(p, s, d, tgt) for s in minus])
                return None if a is None or b is None else a - b
            r3w, r3m = one(t3w), one(t3m)
            latest = max([p.px_now(s)[0] for s in syms + minus if p.px_now(s)], default=None)
            if latest is None or (d - latest).days > 5:
                stale_since = latest
        elif kind == "fred_change":
            sid = syms[0]
            now = p.f_at(sid, d)
            def chg(tgt):
                base = p.f_at(sid, tgt)
                return None if not now or not base or base[0] >= now[0] else (now[1] - base[1]) * 100.0   # % points -> bp
            r3w, r3m = chg(t3w), chg(t3m)
            if now is None or (d - now[0]).days > 7:
                stale_since = now[0] if now else None
        elif kind == "claims":
            ser = p.fred.get(syms[0], [])
            if len(ser) >= 13 and (d - ser[-1][0]).days <= 14:
                a4 = sum(v for _, v in ser[-4:]) / 4.0
                a13 = sum(v for _, v in ser[-13:]) / 13.0
                r3w = (a4 / a13 - 1.0) * 100.0 if a13 else None
                checks.append(None if r3w is None else (1 if r3w >= 5 else (-1 if r3w <= -5 else 0)) * dirn)
            elif ser:
                stale_since = ser[-1][0]

        if kind != "claims":
            checks.append(None if sign_by_band(r3w, f["band_3w"]) is None else sign_by_band(r3w, f["band_3w"]) * dirn)
            checks.append(None if sign_by_band(r3m, f["band_3m"]) is None else sign_by_band(r3m, f["band_3m"]) * dirn)

        # trend check
        trend_state = None
        ts, tsym = f["trend_source"], f["trend_symbol"]
        if ts == "technicals" and tsym in tech and tech[tsym]["a_trend_value"] is not None and tech[tsym]["last_price"] is not None:
            diff = float(tech[tsym]["last_price"]) - float(tech[tsym]["a_trend_value"])
            trend_state = (1 if diff > 0 else -1 if diff < 0 else 0)
        elif ts == "rr_outlook" and tsym in rr:
            trend_state = _outlook_sign(rr[tsym]["outlook"])
        if trend_state is not None:
            checks.append(trend_state * tdir)

        state = None if stale_since else factor_state(checks, int(f["min_checks"]))

        # breakdown override: two straight closes beyond the Hedgeye risk range (down through LRR; for the dollar, above TRR)
        breakdown = False
        if state is not None and kind == "price" and ts == "rr_outlook" and tsym in rr and tsym in rr_prev:
            now_px, prev_px = p.px_now(syms[0]), (p.px.get(syms[0], [])[-2] if len(p.px.get(syms[0], [])) >= 2 else None)
            lrr, trr = rr[tsym]["lrr"], rr[tsym]["trr"]
            lrr_p, trr_p = rr_prev[tsym]["lrr"], rr_prev[tsym]["trr"]
            if now_px and prev_px:
                if dirn > 0 and lrr is not None and lrr_p is not None and now_px[1] < float(lrr) and prev_px[1] < float(lrr_p):
                    breakdown = True
                if dirn < 0 and trr is not None and trr_p is not None and now_px[1] > float(trr) and prev_px[1] > float(trr_p):
                    breakdown = True
            if breakdown:
                state = -1
                note = "broke through its risk range two days in a row"
        if stale_since:
            stale.append(f["label"])
        rows.append({"key": f["factor_key"], "label": f["label"], "family": f["family"], "meter": f["meter"],
                     "weight": float(f["weight"]), "state": state, "r3w": r3w, "r3m": r3m, "trend": trend_state,
                     "breakdown": breakdown, "stale": stale_since, "note": note})

    gm, g_cov = meter([(r["state"], r["weight"]) for r in rows if r["meter"] == "growth"], min_cov)
    im, i_cov = meter([(r["state"], r["weight"]) for r in rows if r["meter"] == "inflation"], min_cov)

    ref_quad = None
    try:
        from etl.derive_risk_dial import _dominant_quad
        ref_quad = _dominant_quad(session, d)
    except Exception:
        log.exception("quad_check: reference quad unavailable")

    g_read = read_vs(G_EXP[ref_quad], gm, band) if ref_quad and gm is not None else None
    i_read = read_vs(I_EXP[ref_quad], im, band) if ref_quad and im is not None else None
    risk = target = None
    label_raw = "NO_DATA"
    mq = None
    fit = None
    if gm is not None and im is not None:
        mq = market_quads(gm, im, band)
        fit = quad_fit(gm, im, fit_scale)
        if ref_quad:
            risk = transition_risk(ref_quad, gm, im)
            label_raw = label_of(risk)
            target = target_quad(ref_quad, g_read, i_read)
        else:
            label_raw = "NO_REF"

    # history: confirm days (no flicker) and how long it has been on watch
    prior = session.execute(text(
        "SELECT as_of_date, risk, label_raw, label_shown FROM drv_quad_check WHERE as_of_date < :d ORDER BY as_of_date DESC LIMIT 12"),
        {"d": d}).mappings().all()
    shown = label_raw
    if confirm > 0 and prior and label_raw not in ("NO_DATA", "NO_REF"):
        prev_shown = prior[0]["label_shown"] or prior[0]["label_raw"]
        if label_raw != prev_shown:
            held = 1
            for pr in prior:
                if pr["label_raw"] == label_raw:
                    held += 1
                else:
                    break
            shown = label_raw if held >= confirm else prev_shown
    watch_days = 0
    if risk is not None and risk >= 40:
        watch_days = 1
        for pr in prior:
            if pr["risk"] is not None and float(pr["risk"]) >= 40:
                watch_days += 1
            else:
                break

    # tooltip lines (plain English)
    def _names(meter_key, st):
        return [r["label"] for r in rows if r["meter"] == meter_key and r["state"] == st and r["weight"] > 0]
    def _read_word(sc):
        return "unclear" if sc is None else ("rising" if sc >= band else "falling" if sc <= -band else "unclear")
    lines = []
    if mq:
        lines.append("Market read: Quad " + (" or ".join(str(x) for x in mq) if len(mq) < 4 else "unclear"))
    if gm is not None:
        dn, up = _names("growth", -1), _names("growth", 1)
        lines.append(f"Growth: {_read_word(gm)} ({gm:+d})" + (f". Weak: {', '.join(dn)}" if dn else "") + (f". Firm: {', '.join(up)}" if up else ""))
    else:
        lines.append("Growth: not enough data")
    if im is not None:
        up, dn = _names("inflation", 1), _names("inflation", -1)
        lines.append(f"Inflation: {_read_word(im)} ({im:+d})" + (f". Rising: {', '.join(up)}" if up else "") + (f". Falling: {', '.join(dn)}" if dn else ""))
    else:
        lines.append("Inflation: not enough data")
    holding = [r["label"] for r in rows if r["state"] == 1 and r["family"] in (1, 2) and r["weight"] > 0]
    if holding:
        lines.append("Not breaking down: " + ", ".join(holding))
    brk = [r["label"] for r in rows if r["breakdown"]]
    if brk:
        lines.append("Broke its risk range: " + ", ".join(brk))
    if watch_days >= 2:
        lines.append(f"On watch {watch_days} derive dates in a row (Hedgeye: weeks 2 and 3 are what matter)")

    session.execute(text("DELETE FROM drv_quad_factor WHERE as_of_date = :d"), {"d": d})
    for r in rows:
        session.execute(text("""
            INSERT INTO drv_quad_factor (as_of_date, factor_key, family, meter, state, ret_3w, ret_3m, trend_state, breakdown, stale_since, weight, note)
            VALUES (:d, :k, :fam, :m, :s, :r3w, :r3m, :ts, :bd, :st, :w, :n)"""),
            {"d": d, "k": r["key"], "fam": r["family"], "m": r["meter"], "s": r["state"],
             "r3w": None if r["r3w"] is None else round(r["r3w"], 3), "r3m": None if r["r3m"] is None else round(r["r3m"], 3),
             "ts": r["trend"], "bd": r["breakdown"], "st": r["stale"], "w": r["weight"], "n": r["note"]})
    session.execute(text("DELETE FROM drv_quad_check WHERE as_of_date = :d"), {"d": d})
    session.execute(text("""
        INSERT INTO drv_quad_check (as_of_date, ref_quad, growth_score, inflation_score, growth_cov, inflation_cov, growth_read, inflation_read,
                                    risk, label_raw, label_shown, target_quad, market_quads, quad_fit, watch_days, detail)
        VALUES (:d, :rq, :g, :i, :gc, :ic, :gr, :ir, :risk, :lr, :ls, :tq, :mq, CAST(:fit AS jsonb), :wd, CAST(:det AS jsonb))"""),
        {"d": d, "rq": ref_quad, "g": gm, "i": im, "gc": round(g_cov, 3), "ic": round(i_cov, 3), "gr": g_read, "ir": i_read,
         "risk": risk, "lr": label_raw, "ls": shown, "tq": target, "mq": mq, "fit": json.dumps(fit) if fit else None,
         "wd": watch_days, "det": json.dumps({"lines": lines, "stale": stale})})

    # one warning per derive when any factor is stale (same pattern as AREA_DRIVER_STALE)
    try:
        session.execute(text("DELETE FROM meta_warning WHERE screen = 'dashboard' AND as_of_date = :d AND code = :c"), {"d": d, "c": WARN_CODE})
        if stale:
            from etl.warnings import add_warning
            add_warning(session, "dashboard", "Quad market check: stale data for " + ", ".join(stale),
                        as_of_date=d, code=WARN_CODE)
    except Exception:
        log.exception("quad_check: warning write failed (non-fatal)")
    session.commit()
    return len(rows)


def derive_quad_check(session: Session, as_of_date: date, parent_run_id=None) -> int:
    """derive_all() call-site signature (session, as_of_date, parent_run_id)."""
    return _derive_quad_check_impl(session, as_of_date)
