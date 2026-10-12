"""Live advice: frozen night plan + live checks (TASK_152; DESIGN_SPEC_3/4/5).

Two jobs, one module:

1. build_plan()  -> hist_advice_plan. One row per stock per trading account
   (ref_accounts.size_mult > 0) for the NEXT trading day, built after the
   end-of-day derive (derive_all step). Prices become LINES: trim line,
   over-max line, dip-buy line, buy-back line. It may be rewritten until
   09:30 ET on its plan_date, then it is frozen.

2. run_live_check() -> hist_advice_live. On every price pull compare the live
   price / day high / day low with the plan lines, set a signal per row (TRIM,
   TRIM_TO_MAX, DIP_BUY_STRONG/LIGHT, BUY_BACK, WAIT, SELL_ALL, SELL_SOME,
   BUY_IDEA, NONE), then apply tiers, merge, floor, budgets and ranking
   (DESIGN_SPEC_5 A1-A6 with the user's 2026-10-12 overrides: accounts are
   independent, Hold = snooze, one combined list with a Buy ideas section).

ADDITIVE ONLY: nothing here changes consolidated_action, final_code,
suggested_target_dollar, AMT$ or target_min/max_dollar. Sizes come from
drv_account_size (TASK_151). tos_symbol only. Idempotent: a check is keyed by
the price time it saw, so re-running the same check rewrites the same rows.

build_live_payload() feeds GET /api/actionable/live (api/routers/dash.py).
"""
from __future__ import annotations

import json
import logging
import statistics
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

RULE_VERSION = "TASK_152-v1"
ACCT_ORDER = {"IRA": 0, "F-A": 1, "F-M": 2}
_BUY_CODES = ("BM", "BMN", "BS")
_SELL_FAMILY = ("SA", "SS", "STM")
# live_rank (DESIGN_SPEC_3 section 6 order)
SIGNAL_RANK = {"TRIM_TO_MAX": 0, "SELL_ALL": 0, "TRIM": 1, "SELL_SOME": 1,
               "DIP_BUY_STRONG": 2, "BUY_BACK": 3, "BUY_IDEA": 3,
               "DIP_BUY_LIGHT": 4, "WAIT": 5, "NONE": 9}
TIER_ORDER = {"MUST": 0, "CONSIDER": 1, "BUYIDEA": 2, "INFO": 3}
_SETTING_DEFAULTS = {
    "overmax_any_day_ratio": "1.25", "must_overmax_ratio": "1.25",
    "today_floor_dollar": "1500", "today_must_budget": "5",
    "today_consider_budget": "8", "today_buyidea_budget": "5",
    "must_sellall_sources": "PS,II,CALL,RTA,SSSCHG,TOP5",
    "rank_edge_buyback": "1.2", "rank_edge_dip": "0.8", "rank_edge_sellsome": "0.5",
    "rank_edge_trim": "0.4", "rank_edge_trim_to_max": "0.3",
    "dont_sell_low_sd": "1.5", "sell_bounce_sd": "0.5", "sell_bounce_days": "5",
    "note_gain_pct": "20", "note_sector_share_pct": "35", "trim_sd": "1.5",
    "live_trim_trr_min_sd": "1.0", "live_overmax_sd": "1.0",
    "trim_over_max_pos_pct": "80", "dip_strong_sd": "1.5", "dip_light_sd": "2.0",
    "buyback_sd": "0.5", "buyback_days": "5", "buyback_bounce_sd": "0.25",
    "live_min_sd_pct": "0.5", "live_sd_cap_mult": "3", "live_sd_min_moves": "15",
    "live_price_stale_min": "45", "chase_day_range_pct": "80",
    "chase_risk_range_pct": "90", "plan_freeze_et": "09:30",
}


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def _f(v) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _et_tz():
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo("America/New_York")
    except Exception:  # tzdata missing: fixed EST fallback
        return timezone(timedelta(hours=-5))


def now_et() -> datetime:
    return datetime.now(_et_tz())


def load_settings(session: Session) -> dict:
    rows = session.execute(text(
        "SELECT setting_name, setting_value FROM ref_settings WHERE setting_name = ANY(:n)"),
        {"n": list(_SETTING_DEFAULTS)}).fetchall()
    raw = dict(_SETTING_DEFAULTS)
    raw.update({r[0]: r[1] for r in rows if r[1] is not None})
    out: dict = {}
    for k, v in raw.items():
        if k in ("must_sellall_sources", "plan_freeze_et"):
            out[k] = str(v)
        else:
            out[k] = float(v)
    out["_kept"] = {s.strip().upper() for s in out["must_sellall_sources"].split(",") if s.strip()}
    return out


def _holidays(session: Session) -> set:
    try:
        return {r[0] for r in session.execute(text("SELECT holiday_date FROM ref_holiday")).fetchall()}
    except Exception:
        return set()


def next_trading_day(session: Session, d: date) -> date:
    hol = _holidays(session)
    n = d + timedelta(days=1)
    while n.weekday() >= 5 or n in hol:
        n += timedelta(days=1)
    return n


def _trading_days_back(session: Session, anchor: date, n: int) -> list:
    rows = session.execute(text(
        "SELECT export_date FROM hist_td WHERE export_date <= :d "
        "GROUP BY export_date ORDER BY export_date DESC LIMIT :n"), {"d": anchor, "n": n}).scalars().all()
    return sorted(rows)


def _shares(dollars, price) -> Optional[int]:
    if not dollars or not price or price <= 0:
        return None
    return int(round(dollars / price))


# ---------------------------------------------------------------------------
# PLAN
# ---------------------------------------------------------------------------

def _closes(session: Session, symbols: list, anchor: date) -> dict:
    """{tos_symbol: [(date, close), ...] ascending}: last hist_y row per day,
    snapshot_date <= anchor, about 130 calendar days."""
    out: dict = {}
    rows = session.execute(text("""
        SELECT DISTINCT ON (tos_symbol, snapshot_date) tos_symbol, snapshot_date, last_price
        FROM hist_y
        WHERE tos_symbol = ANY(:s) AND last_price > 0
          AND snapshot_date <= :a AND snapshot_date >= :lo
        ORDER BY tos_symbol, snapshot_date, sequence DESC
    """), {"s": symbols, "a": anchor, "lo": anchor - timedelta(days=130)}).fetchall()
    for sym, d, px in rows:
        out.setdefault(sym, []).append((d, float(px)))
    return out


def compute_sd(series: list, st: dict) -> tuple:
    """(prior_close, prior_close_date, sd20, note). SD20 = population SD of the
    last 20 close-to-close moves ending at the prior close (matches the spec's
    TXG 84.24 line). Capped to the 60-day median when above cap x median."""
    if not series:
        return None, None, None, "no_price"
    closes = [p for _, p in series]
    prior, pdate = closes[-1], series[-1][0]
    moves = [closes[i] / closes[i - 1] - 1.0 for i in range(1, len(closes))]
    if len(moves) < int(st["live_sd_min_moves"]):
        return prior, pdate, None, "few_moves"
    last20 = moves[-20:]
    sd = statistics.pstdev(last20)
    note = "ok"
    roll = [statistics.pstdev(moves[j - 19:j + 1]) for j in range(max(19, len(moves) - 60), len(moves))]
    if len(roll) >= 5:
        med = statistics.median(roll)
        if med > 0 and sd > st["live_sd_cap_mult"] * med:
            sd, note = med, "capped_to_median"
    if sd * 100.0 < st["live_min_sd_pct"]:
        return prior, pdate, sd, "low_sd"
    return prior, pdate, sd, note


def _recent_trades(session: Session, anchor: date, days: int, acct_short: dict) -> dict:
    """{(short, tos_symbol): {sold_qty, sold_dollar, bought_qty, last_sell_date}}
    over the last `days` trading days up to the anchor (hist_cst + hist_ft)."""
    window = _trading_days_back(session, anchor, int(days))
    if not window:
        return {}
    lo = window[0]
    out: dict = {}

    def add(short, sym, kind, qty, price, d):
        if not short or not sym or qty is None:
            return
        r = out.setdefault((short, sym), {"sold_qty": 0.0, "sold_dollar": 0.0,
                                          "bought_qty": 0.0, "last_sell_date": None})
        q = abs(float(qty))
        if kind == "SELL":
            r["sold_qty"] += q
            r["sold_dollar"] += q * float(price or 0)
            if r["last_sell_date"] is None or d > r["last_sell_date"]:
                r["last_sell_date"] = d
        else:
            r["bought_qty"] += q

    for acct, sym, d, act, qty, px in session.execute(text("""
        SELECT account, tos_symbol, trade_date, action, quantity, price FROM hist_cst
        WHERE trade_date >= :lo AND trade_date <= :a AND tos_symbol IS NOT NULL
          AND lower(action) IN ('buy','sell')
    """), {"lo": lo, "a": anchor}).fetchall():
        add(acct_short.get(acct), sym, "SELL" if act.lower() == "sell" else "BUY", qty, px, d)
    for acct, sym, d, kind, qty, px in session.execute(text("""
        SELECT account_number, tos_symbol, trade_date, action_kind, quantity, price FROM hist_ft
        WHERE trade_date >= :lo AND trade_date <= :a AND tos_symbol IS NOT NULL
          AND action_kind IN ('BUY','SELL')
    """), {"lo": lo, "a": anchor}).fetchall():
        add(acct_short.get(acct), sym, kind, qty, px, d)
    return out


