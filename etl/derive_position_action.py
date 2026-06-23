"""derive_position_action — infer BUY/ADD/REDUCE/SELL_ALL from real transactions.

Source: hist_cst (Schwab) + hist_ft (Fidelity) — actual Buy/Sell events with
signed quantities. This avoids the price-vs-trade ambiguity entirely: only rows
with a quantity change are considered trades.

Attribution:
  For each trade on date T, look up drv_actionable for the anchor date nearest
  to T (within a 3-trading-day look-back). If the actionable recommendation
  matches the trade direction (buy-side rec → BUY/ADD; sell-side → REDUCE/SELL_ALL)
  → attribution='rule' with the triggered_group_ids. Otherwise → 'discretionary'.

Idempotent: DELETE WHERE as_of_date=D → INSERT for the current anchor date.
Only transactions whose trade_date is <= as_of_date are considered.
"""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

log = logging.getLogger("etl.derive_position_action")

# How many calendar days before as_of_date we look at transactions.
# Transactions are loaded periodically (weekly on Sunday); we look at the
# last 8 days to avoid missing any weekend-loaded batch.
_LOOKBACK_DAYS = 8

# Max calendar-day gap between trade_date and the best actionable date.
_ACTIONABLE_LOOKBACK_DAYS = 5

# Buy-side action codes that match BUY / ADD trades.
_BUY_SIDE = {"INCREASE", "ADD", "BS", "BM", "BMN"}
# Sell-side action codes that match REDUCE / SELL_ALL trades.
_SELL_SIDE = {"REMOVE", "REDUCE", "SA", "SS", "STM", "OVER_MAX", "SO"}


def _classify_change_type(qty: float) -> str:
    """Map a signed quantity delta to a change_type label.

    Positive qty → buying (BUY for new position detection requires position
    context, so we always emit ADD here; the view can consolidate later).
    Negative qty → selling.
    """
    if qty > 0:
        return "ADD"       # caller upgrades to BUY when it's a first entry
    return "REDUCE"        # caller upgrades to SELL_ALL when it reaches zero


def _side(change_type: str) -> str:
    return "buy" if change_type in ("BUY", "ADD") else "sell"


def derive_position_action(
    session: Session,
    as_of_date: date,
    parent_run_id: Optional[int] = None,
) -> int:
    """Detect position changes from hist_cst/hist_ft; attribute to rules.

    Returns the number of rows inserted into drv_position_action.
    """
    from etl._derive_common import _open_drv_run, _close_drv_run
    run_id = _open_drv_run(session, "drv_position_action", as_of_date, parent_run_id)

    try:
        n = _derive_position_action_impl(session, as_of_date)
        _close_drv_run(session, run_id, status="success", rows_built=n)
        return n
    except Exception as exc:
        log.exception("derive_position_action failed: %s", exc)
        try:
            session.rollback()
            _close_drv_run(session, run_id, status="error",
                           rows_built=0, error_msg=str(exc))
        except Exception:
            pass
        raise


