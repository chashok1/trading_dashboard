from config.settings import settings
from etl.db import session_scope
from sqlalchemy import text

with session_scope() as s:
    print("CS 2026-05-14 load history:\n")

    # Check meta_etl_run for this file
    result = s.execute(text("""
        SELECT run_id, started_at, finished_at, rows_read, rows_inserted, rows_skipped,
               skip_reasons, status, error_msg
        FROM meta_etl_run
        WHERE file_path LIKE '%CS 2026-05-14%'
        ORDER BY started_at DESC
        LIMIT 3
    """)).fetchall()

    if result:
        for row in result:
            print(f"Run ID: {row[0]}")
            print(f"  Started: {row[1]}")
            print(f"  Finished: {row[2]}")
            print(f"  Read: {row[3]}, Inserted: {row[4]}, Skipped: {row[5]}")
            print(f"  Skip reasons: {row[6]}")
            print(f"  Status: {row[7]}")
            if row[8]:
                print(f"  Error: {row[8][:200]}")
            print()
    else:
        print("No load records found for CS 2026-05-14!")
