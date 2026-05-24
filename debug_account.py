import psycopg
from config.settings import settings

with psycopg.connect(
    host=settings.pg_host, port=settings.pg_port, dbname=settings.pg_database,
    user=settings.pg_user, password=settings.pg_password,
) as conn:
    with conn.cursor() as cur:
        # Check account names in hist_cst
        print("Accounts in hist_cst:")
        cur.execute("""
            SELECT DISTINCT account FROM hist_cst
        """)
        for row in cur.fetchall():
            print(f"  '{row[0]}'")

        # Check account names in hist_cs
        print("\nAccounts in hist_cs:")
        cur.execute("""
            SELECT DISTINCT account FROM hist_cs
        """)
        for row in cur.fetchall():
            print(f"  '{row[0]}'")

        # Try exact match
        print("\nTrying exact match for HYG...")
        cur.execute("""
            SELECT COUNT(*) FROM hist_cst
            WHERE symbol = 'HYG' AND account = 'Rollover_IRA_XXX892'
        """)
        print(f"  Transactions found: {cur.fetchone()[0]}")

        cur.execute("""
            SELECT COUNT(*) FROM hist_cs
            WHERE symbol = 'HYG' AND account = 'Rollover_IRA_XXX892'
        """)
        print(f"  Positions found: {cur.fetchone()[0]}")
