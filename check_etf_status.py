from sqlalchemy import text
from etl.db import session_scope
from datetime import date

with session_scope() as s:
    # Check what the monitor query returns for ETF
    result = s.execute(text("""
        WITH today AS (SELECT CURRENT_DATE AS d),
        is_today AS (
            SELECT r.file_type
            FROM ref_load_files r, today t
            WHERE r.enabled = TRUE
              AND (
                  r.week_day = 'WKDAY' AND EXTRACT(DOW FROM t.d) BETWEEN 1 AND 5 OR
                  r.week_day = 'MON'   AND EXTRACT(DOW FROM t.d) = 1 OR
                  r.week_day = 'TUE'   AND EXTRACT(DOW FROM t.d) = 2 OR
                  r.week_day = 'WED'   AND EXTRACT(DOW FROM t.d) = 3 OR
                  r.week_day = 'THU'   AND EXTRACT(DOW FROM t.d) = 4 OR
                  r.week_day = 'FRI'   AND EXTRACT(DOW FROM t.d) = 5 OR
                  r.week_day = 'SAT'   AND EXTRACT(DOW FROM t.d) = 6 OR
                  r.week_day = 'SUN'   AND EXTRACT(DOW FROM t.d) = 0 OR
                  r.week_day = 'ALL'
              )
        ),
        window_start AS (
            SELECT
                r.file_type,
                CASE
                    WHEN r.week_day = 'SUN'
                         THEN CURRENT_DATE - ((EXTRACT(DOW FROM CURRENT_DATE)::int - 0 + 7) % 7)
                    WHEN r.week_day = 'MON'
                         THEN CURRENT_DATE - ((EXTRACT(DOW FROM CURRENT_DATE)::int - 1 + 7) % 7)
                    ELSE CURRENT_DATE
                END AS window_date
            FROM ref_load_files r
        ),
        last_fp AS (
            SELECT DISTINCT ON (file_type)
                file_type, file_date, processed_at, last_run_id, file_path
            FROM meta_file_processed
            ORDER BY file_type, processed_at DESC
        ),
        today_fp AS (
            SELECT file_type, file_date, processed_at, last_run_id, file_path
            FROM meta_file_processed, today t WHERE file_date = t.d
        )
        SELECT
            r.file_type,
            ws.window_date,
            COALESCE(fp.file_date, lp.file_date) AS file_date,
            it.file_type IS NOT NULL AS is_today,
            fp.file_date IS NOT NULL AS processed_today,
            lp.file_date IS NOT NULL AS has_last_fp
        FROM ref_load_files r
        LEFT JOIN is_today  it ON LOWER(it.file_type) = LOWER(r.file_type)
        LEFT JOIN today_fp  fp ON LOWER(fp.file_type) = LOWER(r.file_type)
        LEFT JOIN window_start ws ON ws.file_type = r.file_type
        LEFT JOIN last_fp   lp ON LOWER(lp.file_type) = LOWER(r.file_type) AND lp.file_date >= ws.window_date
        WHERE LOWER(r.file_type) = 'etf'
    """)).first()

    if result:
        print("ETF Status Debug:")
        print(f"  file_type: {result[0]}")
        print(f"  window_date: {result[1]}")
        print(f"  file_date (last processed): {result[2]}")
        print(f"  is_today: {result[3]}")
        print(f"  processed_today: {result[4]}")
        print(f"  has_last_fp: {result[5]}")
        print()
        if result[5]:  # has_last_fp
            print("✓ Should show as 'done' (file was processed in its window)")
        elif result[3]:  # is_today
            print("Should show as 'pending' or 'overdue' (scheduled today but not processed)")
        else:
            print("✗ Should show as 'not today' (not scheduled today)")
