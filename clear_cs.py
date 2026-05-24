from etl.db import session_scope
from sqlalchemy import text

with session_scope() as s:
    s.execute(text('DELETE FROM meta_file_processed WHERE file_path LIKE :p'),
              {'p': '%CS 2026-05-13%'})
    s.execute(text('DELETE FROM hist_cs WHERE snapshot_date = :d'),
              {'d': '2026-05-13'})
    s.commit()
    print('Cleared CS 2026-05-13 for reprocessing')
