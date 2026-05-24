from etl.db import session_scope
from sqlalchemy import text
with session_scope() as s:
    rows = s.execute(text("""
        SELECT logged_at, log_level, message
        FROM meta_scheduler_log
        WHERE logged_at > now() - interval '5 minutes'
        ORDER BY logged_at ASC
    """)).fetchall()
for r in rows:
    print(f"{r[0].strftime('%H:%M:%S')} [{r[1]}] {r[2][:200]}")
