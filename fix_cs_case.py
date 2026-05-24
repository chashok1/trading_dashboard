from config.settings import settings
from etl.db import session_scope
from sqlalchemy import text

with session_scope() as s:
    # Check exact file types
    print("Checking file_type cases...")

    ref_result = s.execute(text(
        "SELECT file_type FROM ref_load_files WHERE LOWER(file_type) = 'cs'"
    )).first()

    meta_result = s.execute(text(
        "SELECT DISTINCT file_type FROM meta_file_processed WHERE LOWER(file_type) = 'cs'"
    )).first()

    print(f"ref_load_files:      '{ref_result[0] if ref_result else 'NOT FOUND'}'")
    print(f"meta_file_processed: '{meta_result[0] if meta_result else 'NOT FOUND'}'")

    if ref_result and meta_result and ref_result[0] != meta_result[0]:
        print(f"\nCASE MISMATCH FOUND: '{ref_result[0]}' vs '{meta_result[0]}'")
        print(f"Fixing: {ref_result[0]} -> {meta_result[0]}")

        s.execute(text(f"""
            UPDATE ref_load_files
            SET file_type = '{meta_result[0]}'
            WHERE file_type = '{ref_result[0]}'
        """))
        s.commit()
        print("FIXED!")
    elif ref_result == meta_result:
        print("\nNo case mismatch - cases match!")
    else:
        print("\nNote: May need to check data loading")
