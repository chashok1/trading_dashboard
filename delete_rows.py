from etl.db import session_scope
from sqlalchemy import text

with session_scope() as session:
    # Delete hist_tw for 2026-05-27
    tw_deleted = session.execute(text("DELETE FROM hist_tw WHERE snapshot_date = '2026-05-27'")).rowcount
    session.commit()

    # Delete hist_cs for 2026-05-27
    cs_deleted = session.execute(text("DELETE FROM hist_cs WHERE snapshot_date = '2026-05-27'")).rowcount
    session.commit()

    print(f"Deleted {tw_deleted} rows from hist_tw")
    print(f"Deleted {cs_deleted} rows from hist_cs")
