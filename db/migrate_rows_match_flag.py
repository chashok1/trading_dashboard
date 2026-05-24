"""
Migration: add rows_should_match column to ref_load_files.
Indicates whether current and previous row counts should match.
Defaults to TRUE for files with consistent row counts.

Run once from the project root:
    python -m db.migrate_rows_match_flag
"""
from etl.db import session_scope
from sqlalchemy import text

def main():
    with session_scope() as s:
        s.execute(text("""
            ALTER TABLE ref_load_files
            ADD COLUMN IF NOT EXISTS rows_should_match BOOLEAN DEFAULT TRUE
        """))
        s.commit()
        print("Column added (or already exists).")

        # Files with variable row counts: set to FALSE
        # etfchg, iichg: weekly update files with variable counts
        result = s.execute(text("""
            UPDATE ref_load_files
            SET rows_should_match = FALSE
            WHERE LOWER(file_type) IN ('etfchg', 'iichg')
            RETURNING file_type
        """))
        updated = [r[0] for r in result.fetchall()]
        s.commit()
        print(f"Marked as rows_should_NOT_match: {updated}")

        # Show all file types
        rows = s.execute(text("""
            SELECT file_type, week_day, rows_should_match
            FROM ref_load_files
            ORDER BY file_type
        """)).fetchall()
        print("\nCurrent ref_load_files:")
        for r in rows:
            match_flag = "✓ match" if r[2] else "✗ variable"
            print(f"  {r[0]:20s}  week_day={r[1]:10s}  {match_flag}")

if __name__ == "__main__":
    main()
