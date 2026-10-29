"""Portfolio Builder data loaders (read-only SELECTs). Turns database rows into the plain dicts
that etl/builder_engine.py expects. Every loader tolerates a missing / empty table and says so
in the returned `problems` list instead of crashing (the DDL and seed are applied by the user).
"""
from __future__ import annotations

import json
import logging
from datetime import date
from typing import Optional

from sqlalchemy import text

from etl.derive_model_portfolio import (
    PB_PARAMS, BUCKETS, swings, beta_vs_spy, momentum, above_trend, horizon_quad_mix, outlook_key,
)

log = logging.getLogger(__name__)

SPY = "SPY"
_AC_ALIAS = {"Equities": "Equities", "Fixed Income": "Fixed Income", "Commodities": "Commodities", "Gold": "Gold",
             "Crypto": "Crypto", "FX": "Currency", "USD": "Currency", "Cash": "Cash"}


def _q(session, sql: str, params: Optional[dict] = None, problems: Optional[list] = None, what: str = ""):
    """Run a SELECT inside a savepoint; a missing table / column returns [] and logs a problem."""
    try:
        with session.begin_nested():
            return session.execute(text(sql), params or {}).fetchall()
    except Exception as e:  # missing table before init_db, etc.
        if problems is not None:
            problems.append("%s unavailable (%s)" % (what or "query", type(e).__name__))
        log.warning("builder_data: %s failed: %s", what or sql[:40], e)
        return []


def _j(v):
    if isinstance(v, str):
        try:
            return json.loads(v)
        except Exception:
            return None
    return v


def _num(v) -> Optional[float]:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Prices
# ---------------------------------------------------------------------------
def load_closes(session, syms: list, d: date, problems: Optional[list] = None) -> dict:
    """{sym: {date: close}} up to d. hist_quote_daily (long Yahoo history, if it ever has data) fills
    older dates; our own drv_quote close wins on any day both have."""
    out: dict = {s: {} for s in syms}
    if not syms:
        return out
    for r in _q(session, "SELECT symbol, obs_date, close FROM hist_quote_daily WHERE symbol = ANY(:s) "
                         "AND obs_date <= :d AND close IS NOT NULL", {"s": syms, "d": d}, None, "hist_quote_daily"):
        out[r[0]][r[1]] = float(r[2])
    for r in _q(session, "SELECT tos_symbol, as_of_date, last_price FROM drv_quote WHERE tos_symbol = ANY(:s) "
                         "AND as_of_date <= :d AND last_price IS NOT NULL", {"s": syms, "d": d}, problems, "drv_quote"):
        out[r[0]][r[1]] = float(r[2])
    return out


def load_trend_history(session, syms: list, d: date) -> dict:
    out: dict = {s: {} for s in syms}
    for r in _q(session, "SELECT tos_symbol, as_of_date, a_trend_value FROM drv_technicals WHERE tos_symbol = ANY(:s) "
                         "AND as_of_date <= :d AND a_trend_value IS NOT NULL", {"s": syms, "d": d}, None, "trend history"):
        out[r[0]][r[1]] = float(r[2])
    return out


