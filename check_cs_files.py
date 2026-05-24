from config.settings import settings
from etl.db import session_scope
from sqlalchemy import text
from datetime import date

with session_scope() as s:
    today = date.today()

    # Check CS in ref_load_files
    ref = s.execute(text(
        "SELECT file_type, week_day, enabled, optional FROM ref_load_files WHERE file_type = 'CS'"
    )).first()

    if ref:
        print(f"CS Schedule in ref_load_files:")
        print(f"  file_type: {ref[0]}")
        print(f"  week_day: {ref[1]}")
        print(f"  enabled: {ref[2]}")
        print(f"  optional: {ref[3]}")
    else:
        print("CS not found in ref_load_files!")

    print(f"\nCS Files in meta_file_processed (today={today}):")
    meta = s.execute(text("""
        SELECT file_path, file_date, processed_at
        FROM meta_file_processed
        WHERE file_type = 'CS'
        ORDER BY processed_at DESC
        LIMIT 5
    """)).fetchall()

    if meta:
        for file_path, file_date, processed_at in meta:
            is_today = "[TODAY]" if file_date == today else f"[{file_date}]"
            print(f"  {file_path.split(chr(92))[-1]}")
            print(f"    file_date: {file_date} {is_today}")
    else:
        print("  NO CS files found in meta_file_processed!")

    # Check if CS files are scheduled for today
    import datetime
    dow = datetime.date.today().weekday()  # 0=Mon, 4=Fri
    print(f"\nToday is: {['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'][dow]}")
    if ref and ref[1] == 'WKDAY':
        print(f"CS is scheduled for WKDAY - should show if file_date >= today")
