"""
Migrate ref_quad_periods from (period_type, start_date) PK
to (period_type, year, period_num) — standard calendar key.

Run once after applying db/baseline.sql:
    python -m db.migrate_quad_periods_v2
"""
import sys
sys.path.insert(0, '.')
from etl.db import session_scope
from sqlalchemy import text


def run():
    with session_scope() as s:
        cols = {r[0] for r in s.execute(text(
            "SELECT column_name FROM information_schema.columns"
            " WHERE table_name='ref_quad_periods'"
        )).fetchall()}

        if 'start_date' not in cols:
            print("ref_quad_periods: already on new schema — nothing to do.")
            return

        print("Step 1: add year/period_num columns...")
        s.execute(text("ALTER TABLE ref_quad_periods ADD COLUMN IF NOT EXISTS year INT"))
        s.execute(text("ALTER TABLE ref_quad_periods ADD COLUMN IF NOT EXISTS period_num INT"))

        print("Step 2: populate year/period_num from start_date...")
        s.execute(text(
            "UPDATE ref_quad_periods"
            " SET year = EXTRACT(year FROM start_date)::INT,"
            "     period_num = EXTRACT(month FROM start_date)::INT"
            " WHERE period_type='monthly' AND year IS NULL"
        ))
        s.execute(text(
            "UPDATE ref_quad_periods"
            " SET year = EXTRACT(year FROM start_date)::INT,"
            "     period_num = CEIL(EXTRACT(month FROM start_date)/3.0)::INT"
            " WHERE period_type='quarterly' AND year IS NULL"
        ))

        print("Step 3: set NOT NULL on year, period_num...")
        s.execute(text(
            "ALTER TABLE ref_quad_periods"
            " ALTER COLUMN year SET NOT NULL,"
            " ALTER COLUMN period_num SET NOT NULL"
        ))

        print("Step 3: remove duplicates on new key (keep lowest ctid)...")
        s.execute(text(
            "DELETE FROM ref_quad_periods a USING ref_quad_periods b"
            " WHERE a.ctid > b.ctid"
            " AND a.period_type=b.period_type"
            " AND a.year=b.year AND a.period_num=b.period_num"
        ))

        print("Step 4: swap primary key...")
        s.execute(text(
            "ALTER TABLE ref_quad_periods"
            " DROP CONSTRAINT ref_quad_periods_pkey"
        ))
        s.execute(text(
            "ALTER TABLE ref_quad_periods"
            " ADD PRIMARY KEY (period_type, year, period_num)"
        ))

        print("Step 5: drop start_date and end_date...")
        s.execute(text(
            "ALTER TABLE ref_quad_periods"
            " DROP COLUMN IF EXISTS start_date,"
            " DROP COLUMN IF EXISTS end_date"
        ))

        s.commit()
        print("Migration complete.")


if __name__ == '__main__':
    run()
