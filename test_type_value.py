#!/usr/bin/env python3

from etl.db import session_scope
from sqlalchemy import text

with session_scope() as s:
    r = s.execute(text(
        "SELECT DISTINCT type, length(type) as type_len FROM hist_f WHERE type IS NOT NULL"
    )).all()

    print("Type values in hist_f:")
    for row in r:
        type_val = row[0]
        type_len = row[1]
        print(f"  |{type_val}| (length={type_len})")
