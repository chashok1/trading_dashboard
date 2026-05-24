"""Fix the hist_ii filter rule from LATEST_BEFORE to EXACT_MATCH."""
import psycopg
from config.settings import settings

with psycopg.connect(
    host=settings.pg_host,
    port=settings.pg_port,
    dbname=settings.pg_database,
    user=settings.pg_user,
    password=settings.pg_password,
) as conn:
    with conn.cursor() as cur:
        # Update hist_ii filter rule from LATEST_BEFORE to EXACT_MATCH
        cur.execute("""
            UPDATE ref_data_filter_logic
            SET filter_type = 'EXACT_MATCH'
            WHERE table_name = 'hist_ii'
        """)
        conn.commit()
        print("[OK] Updated hist_ii filter rule from LATEST_BEFORE to EXACT_MATCH")

        # Verify
        cur.execute("""
            SELECT table_name, filter_type FROM ref_data_filter_logic WHERE table_name = 'hist_ii'
        """)
        row = cur.fetchone()
        print(f"Verified: {row[0]} = {row[1]}")