# ---------------------------------------------------------------------------
# Fund list + measures (shared by drv_pb_score and the preview)
# ---------------------------------------------------------------------------
def fund_metrics(session, d: date, problems: Optional[list] = None, uni_rows: Optional[list] = None) -> dict:
    """{sym: fund dict} for every fund in ref_pb_universe (or in uni_rows, same column order: the source pool),
    eligible flag + reason, measures and tags."""
    problems = problems if problems is not None else []
    uni = uni_rows if uni_rows is not None else _q(
        session, "SELECT tos_symbol, bucket, area, outlook_category, outlook_sub, active, note "
                 "FROM ref_pb_universe", None, problems, "ref_pb_universe")
    if not uni:
        problems.append("Fund list is empty: run python -m db.init_db and apply db/seeds_portfolio_builder.sql")
        return {}
    syms = [r[0] for r in uni]
    in_syms = {r[0] for r in _q(session, "SELECT tos_symbol FROM drv_symbols WHERE as_of_date = :d AND tos_symbol = ANY(:s)",
                                {"d": d, "s": syms}, problems, "drv_symbols")}
    tech = {r[0]: r for r in _q(session, "SELECT tos_symbol, last_price, volume, a_trend_value FROM drv_technicals "
                                         "WHERE as_of_date = :d AND tos_symbol = ANY(:s)", {"d": d, "s": syms}, problems, "drv_technicals")}
    # liquidity: MEDIAN daily volume over the last ~20 trading days (the anchor day is often a part-day TOSL
    # export, so one day's volume would call every fund illiquid) x today's price.
    med_vol = {r[0]: _num(r[1]) for r in _q(session, "SELECT tos_symbol, percentile_cont(0.5) WITHIN GROUP (ORDER BY volume) "
                                                    "FROM drv_technicals WHERE tos_symbol = ANY(:s) AND as_of_date <= :d "
                                                    "AND as_of_date > CAST(:d AS DATE) - 30 AND volume > 0 GROUP BY tos_symbol",
                                            {"d": d, "s": syms}, None, "volume history")}
    quote = {r[0]: _num(r[1]) for r in _q(session, "SELECT tos_symbol, last_price FROM drv_quote WHERE as_of_date = :d "
                                                   "AND tos_symbol = ANY(:s)", {"d": d, "s": syms}, problems, "drv_quote")}
    outl = {r[0]: r for r in _q(session, "SELECT tos_symbol, rr_outlook, etf_outlook, call_outlook FROM drv_outlooks "
                                        "WHERE as_of_date = :d AND tos_symbol = ANY(:s)", {"d": d, "s": syms}, None, "drv_outlooks")}
    styl = {r[0]: _j(r[1]) or [] for r in _q(session, "SELECT tos_symbol, style_stances FROM drv_macro_score "
                                                      "WHERE as_of_date = :d AND tos_symbol = ANY(:s)", {"d": d, "s": syms}, None, "drv_macro_score")}
    fcall = {r[0]: r[1] for r in _q(session, "SELECT tos_symbol, final_code FROM drv_actionable WHERE as_of_date = :d "
                                            "AND tos_symbol = ANY(:s)", {"d": d, "s": syms}, None, "drv_actionable")}
    closes = load_closes(session, syms + [SPY], d, problems)
    spy = closes.get(SPY) or {}
    spy_dates = sorted(spy)
    funds: dict = {}
    for sym, bucket, area, ocat, osub, active, note in uni:
        price = quote.get(sym)
        if price is None and sym in tech:
            price = _num(tech[sym][1])
        reason = None
        adv = None
        if not active:
            reason = "Not buyable yet" + (": %s" % note if note else "")
        elif sym not in in_syms:
            reason = "Not in today's TOS export"
        elif price is None:
            reason = "No price today"
        else:
            vol = med_vol.get(sym)
            adv = (vol * price) if vol is not None else None
            if adv is None:
                reason = "No volume data"
            elif adv < PB_PARAMS["min_traded_value"]:
                reason = "Trades under $%s a day" % format(int(PB_PARAMS["min_traded_value"]), ",")
        series = [closes[sym][k] for k in sorted(closes.get(sym, {}))]
        b, bw = beta_vs_spy(closes.get(sym, {}), spy, spy_dates) if sym != SPY else (1.0, 0)
        o = outl.get(sym)
        trend = _num(tech[sym][3]) if sym in tech else None
        funds[sym] = {
            "sym": sym, "bucket": bucket, "area": area, "outlook_cat": ocat, "outlook_sub": osub,
            "eligible": reason is None, "reason": reason, "price": price, "adv": adv, "listed": bool(active),
            "vol63": swings(series), "beta": b, "beta_window": bw, "mom": momentum(series),
            "above_trend": above_trend(price, trend), "n_closes": len(series),
            "hedgeye": {"rr": o[1] if o else None, "etf": o[2] if o else None, "call": o[3] if o else None},
            "styles": [x.get("label") for x in styl.get(sym, []) if isinstance(x, dict) and x.get("label")],
            "final_code": fcall.get(sym),
        }
    return funds


# ---------------------------------------------------------------------------
# Source pool: names Hedgeye's own lists are bullish on (PS, GOANY, II, CALL, ETF, SSS, RR)
# ---------------------------------------------------------------------------
SOURCE_LABELS = {"PS": "Portfolio Selector", "GOANY": "Go-Anywhere ETFs", "II": "Investment Ideas", "CALL": "Calls",
                 "ETF": "ETF Pro", "SSS": "Signal Strength", "RR": "Risk Ranges"}


def source_bullish(code: str, outlook, weight, sign) -> bool:
    """One rule per source for 'Hedgeye is bullish on it'. PS / GOANY: on the list is enough."""
    o = str(outlook or "").strip().lower()
    if code in ("PS", "GOANY"):
        return True
    if code in ("II", "ETF", "RR"):
        return o in ("bullish", "long")
    if code == "CALL":
        return o in ("bullish", "long") or (_num(weight) is not None and _num(weight) > 0)
    if code == "SSS":
        return sign is not None and sign > 0
    return False


def source_pool(session, d: date, sources: list, problems: Optional[list] = None) -> dict:
    """{tos_symbol: [source codes]} of every on-list, bullish name in the chosen sources (drv_source_standing)."""
    codes = [c for c in (sources or []) if c in SOURCE_LABELS]
    if not codes:
        return {}
    rows = _q(session, "SELECT source_code, tos_symbol, outlook, weight, signal_sign FROM drv_source_standing "
                       "WHERE as_of_date = :d AND on_list AND source_code = ANY(:c)", {"d": d, "c": codes},
              problems, "drv_source_standing")
    pool: dict = {}
    for code, sym, outlook, weight, sign in rows:
        if sym and source_bullish(code, outlook, weight, sign):
            pool.setdefault(sym, [])
            if code not in pool[sym]:
                pool[sym].append(code)
    return {k: sorted(v) for k, v in pool.items()}


