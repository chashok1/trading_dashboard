#!/usr/bin/env python3
import sys
sys.path.insert(0, '.')
from config.settings import settings
from etl.db import get_engine
from sqlalchemy import inspect, text

engine = get_engine()

# Check schema
inspector = inspect(engine)
columns = inspector.get_columns('hist_cs')

print('hist_cs columns:')
for col in columns:
    print(f'  {col["name"]:30} {col["type"]}')

print('\n' + '='*80)
print('Querying hist_cs for 2026-05-13, Rollover_IRA account:')
print('='*80)

with engine.connect() as conn:
    # Query hist_cs for 2026-05-13, Rollover_IRA account
    query = '''
    SELECT symbol, day_chng_dollar
    FROM hist_cs
    WHERE snapshot_date = '2026-05-13' AND account LIKE '%Rollover_IRA%'
    ORDER BY symbol
    '''
    result = conn.execute(text(query))
    rows = result.fetchall()

    print(f'\nAll positions in Rollover_IRA on 2026-05-13:')
    print(f'Symbol {" "*25} | Day Change')
    print('-' * 50)
    total_all = 0
    total_excl_cash = 0
    for row in rows:
        symbol, day_chng = row
        print(f'{symbol:30} | {day_chng:10.2f}')
        total_all += day_chng if day_chng else 0
        if symbol != 'Cash & Cash Investments':
            total_excl_cash += day_chng if day_chng else 0
    print('-' * 50)
    print(f'Total all positions:   {total_all:10.2f}')
    print(f'Total excl. Cash:      {total_excl_cash:10.2f}')

    print('\n' + '='*80)
    print('Checking all accounts on 2026-05-13:')
    print('='*80)

    query2 = '''
    SELECT account, SUM(day_chng_dollar) as total_all,
           SUM(CASE WHEN symbol != 'Cash & Cash Investments' THEN day_chng_dollar ELSE 0 END) as total_excl_cash
    FROM hist_cs
    WHERE snapshot_date = '2026-05-13'
    GROUP BY account
    ORDER BY account
    '''
    result2 = conn.execute(text(query2))
    rows2 = result2.fetchall()

    print(f'Account {" "*40} | Total All | Total Excl Cash')
    print('-' * 80)
    grand_total_excl_cash = 0
    for row in rows2:
        account, total_all, total_excl = row
        print(f'{account:45} | {total_all:9.2f} | {total_excl:15.2f}')
        grand_total_excl_cash += total_excl if total_excl else 0
    print('-' * 80)
    print(f'{"GRAND TOTAL (excl cash)":45} | {grand_total_excl_cash:9.2f}')
