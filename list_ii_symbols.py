"""List all II symbols for 2026-05-11."""
import psycopg
from config.settings import settings

with psycopg.connect(
    host=settings.pg_host, port=settings.pg_port, dbname=settings.pg_database,
    user=settings.pg_user, password=settings.pg_password,
) as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT symbol, outlook FROM hist_ii WHERE snapshot_date = '2026-05-11' ORDER BY symbol")
        print('All rows in database:')
        for symbol, outlook in cur.fetchall():
            print(f'  {symbol}: {outlook}')
