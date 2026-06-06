"""Re-derive the full cascade for 2026-06-05 in a fresh process, so the
updated composite firing (nested-composite gating fix in drv_stks + nested
support in drv_trig) takes effect for BOTH tables.

Run:  python agent_rederive_all.py
"""
from datetime import date

from etl.db import session_scope
from etl.derive import derive_all

D = date(2026, 6, 5)
with session_scope() as s:
    counts = derive_all(s, D)

print(f"derive_all done for {D}")
for k in ("drv_cat_atomic_input", "drv_stks", "drv_trig", "drv_actionable"):
    print(f"  {k}: {counts.get(k)}")
