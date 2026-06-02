import sys; sys.path.insert(0, ".")
from datetime import date
from etl.db import session_scope
from etl.derive import derive_stks
from etl.derive_actionable import derive_actionable

d = date(2026, 6, 2)

with session_scope() as s:
    n = derive_stks(s, d, None)
    s.commit()
print("derive_stks:", n, "rows")

with session_scope() as s:
    n = derive_actionable(s, d, None)
    s.commit()
print("derive_actionable:", n, "rows")