def _positions(session: Session, sizes_by_acct: dict) -> dict:
    """{short: {'cash': x, 'pos': {sym: (qty, value, cost)}}} at each account's
    size-table value_date (the same position file drv_account_size used)."""
    accts = session.execute(text("""
        SELECT account_number, short_name, source FROM ref_accounts
        WHERE is_active AND size_mult > 0 AND short_name IS NOT NULL AND account_number <> '85911'
    """)).fetchall()
    by_short: dict = {}
    for num, short, src in accts:
        by_short.setdefault(short, {"cs": [], "f": []})["cs" if src == "CS" else "f"].append(num)
    out: dict = {}
    for short, vdate in sizes_by_acct.items():
        a = by_short.get(short)
        if not a or vdate is None:
            continue
        pos: dict = {}
        cash = 0.0
        if a["cs"]:
            rows = session.execute(text("""
                SELECT tos_symbol, symbol, security_type, description, qty, market_value, cost_basis
                FROM hist_cs WHERE account = ANY(:a) AND snapshot_date = :d
            """), {"a": a["cs"], "d": vdate}).fetchall()
        else:
            rows = session.execute(text("""
                SELECT tos_symbol, symbol, type, description, qty, current_value, cost_basis_total
                FROM hist_f WHERE account_number = ANY(:a) AND snapshot_date = :d
            """), {"a": a["f"], "d": vdate}).fetchall()
        for tsym, sym, stype, desc, qty, val, cost in rows:
            is_cash = (str(sym or "") in ("SPAXX**", "Cash & Cash Investments")
                       or "HELD IN MONEY MARKET" in str(desc or "").upper()
                       or str(stype or "") == "Cash and Money Market")
            if is_cash:
                cash += float(val or 0)
                continue
            if str(sym or "").upper() == "PENDING ACTIVITY" or not tsym:
                continue
            q, v, c = pos.get(tsym, (0.0, 0.0, None))
            c2 = c if cost is None else (c or 0.0) + float(cost)
            pos[tsym] = (q + float(qty or 0), v + float(val or 0), c2)
        out[short] = {"cash": cash, "pos": pos}
    return out


def _source_flags(source_actions, winning_source, kept: set) -> dict:
    acts = source_actions if isinstance(source_actions, list) else []
    win_act = None
    kept_remove = False
    for a in acts:
        src = str(a.get("source") or "").upper()
        act = str(a.get("action") or "").upper()
        if src == str(winning_source or "").upper():
            win_act = act
        if src in kept and act == "REMOVE":
            kept_remove = True
    return {"winning_action": win_act, "kept_remove": kept_remove}


def _plan_frozen(plan_date: date, st: dict, now: datetime) -> bool:
    hh, mm = (int(x) for x in str(st["plan_freeze_et"]).split(":")[:2])
    freeze = datetime.combine(plan_date, time(hh, mm), tzinfo=_et_tz())
    return now >= freeze


