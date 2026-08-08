"""
FIFO realized-gain derivation across CS + F transactions.

Why a separate module:
  - hist_cs and hist_f are SNAPSHOTS (not historic). The user may go a week
    or a month without downloading a snapshot.
  - The transactions tables (hist_cst, hist_ft) carry
    the real activity history.
  - To compute realized gain reliably we need to match each sell to the
    buy lots that produced it. That's FIFO.

Algorithm:
  For each (source, account, symbol):
    1. Pull all activity rows ordered by trade_date.
    2. Maintain an ordered queue of open buy lots:
         [(buy_date, remaining_shares, cost_per_share), ...]
       Each BUY pushes to the back. Each SELL pops from the front (FIFO).
    3. For each SELL, accumulate matched cost basis + holding-period weights;
       write one row to drv_realized_gain.

Edge cases we DO handle:
  - Multiple buys before a sell — sell consumes oldest first.
  - Partial sell — only the matched portion of the front lot is consumed.
  - Sell exceeds open shares — we still emit a row, with cost_basis = matched
    portion only (short-sale style) and a warning in `lots_consumed`.
  - Dividend reinvestments (action_kind='BUY' from REINVESTMENT) — treated
    like any other BUY.
  - Money-market sweeps / cash actions — skipped entirely (action_kind != BUY/SELL).
  - Source-specific commission/fees — proceeds is `amount` net of fees, since
    Fidelity already nets them into the Amount column.

Edge cases we DON'T handle yet:
  - Wash-sale adjustments (IRS §1091). The number we report is "gross" realized
    gain, not the tax-adjusted figure.
  - Stock splits / spin-offs / mergers. If you split AAPL 4:1, future SELLs
    will look like they came from "smaller" lots — the dollar math is still
    correct but `shares_sold` won't match the brokerage statement until you
    record the split as a corresponding BUY/SELL pair.
  - Cross-account transfers. A BUY in account X followed by a transfer to
    account Y and SELL there is invisible to this module — each account is
    its own FIFO universe.
"""
from __future__ import annotations

import json
import logging
from collections import deque
from datetime import date
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

log = logging.getLogger("etl.derive_realized")


# Sources we know about and how to read them.
# Each tuple: (source_code, table_name, account_column)
# F uses account_number (not account) as the FIFO grouping/output key:
# hist_ft.account is inconsistently populated for the same physical account
# across load batches (sometimes the raw account number, sometimes the
# account name like "Rollover IRA") — grouping by that string fragments one
# account's lot history into two, so SELLs can't find their matching BUY
# lots and fall back to cost_basis=0 (spurious ~100%-of-proceeds "gains").
# account_number is reliably populated for every hist_ft row.
_SOURCES = [
    ("CS", "hist_cst", "account"),
    ("F",  "hist_ft",  "account_number"),
]


def _fetch_events(session: Session, source: str, table: str,
                  account_col: str) -> list[dict]:
    """Pull all BUY/SELL events for one source, ordered chronologically.

    We intentionally read both tables even though their schemas differ —
    SELECT picks only the columns we need so the shapes line up.
    """
    # CS table has no `action_kind` column — we derive it inline from
    # `action` text. F has the column populated by the loader.
    if source == "CS":
        # CS Action values are short: "Buy" / "Sell" / "Dividend" / etc.
        kind_expr = (
            "CASE UPPER(action) "
            "WHEN 'BUY' THEN 'BUY' "
            "WHEN 'SELL' THEN 'SELL' "
            "WHEN 'REINVEST SHARES' THEN 'BUY' "
            "ELSE 'OTHER' END"
        )
        sql = f"""
            SELECT trade_date, {account_col} AS account, symbol,
                   quantity, price, COALESCE(amount, 0) AS amount,
                   COALESCE(fees, 0) AS fees,
                   {kind_expr} AS kind,
                   action AS raw_action,
                   source_file
            FROM {table}
            WHERE symbol IS NOT NULL AND symbol <> ''
              AND {kind_expr} IN ('BUY', 'SELL')
              AND {account_col} NOT IN (SELECT account_number FROM ref_accounts WHERE is_active = FALSE)
            ORDER BY {account_col}, symbol, trade_date, action
        """
    else:
        sql = f"""
            SELECT trade_date, {account_col} AS account, symbol,
                   quantity, price, COALESCE(amount, 0) AS amount,
                   COALESCE(fees, 0) AS fees,
                   action_kind AS kind,
                   action AS raw_action,
                   source_file
            FROM {table}
            WHERE symbol IS NOT NULL AND symbol <> ''
              AND action_kind IN ('BUY', 'SELL')
              AND {account_col} NOT IN (SELECT account_number FROM ref_accounts WHERE is_active = FALSE)
            ORDER BY {account_col}, symbol, trade_date, action
        """
    return [dict(r) for r in session.execute(text(sql)).mappings().all()]