def source_names(session, d: date, sources: list, problems: Optional[list] = None, account: Optional[str] = None) -> list:
    """Every name on the ticked lists (Hedgeye lists, FUND = the fixed fund list, HELD = what the account holds),
    bullish or not, mapped or not: one row per name with its lists, asset class, factors and a status. 'usable'
    means the Builder can buy it (price, volume, in today's TOS export); a missing asset class does not block it
    because the user can assign one."""
    problems = problems if problems is not None else []
    codes = [c for c in (sources or []) if c in SOURCE_LABELS]
    on: dict = {}
    bull: set = set()
    if codes:
        for code, sym, outlook, weight, sign in _q(
                session, "SELECT source_code, tos_symbol, outlook, weight, signal_sign FROM drv_source_standing "
                         "WHERE as_of_date = :d AND on_list AND source_code = ANY(:c)", {"d": d, "c": codes},
                problems, "drv_source_standing"):
            if not sym or not source_bullish(code, outlook, weight, sign):
                continue
            on.setdefault(sym, set()).add(code)
            bull.add(sym)
    uni_bucket: dict = {}
    if "FUND" in (sources or []):
        for sym, bucket in _q(session, "SELECT tos_symbol, bucket FROM ref_pb_universe", None, problems, "ref_pb_universe"):
            on.setdefault(sym, set()).add("FUND")
            bull.add(sym)
            uni_bucket[sym] = bucket
    if "HELD" in (sources or []) and account and account != "ALL":
        g = account_groups(session, problems).get(account)
        pos = account_positions(session, g, d) if g else None
        for sym in ((pos or {}).get("holdings") or {}):
            on.setdefault(sym, set()).add("HELD")
            bull.add(sym)
    if not on:
        return []
    info = name_info(session, d, sorted(on), problems, uni_bucket)
    out = []
    for sym in sorted(on):
        out.append(dict(info[sym], sources=sorted(on[sym]), bullish=sym in bull))
    return out


def _quad_word(v) -> Optional[str]:
    s = str(v or "").strip().lower()
    if not s:
        return None
    return "bull" if s.startswith("bull") else ("bear" if s.startswith("bear") else "neutral")


def name_info(session, d: date, syms: list, problems: Optional[list] = None, uni_bucket: Optional[dict] = None) -> dict:
    """{sym: info} for any symbols: asset class, sector, beta, style tags, Quad view per Quad (Q1..Q4 as bull / neutral /
    bear, taken from the symbol's sector or asset class: Hedgeye gives no per-stock Quad view), and whether the Builder
    can buy it ('usable'). A missing asset class never blocks: the user can assign one."""
    problems = problems if problems is not None else []
    uni_bucket = uni_bucket or {}
    try:
        from api.routers.dash import _category_axis_map
        with session.begin_nested():
            ac = _category_axis_map(session, d, "asset_class")
            sec = _category_axis_map(session, d, "sector")
    except Exception as e:
        log.warning("name_info: pie map unavailable: %s", e)
        ac, sec = {}, {}
    om = outlook_map(session, problems)
    own = {r[0]: next((x for x in r[1:] if x), None) for r in _q(
        session, "SELECT tos_symbol, rr_outlook, etf_outlook, call_outlook FROM drv_outlooks "
                 "WHERE as_of_date = :d AND tos_symbol = ANY(:s)", {"d": d, "s": list(syms)}, None, "drv_outlooks")}
    uni, bucket_of = [], {}
    for sym in syms:
        b = _bucket_of(ac.get(sym))
        if b not in BUCKETS and uni_bucket.get(sym) in BUCKETS:
            b = uni_bucket[sym]
        bucket_of[sym] = b if b in BUCKETS else None
        uni.append((sym, b, sec.get(sym) or b, "Asset Class", b, True, None))   # active=True: class gaps do not block
    funds = fund_metrics(session, d, problems, uni_rows=uni)
    ind = {r[0]: r[1] for r in _q(session, "SELECT ticker, industry FROM ref_sector WHERE ticker = ANY(:s) AND industry IS NOT NULL",
                                  {"s": list(syms)}, problems, "ref_sector")}
    out = {}
    for sym in syms:
        f = funds.get(sym) or {}
        b, sector = bucket_of[sym], sec.get(sym)
        if b == "Equities" and sector and sector not in ("Unmapped", "Other"):
            cat, sub = "Equity Sectors", sector
        elif b == "Equities":
            cat, sub = "Asset Class", "Equities"
        else:
            cat, sub = "Asset Class", ("USD" if b == "Currency" else b)
        q = om.get(outlook_key(cat, sub)) if b else None
        reason = f.get("reason")
        out[sym] = {"sym": sym, "bucket": b, "sector": sector, "industry": ind.get(sym), "outlook": own.get(sym), "usable": True, "status": "Usable" if reason is None else "Usable (%s)" % reason,
                    "quad": [_quad_word(x) for x in q] if q else [None] * 4,
                    "beta": f.get("beta"), "styles": f.get("styles") or [], "final_code": f.get("final_code"),
                    "mom": f.get("mom"), "above_trend": f.get("above_trend"), "price": f.get("price")}
    return out


