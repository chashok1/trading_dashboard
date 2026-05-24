from etl.db import session_scope
from sqlalchemy import text

with session_scope() as sess:
    # Create hist_pk table with standard structure
    sql = """
    CREATE TABLE IF NOT EXISTS hist_pk (
        snapshot_date DATE NOT NULL,
        symbol TEXT NOT NULL,
        outlook TEXT,
        outlook_modifier TEXT,
        PRIMARY KEY (snapshot_date, symbol)
    );
    """
    
    sess.execute(text(sql))
    print("Created hist_pk table")
    
    # Verify it was created
    cols = sess.execute(text("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'hist_pk'
        ORDER BY ordinal_position;
    """)).fetchall()
    
    print("\nhist_pk schema:")
    for col in cols:
        print(f"  {col[0]:<20} {col[1]}")