"""Dashboard, stks, actionable, portfolio, and per-symbol history endpoints."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

from etl.db import session_scope

from api.models import (
    DashRow, DashSummary, StksRow, SymbolHistoryRow,
)
from api._helpers import _resolve_date


# ---------------------------------------------------------------------------
# Cash detection — applies to both hist_f (Fidelity) and hist_cs (Schwab)
# ---------------------------------------------------------------------------
# Fidelity (hist_f) holds cash either as the SPAXX** money-market fund or
# anything whose description contains "HELD IN MONEY MARKET". Regular brokerage
# accounts have a sweep cash row too, but IRAs use SPAXX** exclusively.
#
# Schwab (hist_cs) marks cash with symbol "Cash & Cash Investments" OR with
# the security_type column set to "Cash and Money Market" (used for some
# money-market positions).
#
# These SQL fragments are interpolated into f-strings; the `%%` escape is
# necessary because the queries are sent through psycopg's pyformat
# parameter handler, which would otherwise interpret a bare `%` as a
# parameter placeholder.
F_IS_CASH = """(
    COALESCE(symbol,'') = 'SPAXX**'
    OR UPPER(COALESCE(description,'')) LIKE '%HELD IN MONEY MARKET%'
)"""
F_IS_NOT_CASH = "NOT " + F_IS_CASH

CS_IS_CASH = """(
    COALESCE(symbol,'') = 'Cash & Cash Investments'
    OR COALESCE(security_type,'') = 'Cash and Money Market'
)"""
CS_IS_NOT_CASH = "NOT " + CS_IS_CASH

# Alias-qualified variants for queries that JOIN hist_cs (aliased as `c`) with
# other tables that also have a `symbol` column (e.g. drv_cs_realized_gain).
# Using a bare `symbol` reference in those queries would be ambiguous.
CS_IS_CASH_C = """(
    COALESCE(c.symbol,'') = 'Cash & Cash Investments'
    OR COALESCE(c.security_type,'') = 'Cash and Money Market'
)"""
CS_IS_NOT_CASH_C = "NOT " + CS_IS_CASH_C

router = APIRouter()


# -----------------------------------------------------------------------------
# Dashboard endpoints
# -----------------------------------------------------------------------------

@router.get("/api/dash", response_model=list[DashRow])
def get_dash(
    date: Optional[str] = Query(None, description="Snapshot date (default = latest)"),
    section: Optional[str] = Query(None, description="Filter to one section"),
):
    d = _resolve_date(date)
    sql = "SELECT * FROM v_dash(:d)"
    params = {"d": d}
    if section:
        sql = "SELECT * FROM v_dash(:d) WHERE section = :sec"
        params["sec"] = section
    with session_scope() as s:
        rows = s.execute(text(sql), params).mappings().all()
    return rows


@router.get("/api/dash/summary", response_model=Optional[DashSummary])
def get_dash_summary(date: Optional[str] = Query(None)):
    d = _resolve_date(date)
    with session_scope() as s:
        row = s.execute(text("SELECT * FROM v_dash_summary(:d)"),
                        {"d": d}).mappings().first()
    if not row:
        return None
    return row


@router.get("/api/briefing", response_model=dict)
def get_briefing(date: Optional[str] = Query(None,
                 description="Snapshot date for the briefing — default = latest")):
    """One-shot morning briefing for the Dashboard landing card.

    Aggregates four things for the user's first-glance check:
      1. yesterday_actions — actions logged in user_action_log on the prior day
         with their forward 5d return (if known)
      2. outlook_flips — count of symbols with non-HOLD actions in
         drv_outlook_action today (and the top 5 held flips)
      3. allocation_drift — categories whose current $ is outside [min, max]
         in ref_asset_allocation, computed from holdings
      4. load_failures — files that the most recent scheduler run touched
         but ended in 'error' status (meta_etl_run)

    All four blocks are independent — a failure in one is logged in
    `warnings` and the rest still return.
    """
    d = _resolve_date(date)
    warnings: list[str] = []

    with session_scope() as s:
        # 1. Yesterday's actions + outcome if known
        yesterday_actions = []
        try:
            rows = s.execute(text("""
                SELECT u.id, u.as_of_date,
                       COALESCE(u.tos_symbol, u.symbol) AS tos_symbol,
                       u.action_code, u.user_action, u.created_at,
                       o.fwd_5d_pct, o.hit
                FROM user_action_log u
                LEFT JOIN drv_rule_outcome o
                  ON o.tos_symbol = COALESCE(u.tos_symbol, u.symbol)
                 AND o.as_of_date = u.as_of_date
                WHERE u.as_of_date >= :d - INTERVAL '7 days'
                  AND u.as_of_date <= :d
                ORDER BY u.created_at DESC
                LIMIT 50
            """), {"d": d}).mappings().all()
            yesterday_actions = [dict(r) for r in rows]
        except Exception as e:
            warnings.append(f"yesterday_actions failed: {e}")

        # 2. Outlook flips today
        outlook_flips = {"total": 0, "held": 0, "top_held": []}
        try:
            agg = s.execute(text("""
                SELECT COUNT(*) AS total,
                       SUM(CASE WHEN held_today THEN 1 ELSE 0 END) AS held
                FROM v_outlook_changes(:d)
            """), {"d": d}).mappings().first()
            if agg:
                outlook_flips["total"] = int(agg["total"] or 0)
                outlook_flips["held"]  = int(agg["held"]  or 0)
            top = s.execute(text("""
                SELECT tos_symbol, dominant_action, sources, n_sources_changed
                FROM v_outlook_changes(:d)
                WHERE held_today = TRUE
                ORDER BY n_sources_changed DESC
                LIMIT 5
            """), {"d": d}).mappings().all()
            outlook_flips["top_held"] = [dict(r) for r in top]
        except Exception as e:
            warnings.append(f"outlook_flips failed: {e}")

        # 3. Allocation drift — categories outside [min, max]
        allocation_drift = []
        try:
            # SUM current $ per category from drv_actionable (uses the same
            # category-resolution logic derive_actionable just ran)
            rows = s.execute(text("""
                WITH cat AS (
                    SELECT position_category AS category,
                           SUM(COALESCE(current_position_dollar, 0)) AS held
                    FROM drv_actionable
                    WHERE as_of_date = :d AND position_category IS NOT NULL
                    GROUP BY position_category
                )
                SELECT a.category, c.held, a.min_dollar, a.max_dollar,
                       CASE
                         WHEN a.min_dollar IS NOT NULL AND c.held < a.min_dollar THEN 'BELOW_MIN'
                         WHEN a.max_dollar IS NOT NULL AND c.held > a.max_dollar THEN 'ABOVE_MAX'
                         ELSE 'WITHIN'
                       END AS status
                FROM ref_asset_allocation a
                JOIN cat c ON c.category = a.category
                WHERE (a.min_dollar IS NOT NULL AND c.held < a.min_dollar)
                   OR (a.max_dollar IS NOT NULL AND c.held > a.max_dollar)
                ORDER BY a.category
            """), {"d": d}).mappings().all()
            allocation_drift = [dict(r) for r in rows]
        except Exception as e:
            warnings.append(f"allocation_drift failed: {e}")

        # 4. Recent ETL failures
        load_failures = []
        try:
            rows = s.execute(text("""
                SELECT file_path, file_type, status, error_msg, started_at
                FROM meta_etl_run
                WHERE status = 'error'
                  AND started_at >= now() - INTERVAL '36 hours'
                ORDER BY started_at DESC
                LIMIT 20
            """)).mappings().all()
            load_failures = [dict(r) for r in rows]
        except Exception as e:
            warnings.append(f"load_failures failed: {e}")

    return {
        "as_of_date":         d.isoformat() if hasattr(d, "isoformat") else str(d),
        "yesterday_actions":  yesterday_actions,
        "outlook_flips":      outlook_flips,
        "allocation_drift":   allocation_drift,
        "load_failures":      load_failures,
        "warnings":           warnings,
    }


@router.get("/api/outlook/changes", response_model=list[dict])
def get_outlook_changes(
    date: Optional[str] = Query(None, description="Snapshot date (default = latest)"),
    held_only: bool = Query(False, description="Restrict to currently-held symbols"),
    limit: int = Query(100, ge=1, le=1000),
):
    """Per-symbol outlook-change roll-up for the Dashboard banner.

    Returns rows from v_outlook_changes(date) — one row per symbol that had at
    least one non-HOLD action in drv_outlook_action on that date. Sorted by
    n_sources_changed DESC. Use ?held_only=true to restrict to positions you
    actually hold.

    Response item shape:
      {
        "tos_symbol": "AAPL",
        "n_sources_changed": 3,
        "sources":  ["RR", "ETF", "CALL"],   # ordered by dominance priority
        "actions":  ["REMOVE", "REDUCE", "REDUCE"],
        "dominant_action": "REMOVE",         # REMOVE > REDUCE > ADD > INCREASE
        "held_today": true,
        "total_delta": -4.5,
        "reasons":  ["weight 2 → -1 ...", ...]
      }
    """
    d = _resolve_date(date)
    sql = "SELECT * FROM v_outlook_changes(:d)"
    params: dict = {"d": d}
    if held_only:
        sql += " WHERE held_today = TRUE"
    sql += " LIMIT :lim"
    params["lim"] = limit
    with session_scope() as s:
        rows = s.execute(text(sql), params).mappings().all()
    return [dict(r) for r in rows]


@router.get("/api/stks", response_model=list[StksRow])
def get_stks(
    date: Optional[str] = Query(None),
    sector: Optional[str] = Query(None),
    asset_class: Optional[str] = Query(None),
    min_brr: Optional[float] = Query(None, description="Filter rr_brr >= this"),
    max_brr: Optional[float] = Query(None, description="Filter rr_brr <= this"),
    outlook: Optional[str] = Query(None, description="BULLISH | BEARISH | NEUTRAL"),
    limit: int = Query(500, ge=1, le=5000),
):
    d = _resolve_date(date)
    where = []
    params: dict = {"d": d, "lim": limit}
    if sector:
        where.append("sector = :sector"); params["sector"] = sector
    if asset_class:
        where.append("asset_class = :ac"); params["ac"] = asset_class
    if min_brr is not None:
        where.append("rr_brr >= :minbrr"); params["minbrr"] = min_brr
    if max_brr is not None:
        where.append("rr_brr <= :maxbrr"); params["maxbrr"] = max_brr
    if outlook:
        where.append("UPPER(composite_label) = :ol"); params["ol"] = outlook.upper()

    where_clause = " AND ".join(["ma.as_of_date = :d"] + where) if where else "ma.as_of_date = :d"
    sql = f"""
        SELECT
            ma.as_of_date, ma.tos_symbol, ma.description, ma.sector, ma.asset_class,
            ma.sub_asset_class, ma.equity_sector, ma.last_price, ma.a_trend_value, ma.a_trade_value,
            ma.a_bb_top, ma.a_bb_bottom, ma.a_bb_streak, ma.a_macd_brr, ma.a_macdh_d_brr,
            ma.pct_brr, ma.rr_outlook, ma.rr_brr, ma.call_outlook, ma.call_modifier,
            ma.etf_outlook, ma.ii_outlook, ma.ssh_signal_sign, ma.iv_percentile, ma.imp_volatility,
            ma.hv_percentile, ma.range_compression, ma.d_iv_to_hv, ma.rsi, ma.earnings_days,
            ma.sma_20, ma.sma_50, ma.sma_200, ma.volume, ma.vlm_projected, ma.market_cap_str,
            ma.beta, ma.pe_ratio, ma.eps, ma.div_yield,
            stks.composite_outlook, stks.composite_label,
            stks.triggered_atomic_ids, stks.triggered_composite_ids
        FROM drv_ma ma
        LEFT JOIN drv_stks stks ON ma.as_of_date = stks.as_of_date AND ma.tos_symbol = stks.tos_symbol
        WHERE {where_clause}
        ORDER BY ma.tos_symbol
        LIMIT :lim
    """
    with session_scope() as s:
        rows = s.execute(text(sql), params).mappings().all()
    return rows


# -----------------------------------------------------------------------------
# Actionable Stocks
# -----------------------------------------------------------------------------

@router.get("/api/actionable/dates")
def list_actionable_dates():
    """Dates where drv_actionable has rows. Used to populate actionable screen date picker."""
    with session_scope() as s:
        rows = s.execute(text("""
            SELECT DISTINCT as_of_date FROM drv_actionable
            ORDER BY 1 DESC
        """)).fetchall()
    return [r[0].isoformat() for r in rows]


@router.get("/api/actionable/sources")
def list_actionable_sources():
    """source_code -> base_weight_method for active outlook sources. Lets the
    Actionable screen pick the Metric-column sort direction per source (rank
    sorts ascending, outlook weight descending, etc.)."""
    with session_scope() as s:
        rows = s.execute(text("""
            SELECT source_code, base_weight_method
            FROM ref_outlook_source
            WHERE deprecated_at IS NULL
            ORDER BY source_code
        """)).fetchall()
    return [{"source_code": r[0], "base_weight_method": r[1]} for r in rows]


@router.get("/api/actionable")
def get_actionable(
    date: Optional[str] = Query(None),
    action: Optional[str] = Query(None, description="Filter to one action"),
    category: Optional[str] = Query(None),
    my_list_only: bool = Query(False),
    show_acted: bool = Query(False),
    show_suppressed: bool = Query(False),
):
    d = _resolve_date(date)
    where = ["a.as_of_date = :d"]
    params: dict = {"d": d}
    if action:
        where.append("a.consolidated_action = :action")
        params["action"] = action.upper()
    if category:
        where.append("a.position_category = :cat")
        params["cat"] = category
    if my_list_only:
        where.append("a.in_my_list IS TRUE")
    if not show_suppressed:
        # Over-Max rows must remain visible — the frontend overlays SELL→MAX
        # on them. Only suppress rows that aren't over their category ceiling.
        where.append(
            "(a.suppressed_reason IS NULL OR "
            " (a.held_today = TRUE AND a.target_max_dollar > 0 "
            "  AND a.current_position_dollar > a.target_max_dollar))"
        )

    sql = f"""
        SELECT a.*,
               COALESCE(a.source_asset_class, m.asset_class) AS real_asset_class,
               q.last_price, q.net_chng, q.pct_change, q.export_date, q.export_time, q.loaded_at,
               u.user_action AS last_user_action,
               u.snooze_until AS snooze_until
        FROM drv_actionable a
        LEFT JOIN drv_ma m
               ON m.tos_symbol = a.tos_symbol AND m.as_of_date = a.as_of_date
        LEFT JOIN drv_quote q
               ON q.tos_symbol = a.tos_symbol AND q.as_of_date = a.as_of_date
        LEFT JOIN LATERAL (
            SELECT user_action, snooze_until
            FROM user_action_log
            WHERE user_action_log.as_of_date = a.as_of_date
              AND user_action_log.tos_symbol = a.tos_symbol
            ORDER BY acted_at DESC LIMIT 1
        ) u ON TRUE
        WHERE {' AND '.join(where)}
    """
    with session_scope() as s:
        rows = s.execute(text(sql), params).mappings().all()
    out = []
    for r in rows:
        d_ = dict(r)
        if not show_acted and d_.get("last_user_action") in ("DONE", "SKIPPED", "OVERRIDDEN"):
            continue
        snooze = d_.get("snooze_until")
        if not show_acted and snooze and snooze >= d:
            continue
        out.append(d_)
    return out


@router.get("/api/actionable/source-data")
def get_actionable_source_data(
    symbol: str = Query(...),
    date: Optional[str] = Query(None),
):
    """Raw source-feed fields for the Actionable-screen hover popover.
    Returns the latest hist_* row (snapshot_date <= date) per source for the
    symbol, limited to the few columns the popover displays."""
    d = _resolve_date(date)
    sym = symbol.strip().upper()

    def _f(v):
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    out: dict = {}
    with session_scope() as s:
        rr = s.execute(text("""
            SELECT buy_trade, sell_trade, snapshot_date FROM hist_rr
            WHERE tos_symbol = :sym AND snapshot_date <= :d
            ORDER BY snapshot_date DESC LIMIT 1
        """), {"sym": sym, "d": d}).first()
        if rr:
            out["RR"] = {"buy_trade": _f(rr[0]), "sell_trade": _f(rr[1]),
                         "snapshot_date": rr[2].isoformat() if rr[2] else None}

        etf = s.execute(text("""
            SELECT brr, trr, snapshot_date FROM hist_etf
            WHERE tos_symbol = :sym AND snapshot_date <= :d
            ORDER BY snapshot_date DESC LIMIT 1
        """), {"sym": sym, "d": d}).first()
        if etf:
            out["ETF"] = {"brr": _f(etf[0]), "trr": _f(etf[1]),
                          "snapshot_date": etf[2].isoformat() if etf[2] else None}

        ps = s.execute(text("""
            SELECT rank, snapshot_date FROM hist_ps
            WHERE ticker = :sym AND snapshot_date <= :d
            ORDER BY snapshot_date DESC LIMIT 1
        """), {"sym": sym, "d": d}).first()
        if ps:
            out["PS"] = {"rank": _f(ps[0]),
                         "snapshot_date": ps[1].isoformat() if ps[1] else None}

        sss = s.execute(text("""
            SELECT pct_delta, anlst_best_idea_rank, snapshot_date FROM hist_sss
            WHERE tos_symbol = :sym AND snapshot_date <= :d
            ORDER BY snapshot_date DESC LIMIT 1
        """), {"sym": sym, "d": d}).first()
        if sss:
            out["SSS"] = {"pct_delta": _f(sss[0]), "anlst_best_idea_rank": sss[1],
                          "snapshot_date": sss[2].isoformat() if sss[2] else None}

        call = s.execute(text("""
            SELECT snapshot_date FROM hist_call
            WHERE tos_symbol = :sym AND snapshot_date <= :d
            ORDER BY snapshot_date DESC LIMIT 1
        """), {"sym": sym, "d": d}).first()
        if call:
            out["CALL"] = {"snapshot_date": call[0].isoformat() if call[0] else None}

        ii = s.execute(text("""
            SELECT snapshot_date FROM hist_ii
            WHERE symbol = :sym AND snapshot_date <= :d
            ORDER BY snapshot_date DESC LIMIT 1
        """), {"sym": sym, "d": d}).first()
        if ii:
            out["II"] = {"snapshot_date": ii[0].isoformat() if ii[0] else None}
    return out


@router.get("/api/actionable/freshness")
def get_actionable_freshness(date: Optional[str] = Query(None)):
    """Report whether drv_actionable for a date is stale — i.e. newer
    outlook-source data was loaded after the date was last derived."""
    d = _resolve_date(date)
    with session_scope() as s:
        from etl.derive_freshness import find_stale_actionable_dates
        stale_dates = find_stale_actionable_dates(s)
    return {
        "date": d.isoformat(),
        "stale": d in stale_dates,
        "stale_count": len(stale_dates),
    }


@router.get("/api/actionable/comparison")
def get_actionable_comparison(
    symbol: str = Query(...),
    date: Optional[str] = Query(None),
):
    """The two source records a rule compared to produce each action: the
    current snapshot record and the previous one it was measured against
    (e.g. this week's PS record vs. last week's). Drives the drilldown
    modal's per-source inline comparison.

    Source-agnostic: the columns returned are introspected from each source
    table via information_schema, so a new source added to ref_outlook_source
    is compared in full with no code change. Housekeeping columns (audit
    trail, keys) are excluded; every remaining column is returned for both
    the current and previous record."""
    d = _resolve_date(date)
    sym = symbol.strip().upper()
    HK_COLS = {"loaded_at", "source_file", "source_run_id", "computed_at",
               "symbol", "ticker", "sequence", "account", "account_number"}
    col_cache: dict = {}
    # Per-method decision-driving field(s): the column(s) the classifier
    # actually evaluates. Only these are highlighted as "what drove the
    # action" - other columns change every snapshot but are informational.
    DRIVER_FIELDS = {
        "outlook_modifier": ["outlook", "outlook_modifier"],
        "rank":             ["rank"],
        "rank_pct_delta":   ["pct_delta"],
    }

    def _jsonable(v):
        if v is None or isinstance(v, (bool, int, float, str)):
            return v
        if hasattr(v, "isoformat"):
            return v.isoformat()
        try:
            return float(v)
        except (TypeError, ValueError):
            return str(v)

    out = []
    with session_scope() as s:

        def _value_columns(tbl, dcol):
            """Non-housekeeping value columns of tbl, in definition order."""
            cols = col_cache.get(tbl)
            if cols is None:
                meta = s.execute(text("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = :t AND table_schema = 'public'
                    ORDER BY ordinal_position
                """), {"t": tbl}).fetchall()
                cols = [r[0] for r in meta
                        if r[0] not in HK_COLS and r[0] != dcol]
                col_cache[tbl] = cols
            return cols

        rows = s.execute(text("""
            WITH eff AS (
                SELECT ros.source_code AS sc, ros.source_table AS tbl,
                       ros.base_weight_method AS bwm,
                       CASE WHEN ros.source_code IN ('ETF','II','SSS','PS','RR')
                            THEN (SELECT MAX(as_of_date)
                                  FROM drv_outlook_action o
                                  WHERE o.source_code = ros.source_code
                                    AND o.as_of_date <= :d)
                            ELSE :d END AS ed
                FROM ref_outlook_source ros
            )
            SELECT doa.source_code, eff.tbl, eff.bwm,
                   COALESCE(doa.source_snapshot_date, doa.as_of_date) AS cur_d,
                   doa.prev_date,
                   doa.base_weight, doa.prev_weight, doa.action
            FROM drv_outlook_action doa
            JOIN eff ON eff.sc = doa.source_code AND doa.as_of_date = eff.ed
            WHERE doa.tos_symbol = :sym
            ORDER BY doa.source_code
        """), {"sym": sym, "d": d}).all()

        def _hist_rec(tbl, snap):
            if tbl is None or snap is None:
                return None
            key = "ticker" if tbl == "hist_ps" else "symbol"
            dcol = "event_date" if tbl in ("hist_etfchg", "hist_iichg") else "snapshot_date"
            cols = _value_columns(tbl, dcol)
            sel = ", ".join(cols + [dcol]) if cols else dcol
            try:
                r = s.execute(text(
                    f"SELECT {sel} FROM {tbl} "
                    f"WHERE {key} = :sym AND {dcol} <= :snap "
                    f"ORDER BY {dcol} DESC LIMIT 1"
                ), {"sym": sym, "snap": snap}).first()
            except Exception:
                return None
            if r is None:
                return None
            fields = {c: _jsonable(r[i]) for i, c in enumerate(cols)}
            actual = r[len(cols)]
            return {"date": actual.isoformat() if actual else None,
                    "fields": fields}

        def _side(rec, weight, snap_d, dropped):
            # `dropped` = the symbol had no effective state for this source at
            # this end of the comparison (base_weight / prev_weight is NULL in
            # drv_outlook_action - e.g. dropped from the current bundle). Show
            # it blank rather than reaching back to a stale pre-drop record.
            if dropped:
                return {"snapshot_date": None, "weight": None,
                        "fields": {}, "dropped": True}
            return {
                "snapshot_date": (rec["date"] if rec
                                  else (snap_d.isoformat() if snap_d else None)),
                "weight": float(weight) if weight is not None else None,
                "fields": rec["fields"] if rec else {},
                "dropped": False,
            }

        for src, tbl, bwm, cur_d, prev_d, base_w, prev_w, action in rows:
            cur_dropped = base_w is None
            prev_dropped = prev_w is None
            cur = None if cur_dropped else _hist_rec(tbl, cur_d)
            prv = None if prev_dropped else _hist_rec(tbl, prev_d)
            out.append({
                "source": src,
                "action": action,
                "table": tbl,
                "driver_fields": DRIVER_FIELDS.get((bwm or "").strip(), []),
                "current": _side(cur, base_w, cur_d, cur_dropped),
                "previous": _side(prv, prev_w, prev_d, prev_dropped),
            })
    return out


