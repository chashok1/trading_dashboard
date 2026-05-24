import psycopg
from config.settings import settings
from datetime import datetime

with psycopg.connect(
    host=settings.pg_host, port=settings.pg_port, dbname=settings.pg_database,
    user=settings.pg_user, password=settings.pg_password,
) as conn:
    with conn.cursor() as cur:
        # Check ETF schedule
        print("ETF Load Schedule:")
        cur.execute("""
            SELECT file_type, target_tab, week_day, time_hhmm
            FROM ref_load_files
            WHERE LOWER(file_type) = 'etf'
        """)
        for row in cur.fetchall():
            print(f"  File Type: {row[0]}")
            print(f"  Target Tab: {row[1]}")
            print(f"  Week Day: {row[2]}")
            print(f"  Time: {row[3]}")

        # Check last processed date
        print("\nLast ETF file processed:")
        cur.execute("""
            SELECT file_path, file_type, file_date, processed_at
            FROM meta_file_processed
            WHERE file_type LIKE '%etf%' OR file_path LIKE '%etf%'
            ORDER BY processed_at DESC
            LIMIT 1
        """)
        row = cur.fetchone()
        if row:
            print(f"  File: {row[0]}")
            print(f"  Type: {row[1]}")
            print(f"  File Date: {row[2]}")
            print(f"  Processed: {row[3]}")
        else:
            print("  No ETF files found in processing history")

        # Check latest ETF data in database
        print("\nLatest ETF data in hist_etf:")
        cur.execute("""
            SELECT MAX(snapshot_date) FROM hist_etf
        """)
        latest = cur.fetchone()[0]
        print(f"  Latest snapshot_date: {latest}")

        # Check how old the latest data is
        if latest:
            cur.execute("""
                SELECT MAX(snapshot_date) FROM hist_etf
            """)
            latest_date = cur.fetchone()[0]
            today = datetime.now().date()
            days_old = (today - latest_date).days
            print(f"  Days old: {days_old}")
            if days_old > 3:
                print(f"  [WARNING] ETF data is {days_old} days old")