def exposure(values: dict, info: dict) -> dict:
    """Percent of the money in each factor. values = {sym: dollars}; info = name_info rows. Percent basis = the money
    in names with a known row (so Picked and Held are comparable). Styles / Quad can overlap, so rows need not add up."""
    from etl.derive_model_portfolio import FLAVOURS
    STYLE_GROUPS = {k: {t.lower() for t in v} for k, v in FLAVOURS.items() if v}
    tot = sum(v for s, v in values.items() if v > 0)
    out = {"total": tot, "beta": None, "asset": {}, "sector": {}, "style": {}, "quad": {}, "lowbeta": 0.0, "highbeta": 0.0}
    if tot <= 0:
        return out
    bsum = bw = 0.0
    quad = {q: {"bull": 0.0, "neutral": 0.0, "bear": 0.0, "none": 0.0} for q in range(4)}
    for sym, v in values.items():
        if v <= 0:
            continue
        r = info.get(sym) or {}
        p = v / tot * 100.0
        b = r.get("bucket") or "Unmapped"
        out["asset"][b] = out["asset"].get(b, 0.0) + p
        sec = r.get("sector") if b == "Equities" and r.get("sector") not in (None, "Unmapped", "Other") else b
        out["sector"][sec] = out["sector"].get(sec, 0.0) + p
        have = {str(t).lower() for t in (r.get("styles") or [])}
        for k, tags in STYLE_GROUPS.items():
            if have & tags:
                out["style"][k] = out["style"].get(k, 0.0) + p
        if r.get("beta") is not None:
            bsum += v
            bw += r["beta"] * v
            out["lowbeta"] += p if r["beta"] <= 0.8 else 0.0
            out["highbeta"] += p if r["beta"] > 1.2 else 0.0
        for i, w in enumerate(r.get("quad") or [None] * 4):
            quad[i][w or "none"] += p
    out["beta"] = (bw / bsum) if bsum else None
    out["quad"] = {"Q%d" % (i + 1): quad[i] for i in range(4)}
    return out


def pool_funds(session, d: date, sources: list, problems: Optional[list] = None, extra: Optional[list] = None,
               bucket_of: Optional[dict] = None) -> dict:
    """Fund dicts (same shape as fund_metrics) for the source pool. Bucket / area come from the SAME maps the
    Portfolio pie uses. SPY is added as a benchmark-only entry (never a pick) so accept can track against it."""
    problems = problems if problems is not None else []
    pool = source_pool(session, d, sources, problems)
    for sym in (extra or []):          # hand-picked names (any list, or held): always in the pool
        pool.setdefault(sym, [])
    if not pool:
        problems.append("No bullish names found in the chosen sources for this date")
        return {}
    try:
        from api.routers.dash import _category_axis_map
        with session.begin_nested():
            ac = _category_axis_map(session, d, "asset_class")
            sec = _category_axis_map(session, d, "sector")
    except Exception as e:
        log.warning("pool_funds: pie map unavailable: %s", e)
        ac, sec = {}, {}
    rows = []
    for sym in sorted(pool):
        bucket = (bucket_of or {}).get(sym) or _bucket_of(ac.get(sym))   # the user's own asset class wins
        sector = sec.get(sym)
        if bucket == "Equities" and sector and sector not in ("Unmapped", "Other"):
            area, cat, sub = sector, "Equity Sectors", sector
        elif bucket == "Equities":
            area, cat, sub = "Broad US", "Asset Class", "Equities"
        else:
            area, cat, sub = bucket, "Asset Class", ("USD" if bucket == "Currency" else bucket)
        rows.append((sym, bucket, area, cat, sub, bucket in BUCKETS,
                     None if bucket in BUCKETS else "Asset class not mapped"))
    if SPY not in pool:
        rows.append((SPY, "Equities", "Broad US", "Asset Class", "Equities", True, None))
    funds = fund_metrics(session, d, problems, uni_rows=rows)
    for sym, f in funds.items():
        f["sources"] = pool.get(sym, [])
        if not f.get("listed"):
            f["reason"] = "Asset class not mapped, so it can't be placed in a bucket"
    if SPY not in pool and SPY in funds:
        funds[SPY].update(eligible=False, reason="Benchmark only", listed=False)
    return funds


