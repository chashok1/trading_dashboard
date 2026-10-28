"""Portfolio Builder: shared numbers, measures, recipes, area fill, mix and caps.

Design: DESIGN_SPEC_9/10/11.md (11 beats 10 beats 9). Detail doc: docs/portfolio_builder_logic.md.

Everything above the "DB steps" divider is PURE (no database, no clock) so it can be
unit-tested with fake data. The DB steps (drv_pb_score, daily marks, warnings) are at
the bottom and run inside derive_all() after drv_actionable.

Every GUESS number from the specs lives in PB_PARAMS (one place). Funds, areas and mix
presets live in tables (ref_pb_universe, ref_pb_mix_preset), not here.
"""
from __future__ import annotations

import logging
import math
import statistics
from datetime import date, timedelta
from typing import Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tunable numbers (all GUESS values from the specs are here)
# ---------------------------------------------------------------------------
PB_PARAMS = {
    "min_traded_value": 5_000_000,   # $ per day (volume x price)            GUESS
    "vol_window": 63, "vol_min_obs": 55,
    "beta_window": 126, "beta_fallback_window": 63, "beta_min_obs": 55,
    "mom_lookback": 126, "mom_skip": 21,
    "low_beta_min": 0.2,             # beta below this is an odd reading      GUESS
    "mom_bonus": 0.05,               # +5 points if rr / etf outlook Bullish   GUESS
    "fund_cap": 0.20,                # of the whole account
    "area_cap": 0.40,                # of the bucket
    "min_weight": 0.03,              # inside a recipe bucket                  GUESS
    "area_floor": 0.03,              # of the bucket                           GUESS
    "min_areas": {"Equities": 3, "Fixed Income": 2},
    "equal_if_at_most": {"Equities": 0, "Fixed Income": 2},
    "tilt_k": 1.0,                   # raw = base x (1 + k x stance)           GUESS
    "chip_band": 0.25,               # B at >= +band, S at <= -band            GUESS
    "broad_two_fund_share": 0.15,    # Broad US / Foreign get 2 funds from here GUESS
    "two_fund_areas": ["Broad US", "Foreign"],
    "quad_watch_blend": 0.25, "quad_transition_blend": 0.50,                  # GUESS
    "default_quad_tilt": 0.25,       # GUESS (overridden by ref_pb_mix_preset.quad_tilt)
    "default_positions": {"Equities": 8, "Fixed Income": 3},
    "small_bucket_per": 5000, "small_bucket_min": 4,                          # GUESS
    "drift_amber_pts": 5,                                                     # GUESS
    "drop_warn_pct": 10,                                                      # GUESS
    "stale_days_alert": 3,                                                    # GUESS
    "split_move": 0.40,
    "beta_promise": 0.8,                                                      # GUESS
    "positions_stale_days": 3,                                                # GUESS
    "household_fund_note": 0.20,                                              # GUESS
    "horizon_months": {"1M": 1, "3M": 3, "6M": 6, "12M": 12},
    "horizon_days": {"1M": 30, "3M": 91, "6M": 182, "12M": 365},
    "horizon_trading_days": {"1M": 21, "3M": 63, "6M": 126, "12M": 252},
    "backtest_step": 21, "backtest_min_periods": 6,
    "quad_min_cover_pct": 50.0,
}

BUCKETS = ["Equities", "Fixed Income", "Gold", "Commodities", "Crypto", "Currency"]
RISKY_BUCKETS = ["Equities", "Commodities", "Crypto"]          # trimmed by the Risk Dial
TILT_BUCKETS = ["Equities", "Fixed Income", "Gold", "Commodities"]
# One standard fund for each bucket that has no recipe. Edit here (or add funds to ref_pb_universe).
STANDARD_FUND = {"Gold": "GLD", "Commodities": "GSG", "Crypto": "IBIT", "Currency": "UUP"}
# ref_quad_outlook row that gives a whole bucket its Quad stance (Quad-tilted preset, mix chips).
BUCKET_OUTLOOK = {
    "Equities": ("Asset Class", "Equities"), "Fixed Income": ("Asset Class", "Fixed Income"),
    "Gold": ("Asset Class", "Gold"), "Commodities": ("Asset Class", "Commodities"),
    "Crypto": ("Asset Class", "Crypto"), "Currency": ("Asset Class", "USD"),
}
# Style flavours (Equities only). Labels are drv_macro_score.style_stances labels. Mom is not offered on purpose.
FLAVOURS = {
    "all": None,
    "defensive": ["Defensives", "Low Beta", "Dividend"],
    "offensive": ["Cyclical", "High Beta", "Small Caps"],
    "value": ["Value"],
    "growth": ["Secular"],
    "mid": ["Mid Caps"],
}
RECIPES = {
    "low_vol": {"label": "Low volatility", "text": "Calmest funds (smallest price swings over 3 months)", "min_days": 63},
    "low_beta": {"label": "Low beta", "text": "Funds that move least with the market", "min_days": 63},
    "momentum": {"label": "Momentum", "text": "Best 6-month trend, still above the Trend line, no Hedgeye Bearish call", "min_days": 127},
    "core": {"label": "Core", "text": "All eligible funds, calmer ones get more", "min_days": 63},
}
SELL_FAMILY = {"SA", "SS", "STM", "SO", "SW", "SWW", "REMOVE", "REDUCE"}
BUY_FAMILY = {"BM", "BS", "BMN", "BW", "BSW", "INCREASE", "ADD"}

