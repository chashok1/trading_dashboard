#!/usr/bin/env python3
import sys
sys.path.insert(0, '.')

# Force reload
import importlib
if 'api.main' in sys.modules:
    del sys.modules['api.main']

from api.main import DATA_TABLE_DATE_COL

print(f"DATA_TABLE_DATE_COL has {len(DATA_TABLE_DATE_COL)} entries")
print(f"drv_cat_* entries: {len([k for k in DATA_TABLE_DATE_COL if k.startswith('drv_cat_')])}")

# Show the raw dict items in order
print("\nAll entries (sorted):")
for k, v in sorted(DATA_TABLE_DATE_COL.items()):
    print(f"  {k}: {v}")