# ---------------------------------------------------------------------------
# Quad, outlook map, Risk Dial, presets
# ---------------------------------------------------------------------------
def outlook_map(session, problems: Optional[list] = None) -> dict:
    return {outlook_key(r[0], r[1]): [r[2], r[3], r[4], r[5]]
            for r in _q(session, "SELECT category, sub_category, quad1, quad2, quad3, quad4 FROM ref_quad_outlook",
                        None, problems, "ref_quad_outlook")}


def quad_context(session, d: date, horizon: str, problems: Optional[list] = None) -> dict:
    from etl.derive_macro import _norm_pcts, _dominant_quad_num

    class _R:  # tiny row shim for _norm_pcts
        def __init__(self, r):
            self.quad1_pct, self.quad2_pct, self.quad3_pct, self.quad4_pct = r[2], r[3], r[4], r[5]

    monthly, quarterly = {}, {}
    for r in _q(session, "SELECT year, period_num, quad1_pct, quad2_pct, quad3_pct, quad4_pct FROM ref_quad_periods "
                         "WHERE period_type = 'monthly' AND (quad1_pct IS NOT NULL OR quad2_pct IS NOT NULL "
                         "OR quad3_pct IS NOT NULL OR quad4_pct IS NOT NULL)", None, problems, "ref_quad_periods"):
        monthly[(r[0], r[1])] = _norm_pcts(_R(r))
    for r in _q(session, "SELECT year, period_num, quad FROM ref_quad_periods WHERE period_type = 'quarterly'", None, None, "quarterly quad"):
        q = _dominant_quad_num(None, r[2])
        if q:
            quarterly[(r[0], r[1])] = q
    chk = _q(session, "SELECT label_shown, target_quad FROM drv_quad_check WHERE as_of_date <= :d ORDER BY as_of_date DESC LIMIT 1",
             {"d": d}, None, "drv_quad_check")
    label, target = (chk[0][0], chk[0][1]) if chk else (None, None)
    h = PB_PARAMS["horizon_days"].get(horizon, 91)
    res = horizon_quad_mix(d, h, monthly, quarterly, label, target)
    res["check_label"] = label
    res["monthly"], res["quarterly"] = monthly, quarterly
    return res


def risk_dial(session, d: date):
    r = _q(session, "SELECT risk_budget, risk_label FROM drv_market_stat WHERE as_of_date = :d", {"d": d}, None, "drv_market_stat")
    if not r or r[0][0] is None:
        return None, None
    return round(float(r[0][0]) / 100.0, 2), r[0][1]


def presets(session, problems: Optional[list] = None) -> dict:
    out = {}
    for r in _q(session, "SELECT preset_key, label, mix, quad_tilt, note FROM ref_pb_mix_preset WHERE active "
                         "ORDER BY sort_order", None, problems, "ref_pb_mix_preset"):
        out[r[0]] = {"label": r[1], "mix": _j(r[2]) or {}, "quad_tilt": _num(r[3]), "note": r[4]}
    return out


# ---------------------------------------------------------------------------
# Accounts and holdings
# ---------------------------------------------------------------------------
def account_groups(session, problems: Optional[list] = None) -> dict:
    """{short_name: {'type', 'f': [acct...], 'cs': [acct...]}} for active accounts (grouped by short_name)."""
    rows = _q(session, "SELECT account_number, COALESCE(NULLIF(short_name, ''), account_number), source, account_type "
                       "FROM ref_accounts WHERE is_active = TRUE", None, None, "ref_accounts+type")
    if not rows:  # account_type column not there yet
        rows = [(r[0], r[1], r[2], None) for r in _q(session, "SELECT account_number, COALESCE(NULLIF(short_name, ''), account_number), "
                                                              "source FROM ref_accounts WHERE is_active = TRUE", None, problems, "ref_accounts")]
        if rows and problems is not None:
            problems.append("ref_accounts.account_type is missing: run python -m db.init_db")
    out: dict = {}
    for num, grp, src, typ in rows:
        g = out.setdefault(grp, {"type": None, "f": [], "cs": []})
        (g["f"] if str(src or "").upper() == "F" else g["cs"]).append(num)
        if typ:
            g["type"] = str(typ).upper()
    for g in out.values():
        g["type"] = g["type"] or "OTHER"
    return out


def _bucket_of(raw: Optional[str]) -> str:
    return _AC_ALIAS.get(raw or "", "Unmapped")