_STANCE_VAL = {"bullish": 1.0, "bearish": -1.0, "neutral": 0.0}


def final_call_side(code: Optional[str]) -> str:
    c = (code or "").strip().upper()
    if c in SELL_FAMILY:
        return "sell"
    if c in BUY_FAMILY:
        return "buy"
    return "neutral"


def _f(x) -> Optional[float]:
    try:
        return None if x is None else float(x)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# R1 measures (closes ascending, only data up to the build day)
# ---------------------------------------------------------------------------
def returns_from_closes(closes: list) -> list:
    out = []
    for i in range(1, len(closes)):
        a, b = closes[i - 1], closes[i]
        if a and b is not None:
            out.append(b / a - 1.0)
    return out


def swings(closes: list, window: int = None, min_obs: int = None) -> Optional[float]:
    """vol63: standard deviation of the last 63 daily returns x sqrt(252); needs 55."""
    window = window or PB_PARAMS["vol_window"]
    min_obs = min_obs or PB_PARAMS["vol_min_obs"]
    rets = returns_from_closes(closes)[-window:]
    if len(rets) < min_obs:
        return None
    return statistics.stdev(rets) * math.sqrt(252)


def beta_vs_spy(fund: dict, spy: dict, dates: list):
    """beta126 = cov(fund, SPY) / var(SPY) on aligned daily returns; falls back to 63 when
    fewer than 126 returns exist. fund/spy are {date: close}; dates = ascending SPY dates.
    Returns (beta or None, window_used)."""
    rf, rs = [], []
    for i in range(1, len(dates)):
        a, b = dates[i - 1], dates[i]
        if a in fund and b in fund and a in spy and b in spy and fund[a] and spy[a]:
            rf.append(fund[b] / fund[a] - 1.0)
            rs.append(spy[b] / spy[a] - 1.0)
    n = len(rf)
    if n >= PB_PARAMS["beta_window"]:
        w = PB_PARAMS["beta_window"]
    elif n >= PB_PARAMS["beta_min_obs"]:
        w = min(PB_PARAMS["beta_fallback_window"], n)
    else:
        return None, 0
    rf, rs = rf[-w:], rs[-w:]
    var = statistics.pvariance(rs)
    if var <= 0:
        return None, w
    mf, ms = sum(rf) / w, sum(rs) / w
    cov = sum((x - mf) * (y - ms) for x, y in zip(rf, rs)) / w
    return cov / var, w


def momentum(closes: list) -> Optional[float]:
    """6-month return skipping the last month: close(t-21) / close(t-126) - 1; needs 127 closes."""
    lb, sk = PB_PARAMS["mom_lookback"], PB_PARAMS["mom_skip"]
    if len(closes) < lb + 1:
        return None
    a, b = closes[-1 - lb], closes[-1 - sk]
    if not a or b is None:
        return None
    return b / a - 1.0


def above_trend(price, trend) -> Optional[bool]:
    p, t = _f(price), _f(trend)
    if p is None or t is None:
        return None
    return p > t


# ---------------------------------------------------------------------------
# R2 recipe scores. m = metrics dict: vol63, beta, mom, above_trend, hedgeye {rr, etf, call}
# Returns (ok, score, excluded_reason)
# ---------------------------------------------------------------------------
def score_fund(recipe: str, m: dict):
    p = PB_PARAMS
    vol, beta, mom = m.get("vol63"), m.get("beta"), m.get("mom")
    if recipe in ("low_vol", "core"):
        if vol is None:
            return False, None, "not enough price history for swings"
        return True, -vol, None
    if recipe == "low_beta":
        if beta is None:
            return False, None, "not enough price history for beta"
        if beta < p["low_beta_min"]:
            return False, None, "beta below %.1f (odd reading)" % p["low_beta_min"]
        return True, -beta, None
    if recipe == "momentum":
        if mom is None:
            return False, None, "needs 127 days of prices"
        if m.get("above_trend") is not True:
            return False, None, "not above its Trend line"
        hy = m.get("hedgeye") or {}
        outs = [str(hy.get(k) or "").strip().lower() for k in ("rr", "etf", "call")]
        if "bearish" in outs:
            return False, None, "Hedgeye Bearish call"
        bonus = p["mom_bonus"] if (outs[0] == "bullish" or outs[1] == "bullish") else 0.0
        return True, mom + bonus, None
    return False, None, "unknown recipe"


