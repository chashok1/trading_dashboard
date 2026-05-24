import psycopg
from config.settings import settings
from datetime import datetime, date

with psycopg.connect(
    host=settings.pg_host, port=settings.pg_port, dbname=settings.pg_database,
    user=settings.pg_user, password=settings.pg_password,
) as conn:
    with conn.cursor() as cur:
        # Check latest ETF data
        print("Latest ETF data:")
        cur.execute("SELECT MAX(snapshot_date) FROM hist_etf")
        latest = cur.fetchone()[0]
        print(f"  Latest snapshot_date: {latest}")

        today = date(2026, 5, 16)
        if latest:
            days_old = (today - latest).days
            print(f"  Days old: {days_old} days")

        # ETF schedule
        print(f"\nETF Schedule: Every Sunday at 09:00")
        print(f"Today is: Friday, {today}")
        print(f"Last Sunday was: 2026-05-12")
        print(f"Next Sunday is: 2026-05-19")

        # Check if there's an ETF file for 2026-05-12 (last Sunday)
        print("\nChecking for ETF file from last Sunday (2026-05-12):")
        cur.execute("""
            SELECT file_path, processed_at FROM meta_file_processed
            WHERE file_path LIKE '%ETF%' AND file_path LIKE '%2026-05-12%'
        """)
        row = cur.fetchone()
        if row:
            print(f"  Found: {row[0]}")
            print(f"  Processed: {row[1]}")
        else:
            print(f"  Not found - ETF file from 2026-05-12 was not processed")

        print(f"\n[Status] ETF data is from {latest}, which is {days_old} days old")
        if days_old >= 3:
            print(f"⚠ [WARNING] ETF data is overdue - expected update on 2026-05-12 (Sunday)")