def _process_symbol_events(events: list[dict]) -> list[dict]:
    """Walk one (account, symbol)'s events chronologically and FIFO-match
    sells against buy lots. Returns a list of sell-event records to insert.

    `events` is already filtered to BUY/SELL only and sorted by trade_date.
    All rows in `events` share the same account + symbol.
    """
    lots: deque[dict] = deque()       # open buy lots: oldest at front
    out: list[dict] = []

    for ev in events:
        qty = float(ev["quantity"] or 0)
        price = float(ev["price"] or 0)
        amount = float(ev["amount"] or 0)
        kind = (ev["kind"] or "OTHER").upper()

        if kind == "BUY":
            # Fidelity reports + quantity for buys; Schwab is the same.
            shares = abs(qty)
            if shares == 0:
                continue
            # Cost per share — prefer the Amount column if available
            # (it nets fees correctly), otherwise fall back to price.
            cost_total = abs(amount) if amount else (shares * price)
            cost_per_share = cost_total / shares if shares else 0
            lots.append({
                "buy_date":       ev["trade_date"],
                "shares":         shares,
                "cost_per_share": cost_per_share,
                "src_file":       ev.get("source_file"),
            })
            continue

        if kind == "SELL":
            shares_to_close = abs(qty)
            if shares_to_close == 0:
                continue
            # `amount` for Fidelity sells is positive (proceeds). For Schwab
            # it should also be positive. If negative, take abs.
            proceeds = abs(amount) if amount else (shares_to_close * price)
            consumed: list[dict] = []
            matched_shares = 0.0
            matched_cost = 0.0
            holding_days_weighted = 0.0
            now_date: date = ev["trade_date"]
            remaining = shares_to_close
            while remaining > 0 and lots:
                lot = lots[0]
                take = min(lot["shares"], remaining)
                consumed.append({
                    "buy_date":       lot["buy_date"].isoformat() if hasattr(lot["buy_date"], "isoformat") else str(lot["buy_date"]),
                    "shares":         round(take, 6),
                    "cost_per_share": round(lot["cost_per_share"], 6),
                    "src_file":       lot.get("src_file"),
                })
                matched_shares += take
                matched_cost   += take * lot["cost_per_share"]
                try:
                    days = (now_date - lot["buy_date"]).days
                except TypeError:
                    days = 0
                holding_days_weighted += take * max(days, 0)
                lot["shares"] -= take
                remaining     -= take
                if lot["shares"] <= 1e-9:
                    lots.popleft()
            warning = None
            if remaining > 1e-6:
                # Sold more than we ever bought — possible if data starts
                # mid-history (the user only downloaded last 6m).
                warning = (
                    f"Unmatched {round(remaining, 4)} sh — "
                    "buy history before transaction window not loaded"
                )
            realized = proceeds - matched_cost
            pct = (realized / matched_cost * 100.0) if matched_cost > 1e-9 else None
            avg_days = (holding_days_weighted / matched_shares) if matched_shares > 1e-9 else None
            long_term = avg_days is not None and avg_days > 365
            out.append({
                "source":            None,  # filled by caller
                "account":           ev["account"],
                "symbol":            ev["symbol"],
                "sell_date":         ev["trade_date"],
                "shares_sold":       round(shares_to_close, 6),
                "sell_proceeds":     round(proceeds, 2),
                "cost_basis":        round(matched_cost, 2),
                "realized_gain":     round(realized, 2),
                "realized_gain_pct": round(pct, 4) if pct is not None else None,
                "holding_days_avg":  round(avg_days, 2) if avg_days is not None else None,
                "is_long_term":      bool(long_term),
                "lots_consumed":     consumed + ([{"warning": warning}] if warning else []),
            })

    return out


