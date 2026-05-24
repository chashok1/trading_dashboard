#!/usr/bin/env python3
"""
Retroactively populate sold_date and realized_gain columns for all historical sales.
For each account/symbol, detect when it disappeared and mark the last occurrence as sold.
"""
from etl.db import session_scope
from sqlalchemy import text
from datetime import datetime

def populate_cs_sales():
    """Detect and mark all sold positions in hist_cs."""
    with session_scope() as s:
        print("Processing Schwab (hist_cs) sales...")

        # Get all unique account/symbol combinations with dates
        accounts = s.execute(text("""
            SELECT DISTINCT account FROM hist_cs ORDER BY account
        """)).fetchall()

        total_marked = 0

        for (account,) in accounts:
            # Get all snapshot dates for this account in order
            dates = s.execute(text("""
                SELECT DISTINCT snapshot_date FROM hist_cs
                WHERE account = :account
                ORDER BY snapshot_date
            """), {"account": account}).fetchall()

            dates = [row[0] for row in dates]

            # For each consecutive pair of dates, find symbols that disappeared
            for i in range(len(dates) - 1):
                curr_date = dates[i]
                next_date = dates[i + 1]

                # Find symbols in current date but not in next date
                sold_symbols = s.execute(text("""
                    SELECT p.symbol, p.qty, p.gain_dollar, p.gain_pct
                    FROM hist_cs p
                    LEFT JOIN hist_cs c
                        ON c.account = p.account
                       AND c.symbol = p.symbol
                       AND c.snapshot_date = :next_date
                    WHERE p.snapshot_date = :curr_date
                      AND p.account = :account
                      AND c.symbol IS NULL
                """), {"curr_date": curr_date, "next_date": next_date, "account": account}).fetchall()

                for symbol, qty, gain_dollar, gain_pct in sold_symbols:
                    # Update the row with sale info
                    s.execute(text("""
                        UPDATE hist_cs
                        SET sold_date = :sold_date,
                            shares_sold = :qty,
                            realized_gain_dollar = :gain,
                            realized_gain_pct = :gain_pct
                        WHERE snapshot_date = :curr_date
                          AND account = :account
                          AND symbol = :symbol
                    """), {
                        "sold_date": next_date,
                        "qty": qty,
                        "gain": gain_dollar,
                        "gain_pct": gain_pct,
                        "curr_date": curr_date,
                        "account": account,
                        "symbol": symbol
                    })
                    total_marked += 1
                    print(f"  {account} {symbol}: sold on {next_date}")

            s.commit()

        print(f"[OK] Marked {total_marked} sales in hist_cs\n")
        return total_marked


def populate_f_sales():
    """Detect and mark all sold positions in hist_f."""
    with session_scope() as s:
        print("Processing Fidelity (hist_f) sales...")

        # Get all unique account/symbol combinations with dates
        accounts = s.execute(text("""
            SELECT DISTINCT account_number FROM hist_f ORDER BY account_number
        """)).fetchall()

        total_marked = 0

        for (account_number,) in accounts:
            # Get all snapshot dates for this account in order
            dates = s.execute(text("""
                SELECT DISTINCT snapshot_date FROM hist_f
                WHERE account_number = :account_number
                ORDER BY snapshot_date
            """), {"account_number": account_number}).fetchall()

            dates = [row[0] for row in dates]

            # For each consecutive pair of dates, find symbols that disappeared
            for i in range(len(dates) - 1):
                curr_date = dates[i]
                next_date = dates[i + 1]

                # Find symbols in current date but not in next date
                sold_symbols = s.execute(text("""
                    SELECT p.symbol, p.qty, p.total_gl_dollar, p.total_gl_pct
                    FROM hist_f p
                    LEFT JOIN hist_f c
                        ON c.account_number = p.account_number
                       AND c.symbol = p.symbol
                       AND c.snapshot_date = :next_date
                    WHERE p.snapshot_date = :curr_date
                      AND p.account_number = :account_number
                      AND c.symbol IS NULL
                """), {"curr_date": curr_date, "next_date": next_date, "account_number": account_number}).fetchall()

                for symbol, qty, gain_dollar, gain_pct in sold_symbols:
                    # Update the row with sale info
                    s.execute(text("""
                        UPDATE hist_f
                        SET sold_date = :sold_date,
                            shares_sold = :qty,
                            realized_gain_dollar = :gain,
                            realized_gain_pct = :gain_pct
                        WHERE snapshot_date = :curr_date
                          AND account_number = :account_number
                          AND symbol = :symbol
                    """), {
                        "sold_date": next_date,
                        "qty": qty,
                        "gain": gain_dollar,
                        "gain_pct": gain_pct,
                        "curr_date": curr_date,
                        "account_number": account_number,
                        "symbol": symbol
                    })
                    total_marked += 1
                    print(f"  {account_number} {symbol}: sold on {next_date}")

            s.commit()

        print(f"[OK] Marked {total_marked} sales in hist_f\n")
        return total_marked


if __name__ == "__main__":
    print("=" * 70)
    print("RETROACTIVELY POPULATING SALES DATA")
    print("=" * 70 + "\n")

    cs_count = populate_cs_sales()
    f_count = populate_f_sales()

    print("=" * 70)
    print(f"COMPLETE: Marked {cs_count + f_count} total sales")
    print("=" * 70)
