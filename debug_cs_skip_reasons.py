"""
Look at the skip_reasons JSON for recent CS loads.
Reveals if the cash row was dropped by the validity gate (missing PK column).

Run from project root:
    python debug_cs_skip_reasons.py
"""
from sqlalchemy import create_engine, text
from config.settings import settings

eng = create_engine(settings.sqlalchemy_url)

with eng.connect() as c:
    rows = c.execute(text("""
        SELECT run_id, file_path, file_type, target_tab,
               rows_read, rows_inserted, rows_skipped,
               skip_reasons,
               started_at, finished_at
          FROM meta_etl_run
         WHERE file_type = 'CS'
         ORDER BY started_at DESC
         LIMIT 5
    """)).all()
    for r in rows:
        print(f"\nrun={r.run_id}  file={r.file_path}")
        print(f"  read={r.rows_read} ins={r.rows_inserted} skp={r.rows_skipped}")
        print(f"  skip_reasons={r.skip_reasons}")
        print(f"  start={r.started_at}  end={r.finished_at}")
