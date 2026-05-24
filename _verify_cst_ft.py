"""Tiny helper called by activate_cst_ft.bat — prints CST/FT rows."""
import sys
from sqlalchemy import text
from etl.db import session_scope

with session_scope() as s:
    rows = s.execute(text("""
        SELECT file_type, source_dir, week_day,
               COALESCE(TO_CHAR(file_time, 'HH24:MI:SS'), '—') AS ftime,
               enabled, optional
        FROM ref_load_files
        WHERE file_type IN ('CST', 'FT')
        ORDER BY file_type
    """)).all()

for r in rows:
    print(f"  {r[0]:4} {r[1]:45} {r[2]:5} {r[3]} enabled={r[4]} optional={r[5]}")

sys.exit(0 if len(rows) == 2 else 1)
