"""Check the filter rule for hist_ii."""
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
        # Check if ref_data_filter_logic table exists
        cur.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'ref_data_filter_logic'
        """)
        if not cur.fetchone():
            print("[OK] ref_data_filter_logic table does NOT exist - all rows shown by default")
        else:
            # Table exists, check if hist_ii has a rule
            cur.execute("""
                SELECT table_name, filter_type, date_column, window_days, description
                FROM ref_data_filter_logic
                WHERE table_name = 'hist_ii'
            """)
            rule = cur.fetchone()

            if rule:
                print("[RULE FOUND] hist_ii filter rule:")
                print(f"  Table: {rule[0]}")
                print(f"  Filter type: {rule[1]}")
                print(f"  Date column: {rule[2]}")
                print(f"  Window days: {rule[3]}")
                print(f"  Description: {rule[4]}")
            else:
                print("[NO RULE] hist_ii has no filter rule - all rows should be shown")

            # Check all filter rules
            cur.execute("SELECT COUNT(*) FROM ref_data_filter_logic")
            print(f"\nTotal filter rules defined: {cur.fetchone()[0]}")

            cur.execute("SELECT table_name, filter_type FROM ref_data_filter_logic ORDER BY table_name")
            print("\nAll defined rules:")
            for row in cur.fetchall():
                print(f"  {row[0]}: {row[1]}")