def account_positions(session, grp: dict, d: date) -> Optional[dict]:
    """Latest positions file of the account group <= the position ceiling. Cash via is_cash(). None if no file."""
    from etl._derive_common import position_ceiling
    ceil = position_ceiling(session, d)
    rows: list = []
    snaps = []
    for tbl, acol, vcol, ccol, pcol, tcol, accts in (
            ("hist_f", "account_number", "current_value", "cost_basis_total", "last_price", "type", grp["f"]),
            ("hist_cs", "account", "market_value", "cost_basis", "price", "security_type", grp["cs"])):
        if not accts:
            continue
        snap = _q(session, "SELECT MAX(snapshot_date) FROM %s WHERE %s = ANY(:a) AND snapshot_date <= :c" % (tbl, acol),
                  {"a": accts, "c": ceil}, None, tbl)
        s = snap[0][0] if snap else None
        if s is None:
            continue
        snaps.append(s)
        rows += _q(session,
                   "SELECT COALESCE(NULLIF(tos_symbol, ''), symbol), SUM(qty), SUM(%s), SUM(%s), MAX(%s), "
                   "BOOL_OR(is_cash(COALESCE(NULLIF(tos_symbol, ''), symbol), %s, description)) FROM %s "
                   "WHERE %s = ANY(:a) AND snapshot_date = :s GROUP BY 1" % (vcol, ccol, pcol, tcol, tbl, acol),
                   {"a": accts, "s": s}, None, tbl + " positions")
    if not snaps:
        return None
    gap = _q(session, "SELECT COUNT(DISTINCT export_date) FROM hist_td WHERE export_date > :s AND export_date <= :d",
             {"s": max(snaps), "d": d}, None, "file age")
    stale = bool(gap and (gap[0][0] or 0) > PB_PARAMS["positions_stale_days"])
    cash, hold = 0.0, {}
    for sym, qty, val, cost, price, is_cash in rows:
        if not sym:
            continue
        if is_cash:
            cash += float(val or 0)
            continue
        h = hold.setdefault(sym, {"qty": 0.0, "value": 0.0, "cost": 0.0, "price": None, "has_cost": False})
        h["qty"] += float(qty or 0)
        h["value"] += float(val or 0)
        if cost is not None:
            h["cost"] += float(cost)
            h["has_cost"] = True
        h["price"] = _num(price) or h["price"]
    for h in hold.values():
        if not h.pop("has_cost"):
            h["cost"] = None
    total = cash + sum(h["value"] for h in hold.values())
    return {"snap_date": max(snaps), "stale": stale, "holdings": hold, "cash": cash, "value": total}


def classify_holdings(session, d: date, pos: dict, funds: dict) -> None:
    """Fill bucket / area on each holding via the SAME map the Portfolio pie uses (_category_axis_map)."""
    try:
        from api.routers.dash import _category_axis_map
        with session.begin_nested():
            ac = _category_axis_map(session, d, "asset_class")
            sec = _category_axis_map(session, d, "sector")
    except Exception as e:
        log.warning("classify_holdings: pie map unavailable: %s", e)
        ac, sec = {}, {}
    areas = {f["area"] for f in funds.values()}
    for s, h in pos["holdings"].items():
        f = funds.get(s)
        h["bucket"] = f["bucket"] if f else _bucket_of(ac.get(s))
        if f:
            h["area"] = f["area"]
        else:
            sc = sec.get(s)
            h["area"] = sc if sc in areas else ("Broad US" if h["bucket"] == "Equities" else h["bucket"])
        h["is_cash"] = False


def current_mix(pos: dict) -> dict:
    """Bucket shares (percent of the account), cash included; Unmapped shown but never a target."""
    tot = pos["value"] or 0.0
    if tot <= 0:
        return {"Cash": 100.0}
    mix: dict = {}
    for h in pos["holdings"].values():
        mix[h["bucket"]] = mix.get(h["bucket"], 0.0) + h["value"] / tot * 100.0
    mix["Cash"] = pos["cash"] / tot * 100.0
    return {k: round(v, 4) for k, v in mix.items() if abs(v) > 1e-9}


def keep_list(session, short: str) -> list:
    return [r[0] for r in _q(session, "SELECT tos_symbol FROM ref_account_keep WHERE account_short = :a ORDER BY tos_symbol",
                             {"a": short}, None, "ref_account_keep")]


def lt_hold_symbols(session) -> list:
    return [r[0] for r in _q(session, "SELECT DISTINCT tos_symbol FROM ref_conviction_hold WHERE status = 'ACTIVE' AND "
                                      "COALESCE(direction, 'HOLD') = 'HOLD'", None, None, "ref_conviction_hold")] or \
        [r[0] for r in _q(session, "SELECT DISTINCT tos_symbol FROM ref_conviction_hold WHERE status = 'ACTIVE'", None, None, "ref_conviction_hold")]


