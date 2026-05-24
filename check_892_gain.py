"""Calculate today's gain for account 892 from Schwab data."""
import psycopg
from config.settings import settings

with psycopg.connect(
    host=settings.pg_host,
    port=settings.pg_port,
    dbname=settings.pg_database,
    user=settings.pg_user,
    password=settings.pg_password,
) as conn:
    with conn.cursor() as cur:
        # Get account 892
        cur.execute("""
            SELECT DISTINCT account FROM hist_cs
            WHERE account LIKE '%892'
        """)
        account = cur.fetchone()[0]
        print(f"Account: {account}\n")

        # Get latest date
        cur.execute("SELECT MAX(snapshot_date) FROM hist_cs WHERE account = %s", (account,))
        latest_date = cur.fetchone()[0]
        print(f"Date: {latest_date}\n")

        # Get all positions
        print("Symbol   | Qty        | Price      | Daily $  | Market Value | Cost Basis  | Total Gain $")
        print("-" * 100)

        cur.execute("""
            SELECT symbol, qty, price, day_chng_dollar, market_value, cost_basis, gain_dollar
            FROM hist_cs
            WHERE account = %s AND snapshot_date = %s
            ORDER BY symbol
        """, (account, latest_date))

        total_day_gain = 0.0
        total_mv = 0.0
        total_cb = 0.0
        total_gain = 0.0

        for symbol, qty, price, day_chng_dollar, market_value, cost_basis, gain_dollar in cur.fetchall():
            qty_f = float(qty) if qty else 0.0
            price_f = float(price) if price else 0.0
            day_chng = float(day_chng_dollar) if day_chng_dollar else 0.0
            mv = float(market_value) if market_value else 0.0
            cb = float(cost_basis) if cost_basis else 0.0
            gain = float(gain_dollar) if gain_dollar else 0.0

            total_day_gain += day_chng
            total_mv += mv
            total_cb += cb
            total_gain += gain

            print(f"{symbol:8} | {qty_f:10.2f} | {price_f:10.2f} | {day_chng:8.2f} | {mv:12.2f} | {cb:10.2f} | {gain:10.2f}")

        print("-" * 100)
        print(f"{'TOTALS':8} | {'':10} | {'':10} | {total_day_gain:8.2f} | {total_mv:12.2f} | {total_cb:10.2f} | {total_gain:10.2f}")

        print(f"\n=== SUMMARY ===")
        print(f"Today's gain (day_chng_dollar): ${total_day_gain:.2f}")
        print(f"You said you see: $314.40")
        print(f"You expected: $344.35")
        print(f"Difference: ${344.35 - total_day_gain:.2f}")
