"""Re-derive drv_rr for all dates that have NULL outlook (source='RR' rows).

Needed when drv_rr was last populated before the outlook column was wired into
_derive_rr_impl. Safe to re-run — idempotent per date (DELETE + INSERT).

Run:  python repopulate_drv_rr_outlook.py
"""
import sys
sys.path.insert(0, '.')

from etl.db import session_scope
from etl.derive import _derive_rr_impl
from sqlalchemy import text


def main():
    with session_scope() as session:
        # Find all as_of_dates where source='RR' rows have NULL outlook
        dates = [
            r[0] for r in session.execute(text("""
                SELECT DISTINCT as_of_date
                FROM drv_rr
                WHERE source = 'RR' AND outlook IS NULL
                ORDER BY as_of_date
            """)).fetchall()
        ]

        if not dates:
            print("All drv_rr dates already have outlook populated — nothing to do.")
            return

        print(f"Found {len(dates)} date(s) needing outlook population: {[str(d) for d in dates]}")

        for d in dates:
            n = _derive_rr_impl(session, d, run_id=0)
            after = session.execute(
                text("SELECT COUNT(*) FILTER (WHERE outlook IS NOT NULL) FROM drv_rr WHERE as_of_date = :d"),
                {"d": d}
            ).scalar()
            total = session.execute(
                text("SELECT COUNT(*) FROM drv_rr WHERE as_of_date = :d"),
                {"d": d}
            ).scalar()
            print(f"  {d}: {after}/{total} rows now have outlook")

        session.commit()
        print("Done.")


if __name__ == "__main__":
    main()
