from etl.db import session_scope
from etl.derive import derive_all
from datetime import date

as_of_date = date(2026, 5, 27)

with session_scope() as session:
    try:
        print(f"Running derive for {as_of_date}...")
        result = derive_all(session, as_of_date)
        print(f"Derive completed successfully!")
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
