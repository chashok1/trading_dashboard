#!/usr/bin/env python3

from etl.db import session_scope
from sqlalchemy import text

with session_scope() as s:
    max_date = s.execute(text(
        "SELECT MAX(snapshot_date) FROM hist_f"
    )).scalar()

    all_rows = s.execute(text("""
        SELECT account_number, account_name, symbol, type, current_value,
               today_gl_dollar, total_gl_dollar, cost_basis_total
        FROM hist_f
        WHERE snapshot_date = :d
        ORDER BY account_number, symbol
    """), {"d": max_date}).mappings().all()

    print(f"All Fidelity rows for {max_date}: {len(all_rows)}")
    for r in all_rows:
        print(f"  {r['account_number']:10} | {r['account_name']:30} | {r['symbol']:15} | Type: {r['type']:10} | Value: {r['current_value']:>10}")

    # Now test the actual query that's in the API
    print("\n\nQuerying with type <> 'Cash' filter:")
    filtered = s.execute(text("""
        SELECT 'F' AS source,
               COALESCE(account_name, account_number) AS account,
               SUM(current_value)    AS market_value,
               SUM(today_gl_dollar)  AS today_gain_dollar,
               SUM(total_gl_dollar)  AS total_gain_dollar,
               SUM(cost_basis_total) AS cost_basis,
               COUNT(DISTINCT symbol) AS positions
        FROM hist_f
        WHERE TRUE
          AND snapshot_date = :d
          AND type <> 'Cash'
        GROUP BY COALESCE(account_name, account_number)
    """), {"d": max_date}).mappings().all()

    print(f"Filtered rows: {len(filtered)}")
    for r in filtered:
        print(f"  {r['account']:30} | Value: {r['market_value']:>10} | Positions: {r['positions']}")
