import psycopg
from config.settings import settings

with psycopg.connect(
    host=settings.pg_host, port=settings.pg_port, dbname=settings.pg_database,
    user=settings.pg_user, password=settings.pg_password,
) as conn:
    with conn.cursor() as cur:
        # Find and delete processing records for CS 2026-05-16 files
        print("Looking for CS 2026-05-16 processing records...")

        # Check meta_file_processed
        cur.execute("""
            SELECT file_path FROM meta_file_processed
            WHERE file_path LIKE '%2026-05-16%' AND file_type LIKE '%CS%'
        """)
        files = cur.fetchall()
        if files:
            print(f"\nFound in meta_file_processed:")
            for (f,) in files:
                print(f"  - {f}")

            cur.execute("""
                DELETE FROM meta_file_processed
                WHERE file_path LIKE '%2026-05-16%' AND file_type LIKE '%CS%'
            """)
            print(f"  [OK] Deleted {cur.rowcount} rows from meta_file_processed")
        else:
            print("\n  No records found in meta_file_processed")

        # Check meta_etl_run
        cur.execute("""
            SELECT file_path FROM meta_etl_run
            WHERE file_path LIKE '%2026-05-16%' AND file_type LIKE '%CS%'
        """)
        runs = cur.fetchall()
        if runs:
            print(f"\nFound in meta_etl_run:")
            for (f,) in runs:
                print(f"  - {f}")

            cur.execute("""
                DELETE FROM meta_etl_run
                WHERE file_path LIKE '%2026-05-16%' AND file_type LIKE '%CS%'
            """)
            print(f"  [OK] Deleted {cur.rowcount} rows from meta_etl_run")
        else:
            print("\n  No records found in meta_etl_run")

        conn.commit()
        print("\n[DONE] CS 2026-05-16 file processing records cleared")
