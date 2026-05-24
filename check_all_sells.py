import psycopg
from config.settings import settings

with psycopg.connect(
    host=settings.pg_host, port=settings.pg_port, dbname=settings.pg_database,
    user=settings.pg_user, password=settings.pg_password,
) as conn:
    with conn.cursor() as cur:
        # Check all sells
        print("All sells in transaction file:")
        cur.execute("""
            SELECT trade_date, action, symbol, quantity, price, amount
            FROM hist_cst
            WHERE LOWER(action) = 'sell'
            ORDER BY trade_date DESC
        """)
        for row in cur.fetchall():
            print(f"  {row[0]} | {row[1]:4} | {row[2]:10} | Qty: {row[3]:6.0f} | Price: ${row[4]:8.2f} | Amount: ${row[5]:10.2f}")

        # Check all realized gains
        print("\nAll realized gains:")
        cur.execute("""
            SELECT as_of_date, account, symbol, realized_gain, shares_sold, avg_cost_per_share, proceeds
            FROM drv_cs_realized_gain
            ORDER BY as_of_date DESC, symbol
        """)
        total_realized = 0.0
        for row in cur.fetchall():
            realized = float(row[3]) if row[3] is not None else 0
            total_realized += realized
            print(f"  {row[0]} | {row[2]:10} | Realized: ${realized:10.2f}")
        print(f"\nTotal realized gain from all sales: ${total_realized:.2f}")

        # Now check the daily gain calculation for 05/15
        print("\n\nDaily gain breakdown for 2026-05-15:")
        cur.execute("""
            SELECT SUM(COALESCE(day_chng_dollar, 0)) as unrealized
            FROM hist_cs
            WHERE account LIKE '%892%' AND snapshot_date = '2026-05-15'
        """)
        unrealized = float(cur.fetchone()[0] or 0)
        print(f"  Unrealized from positions: ${unrealized:.2f}")

        cur.execute("""
            SELECT SUM(COALESCE(realized_gain, 0))
            FROM drv_cs_realized_gain
            WHERE account LIKE '%892%' AND as_of_date = '2026-05-15'
        """)
        realized_on_15 = float(cur.fetchone()[0] or 0)
        print(f"  Realized on 2026-05-15: ${realized_on_15:.2f}")

        total = unrealized + realized_on_15
        print(f"  Total: ${total:.2f}")
        print(f"  Expected: -$344.35")
        print(f"  Difference: ${(-344.35) - total:.2f}")
