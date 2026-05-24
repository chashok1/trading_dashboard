import psycopg
from config.settings import settings

with psycopg.connect(
    host=settings.pg_host, port=settings.pg_port, dbname=settings.pg_database,
    user=settings.pg_user, password=settings.pg_password,
) as conn:
    with conn.cursor() as cur:
        # Get account 892
        cur.execute("SELECT DISTINCT account FROM hist_cs ORDER BY account")
        accounts = [row[0] for row in cur.fetchall()]
        acct_892 = [a for a in accounts if '892' in a][0]

        # Get available dates
        cur.execute("""
            SELECT DISTINCT snapshot_date FROM hist_cs
            WHERE account = %s
            ORDER BY snapshot_date DESC LIMIT 5
        """, (acct_892,))
        dates = [row[0] for row in cur.fetchall()]
        print(f"Available dates: {dates}\n")

        if len(dates) < 2:
            print("Not enough dates to compare")
            exit(0)

        today = dates[0]
        yesterday = dates[1]

        # Get positions from both days
        cur.execute("""
            SELECT symbol FROM hist_cs WHERE account = %s AND snapshot_date = %s
            ORDER BY symbol
        """, (acct_892, today))
        today_symbols = {row[0] for row in cur.fetchall()}

        cur.execute("""
            SELECT symbol FROM hist_cs WHERE account = %s AND snapshot_date = %s
            ORDER BY symbol
        """, (acct_892, yesterday))
        yesterday_symbols = {row[0] for row in cur.fetchall()}

        # Find sold positions (in yesterday but not today)
        sold = yesterday_symbols - today_symbols
        new = today_symbols - yesterday_symbols

        print(f"=== COMPARISON: {yesterday} vs {today} ===\n")

        if sold:
            print(f"SOLD/REMOVED positions ({len(sold)}):")
            for symbol in sorted(sold):
                cur.execute("""
                    SELECT day_chng_dollar, qty, market_value, price
                    FROM hist_cs
                    WHERE account = %s AND snapshot_date = %s AND symbol = %s
                """, (acct_892, yesterday, symbol))
                row = cur.fetchone()
                if row:
                    day_chng = float(row[0]) if row[0] else 0
                    qty = float(row[1]) if row[1] else 0
                    mv = float(row[2]) if row[2] else 0
                    price = float(row[3]) if row[3] else 0
                    print(f"  {symbol:10} | Daily change: ${day_chng:8.2f} | Qty: {qty:8.2f} | Price: {price:8.2f} | MV: ${mv:10.2f}")
        else:
            print("No sold positions")

        if new:
            print(f"\nNEW positions ({len(new)}):")
            for symbol in sorted(new):
                print(f"  {symbol}")
        else:
            print("\nNo new positions")

        # Check total daily change of sold positions
        if sold:
            cur.execute("""
                SELECT SUM(day_chng_dollar)
                FROM hist_cs
                WHERE account = %s AND snapshot_date = %s AND symbol IN ({})
            """.format(','.join(['%s']*len(sold))), [acct_892, yesterday] + list(sold))
            total_sold_gain = float(cur.fetchone()[0] or 0)
            print(f"\nTotal daily gain from SOLD positions: ${total_sold_gain:.2f}")
            print(f"Missing amount needed: -$29.95")