def build_plan(session: Session, anchor: date, plan_date: Optional[date] = None,
               force: bool = False, now: Optional[datetime] = None,
               rule_version: str = RULE_VERSION) -> dict:
    """Write hist_advice_plan for plan_date (default: next trading day after
    the anchor). Skips when the plan exists and is frozen (>= 09:30 ET on
    plan_date) unless force=True (replays)."""
    st = load_settings(session)
    now = now or now_et()
    plan_date = plan_date or next_trading_day(session, anchor)
    have = session.execute(text(
        "SELECT COUNT(*) FROM hist_advice_plan WHERE plan_date = :p"), {"p": plan_date}).scalar() or 0
    if have and not force and _plan_frozen(plan_date, st, now):
        return {"skipped": "frozen", "plan_date": str(plan_date), "rows": have}

    sizes = session.execute(text("""
        SELECT tos_symbol, account_short, category, account_value, size_mult, value_date,
               min_dollar, max_dollar, unit_dollar, min_raw, max_raw, unit_raw, held_dollar
        FROM drv_account_size WHERE as_of_date = :d
    """), {"d": anchor}).mappings().all()
    if not sizes:
        return {"skipped": "no_account_sizes", "plan_date": str(plan_date), "rows": 0}
    acct_vdate = {}
    for r in sizes:
        acct_vdate[r["account_short"]] = r["value_date"]
    symbols = sorted({r["tos_symbol"] for r in sizes})

    act = {r["tos_symbol"]: r for r in session.execute(text("""
        SELECT tos_symbol, final_action, final_code, final_side, winning_source, source_actions,
               low_confidence, stop_breached, sector, trend_line_value
        FROM drv_actionable WHERE as_of_date = :d AND tos_symbol = ANY(:s)
    """), {"d": anchor, "s": symbols}).mappings().all()}
    rr = {r["tos_symbol"]: r for r in session.execute(text(
        "SELECT tos_symbol, lrr, trr, outlook FROM drv_rr WHERE as_of_date = :d AND tos_symbol = ANY(:s)"),
        {"d": anchor, "s": symbols}).mappings().all()}
    prev_d = session.execute(text("SELECT MAX(as_of_date) FROM drv_rr WHERE as_of_date < :d"),
                             {"d": anchor}).scalar()
    prev_out = {r[0]: r[1] for r in session.execute(text(
        "SELECT tos_symbol, outlook FROM drv_rr WHERE as_of_date = :d AND tos_symbol = ANY(:s)"),
        {"d": prev_d, "s": symbols}).fetchall()} if prev_d else {}
    macro = {r[0] for r in session.execute(text("""
        SELECT DISTINCT tos_ticker FROM ref_rrt
        WHERE tos_ticker = ANY(:s) AND (y_ticker LIKE '^%' OR y_ticker LIKE '%=F' OR y_ticker LIKE '%=X')
    """), {"s": symbols}).fetchall()}
    cash_syms = {r[0] for r in session.execute(text(
        "SELECT x FROM unnest(CAST(:s AS text[])) AS x WHERE is_cash(x, NULL, NULL)"),
        {"s": symbols}).fetchall()}
    earn = {r[0]: r[1] for r in session.execute(text(
        "SELECT tos_symbol, earnings_days FROM drv_technicals WHERE as_of_date = :d AND tos_symbol = ANY(:s)"),
        {"d": anchor, "s": symbols}).fetchall()}
    closes = _closes(session, symbols, anchor)
    acct_short = {r[0]: r[1] for r in session.execute(text(
        "SELECT account_number, short_name FROM ref_accounts WHERE short_name IS NOT NULL")).fetchall()}
    trades = _recent_trades(session, anchor, int(st["buyback_days"]), acct_short)
    positions = _positions(session, acct_vdate)

    # household held / cost per symbol (trading accounts) and sector shares
    hh_val: dict = {}
    hh_cost: dict = {}
    for short, p in positions.items():
        for sym, (q, v, c) in p["pos"].items():
            hh_val[sym] = hh_val.get(sym, 0.0) + v
            if c is not None:
                hh_cost[sym] = hh_cost.get(sym, 0.0) + c
    try:
        from etl.derive_category_perf import _canon_sector
    except Exception:  # pragma: no cover - import guard
        def _canon_sector(s):
            return s
    sector_val: dict = {}
    for sym, v in hh_val.items():
        sec = _canon_sector((act.get(sym) or {}).get("sector"))
        if sec and v > 0:
            sector_val[sec] = sector_val.get(sec, 0.0) + v
    book = sum(sector_val.values())

    kept = st["_kept"]
    by_sym: dict = {}
    for r in sizes:
        by_sym.setdefault(r["tos_symbol"], []).append(r)

    rows_out = []
    for sym, srows in by_sym.items():
        a = act.get(sym) or {}
        flags = _source_flags(a.get("source_actions"), a.get("winning_source"), kept)
        code = str(a.get("final_code") or "").upper()
        win_src = str(a.get("winning_source") or "").upper()
        win_act = flags["winning_action"]
        low_conf = bool(a.get("low_confidence"))
        held_any = any((p["pos"].get(sym, (0, 0, None))[0] or 0) > 0 for p in positions.values())
        kept_sell = (code in _SELL_FAMILY and win_src in kept and win_act in ("REMOVE", "REDUCE")
                     and not low_conf)
        kept_sellall = kept_sell and code == "SA"
        kept_sellsome = kept_sell and code in ("SS", "STM")
        r_ = rr.get(sym) or {}
        outlook = r_.get("outlook")
        bullish = str(outlook or "").strip().lower() == "bullish"
        prev_bull = str(prev_out.get(sym) or "").strip().lower() == "bullish"
        stop = bool(a.get("stop_breached"))
        is_macro = sym in macro
        is_cash = sym in cash_syms
        prior, pdate, sd, sd_note = compute_sd(closes.get(sym, []), st)
        lrr, trr = _f(r_.get("lrr")), _f(r_.get("trr"))
        sector = _canon_sector(a.get("sector"))
        sec_share = (sector_val.get(sector, 0.0) / book * 100.0) if (book > 0 and sector) else None
        ed = _f(earn.get(sym))
        earnings_gap = ed is not None and ed != -99 and -1 <= ed <= 0
        sold_any = [(s["account_short"], trades.get((s["account_short"], sym))) for s in srows]
        sold_recent = any(t and t["sold_qty"] > t["bought_qty"] for _, t in sold_any)
        dip_eligible = (bullish and not is_cash and not is_macro and not stop) or sold_recent
        buy_side = code in _BUY_CODES
        dip_tier = ("Strong" if buy_side else "Light") if dip_eligible else None
        dip_mult = st["dip_strong_sd"] if dip_tier == "Strong" else st["dip_light_sd"]
        sd_ok = sd is not None and sd_note not in ("few_moves", "low_sd", "no_price")
        hv_total = hh_val.get(sym)
        hc = hh_cost.get(sym)
        gain_pct = ((hv_total - hc) / hc * 100.0) if (hv_total and hc and hc > 0) else None

        # which accounts hold it; starter order among non-holding accounts
        info = {}
        for s in srows:
            sh = s["account_short"]
            pos = positions.get(sh, {"cash": 0.0, "pos": {}})
            q, v, _c = pos["pos"].get(sym, (0.0, 0.0, None))
            info[sh] = {"row": s, "qty": q, "held": _f(s["held_dollar"]) or 0.0,
                        "cash": pos["cash"], "min": _f(s["min_dollar"]) or 0.0,
                        "max": _f(s["max_dollar"]) or 0.0, "unit": _f(s["unit_dollar"]) or 0.0}
        holders = [sh for sh, i in info.items() if i["held"] > 0]
        room = [sh for sh in holders if info[sh]["held"] < info[sh]["max"]]
        starter_pool = []
        if dip_eligible and (not holders or not room):
            for sh, i in info.items():
                if sh in holders or i["min"] <= 0 or i["cash"] < i["min"]:
                    continue
                starter_pool.append(sh)
            starter_pool.sort(key=lambda sh: (-(info[sh]["min"] - info[sh]["held"]), -info[sh]["cash"],
                                              ACCT_ORDER.get(sh, 9)))
        starter_first = starter_pool[0] if starter_pool else None

        for sh, i in info.items():
            s = i["row"]
            held, mx, unit, mn = i["held"], i["max"], i["unit"], i["min"]
            trim_line = ovr_line = trim_size = None
            over_ratio = (held / mx) if (mx > 0 and held > mx) else None
            if sd_ok and prior and held > 0:
                a_line = prior * (1 + st["trim_sd"] * sd)
                b_line = max(trr, prior * (1 + st["live_trim_trr_min_sd"] * sd)) if trr else None
                trim_line = min(a_line, b_line) if b_line else a_line
                trim_size = min(unit, held) if unit > 0 else None
            if sd_ok and prior and over_ratio:
                cand = [prior * (1 + st["live_overmax_sd"] * sd)]
                if trr and lrr is not None and trr > lrr:
                    cand.append(lrr + st["trim_over_max_pos_pct"] / 100.0 * (trr - lrr))
                ovr_line = min(cand)
            dip_line = dip_size = None
            st_order = None
            if sd_ok and prior and dip_tier:
                dip_line = prior * (1 - dip_mult * sd)
                if sh in holders:
                    if held < mx and unit > 0:
                        dip_size = min(unit, mx - held)
                elif sh in starter_pool:
                    st_order = starter_pool.index(sh) + 1
                    dip_size = mn if st_order == 1 else 0.0
            t = trades.get((sh, sym))
            last_px = last_dt = bb_line = bb_size = None
            if t and t["sold_qty"] > 0:
                net = t["sold_qty"] - t["bought_qty"]
                avg = t["sold_dollar"] / t["sold_qty"]
                last_px, last_dt = avg, t["last_sell_date"]
                if net > 0 and sd_ok and prior:
                    bb_line = avg - st["buyback_sd"] * sd * prior
                    sold_dollar = net * avg
                    room_d = (mx - held) if mx > 0 else sold_dollar
                    bb_size = max(0.0, min(sold_dollar, room_d))
            rows_out.append({
                "plan_date": plan_date, "tos_symbol": sym, "account_short": sh, "anchor_date": anchor,
                "final_action": a.get("final_action"), "final_code": code or None,
                "final_side": a.get("final_side"), "winning_source": win_src or None,
                "winning_action": win_act, "kept_sellall": kept_sellall, "kept_sellsome": kept_sellsome,
                "kept_remove": flags["kept_remove"], "low_confidence": low_conf, "outlook": outlook,
                "outlook_turned": bool(prev_bull and not bullish), "stop_breached": stop,
                "is_cash": is_cash, "is_macro": is_macro, "sector": sector,
                "trend_line": _f(a.get("trend_line_value")), "earnings_gap": earnings_gap,
                "account_value": _f(s["account_value"]), "value_date": s["value_date"],
                "size_mult": _f(s["size_mult"]), "account_cash": i["cash"], "category": s["category"],
                "min_raw": _f(s["min_raw"]), "max_raw": _f(s["max_raw"]), "unit_raw": _f(s["unit_raw"]),
                "min_dollar": mn, "max_dollar": mx, "unit_dollar": unit,
                "held_dollar": held, "held_shares": i["qty"], "gain_pct": gain_pct,
                "sector_share_pct": sec_share if held > 0 else None, "over_ratio": over_ratio,
                "prior_close": prior, "prior_close_date": pdate, "sd20": sd, "sd_note": sd_note,
                "lrr": lrr, "trr": trr, "trim_line": trim_line, "overmax_trim_line": ovr_line,
                "trim_size": trim_size, "dip_eligible": dip_eligible, "dip_tier": dip_tier,
                "dip_line": dip_line, "dip_size": dip_size, "starter_account": starter_first,
                "starter_order": st_order, "last_sell_price": last_px, "last_sell_date": last_dt,
                "buyback_line": bb_line, "buyback_size": bb_size, "rule_version": rule_version,
            })

    # keep rows that can ever matter: held anywhere, dip-eligible, or sold recently
    keep_syms = set()
    for r in rows_out:
        if (r["held_dollar"] or 0) > 0 or r["dip_eligible"] or r["last_sell_price"]:
            keep_syms.add(r["tos_symbol"])
    held_syms = {r["tos_symbol"] for r in rows_out if (r["held_dollar"] or 0) > 0}
    rows_out = [r for r in rows_out if r["tos_symbol"] in keep_syms | held_syms]

    session.execute(text("DELETE FROM hist_advice_plan WHERE plan_date = :p"), {"p": plan_date})
    if rows_out:
        cols = list(rows_out[0].keys())
        session.execute(text(
            "INSERT INTO hist_advice_plan (" + ", ".join(cols) + ", made_at) VALUES ("
            + ", ".join(":" + c for c in cols) + ", NOW())"), rows_out)
    session.commit()
    log.info("build_plan %s (anchor %s): %d rows, %d symbols", plan_date, anchor,
             len(rows_out), len({r['tos_symbol'] for r in rows_out}))
    return {"plan_date": str(plan_date), "anchor": str(anchor), "rows": len(rows_out),
            "symbols": len({r["tos_symbol"] for r in rows_out})}


def build_plan_safe(session: Session, anchor: date, parent_run_id=None) -> int:
    """derive_all() step signature (session, as_of_date, parent_run_id)."""
    cur = session.execute(text("SELECT MAX(export_date) FROM hist_td")).scalar()
    if cur is None or anchor != cur:     # history / forward re-derives never plan
        return 0
    res = build_plan(session, anchor)
    return int(res.get("rows") or 0)


# ---------------------------------------------------------------------------
# LIVE CHECK
# ---------------------------------------------------------------------------

def load_live_prices(session: Session, plan_date: date) -> dict:
    """{tos_symbol: {last, high, low, time (aware), source}} for prices seen on
    plan_date (ET). Yahoo cache first; a fresher TOSL quote (drv_quote, intraday
    on the anchor) wins when its loaded_at is later."""
    out: dict = {}
    for sym, last, hi, lo, fat in session.execute(text("""
        SELECT tos_symbol, last_price, high_price, low_price, fetched_at
        FROM cache_yahoo_quote
        WHERE fetch_status = 'ok' AND last_price IS NOT NULL AND fetched_at IS NOT NULL
          AND (fetched_at AT TIME ZONE 'America/New_York')::date = :p
    """), {"p": plan_date}).fetchall():
        out[sym] = {"last": float(last), "high": _f(hi), "low": _f(lo), "time": fat, "source": "yahoo"}
    for sym, last, hi, lo, la in session.execute(text("""
        SELECT tos_symbol, last_price, high_price, low_price, loaded_at FROM drv_quote
        WHERE as_of_date = (SELECT MAX(as_of_date) FROM drv_quote WHERE as_of_date < :p)
          AND export_date = :p AND last_price IS NOT NULL AND loaded_at IS NOT NULL
    """), {"p": plan_date}).fetchall():
        t = la.astimezone() if la.tzinfo is None else la
        cur = out.get(sym)
        if cur is None or t > cur["time"]:
            out[sym] = {"last": float(last), "high": _f(hi), "low": _f(lo), "time": t, "source": "tosl"}
    return out


