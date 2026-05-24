"""Re-derive drv_actionable for one date in a FRESH process.

This bypasses the running API server / scheduler entirely, so it is guaranteed
to execute the CURRENT etl/derive_actionable.py (case-insensitive category
lookup). It then reports Min coverage per category.

Run from the project root:  python _rederive_actionable.py [YYYY-MM-DD]
Delete this file when we're done.
"""
import sys
from datetime import date

from sqlalchemy import text

from etl.db import session_scope
from etl.derive_actionable import derive_actionable

D = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date.today()

print("Re-deriving drv_actionable for %s  (fresh process)..." % D)
with session_scope() as s:
    n = derive_actionable(s, D)
print("  derive_actionable returned %d rows" % n)

with session_scope() as s:
    rows = s.execute(text("""
        SELECT position_category, COUNT(*) n, COUNT(target_min_dollar) with_min
        FROM drv_actionable
        WHERE as_of_date = :d AND consolidated_action IS NOT NULL
        GROUP BY 1 ORDER BY 2 DESC
    """), {"d": D}).fetchall()

print("\nAction rows by category  (with_min should equal n):")
ok = True
for r in rows:
    blank = (r[1] or 0) - (r[2] or 0)
    if blank:
        ok = False
    flag = "" if blank == 0 else ("   <-- %d STILL BLANK" % blank)
    print("  %-24r rows=%-4d with_min=%-4d%s" % (r[0], r[1], r[2], flag))

print()
print("RESULT: every action row has Min/Max/Units."
      if ok else "RESULT: some action rows are still blank (real code issue).")
