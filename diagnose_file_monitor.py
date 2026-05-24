"""
Diagnose why File Monitor is showing blank grids, and auto-recover.

Runs five checks against the live database:
  1. ref_load_files — should have ~17 rows (your watch list)
  2. meta_file_processed — should have hundreds/thousands of rows
  3. meta_etl_run — should have recent rows
  4. /api/monitor/schedule shape — simulates the query the screen runs
  5. Current PK on ref_load_files — confirms the migration succeeded

If ref_load_files is empty, the script offers to re-populate from
LoadFiles.xlsx. All other empty tables are reported but not auto-fixed —
that's data you'd want to investigate manually.

Usage:
    .venv\\Scripts\\activate
    python diagnose_file_monitor.py
    python diagnose_file_monitor.py --auto-recover   # auto-yes to re-populate
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sqlalchemy import text
from etl.db import session_scope
from config.settings import settings


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--auto-recover", action="store_true",
                    help="Skip the y/n prompt and re-populate ref_load_files automatically")
    args = ap.parse_args()

    print("=" * 70)
    print("FILE MONITOR DIAGNOSTIC")
    print("=" * 70)

    issues = []
    can_recover = False

    with session_scope() as s:
        # ---- Check 1: ref_load_files ----
        try:
            row = s.execute(text("""
                SELECT COUNT(*) AS total,
                       COUNT(DISTINCT file_type) AS distinct_types,
                       COUNT(*) FILTER (WHERE enabled = TRUE) AS enabled_count
                FROM ref_load_files
            """)).first()
            total, distinct, enabled = row
            print(f"\n[1] ref_load_files: total={total}, distinct_types={distinct}, enabled={enabled}")
            if total == 0:
                issues.append("ref_load_files is EMPTY — File Monitor will show no schedule rows")
                can_recover = True
            elif enabled == 0:
                issues.append("ref_load_files has rows but ALL are disabled — schedule will be empty")
            else:
                print(f"    Sample (first 5):")
                rows = s.execute(text("""
                    SELECT file_type, week_day, file_time, source_dir, enabled
                    FROM ref_load_files
                    ORDER BY file_type LIMIT 5
                """)).all()
                for r in rows:
                    print(f"      {r[0]:8} {r[1]:6} {str(r[2] or '-'):10} {r[3]}  enabled={r[4]}")
        except Exception as e:
            issues.append(f"ref_load_files query failed: {e}")

        # ---- Check 2: meta_file_processed ----
        try:
            row = s.execute(text("""
                SELECT COUNT(*) AS total, MAX(processed_at) AS most_recent
                FROM meta_file_processed
            """)).first()
            total, latest = row
            print(f"\n[2] meta_file_processed: total={total}, latest={latest}")
            if total == 0:
                print("    (empty — nothing's been loaded yet; this is fine on a fresh DB)")
        except Exception as e:
            issues.append(f"meta_file_processed query failed: {e}")

        # ---- Check 3: meta_etl_run ----
        try:
            row = s.execute(text("""
                SELECT COUNT(*) AS total,
                       COUNT(*) FILTER (WHERE status = 'error') AS errors,
                       MAX(started_at) AS most_recent
                FROM meta_etl_run
            """)).first()
            total, errors, latest = row
            print(f"\n[3] meta_etl_run: total={total}, errors={errors}, latest={latest}")
        except Exception as e:
            issues.append(f"meta_etl_run query failed: {e}")

        # ---- Check 4: schedule endpoint shape ----
        try:
            row = s.execute(text("""
                WITH today AS (SELECT CURRENT_DATE AS d),
                is_today AS (
                    SELECT r.file_type FROM ref_load_files r, today t
                    WHERE r.enabled = TRUE
                      AND (
                          r.week_day = 'WKDAY' AND EXTRACT(DOW FROM t.d) BETWEEN 1 AND 5 OR
                          r.week_day = 'SUN'   AND EXTRACT(DOW FROM t.d) = 0 OR
                          r.week_day = 'MON'   AND EXTRACT(DOW FROM t.d) = 1 OR
                          r.week_day = 'TUE'   AND EXTRACT(DOW FROM t.d) = 2 OR
                          r.week_day = 'WED'   AND EXTRACT(DOW FROM t.d) = 3 OR
                          r.week_day = 'THU'   AND EXTRACT(DOW FROM t.d) = 4 OR
                          r.week_day = 'FRI'   AND EXTRACT(DOW FROM t.d) = 5 OR
                          r.week_day = 'SAT'   AND EXTRACT(DOW FROM t.d) = 6 OR
                          r.week_day = 'ALL'
                      )
                )
                SELECT COUNT(*) AS expected_today FROM is_today
            """)).scalar() or 0
            print(f"\n[4] is_today (rows the schedule would show for {sys.argv[0]} today): {row}")
            total_rows = s.execute(text("SELECT COUNT(*) FROM ref_load_files")).scalar() or 0
            if row == 0 and total_rows > 0:
                issues.append(f"is_today CTE returned 0 rows even though ref_load_files has {total_rows}. "
                              "Likely no row matches today's day-of-week (e.g., all your file types "
                              "are scheduled WKDAY and today is a weekend).")
        except Exception as e:
            issues.append(f"schedule simulation failed: {e}")

        # ---- Check 5: PK structure ----
        try:
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
            print(f"\n[5] ref_load_files PK columns: {pk_cols}")
            if pk_cols == ['file_type']:
                print("    OK — new single-column PK active")
            elif 'file_time' in pk_cols:
                issues.append(f"Migration didn't complete — PK is still composite: {pk_cols}. "
                              "Re-run `python -m db.init_db`.")
        except Exception as e:
            issues.append(f"PK check failed: {e}")

    # ---- Summary + recovery ----
    print("\n" + "=" * 70)
    if not issues:
        print("✓ Diagnostic clean — File Monitor should be showing data.")
        print("  If the screen is still blank, hard-refresh the browser (Ctrl+F5),")
        print("  or open DevTools → Network and look at /api/monitor/schedule.")
        return 0

    print(f"✗ {len(issues)} issue(s) found:")
    for i, msg in enumerate(issues, 1):
        print(f"  {i}. {msg}")

    if not can_recover:
        print("\nNo auto-recovery available for these issues. Investigate above.")
        return 1

    # Auto-recover path
    print("\n" + "=" * 70)
    print("RECOVERY: re-populate ref_load_files from LoadFiles.xlsx")
    print("=" * 70)

    lf = settings.loadfiles_file
    if not lf or not Path(lf).exists():
        print(f"LoadFiles.xlsx not found at: {lf!r}")
        print("Set LOADFILES_FILE in .env, then re-run.")
        return 2

    if args.auto_recover:
        proceed = True
    else:
        ans = input(f"\nRe-load from {lf}? [y/N]: ").strip().lower()
        proceed = ans in ("y", "yes")

    if not proceed:
        print("Skipped. Run manually: python -m etl.tickers_initial_load")
        return 1

    print("\nRe-loading...")
    from etl.load_raw import load_loadfiles
    with session_scope() as s:
        rows_read, rows_inserted, rows_skipped = load_loadfiles(s, lf)
    print(f"  {rows_read} read, {rows_inserted} inserted, {rows_skipped} skipped")

    # Confirm
    with session_scope() as s:
        total = s.execute(text("SELECT COUNT(*) FROM ref_load_files")).scalar() or 0
    print(f"\nref_load_files now has {total} rows.")
    print("Restart uvicorn or hard-refresh the browser to see them on File Monitor.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
