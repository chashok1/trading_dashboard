from etl.db import session_scope
from sqlalchemy import text

with session_scope() as session:
    # Check what file types are configured
    result = session.execute(text("""
        SELECT file_type, source_dir FROM ref_load_files
        WHERE file_type ILIKE '%CS%' OR file_type ILIKE '%schwab%'
    """)).fetchall()
    print('CS file types configured:')
    for row in result:
        print(f'  {row[0]}: {row[1]}')