def load_prices_from_hist_y(session: Session, day: date) -> dict:
    """Replay prices: the day's last hist_y row (close / high / low), stamped
    16:00 ET. Used to replay a past day with stored data only."""
    t = datetime.combine(day, time(16, 0), tzinfo=_et_tz())
    out: dict = {}
    for sym, last, hi, lo in session.execute(text("""
        SELECT DISTINCT ON (tos_symbol) tos_symbol, last_price, high_price, low_price
        FROM hist_y WHERE snapshot_date = :d AND last_price > 0 AND tos_symbol IS NOT NULL
        ORDER BY tos_symbol, sequence DESC
    """), {"d": day}).fetchall():
        out[sym] = {"last": float(last), "high": _f(hi), "low": _f(lo), "time": t, "source": "hist_y"}
    return out


def _pvv_line(pvv: Optional[dict]) -> Optional[str]:
    if not pvv:
        return None
    ts = pvv.get("at")
    hm = ts.astimezone(_et_tz()).strftime("%H:%M") if ts else ""
    sig = pvv.get("sig_today")
    return f"PVV today: {pvv.get('decision') or 'n/a'}" + (f" (today {sig})" if sig else "") + (f" · {hm}" if hm else "")


def evaluate_row(p: dict, px: Optional[dict], st: dict, ctx: dict) -> dict:
    """One plan row against one price -> a line dict (signal NONE when nothing
    fires). `ctx`: conviction (HOLD/AVOID/None), first_bounce (prior caution
    bounce price today), pvv (dict), stale (bool)."""
    sym, acct = p["tos_symbol"], p["account_short"]
    held = _f(p["held_dollar"]) or 0.0
    mx = _f(p["max_dollar"]) or 0.0
    unit = _f(p["unit_dollar"]) or 0.0
    prior, sd = _f(p["prior_close"]), _f(p["sd20"])
    sd_ok = bool(sd) and bool(prior) and p["sd_note"] not in ("few_moves", "low_sd", "no_price")
    code = (p["final_code"] or "").upper()
    price = hi = lo = None
    if px and not ctx.get("stale"):
        price, hi, lo = px["last"], px["high"] or px["last"], px["low"] or px["last"]
        hi, lo = max(hi, price), min(lo, price)
    line = {"tos_symbol": sym, "account_short": acct, "signal": "NONE", "side": None, "size_dollar": None,
            "shares": None, "limit_price": None, "price_kind": None, "reason": None, "evidence": None,
            "tier_hint": "INFO", "kind": None, "caution": None, "bounce_price": None, "chase": False,
            "pvv_line": None, "price": px["last"] if px else None, "day_high": px["high"] if px else None,
            "day_low": px["low"] if px else None, "ratio": None, "extra": {}}
    blocked_buy = (code == "SA" or bool(p["stop_breached"]) or ctx.get("conviction") == "AVOID")
    cands = []

    # SELL ALL (kept source) -- every holding account, whole position
    if p["kept_sellall"] and held > 0:
        cands.append(("SELL_ALL", "sell", held, None, "now", "MUST", "sellall",
                      f"{p['winning_source']} dropped it" if p["winning_action"] == "REMOVE"
                      else f"{p['winning_source']} cut it", "good"))
    else:
        # T2: over max -> sell back to max
        ratio = (held / mx) if (mx > 0 and held > mx) else None
        t2 = None
        if ratio and p["sd_note"] != "low_sd":
            any_day = ratio > st["overmax_any_day_ratio"]
            line_px = _f(p["overmax_trim_line"])
            price_hit = sd_ok and hi is not None and line_px is not None and hi >= line_px
            if any_day or price_hit:
                size = held - mx
                must = ratio > st["must_overmax_ratio"]
                # 2026-10-12 (user): over-max is housekeeping, not a timing call -> INFO only
                # (visible in the LIVE column + tooltip, never in Act / required).
                t2 = ("TRIM_TO_MAX", "sell", size, price if price else prior, "now",
                      "INFO", "trim_to_max",
                      (f"{ratio:.1f}× over max" if must else "over max, price up"),
                      "good" if must else "weak")
                line["ratio"] = ratio
        # T1: spike trim
        t1 = None
        tl = _f(p["trim_line"])
        ts = _f(p["trim_size"])
        if sd_ok and tl and ts and hi is not None and hi >= tl:
            moves = (hi / prior - 1.0) / sd if prior else None
            t1 = ("TRIM", "sell", ts, tl, "limit_ge", "CONSIDER", "trim",
                  f"up {moves:.1f} normal moves" if moves is not None else "spike", "weak")
        if t1 and t2:
            cands.append(t1)  # the spike trim is the timing call; over-max is info only
        elif t2 or t1:
            cands.append(t2 or t1)
        # SELL SOME from a kept source: one unit
        if not cands and p["kept_sellsome"] and held > 0 and unit > 0:
            cands.append(("SELL_SOME", "sell", min(unit, held), None, "now", "CONSIDER", "sellsome",
                          f"{p['winning_source']} cut its weight", "fair"))

    # buys (blocked by SELL ALL / stop / Avoid; buy-back also by a kept REMOVE)
    sell_chosen = bool(cands)
    if not blocked_buy and not p["kept_sellall"] and sd_ok and lo is not None:
        dl, ds = _f(p["dip_line"]), _f(p["dip_size"])
        if p["dip_tier"] and dl and ds and ds > 0 and lo <= dl:
            held_acct = held > 0
            strong = p["dip_tier"] == "Strong"
            reason = ("dip on buy call" if strong else "dip, no buy call")
            cands.append(("DIP_BUY_STRONG" if strong else "DIP_BUY_LIGHT", "buy", ds, dl, "limit_le",
                          "CONSIDER" if strong else "INFO", "dip",
                          reason, "weak", "ADD" if held_acct else "START"))
        bl, bs = _f(p["buyback_line"]), _f(p["buyback_size"])
        if bl and bs and bs > 0 and not p["kept_remove"] and lo <= bl:
            if price is not None and prior is not None and price >= prior:
                cands.append(("BUY_BACK", "buy", bs, bl, "limit_le", "CONSIDER", "buyback",
                              "cheaper re-entry below your sale", "fair"))
            else:
                cands.append(("WAIT", "buy", None, None, None, "INFO", "wait",
                              "buy-back line reached, still falling", None))

    # choose
    chosen = None
    if cands:
        sells = [c for c in cands if c[1] == "sell"]
        buys = [c for c in cands if c[1] == "buy"]
        if sells and buys and prior is not None and price is not None:
            # TRIM vs DIP in one account: the later move wins (price side is the proxy)
            chosen = sells[0] if price >= prior else buys[0]
            line["extra"]["also"] = (buys[0] if chosen is sells[0] else sells[0])[0]
        elif sells:
            chosen = sells[0]
        else:
            order = {"BUY_BACK": 0, "DIP_BUY_STRONG": 1, "DIP_BUY_LIGHT": 2, "WAIT": 3}
            chosen = sorted(buys, key=lambda c: order.get(c[0], 9))[0]
            if len(buys) > 1:
                line["extra"]["also"] = [c[0] for c in buys if c is not chosen][0]
    if chosen:
        sig, side, size, lpx, kind, tier, ekind, reason, ev = chosen[:9]
        line.update({"signal": sig, "side": side, "size_dollar": size, "limit_price": lpx,
                     "price_kind": kind, "tier_hint": tier, "kind": ekind, "reason": reason, "evidence": ev})
        if len(chosen) > 9:
            line["extra"]["verb"] = chosen[9]
        ref_px = lpx if (kind in ("limit_ge", "limit_le") and lpx) else (price or prior)
        line["shares"] = _shares(size, ref_px)

    # caution: Final Call SELL SOME/STM under a live buy
    if line["side"] == "buy" and code in ("SS", "STM"):
        line["caution"] = "Last night's call was SELL SOME"
    # chase tag
    if line["side"] == "buy" and price is not None and lo is not None and hi is not None:
        rng = hi - lo
        top = rng > 0 and (price - lo) / rng >= st["chase_day_range_pct"] / 100.0
        lrr, trr = _f(p["lrr"]), _f(p["trr"])
        hi_rr = trr and lrr is not None and trr > lrr and (price - lrr) / (trr - lrr) >= st["chase_risk_range_pct"] / 100.0
        line["chase"] = bool(top or hi_rr)
    # PVV on WAIT
    if line["signal"] == "WAIT":
        line["pvv_line"] = _pvv_line(ctx.get("pvv"))

    # G1: "Don't sell the low" -- held, down >= 1.5 SD, a sell path active
    if held > 0 and sd_ok and price is not None and price <= prior * (1 - st["dont_sell_low_sd"] * sd):
        sell_path = (bool(p["stop_breached"]) or code in _SELL_FAMILY
                     or (p["winning_action"] in ("REMOVE", "REDUCE"))
                     or line["signal"] == "TRIM_TO_MAX")
        exempt = (str(p["winning_source"] or "") in ("CALL", "RTA", "TOP5")
                  and p["winning_action"] in ("REMOVE", "REDUCE"))
        tl_ = _f(p["trend_line"])
        trend_break = tl_ is not None and prior >= tl_ and price < tl_
        if sell_path and not exempt and not trend_break and not p["earnings_gap"]:
            downs = (prior - price) / (prior * sd)
            bounce = ctx.get("first_bounce") or round(price + st["sell_bounce_sd"] * sd * prior, 2)
            g1 = (f"Down {downs:.1f} normal moves today. Your past full exits on days like this: "
                  f"the stock was higher 5 days later on average (+1.6%), about half the time.")
            line["caution"] = (line["caution"] + "\n" + g1) if line["caution"] else g1
            line["bounce_price"] = bounce
            line["extra"]["bounce_days"] = int(st["sell_bounce_days"])
            if line["side"] == "sell":
                line["extra"]["wants_limit"] = True
                line["limit_price"] = bounce
                line["price_kind"] = "limit_ge_bounce"
                line["shares"] = _shares(line["size_dollar"], bounce)
    return line


