"""Trade-date lookup for the Actionable screen ("Bought 10/1" / "Sold 10/1" tags).

Per symbol, the most recent buy and the most recent sell on or before the
screen date. Display only -- never touches the Final Call. Used by
web/actionable.js to (1) tag sell-signal rows with when you last bought,
(2) tag + park (Trade view) rows you traded on the screen date.

A trade is detected from (latest of): your real transactions (hist_cst Buy/Sell,
hist_ft BUY/SELL, 60-day lookback) and any day an account's share count rose
(buy) / fell (sell) versus its previous position snapshot (14-day lookback;
covers days the transaction files are behind).
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, Optional

from sqlalchemy import text

TX_LOOKBACK_DAYS = 60
SNAP_LOOKBACK_DAYS = 14


def trading_days_since(then: date, as_of: date) -> int:
    """Weekdays in (then, as_of]. 0 = same day. -1 if `then` is after as_of."""
    if then > as_of:
        return -1
    n, d = 0, then
    while d < as_of:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n += 1
    return n


def is_today(then: Optional[date], as_of: date) -> bool:
    return then is not None and then == as_of


# --- "today" = the current market SESSION, not the screen (anchor) date -----------
# The screen date is the last TOSD load, so during 10/1 trading it is still 9/30 and
# same-day trades/Done marks would never line up (user, 2026-10-01). The session date
# is the calendar date once the market has opened on a trading day (before 9:30 AM ET,
# weekends and holidays: the previous trading day) -- the same rule as the position-file
# date policy (etl/market_date.py). Everything "today" clears when the next session opens.

def prev_trading_day(d: date, holidays=()) -> date:
    hol = set(holidays or ())
    d -= timedelta(days=1)
    while d.weekday() >= 5 or d in hol:
        d -= timedelta(days=1)
    return d


def flags_apply(screen_date: date, session_day: date, holidays=()) -> bool:
    """Show "actioned today" flags only on the live screen: the session date itself or
    the trading day before it (the lagging anchor during the session). Older dates picked
    from the date picker don't get today's flags."""
    return screen_date >= prev_trading_day(session_day, holidays)


def current_session_day(session):
    """(session_day, holidays) as of now, ET."""
    from etl.market_date import market_date_for, _holidays, _now_et
    hol = _holidays(session)
    return market_date_for(_now_et(), hol), hol


def done_symbols_for_session(session, session_day: date, holidays=()) -> set:
    """Symbols marked DONE during the given session (by when it was clicked, not by the
    screen date it was stored under)."""
    from etl.market_date import market_date_for
    rows = session.execute(text("""
        SELECT tos_symbol, acted_at FROM user_action_log
        WHERE user_action = 'DONE' AND acted_at >= :lo
    """), {"lo": session_day - timedelta(days=4)}).all()
    return {sym for sym, at in rows if market_date_for(at, holidays) == session_day}


def trade_dates(session, as_of: date) -> Dict[str, dict]:
    """{tos_symbol: {'bought': date|None, 'sold': date|None}}."""
    tx_lo = as_of - timedelta(days=TX_LOOKBACK_DAYS)
    sn_lo = as_of - timedelta(days=SNAP_LOOKBACK_DAYS)
    rows = session.execute(text("""
        WITH tx AS (
            SELECT tos_symbol, 'B' AS k, MAX(trade_date) AS d FROM hist_cst
              WHERE action = 'Buy' AND tos_symbol IS NOT NULL AND trade_date BETWEEN :tx_lo AND :d
              GROUP BY tos_symbol
            UNION ALL
            SELECT tos_symbol, 'S', MAX(trade_date) FROM hist_cst
              WHERE action = 'Sell' AND tos_symbol IS NOT NULL AND trade_date BETWEEN :tx_lo AND :d
              GROUP BY tos_symbol
            UNION ALL
            SELECT tos_symbol, 'B', MAX(trade_date) FROM hist_ft
              WHERE action_kind = 'BUY' AND tos_symbol IS NOT NULL AND trade_date BETWEEN :tx_lo AND :d
              GROUP BY tos_symbol
            UNION ALL
            SELECT tos_symbol, 'S', MAX(trade_date) FROM hist_ft
              WHERE action_kind = 'SELL' AND tos_symbol IS NOT NULL AND trade_date BETWEEN :tx_lo AND :d
              GROUP BY tos_symbol
        ),
        snap AS (
            SELECT tos_symbol, snapshot_date, qty,
                   LAG(qty) OVER (PARTITION BY tos_symbol, acct ORDER BY snapshot_date) AS prev_qty
            FROM (
                SELECT tos_symbol, account AS acct, snapshot_date, qty FROM hist_cs
                  WHERE tos_symbol IS NOT NULL AND qty IS NOT NULL AND snapshot_date BETWEEN :lo2 AND :d
                UNION ALL
                SELECT tos_symbol, account_number, snapshot_date, qty FROM hist_f
                  WHERE tos_symbol IS NOT NULL AND qty IS NOT NULL AND snapshot_date BETWEEN :lo2 AND :d
            ) p
        ),
        chg AS (
            SELECT tos_symbol, CASE WHEN qty > prev_qty THEN 'B' ELSE 'S' END AS k, MAX(snapshot_date) AS d
            FROM snap
            WHERE prev_qty IS NOT NULL AND qty <> prev_qty AND snapshot_date >= :sn_lo
            GROUP BY tos_symbol, CASE WHEN qty > prev_qty THEN 'B' ELSE 'S' END
        )
        SELECT tos_symbol, k, MAX(d) FROM (SELECT * FROM tx UNION ALL SELECT * FROM chg) u
        GROUP BY tos_symbol, k
    """), {"d": as_of, "tx_lo": tx_lo, "sn_lo": sn_lo, "lo2": sn_lo - timedelta(days=7)}).all()
    out: Dict[str, dict] = {}
    for sym, k, d in rows:
        e = out.setdefault(sym, {"bought": None, "sold": None})
        e["bought" if k == "B" else "sold"] = d
    return out


# ---------------------------------------------------------------------------
# What exactly did you do today? (Bought / Bought more / Sold some / Sold all)
# ---------------------------------------------------------------------------

_EPS = 1e-6


def classify_today(pre: Optional[float], bought: Optional[float], sold: Optional[float],
                   snap_post: Optional[float] = None) -> Optional[str]:
    """Label for today's activity in one symbol.

    pre        shares held before today (latest position snapshot dated before
               the screen date, all accounts -- always pre-trade)
    bought/sold today's gross shares from the transaction files
    snap_post  shares in the latest position snapshot on/before the screen date;
               used only when no transactions are loaded yet

    Returns 'bought_new' | 'bought_more' | 'sold_some' | 'sold_all' | 'traded' | None.
    """
    pre = float(pre or 0)
    b, s = float(bought or 0), float(sold or 0)
    if b > _EPS or s > _EPS:
        net = b - s
    elif snap_post is not None and abs(float(snap_post) - pre) > _EPS:
        net = float(snap_post) - pre
    else:
        return None
    post = pre + net
    if b > _EPS and s > _EPS and abs(net) <= _EPS:
        return "traded"
    if net > _EPS:
        return "bought_new" if pre <= _EPS else "bought_more"
    if net < -_EPS:
        return "sold_all" if post <= _EPS else "sold_some"
    return None


def today_flows(session, as_of: date) -> Dict[str, dict]:
    """{tos_symbol: {'pre', 'bought', 'sold', 'snap_post'}} for the screen date."""
    out: Dict[str, dict] = {}

    def slot(sym):
        return out.setdefault(sym, {"pre": 0.0, "bought": 0.0, "sold": 0.0, "snap_post": None})

    for sym, b, s in session.execute(text("""
        SELECT tos_symbol,
               SUM(CASE WHEN action = 'Buy'  THEN ABS(quantity) ELSE 0 END),
               SUM(CASE WHEN action = 'Sell' THEN ABS(quantity) ELSE 0 END)
        FROM hist_cst WHERE trade_date = :d AND tos_symbol IS NOT NULL GROUP BY tos_symbol
        UNION ALL
        SELECT tos_symbol,
               SUM(CASE WHEN action_kind = 'BUY'  THEN ABS(quantity) ELSE 0 END),
               SUM(CASE WHEN action_kind = 'SELL' THEN ABS(quantity) ELSE 0 END)
        FROM hist_ft WHERE trade_date = :d AND tos_symbol IS NOT NULL GROUP BY tos_symbol
    """), {"d": as_of}).all():
        e = slot(sym)
        e["bought"] += float(b or 0)
        e["sold"] += float(s or 0)

    for key, op in (("pre", "<"), ("snap_post", "<=")):
        for sym, q in session.execute(text(f"""
            SELECT tos_symbol, SUM(qty) FROM (
                SELECT tos_symbol, qty FROM hist_cs
                 WHERE tos_symbol IS NOT NULL AND qty IS NOT NULL AND snapshot_date =
                       (SELECT MAX(snapshot_date) FROM hist_cs WHERE snapshot_date {op} :d)
                UNION ALL
                SELECT tos_symbol, qty FROM hist_f
                 WHERE tos_symbol IS NOT NULL AND qty IS NOT NULL AND snapshot_date =
                       (SELECT MAX(snapshot_date) FROM hist_f WHERE snapshot_date {op} :d)
            ) p GROUP BY tos_symbol
        """), {"d": as_of}).all():
            slot(sym)[key] = float(q or 0)
    return out