def derive_realized_gain(session: Session) -> int:
    """Rebuild drv_realized_gain across all known transaction sources.

    Idempotent: TRUNCATEs drv_realized_gain then re-inserts. Because the FIFO
    matching is a stateful walk over all history, partial rebuilds aren't
    meaningful — we always recompute the whole table.

    Returns the number of sell-event rows written.
    """
    all_rows: list[dict] = []
    for source, table, account_col in _SOURCES:
        try:
            events = _fetch_events(session, source, table, account_col)
        except Exception as e:
            log.warning("source %s: read failed (%s); skipping", source, e)
            continue
        log.info("source %s: %d BUY/SELL events", source, len(events))

        # Group consecutive rows by (account, symbol). The SQL ORDER BY in
        # _fetch_events guarantees they're already adjacent, so we can scan.
        bucket: list[dict] = []
        last_key: Optional[tuple[str, str]] = None
        for ev in events:
            key = (ev["account"], ev["symbol"])
            if last_key is not None and key != last_key:
                rows = _process_symbol_events(bucket)
                for r in rows:
                    r["source"] = source
                all_rows.extend(rows)
                bucket = []
            bucket.append(ev)
            last_key = key
        if bucket:
            rows = _process_symbol_events(bucket)
            for r in rows:
                r["source"] = source
            all_rows.extend(rows)

    # Rebuild table
    session.execute(text("TRUNCATE TABLE drv_realized_gain"))
    if not all_rows:
        session.commit()
        return 0
    session.execute(text("""
        INSERT INTO drv_realized_gain
          (source, account, tos_symbol, sell_date, shares_sold,
           sell_proceeds, cost_basis, realized_gain, realized_gain_pct,
           holding_days_avg, is_long_term, lots_consumed)
        VALUES
          (:source, :account, :symbol, :sell_date, :shares_sold,
           :sell_proceeds, :cost_basis, :realized_gain, :realized_gain_pct,
           :holding_days_avg, :is_long_term, CAST(:lots_consumed AS JSONB))
        ON CONFLICT (source, account, tos_symbol, sell_date, shares_sold) DO UPDATE SET
           sell_proceeds     = EXCLUDED.sell_proceeds,
           cost_basis        = EXCLUDED.cost_basis,
           realized_gain     = EXCLUDED.realized_gain,
           realized_gain_pct = EXCLUDED.realized_gain_pct,
           holding_days_avg  = EXCLUDED.holding_days_avg,
           is_long_term      = EXCLUDED.is_long_term,
           lots_consumed     = EXCLUDED.lots_consumed,
           computed_at       = now()
    """), [
        {**r, "lots_consumed": json.dumps(r["lots_consumed"], default=str)}
        for r in all_rows
    ])
    session.commit()
    return len(all_rows)


if __name__ == "__main__":
    from etl.db import session_scope
    from etl._logging import setup_logging
    setup_logging()
    with session_scope() as s:
        n = derive_realized_gain(s)
        print(f"drv_realized_gain rebuilt: {n} sell-event rows")
