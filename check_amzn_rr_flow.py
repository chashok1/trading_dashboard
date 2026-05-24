#!/usr/bin/env python3
"""Trace one symbol's Risk Range (RR) data from hist_rr through every derived
table. Read-only diagnostic — no writes.

Run from the project root:

    python check_amzn_rr_flow.py            # defaults to AMZN
    python check_amzn_rr_flow.py TSLA       # any other symbol

Stages printed:
  1. hist_rr            - raw RR rows for the symbol (load cadence + gaps)
  2. hist_rr cadence    - distinct RR snapshot dates (all symbols) to show
                          the weekday load pattern and weekend/holiday gaps
  3. drv_outlook_action - the per-source RR action (where a bad REMOVE lives)
  4. drv_ma             - the symbol's rr_* columns in the master aggregate
  5. drv_stks           - the symbol's RR + composite outlook
  6. drv_dash           - the symbol's dashboard rows
  7. drv_actionable     - the consolidated decision + source_actions JSONB
  8. DIAGNOSTIC         - for every RR REMOVE, whether hist_rr actually has the
                          symbol on/before that date (proves the exact-date bug)
"""
import sys

from etl.db import session_scope
from sqlalchemy import text

SYMBOL = (sys.argv[1].upper().strip() if len(sys.argv) > 1 else "AMZN")
LIMIT = 20  # most recent N rows per stage


def show(title, rows, headers):
    """Print rows as a simple aligned table."""
    print(f"\n{'=' * 80}\n{title}\n{'=' * 80}")
    if not rows:
        print("  (no rows)")
        return
    widths = [len(h) for h in headers]
    body = []
    for r in rows:
        cells = ["" if v is None else str(v) for v in r]
        body.append(cells)
        for i, c in enumerate(cells):
            if i < len(widths):
                widths[i] = max(widths[i], len(c))
    print("  " + " | ".join(h.ljust(widths[i]) for i, h in enumerate(headers)))
    print("  " + "-+-".join("-" * w for w in widths))
    for cells in body:
        print("  " + " | ".join(
            cells[i].ljust(widths[i]) for i in range(len(headers))))


def stage(title, sql, params, headers):
    """Run one SELECT and print it; never abort the whole run on error."""
    try:
        with session_scope() as s:
            rows = s.execute(text(sql), params).fetchall()
        show(title, rows, headers)
    except Exception as e:
        print(f"\n{title}\n  QUERY FAILED: {e}")


