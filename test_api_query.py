#!/usr/bin/env python3

from etl.db import session_scope
from sqlalchemy import text
from datetime import date

d = date(2026, 5, 13)

with session_scope() as s:
    # This is the exact query from the API
    acct_rows = list(s.execute(text("""
        WITH u AS (
          SELECT 'F' AS source,
                 COALESCE(account_name, account_number) AS account,
                 SUM(current_value)    AS market_value,
                 SUM(today_gl_dollar)  AS today_gain_dollar,
                 SUM(total_gl_dollar)  AS total_gain_dollar,
                 SUM(cost_basis_total) AS cost_basis,
                 COUNT(DISTINCT symbol) AS positions
          FROM hist_f
          WHERE TRUE
            AND snapshot_date = (SELECT MAX(snapshot_date) FROM hist_f WHERE snapshot_date <= :d)
            AND type <> 'Cash'
          GROUP BY COALESCE(account_name, account_number)
          UNION ALL
          SELECT 'CS' AS source,
                 account,
                 SUM(market_value),
                 SUM(day_chng_dollar),
                 SUM(gain_dollar),
                 SUM(cost_basis),
                 COUNT(DISTINCT symbol)
          FROM hist_cs
          WHERE TRUE
            AND snapshot_date = (SELECT MAX(snapshot_date) FROM hist_cs WHERE snapshot_date <= :d)
            AND symbol <> 'Cash & Cash Investments'
          GROUP BY account
        )
        SELECT * FROM u ORDER BY source, account
    """), {"d": d}).mappings().all())

    print(f"Query returned {len(acct_rows)} rows:")
    for r in acct_rows:
        print(f"  {r['source']:3} | {r['account']:45} | MV=${r['market_value']:>10,.2f} | Pos={r['positions']}")