def merge_lines(lines: list, stock: dict, st: dict, buyideas: list) -> dict:
    """Tiers, floor, Hold snooze, budgets and ranking (DESIGN_SPEC_5 A1-A6 with
    the 2026-10-12 overrides). Mutates the lines (tier, list_rank, in_list,
    optional_line, small_line, est_value). Returns {'entries': {...}, 'buyideas': [...]}."""
    floor = st["today_floor_dollar"]
    by_sym: dict = {}
    for ln in lines:
        by_sym.setdefault(ln["tos_symbol"], []).append(ln)
    entries = {}
    for sym, lns in by_sym.items():
        sk = stock.get(sym, {})
        conv = sk.get("conviction")
        hold_note = False
        for ln in lns:
            ln["tier"] = ln["tier_hint"] if ln["signal"] not in ("NONE",) else None
            ln["small_line"] = False
            ln["optional_line"] = False
            ln["est_value"] = None
            if ln["signal"] == "NONE" or ln["tier"] is None:
                continue
            if ln["tier"] == "MUST" and conv == "HOLD":
                ln["tier"], hold_note = "CONSIDER", True
                ln["extra"]["hold_note"] = "you marked Hold"
            sz = ln["size_dollar"]
            if ln["signal"] != "WAIT" and (sz is None or sz < floor):
                ln["small_line"], ln["tier"] = True, "INFO"
        live = [l for l in lns if l["tier"] in ("MUST", "CONSIDER")]
        stock_tier = "INFO"
        if any(l["tier"] == "MUST" for l in live):
            stock_tier = "MUST"
        elif live:
            stock_tier = "CONSIDER"
        for ln in lns:
            if ln["tier"] in ("MUST", "CONSIDER") and ln["tier"] != stock_tier:
                ln["optional_line"] = True
            if ln["tier"] == "CONSIDER":
                edge = {"buyback": st["rank_edge_buyback"], "dip": st["rank_edge_dip"],
                        "sellsome": st["rank_edge_sellsome"], "trim": st["rank_edge_trim"],
                        "trim_to_max": st["rank_edge_trim_to_max"]}.get(ln["kind"], 0.0)
                ln["est_value"] = round((ln["size_dollar"] or 0.0) * edge / 100.0, 2)
        dollars = sum((l["size_dollar"] or 0.0) for l in live if l["tier"] == stock_tier)
        est = sum((l["est_value"] or 0.0) for l in live if l["tier"] == "CONSIDER")
        sell_first = 0 if any(l["side"] == "sell" for l in live) else 1
        acct_best = min((ACCT_ORDER.get(l["account_short"], 9) for l in live), default=9)
        entries[sym] = {"tier": stock_tier, "dollars": dollars, "est": est,
                        "sort_c": (-est, -dollars, sell_first, acct_best, sym),
                        "sort_m": (-dollars, sym), "hold_note": hold_note, "lines": lns}
    # rank + budgets
    must = sorted([s for s, e in entries.items() if e["tier"] == "MUST"], key=lambda s: entries[s]["sort_m"])
    cons = sorted([s for s, e in entries.items() if e["tier"] == "CONSIDER"], key=lambda s: entries[s]["sort_c"])
    cb = int(st["today_consider_budget"])
    for i, s in enumerate(must, 1):
        entries[s]["rank"], entries[s]["in_list"] = i, True
    for i, s in enumerate(cons, 1):
        entries[s]["rank"], entries[s]["in_list"] = i, i <= cb
    for s, e in entries.items():
        if e["tier"] == "INFO":
            e["rank"], e["in_list"] = None, False
    # Buy ideas (Trade Mode buys): not already MUST/CONSIDER, not blocked, >= floor, top N by $
    listed = set(must) | set(cons)
    ideas = []
    for b in buyideas:
        sk = stock.get(b["tos_symbol"], {})
        if b["tos_symbol"] in listed or sk.get("blocked_buy") or sk.get("conviction") == "AVOID":
            continue
        if (b.get("size_dollar") or 0) < floor:
            continue
        ideas.append(b)
    ideas.sort(key=lambda b: (-(b.get("size_dollar") or 0), b["tos_symbol"]))
    nb = int(st["today_buyidea_budget"])
    for i, b in enumerate(ideas, 1):
        b["rank"], b["in_list"] = i, i <= nb
    for s, e in entries.items():
        for ln in e["lines"]:
            ln["list_rank"], ln["in_list"] = e.get("rank"), bool(e.get("in_list")) and not ln["small_line"]
            ln["stock_tier"] = e["tier"]
    return {"entries": entries, "buyideas": ideas}


def _buy_amt(r: dict) -> float:
    """AMT$ for a buy-side Final Call -- mirrors web/actionable.js r._amt."""
    code = str(r.get("final_code") or "").upper()
    act = str(r.get("consolidated_action") or "").upper()
    pos = _f(r.get("current_position_dollar")) or 0.0
    tgt = _f(r.get("suggested_target_dollar")) or 0.0
    mn = _f(r.get("target_min_dollar"))
    if code == "BMN" and act == "ADD" and mn is not None:
        return mn - pos if pos < mn else 0.0
    if code in ("BM", "BS", "BMN"):
        return tgt - pos if tgt > pos else 0.0
    return 0.0


def buyidea_candidates(anchor: date) -> list:
    """Stocks that pass the Trade Mode strict buy rule (web/actionable.js
    _isTradeModeQualifyingBuy). The rule is NOT re-implemented here: the same
    Python port the nightly Trade Mode email uses (etl/export_trade_mode.py,
    already kept in step with the JS) is applied to the same rows the browser
    gets from GET /api/actionable. Size = the Final Call's existing AMT$."""
    from api.routers.dash import (get_actionable, get_actionable_settings,
                                  get_actionable_source_scorecard)
    from api.routers.rules import get_factor_scorecard
    from starlette.responses import Response
    from etl.export_trade_mode import _is_qualifying_buy, _buy_tradability_score
    rows = get_actionable(date=str(anchor), action=None, category=None, my_list_only=False,
                          show_acted=False, show_suppressed=True)
    sets = get_actionable_settings()
    sc = get_actionable_source_scorecard()
    frows = get_factor_scorecard(Response(), min_n=30, limit=500)
    factor = {f"{r['factor']}|{r['bucket']}": r for r in frows if r.get("factor")}
    ob, os_, rv = sets["rsi_overbought"], sets["rsi_oversold"], sets["vlm_rvol_avoid_threshold"]
    out = []
    for r in rows:
        if not _is_qualifying_buy(r, True, ob, os_, rv, factor, sc):
            continue
        out.append({"tos_symbol": r["tos_symbol"], "size_dollar": _buy_amt(r),
                    "final_action": r.get("final_action"), "final_code": r.get("final_code"),
                    "winning_source": r.get("winning_source"),
                    "score": _buy_tradability_score(r, ob, os_, rv, factor, sc)})
    return out


def _carried(session: Session, plan_date: date, symbols: list) -> dict:
    """{symbol: (days_open_before_today, since_date)}: consecutive earlier
    trading days with a MUST tier in the saved checks (not the night plan)."""
    if not symbols:
        return {}
    hol = _holidays(session)
    rows = session.execute(text("""
        SELECT tos_symbol, plan_date FROM hist_advice_live
        WHERE tier = 'MUST' AND plan_date < :p AND plan_date >= :lo AND tos_symbol = ANY(:s)
        GROUP BY 1, 2
    """), {"p": plan_date, "lo": plan_date - timedelta(days=40), "s": symbols}).fetchall()
    have: dict = {}
    for s, d in rows:
        have.setdefault(s, set()).add(d)
    out = {}
    for s in symbols:
        d = plan_date
        n, since = 0, None
        while True:
            d -= timedelta(days=1)
            while d.weekday() >= 5 or d in hol:
                d -= timedelta(days=1)
            if d in have.get(s, ()):
                n, since = n + 1, d
            else:
                break
        out[s] = (n, since)
    return out