def rank_scored(rows: list) -> list:
    """rows: [{sym, score, vol63}] (ok only). Best first; ties by lower vol63, then symbol A-Z."""
    return sorted(rows, key=lambda r: (-r["score"], r["vol63"] if r.get("vol63") is not None else 9e9, r["sym"]))


# ---------------------------------------------------------------------------
# R3 weights inside a bucket / area
# ---------------------------------------------------------------------------
def inverse_swing_weights(vols: dict) -> dict:
    """{sym: vol} -> weights adding to 1. Missing/zero vol -> equal weight for everyone."""
    if not vols:
        return {}
    if any((v is None or v <= 0) for v in vols.values()):
        n = len(vols)
        return {s: 1.0 / n for s in vols}
    raw = {s: 1.0 / v for s, v in vols.items()}
    tot = sum(raw.values())
    return {s: r / tot for s, r in raw.items()}


def apply_caps(w: dict, fund_cap: float, area_of: Optional[dict] = None, area_cap: Optional[float] = None,
               min_weight: float = 0.0, max_passes: int = 10) -> dict:
    """Cap every fund at fund_cap (raised to 1/n when too few funds) and every area at area_cap
    (raised to 1/n_areas), share the excess pro-rata among funds that still have room, repeat
    up to max_passes, then drop funds under min_weight and share their weight out.
    Weights are fractions of the bucket. Can sum to less than 1 only if nothing has room."""
    w = {s: v for s, v in w.items() if v and v > 0}
    n = len(w)
    if n == 0:
        return {}
    cap = max(fund_cap, 1.0 / n)
    acap = None
    if area_of and area_cap:
        n_areas = len({area_of.get(s) for s in w})
        acap = max(area_cap, 1.0 / max(1, n_areas))
    tot0 = sum(w.values())
    w = {s: v / tot0 for s, v in w.items()}
    for _ in range(max_passes):
        excess = 0.0
        for s in list(w):
            if w[s] > cap + 1e-12:
                excess += w[s] - cap
                w[s] = cap
        if acap is not None:
            by_area: dict = {}
            for s, v in w.items():
                by_area.setdefault(area_of.get(s), []).append(s)
            for a, syms in by_area.items():
                tot = sum(w[s] for s in syms)
                if tot > acap + 1e-12:
                    k = acap / tot
                    for s in syms:
                        excess += w[s] * (1 - k)
                        w[s] *= k
        if excess < 1e-12:
            break
        area_tot: dict = {}
        if acap is not None:
            for s, v in w.items():
                area_tot[area_of.get(s)] = area_tot.get(area_of.get(s), 0.0) + v
        room = [s for s in w if w[s] < cap - 1e-12 and (acap is None or area_tot.get(area_of.get(s), 0) < acap - 1e-12)]
        rsum = sum(w[s] for s in room)
        if not room or rsum <= 0:
            break
        for s in room:
            w[s] += excess * w[s] / rsum
    if min_weight and len(w) > 1:
        small = [s for s, v in w.items() if v < min_weight]
        if small and len(small) < len(w):
            for s in small:
                del w[s]
            t = sum(w.values())
            w = {s: v / t for s, v in w.items()}
    return w


# ---------------------------------------------------------------------------
# Quad mix over the holding period (horizon-matched window) and area stances
# ---------------------------------------------------------------------------
def _onehot(q: int) -> list:
    return [1.0 if i + 1 == q else 0.0 for i in range(4)]


