"""Check what dates are in hist_ii and test the LATEST_BEFORE logic."""
import psycopg
from datetime import datetime
from config.settings import settings

with psycopg.connect(
    host=settings.pg_host,
    port=settings.pg_port,
    dbname=settings.pg_database,
    user=settings.pg_user,
    password=settings.pg_password,
) as conn:
    with conn.cursor() as cur:
        # Get all distinct dates in hist_ii
        cur.execute("SELECT DISTINCT snapshot_date FROM hist_ii ORDER BY snapshot_date DESC LIMIT 10")
        print("Latest 10 dates in hist_ii:")
        all_dates = []
        for row in cur.fetchall():
            all_dates.append(row[0])
            print(f"  {row[0]}")

        # Simulate what LATEST_BEFORE filter does
        test_date = datetime(2026, 5, 11).date()
        print(f"\nSimulating LATEST_BEFORE filter for date={test_date}:")
        print(f"  Query: SELECT MAX(snapshot_date) WHERE snapshot_date < '{test_date}'")

        cur.execute("SELECT MAX(snapshot_date) FROM hist_ii WHERE snapshot_date < %s", (test_date,))
        result = cur.fetchone()[0]
        print(f"  Result: {result}")

        if result:
            cur.execute("SELECT COUNT(*) FROM hist_ii WHERE snapshot_date = %s", (result,))
            count = cur.fetchone()[0]
            print(f"  Rows for that date: {count}")

            cur.execute("""
                SELECT symbol, outlook FROM hist_ii
                WHERE snapshot_date = %s
                ORDER BY symbol
            """, (result,))
            print(f"  Symbols for {result}:")
            for symbol, outlook in cur.fetchall():
                print(f"    {symbol}: {outlook}")
        else:
            print(f"  [ERROR] No data found before {test_date}")

        # Check what's the latest date overall
        cur.execute("SELECT MAX(snapshot_date) FROM hist_ii")
        latest = cur.fetchone()[0]
        print(f"\nLatest date in hist_ii: {latest}")
