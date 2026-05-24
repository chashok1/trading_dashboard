from etl.db import session_scope
from sqlalchemy import text

with session_scope() as sess:
    # Check if hist_pk exists
    result = sess.execute(text("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables 
            WHERE table_name = 'hist_pk'
        );
    """)).scalar()
    
    if result:
        print("hist_pk EXISTS")
        # Show structure
        cols = sess.execute(text("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'hist_pk'
            ORDER BY ordinal_position;
        """)).fetchall()
        print("Columns:")
        for col in cols:
            print(f"  {col[0]:<20} {col[1]}")
    else:
        print("hist_pk DOES NOT EXIST - this table needs to be created")
        print("\nChecking what tables do exist:")
        tables = sess.execute(text("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'public' AND table_name LIKE 'hist%'
            ORDER BY table_name;
        """)).fetchall()
        for t in tables:
            print(f"  {t[0]}")