def running_model(session, short: str):
    r = _q(session, "SELECT portfolio_id, name, horizon, end_date, status FROM user_model_portfolio WHERE account_short = :a "
                    "AND status IN ('PENDING', 'RUNNING') ORDER BY portfolio_id DESC LIMIT 1", {"a": short}, None, "user_model_portfolio")
    if not r:
        return None
    return {"portfolio_id": r[0][0], "name": r[0][1], "horizon": r[0][2], "end_date": r[0][3].isoformat() if r[0][3] else None, "status": r[0][4]}


def list_accounts(session, d: date) -> dict:
    problems: list = []
    funds = fund_metrics(session, d, problems)
    out = []
    groups = account_groups(session, problems)
    total_all = 0.0
    for short in sorted(groups):
        g = groups[short]
        pos = account_positions(session, g, d)
        if pos is None:
            continue
        classify_holdings(session, d, pos, funds)
        kept = keep_list(session, short)
        total_all += pos["value"]
        out.append({"short": short, "type": g["type"], "value": pos["value"], "snap_date": pos["snap_date"].isoformat(),
                    "stale": pos["stale"], "current_mix": current_mix(pos), "kept": kept,
                    "kept_value": sum(pos["holdings"][s]["value"] for s in kept if s in pos["holdings"]),
                    "running": running_model(session, short),
                    "holdings": [{"sym": s, "value": h["value"], "bucket": h["bucket"], "area": h["area"]}
                                 for s, h in sorted(pos["holdings"].items(), key=lambda kv: -kv[1]["value"])]})
    return {"accounts": out, "whole_book_value": total_all, "problems": problems}


def manual_kwargs(req: dict) -> dict:
    """load_context kwargs for a hand-picked build (req['manual'] + req['picks'] = [{sym, bucket, pct}]): the pool is
    exactly the picked names, each in the asset class the user gave it. Normal builds pass nothing extra."""
    if not (req or {}).get("manual"):
        return {}
    picks = [p for p in (req.get("picks") or []) if p.get("sym")]
    return {"extra": [p["sym"] for p in picks], "bucket_of": {p["sym"]: p.get("bucket") for p in picks if p.get("bucket") in BUCKETS},
            "use_keep": False}      # hand-picked: a held name you want is simply picked; saved 'keep as is' rows are ignored


def load_context(session, d: date, account: str, horizon: str, problems: Optional[list] = None,
                 sources: Optional[list] = None, extra: Optional[list] = None, bucket_of: Optional[dict] = None,
                 use_keep: bool = True):
    """Everything build_positions needs. account='ALL' = whole book (preview only).
    sources = Hedgeye source codes: the pick pool is those lists' bullish names instead of the fixed fund list."""
    problems = problems if problems is not None else []
    funds = pool_funds(session, d, sources, problems, extra, bucket_of) if (sources or extra) else fund_metrics(session, d, problems)
    groups = account_groups(session, problems)
    names = sorted(groups) if account == "ALL" else [account]
    merged = {"snap_date": None, "stale": False, "holdings": {}, "cash": 0.0, "value": 0.0}
    atype, kept = "OTHER", []
    for nm in names:
        g = groups.get(nm)
        if not g:
            continue
        pos = account_positions(session, g, d)
        if pos is None:
            continue
        classify_holdings(session, d, pos, funds)
        merged["snap_date"] = max(filter(None, [merged["snap_date"], pos["snap_date"]]))
        merged["stale"] = merged["stale"] or pos["stale"]
        merged["cash"] += pos["cash"]
        merged["value"] += pos["value"]
        for s, h in pos["holdings"].items():
            m = merged["holdings"].setdefault(s, dict(h, qty=0.0, value=0.0, cost=None))
            m["qty"] += h["qty"]
            m["value"] += h["value"]
            if h["cost"] is not None:
                m["cost"] = (m["cost"] or 0.0) + h["cost"]
        if account != "ALL":
            atype = g["type"]
            kept = keep_list(session, nm) if use_keep else []
    if account != "ALL" and not merged["snap_date"]:
        problems.append("No positions file found for account %s" % account)
    for s, h in merged["holdings"].items():
        if h.get("price") is None and funds.get(s):
            h["price"] = funds[s]["price"]
        elif funds.get(s) and funds[s].get("price") is None and h.get("price"):
            funds[s]["price"] = float(h["price"])      # not in the TOS export (e.g. a mutual fund): use the broker's price
    mult, label = risk_dial(session, d)
    ctx = {
        "D": d, "funds": funds, "outlook": outlook_map(session, problems), "quad": quad_context(session, d, horizon, problems),
        "risk_mult": mult, "risk_label": label, "presets": presets(session, problems),
        "kept": kept,
        "account": {"name": account, "type": atype, "value": merged["value"], "holdings": merged["holdings"], "cash": merged["cash"],
                    "current_mix": current_mix(merged) if merged["snap_date"] else {"Cash": 100.0},
                    "snap_date": merged["snap_date"], "stale": merged["stale"]},
        "problems": problems,
    }
    return ctx


_BT_CACHE: dict = {}
_BT_IN: dict = {}


