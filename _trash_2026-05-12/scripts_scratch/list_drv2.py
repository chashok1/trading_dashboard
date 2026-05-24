#!/usr/bin/env python3
from etl.db import session_scope
from etl.ma_codegen import get_all_drv2_tables

with session_scope() as session:
    tables = get_all_drv2_tables(session)
    print(f"Found {len(tables)} drv2_* tables:")
    for t in sorted(tables):
        print(f"  '{t}'")
