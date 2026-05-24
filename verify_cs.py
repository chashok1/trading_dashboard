from etl.db import session_scope
from sqlalchemy import text

with session_scope() as s:
    result = s.execute(text('''
        SELECT snapshot_date, COUNT(*) as row_count,
               COUNT(DISTINCT account) as accounts,
               COUNT(DISTINCT symbol) as symbols
        FROM hist_cs
        WHERE snapshot_date = '2026-05-13'
        GROUP BY snapshot_date
    ''')).fetchone()

    if result:
        print(f'Data for {result[0]}:')
        print(f'  Total rows: {result[1]}')
        print(f'  Accounts: {result[2]}')
        print(f'  Symbols: {result[3]}')

        # Show sample data
        print('\nTop 5 positions by market value:')
        samples = s.execute(text('''
            SELECT account, symbol, qty, price, market_value, gain_dollar, gain_pct
            FROM hist_cs
            WHERE snapshot_date = '2026-05-13'
            ORDER BY market_value DESC LIMIT 5
        ''')).fetchall()
        for row in samples:
            qty = row[2] if row[2] is not None else 0
            mv = row[4] if row[4] is not None else 0
            gain = row[5] if row[5] is not None else 0
            pct = row[6] if row[6] is not None else 0
            print(f'  Acct {row[0]} | {row[1]:6} | Qty={qty:7.1f} | MV=${mv:12,.0f} | Gain ${gain:10,.0f} ({pct:6.1f}%)')
    else:
        print('No data found')