def horizon_quad_mix(d: date, h_days: int, monthly: dict, quarterly: dict,
                     check_label: Optional[str] = None, target_quad: Optional[int] = None):
    """Expected Quad mix over [d, d+h). monthly = {(y, m): [q1..q4 fractions]}; quarterly =
    {(y, qn): quad int} (declared Quad, used one-hot for months with no monthly row).
    Uses derive_macro.window_weights / build_effective_distribution (same code as MACRO).
    Returns dict: shares[4], coverage_pct, weighted [((y,m), w)], note, blend."""
    from etl.derive_macro import window_weights, build_effective_distribution
    end = d + timedelta(days=h_days)
    pcts: dict = {}
    cur = date(d.year, d.month, 1)
    while cur < end:
        key = (cur.year, cur.month)
        if key in monthly:
            pcts[key] = monthly[key]
        else:
            q = quarterly.get((cur.year, (cur.month - 1) // 3 + 1))
            if q:
                pcts[key] = _onehot(int(q))
        cur = date(cur.year + (cur.month // 12), (cur.month % 12) + 1, 1)
    weighted, coverage = window_weights(d, list(pcts.keys()), h_days, 0)
    if not weighted:
        return {"shares": None, "coverage_pct": 0.0, "weighted": [], "note": "No Quad outlook for these months", "blend": None}
    eff = build_effective_distribution(weighted, pcts)
    tot = sum(eff) or 1.0
    eff = [x / tot for x in eff]
    note, blend = None, None
    lab = (check_label or "").upper()
    if lab in ("WATCH", "TRANSITION") and target_quad:
        b = PB_PARAMS["quad_watch_blend"] if lab == "WATCH" else PB_PARAMS["quad_transition_blend"]
        oh = _onehot(int(target_quad))
        eff = [(1 - b) * e + b * o for e, o in zip(eff, oh)]
        blend = {"label": lab, "target_quad": int(target_quad), "share": b}
    elif lab in ("", "NO_DATA", "NO_REF"):
        note = "market check unavailable"
    if coverage < PB_PARAMS["quad_min_cover_pct"]:
        note = ((note + "; ") if note else "") + "Quad outlook covers only %.0f%% of your period" % coverage
    return {"shares": eff, "coverage_pct": coverage, "weighted": weighted, "note": note, "blend": blend}


def outlook_key(cat, sub):
    if cat is None or sub is None:
        return None
    return (str(cat).strip().lower(), str(sub).strip().lower())


def area_stance(texts: Optional[list], shares: Optional[list], override: Optional[list] = None) -> Optional[float]:
    """Stance of one area. texts = [q1..q4] 'Bullish/Neutral/Bearish' (None = no view -> None).
    Default: sum of share_k x outlook_k. Override (list of Quad numbers): one Quad = that outlook;
    several = +1 if Bullish in all, -1 if Bearish in any, else 0 (AND rule)."""
    if not texts:
        return None
    vals = [_STANCE_VAL.get(str(t or "").strip().lower(), 0.0) for t in texts]
    if override:
        picked = [vals[int(q) - 1] for q in override]
        if len(picked) == 1:
            return picked[0]
        if any(v < 0 for v in picked):
            return -1.0
        return 1.0 if all(v > 0 for v in picked) else 0.0
    if not shares:
        return None
    return round(sum(shares[i] * vals[i] for i in range(4)), 4)


def chip_of(stance: Optional[float]) -> str:
    if stance is None:
        return "-"
    band = PB_PARAMS["chip_band"]
    return "B" if stance >= band else ("S" if stance <= -band else "H")


# ---------------------------------------------------------------------------
# S2 Fill from Macro and Quad (inside one bucket)
# ---------------------------------------------------------------------------
def fill_areas(areas: list, bucket: str, bucket_dollars: float, locks: Optional[dict] = None) -> dict:
    """areas: [{name, stance (None = no view), eligible (bool), kept_dollars}].
    locks: {name: pct 0..100} typed by the user. Returns {rows, message, unallocated}.
    row: name, stance, chip, base, raw, fill (fraction of bucket), locked, kept_dollars,
         buy_dollars, notes[]. Pure and deterministic."""
    p = PB_PARAMS
    locks = {k: v for k, v in (locks or {}).items() if v is not None}
    rows = []
    for a in areas:
        if a.get("eligible") or (a.get("kept_dollars") or 0) > 0:
            st = a.get("stance")
            rows.append({"name": a["name"], "stance": st, "chip": chip_of(st), "kept_dollars": a.get("kept_dollars") or 0.0,
                         "notes": [], "revived": False, "locked": a["name"] in locks})
    if not rows:
        return {"rows": [], "message": "No area has an eligible fund", "unallocated": 1.0}
    n = len(rows)
    base = 1.0 / n
    min_areas = p["min_areas"].get(bucket, 3)
    equal_max = p["equal_if_at_most"].get(bucket, 0)
    k = p["tilt_k"]
    for r in rows:
        r["base"] = base
        st = r["stance"] or 0.0
        if equal_max and n <= equal_max:
            r["raw"] = base
        elif r["chip"] == "S":
            r["raw"] = 0.0
        else:
            r["raw"] = max(0.0, base * (1.0 + k * st))
    if not (equal_max and n <= equal_max):
        nz = sum(1 for r in rows if r["raw"] > 0)
        if nz < min(min_areas, n):
            zero = sorted([r for r in rows if r["raw"] <= 0], key=lambda r: -(r["stance"] or 0.0))
            for r in zero[: min(min_areas, n) - nz]:
                r["raw"] = 0.5 * base
                r["revived"] = True
                r["notes"].append("Kept at half the base share: fewer than %d areas would be left" % min_areas)

    def _spread(use_locks: bool):
        lk = {r["name"]: locks[r["name"]] / 100.0 for r in rows if use_locks and r["name"] in locks}
        lsum = sum(lk.values())
        if lsum > 1.0 + 1e-9:
            return None, lsum
        free = max(0.0, 1.0 - lsum)
        un = [r for r in rows if r["name"] not in lk]
        rsum = sum(r["raw"] for r in un)
        fill = dict(lk)
        for r in un:
            fill[r["name"]] = (r["raw"] / rsum * free) if rsum > 0 else 0.0
        # cap and floor on unlocked rows only
        revived = {r["name"] for r in rows if r["revived"]}
        for _ in range(10):
            open_ = [r["name"] for r in un if fill[r["name"]] > 0]
            cap = max(p["area_cap"], free / max(1, len(open_)))
            ex = 0.0
            for nm in open_:
                if fill[nm] > cap + 1e-12:
                    ex += fill[nm] - cap
                    fill[nm] = cap
            nz = sum(1 for r in rows if fill[r["name"]] > 0)
            for nm in sorted(open_, key=lambda x: fill[x]):
                if 0 < fill[nm] < p["area_floor"] and nm not in revived and nz > min(min_areas, n):
                    ex += fill[nm]
                    fill[nm] = 0.0
                    nz -= 1
            if ex < 1e-12:
                break
            room = [nm for nm in open_ if 0 < fill[nm] < cap - 1e-12]
            rs = sum(fill[nm] for nm in room)
            if not room or rs <= 0:
                break
            for nm in room:
                fill[nm] += ex * fill[nm] / rs
        return fill, lsum

    auto, _ = _spread(False)
    final, lsum = _spread(True)
    message = None
    if final is None:
        message = "Locked areas add to %.0f%%: lower one." % (lsum * 100)
        final = auto
    unalloc = max(0.0, 1.0 - sum(final.values()))
    # kept holdings: an area is at least its kept share; the excess comes off the other unlocked areas
    if bucket_dollars > 0:
        for r in rows:
            ks = r["kept_dollars"] / bucket_dollars
            if ks > final[r["name"]] + 1e-12:
                need = ks - final[r["name"]]
                r["notes"].append("Kept holdings already exceed this area by $%s" % format(round(need * bucket_dollars), ","))
                final[r["name"]] = ks
                oth = [o for o in rows if o is not r and not o["locked"] and final[o["name"]] > 0]
                os_ = sum(final[o["name"]] for o in oth)
                if os_ > 0:
                    for o in oth:
                        final[o["name"]] = max(0.0, final[o["name"]] - need * final[o["name"]] / os_)
    for r in rows:
        r["fill"] = round(final[r["name"]], 6)
        r["auto_fill"] = round(auto[r["name"]], 6)
        dollars = r["fill"] * bucket_dollars
        r["buy_dollars"] = max(0.0, dollars - r["kept_dollars"])
    return {"rows": rows, "message": message, "unallocated": round(unalloc, 6)}


# ---------------------------------------------------------------------------
# S3 pick funds inside an area / bucket
# ---------------------------------------------------------------------------
def pick_in_area(funds: list, rule: str, n_funds: int, skip_syms: Optional[set] = None):
    """funds: [{sym, vol63, beta, mom, above_trend, hedgeye}] eligible funds of ONE area.
    rule: low_vol | low_beta | momentum | core. skip_syms = Final Call sells (replaced by the
    next fund in the same area). Returns (picks [{sym, weight, score}], skipped [{sym, reason}],
    note). weight = inverse-swing share inside the area; picks empty -> note says why."""
    skip_syms = skip_syms or set()
    ok, why_not = [], []
    for f in funds:
        good, sc, ex = score_fund(rule, f)
        if good:
            ok.append({"sym": f["sym"], "score": sc, "vol63": f.get("vol63")})
        else:
            why_not.append({"sym": f["sym"], "reason": ex})
    ranked = rank_scored(ok)
    picks, skipped = [], []
    for r in ranked:
        if r["sym"] in skip_syms:
            skipped.append({"sym": r["sym"], "reason": "Final Call sells it"})
            continue
        if len(picks) < n_funds:
            picks.append(r)
    if not picks:
        note = "None qualifies" if not ranked else "Every qualifying fund has a Sell call"
        return [], skipped, note
    w = inverse_swing_weights({r["sym"]: r.get("vol63") for r in picks})
    for r in picks:
        r["weight"] = w[r["sym"]]
    return picks, skipped, None


# ---------------------------------------------------------------------------
# Mix (asset-class buckets): presets, Quad tilt, Risk Dial trim, kept floors
# ---------------------------------------------------------------------------
def mix_total(mix: dict) -> float:
    return sum(v for k, v in mix.items() if k != "Cash")


def normalise_mix(mix: dict) -> dict:
    """Cash is always 'the rest'. Scale the other buckets down if they add to more than 100."""
    out = {k: max(0.0, float(v or 0)) for k, v in mix.items() if k != "Cash"}
    t = sum(out.values())
    if t > 100.0:
        out = {k: v * 100.0 / t for k, v in out.items()}
        t = 100.0
    out["Cash"] = round(100.0 - t, 6)
    return out


def quad_tilt_mix(base: dict, stances: dict, tilt: float) -> dict:
    """Quad-tilted preset: share x (1 + tilt x stance) for Equities / Fixed Income / Gold / Commodities;
    Cash and Crypto are not tilted; then the tilted buckets are rescaled so Cash keeps its base share."""
    out = {k: float(v or 0) for k, v in base.items()}
    cash = out.get("Cash", 100.0 - sum(v for k, v in out.items() if k != "Cash"))
    for b in TILT_BUCKETS:
        if out.get(b):
            out[b] = out[b] * (1.0 + tilt * (stances.get(b) or 0.0))
    non_cash = {k: v for k, v in out.items() if k != "Cash"}
    tilted_sum = sum(non_cash.values())
    target = 100.0 - cash
    if tilted_sum > 0:
        non_cash = {k: v * target / tilted_sum for k, v in non_cash.items()}
    non_cash["Cash"] = cash
    return non_cash


def risk_dial_trim(mix: dict, multiplier: Optional[float], kept_floor: Optional[dict] = None) -> dict:
    """Risky buckets x multiplier, the money removed goes to Cash. Never trims below a kept floor (pct)."""
    out = dict(mix)
    if multiplier is None or multiplier >= 1.0:
        return out
    kept_floor = kept_floor or {}
    moved = 0.0
    for b in RISKY_BUCKETS:
        v = out.get(b) or 0.0
        if v <= 0:
            continue
        new = max(min(v, kept_floor.get(b, 0.0)), v * multiplier)
        moved += v - new
        out[b] = new
    out["Cash"] = (out.get("Cash") or 0.0) + moved
    return out


def enforce_floors(mix: dict, floors: dict) -> dict:
    """Raise a bucket to its kept floor, paid for by Cash first, then by buckets above their floors."""
    out = dict(mix)
    need = 0.0
    for b, fl in floors.items():
        if b == "Cash":
            continue
        if (out.get(b) or 0.0) < fl:
            need += fl - (out.get(b) or 0.0)
            out[b] = fl
    if need <= 0:
        return out
    take = min(need, out.get("Cash") or 0.0)
    out["Cash"] = (out.get("Cash") or 0.0) - take
    need -= take
    if need > 1e-9:
        room = {b: out[b] - floors.get(b, 0.0) for b in out if b != "Cash" and out[b] - floors.get(b, 0.0) > 0}
        rs = sum(room.values())
        if rs > 0:
            for b, r in room.items():
                out[b] -= min(r, need * r / rs)
    return out


def whole_shares(dollars: float, price: Optional[float]) -> int:
    if not price or price <= 0 or dollars <= 0:
        return 0
    return int(math.floor(dollars / price + 1e-9))


def positions_for_bucket(bucket: str, n_default: int, bucket_dollars: float) -> int:
    """Default number of positions: small buckets get fewer (1 per $5k, minimum 4)."""
    p = PB_PARAMS
    n = n_default
    if bucket_dollars and bucket_dollars < 40_000:
        n = min(n, max(p["small_bucket_min"], int(bucket_dollars // p["small_bucket_per"])))
    return max(1, n)


# ---------------------------------------------------------------------------
# Paper-model statistics, alerts and promise check (pure)
# ---------------------------------------------------------------------------
def beta_from_returns(rf: list, rs: list) -> Optional[float]:
    n = min(len(rf), len(rs))
    if n < 5:
        return None
    rf, rs = rf[-n:], rs[-n:]
    var = statistics.pvariance(rs)
    if var <= 0:
        return None
    mf, ms = sum(rf) / n, sum(rs) / n
    return sum((x - mf) * (y - ms) for x, y in zip(rf, rs)) / n / var


def series_stats(values: list, spy_values: list, start_value: float) -> dict:
    """values / spy_values: daily marks (ascending). start_value = what was put in on day 0.
    Returns return, spy return, worst drop, swings of the model and of SPY (None until 5 daily returns)."""
    out = {"ret": None, "spy_ret": None, "worst_drop": None, "swings": None, "spy_swings": None, "beta": None, "days": len(values)}
    if not values or not start_value:
        return out
    out["ret"] = values[-1] / start_value - 1.0
    if spy_values and spy_values[0]:
        out["spy_ret"] = spy_values[-1] / start_value - 1.0
    peak, worst = start_value, 0.0
    for v in values:
        peak = max(peak, v)
        worst = min(worst, v / peak - 1.0)
    out["worst_drop"] = worst
    mv = [start_value] + list(values)
    sv = [start_value] + list(spy_values)
    rm, rs = returns_from_closes(mv), returns_from_closes(sv)
    if len(rm) >= 5:
        out["swings"] = statistics.stdev(rm) * math.sqrt(252)
    if len(rs) >= 5:
        out["spy_swings"] = statistics.stdev(rs) * math.sqrt(252)
    out["beta"] = beta_from_returns(rm, rs)
    return out


def evaluate_alerts(opt_in: dict, state: dict) -> list:
    """Alert only, never changes holdings. Data-problem alerts are always on.
    state: value, amount, quad_label, risk_label, positions [{sym, stale_days, move, final_side, is_kept}]."""
    p = PB_PARAMS
    out = []
    opt_in = opt_in or {}
    amt, val = state.get("amount"), state.get("value")
    if opt_in.get("drop") and amt and val is not None and val <= amt * (1 - p["drop_warn_pct"] / 100.0):
        out.append({"code": "drop", "message": "Model is down %.0f%% or more from its start" % p["drop_warn_pct"]})
    if opt_in.get("quad_turn") and (state.get("quad_label") or "").upper() == "TRANSITION":
        out.append({"code": "quad_turn", "message": 'The Quad check now says "transition"'})
    if opt_in.get("no_new_risk") and (state.get("risk_label") or "").upper() == "NOT INVESTABLE":
        out.append({"code": "no_new_risk", "message": 'The Risk Dial now says "No new risk"'})
    if opt_in.get("final_call_sell"):
        sells = [x["sym"] for x in state.get("positions", []) if x.get("final_side") == "sell" and not x.get("is_kept")]
        if sells:
            out.append({"code": "final_call_sell", "message": "Final Call now says Sell on: " + ", ".join(sorted(sells))})
    for x in state.get("positions", []):
        if (x.get("stale_days") or 0) >= p["stale_days_alert"]:
            out.append({"code": "stale:" + x["sym"], "message": "%s has no new price for %d trading days" % (x["sym"], x["stale_days"])})
        mv = x.get("move")
        if mv is not None and abs(mv) > p["split_move"]:
            out.append({"code": "split:" + x["sym"], "message": "%s moved %+.0f%% in a day: possible split, check" % (x["sym"], mv * 100)})
    return out


def fire_once(warnings: dict, alerts: list, d: date) -> dict:
    """Each alert is recorded once (kept until dismissed). warnings = {opt_in, fired[], dismissed[]}."""
    w = dict(warnings or {})
    w.setdefault("opt_in", {})
    w.setdefault("fired", [])
    w.setdefault("dismissed", [])
    have = {f["code"] for f in w["fired"]}
    for a in alerts:
        if a["code"] not in have:
            w["fired"].append({"code": a["code"], "message": a["message"], "date": d.isoformat()})
            have.add(a["code"])
    return w


def promise_check(rules: list, area_mode: bool, stats: dict, pos_rets: dict, area_chips: dict,
                  quad_labels: list) -> dict:
    """Live promise check (final at the end). rules = pick rules used (low_vol / low_beta / momentum / core).
    Result per item: pass | fail | pending (fewer than 5 daily returns). Hit rate = holdings beating SPY."""
    items = []
    spy_ret = stats.get("spy_ret")
    pend = stats.get("swings") is None

    def item(label, ok, detail):
        items.append({"label": label, "result": "pending" if ok is None else ("pass" if ok else "fail"), "detail": detail})

    if "low_vol" in rules:
        s, b = stats.get("swings"), stats.get("spy_swings")
        item("Low volatility: calmer than SPY?", None if (s is None or b is None) else s < b,
             "n/a yet" if (s is None or b is None) else "%.0f%% vs %.0f%%" % (s * 100, b * 100))
    if "low_beta" in rules:
        bt = stats.get("beta")
        item("Low beta: moves less than the market?", None if bt is None else bt < PB_PARAMS["beta_promise"],
             "n/a yet" if bt is None else "beta %.2f (limit %.1f)" % (bt, PB_PARAMS["beta_promise"]))
    if "momentum" in rules:
        r = stats.get("ret")
        item("Momentum: trend keeps going (beating SPY)?", None if (r is None or spy_ret is None) else r > spy_ret,
             "n/a yet" if r is None or spy_ret is None else "%+.1f%% vs %+.1f%%" % (r * 100, spy_ret * 100))
    if area_mode:
        r = stats.get("ret")
        n = len(quad_labels)
        calm = (sum(1 for x in quad_labels if (x or "").upper() != "TRANSITION") / n) if n else None
        ok = None if (r is None or spy_ret is None or calm is None) else (calm > 0.5 and r > spy_ret)
        item("Quad call held and the areas worked?", ok,
             "n/a yet" if ok is None else "Quad check not TRANSITION on %.0f%% of days; model %+.1f%% vs SPY %+.1f%%" % (calm * 100, r * 100, spy_ret * 100))
        fav = [v for k, v in pos_rets.items() if area_chips.get(k) == "B" and v is not None]
        if fav and spy_ret is not None:
            avg = sum(fav) / len(fav)
            item("Favoured areas beating SPY?", avg > spy_ret, "%+.1f%% vs %+.1f%%" % (avg * 100, spy_ret * 100))
    rets = [v for v in pos_rets.values() if v is not None]
    hit = {"beat": None, "of": len(rets)}
    if rets and spy_ret is not None:
        hit["beat"] = sum(1 for v in rets if v > spy_ret)
    return {"items": items, "hit_rate": hit}


# ---------------------------------------------------------------------------
# DB steps (run inside derive_all after drv_actionable). Idempotent per as_of_date.
# ---------------------------------------------------------------------------
def _derive_pb_score_impl(session, as_of_date: date, run_id=None) -> int:
    import json
    from sqlalchemy import text
    from etl import builder_data as bd
    d = as_of_date
    if session.execute(text("SELECT to_regclass('drv_pb_score')")).scalar() is None:
        log.info("drv_pb_score %s: table not created yet (run python -m db.init_db) -- skipped", d)
        return 0
    problems: list = []
    funds = bd.fund_metrics(session, d, problems)
    session.execute(text("DELETE FROM drv_pb_score WHERE as_of_date = :d"), {"d": d})
    if not funds:
        session.commit()
        log.info("drv_pb_score %s: no fund list (%s)", d, "; ".join(problems))
        return 0
    quad = bd.quad_context(session, d, "3M")
    omap = bd.outlook_map(session)
    shares = quad.get("shares")
    rows = []
    for key in RECIPES:
        scored = []
        for s, f in funds.items():
            if not f["eligible"]:
                continue
            ok, sc, _ = score_fund(key, f)
            if ok:
                scored.append({"sym": s, "score": sc, "vol63": f["vol63"]})
        rank = {r["sym"]: i + 1 for i, r in enumerate(rank_scored(scored))}
        for s, f in funds.items():
            if f["eligible"]:
                ok, sc, ex = score_fund(key, f)
            else:
                ok, sc, ex = False, None, f["reason"]
            st = area_stance(omap.get(outlook_key(f["outlook_cat"], f["outlook_sub"])), shares)
            rows.append({"d": d, "k": key, "s": s, "el": bool(ok), "sc": sc, "rk": rank.get(s) if ok else None,
                         "v": f["vol63"], "b": f["beta"], "m": f["mom"], "qs": st, "ex": None if ok else ex,
                         "rs": json.dumps({"beta_window": f["beta_window"], "n_closes": f["n_closes"],
                                           "above_trend": f["above_trend"], "area": f["area"], "bucket": f["bucket"]})})
    session.execute(text(
        "INSERT INTO drv_pb_score (as_of_date, recipe_key, tos_symbol, eligible, score, rank, vol63, beta, mom, "
        "quad_stance, reason, excluded_reason) VALUES (:d, :k, :s, :el, :sc, :rk, :v, :b, :m, :qs, "
        "CAST(:rs AS JSONB), :ex)"), rows)
    session.commit()
    return len(rows)


def derive_pb_score(session, as_of_date: date, parent_run_id=None) -> int:
    """derive_all() call-site signature (session, as_of_date, parent_run_id)."""
    return _derive_pb_score_impl(session, as_of_date)


def derive_model_marks(session, as_of_date: date, parent_run_id=None) -> int:
    """Daily paper marks for every running model portfolio + alerts + status changes (etl/builder_store.py)."""
    from etl import builder_store as bs
    return bs.mark_all(session, as_of_date)
