#!/usr/bin/env python3
import csv

csv_path = r'C:\Ashok\Invest\Cluade\CS 2026-05-13.csv'
try:
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f'Total rows in CSV: {len(rows)}')
    print()

    # Find CAVA row
    cava_rows = [r for r in rows if 'CAVA' in r.get('Symbol', '')]

    if cava_rows:
        print('CAVA rows in CSV:')
        for r in cava_rows:
            symbol = r.get('Symbol')
            qty = r.get('Quantity')
            price = r.get('Price')
            day_chng = r.get('Day Change Dollar')
            account = r.get('Account')
            print(f'  Symbol: {symbol}')
            print(f'  Account: {account}')
            print(f'  Qty: {qty}')
            print(f'  Price: {price}')
            print(f'  Day Change Dollar: {day_chng}')
            print()
    else:
        print('No CAVA found in CSV')

    # Show all rows with their day change
    print('All positions with their Day Change Dollar:')
    print('-' * 60)
    total_day_chng = 0
    for r in rows:
        symbol = r.get('Symbol', '')
        day_chng_str = r.get('Day Change Dollar', '')
        account = r.get('Account', '')
        if symbol and symbol != 'Totals':
            try:
                day_chng = float(day_chng_str) if day_chng_str else 0
                total_day_chng += day_chng
                print(f'{symbol:20} | {day_chng:10.2f} | {account}')
            except ValueError:
                print(f'{symbol:20} | {day_chng_str:10} | {account}')

    print('-' * 60)
    print(f'Total Day Change: {total_day_chng:.2f}')

except FileNotFoundError:
    print(f'File not found: {csv_path}')
