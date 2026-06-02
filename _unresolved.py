import sys; sys.path.insert(0, ".")
from sqlalchemy import text
from etl.db import session_scope
from compare_excel import COL_MAP

# Invert COL_MAP: excel_header -> db_col
# Also build rule_name -> db_col lookup via COL_MAP
UNRESOLVABLE = {
    18: "Trade Trend Relation",
    19: "!Trade Trend Relation",
    28: "BRR% Dir Rule",
    52: "3mn Long Rule",
    59: "!Perf1D SD Rule",
    91: "!3wk Outlook",
    92: "!3wk Outlook Days",
    93: "Bull Rule",
    94: "!Bull Rule",
    95: "PerfOrBull Rule",
    96: "!PerfOrBull Rule",
    103: "Trade Close to BRR",
    104: "Trade Close to TRR",
}

# Map rule_name variations to COL_MAP keys
NAME_TO_EXCEL = {
    "Trade Trend Relation":   "TrTn Relation",
    "!Trade Trend Relation":  "!TrTn Relation",
    "BRR% Dir Rule":          "BRR% Dir",
    "3mn Long Rule":          "3m-Long",
    "!Perf1D SD Rule":        "!Perf1D_sd",
    "!3wk Outlook":           "!3wk ol",
    "!3wk Outlook Days":      "!3wk ol days",
    "Bull Rule":              "BULL",
    "!Bull Rule":             "!BULL",
    "PerfOrBull Rule":        "PerfOrBull",
    "!PerfOrBull Rule":       "!PerfOrBull",
    "Trade Close to BRR":     "BRRTrade",
    "Trade Close to TRR":     "TRRTrade",
}

print(f"{'ID':>4}  {'Rule Name':<30}  {'Excel Header':<25}  {'DB Column (drv_cat_atomic_input)'}")
print("-" * 95)
for rid, rname in UNRESOLVABLE.items():
    xl_hdr = NAME_TO_EXCEL.get(rname, "?")
    db_col = COL_MAP.get(xl_hdr, "NOT FOUND")
    fqn    = f"drv_cat_atomic_input.{db_col}" if db_col != "NOT FOUND" else "NOT FOUND"
    print(f"  {rid:>4}  {rname:<30}  {xl_hdr:<25}  {fqn}")
