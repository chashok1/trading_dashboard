from etl.db import session_scope
from sqlalchemy import text

with session_scope() as sess:
    # Update Schwab folder path
    sess.execute(text("""
        UPDATE ref_load_files 
        SET source_dir = 'C:\Ashok\Investing\Stocks\CS\Archive'
        WHERE file_type = 'Schwab';
    """))
    
    # Verify
    result = sess.execute(text("""
        SELECT file_type, source_dir FROM ref_load_files 
        WHERE file_type IN ('Schwab', 'Call');
    """)).fetchall()
    
    print("Updated file paths in ref_load_files:")
    for row in result:
        print(f"  {row[0]:<15} -> {row[1]}")