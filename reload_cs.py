from etl.db import session_scope
from etl.load_raw import load_cs_positions_csv
from pathlib import Path

file_path = r"C:\Ashok\Investing\Stocks\CS\Archive\CS 2026-05-27.csv"
source_file = Path(file_path).name

with session_scope() as session:
    try:
        rows_read, rows_inserted, rows_skipped = load_cs_positions_csv(session, file_path, source_file)
        print(f"CS File Result:")
        print(f"  Rows read: {rows_read}")
        print(f"  Rows inserted: {rows_inserted}")
        print(f"  Rows skipped: {rows_skipped}")
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
