"""
Direct migration: swap ref_load_files PK from (file_type, week_day, file_time)
to (file_type) only.

The DO block in baseline.sql wasn't getting executed (init_db swallows it or
it silently no-ops). This script runs the migration in its own transaction so
you can see exactly what happens.

Safe to re-run — checks current PK state and only acts if it's the old form.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import text
from etl.db import session_scope


def main():
    print("=" * 70)
    print("Migrating ref_load_files PK: (file_type, week_day, file_time) → (file_type)")
    print("=" * 70)

    with session_scope() as s:
        # Current PK?
        rows = s.execute(text("""
            SELECT kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
            WHERE tc.table_name = 'ref_load_files'
              AND tc.constraint_type = 'PRIMARY KEY'
            ORDER BY kcu.ordinal_position
        """)).all()
        pk_cols = [r[0] for r in rows]
        print(f"\nCurrent PK: {pk_cols}")

        if pk_cols == ['file_type']:
            print("Already migrated — nothing to do.")
            return 0

        if 'file_time' not in pk_cols:
            print(f"Unexpected PK shape: {pk_cols}. Aborting.")
            return 1

        # Step 1: are there duplicate file_types that would break a single-col PK?
        dups = s.execute(text("""
            SELECT file_type, COUNT(*) AS n
            FROM ref_load_files GROUP BY file_type HAVING COUNT(*) > 1
            ORDER BY n DESC
        """)).all()

        if dups:
            print(f"\nFound {len(dups)} duplicate file_type values:")
            for row in dups:
                print(f"  {row[0]}: {row[1]} rows")
            print("\nDedup: keeping the most recently loaded row per file_type")

            n_deleted = s.execute(text("""
                DELETE FROM ref_load_files WHERE ctid IN (
                    SELECT ctid FROM (
                        SELECT ctid,
                               ROW_NUMBER() OVER (
                                   PARTITION BY file_type
                                   ORDER BY loaded_at DESC NULLS LAST, ctid DESC
                               ) AS rn
                        FROM ref_load_files
                    ) d WHERE d.rn > 1
                )
            """)).rowcount
            print(f"  Deleted {n_deleted} duplicate rows")
        else:
            print("\nNo duplicate file_types — dedup step skipped")

        # Step 2: swap the PK
        print("\nDropping old composite PK ...")
        s.execute(text("ALTER TABLE ref_load_files DROP CONSTRAINT ref_load_files_pkey"))
        print("Adding new single-column PK ...")
        s.execute(text("ALTER TABLE ref_load_files ADD PRIMARY KEY (file_type)"))
        s.commit()

        # Confirm
        rows = s.execute(text("""
            SELECT kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
            WHERE tc.table_name = 'ref_load_files'
              AND tc.constraint_type = 'PRIMARY KEY'
            ORDER BY kcu.ordinal_position
        """)).all()
        new_pk = [r[0] for r in rows]
        total = s.execute(text("SELECT COUNT(*) FROM ref_load_files")).scalar()

    print(f"\nNew PK: {new_pk}")
    print(f"Rows remaining: {total}")
    if new_pk == ['file_type']:
        print("\n✓ Migration complete. The Ref Data UI can now edit file_time + week_day inline.")
        return 0
    else:
        print(f"\n✗ Migration didn't end with the expected PK: {new_pk}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
