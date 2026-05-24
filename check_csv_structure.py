#!/usr/bin/env python3
import csv

csv_path = r'C:\Ashok\Invest\Cluade\CS 2026-05-13.csv'
with open(csv_path, 'r', encoding='utf-8') as f:
    # Read raw first few lines to see structure
    lines = []
    for i in range(5):
        lines.append(f.readline())

print('Raw CSV lines:')
for i, line in enumerate(lines):
    print(f'Line {i}: {repr(line[:120])}')

print('\n' + '='*80)

# Now parse with csv.DictReader
with open(csv_path, 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    headers = reader.fieldnames

    print(f'CSV Headers ({len(headers)} total):')
    for i, h in enumerate(headers):
        print(f'  {i:2}: {repr(h)}')

    print('\n' + '='*80)
    print('Looking for CAVA row:')

    # Get first CAVA row
    for row in reader:
        if 'CAVA' in str(row.get('Symbol', '')):
            print('CAVA row:')
            for h in headers:
                val = row.get(h)
                if val:
                    print(f'  {h:30} = {repr(val)}')
            break
