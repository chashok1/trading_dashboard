"""Rebuild drv_actionable for the latest 5 dates."""
from config.settings import settings
from sqlalchemy import create_engine, text
from etl.db import session_scope
from etl.derive_outlook_action import derive_outlook_action
from etl.derive_actionable import derive_actionable
from datetime import datetime

engine = create_engine(settings.sqlalchemy_url)

# Get the last 5 distinct dates from drv_dash
with session_scope() as s:
    rows = s.execute(text("""
        SELECT DISTINCT as_of_date FROM drv_dash
        ORDER BY as_of_date DESC LIMIT 5
    """)).fetchall()

dates_to_rebuild = [r[0] for r in rows]
print(f"Rebuilding drv_actionable for {len(dates_to_rebuild)} date(s):")

rebuilt = []
for d in dates_to_rebuild:
    print(f"\n  {d}...")
    entry = {"date": d.isoformat(), "ok": False, "rows_outlook": 0, "rows_actionable": 0, "error": None}
    try:
        with session_scope() as s:
            entry["rows_outlook"] = derive_outlook_action(s, d, None)
            entry["rows_actionable"] = derive_actionable(s, d)
            entry["ok"] = True
        print(f"    OK: {entry['rows_outlook']} outlook, {entry['rows_actionable']} actionable")
    except Exception as e:
        entry["error"] = str(e)[:200]
        print(f"    ERROR: {entry['error']}")
    rebuilt.append(entry)

# Summary
ok_count = sum(1 for r in rebuilt if r["ok"])
print(f"\nSummary: {ok_count}/{len(rebuilt)} dates rebuilt successfully")

if ok_count == len(rebuilt):
    print("\n[SUCCESS] drv_actionable is now up-to-date!")
else:
    print("\n[WARNING] Some dates failed. Review errors above.")
