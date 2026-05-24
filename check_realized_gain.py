import psycopg
from config.settings import settings

with psycopg.connect(
    host=settings.pg_host, port=settings.pg_port, dbname=settings.pg_database,
    user=settings.pg_user, password=settings.pg_password,
) as conn:
    with conn.cursor() as cur:
        # Check realized gains
        cur.execute("""
            SELECT as_of_date, account, symbol, realized_gain, shares_sold, avg_cost_per_share, proceeds
            FROM drv_cs_realized_gain
            WHERE as_of_date = '2026-05-15'
            ORDER BY symbol
        """)
        print("Realized gains on 2026-05-15:")
        for row in cur.fetchall():
            realized = row[3] if row[3] is not None else 0
            shares = row[4] if row[4] is not None else 0
            avg_cost = row[5] if row[5] is not None else 0
            proceeds = row[6] if row[6] is not None else 0
            print(f"  {row[2]:10} | {row[0]} | {row[1]:25} | Realized: ${realized:10.2f} | Shares: {shares:6.2f} | Avg Cost: ${avg_cost:8.2f} | Proceeds: ${proceeds:10.2f}")

        # Check what the portfolio endpoint will see
        cur.execute("""
            SELECT account, symbol,
                   COALESCE(day_chng_dollar, 0) as unrealized,
                   snapshot_date
            FROM hist_cs
            WHERE account LIKE '%892%' AND snapshot_date = '2026-05-15'
            ORDER BY symbol
        """)
        print("\nPositions on 2026-05-15 (unrealized gain):")
        for row in cur.fetchall():
            print(f"  {row[1]:10} | Account: {row[0][:25]:25} | Unrealized: ${row[2]:10.2f}")

        # Calculate total daily gain
        cur.execute("""
            SELECT SUM(COALESCE(day_chng_dollar, 0) + COALESCE(rg.realized_gain, 0))
            FROM hist_cs c
            LEFT JOIN drv_cs_realized_gain rg
                 ON rg.account = c.account
                AND rg.symbol = c.symbol
                AND rg.as_of_date = c.snapshot_date
            WHERE c.account LIKE '%892%' AND c.snapshot_date = '2026-05-15'
        """)
        total = cur.fetchone()[0] or 0
        print(f"\nTotal daily gain (unrealized + realized) for account 892 on 2026-05-15: ${total:.2f}")
        print(f"Expected: -$344.35")
