import sys, warnings; sys.path.insert(0, "."); warnings.filterwarnings("ignore")
import openpyxl
from sqlalchemy import text
from etl.db import session_scope

wb = openpyxl.load_workbook("atomic.xlsx", read_only=True, data_only=True)
ws = wb.active
xl_headers = [str(c).strip() if c is not None else "" for c in next(ws.iter_rows(values_only=True))]
wb.close()

with session_scope() as s:
    row = s.execute(text("SELECT * FROM drv_cat_atomic_input LIMIT 1")).mappings().first()
    db_cols = list(row.keys()) if row else []

META = {"as_of_date", "source_run_id", "computed_at", "tos_symbol"}
db_data = [c for c in db_cols if c not in META]
xl_data  = [h for h in xl_headers if h and h != "Symbol"]

print(f"Excel  : {len(xl_headers)} total cols  ({len(xl_data)} data + 1 Symbol)")
print(f"DB     : {len(db_cols)} total cols  ({len(db_data)} data + {len(META)} metadata)")
print(f"Match  : {'YES' if len(xl_data)==len(db_data) else 'NO'}  (Excel data={len(xl_data)}, DB data={len(db_data)})")
print()

from compare_excel import COL_MAP
xl_set = set(xl_data)
db_set = set(db_data)
mapped_xl  = set(COL_MAP.keys())
mapped_db  = set(COL_MAP.values())

xl_not_mapped = xl_set - mapped_xl
db_not_mapped = db_set - mapped_db
xl_no_db      = mapped_xl - xl_set   # in map but not in xl
db_no_xl      = mapped_db - db_set   # in map but not in db

print(f"COL_MAP entries : {len(COL_MAP)}")
print(f"XL cols not in COL_MAP : {sorted(xl_not_mapped) or 'none'}")
print(f"DB cols not in COL_MAP : {sorted(db_not_mapped) or 'none'}")
