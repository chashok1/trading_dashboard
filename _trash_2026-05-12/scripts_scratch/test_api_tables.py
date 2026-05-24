#!/usr/bin/env python3
from api.main import DATA_TABLE_DATE_COL
from etl.db import session_scope
from sqlalchemy import text

print(f"Total tables in DATA_TABLE_DATE_COL: {len(DATA_TABLE_DATE_COL)}")
print(f"drv_cat_* tables in dict: {len([k for k in DATA_TABLE_DATE_COL.keys() if k.startswith('drv_cat_')])}")

drv_cat_tables = [k for k in DATA_TABLE_DATE_COL.keys() if k.startswith('drv_cat_')]
print(f"\nDrv_cat_* tables:")
for t in sorted(drv_cat_tables):
    print(f"  {t}")

print("\n\nTesting API logic:")
with session_scope() as s:
    working = []
    failing = []
    for table_name in sorted(drv_cat_tables):
        try:
            count_row = s.execute(text(f"SELECT COUNT(*) FROM {table_name}")).first()
            row_count = count_row[0] if count_row else 0
            working.append((table_name, row_count))
        except Exception as e:
            failing.append((table_name, str(e)))

    print(f"\nWorking ({len(working)}):")
    for name, count in working[:3]:
        print(f"  {name}: {count} rows")
    if len(working) > 3:
        print(f"  ... and {len(working) - 3} more")

    if failing:
        print(f"\nFailing ({len(failing)}):")
        for name, err in failing[:2]:
            print(f"  {name}: {err[:80]}")
