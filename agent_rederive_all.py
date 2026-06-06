"""Re-derive the full cascade for 2026-06-04 in a fresh process, so the
refactored composite firing (_atomic_member_weight / _composite_fire, now shared
by drv_stks and drv_trig) takes effect for BOTH tables.

Run:  python agent_rederive_all.py
"""
from datetime import date

from etl.db import session_scope
from etl.derive import derive_all

D = date(2026, 6, 4)
with session_scope() as s:
    counts = derive_all(s, D)

print(f"derive_all done for {D}")
for k in ("drv_cat_atomic_input", "drv_stks", "drv_trig", "drv_actionable"):
    print(f"  {k}: {counts.get(k)}")
