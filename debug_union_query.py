from sqlalchemy import text
from etl.db import session_scope
from datetime import date

with session_scope() as s:
    d = date(2026, 5, 15)

    # Check if HYG is in hist_cs on this date
    print("Check 1: Is HYG in hist_cs on 2026-05-15?")
    result = s.execute(text("""
        SELECT COUNT(*) FROM hist_cs c
        WHERE c.symbol = 'HYG'
        AND c.snapshot_date = (SELECT MAX(snapshot_date) FROM hist_cs WHERE snapshot_date <= :d)
    """), {"d": d}).scalar()
    print(f"  Count: {result}")

    # Check realized gains for HYG
    print("\nCheck 2: Realized gains for HYG:")
    result = s.execute(text("""
        SELECT realized_gain, as_of_date, symbol FROM drv_cs_realized_gain
        WHERE symbol = 'HYG'
        ORDER BY as_of_date DESC
    """)).fetchall()
    for row in result:
        print(f"  {row[1]} | {row[2]} | Realized: ${float(row[0]) if row[0] else 0:.2f}")

    # Check if HYG would be excluded by the NOT EXISTS clause
    print("\nCheck 3: Would HYG pass the NOT EXISTS filter?")
    result = s.execute(text("""
        SELECT rg.symbol, rg.realized_gain
        FROM drv_cs_realized_gain rg
        WHERE rg.as_of_date = (SELECT MAX(snapshot_date) FROM hist_cs WHERE snapshot_date <= :d)
          AND NOT EXISTS (
            SELECT 1 FROM hist_cs c
            WHERE c.account = rg.account
              AND c.symbol = rg.symbol
              AND c.snapshot_date = (SELECT MAX(snapshot_date) FROM hist_cs WHERE snapshot_date <= :d)
          )
    """), {"d": d}).fetchall()
    for row in result:
        print(f"  {row[0]} | Realized: ${float(row[1]) if row[1] else 0:.2f}")

    if not result:
        print("  No rows match the filter (HYG not included)")
