import csv

input_file = r"C:\Ashok\Investing\Stocks\CS\Archive\CS 2026-05-13.csv"

with open(input_file, 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)

    print("CSV column names:")
    for i, col in enumerate(reader.fieldnames):
        print(f"  {i}: {repr(col)}")

    print("\nFirst 3 rows:")
    for i, row in enumerate(reader):
        if i >= 3:
            break
        print(f"\nRow {i}:")
        for key, val in row.items():
            if val and val.strip():
                print(f"  {key}: {repr(val)}")
