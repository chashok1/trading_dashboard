from config.settings import settings
from etl.db import session_scope
from sqlalchemy import text
from etl.etl_load import load_one_file

cs_file = "C:\\Ashok\\Investing\\Stocks\\CS\\Archive\\CS 2026-05-14.csv"

# Step 1: Remove from processed cache
with session_scope() as s:
    s.execute(text("DELETE FROM meta_file_processed WHERE file_path = :p"), {"p": cs_file})
    s.commit()
    print(f"Cleared {cs_file} from processed cache")

# Step 2: Reload the file
print(f"\nReloading {cs_file}...")
result = load_one_file(cs_file, do_derive=False)

print(f"\nLoad result:")
print(f"  Status: {result.get('status')}")
print(f"  File type: {result.get('file_type')}")
print(f"  Target tab: {result.get('target_tab')}")

# Step 3: Check how many rows were inserted
with session_scope() as s:
    count = s.execute(text("""
        SELECT COUNT(*) FROM hist_cs WHERE snapshot_date = '2026-05-14'
    """)).scalar()

    print(f"\nRows now in hist_cs for 2026-05-14: {count}")

    if count > 0:
        print("SUCCESS! CS data for 2026-05-14 is now loaded.")
    else:
        print("Still no data. Need to investigate further.")
