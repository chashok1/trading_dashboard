from etl.db import session_scope
from sqlalchemy import text

with session_scope() as s:
    rows = s.execute(text('''
        SELECT account, symbol, market_value, day_chng_dollar, gain_dollar
        FROM hist_cs
        WHERE snapshot_date = '2026-05-13'
        ORDER BY account, symbol
    ''')).fetchall()

    print('CS Data:')
    for row in rows:
        acct = row[0] if row[0] else ''
        sym = row[1] if row[1] else ''
        mv = row[2] if row[2] is not None else 0
        today = row[3] if row[3] is not None else 0
        total = row[4] if row[4] is not None else 0
        print(f'{acct:40} | {sym:25} | MV={mv:>10.2f} | Today={today:>8.2f} | Total={total:>10.2f}')
