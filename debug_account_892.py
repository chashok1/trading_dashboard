"""Debug account 892 today's gain calculation."""
import psycopg
from config.settings import settings
from datetime import datetime

with psycopg.connect(
    host=settings.pg_host,
    port=settings.pg_port,
    dbname=settings.pg_database,
    user=settings.pg_user,
    password=settings.pg_password,
) as conn:
    with conn.cursor() as cur:
        # Find account ending with 892 in hist_cs
        cur.execute("""
            SELECT DISTINCT account FROM hist_cs
            WHERE account LIKE '%892'
            LIMIT 1
        """)
        acct = cur.fetchone()
        if not acct:
            print("Account ending with 892 not found in hist_cs")
            exit(1)

        account = acct[0]
        print(f"Account: {account}\n")

        # Get latest date
        cur.execute("SELECT MAX(snapshot_date) FROM drv_ma WHERE account = %s", (account,))
        latest_date = cur.fetchone()[0]
        print(f"Latest date: {latest_date}\n")

        # Check CS raw data for this account on latest date
        print("=== Schwab (CS) Raw Data ===")
        cur.execute("""
            SELECT symbol, qty, last_price, last_price_change, market_value, cost_basis
            FROM hist_cs
            WHERE account = %s AND snapshot_date = %s
            ORDER BY symbol
        """, (account, latest_date))

        total_gain = 0
        rows = cur.fetchall()
        for symbol, qty, last_price, last_price_change, mv, cb in rows:
            qty = float(qty) if qty else 0
            lp = float(last_price) if last_price else 0
            lpc = float(last_price_change) if last_price_change else 0
            mv = float(mv) if mv else 0
            cb = float(cb) if cb else 0

            daily_gain = qty * lpc if qty and lpc else 0
            total_gain += daily_gain

            print(f"{symbol:6} | Qty: {qty:8.2f} | Price: {lp:8.2f} | Chg: {lpc:7.3f} | Daily: {daily_gain:8.2f} | MV: {mv:10.2f}")

        print(f"\nCalculated today's gain from CS raw: ${total_gain:.2f}")

        # Check hist_cs to see all columns
        print("\n=== hist_cs table structure ===")
        cur.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'hist_cs'
            ORDER BY ordinal_position
        """)
        for col, dtype in cur.fetchall():
            print(f"  {col}: {dtype}")

        # Get account info
        print(f"\n=== Checking account: {account} on {latest_date} ===")
        cur.execute("""
            SELECT COUNT(*), SUM(market_value), SUM(COALESCE(market_value - cost_basis, 0))
            FROM hist_cs
            WHERE account = %s AND snapshot_date = %s
        """, (account, latest_date))

        count, total_mv, total_gain = cur.fetchone()
        print(f"Positions: {count}")
        print(f"Total market value: ${total_mv if total_mv else 0:.2f}")
        print(f"Total gain (MV - CB): ${total_gain if total_gain else 0:.2f}")
