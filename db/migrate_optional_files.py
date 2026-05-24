"""
One-time migration: add optional column to ref_load_files.
Run once from the project root:
    python -m db.migrate_optional_files
"""
from etl.db import session_scope
from sqlalchemy import text

def main():
    with session_scope() as s:
        s.execute(text("""
            ALTER TABLE ref_load_files
            ADD COLUMN IF NOT EXISTS optional BOOLEAN DEFAULT FALSE
        """))
        s.commit()
        print("Column added (or already exists).")

        # Mark optional file types
        result = s.execute(text("""
            UPDATE ref_load_files
            SET optional = TRUE
            WHERE LOWER(file_type) IN ('iichg', 'f')
            RETURNING file_type
        """))
        updated = [r[0] for r in result.fetchall()]
        s.commit()
        print(f"Marked as optional: {updated}")

        # Show all file types so we can confirm the right names
        rows = s.execute(text("""
            SELECT file_type, week_day, optional
            FROM ref_load_files
            ORDER BY file_type
        """)).fetchall()
        print("\nCurrent ref_load_files:")
        for r in rows:
            print(f"  {r[0]:20s}  week_day={r[1]:10s}  optional={r[2]}")

if __name__ == "__main__":
    main()
