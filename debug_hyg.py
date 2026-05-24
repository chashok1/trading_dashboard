import psycopg
from config.settings import settings

with psycopg.connect(
    host=settings.pg_host, port=settings.pg_port, dbname=settings.pg_database,
    user=settings.pg_user, password=settings.pg_password,
) as conn:
    with conn.cursor() as cur:
        # Check HYG on 2026-05-14 (prior to sale)
        print("HYG on 2026-05-14 (prior day):")
        cur.execute("""
            SELECT account, symbol, qty, price, cost_basis, market_value
            FROM hist_cs
            WHERE symbol = 'HYG' AND snapshot_date = '2026-05-14'
        """)
        for row in cur.fetchall():
            print(f"  Account: {row[0]} | Symbol: {row[1]} | Qty: {row[2]} | Price: {row[3]} | Cost Basis: {row[4]} | Market Value: {row[5]}")

        # Check HYG transaction
        print("\nHYG transaction:")
        cur.execute("""
            SELECT trade_date, action, symbol, quantity, price, amount
            FROM hist_cst
            WHERE symbol = 'HYG'
        """)
        for row in cur.fetchall():
            print(f"  Date: {row[0]} | Action: {row[1]} | Symbol: {row[2]} | Qty: {row[3]} | Price: {row[4]} | Amount: {row[5]}")

        # Check the derive query directly
        print("\nDerived calculation:")
        cur.execute("""
            SELECT t.account, t.symbol, t.quantity, t.amount,
                   c.cost_basis, c.qty AS held_qty
            FROM hist_cst t
            LEFT JOIN hist_cs c
                   ON c.account = t.account
                  AND c.symbol   = t.symbol
                  AND c.snapshot_date = (SELECT MAX(snapshot_date) FROM hist_cs WHERE snapshot_date < '2026-05-15')
            WHERE t.trade_date = '2026-05-15'
              AND LOWER(t.action) = 'sell'
              AND t.symbol = 'HYG'
        """)
        for row in cur.fetchall():
            print(f"  Account: {row[0]} | Symbol: {row[1]} | Qty Sold: {row[2]} | Amount: {row[3]} | Cost Basis: {row[4]} | Held Qty: {row[5]}")
            if row[4] is not None and row[5] is not None and float(row[5]) != 0:
                avg_cost = float(row[4]) / float(row[5])
                realized = float(row[3]) - (float(row[2]) * avg_cost)
                print(f"    Calculated avg_cost: ${avg_cost:.4f}, realized: ${realized:.2f}")
