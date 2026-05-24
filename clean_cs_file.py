import csv
import re

input_file = r"C:\Ashok\Invest\Cluade\CS 2026-05-13.csv"
output_file = r"C:\Ashok\Invest\Cluade\CS 2026-05-13.csv"

rows_in = []
rows_out = []

# Read with proper CSV handling
with open(input_file, 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    rows_in = list(reader)

print(f"Read {len(rows_in)} data rows")

# Process rows
for row in rows_in:
    section = row.get('Section', '')
    symbol = row.get('Symbol', '')

    # Skip summary total rows and empty symbols, but keep cash positions
    if not symbol or symbol in ['--', 'Positions Total', '']:
        continue

    # Use full section name as account (e.g., "Designated_Bene_Individual ...254")
    account = section

    # Create new row with proper column names
    new_row = {
        'Date': row.get('Date', ''),
        'Account': account,
        'Symbol': symbol,
        'Description': row.get('Description', ''),
        'Qty (Quantity)': row.get('Qty (Quantity)', ''),
        'Price': row.get('Price', ''),
        'Mkt Val (Market Value)': row.get('Mkt Val (Market Value)', ''),
        'Price Chng $ (Price Change $)': row.get('Price Chng $ (Price Change $)', ''),
        'Price Chng % (Price Change %)': row.get('Price Chng % (Price Change %)', ''),
        'Day Chng $ (Day Change $)': row.get('Day Chng $ (Day Change $)', ''),
        'Day Chng % (Day Change %)': row.get('Day Chng % (Day Change %)', ''),
        'Cost Basis': row.get('Cost Basis', ''),
        'Gain $ (Gain/Loss $)': row.get('Gain $ (Gain/Loss $)', ''),
        'Gain % (Gain/Loss %)': row.get('Gain % (Gain/Loss %)', ''),
        'Reinvest?': row.get('Reinvest?', ''),
        'Reinvest Capital Gains?': row.get('Reinvest Capital Gains?', ''),
        'Security Type': row.get('Asset Type', ''),
    }
    rows_out.append(new_row)

print(f"After filtering: {len(rows_out)} rows")

# Write output
fieldnames = [
    'Date', 'Account', 'Symbol', 'Description', 'Qty (Quantity)', 'Price',
    'Mkt Val (Market Value)', 'Price Chng $ (Price Change $)', 'Price Chng % (Price Change %)',
    'Day Chng $ (Day Change $)', 'Day Chng % (Day Change %)', 'Cost Basis',
    'Gain $ (Gain/Loss $)', 'Gain % (Gain/Loss %)', 'Reinvest?',
    'Reinvest Capital Gains?', 'Security Type'
]

with open(output_file, 'w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows_out)

print(f"Wrote {len(rows_out)} cleaned rows")

# Show sample
if rows_out:
    print("\nSample rows:")
    for row in rows_out[:3]:
        print(f"  {row['Date']} | Acct:{row['Account']} | {row['Symbol']} | {row['Mkt Val (Market Value)']}")