def main():
    print(f"\nRR data-flow trace for symbol: {SYMBOL}")

    # 1. hist_rr - raw RR rows for the symbol --------------------------------
    stage(
        f"1. hist_rr - raw Risk Range rows for {SYMBOL} (newest {LIMIT})",
        """
        SELECT snapshot_date, symbol, tos_symbol, outlook,
               buy_trade, sell_trade, last_price
        FROM hist_rr
        WHERE symbol = :sym OR tos_symbol = :sym
        ORDER BY snapshot_date DESC
        LIMIT :lim
        """,
        {"sym": SYMBOL, "lim": LIMIT},
        ["snapshot_date", "symbol", "tos_symbol", "outlook",
         "buy_trade", "sell_trade", "last_price"],
    )

    # 2. hist_rr load cadence (all symbols) ----------------------------------
    stage(
        f"2. hist_rr load cadence - distinct snapshot dates (newest {LIMIT})",
        """
        SELECT snapshot_date,
               to_char(snapshot_date, 'Dy') AS weekday,
               COUNT(*) AS rr_rows
        FROM hist_rr
        GROUP BY snapshot_date
        ORDER BY snapshot_date DESC
        LIMIT :lim
        """,
        {"lim": LIMIT},
        ["snapshot_date", "weekday", "rr_rows"],
    )

    # 3. drv_outlook_action - the RR source action --------------------------
    stage(
        f"3. drv_outlook_action - RR source rows for {SYMBOL} (newest {LIMIT})",
        """
        SELECT as_of_date, base_weight, prev_weight, prev_date,
               weight_delta, held_today, action, action_reason
        FROM drv_outlook_action
        WHERE symbol = :sym AND source_code = 'RR'
        ORDER BY as_of_date DESC
        LIMIT :lim
        """,
        {"sym": SYMBOL, "lim": LIMIT},
        ["as_of_date", "base_wt", "prev_wt", "prev_date",
         "delta", "held", "action", "action_reason"],
    )

    # 4. drv_ma - the rr_* columns in the master aggregate ------------------
    stage(
        f"4. drv_ma - {SYMBOL} rr_* columns (newest {LIMIT})",
        """
        SELECT as_of_date, rr_date, rr_outlook, rr_brr,
               rr_buy_trade, rr_sell_trade, last_price
        FROM drv_ma
        WHERE symbol = :sym
        ORDER BY as_of_date DESC
        LIMIT :lim
        """,
        {"sym": SYMBOL, "lim": LIMIT},
        ["as_of_date", "rr_date", "rr_outlook", "rr_brr",
         "rr_buy_trade", "rr_sell_trade", "last_price"],
    )

    # 5. drv_stks - RR + composite outlook ----------------------------------
    stage(
        f"5. drv_stks - {SYMBOL} RR + composite (newest {LIMIT})",
        """
        SELECT as_of_date, rr_outlook, rr_brr,
               composite_outlook, composite_label
        FROM drv_stks
        WHERE symbol = :sym
        ORDER BY as_of_date DESC
        LIMIT :lim
        """,
        {"sym": SYMBOL, "lim": LIMIT},
        ["as_of_date", "rr_outlook", "rr_brr",
         "composite_outlook", "composite_label"],
    )

    # 6. drv_dash - dashboard rows ------------------------------------------
    stage(
        f"6. drv_dash - {SYMBOL} dashboard rows (newest {LIMIT})",
        """
        SELECT as_of_date, section, rr_outlook, rr_brr, last_price
        FROM drv_dash
        WHERE symbol = :sym
        ORDER BY as_of_date DESC
        LIMIT :lim
        """,
        {"sym": SYMBOL, "lim": LIMIT},
        ["as_of_date", "section", "rr_outlook", "rr_brr", "last_price"],
    )

    # 7. drv_actionable - the consolidated decision -------------------------
    stage(
        f"7. drv_actionable - {SYMBOL} consolidated decision (newest {LIMIT})",
        """
        SELECT as_of_date, consolidated_action, winning_source,
               winning_priority, position_category, suppressed_reason
        FROM drv_actionable
        WHERE symbol = :sym
        ORDER BY as_of_date DESC
        LIMIT :lim
        """,
        {"sym": SYMBOL, "lim": LIMIT},
        ["as_of_date", "consolidated_action", "winning_source",
         "winning_priority", "position_category", "suppressed_reason"],
    )

    # 7b. drv_actionable.source_actions JSONB for the most recent row -------
    try:
        with session_scope() as s:
            row = s.execute(text("""
                SELECT as_of_date, source_actions
                FROM drv_actionable
                WHERE symbol = :sym
                ORDER BY as_of_date DESC
                LIMIT 1
            """), {"sym": SYMBOL}).first()
        print(f"\n{'=' * 80}\n7b. drv_actionable.source_actions JSONB "
              f"(most recent row)\n{'=' * 80}")
        if row:
            print(f"  as_of_date = {row[0]}")
            print(f"  source_actions = {row[1]}")
        else:
            print("  (no drv_actionable row)")
    except Exception as e:
        print(f"  source_actions query failed: {e}")

    # 8. DIAGNOSTIC - does hist_rr actually have the symbol near each REMOVE?
    stage(
        f"8. DIAGNOSTIC - every RR REMOVE for {SYMBOL} vs. real hist_rr data",
        """
        SELECT oa.as_of_date,
               to_char(oa.as_of_date, 'Dy') AS weekday,
               oa.action,
               EXISTS (
                   SELECT 1 FROM hist_rr h
                   WHERE (h.symbol = :sym OR h.tos_symbol = :sym)
                     AND h.snapshot_date = oa.as_of_date
               ) AS rr_row_on_exact_date,
               (SELECT MAX(h.snapshot_date) FROM hist_rr h
                 WHERE (h.symbol = :sym OR h.tos_symbol = :sym)
                   AND h.snapshot_date <= oa.as_of_date
               ) AS latest_rr_on_or_before,
               oa.action_reason
        FROM drv_outlook_action oa
        WHERE oa.symbol = :sym AND oa.source_code = 'RR'
          AND oa.action = 'REMOVE'
        ORDER BY oa.as_of_date DESC
        LIMIT :lim
        """,
        {"sym": SYMBOL, "lim": LIMIT},
        ["as_of_date", "weekday", "action", "rr_row_on_exact_date",
         "latest_rr_on_or_before", "action_reason"],
    )
    print()
    print("  Read stage 8 like this: if `rr_row_on_exact_date` is False but")
    print("  `latest_rr_on_or_before` is a real (recent) date, the REMOVE is")
    print("  spurious — hist_rr DOES have the symbol, just not dated to that")
    print("  exact calendar day (a weekend/holiday gap).")
    print()


if __name__ == "__main__":
    main()
