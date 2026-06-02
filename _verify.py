import sys; sys.path.insert(0, ".")
from sqlalchemy import text
from etl.db import session_scope
from etl.derive import _resolve_atomic_input_column, eval_atomic_rule

with session_scope() as s:
    col_map = _resolve_atomic_input_column(s)
    rule_row = s.execute(text(
        "SELECT atomic_rule_id, rule_name, scoring_mode, brkeout_from, brkeout_to, "
        "wt_below, wt_between, wt_above FROM ref_trig_atomic_rule WHERE atomic_rule_id=8"
    )).mappings().first()
    ai_val = s.execute(text(
        "SELECT bb_threshold FROM drv_cat_atomic_input "
        "WHERE tos_symbol='AAPL' AND as_of_date=(SELECT MAX(as_of_date) FROM drv_cat_atomic_input)"
    )).scalar()

resolved = col_map.get(8)
rule = dict(rule_row)
weight = eval_atomic_rule(ai_val, rule)
print("Resolved column :", resolved)
print("bb_threshold val :", ai_val)
print("Computed weight  :", weight)
print("Expected         : 0 (AAPL not on fresh crossover day, so bb_threshold=0)")
