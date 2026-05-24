#!/usr/bin/env python3
"""Apply sale tracking columns to hist_f and hist_cs tables."""
from etl.db import session_scope
from sqlalchemy import text

def apply_columns():
    with session_scope() as s:
        # Add columns to hist_cs
        print("Adding columns to hist_cs...")
        s.execute(text("ALTER TABLE hist_cs ADD COLUMN IF NOT EXISTS sold_date DATE"))
        s.execute(text("ALTER TABLE hist_cs ADD COLUMN IF NOT EXISTS shares_sold NUMERIC"))
        s.execute(text("ALTER TABLE hist_cs ADD COLUMN IF NOT EXISTS realized_gain_dollar NUMERIC"))
        s.execute(text("ALTER TABLE hist_cs ADD COLUMN IF NOT EXISTS realized_gain_pct NUMERIC"))
        s.commit()
        print("[OK] hist_cs columns added")

        # Add columns to hist_f
        print("Adding columns to hist_f...")
        s.execute(text("ALTER TABLE hist_f ADD COLUMN IF NOT EXISTS sold_date DATE"))
        s.execute(text("ALTER TABLE hist_f ADD COLUMN IF NOT EXISTS shares_sold NUMERIC"))
        s.execute(text("ALTER TABLE hist_f ADD COLUMN IF NOT EXISTS realized_gain_dollar NUMERIC"))
        s.execute(text("ALTER TABLE hist_f ADD COLUMN IF NOT EXISTS realized_gain_pct NUMERIC"))
        s.commit()
        print("[OK] hist_f columns added")

        # Verify
        from sqlalchemy import inspect
        engine = s.get_bind()
        cs_cols = [c['name'] for c in inspect(engine).get_columns('hist_cs')]
        f_cols = [c['name'] for c in inspect(engine).get_columns('hist_f')]

        print(f"\nhist_cs has sold_date: {'sold_date' in cs_cols}")
        print(f"hist_f has sold_date: {'sold_date' in f_cols}")

if __name__ == "__main__":
    apply_columns()
