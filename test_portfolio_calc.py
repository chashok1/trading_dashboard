from sqlalchemy import text
from etl.db import session_scope
from datetime import date

with session_scope() as s:
    d = date(2026, 5, 15)

    # Simulate the portfolio endpoint query for CS (with UNION for sold positions)
    sql = text("""
      (
      -- Held positions with unrealized gain + any realized gain from sales on this date
      SELECT
        'CS'                                      AS source,
        c.account                                   AS account,
        c.account                                   AS account_id,
        c.symbol,
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
          AND rg.symbol = c.symbol
          AND rg.as_of_date = (SELECT MAX(snapshot_date) FROM hist_cs WHERE snapshot_date <= :d)
      WHERE TRUE
        AND c.snapshot_date = (SELECT MAX(snapshot_date) FROM hist_cs WHERE snapshot_date <= :d)
        AND c.account LIKE :acct_pattern
      )
      UNION ALL
      (
      -- Sold positions: realized gains for positions not in today's hist_cs
      SELECT
        'CS'                                      AS source,
        rg.account                                  AS account,
        rg.account                                  AS account_id,
        rg.symbol,
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
        AND rg.account LIKE :acct_pattern
        AND NOT EXISTS (
          SELECT 1 FROM hist_cs c
          WHERE c.account = rg.account
            AND c.symbol = rg.symbol
            AND c.snapshot_date = (SELECT MAX(snapshot_date) FROM hist_cs WHERE snapshot_date <= :d)
        )
      )
    """)

    rows = s.execute(sql, {"d": d, "acct_pattern": "%892%"}).fetchall()

    print(f"Portfolio positions for account 892 on {d}:")
    print(f"{'Symbol':<10} {'Today Gain $':<15}")
    print("-" * 25)

    total = 0.0
    for row in rows:
        symbol = row[3]
        today_gain = float(row[10]) if row[10] is not None else 0
        total += today_gain
        print(f"{symbol:<10} ${today_gain:>13.2f}")

    print("-" * 25)
    print(f"{'TOTAL':<10} ${total:>13.2f}")
    print(f"\nExpected: -$344.35")
    print(f"Difference: ${(-344.35) - total:.2f}")