def _bt_inputs(session, d: date, sources, horizon: str, problems: list):
    """Funds + closes + trend + Quad inputs for a back-test, cached per (day, sources, horizon)."""
    key = (d, tuple(sorted(sources or [])), horizon)
    if key in _BT_IN:
        return _BT_IN[key]
    funds = pool_funds(session, d, sources, problems) if sources else fund_metrics(session, d, problems)
    if not funds:
        return None
    syms = list(funds) + [SPY]
    closes = load_closes(session, syms, d, problems)
    trend = load_trend_history(session, syms, d)
    quad = quad_context(session, d, horizon, problems)
    base_ctx = {"outlook": outlook_map(session, problems), "presets": presets(session, problems),
                "quad_inputs": {"monthly": quad.get("monthly"), "quarterly": quad.get("quarterly")}}
    if len(_BT_IN) > 5:
        _BT_IN.clear()
    _BT_IN[key] = (funds, closes, trend, base_ctx)
    return _BT_IN[key]


def run_backtest(session, d: date, req: dict) -> dict:
    """"What would have happened": replays the build on past start dates (see builder_engine.backtest).
    INFORMATIONAL ONLY: it never removes or changes a pick. Cached per (D, request, horizon).
    Uses hist_quote_daily automatically if it ever has data."""
    import hashlib
    from etl.builder_engine import backtest
    horizon = req.get("horizon") or "3M"
    key = (d, horizon, hashlib.md5(json.dumps(req, sort_keys=True, default=str).encode()).hexdigest())
    if key in _BT_CACHE:
        return _BT_CACHE[key]
    problems: list = []
    inp = _bt_inputs(session, d, req.get("sources"), horizon, problems)
    if inp is None:
        return {"periods": [], "summary": {"periods": 0, "message": "Not enough history yet", "bars": []}, "problems": problems}
    funds, closes, trend, base_ctx = inp
    res = backtest(closes, trend, funds, base_ctx, req, horizon)
    res["problems"] = problems
    res["note"] = ("Uses today's fund list for old dates (survivorship, minor for big index funds). The Final Call skip, Hedgeye "
                   "outlooks and flavour filters are not replayed. Applies your recipe mechanically. Past results only, not a forecast.")
    if req.get("sources"):
        res["note"] += (" Source lists are replayed with TODAY'S membership (their past membership is not kept), "
                        "so names that were added because they already went up flatter the result. Information only: it never removes a pick.")
    if len(_BT_CACHE) > 50:
        _BT_CACHE.clear()
    _BT_CACHE[key] = res
    return res


COMPARE_VARIANTS = [("as_picked", "As picked", []), ("low_beta", "+ Low beta", ["low_beta"]),
                    ("quad", "+ Quad check", ["quad"]), ("both", "+ Both", ["low_beta", "quad"])]


def compare_variants(session, d: date, account: str, horizon: str, req: dict) -> dict:
    """Option B: the same source pool built with each validation check, side by side, plus a back-test per variant.
    The back-test is informational only: it never feeds back into which names are picked."""
    from etl.builder_engine import build_positions
    problems: list = []
    ctx = load_context(session, d, account, horizon, problems, sources=req.get("sources"))
    funds = ctx["funds"]
    out = []
    for key, label, checks in COMPARE_VARIANTS:
        r = dict(req, checks=checks)
        res = build_positions(ctx, r)
        pos = [x for x in res["positions"] if not x["is_kept"]]
        tv = sum(x["value"] for x in pos) or 0.0
        bw = [(x["value"], (funds.get(x["sym"]) or {}).get("beta")) for x in pos]
        bw = [(v, b) for v, b in bw if b is not None]
        removed = [s for s in res["skipped"] if s.get("kind") == "check"]
        try:
            bt = run_backtest(session, d, dict(r, account=account, horizon=horizon))
            bts = bt.get("summary")
        except Exception as e:  # never let the info-only back-test break the comparison
            log.warning("compare back-test failed: %s", e)
            bts = {"message": "Back-test unavailable", "periods": 0}
        out.append({"key": key, "label": label, "checks": checks, "n_positions": len(pos),
                    "invested_pct": (res.get("invested", 0.0) / res["amount"] * 100.0) if res["amount"] else None,
                    "cash_pct": (res.get("cash") or {}).get("pct"),
                    "beta": (sum(v * b for v, b in bw) / sum(v for v, _ in bw)) if bw else None,
                    "removed": [{"sym": s["sym"], "reason": s["reason"]} for s in removed],
                    "top": [{"sym": x["sym"], "weight": x["weight"], "sources": x.get("sources")}
                            for x in sorted(pos, key=lambda x: -x["value"])[:10]],
                    "backtest": bts})
    return {"variants": out, "problems": ctx["problems"], "pool_size": sum(1 for f in funds.values() if f.get("eligible"))}
