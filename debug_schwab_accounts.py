"""Debug Schwab accounts and daily gain calculation."""
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
        print("=== ALL SCHWAB ACCOUNTS ===\n")

        # Get all distinct Schwab accounts
        cur.execute("""
            SELECT DISTINCT account FROM hist_cs
            ORDER BY account
        """)

        accounts = [row[0] for row in cur.fetchall()]
        print(f"Total Schwab accounts: {len(accounts)}")
        for acct in accounts:
            print(f"  - {acct}")

        # Get latest date
        cur.execute("SELECT MAX(snapshot_date) FROM hist_cs")
        latest_date = cur.fetchone()[0]
        print(f"\nLatest date: {latest_date}\n")

        # Calculate total daily gain across ALL Schwab accounts
        print("=== DAILY GAIN BY ACCOUNT ===")
        cur.execute("""
            SELECT account, SUM(day_chng_dollar) as total_day_gain
            FROM hist_cs
            WHERE snapshot_date = %s
            GROUP BY account
            ORDER BY account
        """, (latest_date,))

        grand_total = 0.0
        for account, day_gain in cur.fetchall():
            day_gain = float(day_gain) if day_gain else 0.0
            grand_total += day_gain
            print(f"{account:30} | ${day_gain:10.2f}")

        print(f"\n{'TOTAL (all Schwab accounts)':30} | ${grand_total:10.2f}")

        # Now check account 892 specifically
        print(f"\n=== ACCOUNT 892 BREAKDOWN ===")
        cur.execute("""
            SELECT COUNT(*), SUM(day_chng_dollar)
            FROM hist_cs
            WHERE account LIKE '%892' AND snapshot_date = %s
        """, (latest_date,))

        count, total_day = cur.fetchone()
        total_day = float(total_day) if total_day else 0.0
        print(f"Positions in account 892: {count}")
        print(f"Daily gain in account 892: ${total_day:.2f}")

        # Check if there are any pending or excluded positions
        print(f"\n=== CHECK FOR EXCLUDED/PENDING POSITIONS ===")
        cur.execute("""
            SELECT COUNT(*), SUM(day_chng_dollar)
            FROM hist_cs
            WHERE account LIKE '%892' AND snapshot_date = %s
            AND security_type IS NOT NULL
        """, (latest_date,))

        count2, total2 = cur.fetchone()
        total2 = float(total2) if total2 else 0.0
        print(f"Positions with security_type: {count2}")
        print(f"Daily gain: ${total2:.2f}")

        # List positions that might be missing
        print(f"\n=== POSITIONS WITH NULL/ZERO VALUES ===")
        cur.execute("""
            SELECT symbol, security_type, day_chng_dollar
            FROM hist_cs
            WHERE account LIKE '%892' AND snapshot_date = %s
            AND (day_chng_dollar IS NULL OR day_chng_dollar = 0)
            ORDER BY symbol
        """, (latest_date,))

        rows = cur.fetchall()
        if rows:
            for symbol, sec_type, day_gain in rows:
                print(f"{symbol:10} | Type: {sec_type:15} | Daily: {day_gain}")
        else:
            print("None")

        print(f"\n=== MISSING $29.95 ANALYSIS ===")
        print(f"Calculated: -$314.40")
        print(f"Expected: -$344.35")
        print(f"Missing: $29.95")
