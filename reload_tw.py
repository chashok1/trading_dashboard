from etl.db import session_scope
from etl.load_raw import load_tw
from etl.excel_io import open_workbook
from pathlib import Path

file_path = "etl/working/TOSW 2026-05-27.csv"
source_file = Path(file_path).name

with session_scope() as session:
    try:
        wb = open_workbook(file_path)
        rows_read, rows_inserted, rows_skipped = load_tw(session, wb, source_file)
        print(f"TW File Result:")
        print(f"  Rows read: {rows_read}")
        print(f"  Rows inserted: {rows_inserted}")
        print(f"  Rows skipped: {rows_skipped}")
        session.commit()
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
