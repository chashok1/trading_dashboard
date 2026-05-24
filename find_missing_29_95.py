"""Find the missing $29.95 in account 892's daily gain."""
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
        # Get latest date
        cur.execute("SELECT MAX(snapshot_date) FROM hist_cs")
        latest_date = cur.fetchone()[0]
        print(f"Date: {latest_date}\n")

        # Check for CASH or other special entries
        print("=== CHECKING FOR CASH/SPECIAL POSITIONS ===")
        cur.execute("""
            SELECT symbol, qty, price, day_chng_dollar, security_type, description
            FROM hist_cs
            WHERE account LIKE '%892' AND snapshot_date = %s
            ORDER BY symbol
        """, (latest_date,))

        total_daily = 0.0
        for symbol, qty, price, day_chng_dollar, sec_type, desc in cur.fetchall():
            day_chng = float(day_chng_dollar) if day_chng_dollar else 0.0
            total_daily += day_chng
            print(f"{symbol:10} | Qty: {float(qty) if qty else 0:8.2f} | Chg: {day_chng:8.2f} | Type: {sec_type:20} | {desc}")

        print(f"\nTotal daily gain: ${total_daily:.2f}")
        print(f"Expected: $-344.35")
        print(f"Missing: ${-344.35 - total_daily:.2f}")

        # Check for UNINVESTED_CASH or similar
        print("\n=== CHECK FOR CASH ENTRIES ===")
        cur.execute("""
            SELECT symbol, qty, day_chng_dollar
            FROM hist_cs
            WHERE account LIKE '%892' AND snapshot_date = %s
            AND (symbol ILIKE '%cash%' OR symbol ILIKE '%money%' OR symbol = '')
        """, (latest_date,))

        rows = cur.fetchall()
        if rows:
            for symbol, qty, day_chng in rows:
                print(f"  {symbol}: {day_chng}")
        else:
            print("  None found")

        # Check yesterday's data to see if there's a position that's not in today's file
        print("\n=== COMPARING WITH YESTERDAY'S DATA ===")
        cur.execute("""
            SELECT snapshot_date FROM hist_cs
            WHERE account LIKE '%892'
            ORDER BY snapshot_date DESC
            LIMIT 5
        """)

        dates = [row[0] for row in cur.fetchall()]
        print(f"Dates available for account 892: {dates}")

        if len(dates) > 1:
            yesterday = dates[1]
            print(f"\nPositions in yesterday's file ({yesterday}):")
            cur.execute("""
                SELECT symbol FROM hist_cs
                WHERE account LIKE '%892' AND snapshot_date = %s
                ORDER BY symbol
            """, (yesterday,))
            yesterday_symbols = {row[0] for row in cur.fetchall()}

            print(f"Positions in today's file ({latest_date}):")
            cur.execute("""
                SELECT symbol FROM hist_cs
                WHERE account LIKE '%892' AND snapshot_date = %s
                ORDER BY symbol
            """, (latest_date,))
            today_symbols = {row[0] for row in cur.fetchall()}

            missing = yesterday_symbols - today_symbols
            if missing:
                print(f"\n[!] POSITIONS MISSING FROM TODAY'S FILE:")
                for sym in sorted(missing):
                    print(f"    - {sym}")
