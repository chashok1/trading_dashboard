"""
Diagnose why the Portfolio → Realized tab is blank.

Three possible causes:
  1. hist_cst / hist_ft are empty
     → no transactions have been loaded; load the CSV first
  2. drv_realized_gain is empty
     → transactions exist, but the FIFO derive step hasn't run
  3. /api/portfolio/realized returns 0 rows
     → data exists, but the query has a filter that hides it

This script reads each layer and prints what it finds. Always run with
the venv active.
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import text
from etl.db import session_scope


def main():
    print("=" * 70)
    print("REALIZED-TAB DIAGNOSTIC")
    print("=" * 70)
    issues = []

    with session_scope() as s:
        # ---- Layer 1: transactions tables ----
        print("\n[1] Transaction tables")
        for tbl in ("hist_cst", "hist_ft"):
            try:
                row = s.execute(text(f"""
                    SELECT COUNT(*) AS total,
                           COUNT(*) FILTER (WHERE
                               {'action_kind' if tbl.endswith('_f_transactions') else "UPPER(action)"}
                               = 'SELL') AS n_sells,
                           MIN(trade_date) AS earliest,
                           MAX(trade_date) AS latest
                    FROM {tbl}
                """)).first()
                total, n_sells, earliest, latest = row
                print(f"    {tbl}:")
                print(f"      total rows: {total}")
                print(f"      SELL rows:  {n_sells}")
                print(f"      date range: {earliest} → {latest}")
                if total == 0:
                    issues.append(f"{tbl} is EMPTY — no transactions to FIFO-match")
                elif n_sells == 0:
                    issues.append(f"{tbl} has {total} rows but ZERO sells — only buys/cash will show no realized gain")
            except Exception as e:
                issues.append(f"{tbl}: query failed: {e}")
                print(f"      ERROR: {e}")

        # ---- Layer 2: derived realized-gain table ----
        print("\n[2] drv_realized_gain (FIFO-matched output)")
        try:
            row = s.execute(text("""
                SELECT COUNT(*) AS total,
                       COUNT(*) FILTER (WHERE source = 'CS') AS n_cs,
                       COUNT(*) FILTER (WHERE source = 'F')  AS n_f,
                       SUM(realized_gain) AS total_realized,
                       MIN(sell_date) AS earliest,
                       MAX(sell_date) AS latest
                FROM drv_realized_gain
            """)).first()
            total, n_cs, n_f, total_realized, earliest, latest = row
            print(f"    total sell-event rows:  {total}")
            print(f"      CS:   {n_cs}")
            print(f"      F:    {n_f}")
            print(f"    total realized gain:    ${total_realized:,.2f}" if total_realized else "    total realized gain:    $0.00")
            print(f"    date range:             {earliest} → {latest}")
            if total == 0:
                issues.append("drv_realized_gain is EMPTY — FIFO derive hasn't run")
        except Exception as e:
            issues.append(f"drv_realized_gain: query failed: {e}")
            print(f"    ERROR: {e}")

        # ---- Layer 3: API endpoint shape ----
        print("\n[3] /api/portfolio/realized (what the tab actually fetches)")
        try:
            row = s.execute(text("""
                SELECT symbol AS bucket,
                       COUNT(*) AS n_sells,
                       SUM(realized_gain) AS total_realized
                FROM drv_realized_gain
                GROUP BY symbol
                ORDER BY total_realized DESC NULLS LAST
                LIMIT 5
            """)).all()
            if not row:
                print("    (no rows — Realized tab will be blank)")
            else:
                print("    Top 5 symbols by total realized:")
                for r in row:
                    print(f"      {r[0]:8}  n_sells={r[1]:>3}  realized=${float(r[2] or 0):>12,.2f}")
        except Exception as e:
            print(f"    ERROR: {e}")

    # ---- Summary + action ----
    print("\n" + "=" * 70)
    if not issues:
        print("Realized tab has data. If the UI still shows blank, hard-refresh (Ctrl+F5).")
        return 0

    print(f"{len(issues)} issue(s) found:")
    for i, msg in enumerate(issues, 1):
        print(f"  {i}. {msg}")

    print("\n--- Action ---")
    print("• If transactions tables are empty:")
    print("    python -m etl.etl_load \"C:\\path\\to\\your_transactions.csv\"")
    print("• If drv_realized_gain is empty (most likely cause):")
    print("    python -m etl.derive_realized")
    print("• Then hard-refresh the Portfolio → Realized tab")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
