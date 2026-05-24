"""
Print the raw CS CSV exactly as Python's csv reader sees it.
This bypasses every filter/loader so we can confirm whether the file
contains a 'Cash & Cash Investments' row at all.

Run from project root:
    python debug_cs_csv_raw.py
"""
import csv
import os

# Look in standard location first; fall back to most recent file_path in meta_etl_run
candidates = [
    r"C:\Ashok\Investing\Stocks\CS\Archive\CS 2026-05-18.csv",
    r"C:\Ashok\Investing\Stocks\CS\Archive\CS 2026-05-19.csv",
]
path = next((p for p in candidates if os.path.exists(p)), None)
if not path:
    print("ERROR: no CS CSV found in known locations. Edit the script with the right path.")
    raise SystemExit

print(f"File: {path}")
print(f"Size: {os.path.getsize(path)} bytes\n")

with open(path, 'r', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    headers = reader.fieldnames
    print("Headers:")
    for h in headers:
        print(f"  {h!r}")
    print()

    rows = list(reader)
    print(f"Total data rows: {len(rows)}\n")

    print("=== Rows containing 'cash' or 'money' in any field ===")
    hits = 0
    for i, row in enumerate(rows, 1):
        joined = ' '.join(str(v) for v in row.values()).lower()
        if 'cash' in joined or 'money' in joined:
            print(f"\nRow {i}:")
            for k, v in row.items():
                if v not in (None, '', ' '):
                    print(f"  {k!r}: {v!r}")
            hits += 1
    if hits == 0:
        print("  (nothing matches — the file has no cash entry)")

    print("\n=== First 3 data rows (for reference) ===")
    for i, row in enumerate(rows[:3], 1):
        print(f"\nRow {i}:")
        for k, v in row.items():
            print(f"  {k!r}: {v!r}")

    print("\n=== Last 3 data rows ===")
    for i, row in enumerate(rows[-3:], len(rows) - 2):
        print(f"\nRow {i}:")
        for k, v in row.items():
            print(f"  {k!r}: {v!r}")