def run_live_check(session: Session, plan_date: Optional[date] = None, prices: Optional[dict] = None,
                   now: Optional[datetime] = None, write: bool = True, replay: bool = False,
                   with_buyideas: bool = True, conv_override: Optional[dict] = None) -> dict:
    """Compare the plan with live prices, tier/rank, and save the check."""
    st = load_settings(session)
    now = now or now_et()
    if plan_date is None:
        plan_date = session.execute(text(
            "SELECT MAX(plan_date) FROM hist_advice_plan WHERE plan_date <= :t"),
            {"t": now.astimezone(_et_tz()).date()}).scalar()
    if plan_date is None:
        return {"skipped": "no_plan"}
    prow = session.execute(text("SELECT * FROM hist_advice_plan WHERE plan_date = :p"),
                           {"p": plan_date}).mappings().all()
    if not prow:
        return {"skipped": "no_plan", "plan_date": str(plan_date)}
    if prices is None:
        prices = load_live_prices(session, plan_date)
    if not prices:
        return {"skipped": "no_fresh_prices", "plan_date": str(plan_date)}
    checked_at = max(p["time"] for p in prices.values()).replace(microsecond=0)
    stale_cut = timedelta(minutes=st["live_price_stale_min"])
    if now - checked_at > stale_cut:
        return {"skipped": "stale_prices", "plan_date": str(plan_date), "checked_at": str(checked_at)}

    anchor = prow[0]["anchor_date"]
    syms = sorted({r["tos_symbol"] for r in prow})
    conv = {r[0]: r[1] for r in session.execute(text(
        "SELECT tos_symbol, direction FROM ref_conviction_hold WHERE status = 'ACTIVE' AND tos_symbol = ANY(:s)"),
        {"s": syms}).fetchall()}
    if conv_override:
        conv.update(conv_override)
    pvv = {r[0]: {"decision": r[1], "sig_today": r[2], "at": r[3]} for r in session.execute(text(
        "SELECT tos_symbol, decision, sig_today, derived_at FROM drv_pvv WHERE as_of_date = :d AND tos_symbol = ANY(:s)"),
        {"d": anchor, "s": syms}).fetchall()}
    first_bounce = {(r[0], r[1]): float(r[2]) for r in session.execute(text("""
        SELECT DISTINCT ON (tos_symbol, account_short) tos_symbol, account_short, bounce_price
        FROM hist_advice_live WHERE plan_date = :p AND bounce_price IS NOT NULL AND checked_at < :c
        ORDER BY tos_symbol, account_short, checked_at
    """), {"p": plan_date, "c": checked_at}).fetchall()}

    lines = []
    for p in prow:
        px = prices.get(p["tos_symbol"])
        stale = bool(px and now - px["time"] > stale_cut)
        ctx = {"conviction": conv.get(p["tos_symbol"]), "pvv": pvv.get(p["tos_symbol"]), "stale": stale,
               "first_bounce": first_bounce.get((p["tos_symbol"], p["account_short"]))}
        ln = evaluate_row(dict(p), px, st, ctx)
        ln["stale"] = stale
        ln["price_time"] = px["time"] if px else None
        lines.append(ln)

    stock = {}
    for p in prow:
        s = stock.setdefault(p["tos_symbol"], {})
        s["conviction"] = conv.get(p["tos_symbol"])
        s["blocked_buy"] = bool((p["final_code"] or "").upper() == "SA" or p["stop_breached"]
                                or p["kept_sellall"])
    ideas = []
    if with_buyideas and anchor:
        try:
            ideas = buyidea_candidates(anchor)
        except Exception:
            log.exception("buyidea_candidates failed (continuing without Buy ideas)")
    merged = merge_lines(lines, stock, st, ideas)
    carried = _carried(session, plan_date, [s for s, e in merged["entries"].items() if e["tier"] == "MUST"])

    # first check of the plan day also saves one NONE row per stock/account
    first_of_day = not session.execute(text(
        "SELECT 1 FROM hist_advice_live WHERE plan_date = :p AND checked_at < :c LIMIT 1"),
        {"p": plan_date, "c": checked_at}).first()
    out_rows = []
    for ln in lines:
        e = merged["entries"][ln["tos_symbol"]]
        if ln["signal"] == "NONE" and not ln["caution"] and not first_of_day:
            continue
        c = carried.get(ln["tos_symbol"], (0, None)) if ln.get("stock_tier") == "MUST" else (None, None)
        notes = dict(ln["extra"])
        notes["ratio"] = ln["ratio"]
        if ln["tos_symbol"] in conv:
            notes["conviction"] = conv[ln["tos_symbol"]]
        if c[1]:
            notes["since_date"] = str(c[1])
        if replay:
            notes["replay"] = True
        out_rows.append(_live_row(ln, plan_date, checked_at, e, c[0], notes))
    for b in merged["buyideas"]:
        out_rows.append({
            "checked_at": checked_at, "plan_date": plan_date, "tos_symbol": b["tos_symbol"],
            "account_short": "ALL", "price": None, "price_time": checked_at, "day_high": None,
            "day_low": None, "signal": "BUY_IDEA", "live_rank": SIGNAL_RANK["BUY_IDEA"],
            "reason": f"{b.get('winning_source') or 'Final Call'} buy call", "side": "buy",
            "size_dollar": b["size_dollar"], "shares": None, "limit_price": None, "price_kind": "idea",
            "evidence": "weak", "caution": None, "bounce_price": None, "chase": False, "pvv_line": None,
            "tier": "BUYIDEA", "list_rank": b["rank"], "in_list": b["in_list"], "optional_line": False,
            "small_line": False, "est_value": None, "carried_days": None, "stale": False,
            "gain_pct": None, "outlook_turned": False, "sector_name": None, "sector_share_pct": None,
            "notes": json.dumps({"final_action": b.get("final_action"), "final_code": b.get("final_code"),
                                 "score": round(float(b.get("score") or 0), 1), **({"replay": True} if replay else {})}),
        })
    if write:
        _write_rows(session, plan_date, checked_at, out_rows)
    n_by_tier: dict = {}
    for e in merged["entries"].values():
        n_by_tier[e["tier"]] = n_by_tier.get(e["tier"], 0) + 1
    return {"plan_date": str(plan_date), "checked_at": str(checked_at), "rows": len(out_rows),
            "stocks_by_tier": n_by_tier, "buyideas": len(merged["buyideas"]),
            "must": sorted(s for s, e in merged["entries"].items() if e["tier"] == "MUST"),
            "_merged": merged if not write else None}


def _live_row(ln: dict, plan_date: date, checked_at: datetime, entry: dict, carried_days, notes: dict) -> dict:
    return {
        "checked_at": checked_at, "plan_date": plan_date, "tos_symbol": ln["tos_symbol"],
        "account_short": ln["account_short"], "price": ln["price"], "price_time": ln.get("price_time"),
        "day_high": ln["day_high"], "day_low": ln["day_low"], "signal": ln["signal"],
        "live_rank": SIGNAL_RANK.get(ln["signal"], 9), "reason": ln["reason"], "side": ln["side"],
        "size_dollar": ln["size_dollar"], "shares": ln["shares"], "limit_price": ln["limit_price"],
        "price_kind": ln["price_kind"], "evidence": ln["evidence"], "caution": ln["caution"],
        "bounce_price": ln["bounce_price"], "chase": bool(ln["chase"]), "pvv_line": ln["pvv_line"],
        "tier": ln.get("tier"), "list_rank": ln.get("list_rank"), "in_list": bool(ln.get("in_list")),
        "optional_line": bool(ln.get("optional_line")), "small_line": bool(ln.get("small_line")),
        "est_value": ln.get("est_value"), "carried_days": carried_days, "stale": bool(ln.get("stale")),
        "gain_pct": None, "outlook_turned": False, "sector_name": None, "sector_share_pct": None,
        "notes": json.dumps(notes, default=str),
    }


_LIVE_COLS = ["checked_at", "plan_date", "tos_symbol", "account_short", "price", "price_time", "day_high",
              "day_low", "signal", "live_rank", "reason", "side", "size_dollar", "shares", "limit_price",
              "price_kind", "evidence", "caution", "bounce_price", "chase", "pvv_line", "tier", "list_rank",
              "in_list", "optional_line", "small_line", "est_value", "carried_days", "stale", "gain_pct",
              "outlook_turned", "sector_name", "sector_share_pct", "notes"]


def _write_rows(session: Session, plan_date: date, checked_at: datetime, rows: list) -> None:
    """Idempotent: the check is keyed by its price time, so a re-run replaces
    that check's rows. NONE-state rows are not written (the newest check is the
    truth: a stock missing from it has no signal)."""
    # fill plan-derived note fields (gain / outlook-turned / sector) from the plan
    plan = {(r["tos_symbol"], r["account_short"]): r for r in session.execute(text(
        "SELECT tos_symbol, account_short, gain_pct, outlook_turned, sector, sector_share_pct "
        "FROM hist_advice_plan WHERE plan_date = :p"), {"p": plan_date}).mappings().all()}
    for r in rows:
        pr = plan.get((r["tos_symbol"], r["account_short"]))
        if pr:
            r["gain_pct"], r["outlook_turned"] = pr["gain_pct"], bool(pr["outlook_turned"])
            r["sector_name"], r["sector_share_pct"] = pr["sector"], pr["sector_share_pct"]
    session.execute(text("DELETE FROM hist_advice_live WHERE checked_at = :c AND plan_date = :p"),
                    {"c": checked_at, "p": plan_date})
    if rows:
        session.execute(text(
            "INSERT INTO hist_advice_live (" + ", ".join(_LIVE_COLS) + ") VALUES ("
            + ", ".join(("CAST(:notes AS jsonb)") if c == "notes" else (":" + c) for c in _LIVE_COLS) + ")"), rows)
    session.commit()