@router.post("/api/actionable/{symbol}/action", response_model=dict)
def post_actionable_action(symbol: str, payload: dict):
    """Capture user decision with full forensic snapshot."""
    sym_u = symbol.upper().strip()
    as_of_str = payload.get("as_of_date")
    if not as_of_str:
        raise HTTPException(400, "as_of_date required")
    try:
        as_of = datetime.strptime(as_of_str, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(400, "as_of_date must be YYYY-MM-DD")
    user_action = (payload.get("user_action") or "").upper()
    if user_action not in ("DONE", "SKIPPED", "SNOOZED", "OVERRIDDEN"):
        raise HTTPException(400, "user_action must be DONE/SKIPPED/SNOOZED/OVERRIDDEN")

    with session_scope() as s:
        # Snapshot drv_actionable row
        act_row = s.execute(text("""
            SELECT * FROM drv_actionable
            WHERE as_of_date = :d AND tos_symbol = :sym
        """), {"d": as_of, "sym": sym_u}).mappings().first()
        if not act_row:
            raise HTTPException(404, f"no drv_actionable row for {sym_u} on {as_of}")
        a = dict(act_row)

        # Snapshot raw hist_* rows from each source for forensic replay
        raw_snapshot: dict = {}
        sources = s.execute(text("""
            SELECT source_code, source_table FROM ref_outlook_source
            WHERE deprecated_at IS NULL
        """)).fetchall()
        for sc, tbl in sources:
            date_col = "event_date" if tbl in ("hist_etfchg", "hist_iichg") else "snapshot_date"
            key_col  = "ticker"    if tbl in ("hist_ps",) else "symbol"
            try:
                r = s.execute(text(f"""
                    SELECT * FROM {tbl}
                    WHERE {key_col} = :sym AND {date_col} <= :d
                    ORDER BY {date_col} DESC LIMIT 1
                """), {"sym": sym_u, "d": as_of}).mappings().first()
                if r:
                    safe = {}
                    for k, v in dict(r).items():
                        try:
                            json.dumps(v)
                            safe[k] = v
                        except (TypeError, ValueError):
                            safe[k] = str(v) if v is not None else None
                    raw_snapshot[sc] = safe
            except Exception:
                continue

        snooze_until = payload.get("snooze_until")
        if snooze_until:
            try:
                snooze_until = datetime.strptime(snooze_until, "%Y-%m-%d").date()
            except ValueError:
                snooze_until = None

        ret = s.execute(text("""
            INSERT INTO user_action_log (
                user_id, as_of_date, symbol, tos_symbol, user_action, user_action_target,
                snooze_until, user_notes,
                consolidated_action, winning_source, winning_priority,
                position_category, target_min_dollar, target_max_dollar,
                units_dollar, maintain_min, suggested_target_dollar,
                held_at_action, position_dollar_at_action, in_my_list,
                source_actions, rules_engine_fires, source_raw_snapshot
            ) VALUES (
                :uid, :d, :sym, :sym, :ua, :target,
                :snooze, :notes,
                :ca, :ws, :wp,
                :cat, :tmin, :tmax,
                :unit, :mm, :stgt,
                :held, :pos, :iml,
                CAST(:srca AS JSONB), CAST(:fires AS JSONB), CAST(:raw AS JSONB)
            ) RETURNING id
        """), {
            "uid":    payload.get("user_id", "default"),
            "d":      as_of, "sym": sym_u, "ua": user_action,
            "target": payload.get("user_action_target"),
            "snooze": snooze_until,
            "notes":  payload.get("user_notes"),
            "ca":     a.get("consolidated_action"),
            "ws":     a.get("winning_source"),
            "wp":     a.get("winning_priority"),
            "cat":    a.get("position_category"),
            "tmin":   a.get("target_min_dollar"),
            "tmax":   a.get("target_max_dollar"),
            "unit":   a.get("units_dollar"),
            "mm":     a.get("maintain_min"),
            "stgt":   a.get("suggested_target_dollar"),
            "held":   a.get("held_today"),
            "pos":    a.get("current_position_dollar"),
            "iml":    a.get("in_my_list"),
            "srca":   json.dumps(a.get("source_actions") or []),
            "fires":  json.dumps(a.get("rules_engine_fires") or []),
            "raw":    json.dumps(raw_snapshot),
        }).first()
        s.commit()
    return {"ok": True, "log_id": ret[0] if ret else None}


@router.delete("/api/actionable/{symbol}/action")
def clear_actionable_action(symbol: str, date: str = Query(...)):
    """Un-suppress: remove SKIPPED user_action_log rows for (date, symbol) so
    the action reappears on the Actionable screen. Backs the grid's
    Suppress/Un-suppress toggle."""
    sym = symbol.upper().strip()
    try:
        as_of = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(400, "date must be YYYY-MM-DD")
    with session_scope() as s:
        res = s.execute(text("""
            DELETE FROM user_action_log
            WHERE as_of_date = :d AND tos_symbol = :sym AND user_action = 'SKIPPED'
        """), {"d": as_of, "sym": sym})
    return {"cleared": res.rowcount or 0}


@router.get("/api/actionable/history")
def get_actionable_history(symbol: str = Query(...), limit: int = Query(50, ge=1, le=500)):
    sym_u = symbol.upper().strip()
    with session_scope() as s:
        rows = s.execute(text("""
            SELECT * FROM user_action_log
            WHERE tos_symbol = :sym
            ORDER BY acted_at DESC
            LIMIT :lim
        """), {"sym": sym_u, "lim": limit}).mappings().all()
    return [dict(r) for r in rows]


# -----------------------------------------------------------------------------
# Database Statistics
# -----------------------------------------------------------------------------

@router.get("/api/stats/tables")
def get_table_stats(date: Optional[str] = Query(None)):
    """Table statistics for a given snapshot date."""
    d = _resolve_date(date)

    with session_scope() as s:
        # Get all tables with info about whether they have date columns
        rows = s.execute(text("""
            SELECT
                t.table_name,
                CASE
                    WHEN t.table_name LIKE 'hist_%' THEN 'hist'
                    WHEN t.table_name LIKE 'drv_cat_%' THEN 'drv_cat'
                    WHEN t.table_name LIKE 'drv_%' THEN 'drv'
                    WHEN t.table_name LIKE 'ref_%' THEN 'ref'
                    WHEN t.table_name LIKE 'meta_%' THEN 'meta'
                    ELSE 'other'
                END as category,
                EXISTS(SELECT 1 FROM information_schema.columns
                       WHERE table_schema='public' AND table_name=t.table_name
                       AND column_name='as_of_date') as has_date_col
            FROM information_schema.tables t
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            ORDER BY category, table_name
        """)).fetchall()

    results = []
    for table_name, category, has_date_col in rows:
        with session_scope() as s:
            if has_date_col:
                # Table has as_of_date, get full stats
                row = s.execute(text(f"""
                    SELECT
                        COUNT(*) as total_rows,
                        COUNT(*) FILTER (WHERE as_of_date = :d) as rows_on_date,
                        COUNT(DISTINCT as_of_date) as distinct_dates,
                        MIN(as_of_date)::text as min_date,
                        MAX(as_of_date)::text as max_date
                    FROM {table_name}
                """), {"d": d}).mappings().first()

                results.append({
                    "name": table_name,
                    "category": category,
                    "rows_on_date": row['rows_on_date'] or 0,
                    "total_rows": row['total_rows'] or 0,
                    "distinct_dates": row['distinct_dates'] or 0,
                    "date_col": "as_of_date",
                    "min_date": row['min_date'],
                    "max_date": row['max_date'],
                })
            else:
                # No date column, just count rows
                row = s.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar()
                results.append({
                    "name": table_name,
                    "category": category,
                    "rows_on_date": None,
                    "total_rows": row or 0,
                    "distinct_dates": None,
                    "date_col": None,
                    "min_date": None,
                    "max_date": None,
                })

    return results


# -----------------------------------------------------------------------------
# Portfolio
# -----------------------------------------------------------------------------

@router.get("/api/portfolio")
def get_portfolio(
    date: Optional[str] = Query(None),
    consolidated: bool = Query(False, description="If true, sum across accounts per symbol"),
    account: Optional[str] = Query(None, description="Filter to one account (number or name)"),
    source: Optional[str] = Query(None, description="F | CS | (none = both)"),
    latest_prices: bool = Query(False, description="Re-price held positions using drv_quote.last_price"),
):
    """
    Unified portfolio across hist_f (Fidelity) and hist_cs (Charles Schwab) on
    the latest snapshot on or before `date`. One row per (symbol, account) by
    default; consolidated=true sums across accounts per symbol.
    """
    d = _resolve_date(date)
    src_f = (source or "").upper() != "CS"
    src_cs = (source or "").upper() != "F"

    parts = []
    params: dict = {"d": d}
    if src_f:
        parts.append("""
          SELECT
            'F'                                       AS source,
            COALESCE(account_name, account_number)    AS account,
            account_number                            AS account_id,
            tos_symbol                                AS symbol,
            description,
            type                                      AS security_type,
            qty,
            avg_cost_basis                            AS avg_cost,
            last_price,
            current_value                             AS market_value,
            today_gl_dollar                           AS today_gain_dollar,
            today_gl_pct                              AS today_gain_pct,
            total_gl_dollar                           AS total_gain_dollar,
            total_gl_pct                              AS total_gain_pct,
            cost_basis_total                          AS cost_basis,
            pct_of_account,
            snapshot_date
          FROM hist_f
          WHERE TRUE
            AND snapshot_date = (SELECT MAX(snapshot_date) FROM hist_f WHERE snapshot_date <= :d)
        """)
    if src_cs:
        parts.append("""
          (
          -- Held positions with unrealized gain + any realized gain from sales on this date
          SELECT
            'CS'                                      AS source,
            c.account                                   AS account,
            c.account                                   AS account_id,
            c.tos_symbol                                AS symbol,
            c.description,
            c.security_type,
            c.qty,
            CASE WHEN c.qty > 0 THEN c.cost_basis / c.qty ELSE NULL END AS avg_cost,
            c.price                                     AS last_price,
            c.market_value,
            COALESCE(c.day_chng_dollar, 0) + COALESCE(rg.realized_gain, 0)  AS today_gain_dollar,
            c.day_chng_pct                              AS today_gain_pct,
            c.gain_dollar                               AS total_gain_dollar,
            c.gain_pct                                  AS total_gain_pct,
            c.cost_basis,
            NULL::NUMERIC                             AS pct_of_account,
            c.snapshot_date
          FROM hist_cs c
          LEFT JOIN drv_cs_realized_gain rg
               ON rg.account = c.account
              AND rg.tos_symbol = c.tos_symbol
              AND rg.as_of_date = (SELECT MAX(snapshot_date) FROM hist_cs WHERE snapshot_date <= :d)
          WHERE TRUE
            AND c.snapshot_date = (SELECT MAX(snapshot_date) FROM hist_cs WHERE snapshot_date <= :d)
          )
          UNION ALL
          (
          -- Sold positions: realized gains for positions not in today's hist_cs
          SELECT
            'CS'                                      AS source,
            rg.account                                  AS account,
            rg.account                                  AS account_id,
            rg.tos_symbol                              AS symbol,
            NULL::TEXT                                AS description,
            NULL::TEXT                                AS security_type,
            rg.shares_sold                              AS qty,
            rg.avg_cost_per_share                       AS avg_cost,
            NULL::NUMERIC                             AS last_price,
            NULL::NUMERIC                             AS market_value,
            rg.realized_gain                            AS today_gain_dollar,
            NULL::NUMERIC                             AS today_gain_pct,
            NULL::NUMERIC                             AS total_gain_dollar,
            NULL::NUMERIC                             AS total_gain_pct,
            NULL::NUMERIC                             AS cost_basis,
            NULL::NUMERIC                             AS pct_of_account,
            (SELECT MAX(snapshot_date) FROM hist_cs WHERE snapshot_date <= :d)  AS snapshot_date
          FROM drv_cs_realized_gain rg
          WHERE rg.as_of_date = (SELECT MAX(snapshot_date) FROM hist_cs WHERE snapshot_date <= :d)
            AND NOT EXISTS (
              SELECT 1 FROM hist_cs c
              WHERE c.account = rg.account
                AND c.tos_symbol = rg.tos_symbol
                AND c.snapshot_date = (SELECT MAX(snapshot_date) FROM hist_cs WHERE snapshot_date <= :d)
            )
          )
        """)
    if not parts:
        return []

    union_sql = " UNION ALL ".join(parts)

    if consolidated:
        sql = f"""
        WITH u AS ({union_sql})
        SELECT
          string_agg(DISTINCT source, '+' ORDER BY source) AS source,
          'ALL'                              AS account,
          'ALL'                              AS account_id,
          symbol,
          MAX(description)                   AS description,
          MAX(security_type)                 AS security_type,
          SUM(qty)                           AS qty,
          CASE WHEN SUM(qty) > 0
               THEN SUM(qty * COALESCE(avg_cost,0)) / NULLIF(SUM(qty),0)
               ELSE NULL END                 AS avg_cost,
          MAX(last_price)                    AS last_price,
          SUM(market_value)                  AS market_value,
          SUM(today_gain_dollar)             AS today_gain_dollar,
          CASE WHEN SUM(market_value - COALESCE(today_gain_dollar,0)) <> 0
               THEN SUM(today_gain_dollar) /
                    NULLIF(SUM(market_value - COALESCE(today_gain_dollar,0)), 0) * 100
               ELSE NULL END                 AS today_gain_pct,
          SUM(total_gain_dollar)             AS total_gain_dollar,
          CASE WHEN SUM(cost_basis) <> 0
               THEN SUM(total_gain_dollar) / NULLIF(SUM(cost_basis),0) * 100
               ELSE NULL END                 AS total_gain_pct,
          SUM(cost_basis)                    AS cost_basis,
          SUM(pct_of_account)                AS pct_of_account,
          MAX(snapshot_date)                 AS snapshot_date
        FROM u
        GROUP BY symbol
        ORDER BY SUM(market_value) DESC NULLS LAST, symbol
        """
    else:
        sql = f"""
        WITH u AS ({union_sql})
        SELECT * FROM u
        {"WHERE account = :acct" if account else ""}
        ORDER BY market_value DESC NULLS LAST, symbol
        """
        if account:
            params["acct"] = account

    with session_scope() as s:
        rows = s.execute(text(sql), params).mappings().all()
        out = [dict(r) for r in rows]

        # ── Optional: re-price using drv_quote.last_price ────────────────────
        # When latest_prices=True, override last_price, market_value, and the
        # "today's gain" pair for each held position with:
        #   - last_price    = drv_quote.last_price at MAX(as_of_date)
        #   - market_value  = qty * latest_price
        #   - day_change_$  = (latest_price - prev_close) * qty
        #   - day_change_%  = (latest_price - prev_close) / prev_close * 100
        # prev_close = hist_cs.price / hist_f.last_price at the snapshot
        # immediately preceding the latest drv_quote.as_of_date. (A2.)
        if latest_prices and out:
            syms_held = list({r["symbol"] for r in out if r.get("symbol") and r.get("qty")})
            if syms_held:
                qrow = s.execute(text(
                    "SELECT MAX(as_of_date) FROM drv_quote"
                )).first()
                latest_dq_date = qrow[0] if qrow else None
                latest_price_map = {}
                if latest_dq_date:
                    for r in s.execute(text("""
                        SELECT tos_symbol, last_price FROM drv_quote
                         WHERE as_of_date = :d AND tos_symbol = ANY(:syms)
                    """), {"d": latest_dq_date, "syms": syms_held}).all():
                        if r[1] is not None:
                            latest_price_map[r[0]] = float(r[1])
                # prev_close: hist_td.last_price at the snapshot immediately
                # preceding latest_dq_date. (DISTINCT ON picks one row per symbol
                # since hist_td PK is (snapshot_date, symbol, sequence).)
                prev_close_map: dict = {}
                if latest_dq_date:
                    for r in s.execute(text("""
                        SELECT tos_symbol, last_price FROM drv_quote
                         WHERE as_of_date = (SELECT MAX(as_of_date) FROM drv_quote
                                              WHERE as_of_date < :d)
                           AND tos_symbol = ANY(:syms)
                    """), {"d": latest_dq_date, "syms": syms_held}).all():
                        if r[1] is not None:
                            prev_close_map[r[0]] = float(r[1])
                for r in out:
                    sym = r.get("symbol")
                    qty = r.get("qty")
                    if not sym or qty is None: continue
                    lp = latest_price_map.get(sym)
                    if lp is None: continue
                    pc = prev_close_map.get(sym)
                    r["last_price"]    = lp
                    r["market_value"]  = float(qty) * lp
                    if pc is not None and pc != 0:
                        r["today_gain_dollar"] = (lp - pc) * float(qty)
                        r["today_gain_pct"]    = (lp - pc) / pc * 100.0
                    # Total Gain re-derives from the new market value. Cost
                    # basis is the purchase cost and doesn't move with price.
                    cb = r.get("cost_basis")
                    if cb is not None:
                        cb_f = float(cb)
                        r["total_gain_dollar"] = r["market_value"] - cb_f
                        if cb_f != 0:
                            r["total_gain_pct"] = (r["market_value"] - cb_f) / cb_f * 100.0

        # Decorate with sector + current actionable + in_my_list
        if out:
            syms = list({r["symbol"] for r in out if r.get("symbol")})
            sector_map = {
                row[0]: row[1] for row in s.execute(text("""
                    SELECT DISTINCT ON (tos_symbol) tos_symbol, sector
                    FROM drv_dash
                    WHERE tos_symbol = ANY(:syms) AND as_of_date <= :d
                    ORDER BY tos_symbol, as_of_date DESC
                """), {"syms": syms, "d": d}).all()
            }
            act_map: dict = {}
            try:
                for row in s.execute(text("""
                    SELECT tos_symbol, consolidated_action, winning_source, winning_priority,
                           suggested_target_dollar, in_my_list
                    FROM drv_actionable
                    WHERE as_of_date = (SELECT MAX(as_of_date) FROM drv_actionable WHERE as_of_date <= :d)
                      AND tos_symbol = ANY(:syms)
                """), {"syms": syms, "d": d}).all():
                    act_map[row[0]] = {
                        "consolidated_action":    row[1],
                        "winning_source":         row[2],
                        "winning_priority":       row[3],
                        "suggested_target_dollar": float(row[4]) if row[4] is not None else None,
                        "in_my_list":             row[5],
                    }
            except Exception:
                pass
            in_my = set()
            try:
                for row in s.execute(text("SELECT tos_symbol FROM ref_my_stocks WHERE active = 'Y'")).all():
                    in_my.add(row[0])
            except Exception:
                pass
            for r in out:
                sym = r.get("symbol")
                r["sector"] = sector_map.get(sym)
                a = act_map.get(sym) or {}
                r["consolidated_action"]    = a.get("consolidated_action")
                r["winning_source"]         = a.get("winning_source")
                r["winning_priority"]       = a.get("winning_priority")
                r["suggested_target_dollar"] = a.get("suggested_target_dollar")
                r["in_my_list"]             = sym in in_my or bool(a.get("in_my_list"))

            # YTD / MTD gain per row
            ytd_start = d.replace(month=1, day=1)
            mtd_start = d.replace(day=1)

            def _snap_before(tbl, date_col, cutoff):
                return s.execute(text(
                    f"SELECT MAX({date_col}) FROM {tbl} WHERE {date_col} < :c"
                ), {"c": cutoff}).scalar()

            ytd_f  = _snap_before("hist_f",  "snapshot_date", ytd_start)
            ytd_cs = _snap_before("hist_cs", "snapshot_date", ytd_start)
            mtd_f  = _snap_before("hist_f",  "snapshot_date", mtd_start)
            mtd_cs = _snap_before("hist_cs", "snapshot_date", mtd_start)

            def _build_gain_map(tbl, date_col, snap, sym_col, acct_col, gain_col, src_label):
                if not snap:
                    return {}
                rows2 = s.execute(text(
                    f"SELECT {sym_col}, {acct_col}, COALESCE({gain_col},0) FROM {tbl} "
                    f"WHERE TRUE AND {date_col} = :s"
                ), {"s": snap}).all()
                return {(src_label, str(r[1]), r[0]): float(r[2]) for r in rows2}

            ytd_map = {
                **_build_gain_map("hist_f",  "snapshot_date", ytd_f,  "symbol", "account_number", "total_gl_dollar", "F"),
                **_build_gain_map("hist_cs", "snapshot_date", ytd_cs, "symbol", "account",         "gain_dollar",     "CS"),
            }
            mtd_map = {
                **_build_gain_map("hist_f",  "snapshot_date", mtd_f,  "symbol", "account_number", "total_gl_dollar", "F"),
                **_build_gain_map("hist_cs", "snapshot_date", mtd_cs, "symbol", "account",         "gain_dollar",     "CS"),
            }

            # Fetch Tot Amt parameter for % of TP calculation
            tot_amt_row = s.execute(text("""
                SELECT CAST(value AS NUMERIC) FROM ref_param
                WHERE sheet = '_param' AND param_name = 'Tot Amt'
            """)).scalar()
            tot_amt = float(tot_amt_row) if tot_amt_row else None

            for r in out:
                tg   = float(r.get("total_gain_dollar") or 0)
                src  = r.get("source", "")
                acct = r.get("account_id") or r.get("account") or ""
                sym  = r.get("symbol", "")
                if consolidated:
                    # sum ytd/mtd across all accounts for this symbol
                    ytd_b = sum(v for (s2, _a, sy), v in ytd_map.items() if sy == sym)
                    mtd_b = sum(v for (s2, _a, sy), v in mtd_map.items() if sy == sym)
                else:
                    key = (src, str(acct), sym)
                    ytd_b = ytd_map.get(key)
                    mtd_b = mtd_map.get(key)
                r["ytd_gain_dollar"] = tg - ytd_b if ytd_b is not None else tg
                r["mtd_gain_dollar"] = tg - mtd_b if mtd_b is not None else tg

                # Calculate % of TP (total portfolio target amount)
                mv = float(r.get("market_value") or 0)
                r["pct_of_tp"] = (mv / tot_amt * 100) if tot_amt and tot_amt > 0 else None

            # ─── Position-limit decoration ──────────────────────────────────
            # Resolve each symbol's lookup category (PS/ETF use asset_class)
            # and attach min/max/units + limit_status (BELOW_MIN/WITHIN/ABOVE_MAX/AT_FLOOR/NO_LIMIT).
            asset_class_ps = {}
            try:
                for row in s.execute(text("""
                    SELECT DISTINCT ON (ticker) ticker, asset_class
                    FROM hist_ps
                    WHERE asset_class IS NOT NULL AND asset_class <> ''
                      AND snapshot_date <= :d
                    ORDER BY ticker, snapshot_date DESC
                """), {"d": d}).fetchall():
                    asset_class_ps[row[0]] = row[1]
            except Exception:
                pass
            asset_class_etf = {}
            try:
                for row in s.execute(text("""
                    SELECT DISTINCT ON (symbol) symbol, asset_class
                    FROM hist_etf
                    WHERE asset_class IS NOT NULL AND asset_class <> ''
                      AND snapshot_date <= :d
                    ORDER BY symbol, snapshot_date DESC
                """), {"d": d}).fetchall():
                    asset_class_etf[row[0]] = row[1]
            except Exception:
                pass

            src_cat_map = {}
            try:
                for row in s.execute(text("""
                    SELECT source_code, position_category FROM ref_outlook_source
                """)).fetchall():
                    src_cat_map[row[0]] = row[1]
            except Exception:
                pass

            rule_map = {}
            try:
                for row in s.execute(text("""
                    SELECT category, min_dollar, max_dollar, units, maintain_min_position
                    FROM ref_asset_allocation
                """)).fetchall():
                    rule_map[row[0]] = {
                        "min_dollar": float(row[1]) if row[1] is not None else None,
                        "max_dollar": float(row[2]) if row[2] is not None else None,
                        "units":      float(row[3]) if row[3] is not None else None,
                        "maintain":   bool(row[4]),
                    }
            except Exception:
                pass

            for r in out:
                sym = r.get("symbol")
                win_src = r.get("winning_source")
                cat = None
                if win_src == "PS":
                    cat = asset_class_ps.get(sym) or src_cat_map.get(win_src)
                elif win_src == "ETF":
                    cat = asset_class_etf.get(sym) or src_cat_map.get(win_src)
                elif win_src == "ETFCHG":
                    # 1) explicit 'ETFCHG' row → 2) hist_etf.asset_class → 3) 'ETF' row → 4) source default
                    if "ETFCHG" in rule_map:
                        cat = "ETFCHG"
                    elif asset_class_etf.get(sym):
                        cat = asset_class_etf[sym]
                    elif "ETF" in rule_map:
                        cat = "ETF"
                    else:
                        cat = src_cat_map.get(win_src)
                elif win_src:
                    cat = src_cat_map.get(win_src)
                else:
                    # No actionable row — try asset_class lookups directly
                    cat = asset_class_ps.get(sym) or asset_class_etf.get(sym)

                rule = rule_map.get(cat) if cat else None
                r["applied_category"] = cat
                if rule:
                    r["limit_min"]   = rule["min_dollar"]
                    r["limit_max"]   = rule["max_dollar"]
                    r["limit_units"] = rule["units"]
                    r["limit_maintain_min"] = rule["maintain"]
                    mv = float(r.get("market_value") or 0)
                    if rule["min_dollar"] is not None and mv < rule["min_dollar"]:
                        r["limit_status"] = "BELOW_MIN"
                    elif rule["max_dollar"] is not None and mv > rule["max_dollar"]:
                        r["limit_status"] = "ABOVE_MAX"
                    elif (rule["min_dollar"] is not None and rule["maintain"]
                          and abs(mv - rule["min_dollar"]) < 1.0):
                        r["limit_status"] = "AT_FLOOR"
                    else:
                        r["limit_status"] = "WITHIN"
                else:
                    r["limit_min"] = None
                    r["limit_max"] = None
                    r["limit_units"] = None
                    r["limit_maintain_min"] = None
                    r["limit_status"] = "NO_LIMIT"

    return out


@router.get("/api/portfolio/activity")
def get_portfolio_activity(
    days: int = Query(180, ge=1, le=3650,
                      description="How far back to look (ignored if from/to set)"),
    from_date: Optional[str] = Query(None, alias="from"),
    to_date:   Optional[str] = Query(None, alias="to"),
    symbol:    Optional[str] = Query(None),
    account:   Optional[str] = Query(None,
                description="Substring match on account name/number"),
    source:    Optional[str] = Query(None, description="CS | F | (none = both)"),
    kind:      Optional[str] = Query(None,
                description="BUY | SELL | DIV | INT | CASH | OTHER (F only); "
                            "for CS we infer from the action text"),
    limit:     int = Query(500, ge=1, le=5000),
    offset:    int = Query(0, ge=0),
):
    """Unified activity feed across hist_cst + hist_ft.

    Output is one row per transaction, normalized to a common shape:
      { source, account, symbol, trade_date, action_kind, action,
        quantity, price, amount, fees, description }

    Ordered by trade_date DESC. Use ?source=CS or ?source=F to restrict.
    """
    from datetime import datetime, timedelta

    src = (source or "").upper()
    src_cs = src in ("", "CS")
    src_f  = src in ("", "F")

    # Date window resolution
    today = datetime.now().date()
    fd = None
    td = None
    if from_date:
        try:
            fd = datetime.strptime(from_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(400, "from must be YYYY-MM-DD")
    if to_date:
        try:
            td = datetime.strptime(to_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(400, "to must be YYYY-MM-DD")
    if fd is None:
        fd = today - timedelta(days=days)
    if td is None:
        td = today

    params: dict = {"fd": fd, "td": td, "lim": limit, "off": offset}
    parts: list[str] = []

    # CS branch — derive kind from the short Schwab action text.
    cs_kind_expr = (
        "CASE UPPER(action) "
        "WHEN 'BUY'  THEN 'BUY'  "
        "WHEN 'SELL' THEN 'SELL' "
        "WHEN 'DIVIDEND' THEN 'DIV' "
        "WHEN 'INTEREST' THEN 'INT' "
        "WHEN 'REINVEST SHARES' THEN 'BUY' "
        "WHEN 'REINVEST DIVIDEND' THEN 'BUY' "
        "ELSE 'OTHER' END"
    )
    if src_cs:
        cs_sql = f"""
          SELECT 'CS' AS source,
                 account, symbol, trade_date,
                 {cs_kind_expr} AS action_kind,
                 action,
                 quantity, price, amount, fees,
                 description
          FROM hist_cst
          WHERE trade_date BETWEEN :fd AND :td
        """
        if symbol:
            cs_sql += " AND UPPER(symbol) = :sym"; params["sym"] = symbol.upper()
        if account:
            cs_sql += " AND account ILIKE :acc"; params["acc"] = f"%{account}%"
        if kind:
            cs_sql += f" AND {cs_kind_expr} = :kind"; params["kind"] = kind.upper()
        parts.append(cs_sql)

    if src_f:
        f_sql = """
          SELECT 'F' AS source,
                 account, symbol, trade_date,
                 action_kind,
                 action,
                 quantity, price, amount, fees,
                 description
          FROM hist_ft
          WHERE trade_date BETWEEN :fd AND :td
        """
        if symbol:
            f_sql += " AND UPPER(symbol) = :sym"; params["sym"] = symbol.upper()
        if account:
            f_sql += " AND (account ILIKE :acc OR account_number ILIKE :acc)"
            params["acc"] = f"%{account}%"
        if kind:
            f_sql += " AND action_kind = :kind"; params["kind"] = kind.upper()
        parts.append(f_sql)

    if not parts:
        return []

    union = " UNION ALL ".join(f"({p})" for p in parts)
    sql = f"""
        SELECT * FROM ({union}) u
        ORDER BY trade_date DESC, source, symbol
        LIMIT :lim OFFSET :off
    """
    with session_scope() as s:
        rows = s.execute(text(sql), params).mappings().all()
    return [dict(r) for r in rows]


@router.get("/api/portfolio/accounts")
def get_portfolio_accounts(
    has_realized: bool = Query(True,
        description="Only return accounts that have at least one realized-gain row"),
):
    """List distinct accounts for the Realized tab's filter dropdown.

    When has_realized=True (default), returns only accounts with at least one
    sell event in drv_realized_gain — so the dropdown stays useful.
    """
    if has_realized:
        sql = """
            SELECT DISTINCT account, source
            FROM drv_realized_gain
            WHERE account IS NOT NULL
            ORDER BY source, account
        """
    else:
        # Union of every account known anywhere
        sql = """
            SELECT DISTINCT account, source FROM (
              SELECT COALESCE(account_name, account_number) AS account, 'F'  AS source FROM hist_f
              UNION  SELECT account, 'CS'    FROM hist_cs
              UNION  SELECT COALESCE(account, account_number) AS account, 'F'     FROM hist_ft
              UNION  SELECT account, 'CS'    FROM hist_cst
            ) u
            WHERE account IS NOT NULL
            ORDER BY source, account
        """
    with session_scope() as s:
        rows = s.execute(text(sql)).all()
    return [{"account": r[0], "source": r[1]} for r in rows]


@router.get("/api/portfolio/realized")
def get_portfolio_realized(
    date: Optional[str] = Query(None,
        description="Anchor date for YTD/MTD comparison columns (default = today)"),
    symbol:  Optional[str] = Query(None),
    account: Optional[str] = Query(None,
        description="Substring match on account name (ILIKE %account%)"),
    source:  Optional[str] = Query(None),
    group_by: str = Query("symbol", description="symbol | account | none (= raw sells)"),
    from_date: Optional[str] = Query(None, alias="from",
        description="Filter result rows to sell_date >= this (YYYY-MM-DD)"),
    to_date: Optional[str]   = Query(None, alias="to",
        description="Filter result rows to sell_date <= this (YYYY-MM-DD)"),
):
    """Realized-gain rollup from drv_realized_gain (FIFO matched).

    Three response shapes depending on `group_by`:
      symbol  → one row per symbol with totals + YTD + MTD
      account → one row per account with totals + YTD + MTD
      none    → raw sell-event rows ordered by sell_date DESC
                (use this view to drill into per-sale detail + lots_consumed)

    Date filters:
      • date         — anchor for the YTD / MTD comparison columns
      • from / to    — restrict the underlying sell events. Used by the
                       MTD / YTD / Custom presets in the Realized tab.
    """
    from datetime import datetime

    d = _resolve_date(date)
    ytd_start = d.replace(month=1, day=1)
    mtd_start = d.replace(day=1)

    # Parse from / to YYYY-MM-DD
    fd = None
    td = None
    if from_date:
        try:
            fd = datetime.strptime(from_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(400, "from must be YYYY-MM-DD")
    if to_date:
        try:
            td = datetime.strptime(to_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(400, "to must be YYYY-MM-DD")

    where_extra = []
    params: dict = {"d": d, "ytd": ytd_start, "mtd": mtd_start}
    if symbol:
        where_extra.append("symbol = :sym"); params["sym"] = symbol.upper()
    if account:
        where_extra.append("account ILIKE :acc"); params["acc"] = f"%{account}%"
    if source:
        where_extra.append("source = :src"); params["src"] = source.upper()
    if fd:
        where_extra.append("sell_date >= :fd"); params["fd"] = fd
    if td:
        where_extra.append("sell_date <= :td"); params["td"] = td
    wclause = (" AND " + " AND ".join(where_extra)) if where_extra else ""

    if group_by == "none":
        sql = f"""
            SELECT source, account, symbol, sell_date, shares_sold,
                   sell_proceeds, cost_basis, realized_gain, realized_gain_pct,
                   holding_days_avg, is_long_term, lots_consumed
            FROM drv_realized_gain
            WHERE sell_date <= :d {wclause}
            ORDER BY sell_date DESC, symbol
            LIMIT 1000
        """
        with session_scope() as s:
            return [dict(r) for r in s.execute(text(sql), params).mappings().all()]

    key = "symbol" if group_by == "symbol" else "account"
    if key not in ("symbol", "account"):
        key = "symbol"
    sql = f"""
        SELECT {key} AS bucket,
               COUNT(*) AS n_sells,
               SUM(shares_sold)                                   AS total_shares,
               SUM(sell_proceeds)                                 AS total_proceeds,
               SUM(cost_basis)                                    AS total_cost,
               SUM(realized_gain)                                 AS total_realized,
               SUM(CASE WHEN sell_date >= :ytd
                        THEN realized_gain ELSE 0 END)            AS ytd_realized,
               SUM(CASE WHEN sell_date >= :mtd
                        THEN realized_gain ELSE 0 END)            AS mtd_realized,
               SUM(CASE WHEN is_long_term THEN realized_gain
                        ELSE 0 END)                               AS long_term_gain,
               SUM(CASE WHEN NOT is_long_term THEN realized_gain
                        ELSE 0 END)                               AS short_term_gain,
               MIN(sell_date)                                     AS first_sell,
               MAX(sell_date)                                     AS last_sell
        FROM drv_realized_gain
        WHERE sell_date <= :d {wclause}
        GROUP BY {key}
        ORDER BY total_realized DESC NULLS LAST
    """
    with session_scope() as s:
        rows = s.execute(text(sql), params).mappings().all()
    return [dict(r) for r in rows]


@router.get("/api/portfolio/snapshot-status")
def get_portfolio_snapshot_status():
    """One row per account telling you how stale that account's last snapshot
    is. Used by the Portfolio screen to flag stale data ("CS Rollover_IRA
    hasn't been refreshed in 4 days — current value may be off")."""
    sql = """
        WITH cs AS (
          SELECT 'CS' AS source, account AS account, MAX(snapshot_date) AS last_snapshot
          FROM hist_cs GROUP BY account
        ),
        f AS (
          SELECT 'F' AS source,
                 COALESCE(account_name, account_number) AS account,
                 MAX(snapshot_date) AS last_snapshot
          FROM hist_f GROUP BY COALESCE(account_name, account_number)
        )
        SELECT source, account, last_snapshot,
               (CURRENT_DATE - last_snapshot) AS days_stale
        FROM (SELECT * FROM cs UNION ALL SELECT * FROM f) u
        ORDER BY days_stale DESC, source, account
    """
    with session_scope() as s:
        rows = s.execute(text(sql)).mappings().all()
        # Per-tab "latest data" so the Portfolio screen can pick a sensible
        # default period for Activity (hist_cst) and Realized (drv_cs_realized_gain).
        # When today has no rows we want the UI to land on Custom + last
        # available date for that specific tab.
        meta = s.execute(text("""
            SELECT
              (SELECT MAX(trade_date) FROM hist_cst)             AS last_activity_date,
              (SELECT EXISTS(SELECT 1 FROM hist_cst
                              WHERE trade_date = CURRENT_DATE))  AS activity_today,
              (SELECT MAX(as_of_date) FROM drv_cs_realized_gain) AS last_realized_date,
              (SELECT EXISTS(SELECT 1 FROM drv_cs_realized_gain
                              WHERE as_of_date = CURRENT_DATE))  AS realized_today
        """)).mappings().first() or {}
    return {
        "rows": [dict(r) for r in rows],
        "last_activity_date": meta.get("last_activity_date").isoformat()
            if meta.get("last_activity_date") else None,
        "activity_today":     bool(meta.get("activity_today")),
        "last_realized_date": meta.get("last_realized_date").isoformat()
            if meta.get("last_realized_date") else None,
        "realized_today":     bool(meta.get("realized_today")),
    }


@router.get("/api/portfolio/trends")
def get_portfolio_trends(
    period:  str           = Query("mtd", description="mtd | ytd | 1y | 5y"),
    account: Optional[str] = Query(None),
    source:  Optional[str] = Query(None, description="CS | F | (none = both)"),
):
    """Portfolio trend data for the Trends panel on the Positions tab.

    Returns time-series arrays suitable for Chart.js:
      - dates[]            -- one entry per snapshot date in window
      - account_value[]    -- total market value (held positions) per date
      - day_change[]       -- daily P&L per date
      - cumulative_pl[]    -- running sum of day_change
      - per_account[acct]  -- per-account market value series for sparklines

    Period maps to a start-date relative to today:
      mtd = 1st of current month, ytd = Jan 1, 1y = 365 days back, 5y = 5*365 back
    """
    from datetime import datetime as _dt, timedelta as _td
    today = _dt.now().date()
    if period == "ytd":
        start = today.replace(month=1, day=1)
    elif period == "1y":
        start = today - _td(days=365)
    elif period == "5y":
        start = today - _td(days=365 * 5)
    elif period == "30d":
        start = today - _td(days=30)
    elif period == "90d":
        start = today - _td(days=90)
    elif period == "180d":
        start = today - _td(days=180)
    else:  # default mtd
        start = today.replace(day=1)

    src_u = (source or "").upper()
    inc_cs = src_u in ("", "CS")
    inc_f  = src_u in ("", "F")

    params: dict = {"start": start, "end": today}
    if account:
        params["acct"] = account

    cs_acct_clause = " AND account = :acct" if account else ""
    f_acct_clause  = " AND COALESCE(account_name, account_number) = :acct" if account else ""

    unions = []
    if inc_cs:
        unions.append(f"""
            SELECT snapshot_date AS d,
                   account       AS acct,
                   SUM(CASE WHEN {CS_IS_NOT_CASH} THEN market_value ELSE 0 END)        AS mv,
                   SUM(CASE WHEN {CS_IS_NOT_CASH} THEN COALESCE(day_chng_dollar,0) ELSE 0 END) AS dc
              FROM hist_cs
             WHERE snapshot_date BETWEEN :start AND :end {cs_acct_clause}
             GROUP BY snapshot_date, account
        """)
    if inc_f:
        unions.append(f"""
            SELECT snapshot_date AS d,
                   COALESCE(account_name, account_number) AS acct,
                   SUM(CASE WHEN {F_IS_NOT_CASH} THEN current_value ELSE 0 END)    AS mv,
                   SUM(CASE WHEN {F_IS_NOT_CASH} THEN today_gl_dollar  ELSE 0 END) AS dc
              FROM hist_f
             WHERE snapshot_date BETWEEN :start AND :end {f_acct_clause}
             GROUP BY snapshot_date, COALESCE(account_name, account_number)
        """)
    if not unions:
        return {"dates": [], "account_value": [], "day_change": [],
                "cumulative_pl": [], "per_account": {}}

    sql = "SELECT d, acct, mv, dc FROM (" + " UNION ALL ".join(unions) + \
          ") u ORDER BY d, acct"

    with session_scope() as s:
        rows = s.execute(text(sql), params).all()

    # Aggregate by date for the headline series, and build per-account series.
    from collections import defaultdict
    by_date: dict = defaultdict(lambda: {"mv": 0.0, "dc": 0.0})
    acct_dates: dict = defaultdict(set)
    acct_series: dict = defaultdict(dict)   # acct -> {date: mv}
    for d, acct, mv, dc in rows:
        by_date[d]["mv"] += float(mv or 0)
        by_date[d]["dc"] += float(dc or 0)
        acct_series[acct][d] = float(mv or 0)
        acct_dates[acct].add(d)

    dates_sorted = sorted(by_date.keys())
    account_value = [round(by_date[d]["mv"], 2) for d in dates_sorted]
    day_change    = [round(by_date[d]["dc"], 2) for d in dates_sorted]
    cum = 0.0
    cumulative_pl = []
    for v in day_change:
        cum += v
        cumulative_pl.append(round(cum, 2))

    # For sparklines: align each account's series to dates_sorted, fill gaps
    # with the previous value (no snapshot that day → carry forward).
    per_account = {}
    for acct, dvals in acct_series.items():
        last = None
        arr = []
        for d in dates_sorted:
            if d in dvals:
                last = dvals[d]
            arr.append(round(last, 2) if last is not None else None)
        per_account[acct] = arr

    return {
        "period":        period,
        "start":         start.isoformat(),
        "end":           today.isoformat(),
        "dates":         [d.isoformat() for d in dates_sorted],
        "account_value": account_value,
        "day_change":    day_change,
        "cumulative_pl": cumulative_pl,
        "per_account":   per_account,
    }


@router.get("/api/portfolio/summary")
def get_portfolio_summary(date: Optional[str] = Query(None)):
    """KPI strip: totals + per-account breakdown + YTD/MTD on the resolved date."""
    d = _resolve_date(date)
    ytd_start = d.replace(month=1, day=1)
    mtd_start = d.replace(day=1)

    with session_scope() as s:
        # Overall totals (MV includes all cash, gains/cost/legs exclude cash)
        row = s.execute(text(f"""
            WITH latest_cs AS (
                SELECT MAX(snapshot_date) AS d FROM hist_cs WHERE snapshot_date <= :d
            ),
            prev_cs_snap AS (
                SELECT MAX(snapshot_date) AS d FROM hist_cs
                 WHERE snapshot_date < (SELECT d FROM latest_cs)
            ),
            prev_close_cs AS (
                -- yesterday's close per (account, symbol)
                SELECT account, tos_symbol, price
                  FROM hist_cs
                 WHERE snapshot_date = (SELECT d FROM prev_cs_snap)
            ),
            cs_sold_move AS (
                -- For each sell today: (sell_price - yesterday_close) * abs(qty)
                SELECT cst.account,
                       SUM((cst.price - pc.price) * ABS(COALESCE(cst.quantity, 0))) AS amt
                  FROM hist_cst cst
                  JOIN prev_close_cs pc
                    ON pc.account = cst.account AND pc.tos_symbol = cst.tos_symbol
                 WHERE cst.trade_date = (SELECT d FROM latest_cs)
                   AND UPPER(COALESCE(cst.action, '')) LIKE '%SELL%'
                   AND cst.quantity IS NOT NULL
                   AND cst.price    IS NOT NULL
                 GROUP BY cst.account
            ),
            cs_div_int AS (
                -- Dividends, interest, reinvested income today (settled in cash)
                SELECT account, SUM(COALESCE(amount, 0)) AS amt
                  FROM hist_cst
                 WHERE trade_date = (SELECT d FROM latest_cs)
                   AND (UPPER(COALESCE(action, '')) LIKE '%DIVIDEND%'
                        OR UPPER(COALESCE(action, '')) LIKE '%INTEREST%'
                        OR UPPER(COALESCE(action, '')) LIKE '%REINV%')
                 GROUP BY account
            ),
            u AS (
              SELECT CASE WHEN {F_IS_NOT_CASH} THEN current_value ELSE 0 END AS mv,
                     CASE WHEN {F_IS_NOT_CASH} THEN today_gl_dollar ELSE 0 END AS tg,
                     CASE WHEN {F_IS_NOT_CASH} THEN today_gl_dollar ELSE 0 END AS dc,
                     0::NUMERIC AS rt,
                     CASE WHEN {F_IS_NOT_CASH} THEN total_gl_dollar ELSE 0 END AS sg,
                     CASE WHEN {F_IS_NOT_CASH} THEN cost_basis_total ELSE 0 END AS cb,
                     CASE WHEN {F_IS_NOT_CASH} THEN 1 ELSE 0 END AS leg_count,
                     CASE WHEN {F_IS_CASH} THEN current_value ELSE 0 END AS cash_mv
              FROM hist_f
              WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM hist_f WHERE snapshot_date <= :d)
              UNION ALL
              SELECT CASE WHEN {CS_IS_NOT_CASH_C} THEN c.market_value ELSE 0 END,
                     -- CS today_gain row contribution: just day_chng. Per-account intraday-on-sold + DIV/INT added below.
                     CASE WHEN {CS_IS_NOT_CASH_C}
                          THEN COALESCE(c.day_chng_dollar, 0) ELSE 0 END,
                     CASE WHEN {CS_IS_NOT_CASH_C}
                          THEN COALESCE(c.day_chng_dollar, 0) ELSE 0 END,
                     CASE WHEN {CS_IS_NOT_CASH_C}
                          THEN COALESCE(rg.realized_gain, 0) ELSE 0 END,
                     CASE WHEN {CS_IS_NOT_CASH_C} THEN c.gain_dollar ELSE 0 END,
                     CASE WHEN {CS_IS_NOT_CASH_C} THEN c.cost_basis ELSE 0 END,
                     CASE WHEN {CS_IS_NOT_CASH_C} THEN 1 ELSE 0 END,
                     CASE WHEN {CS_IS_CASH_C} THEN c.market_value ELSE 0 END
              FROM hist_cs c
              LEFT JOIN drv_cs_realized_gain rg
                   ON rg.account = c.account
                  AND rg.tos_symbol = c.tos_symbol
                  AND rg.as_of_date = (SELECT d FROM latest_cs)
              WHERE c.snapshot_date = (SELECT d FROM latest_cs)
            )
            SELECT COALESCE(SUM(mv),0) AS market_value,
                   -- Schwab-style Today's Gain:
                   --   per-position day_chng (held)
                   -- + intraday move on sold shares (sell_price - yesterday_close) * qty
                   -- + dividends/interest today (settled to cash)
                   COALESCE(SUM(tg),0)
                     + COALESCE((SELECT SUM(amt) FROM cs_sold_move), 0)
                     + COALESCE((SELECT SUM(amt) FROM cs_div_int),   0)
                     AS today_gain_dollar,
                   COALESCE(SUM(dc),0) AS day_change_dollar,
                   -- Pull realized_today directly from drv_cs_realized_gain so
                   -- fully-sold-out positions (no hist_cs row today) are counted.
                   -- Strictly today's snapshot: if nothing was sold on the
                   -- current day this returns 0 (no fall-through to prior days).
                   COALESCE((SELECT SUM(realized_gain) FROM drv_cs_realized_gain
                              WHERE as_of_date = (SELECT d FROM latest_cs)), 0)
                       AS realized_today_dollar,
                   COALESCE(SUM(sg),0) AS total_gain_dollar,
                   COALESCE(SUM(cb),0) AS cost_basis,
                   COALESCE(SUM(leg_count),0)::INTEGER AS legs,
                   COALESCE(SUM(cash_mv),0) AS cash_value
            FROM u
        """), {"d": d}).mappings().first()

        # Per-account breakdown (exclude cash positions from totals, but include cash value separately)
        acct_rows = list(s.execute(text(f"""
            WITH f_accts AS (
              SELECT 'F' AS source,
                     COALESCE(account_name, account_number) AS account,
                     SUM(CASE WHEN {F_IS_NOT_CASH} THEN current_value ELSE 0 END) AS market_value,
                     SUM(CASE WHEN {F_IS_NOT_CASH} THEN today_gl_dollar ELSE 0 END) AS today_gain_dollar,
                     SUM(CASE WHEN {F_IS_NOT_CASH} THEN today_gl_dollar ELSE 0 END) AS day_change_dollar,
                     0::NUMERIC AS realized_today_dollar,
                     SUM(CASE WHEN {F_IS_NOT_CASH} THEN total_gl_dollar ELSE 0 END) AS total_gain_dollar,
                     SUM(CASE WHEN {F_IS_NOT_CASH} THEN cost_basis_total ELSE 0 END) AS cost_basis,
                     COUNT(DISTINCT CASE WHEN {F_IS_NOT_CASH} THEN symbol END) AS positions,
                     SUM(CASE WHEN {F_IS_CASH} THEN current_value ELSE 0 END) AS cash_value
              FROM hist_f
              WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM hist_f WHERE snapshot_date <= :d)
              GROUP BY COALESCE(account_name, account_number)
            ),
            latest_cs AS (
              SELECT MAX(snapshot_date) AS d FROM hist_cs WHERE snapshot_date <= :d
            ),
            prev_cs_snap AS (
              SELECT MAX(snapshot_date) AS d FROM hist_cs
               WHERE snapshot_date < (SELECT d FROM latest_cs)
            ),
            prev_close_cs AS (
              SELECT account, tos_symbol, price FROM hist_cs
               WHERE snapshot_date = (SELECT d FROM prev_cs_snap)
            ),
            cs_sold_move AS (
              SELECT cst.account,
                     SUM((cst.price - pc.price) * ABS(COALESCE(cst.quantity, 0))) AS amt
                FROM hist_cst cst
                JOIN prev_close_cs pc
                  ON pc.account = cst.account AND pc.tos_symbol = cst.tos_symbol
               WHERE cst.trade_date = (SELECT d FROM latest_cs)
                 AND UPPER(COALESCE(cst.action, '')) LIKE '%SELL%'
                 AND cst.quantity IS NOT NULL
                 AND cst.price    IS NOT NULL
               GROUP BY cst.account
            ),
            cs_div_int AS (
              SELECT account, SUM(COALESCE(amount, 0)) AS amt
                FROM hist_cst
               WHERE trade_date = (SELECT d FROM latest_cs)
                 AND (UPPER(COALESCE(action, '')) LIKE '%DIVIDEND%'
                      OR UPPER(COALESCE(action, '')) LIKE '%INTEREST%'
                      OR UPPER(COALESCE(action, '')) LIKE '%REINV%')
               GROUP BY account
            ),
            -- Realized P&L per account, directly from drv_cs_realized_gain.
            -- Strictly today's snapshot (no fall-back). Captures sold-out
            -- positions that no longer appear in hist_cs.
            cs_realized_by_acct AS (
              SELECT account, SUM(realized_gain) AS realized_today_dollar
                FROM drv_cs_realized_gain
               WHERE as_of_date = (SELECT d FROM latest_cs)
               GROUP BY account
            ),
            cs_accts AS (
              SELECT 'CS' AS source,
                     c.account,
                     SUM(CASE WHEN {CS_IS_NOT_CASH_C} THEN c.market_value ELSE 0 END) AS market_value,
                     -- Schwab-style Today's Gain per account (day_chng + sold-intraday + DIV/INT)
                     SUM(CASE WHEN {CS_IS_NOT_CASH_C}
                              THEN COALESCE(c.day_chng_dollar, 0) ELSE 0 END)
                       + COALESCE(MAX(sm.amt), 0)
                       + COALESCE(MAX(di.amt), 0)
                       AS today_gain_dollar,
                     SUM(CASE WHEN {CS_IS_NOT_CASH_C}
                              THEN COALESCE(c.day_chng_dollar, 0) ELSE 0 END) AS day_change_dollar,
                     -- Direct from drv_cs_realized_gain via the per-account
                     -- pre-aggregate CTE so fully-sold-out positions are
                     -- counted (LEFT JOIN above only sees still-held rows).
                     COALESCE(MAX(rt2.realized_today_dollar), 0) AS realized_today_dollar,
                     SUM(CASE WHEN {CS_IS_NOT_CASH_C} THEN c.gain_dollar ELSE 0 END) AS total_gain_dollar,
                     SUM(CASE WHEN {CS_IS_NOT_CASH_C} THEN c.cost_basis ELSE 0 END) AS cost_basis,
                     COUNT(DISTINCT CASE WHEN {CS_IS_NOT_CASH_C} THEN c.symbol END) AS positions,
                     SUM(CASE WHEN {CS_IS_CASH_C} THEN c.market_value ELSE 0 END) AS cash_value
              FROM hist_cs c
              LEFT JOIN drv_cs_realized_gain rg
                   ON rg.account = c.account
                  AND rg.tos_symbol = c.tos_symbol
                  AND rg.as_of_date = (SELECT d FROM latest_cs)
              LEFT JOIN cs_sold_move sm ON sm.account = c.account
              LEFT JOIN cs_div_int   di ON di.account = c.account
              LEFT JOIN cs_realized_by_acct rt2 ON rt2.account = c.account
              WHERE c.snapshot_date = (SELECT d FROM latest_cs)
              GROUP BY c.account
            )
            SELECT * FROM f_accts
            UNION ALL
            SELECT * FROM cs_accts
            ORDER BY source, account
        """), {"d": d}).mappings().all())

        # YTD/MTD per-account baselines
        ytd_cs_acct = {}
        mtd_cs_acct = {}

        # Get YTD baseline (last snapshot before Jan 1)
        ytd_snap = s.execute(text(
            "SELECT MAX(snapshot_date) FROM hist_cs WHERE snapshot_date < :s"
        ), {"s": ytd_start}).scalar()
        if ytd_snap:
            ytd_rows = s.execute(text(f"""
                SELECT account, COALESCE(SUM(gain_dollar),0) AS total_gain_dollar
                FROM hist_cs
                WHERE snapshot_date = :s AND {CS_IS_NOT_CASH}
                GROUP BY account
            """), {"s": ytd_snap}).mappings().all()
            for r in ytd_rows:
                ytd_cs_acct[r["account"]] = float(r["total_gain_dollar"] or 0)

        # Get MTD baseline (last snapshot before 1st of this month)
        mtd_snap = s.execute(text(
            "SELECT MAX(snapshot_date) FROM hist_cs WHERE snapshot_date < :s"
        ), {"s": mtd_start}).scalar()
        if mtd_snap:
            mtd_rows = s.execute(text(f"""
                SELECT account, COALESCE(SUM(gain_dollar),0) AS total_gain_dollar
                FROM hist_cs
                WHERE snapshot_date = :s AND {CS_IS_NOT_CASH}
                GROUP BY account
            """), {"s": mtd_snap}).mappings().all()
            for r in mtd_rows:
                mtd_cs_acct[r["account"]] = float(r["total_gain_dollar"] or 0)

        # Global YTD/MTD (for KPI strip)
        ytd_f = s.execute(text(
            "SELECT MAX(snapshot_date) FROM hist_f WHERE snapshot_date < :s"
        ), {"s": ytd_start}).scalar()
        ytd_cs_global = s.execute(text(
            "SELECT MAX(snapshot_date) FROM hist_cs WHERE snapshot_date < :s"
        ), {"s": ytd_start}).scalar()

        def _gain_sum(tbl, date_col, snap):
            if not snap:
                return 0.0
            gain_col = "total_gl_dollar" if tbl == "hist_f" else "gain_dollar"
            symbol_filter = f"AND {F_IS_NOT_CASH}" if tbl == "hist_f" \
                          else f"AND {CS_IS_NOT_CASH}"
            v = s.execute(text(
                f"SELECT COALESCE(SUM({gain_col}),0) FROM {tbl} "
                f"WHERE TRUE AND {date_col} = :s {symbol_filter}"
            ), {"s": snap}).scalar()
            return float(v or 0)

        ytd_base = _gain_sum("hist_f", "snapshot_date", ytd_f) + _gain_sum("hist_cs", "snapshot_date", ytd_cs_global)

        # MTD baseline: last snapshot before 1st of this month
        mtd_f  = s.execute(text(
            "SELECT MAX(snapshot_date) FROM hist_f WHERE snapshot_date < :s"
        ), {"s": mtd_start}).scalar()
        mtd_cs_global = s.execute(text(
            "SELECT MAX(snapshot_date) FROM hist_cs WHERE snapshot_date < :s"
        ), {"s": mtd_start}).scalar()
        mtd_base = _gain_sum("hist_f", "snapshot_date", mtd_f) + _gain_sum("hist_cs", "snapshot_date", mtd_cs_global)

        pos_count = s.execute(text(f"""
            WITH u AS (
              SELECT DISTINCT symbol FROM hist_f WHERE TRUE
                AND snapshot_date = (SELECT MAX(snapshot_date) FROM hist_f WHERE snapshot_date <= :d)
                AND {F_IS_NOT_CASH}
              UNION
              SELECT DISTINCT symbol FROM hist_cs WHERE TRUE
                AND snapshot_date = (SELECT MAX(snapshot_date) FROM hist_cs WHERE snapshot_date <= :d)
                AND {CS_IS_NOT_CASH}
            ) SELECT COUNT(*) FROM u
        """), {"d": d}).scalar() or 0

        # ─── Position-limit counts: above_max / below_min / at_floor ───────
        # NOTE: this MUST be inside the session block; the prior version
        # used `s` after the with-block had closed, and the bare
        # try/except silently swallowed "session is closed" errors so the
        # counts always returned 0.
        cnt = None
        try:
            cnt = s.execute(text(f"""
          WITH pos AS (
            SELECT symbol, SUM(mv) AS mv FROM (
              SELECT symbol, COALESCE(current_value,0) AS mv FROM hist_f
                WHERE TRUE
                  AND snapshot_date = (SELECT MAX(snapshot_date) FROM hist_f WHERE snapshot_date <= :d)
                  AND {F_IS_NOT_CASH}
              UNION ALL
              SELECT symbol, COALESCE(market_value,0) FROM hist_cs
                WHERE TRUE
                  AND snapshot_date = (SELECT MAX(snapshot_date) FROM hist_cs WHERE snapshot_date <= :d)
                  AND {CS_IS_NOT_CASH}
            ) u GROUP BY symbol
          ),
          ac_ps AS (
            SELECT DISTINCT ON (ticker) ticker AS symbol, asset_class FROM hist_ps
            WHERE asset_class IS NOT NULL AND asset_class <> '' AND snapshot_date <= :d
            ORDER BY ticker, snapshot_date DESC
          ),
          ac_etf AS (
            SELECT DISTINCT ON (symbol) symbol, asset_class FROM hist_etf
            WHERE asset_class IS NOT NULL AND asset_class <> '' AND snapshot_date <= :d
            ORDER BY symbol, snapshot_date DESC
          ),
          joined AS (
            SELECT p.symbol, p.mv,
                   COALESCE(ac_ps.asset_class, ac_etf.asset_class) AS category,
                   raa.min_dollar, raa.max_dollar, raa.maintain_min_position
            FROM pos p
            LEFT JOIN ac_ps ON ac_ps.symbol = p.symbol
            LEFT JOIN ac_etf  ON ac_etf.symbol  = p.symbol
            LEFT JOIN ref_asset_allocation raa
              ON raa.category = COALESCE(ac_ps.asset_class, ac_etf.asset_class)
          )
          SELECT
            COUNT(*) FILTER (WHERE max_dollar IS NOT NULL AND mv > max_dollar)              AS above_max,
            COUNT(*) FILTER (WHERE min_dollar IS NOT NULL AND mv < min_dollar)              AS below_min,
            COUNT(*) FILTER (WHERE min_dollar IS NOT NULL AND maintain_min_position
                                   AND abs(mv - min_dollar) < 1.0)                          AS at_floor
          FROM joined
            """), {"d": d}).mappings().first()
        except Exception:
            cnt = None

    # ── outside the session: assemble the response dict ────────────────────
    d2 = dict(row) if row else {}
    cb = float(d2.get("cost_basis") or 0)
    sg = float(d2.get("total_gain_dollar") or 0)
    mv = float(d2.get("market_value") or 0)
    tg = float(d2.get("today_gain_dollar") or 0)
    d2["total_gain_pct"]  = (sg / cb * 100) if cb else None
    d2["today_gain_pct"]  = (tg / (mv - tg) * 100) if (mv - tg) else None
    d2["ytd_gain_dollar"] = sg - ytd_base
    d2["mtd_gain_dollar"] = sg - mtd_base
    d2["accounts"]        = sum(1 for _ in acct_rows)
    d2["positions"]       = int(pos_count)
    d2["as_of_date"]      = d.isoformat()
    d2["above_max"] = int(cnt["above_max"] or 0) if cnt else 0
    d2["below_min"] = int(cnt["below_min"] or 0) if cnt else 0
    d2["at_floor"]  = int(cnt["at_floor"]  or 0) if cnt else 0
    d2["by_account"]       = []
    for r in acct_rows:
        mv = float(r["market_value"] or 0)
        tgd = float(r["today_gain_dollar"] or 0)
        tgp_denom = mv - tgd
        sgd = float(r["total_gain_dollar"] or 0)
        cb = float(r["cost_basis"] or 0)
        ytd_gain = sgd - ytd_cs_acct.get(r["account"], 0)
        mtd_gain = sgd - mtd_cs_acct.get(r["account"], 0)

        dcd = float(r["day_change_dollar"] or 0)
        rtd = float(r["realized_today_dollar"] or 0)
        d2["by_account"].append({
            "source":              r["source"],
            "account":             r["account"],
            "market_value":        mv,
            "today_gain_dollar":   tgd,
            "today_gain_pct":      (tgd / tgp_denom * 100) if tgp_denom else None,
            "day_change_dollar":   dcd,
            "realized_today_dollar": rtd,
            "ytd_gain_dollar":     ytd_gain,
            "mtd_gain_dollar":     mtd_gain,
            "cost_basis":          cb,
            "cash_value":          float(r["cash_value"] or 0),
            "positions":           int(r["positions"] or 0),
        })
    return d2


@router.get("/api/portfolio/{symbol}")
def get_portfolio_symbol(
    symbol: str,
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
    limit_days: int = Query(180, ge=1, le=2000),
):
    """Per-symbol detail bundle: snapshot timeseries + legs + user_actions + actionable history."""
    sym = symbol.upper().strip()
    params: dict = {"sym": sym, "lim": limit_days}
    where_t = []
    if from_date:
        try:
            params["fd"] = datetime.strptime(from_date, "%Y-%m-%d").date()
            where_t.append("snapshot_date >= :fd")
        except ValueError:
            pass
    if to_date:
        try:
            params["td"] = datetime.strptime(to_date, "%Y-%m-%d").date()
            where_t.append("snapshot_date <= :td")
        except ValueError:
            pass
    where_extra = (" AND " + " AND ".join(where_t)) if where_t else ""

    with session_scope() as s:
        # Snapshot time series (consolidated across sources & accounts)
        ts = s.execute(text(f"""
          WITH u AS (
            SELECT snapshot_date, qty, current_value AS mv, total_gl_dollar AS tg
            FROM hist_f
            WHERE symbol = :sym {where_extra}
            UNION ALL
            SELECT snapshot_date, qty, market_value AS mv, gain_dollar AS tg
            FROM hist_cs
            WHERE symbol = :sym {where_extra}
          )
          SELECT snapshot_date,
                 SUM(qty) AS qty,
                 SUM(mv)  AS market_value,
                 SUM(tg)  AS total_gain_dollar
          FROM u
          GROUP BY snapshot_date
          ORDER BY snapshot_date DESC
          LIMIT :lim
        """), params).mappings().all()

        # Leg events RETIRED 2026-05-12 — hist_f / hist_cs leg_* + ignore_flag + qty_diff cols dropped.
        # Per-event history is no longer reconstructable; the drilldown shows only the snapshot timeline.
        legs = []

        # User actions
        # User actions
        actions = s.execute(text("""
          SELECT acted_at, user_id, as_of_date, user_action, user_action_target,
                 snooze_until, user_notes, consolidated_action, winning_source,
                 winning_priority, position_category, suggested_target_dollar,
                 position_dollar_at_action
          FROM user_action_log
          WHERE symbol = :sym
          ORDER BY acted_at DESC
          LIMIT 100
        """), {"sym": sym}).mappings().all()

        # Actionable recommendation history
        rec_hist = []
        try:
            rec_hist = s.execute(text("""
              SELECT as_of_date, consolidated_action, winning_source, winning_priority,
                     suggested_target_dollar, suppressed_reason, in_my_list
              FROM drv_actionable
              WHERE symbol = :sym
              ORDER BY as_of_date DESC
              LIMIT :lim
            """), {"sym": sym, "lim": limit_days}).mappings().all()
        except Exception:
            rec_hist = []

        # Snapshot symbol description / sector
        meta = s.execute(text("""
          SELECT DISTINCT ON (tos_symbol) tos_symbol, description, sector
          FROM drv_dash
          WHERE tos_symbol = :sym
          ORDER BY tos_symbol, as_of_date DESC
        """), {"sym": sym}).mappings().first()

    return {
        "tos_symbol":  sym,
        "description": (dict(meta).get("description") if meta else None),
        "sector":      (dict(meta).get("sector")      if meta else None),
        "timeseries":  [dict(r) for r in ts][::-1],
        "legs":        [dict(r) for r in legs],
        "user_actions": [dict(r) for r in actions],
        "recommendation_history": [dict(r) for r in rec_hist],
    }


@router.get("/api/portfolio/{symbol}/detail")
def get_portfolio_detail(symbol: str, date: Optional[str] = Query(None)):
    """Enhanced portfolio detail view with daily changes, account breakdown, and key metrics."""
    d = _resolve_date(date)
    sym = symbol.upper().strip()

    with session_scope() as s:
        # Get latest prices and descriptions
        latest_f = s.execute(text("""
            SELECT MAX(snapshot_date) FROM hist_f WHERE symbol = :sym AND snapshot_date <= :d
        """), {"sym": sym, "d": d}).scalar()

        latest_cs = s.execute(text("""
            SELECT MAX(snapshot_date) FROM hist_cs WHERE symbol = :sym AND snapshot_date <= :d
        """), {"sym": sym, "d": d}).scalar()

        if not latest_f and not latest_cs:
            raise HTTPException(status_code=404, detail=f"No data for {sym}")

        # Get absolute latest snapshots (for any symbol, to check current position)
        abs_latest_f = s.execute(text("SELECT MAX(snapshot_date) FROM hist_f")).scalar()
        abs_latest_cs = s.execute(text("SELECT MAX(snapshot_date) FROM hist_cs")).scalar()

        # 2-year timeseries anchored to latest available data for this symbol
        anchor = max(x for x in [latest_f, latest_cs] if x is not None)
        cutoff = anchor - timedelta(days=730)
        ts_sql = """
            SELECT snapshot_date, SUM(qty) as qty, SUM(mv) as market_value,
                   SUM(tg) as total_gain_dollar
            FROM (
                SELECT snapshot_date, qty, current_value as mv, total_gl_dollar as tg
                FROM hist_f WHERE symbol = :sym AND snapshot_date <= :anchor
                UNION ALL
                SELECT snapshot_date, qty, market_value as mv, gain_dollar as tg
                FROM hist_cs WHERE symbol = :sym AND snapshot_date <= :anchor
            ) t
            WHERE snapshot_date >= :cutoff
            GROUP BY snapshot_date ORDER BY snapshot_date
        """
        ts = s.execute(text(ts_sql), {"sym": sym, "anchor": anchor, "cutoff": cutoff}).fetchall()

        # Add daily changes via post-processing
        ts_with_changes = []
        for i, row in enumerate(ts):
            daily_change = 0.0
            if i > 0:
                prev_mv = ts[i-1][2]
                curr_mv = row[2]
                if prev_mv:
                    daily_change = round(float(curr_mv or 0) - float(prev_mv), 2)
            ts_with_changes.append({
                "date": row[0].isoformat() if row[0] else "",
                "qty": float(row[1]) if row[1] else 0,
                "market_value": float(row[2]) if row[2] else 0,
                "total_gain": float(row[3]) if row[3] else 0,
                "daily_change": daily_change
            })

        # Get account breakdown from absolute latest snapshots
        accounts_sql = """
            SELECT account, SUM(mv) as total_value, SUM(qty) as total_qty
            FROM (
                SELECT account_number as account, current_value as mv, qty FROM hist_f
                WHERE symbol = :sym AND snapshot_date = :abs_latest_f
                UNION ALL
                SELECT account, market_value as mv, qty FROM hist_cs
                WHERE symbol = :sym AND snapshot_date = :abs_latest_cs
            ) t
            GROUP BY account ORDER BY total_value DESC
        """
        accounts = s.execute(text(accounts_sql), {"sym": sym, "abs_latest_f": abs_latest_f, "abs_latest_cs": abs_latest_cs}).fetchall()

        # Check if symbol was sold (marked by sold_date when it disappeared from latest snapshot)
        f_sold_date = s.execute(text("""
            SELECT MAX(sold_date) FROM hist_f
            WHERE symbol = :sym
        """), {"sym": sym}).scalar()

        cs_sold_date = s.execute(text("""
            SELECT MAX(sold_date) FROM hist_cs
            WHERE symbol = :sym
        """), {"sym": sym}).scalar()

        is_sold = f_sold_date is not None or cs_sold_date is not None

        # Get current position from absolute latest snapshots (not latest for this symbol)
        # If symbol is missing from latest snapshot, qty = 0 (it was sold)
        current_sql = """
            SELECT COALESCE(f.desc, c.desc)               AS description,
                   COALESCE(f.qty,  0) + COALESCE(c.qty,  0) AS qty,
                   COALESCE(f.mv,   0) + COALESCE(c.mv,   0) AS market_value,
                   COALESCE(f.gain, 0) + COALESCE(c.gain, 0) AS total_gain,
                   COALESCE(f.gain_pct, 0)                AS gain_pct,
                   COALESCE(f.price, c.price)              AS last_price
            FROM (
                SELECT MAX(description) AS desc, SUM(qty) AS qty,
                       SUM(current_value) AS mv, SUM(total_gl_dollar) AS gain,
                       AVG(total_gl_pct) AS gain_pct, MAX(last_price) AS price
                FROM hist_f WHERE symbol = :sym AND snapshot_date = :abs_latest_f
            ) f
            FULL OUTER JOIN (
                SELECT MAX(description) AS desc, SUM(qty) AS qty,
                       SUM(market_value) AS mv, SUM(gain_dollar) AS gain,
                       AVG(gain_pct) AS gain_pct, MAX(price) AS price
                FROM hist_cs WHERE symbol = :sym AND snapshot_date = :abs_latest_cs
            ) c ON TRUE
        """
        current = s.execute(text(current_sql), {"sym": sym, "abs_latest_f": abs_latest_f, "abs_latest_cs": abs_latest_cs}).first()

        if not current:
            raise HTTPException(status_code=404, detail=f"Could not load details for {sym}")

        # Get realized gains from sales
        f_realized = s.execute(text("""
            SELECT COALESCE(SUM(realized_gain_dollar), 0) FROM hist_f
            WHERE symbol = :sym AND realized_gain_dollar IS NOT NULL
        """), {"sym": sym}).scalar() or 0.0

        cs_realized = s.execute(text("""
            SELECT COALESCE(SUM(realized_gain_dollar), 0) FROM hist_cs
            WHERE symbol = :sym AND realized_gain_dollar IS NOT NULL
        """), {"sym": sym}).scalar() or 0.0

        realized_gains = float(f_realized) + float(cs_realized)

        # Calculate YTD and MTD realized gains (from sales)
        ytd_start = d.replace(month=1, day=1)
        mtd_start = d.replace(day=1)

        # Sum realized gains from sales in YTD
        ytd_f_realized = s.execute(text("""
            SELECT COALESCE(SUM(realized_gain_dollar), 0) FROM hist_f
            WHERE symbol = :sym AND sold_date >= :ytd_start AND sold_date <= :d
        """), {"sym": sym, "ytd_start": ytd_start, "d": d}).scalar() or 0.0

        ytd_cs_realized = s.execute(text("""
            SELECT COALESCE(SUM(realized_gain_dollar), 0) FROM hist_cs
            WHERE symbol = :sym AND sold_date >= :ytd_start AND sold_date <= :d
        """), {"sym": sym, "ytd_start": ytd_start, "d": d}).scalar() or 0.0

        ytd_dollar = float(ytd_f_realized) + float(ytd_cs_realized)

        # Sum realized gains from sales in MTD
        mtd_f_realized = s.execute(text("""
            SELECT COALESCE(SUM(realized_gain_dollar), 0) FROM hist_f
            WHERE symbol = :sym AND sold_date >= :mtd_start AND sold_date <= :d
        """), {"sym": sym, "mtd_start": mtd_start, "d": d}).scalar() or 0.0

        mtd_cs_realized = s.execute(text("""
            SELECT COALESCE(SUM(realized_gain_dollar), 0) FROM hist_cs
            WHERE symbol = :sym AND sold_date >= :mtd_start AND sold_date <= :d
        """), {"sym": sym, "mtd_start": mtd_start, "d": d}).scalar() or 0.0

        mtd_dollar = float(mtd_f_realized) + float(mtd_cs_realized)

        ytd_pct = 0.0
        mtd_pct = 0.0
        if current[2] and current[2] > 0:
            ytd_pct = (ytd_dollar / float(current[2])) * 100 if current[2] else 0.0
            mtd_pct = (mtd_dollar / float(current[2])) * 100 if current[2] else 0.0

        return {
            "tos_symbol": sym,
            "as_of_date": d.isoformat(),
            "accounts": [
                {
                    "name": row[0] or "Unknown",
                    "total_value": float(row[1]) if row[1] else 0,
                    "total_qty": float(row[2]) if row[2] else 0
                }
                for row in accounts
            ],
            "current": {
                "description": current[0] or "Position",
                "qty": float(current[1]) if current[1] else 0,
                "market_value": float(current[2]) if current[2] else 0,
                "total_gain_dollar": float(current[3]) if current[3] else 0,
                "avg_gain_pct": float(current[4]) if current[4] else 0,
                "last_price": float(current[5]) if current[5] else 0
            },
            "periods": {
                "ytd_dollar": float(ytd_dollar),
                "ytd_pct": float(ytd_pct),
                "mtd_dollar": float(mtd_dollar),
                "mtd_pct": float(mtd_pct)
            },
            "is_sold": is_sold,
            "realized_gains_total": float(realized_gains)
        }


@router.get("/api/symbol/{sym}/history", response_model=list[SymbolHistoryRow])
def get_symbol_history(
    sym: str,
    from_date: Optional[str] = Query(None, alias="from"),
    to_date:   Optional[str] = Query(None, alias="to"),
):
    """Return per-snapshot history for a single symbol, ordered newest first.

    Pulls from drv_ma. Optional from/to dates filter the range.
    """
    from datetime import date as _date

    def _parse(s_):
        if not s_:
            return None
        try:
            return _date.fromisoformat(s_)
        except Exception:
            return None

    d_from = _parse(from_date)
    d_to   = _parse(to_date)

    params: dict = {"sym": (sym or "").upper()}
    where = ["symbol = :sym"]
    if d_from:
        where.append("as_of_date >= :d_from"); params["d_from"] = d_from
    if d_to:
        where.append("as_of_date <= :d_to");   params["d_to"]   = d_to
    where_sql = " AND ".join(where)

    with session_scope() as s:
        rows = s.execute(text(f"""
            SELECT as_of_date,
                   last_price,
                   rr_brr,
                   pct_brr,
                   rr_outlook,
                   sector
              FROM drv_ma
             WHERE {where_sql}
             ORDER BY as_of_date DESC
        """), params).mappings().all()

    return [SymbolHistoryRow(**r) for r in rows]
