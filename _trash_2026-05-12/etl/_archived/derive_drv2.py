"""drv2_* table populators (Phase 1 of drv2 migration).

Reads from drv_* / hist_* sources (latest snapshot per (as_of_date, symbol))
and writes one row per (as_of_date, symbol) into the corresponding drv2_* table.

Wired into etl.derive.derive_all() AFTER all derive_<source>() steps and BEFORE
derive_ma() so drv2_* is fresh for any downstream consumer.

Each derive_drv2_<x>() is idempotent: it DELETEs all rows for the as_of_date
first, then inserts.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

log = logging.getLogger("etl.derive_drv2")


# -----------------------------------------------------------------------------
# Local _wrap (avoids circular import with etl.derive — same pattern as
# derive_v2.py).
# -----------------------------------------------------------------------------

def _open_drv_run(session: Session, target: str, as_of_date: date,
                  parent_run_id: Optional[int] = None) -> int:
    row = session.execute(text("""
        INSERT INTO meta_derived_run
          (as_of_date, target_table, status, parent_run_id)
        VALUES (:d, :t, 'running', :prid)
        RETURNING run_id
    """), {"d": as_of_date, "t": target, "prid": parent_run_id}).first()
    return row[0] if row else 0


def _close_drv_run(session: Session, run_id: int, *, rows_built: int = 0,
                   status: str = "success", error_msg: Optional[str] = None) -> None:
    if not run_id:
        return
    session.execute(text("""
        UPDATE meta_derived_run
        SET rows_built = :rb, status = :st, error_msg = :em
        WHERE run_id = :rid
    """), {"rb": rows_built, "st": status, "em": error_msg, "rid": run_id})


def _wrap(target: str, fn):
    def runner(session: Session, as_of_date: date, parent_run_id: Optional[int] = None):
        rid = _open_drv_run(session, target, as_of_date, parent_run_id)
        try:
            n = fn(session, as_of_date, rid)
            _close_drv_run(session, rid, rows_built=n)
            log.info("%s @ %s: %d rows", target, as_of_date, n)
            return n
        except Exception as e:
            _close_drv_run(session, rid, rows_built=0, status="error", error_msg=str(e)[:500])
            raise
    return runner


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def _replace(session: Session, table: str, as_of_date: date, sql: str, **params):
    """DELETE + INSERT pattern. SQL must be the INSERT _ SELECT body."""
    session.execute(
        text(f"DELETE FROM {table} WHERE as_of_date = :d"),
        {"d": as_of_date},
    )
    res = session.execute(text(sql), {"d": as_of_date, "rid": params.get("rid"), **params})
    return res.rowcount or 0


# -----------------------------------------------------------------------------
# drv2_tl / drv2_td / drv2_tw — latest sequence per (snapshot_date, symbol)
# -----------------------------------------------------------------------------

def _derive_drv2_tl_impl(s: Session, d: date, rid: int) -> int:
    return _replace(s, "drv2_tl", d, """
        INSERT INTO drv2_tl (
            as_of_date, symbol, sequence,
            last_price, net_chng, change_pct, open_price, high_price, low_price,
            volume, rsi, imp_volatility, vlm_projected,
            source_run_id
        )
        SELECT DISTINCT ON (h.snapshot_date, h.symbol)
            h.snapshot_date AS as_of_date, h.symbol, h.sequence,
            h.last_price, h.net_chng, h.change_pct, h.open_price, h.high_price, h.low_price,
            h.volume, h.rsi,
            COALESCE(d2.imp_volatility_clean, h.imp_volatility_raw),
            d2.vlm_projected,
            :rid
        FROM hist_tl h
        LEFT JOIN drv_tl d2
            ON d2.snapshot_date = h.snapshot_date
           AND d2.symbol = h.symbol
           AND d2.sequence = h.sequence
        WHERE h.snapshot_date = :d
        ORDER BY h.snapshot_date, h.symbol, h.sequence DESC
    """, rid=rid)


def _derive_drv2_td_impl(s: Session, d: date, rid: int) -> int:
    return _replace(s, "drv2_td", d, """
        INSERT INTO drv2_td (
            as_of_date, symbol, sequence,
            last_price, net_chng, change_pct, open_price, high_price, low_price,
            rsi, historical_vol, imp_volatility,
            a_trend_value, a_trade_value, a_bb_bottom, a_bb_top, a_bb_streak,
            a_bb_high_low, a_bb_high_low_days, a_iv_percentile, a_hv_percentile,
            a_bb_top_slope, a_bb_bot_slope,
            source_run_id
        )
        SELECT DISTINCT ON (h.snapshot_date, h.symbol)
            h.snapshot_date AS as_of_date, h.symbol, h.sequence,
            h.last_price, h.net_chng, h.change_pct, h.open_price, h.high_price, h.low_price,
            h.rsi, h.historical_vol, h.imp_volatility,
            h.a_trend_value, h.a_trade_value, h.a_bb_bottom, h.a_bb_top, h.a_bb_streak,
            h.a_bb_high_low, h.a_bb_high_low_days, h.a_iv_percentile, h.a_hv_percentile,
            h.a_bb_top_slope, h.a_bb_bot_slope,
            :rid
        FROM hist_td h
        WHERE h.snapshot_date = :d
        ORDER BY h.snapshot_date, h.symbol, h.sequence DESC
    """, rid=rid)


def _derive_drv2_tw_impl(s: Session, d: date, rid: int) -> int:
    return _replace(s, "drv2_tw", d, """
        INSERT INTO drv2_tw (
            as_of_date, symbol, sequence,
            last_price, change_pct, sector, beta, standard_dev, fcf_per_share,
            high_52, low_52, sma_20, sma_50, sma_200,
            a_macdays_streak, a_macd_brr1, a_macdh_d_brr1,
            volume, a_volume_spike, volume_avg_10d, volume_avg_3m, volume_rate_change,
            a_perf_2m, a_perf_2wk, a_perf_3d,
            a_3mn_high, a_3mn_low, a_3mn_high_low, a_3wk_high_low,
            a_earnings_days, market_cap_str,
            source_run_id
        )
        SELECT DISTINCT ON (h.snapshot_date, h.symbol)
            h.snapshot_date AS as_of_date, h.symbol, h.sequence,
            h.last_price, h.change_pct, h.sector, h.beta, h.standard_dev, h.fcf_per_share,
            h.high_52, h.low_52, h.sma_20, h.sma_50, h.sma_200,
            h.a_macdays_streak, h.a_macd_brr1, h.a_macdh_d_brr1,
            h.volume, h.a_volume_spike, h.volume_avg_10d, h.volume_avg_3m, h.volume_rate_change,
            h.a_perf_2m, h.a_perf_2wk, h.a_perf_3d,
            h.a_3mn_high, h.a_3mn_low, h.a_3mn_high_low, h.a_3wk_high_low,
            h.a_earnings_days, h.market_cap_str,
            :rid
        FROM hist_tw h
        WHERE h.snapshot_date = :d
        ORDER BY h.snapshot_date, h.symbol, h.sequence DESC
    """, rid=rid)


# -----------------------------------------------------------------------------
# drv2_call / drv2_etf / drv2_ii / drv2_ssh — latest snapshot <= as_of_date
# -----------------------------------------------------------------------------

def _derive_drv2_call_impl(s: Session, d: date, rid: int) -> int:
    return _replace(s, "drv2_call", d, """
        INSERT INTO drv2_call (as_of_date, symbol, outlook, outlook_modifier, source_run_id)
        SELECT :d, c.symbol, c.outlook, c.outlook_modifier, :rid
        FROM hist_call c
        WHERE c.snapshot_date = (
            SELECT MAX(snapshot_date) FROM hist_call
            WHERE snapshot_date <= :d AND symbol = c.symbol
        )
    """, rid=rid)


def _derive_drv2_etf_impl(s: Session, d: date, rid: int) -> int:
    return _replace(s, "drv2_etf", d, """
        INSERT INTO drv2_etf (as_of_date, symbol, sector, date_added, recent_price, brr, trr, asset_class, include_flag, source_run_id)
        SELECT :d, e.symbol, e.sector, e.date_added, e.recent_price, e.brr, e.trr, e.asset_class, e.include_flag, :rid
        FROM hist_etf e
        WHERE e.snapshot_date = (
            SELECT MAX(snapshot_date) FROM hist_etf
            WHERE snapshot_date <= :d AND symbol = e.symbol
        )
    """, rid=rid)


def _derive_drv2_etfchg_impl(s: Session, d: date, rid: int) -> int:
    return _replace(s, "drv2_etfchg", d, """
        INSERT INTO drv2_etfchg (as_of_date, symbol, event_date, action, chg, wt, outlook, description, source_run_id)
        SELECT :d, ec.symbol, ec.event_date, ec.action, ec.chg, ec.wt, ec.outlook, ec.description, :rid
        FROM hist_etfchg ec
        WHERE ec.event_date = (
            SELECT MAX(event_date) FROM hist_etfchg
            WHERE event_date <= :d AND symbol = ec.symbol
        )
    """, rid=rid)


def _derive_drv2_ii_impl(s: Session, d: date, rid: int) -> int:
    return _replace(s, "drv2_ii", d, """
        INSERT INTO drv2_ii (as_of_date, symbol, outlook, include_flag, source_run_id)
        SELECT :d, i.symbol, i.outlook, i.include_flag, :rid
        FROM hist_ii i
        WHERE i.snapshot_date = (
            SELECT MAX(snapshot_date) FROM hist_ii
            WHERE snapshot_date <= :d AND symbol = i.symbol
        )
    """, rid=rid)


def _derive_drv2_ssh_impl(s: Session, d: date, rid: int) -> int:
    return _replace(s, "drv2_ssh", d, """
        INSERT INTO drv2_ssh (as_of_date, symbol, days_on, signal_date, prior_close, last_close, pct_delta, sector, analyst, anlst_best_idea_rank, source_run_id)
        SELECT :d, h.symbol, h.days_on, h.signal_date, h.prior_close, h.last_close, h.pct_delta, h.sector, h.analyst, h.anlst_best_idea_rank, :rid
        FROM hist_ssh h
        WHERE h.snapshot_date = (
            SELECT MAX(snapshot_date) FROM hist_ssh
            WHERE snapshot_date <= :d AND symbol = h.symbol
        )
    """, rid=rid)


def _derive_drv2_rr_impl(s: Session, d: date, rid: int) -> int:
    return _replace(s, "drv2_rr", d, """
        INSERT INTO drv2_rr (as_of_date, symbol, last_price, buy_trade, sell_trade, weight, modifier, entry, cont, brr, name, outlook, source_run_id)
        SELECT :d, r.symbol, r.last_price, r.buy_trade, r.sell_trade, r.weight, r.modifier, r.entry, r.cont, r.brr, r.name, r.outlook, :rid
        FROM hist_rr r
        WHERE r.snapshot_date = (
            SELECT MAX(snapshot_date) FROM hist_rr
            WHERE snapshot_date <= :d AND symbol = r.symbol
        )
    """, rid=rid)


def _derive_drv2_ps_impl(s: Session, d: date, rid: int) -> int:
    return _replace(s, "drv2_ps", d, """
        INSERT INTO drv2_ps (as_of_date, symbol, rank, wk_ago, mn_ago, asset_class, minimum, maximum, source_run_id)
        SELECT :d, p.ticker AS symbol, p.rank, p.wk_ago, p.mn_ago, p.asset_class, p.minimum, p.maximum, :rid
        FROM hist_psrk p
        WHERE p.snapshot_date = (
            SELECT MAX(snapshot_date) FROM hist_psrk
            WHERE snapshot_date <= :d AND ticker = p.ticker
        )
    """, rid=rid)


# -----------------------------------------------------------------------------
# drv2_ssl / drv2_sss — wrap drv_ssl/drv_sss in a JSONB payload (defensive:
# drv_ssl/drv_sss schemas vary; row_to_json sidesteps schema drift).
# -----------------------------------------------------------------------------

def _derive_drv2_ssl_impl(s: Session, d: date, rid: int) -> int:
    return _replace(s, "drv2_ssl", d, """
        INSERT INTO drv2_ssl (as_of_date, symbol, payload, source_run_id)
        SELECT :d, x.symbol, to_jsonb(x), :rid
        FROM drv_ssl x
        WHERE x.as_of_date = :d
    """, rid=rid)


def _derive_drv2_sss_impl(s: Session, d: date, rid: int) -> int:
    return _replace(s, "drv2_sss", d, """
        INSERT INTO drv2_sss (as_of_date, symbol, payload, source_run_id)
        SELECT :d, x.symbol, to_jsonb(x), :rid
        FROM drv_sss x
        WHERE x.as_of_date = :d
    """, rid=rid)


# -----------------------------------------------------------------------------
# drv2_holdings — UNION SUM of hist_f + hist_cs per symbol on latest date <= :d
# -----------------------------------------------------------------------------

def _derive_drv2_holdings_impl(s: Session, d: date, rid: int) -> int:
    return _replace(s, "drv2_holdings", d, """
        INSERT INTO drv2_holdings (as_of_date, symbol, total_qty, total_value, qty_fid, qty_cs, source_run_id)
        WITH fid AS (
            SELECT symbol, SUM(qty) AS qty_fid, SUM(current_value) AS val_fid
            FROM hist_f
            WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM hist_f WHERE snapshot_date <= :d)
            GROUP BY symbol
        ),
        cs AS (
            SELECT symbol, SUM(qty) AS qty_cs, SUM(market_value) AS val_cs
            FROM hist_cs
            WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM hist_cs WHERE snapshot_date <= :d)
            GROUP BY symbol
        )
        SELECT :d,
               COALESCE(f.symbol, c.symbol) AS symbol,
               COALESCE(f.qty_fid, 0) + COALESCE(c.qty_cs, 0) AS total_qty,
               COALESCE(f.val_fid, 0) + COALESCE(c.val_cs, 0) AS total_value,
               COALESCE(f.qty_fid, 0),
               COALESCE(c.qty_cs, 0),
               :rid
        FROM fid f
        FULL OUTER JOIN cs c ON c.symbol = f.symbol
    """, rid=rid)


# -----------------------------------------------------------------------------
# Public derive_drv2_* (wrapped for run tracking)
# -----------------------------------------------------------------------------

derive_drv2_tl       = _wrap("drv2_tl",       _derive_drv2_tl_impl)
derive_drv2_td       = _wrap("drv2_td",       _derive_drv2_td_impl)
derive_drv2_tw       = _wrap("drv2_tw",       _derive_drv2_tw_impl)
derive_drv2_call     = _wrap("drv2_call",     _derive_drv2_call_impl)
derive_drv2_etf      = _wrap("drv2_etf",      _derive_drv2_etf_impl)
derive_drv2_etfchg   = _wrap("drv2_etfchg",   _derive_drv2_etfchg_impl)
derive_drv2_ii       = _wrap("drv2_ii",       _derive_drv2_ii_impl)
derive_drv2_ssh      = _wrap("drv2_ssh",      _derive_drv2_ssh_impl)
derive_drv2_rr       = _wrap("drv2_rr",       _derive_drv2_rr_impl)
derive_drv2_ps       = _wrap("drv2_ps",       _derive_drv2_ps_impl)
derive_drv2_ssl      = _wrap("drv2_ssl",      _derive_drv2_ssl_impl)
derive_drv2_sss      = _wrap("drv2_sss",      _derive_drv2_sss_impl)
derive_drv2_holdings = _wrap("drv2_holdings", _derive_drv2_holdings_impl)


def derive_all_drv2(session: Session, as_of_date: date,
                    parent_run_id: Optional[int] = None) -> dict:
    """Run every derive_drv2_*. Returns {table: rows_built}.

    Each step runs inside its own SAVEPOINT (begin_nested) so a failure rolls
    back only that step's writes; the outer transaction stays usable so the
    pipeline can continue to derive_ma() afterwards.
    """
    counts: dict = {}
    steps = [
        ("drv2_tl",       derive_drv2_tl),
        ("drv2_td",       derive_drv2_td),
        ("drv2_tw",       derive_drv2_tw),
        ("drv2_call",     derive_drv2_call),
        ("drv2_etf",      derive_drv2_etf),
        ("drv2_etfchg",   derive_drv2_etfchg),
        ("drv2_ii",       derive_drv2_ii),
        ("drv2_ssh",      derive_drv2_ssh),
        ("drv2_rr",       derive_drv2_rr),
        ("drv2_ps",       derive_drv2_ps),
        ("drv2_ssl",      derive_drv2_ssl),
        ("drv2_sss",      derive_drv2_sss),
        ("drv2_holdings", derive_drv2_holdings),
    ]
    for name, fn in steps:
        sp = session.begin_nested()
        try:
            counts[name] = fn(session, as_of_date, parent_run_id)
            sp.commit()
        except Exception as e:
            sp.rollback()
            log.warning("%s skipped: %s", name, e)
            counts[name] = 0
    return counts
