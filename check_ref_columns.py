import psycopg
from config.settings import settings

with psycopg.connect(
    host=settings.pg_host, port=settings.pg_port, dbname=settings.pg_database,
    user=settings.pg_user, password=settings.pg_password,
) as conn:
    with conn.cursor() as cur:
        # Get column names
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'ref_load_files'
            ORDER BY ordinal_position
        """)
        print("ref_load_files columns:")
        for (col,) in cur.fetchall():
            print(f"  - {col}")

        print("\nETF record:")
        cur.execute("SELECT * FROM ref_load_files WHERE LOWER(file_type) = 'etf'")
        # Get column names from cursor description
        cols = [desc[0] for desc in cur.description]
        row = cur.fetchone()
        if row:
            for col, val in zip(cols, row):
                print(f"  {col}: {val}")
