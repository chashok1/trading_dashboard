from etl.db import session_scope
from sqlalchemy import text

with session_scope() as session:
    # Check if source_file is populated for hist_cs 2026-05-27
    result = session.execute(text("""
        SELECT COUNT(*) as total, COUNT(source_file) as with_source, COUNT(CASE WHEN source_file IS NULL THEN 1 END) as null_source
        FROM hist_cs WHERE snapshot_date = '2026-05-27'
    """)).fetchone()

    print(f"hist_cs (2026-05-27):")
    print(f"  Total rows: {result[0]}")
    print(f"  With source_file: {result[1]}")
    print(f"  NULL source_file: {result[2]}")

    # Show sample
    sample = session.execute(text("""
        SELECT symbol, source_file FROM hist_cs WHERE snapshot_date = '2026-05-27' LIMIT 3
    """)).fetchall()
    print(f"  Sample:")
    for row in sample:
        print(f"    {row[0]}: {row[1]}")