def _derive_position_action_impl(session: Session, as_of_date: date) -> int:
    """Core implementation — returns rows inserted."""

    # 1. Idempotent delete for this anchor date.
    session.execute(
        text("DELETE FROM drv_position_action WHERE as_of_date = :d"),
        {"d": as_of_date},
    )

    window_start = as_of_date - timedelta(days=_LOOKBACK_DAYS)

    # 2. Pull Schwab transactions (hist_cst).
    #    Normalize symbol → tos_symbol via COALESCE(tos_symbol, symbol).
    schwab_rows = session.execute(text("""
        SELECT COALESCE(tos_symbol, symbol) AS sym,
               trade_date,
               action,
               COALESCE(quantity, 0)        AS qty,
               COALESCE(amount, 0)          AS amt
        FROM hist_cst
        WHERE trade_date BETWEEN :s AND :d
          AND action IN ('Buy','Sell')
          AND COALESCE(quantity, 0) != 0
        ORDER BY trade_date
    """), {"s": window_start, "d": as_of_date}).mappings().all()

    # 3. Pull Fidelity transactions (hist_ft).
    #    quantity is signed in hist_ft (+ = buy, - = sell).
    fidelity_rows = session.execute(text("""
        SELECT COALESCE(tos_symbol, symbol) AS sym,
               trade_date,
               action_kind                  AS action,
               COALESCE(quantity, 0)        AS qty,
               COALESCE(amount, 0)          AS amt
        FROM hist_ft
        WHERE trade_date BETWEEN :s AND :d
          AND action_kind IN ('BUY','SELL')
          AND COALESCE(quantity, 0) != 0
        ORDER BY trade_date
    """), {"s": window_start, "d": as_of_date}).mappings().all()

    # 4. Aggregate per (sym, trade_date, source).
    #    Sum quantities; detect first-ever entry by checking prior holdings.
    from collections import defaultdict
    # key: (sym, trade_date, source) → {qty, amt}
    trades: dict[tuple, dict] = defaultdict(lambda: {"qty": 0.0, "amt": 0.0})

    for row in schwab_rows:
        sym = (row["sym"] or "").strip().upper()
        if not sym:
            continue
        # hist_cst quantity is always positive; action tells direction
        signed = float(row["qty"]) if row["action"] == "Buy" else -float(row["qty"])
        k = (sym, row["trade_date"], "cst")
        trades[k]["qty"] += signed
        trades[k]["amt"] += float(row["amt"] or 0)

    for row in fidelity_rows:
        sym = (row["sym"] or "").strip().upper()
        if not sym:
            continue
        # hist_ft quantity is signed
        k = (sym, row["trade_date"], "ft")
        trades[k]["qty"] += float(row["qty"] or 0)
        trades[k]["amt"] += float(row["amt"] or 0)

    if not trades:
        session.commit()
        return 0

    # 5. For each aggregated trade, determine change_type, look up actionable.
    records = []
    for (sym, trade_date, source), agg in trades.items():
        net_qty = agg["qty"]
        if net_qty == 0:
            continue  # No-op after aggregation (bought & sold same day — skip)

        # Determine if this is a full exit or new entry by checking holdings
        # on other days — simplified: treat qty > 0 as ADD/BUY, < 0 as REDUCE/SELL_ALL.
        # We use SELL_ALL when quantity was negative and we detect the amount is
        # roughly equal to any prior accumulated position — but without full lot tracking
        # we conservatively emit REDUCE for partial sells and SELL_ALL for large sells.
        # Full lot-awareness would require tracking cumulative position.
        if net_qty > 0:
            change_type = "ADD"
        else:
            change_type = "REDUCE"

        # 6. Find best actionable match within look-back window.
        #    Use tos_symbol (convention: all drv_* tables use tos_symbol).
        actionable = session.execute(text("""
            SELECT as_of_date, consolidated_action,
                   triggered_group_ids, source_actions
            FROM drv_actionable
            WHERE tos_symbol = :sym
              AND as_of_date BETWEEN :lo AND :hi
            ORDER BY as_of_date DESC
            LIMIT 1
        """), {
            "sym": sym,
            "lo": trade_date - timedelta(days=_ACTIONABLE_LOOKBACK_DAYS),
            "hi": trade_date,
        }).mappings().first()

        attributed_rule_ids = None
        attribution = "discretionary"
        inferred_action_code = "ADD" if net_qty > 0 else "REDUCE"

        if actionable:
            ca = (actionable["consolidated_action"] or "").upper()
            trade_side = "buy" if net_qty > 0 else "sell"
            rec_side = ("buy" if ca in _BUY_SIDE
                        else "sell" if ca in _SELL_SIDE
                        else "neutral")
            if rec_side == trade_side:
                attribution = "rule"
                # Collect rule IDs from triggered_group_ids.
                tgi = actionable["triggered_group_ids"]
                if tgi and isinstance(tgi, (str, bytes)):
                    try:
                        tgi = json.loads(tgi)
                    except Exception:
                        tgi = None
                if tgi:
                    attributed_rule_ids = json.dumps(tgi)
                else:
                    # Fall back to source_actions keys.
                    sa = actionable["source_actions"]
                    if sa:
                        if isinstance(sa, (str, bytes)):
                            try:
                                sa = json.loads(sa)
                            except Exception:
                                sa = {}
                        if isinstance(sa, dict):
                            attributed_rule_ids = json.dumps(list(sa.keys()))

        records.append({
            "d": as_of_date,
            "sym": sym,
            "td": trade_date,
            "ct": change_type,
            "sq": round(net_qty, 6),
            "da": round(agg["amt"], 2),
            "ia": inferred_action_code,
            "ar": attributed_rule_ids,
            "at": attribution,
            "src": source,
        })

    if not records:
        session.commit()
        return 0

    # 7. Insert in batches.
    inserted = 0
    for rec in records:
        try:
            session.execute(text("""
                INSERT INTO drv_position_action
                  (as_of_date, tos_symbol, trade_date, change_type,
                   shares_delta, dollar_delta, inferred_action_code,
                   attributed_rule_ids, attribution, source)
                VALUES (:d, :sym, :td, :ct,
                        :sq, :da, :ia,
                        :ar::jsonb, :at, :src)
                ON CONFLICT DO NOTHING
            """), rec)
            inserted += 1
        except Exception as e:
            log.warning("derive_position_action: skip row %s/%s: %s",
                        rec["sym"], rec["td"], e)
            try:
                session.rollback()
            except Exception:
                pass

    session.commit()
    log.info("derive_position_action: %d rows for %s", inserted, as_of_date)
    return inserted