def run_live_check_safe() -> dict:
    """Hook for price pulls (yahoo_fetch, TOSL loads). Never raises."""
    try:
        from etl.db import session_scope
        with session_scope() as s:
            res = run_live_check(s)
        res.pop("_merged", None)
        log.info("live advice check: %s", res)
        return res
    except BaseException as e:  # noqa: BLE001 - a broken check must not break a price pull
        log.exception("live advice check failed (non-fatal): %s", e)
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# API PAYLOAD  (GET /api/actionable/live)
# ---------------------------------------------------------------------------

def _k(x) -> str:
    """$ text: $13.9k, $8k, $950."""
    x = float(x or 0)
    if x >= 1000:
        v = round(x / 1000.0, 1)
        return f"${v:g}k"
    return f"${x:,.0f}"


def _px(x) -> str:
    return f"${float(x):,.2f}"


def _group_text(sym: str, lns: list, days: int) -> str:
    """One order-like sentence for lines of the same signal in one stock."""
    lns = sorted(lns, key=lambda l: ACCT_ORDER.get(l["account_short"], 9))
    first = lns[0]
    sig, verb = first["signal"], (first.get("notes") or {}).get("verb")
    total = sum(float(l["size_dollar"] or 0) for l in lns)
    shs = [l["shares"] for l in lns]
    names = [l["account_short"] for l in lns]

    def n(v) -> str:
        return str(int(v)) if v else "?"

    def who() -> str:
        if all(s == shs[0] for s in shs):
            nm = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
            return f"{n(shs[0])} {sym} in {nm}"
        parts = [f"{n(shs[0])} {sym} in {names[0]}"]
        parts += [f"{n(s)} in {nm_}" for s, nm_ in zip(shs[1:], names[1:])]
        return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]

    reason = first.get("reason") or ""
    kind, lpx = first.get("price_kind"), first.get("limit_price")
    if kind == "limit_ge_bounce" and lpx:
        where = f" at {_px(lpx)} limit (bounce, {days} days)"
    elif kind == "limit_ge" and lpx:
        where = f" at {_px(lpx)}+"
    elif kind == "limit_le" and lpx:
        where = f" at {_px(lpx)} or less"
    elif kind == "now" and first.get("price"):
        where = f" at ~{_px(first['price'])}"
    else:
        where = ""
    tail = f" — {reason}" if reason else ""
    if sig == "SELL_ALL":
        return f"SELL ALL {who()}{where} (~{_k(total)}){tail}"
    if sig == "TRIM_TO_MAX":
        return f"SELL {who()}{where} (back to max, {_k(total)}){tail}"
    if sig == "TRIM":
        return f"TRIM {who()}{where} ({_k(total)}){tail}"
    if sig == "SELL_SOME":
        return f"SELL {who()} (1 unit, {_k(total)}){tail}"
    if sig == "BUY_BACK":
        return f"BUY BACK {who()}{where} ({_k(total)}){tail}"
    if sig in ("DIP_BUY_STRONG", "DIP_BUY_LIGHT"):
        v = verb or "ADD"
        extra = "min" if v == "START" else "1 unit"
        return f"{v} {who()}{where} ({extra}, {_k(total)}){tail}"
    return f"{sig} {sym}"


def _fmt_md(d) -> str:
    return f"{d.month}/{d.day}" if d else ""


def _plain_time(dt) -> str:
    if not dt:
        return ""
    return dt.astimezone(_et_tz()).strftime("%H:%M") + " ET"


def _num(v):
    return float(v) if v is not None else None


