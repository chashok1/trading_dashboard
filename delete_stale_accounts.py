"""Delete stale Schwab accounts 893, 894, 895, 896."""
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
        # Show what will be deleted
        cur.execute("""
            SELECT account, COUNT(*) as row_count
            FROM hist_cs
            WHERE account LIKE '%89_'
            GROUP BY account
            ORDER BY account
        """)

        print("=== ACCOUNTS TO DELETE ===")
        to_delete = []
        for account, count in cur.fetchall():
            if account.endswith('893') or account.endswith('894') or account.endswith('895') or account.endswith('896'):
                to_delete.append(account)
                print(f"{account}: {count} rows")

        if not to_delete:
            print("No stale accounts found")
            exit(0)

        # Delete them
        print(f"\nDeleting {len(to_delete)} stale accounts...")
        for account in to_delete:
            cur.execute("DELETE FROM hist_cs WHERE account = %s", (account,))
            print(f"  Deleted {account}")

        conn.commit()
        print(f"\n[OK] Deleted {len(to_delete)} stale accounts")

        # Verify deletion
        cur.execute("""
            SELECT DISTINCT account FROM hist_cs
            ORDER BY account
        """)
        print(f"\nRemaining accounts:")
        for (account,) in cur.fetchall():
            print(f"  - {account}")
