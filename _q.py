import sys; sys.path.insert(0, ".")
from sqlalchemy import text
from etl.db import session_scope
with session_scope() as s:
    rules = s.execute(text(
        "SELECT atomic_rule_id, rule_name, ma_column_name, scoring_mode, "
        "brkeout_from, brkeout_to, wt_below, wt_between, wt_above, score_params "
        "FROM ref_trig_atomic_rule "
        "WHERE lower(rule_name) LIKE chr(37)||chr(98)||chr(98)||chr(116)||chr(104)||chr(114)||chr(101)||chr(115)||chr(104)||chr(37) "
        "AND deprecated_at IS NULL ORDER BY rule_name"
    )).mappings().fetchall()
    for r in rules:
        print(dict(r))
    val = s.execute(text(
        "SELECT bbthresh_co_days, bbthresh_co_days2, bb_threshold "
        "FROM drv_cat_atomic_input "
        "WHERE tos_symbol=chr(65)||chr(65)||chr(80)||chr(76) "
        "AND as_of_date=(SELECT MAX(as_of_date) FROM drv_cat_atomic_input)"
    )).first()
    print("AAPL values:", val)
