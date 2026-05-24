#!/usr/bin/env python3
import os
import psycopg

pw = 'pgdbpw'  # or use os.getenv('PG_PASSWORD', 'pgdbpw')
try:
    conn = psycopg.connect(host='localhost', dbname='trading', user='postgres', password=pw)
    cur = conn.cursor()
    cur.execute('SELECT file_type, week_day, file_time, target_tab, source_dir, enabled FROM ref_load_files ORDER BY file_type')

    rows = cur.fetchall()
    print("File Type    | Week Day     | Time       | Target Tab      | Source Dir                                             | Enabled")
    print("-" * 140)
    for row in rows:
        ft, wd, ft_time, tt, sd, ena = row
        time_str = str(ft_time) if ft_time else "---"
        print(f"{ft:12} | {wd:12} | {time_str:10} | {tt:15} | {sd:55} | {str(ena):7}")

    cur.close()
    conn.close()
except Exception as e:
    print(f"Error: {e}")
