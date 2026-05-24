"""Debug account 892 (Schwab) today's gain calculation."""
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
        # Find account ending with 892
        cur.execute("""
            SELECT DISTINCT account FROM hist_cs
            WHERE account LIKE '%892'
        """)
        acct_row = cur.fetchone()
        if not acct_row:
            print("Account ending with 892 not found")
            exit(1)

        account = acct_row[0]
        print(f"Account: {account}\n")

        # Get latest date
        cur.execute("SELECT MAX(snapshot_date) FROM hist_cs WHERE account = %s", (account,))
        latest_date = cur.fetchone()[0]
        print(f"Latest snapshot date: {latest_date}\n")

        # Check CS raw data - calculate today's gain
        print("=== Schwab (hist_cs) Raw Data ===")
        print("Symbol   | Qty        | Last Price | Chg/day | Market Value | Cost Basis  | Today Gain")
        print("-" * 95)

        cur.execute("""
            SELECT symbol, qty, last_price, last_price_change, market_value, cost_basis
            FROM hist_cs
            WHERE account = %s AND snapshot_date = %s
            ORDER BY symbol
        """, (account, latest_date))

        total_today_gain_calc = 0.0
        for symbol, qty, last_price, last_price_change, market_value, cost_basis in cur.fetchall():
            qty = float(qty) if qty else 0.0
            lp = float(last_price) if last_price else 0.0
            lpchg = float(last_price_change) if last_price_change else 0.0
            mv = float(market_value) if market_value else 0.0
            cb = float(cost_basis) if cost_basis else 0.0

            # Today's gain = Qty * Daily change
            today_gain = qty * lpchg if qty and lpchg else 0.0
            total_today_gain_calc += today_gain

            print(f"{symbol:8} | {qty:10.2f} | {lp:10.2f} | {lpchg:7.3f} | {mv:12.2f} | {cb:10.2f} | {today_gain:10.2f}")

        print("-" * 95)
        print(f"{'TOTAL':8} | {'':10} | {'':10} | {'':7} | {'':12} | {'':10} | {total_today_gain_calc:10.2f}")
        print(f"\nCalculated today's gain (Qty * DailyChg): ${total_today_gain_calc:.2f}")
