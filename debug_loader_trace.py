"""
Manually re-run the CS CSV loader logic against the file and print exactly
what happens to every row. This tells us which filter is dropping the
'Cash & Cash Investments' rows.

Run from project root:
    python debug_loader_trace.py
"""
import csv
import os
import re
from etl.casters import to_text, to_date

CSV = r"C:\Ashok\Investing\Stocks\CS\Archive\CS 2026-05-18.csv"

_fn = os.path.basename(CSV)
_m = re.search(r'(\d{4})[-_/](\d{1,2})[-_/](\d{1,2})', _fn)
fname_date = None
if _m:
    fname_date = to_date(f"{_m.group(1)}-{int(_m.group(2)):02d}-{int(_m.group(3)):02d}")
print(f"fname_date={fname_date}\n")

n_total = 0
n_kept  = 0
n_skip_sec_or_sym = 0
n_skip_totals     = 0
n_skip_no_date    = 0

print(f"{'i':>3} {'verdict':<14} symbol")
with open(CSV, 'r', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    for i, row in enumerate(reader, 1):
        n_total += 1
        sec = row.get('Section')
        sym_raw = row.get('Symbol')
        dat = row.get('Date')

        if not sec or not sym_raw:
            n_skip_sec_or_sym += 1
            print(f"{i:>3} SKIP no-sec/sym {sym_raw!r}  Section={sec!r}")
            continue

        sym = to_text(sym_raw).strip()
        if sym.lower() in ('positions total', 'total', 'totals'):
            n_skip_totals += 1
            # too noisy; just count
            continue

        snap_date = to_date(dat) if dat else None
        if snap_date is None:
            snap_date = fname_date
        if snap_date is None:
            n_skip_no_date += 1
            print(f"{i:>3} SKIP no-date    {sym!r}  Date={dat!r}")
            continue

        n_kept += 1
        if 'cash' in sym.lower():
            print(f"{i:>3} KEEP CASH       {sym!r}  Date={dat!r}->{snap_date}  Section={sec!r}")

print(f"\nTotals: read={n_total}  kept={n_kept}")
print(f"  skip (Section/Symbol empty): {n_skip_sec_or_sym}")
print(f"  skip (totals row)          : {n_skip_totals}")
print(f"  skip (no date)             : {n_skip_no_date}")
