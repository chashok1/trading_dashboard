"""Diagnostic: trace the PS weekly period logic end to end.

Run from project root:   python check_ps_debug.py [YYYY-MM-DD]
Pick a date inside the PS week that has comparison data, e.g. 2026-05-21.
Safe to delete afterwards.
"""
import sys
from datetime import date

from sqlalchemy import text

from etl.db import session_scope
from etl.derive_outlook_action import (
    _load_anchor_dow, _find_week_period_snapshots, derive_outlook_action,
)
from etl.derive_actionable import derive_actionable

D = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date.today()
print("=" * 60)
print("PS DIAGNOSTIC  --  as_of_date =", D)
print("=" * 60)

with session_scope() as s:
    print("\n[1] hist_ps snapshots (date | rows | non-null rank):")
    for r in s.execute(text(
        "SELECT snapshot_date, COUNT(*), COUNT(rank) FROM hist_ps "
        "GROUP BY snapshot_date ORDER BY snapshot_date DESC LIMIT 10"
    )).fetchall():
        print(f"    {r[0]}   rows={r[1]:<4} rank={r[2]}")

    print("\n[2] ref_load_files PS config:")
    for r in s.execute(text(
        "SELECT file_type, target_tab, target_table, week_day FROM ref_load_files "
        "WHERE target_table = 'hist_ps' OR file_type ILIKE 'ps'"
    )).fetchall():
        print(f"    file_type={r[0]!r} target_tab={r[1]!r} "
              f"target_table={r[2]!r} week_day={r[3]!r}")

    anchor = _load_anchor_dow(s, "hist_ps")
    curr, prev = _find_week_period_snapshots(s, "hist_ps", "snapshot_date", D, anchor)
    print(f"\n[3] _load_anchor_dow -> {anchor}  (PG DOW: 0=Sun..6=Sat)")
    print(f"    _find_week_period_snapshots -> curr_snap={curr}  prev_snap={prev}")

    print("\n[4] holdings overlap with the two snapshots:")
    held = {x[0] for x in s.execute(text(
        "SELECT symbol FROM hist_f WHERE snapshot_date=(SELECT MAX(snapshot_date) FROM hist_f) "
        "GROUP BY symbol HAVING SUM(qty)>0 "
        "UNION SELECT symbol FROM hist_cs WHERE snapshot_date=(SELECT MAX(snapshot_date) FROM hist_cs) "
        "GROUP BY symbol HAVING SUM(qty)>0"
    )).fetchall()}
    for label, snap in (("curr", curr), ("prev", prev)):
        if snap is None:
            print(f"    {label}: (None)")
            continue
        tk = {x[0] for x in s.execute(text(
            "SELECT ticker FROM hist_ps WHERE snapshot_date=:d"
        ), {"d": snap}).fetchall()}
        print(f"    {label} {snap}: {len(tk)} tickers, {len(tk & held)} of them held")

print("\n[5] running derive_outlook_action(", D, ") ...")
try:
    with session_scope() as s:
        n = derive_outlook_action(s, D, None)
    print(f"    OK -> {n} total rows inserted")
except Exception as e:
    print(f"    ERROR: {type(e).__name__}: {e}")

with session_scope() as s:
    print("\n[6] drv_outlook_action PS rows (as_of_date | action | count):")
    for r in s.execute(text(
        "SELECT as_of_date, action, COUNT(*) FROM drv_outlook_action "
        "WHERE source_code='PS' GROUP BY as_of_date, action "
        "ORDER BY as_of_date DESC, action"
    )).fetchall():
        print(f"    {r[0]}   {r[1] or '(none)':<9} {r[2]}")

print("\n[7] running derive_actionable(", D, ") ...")
try:
    with session_scope() as s:
        n = derive_actionable(s, D)
    print(f"    OK -> {n} rows")
except Exception as e:
    print(f"    ERROR: {type(e).__name__}: {e}")

with session_scope() as s:
    print("\n[8] drv_actionable rows where PS is winning source:")
    for r in s.execute(text(
        "SELECT consolidated_action, COUNT(*) FROM drv_actionable "
        "WHERE as_of_date=:d AND winning_source='PS' GROUP BY 1 ORDER BY 2 DESC"
    ), {"d": D}).fetchall():
        print(f"    {r[0] or '(none)':<9} {r[1]}")
print("\ndone.")
