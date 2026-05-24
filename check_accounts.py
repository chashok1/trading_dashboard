import csv
from collections import defaultdict

with open(r'C:\Ashok\Investing\Stocks\CS\Archive\CS 2026-05-13.csv', 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    accounts = defaultdict(list)

    for row in reader:
        section = row.get('Section', '').strip()
        symbol = row.get('Symbol', '').strip()

        # Skip summary/header rows
        if symbol in ['Cash & Cash Investments', 'Positions Total', '--', '']:
            continue

        accounts[section].append(symbol)

print('Accounts with holdings:')
for section in sorted(accounts.keys()):
    positions = accounts[section]
    print(f'\n{section}')
    print(f'  {len(positions)} positions: {", ".join(sorted(set(positions))[:5])}...')