def build_live_payload(session: Session, plan_date: Optional[date] = None,
                       now: Optional[datetime] = None) -> dict:
    st = load_settings(session)
    now = now or now_et()
    if plan_date is None:
        plan_date = session.execute(text(
            "SELECT MAX(plan_date) FROM hist_advice_plan WHERE plan_date <= :t"),
            {"t": now.astimezone(_et_tz()).date()}).scalar()
    out = {"plan_date": str(plan_date) if plan_date else None, "checked_at": None, "price_time": None,
           "stale": False, "stale_minutes": None, "stocks": {}, "today": None}
    if plan_date is None:
        out["today"] = {"must": [], "consider": [], "buyideas": [], "more_count": 0, "must_over_budget": 0,
                        "not_listed": [], "why": "", "quiet": "No plan yet.", "messages": [],
                        "act_symbols": [], "price_time": None,
                        "counts": {"must": 0, "consider": 0, "buyideas": 0, "act": 0}}
        return out
    plan = session.execute(text("SELECT * FROM hist_advice_plan WHERE plan_date = :p"),
                           {"p": plan_date}).mappings().all()
    checked_at = session.execute(text(
        "SELECT MAX(checked_at) FROM hist_advice_live WHERE plan_date = :p"), {"p": plan_date}).scalar()
    rows = []
    if checked_at:
        rows = session.execute(text(
            "SELECT * FROM hist_advice_live WHERE plan_date = :p AND checked_at = :c"),
            {"p": plan_date, "c": checked_at}).mappings().all()
    plan_by: dict = {}
    for r in plan:
        plan_by.setdefault(r["tos_symbol"], []).append(dict(r))
    price_time = max((r["price_time"] for r in rows if r["price_time"]), default=checked_at)
    out["checked_at"] = checked_at.isoformat() if checked_at else None
    out["price_time"] = price_time.isoformat() if price_time else None
    stale_min = None
    if price_time:
        stale_min = int((now - price_time).total_seconds() // 60)
        out["stale_minutes"] = stale_min
        out["stale"] = (stale_min > st["live_price_stale_min"]
                        and plan_date >= now.astimezone(_et_tz()).date())

    by_sym: dict = {}
    for r in rows:
        d = dict(r)
        nt = r["notes"]
        d["notes"] = nt if isinstance(nt, dict) else (json.loads(nt) if nt else {})
        by_sym.setdefault(r["tos_symbol"], []).append(d)

    stocks = {}
    for sym in set(by_sym) | set(plan_by):
        lns = by_sym.get(sym, [])
        pl = plan_by.get(sym, [])
        p0 = pl[0] if pl else {}
        tiers = [l["tier"] for l in lns if l["tier"]]
        tier = min(tiers, key=lambda t: TIER_ORDER.get(t, 9)) if tiers else None
        live = [l for l in lns if l["signal"] != "NONE" and not l["small_line"]]
        best = (min(live, key=lambda l: (SIGNAL_RANK.get(l["signal"], 9), -float(l["size_dollar"] or 0)))
                if live else None)
        price = next((float(l["price"]) for l in lns if l["price"] is not None), None)
        prior, sd = _num(p0.get("prior_close")), _num(p0.get("sd20"))
        lrr, trr = _num(p0.get("lrr")), _num(p0.get("trr"))
        room_pct = room_sd = width = None
        if price and trr:
            room_pct = (trr - price) / price * 100.0
            room_sd = (room_pct / 100.0 / sd) if sd else None
        if price and trr and lrr is not None:
            width = (trr - lrr) / price * 100.0
        accts = []
        for p in sorted(pl, key=lambda r: ACCT_ORDER.get(r["account_short"], 9)):
            accts.append({"name": p["account_short"], "held": _num(p["held_dollar"]),
                          "max": _num(p["max_dollar"]), "min": _num(p["min_dollar"]),
                          "unit": _num(p["unit_dollar"]), "held_shares": _num(p["held_shares"]),
                          "over_ratio": _num(p["over_ratio"]), "starter_order": p["starter_order"],
                          "last_sell_price": _num(p["last_sell_price"]),
                          "buyback_line": _num(p["buyback_line"]), "category": p["category"]})
        line_out = []
        for l in sorted(lns, key=lambda l: (ACCT_ORDER.get(l["account_short"], 9), l["account_short"])):
            if l["signal"] == "NONE" and not l["caution"]:
                continue
            line_out.append({
                "account": l["account_short"], "signal": l["signal"], "side": l["side"], "tier": l["tier"],
                "size": _num(l["size_dollar"]), "shares": _num(l["shares"]), "price": _num(l["limit_price"]),
                "price_kind": l["price_kind"], "reason": l["reason"], "evidence": l["evidence"],
                "optional": bool(l["optional_line"]), "small": bool(l["small_line"]),
                "caution": l["caution"], "bounce_price": _num(l["bounce_price"]), "chase": bool(l["chase"]),
                "pvv_line": l["pvv_line"], "est_value": _num(l["est_value"]),
                "ratio": l["notes"].get("ratio"), "verb": l["notes"].get("verb"),
                "also": l["notes"].get("also"), "hold_note": l["notes"].get("hold_note")})
        n0 = next((l for l in lns if l["notes"].get("since_date")), None)
        stocks[sym] = {
            "tier": tier,
            "rank": next((l["list_rank"] for l in lns if l["list_rank"] is not None and l["tier"] == tier), None),
            "in_list": any(l["in_list"] for l in lns), "signal": best["signal"] if best else None,
            "chase": any(l["chase"] for l in lns),
            "caution": next((l["caution"] for l in lns if l["caution"]), None),
            "bounce_price": next((_num(l["bounce_price"]) for l in lns if l["bounce_price"] is not None), None),
            "pvv_line": next((l["pvv_line"] for l in lns if l["pvv_line"]), None),
            "final_code": p0.get("final_code"), "final_action": p0.get("final_action"),
            "est_value": sum(float(l["est_value"] or 0) for l in lns) or None,
            "carried_days": next((l["carried_days"] for l in lns if l["carried_days"] is not None), None),
            "since_date": n0["notes"].get("since_date") if n0 else None,
            "price": price, "stale": any(l["stale"] for l in lns) or out["stale"],
            "plan": {"prior_close": prior, "sd_pct": sd * 100.0 if sd else None,
                     "trim_line": _num(p0.get("trim_line")), "dip_tier": p0.get("dip_tier"),
                     "dip_line": _num(p0.get("dip_line")), "lrr": lrr, "trr": trr,
                     "room_pct": room_pct, "room_sd": room_sd, "range_width_pct": width,
                     "sd_note": p0.get("sd_note")},
            "notes": {"gain_pct": _num(p0.get("gain_pct")), "outlook_turned": bool(p0.get("outlook_turned")),
                      "sector": p0.get("sector"),
                      "sector_share_pct": next((_num(p["sector_share_pct"]) for p in pl
                                                if p["sector_share_pct"] is not None), None),
                      "stop_breached": bool(p0.get("stop_breached")),
                      "gain_note_min": st["note_gain_pct"], "sector_note_min": st["note_sector_share_pct"]},
            "accounts": accts, "lines": line_out,
        }
    out["stocks"] = stocks

    # ---- today block ----
    days = int(st["sell_bounce_days"])

    def gtext(sym: str, s: dict, g: list) -> str:
        rr = [{"signal": x["signal"], "account_short": x["account"], "shares": x["shares"],
               "size_dollar": x["size"], "limit_price": x["price"], "price_kind": x["price_kind"],
               "reason": x["reason"], "price": s["price"], "notes": {"verb": x["verb"]}} for x in g]
        return _group_text(sym, rr, days)

    def entry(sym: str) -> dict:
        s = stocks[sym]
        lns = [l for l in s["lines"] if not l["small"]]
        prim = [l for l in lns if l["tier"] == s["tier"] and not l["optional"]] or lns
        groups: dict = {}
        for l in prim:
            groups.setdefault((l["signal"], l["verb"]), []).append(l)
        gl = sorted(groups.values(), key=lambda g: -sum(float(x["size"] or 0) for x in g))
        head = gtext(sym, s, gl[0]) if gl else ""
        sub = [{"text": gtext(sym, s, g), "optional": False} for g in gl[1:]]
        og: dict = {}
        for l in lns:
            if l["optional"] and l["tier"] == "CONSIDER":
                og.setdefault((l["signal"], l["verb"]), []).append(l)
        sub += [{"text": gtext(sym, s, g), "optional": True} for g in og.values()]
        hold = next((l["hold_note"] for l in lns if l.get("hold_note")), None)
        return {"symbol": sym, "tier": s["tier"], "rank": s["rank"], "text": head, "lines": sub,
                "evidence": prim[0]["evidence"] if prim else None, "carried_days": s["carried_days"],
                "since_date": s["since_date"], "hold_note": hold, "est_value": s["est_value"],
                "stale": s["stale"], "caution": s["caution"]}

    def ranked(tier: str) -> list:
        return sorted([sy for sy, s in stocks.items() if s["tier"] == tier],
                      key=lambda sy: (stocks[sy]["rank"] or 999, sy))

    must = ranked("MUST")
    cons_all = ranked("CONSIDER")
    cons = [sy for sy in cons_all if stocks[sy]["in_list"]]
    ideas_all = ranked("BUYIDEA")
    ideas = [sy for sy in ideas_all if stocks[sy]["in_list"]]
    ideas_e = []
    for sy in ideas:
        r = next((l for l in by_sym.get(sy, []) if l["signal"] == "BUY_IDEA"), None)
        if not r:
            continue
        ideas_e.append({"symbol": sy, "tier": "BUYIDEA", "rank": r["list_rank"], "lines": [],
                        "text": f"{r['notes'].get('final_action') or 'BUY'} {sy} (~{_k(r['size_dollar'])}) — {r['reason']}",
                        "evidence": r["evidence"], "carried_days": None, "since_date": None,
                        "hold_note": None, "est_value": None, "stale": False, "caution": None})
    # "Not listed today" counts
    listed = set(must) | set(cons_all) | set(ideas_all)
    nl = {"tech_sell": 0, "low_conf": 0, "stop": 0, "light": 0, "wait": 0, "small": 0}
    for sy, pl in plan_by.items():
        if sy in listed or not any((p["held_dollar"] or 0) > 0 for p in pl):
            continue
        p0 = pl[0]
        code = (p0["final_code"] or "").upper()
        if p0["low_confidence"] and code in _SELL_FAMILY:
            nl["low_conf"] += 1
        elif code in ("SS", "STM") and not p0["kept_sellsome"]:
            nl["tech_sell"] += 1
        if p0["stop_breached"]:
            nl["stop"] += 1
    for sy, s in stocks.items():
        if sy in listed:
            continue
        sigs = {l["signal"] for l in s["lines"]}
        if "DIP_BUY_LIGHT" in sigs:
            nl["light"] += 1
        if "WAIT" in sigs:
            nl["wait"] += 1
        real = [l for l in s["lines"] if l["signal"] not in ("NONE", "WAIT")]
        if real and all(l["small"] for l in real):
            nl["small"] += 1
    anchor = plan[0]["anchor_date"] if plan else None
    nobuy = 0
    if anchor:
        nobuy = session.execute(text("""
            SELECT COUNT(*) FROM drv_actionable WHERE as_of_date = :d AND final_code IN ('BM','BMN','BS')
              AND fc_feasible AND NOT (tos_symbol = ANY(:l))"""),
            {"d": anchor, "l": list(listed) or ["-"]}).scalar() or 0
    labels = [("tech_sell", "Technical SELL SOME"), ("low_conf", "LOW CONF sells"), ("stop", "stop hits"),
              ("light", "light dip buys"), ("wait", "waiting for a buy-back"), ("small", "too small to list")]
    not_listed = [{"key": k, "n": nl[k], "label": lab} for k, lab in labels if nl[k]]
    if nobuy:
        not_listed.append({"key": "buy_calls", "n": int(nobuy), "label": "buy calls with no price trigger"})
    # messages
    msgs = []
    if out["stale"] and stale_min is not None:
        h, m = divmod(stale_min, 60)
        age = f"{h} h {m} m" if h else f"{m} m"
        msgs.append(f"Prices are {age} old — the list may be out of date.")
    have_accts = {r["account_short"] for r in plan}
    if plan:
        for short, nums, srcs in session.execute(text("""
            SELECT short_name, array_agg(account_number), array_agg(source) FROM ref_accounts
            WHERE is_active AND size_mult > 0 AND short_name IS NOT NULL AND account_number <> '85911'
            GROUP BY short_name ORDER BY short_name""")).fetchall():
            if short in have_accts:
                continue
            cs = [n_ for n_, s_ in zip(nums, srcs) if s_ == "CS"]
            tbl, col = ("hist_cs", "account") if cs else ("hist_f", "account_number")
            last = session.execute(text(f"SELECT MAX(snapshot_date) FROM {tbl} WHERE {col} = ANY(:a)"),
                                   {"a": cs or nums}).scalar()
            msgs.append(f"Can't size {short}: no position file since {_fmt_md(last)}." if last
                        else f"Can't size {short}: no position file.")
    n_cons, n_ideas = len(cons_all), len(ideas_all)
    quiet = why = ""
    if not must:
        quiet = "No required actions today."
        if n_cons + n_ideas:
            why = ("Why: nothing is over 1.25× max and no kept source says SELL ALL on a stock you hold. "
                   f"{n_cons + n_ideas} optional ideas below.")
        else:
            why = ("Nothing to consider either — no trims (nothing up 1.5 normal moves), no dip-buys, "
                   "no buy-backs." + (f" Checked {_plain_time(price_time)}." if price_time else ""))
    act = sorted(listed)
    out["today"] = {
        "must": [entry(s) for s in must], "consider": [entry(s) for s in cons], "buyideas": ideas_e,
        "more_count": max(0, n_cons - len(cons)),
        "must_over_budget": max(0, len(must) - int(st["today_must_budget"])),
        "consider_total": n_cons, "buyideas_total": n_ideas,
        "not_listed": not_listed, "quiet": quiet, "why": why, "messages": msgs,
        "act_symbols": act, "price_time": out["price_time"], "price_time_text": _plain_time(price_time),
        "counts": {"must": len(must), "consider": n_cons, "buyideas": n_ideas, "act": len(act)},
    }
    return out
