import sys; sys.path.insert(0, ".")
from sqlalchemy import text
from etl.db import session_scope
with session_scope() as s:
    n = s.execute(text(
        "UPDATE ref_trig_atomic_rule "
        "SET ma_column_name = 'drv_cat_atomic_input.bb_threshold' "
        "WHERE atomic_rule_id = 8 AND deprecated_at IS NULL"
    )).rowcount
    s.commit()
print("Updated rows:", n)
# Verify
with session_scope() as s:
    r = s.execute(text(
        "SELECT atomic_rule_id, rule_name, ma_column_name FROM ref_trig_atomic_rule WHERE atomic_rule_id=8"
    )).first()
    print("Rule:", r)
