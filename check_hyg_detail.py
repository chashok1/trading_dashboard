import psycopg
from config.settings import settings

with psycopg.connect(
    host=settings.pg_host, port=settings.pg_port, dbname=settings.pg_database,
    user=settings.pg_user, password=settings.pg_password,
) as conn:
    with conn.cursor() as cur:
        # Check HYG across dates
        print("HYG position history:")
        cur.execute("""
            SELECT snapshot_date, account, symbol, qty, price, cost_basis, market_value, day_chng_dollar
            FROM hist_cs
            WHERE symbol = 'HYG'
            ORDER BY snapshot_date DESC
        """)
        for row in cur.fetchall():
            print(f"  {row[0]} | {row[2]} | Qty: {float(row[3]) if row[3] else 0:6.0f} | Price: ${float(row[4]) if row[4] else 0:8.2f} | Cost Basis: ${float(row[5]) if row[5] else 0:10.2f} | Market Value: ${float(row[6]) if row[6] else 0:10.2f} | Daily Change: ${float(row[7]) if row[7] else 0:8.2f}")

        # The expected -$344.35 might include HYG's daily change from both days
        print("\nHYG daily change across dates:")
        cur.execute("""
            SELECT snapshot_date, day_chng_dollar
            FROM hist_cs
            WHERE symbol = 'HYG'
            ORDER BY snapshot_date DESC
            LIMIT 5
        """)
        total_hyg_daily = 0
        for row in cur.fetchall():
            val = float(row[1]) if row[1] else 0
            total_hyg_daily += val
            print(f"  {row[0]}: ${val:8.2f}")
        print(f"  Total HYG daily changes: ${total_hyg_daily:8.2f}")
