import sys; sys.path.insert(0, ".")
from sqlalchemy import text
from etl.db import session_scope

FIXES = {
    18:  "drv_cat_atomic_input.trtn_relation",
    19:  "drv_cat_atomic_input.not_trtn_relation",
    28:  "drv_cat_atomic_input.brrpct_dir",
    52:  "drv_cat_atomic_input.3m_long",
    59:  "drv_cat_atomic_input.not_perf1d_sd",
    91:  "drv_cat_atomic_input.not_3wk_ol",
    92:  "drv_cat_atomic_input.not_3wk_ol_days",
    93:  "drv_cat_atomic_input.bull",
    94:  "drv_cat_atomic_input.not_bull",
    95:  "drv_cat_atomic_input.perforbull",
    96:  "drv_cat_atomic_input.not_perforbull",
    103: "drv_cat_atomic_input.brrtrade",
    104: "drv_cat_atomic_input.trrtrade",
}

with session_scope() as s:
    for rid, fqn in FIXES.items():
        n = s.execute(text(
            "UPDATE ref_trig_atomic_rule SET ma_column_name=:fqn WHERE atomic_rule_id=:rid AND deprecated_at IS NULL"
        ), {"fqn": fqn, "rid": rid}).rowcount
        print(f"  id={rid:>3}  updated={n}  {fqn}")
    s.commit()
print("Done.")
