from config.settings import settings
from etl.db import session_scope
from sqlalchemy import text

with session_scope() as s:
    print("CS 2026-05-14 file status:\n")

    # Check meta_file_processed
    result = s.execute(text("""
        SELECT file_path, file_date, processed_at, file_type, target_tab
        FROM meta_file_processed
        WHERE file_path LIKE '%CS 2026-05-14%'
    """)).first()

    if result:
        print(f"File: {result[0]}")
        print(f"file_date: {result[1]}")
        print(f"processed_at: {result[2]}")
        print(f"target_tab: {result[4]}")
    else:
        print("File not found in meta_file_processed!")

    # Check if data actually exists in hist_cs for 2026-05-14
    print("\nData in hist_cs:")
    result = s.execute(text("""
        SELECT snapshot_date, COUNT(*) as rows
        FROM hist_cs
        WHERE snapshot_date = '2026-05-14'
        GROUP BY snapshot_date
    """)).first()

    if result:
        print(f"  2026-05-14: {result[1]} rows")
    else:
        print(f"  2026-05-14: NO DATA!")

    # Check latest dates in hist_cs
    print("\nLatest dates in hist_cs:")
    result = s.execute(text("""
        SELECT snapshot_date, COUNT(*) as rows
        FROM hist_cs
        GROUP BY snapshot_date
        ORDER BY snapshot_date DESC
        LIMIT 3
    """))
    for row in result:
        print(f"  {row[0]}: {row[1]} rows")
