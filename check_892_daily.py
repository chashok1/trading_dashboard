import psycopg
from config.settings import settings

with psycopg.connect(
    host=settings.pg_host, port=settings.pg_port, dbname=settings.pg_database,
    user=settings.pg_user, password=settings.pg_password,
) as conn:
    with conn.cursor() as cur:
        # Get account
        cur.execute("SELECT DISTINCT account FROM hist_cs ORDER BY account")
        accounts = [row[0] for row in cur.fetchall()]
        acct_892 = [a for a in accounts if '892' in a][0]

        # Latest date
        cur.execute("SELECT MAX(snapshot_date) FROM hist_cs")
        latest = cur.fetchone()[0]

        # Sum daily gain for 892
        cur.execute("SELECT SUM(day_chng_dollar) FROM hist_cs WHERE account = %s AND snapshot_date = %s", (acct_892, latest))
        total = float(cur.fetchone()[0] or 0)

        print(f"Account: {acct_892}")
        print(f"Date: {latest}")
        print(f"Daily gain: ${total:.2f}")
        print(f"Expected: $-344.35")
        print(f"Missing: ${-344.35 - total:.2f}")

        # Count positions
        cur.execute("SELECT COUNT(*) FROM hist_cs WHERE account = %s AND snapshot_date = %s", (acct_892, latest))
        count = cur.fetchone()[0]
        print(f"Positions: {count}")

        # Check file source
        cur.execute("SELECT DISTINCT source_file FROM hist_cs WHERE account = %s AND snapshot_date = %s ORDER BY source_file", (acct_892, latest))
        files = [row[0] for row in cur.fetchall()]
        print(f"\nSource files:")
        for f in files:
            print(f"  {f}")
