"""Find missing $29.95 in account 892."""
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

        # Get all positions
        cur.execute("""
            SELECT symbol, day_chng_dollar
            FROM hist_cs
            WHERE account LIKE '%892' AND snapshot_date = %s
            ORDER BY symbol
        """, (latest_date,))

        total = 0.0
        print("Symbol       | Daily Change")
        print("-" * 30)
        for symbol, day_chng in cur.fetchall():
            day_chng = float(day_chng) if day_chng else 0.0
            total += day_chng
            print(f"{symbol:12} | {day_chng:12.2f}")

        print("-" * 30)
        print(f"Total        | {total:12.2f}")
        print(f"\nYou see: -$314.40")
        print(f"You expect: -$344.35")
        print(f"Missing: ${-344.35 - total:.2f}")

        # Count positions
        cur.execute("SELECT COUNT(*) FROM hist_cs WHERE account LIKE '%892' AND snapshot_date = %s", (latest_date,))
        count = cur.fetchone()[0]
        print(f"\nTotal positions: {count}")

        # Check if there's a cash position with different symbol
        print("\n=== CHECKING FOR CASH ===")
        cur.execute("""
            SELECT symbol FROM hist_cs
            WHERE account LIKE '%892' AND snapshot_date = %s
            AND (symbol = 'CASH' OR symbol = '' OR symbol IS NULL OR security_type LIKE '%Cash%')
        """, (latest_date,))

        rows = cur.fetchall()
        if rows:
            print("Found cash positions:")
            for (sym,) in rows:
                print(f"  - {sym}")
        else:
            print("No cash positions found")
