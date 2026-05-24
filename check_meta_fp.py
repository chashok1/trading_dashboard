from sqlalchemy import text
from etl.db import session_scope

with session_scope() as s:
    print("meta_file_processed for ETF:")
    result = s.execute(text("""
        SELECT file_type, file_date, processed_at, file_path
        FROM meta_file_processed
        WHERE LOWER(file_type) = 'etf'
        ORDER BY processed_at DESC
        LIMIT 5
    """)).fetchall()

    if result:
        for row in result:
            print(f"  Type: {row[0]:15} | Date: {row[1]} | Processed: {row[2]} | Path: {row[3]}")
    else:
        print("  No ETF records found")

    print("\nAll enabled file types in ref_load_files:")
    result = s.execute(text("""
        SELECT file_type FROM ref_load_files WHERE enabled = TRUE ORDER BY file_type
    """)).fetchall()
    for (ft,) in result:
        print(f"  - {ft}")
