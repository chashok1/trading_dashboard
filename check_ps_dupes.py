from sqlalchemy import text
from etl.db import session_scope

with session_scope() as s:
    print("PS in ref_load_files:")
    result = s.execute(text("""
        SELECT file_type, target_tab, week_day FROM ref_load_files
        WHERE LOWER(file_type) = 'ps'
        ORDER BY file_type
    """)).fetchall()
    print(f"  Found {len(result)} entries:")
    for row in result:
        print(f"    - file_type='{row[0]}', target_tab='{row[1]}', week_day='{row[2]}'")

    print("\nPS in meta_file_processed:")
    result = s.execute(text("""
        SELECT DISTINCT file_type FROM meta_file_processed
        WHERE LOWER(file_type) = 'ps'
    """)).fetchall()
    print(f"  Found {len(result)} distinct file_types:")
    for (ft,) in result:
        print(f"    - '{ft}'")

    print("\nPS in meta_etl_run:")
    result = s.execute(text("""
        SELECT DISTINCT file_type FROM meta_etl_run
        WHERE LOWER(file_type) = 'ps'
    """)).fetchall()
    print(f"  Found {len(result)} distinct file_types:")
    for (ft,) in result:
        print(f"    - '{ft}'")
