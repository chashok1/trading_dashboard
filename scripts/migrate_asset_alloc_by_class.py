"""2026-11-19: replace ref_asset_allocation with the by-asset-class sizing table.

Old rows were mostly source lists (Call, Sig, RR, II, PS, ETF, CAll*, ...). New rows are what a
symbol IS (see etl/size_class.py). Percentages are of one account; dollar columns are on the
old $400,000 household base (derive_account_size / household_alloc recompute the real dollars).

Safe to re-run: it rewrites the table to the same rows each time. Back up first with
    SELECT * FROM ref_asset_allocation   (a CSV copy is kept in data/ by the task that ran this).
Run: python -m scripts.migrate_asset_alloc_by_class
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from etl.db import session_scope

BASE = 400000
# category, min_pct, max_pct, units_pct
ROWS = [
    ("Stocks",                 0.01,  0.03,  0.01),
    ("Stocks (Call/RR only)",  0.005, 0.015, 0.005),   # a stock on Call or RR and NOT on Signal Strength: half strength
    ("Exchange Traded Funds",  0.02,  0.06,  0.01),
    ("Fixed Income",           0.03,  0.10,  0.015),
    ("Commodities",            0.01,  0.02,  0.005),
    ("Foreign Currency",       0.04,  0.12,  0.02),
    ("Cash",                   0.0,   1.0,   0.0),
    ("Other",                  0.0,   0.0,   0.00125),
]


def main():
    with session_scope() as s:
        s.execute(text("DELETE FROM ref_asset_allocation"))
        for cat, mn, mx, up in ROWS:
            s.execute(text(
                "INSERT INTO ref_asset_allocation "
                "(category, min_pct, max_pct, units_pct, min_dollar, max_dollar, units, maintain_min_position) "
                "VALUES (:c, :mn, :mx, :up, :mnd, :mxd, :u, FALSE)"),
                {"c": cat, "mn": mn, "mx": mx, "up": up,
                 "mnd": mn * BASE, "mxd": mx * BASE, "u": up * BASE})
        n = s.execute(text("SELECT COUNT(*) FROM ref_asset_allocation")).scalar()
    print(f"ref_asset_allocation rewritten: {n} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
