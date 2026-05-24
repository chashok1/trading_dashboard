import os
os.chdir('.')
from etl.db import session_scope
from sqlalchemy import text

print("=" * 80)
print("ETL FILE PROCESSING REPORT")
print("=" * 80)

with session_scope() as sess:
    # Check schema first
    print("\n[1] ref_load_files SCHEMA:")
    print("-" * 80)
    cols = sess.execute(text("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'ref_load_files'
        ORDER BY ordinal_position;
    """)).fetchall()
    for col in cols:
        print(f"  {col[0]:<20} {col[1]}")
    
    # Get the actual data
    print("\n[2] SCHEDULED FILE TYPES:")
    print("-" * 80)
    scheduled = sess.execute(text("""
        SELECT * FROM ref_load_files ORDER BY file_type;
    """)).fetchall()
    print(f"  Total file types: {len(scheduled)}")
    for row in scheduled:
        print(f"  {row}")
    
    # Summary of loads by file type
    print("\n[3] LOADS BY FILE TYPE (last 30 days):")
    print("-" * 80)
    summary = sess.execute(text("""
        SELECT 
            file_type,
            COUNT(*) as loads,
            SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as ok,
            SUM(rows_inserted) as total_rows
        FROM meta_etl_run
        WHERE started_at > now() - interval '30 days'
        GROUP BY file_type
        ORDER BY file_type;
    """)).fetchall()
    
    for row in summary:
        print(f"  {row[0]:<15} | {row[1]:3} loads | {row[2]:3} ok | {row[3]:,} rows")

    # Files with 0 rows
    print("\n[4] FILES WITH 0 ROWS INSERTED:")
    print("-" * 80)
    zero_rows = sess.execute(text("""
        SELECT file_type, COUNT(*) as count
        FROM meta_etl_run
        WHERE rows_inserted = 0 AND status = 'success'
        GROUP BY file_type;
    """)).fetchall()
    
    for row in zero_rows:
        print(f"  {row[0]:<15} | {row[1]} files")