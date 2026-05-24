"""
Detect and mark position sales by comparing consecutive snapshots.
When a symbol is missing from a new snapshot but was in the previous one, mark it as sold.
"""
from sqlalchemy import text
from etl.db import session_scope


def mark_cs_sales(snapshot_date):
    """
    Mark sold positions in hist_cs by comparing snapshot_date with the previous snapshot.
    For each account/symbol that was in the previous snapshot but missing from this one,
    update the previous row with sold_date, shares_sold, realized_gain, etc.
    """
    with session_scope() as s:
        # Find the previous snapshot date for this account
        prev_date = s.execute(text("""
            SELECT MAX(snapshot_date) FROM hist_cs
            WHERE snapshot_date < :d
        """), {"d": snapshot_date}).scalar()

        if not prev_date:
            return 0  # No previous snapshot to compare against

        # Find all accounts in the current snapshot
        accounts = s.execute(text("""
            SELECT DISTINCT account FROM hist_cs WHERE snapshot_date = :d
        """), {"d": snapshot_date}).fetchall()

        total_marked = 0

        for (account,) in accounts:
            # Find symbols in previous snapshot but not in current snapshot (for this account)
            sold_symbols = s.execute(text("""
                SELECT p.symbol, p.qty, p.gain_dollar, p.gain_pct, p.cost_basis
                FROM hist_cs p
                LEFT JOIN hist_cs c
                    ON c.account = p.account
                   AND c.symbol = p.symbol
                   AND c.snapshot_date = :curr_d
                WHERE p.snapshot_date = :prev_d
                  AND p.account = :account
                  AND c.symbol IS NULL
            """), {"prev_d": prev_date, "curr_d": snapshot_date, "account": account}).fetchall()

            for symbol, qty, gain_dollar, gain_pct, cost_basis in sold_symbols:
                # Update the previous row to mark it as sold
                s.execute(text("""
                    UPDATE hist_cs
                    SET sold_date = :sold_d,
                        shares_sold = :qty,
                        realized_gain_dollar = COALESCE(:gain, gain_dollar),
                        realized_gain_pct = COALESCE(:gain_pct, gain_pct)
                    WHERE snapshot_date = :prev_d
                      AND account = :account
                      AND symbol = :symbol
                """), {
                    "sold_d": snapshot_date,
                    "qty": qty,
                    "gain": gain_dollar,
                    "gain_pct": gain_pct,
                    "prev_d": prev_date,
                    "account": account,
                    "symbol": symbol
                })
                total_marked += 1

        s.commit()
        return total_marked


def mark_f_sales(snapshot_date):
    """
    Mark sold positions in hist_f by comparing snapshot_date with the previous snapshot.
    """
    with session_scope() as s:
        # Find the previous snapshot date
        prev_date = s.execute(text("""
            SELECT MAX(snapshot_date) FROM hist_f
            WHERE snapshot_date < :d
        """), {"d": snapshot_date}).scalar()

        if not prev_date:
            return 0

        # Find all accounts in the current snapshot
        accounts = s.execute(text("""
            SELECT DISTINCT account_number FROM hist_f WHERE snapshot_date = :d
        """), {"d": snapshot_date}).fetchall()

        total_marked = 0

        for (account_number,) in accounts:
            # Find symbols sold (present in previous, missing in current)
            sold_symbols = s.execute(text("""
                SELECT p.symbol, p.qty, p.total_gl_dollar, p.total_gl_pct, p.cost_basis_total
                FROM hist_f p
                LEFT JOIN hist_f c
                    ON c.account_number = p.account_number
                   AND c.symbol = p.symbol
                   AND c.snapshot_date = :curr_d
                WHERE p.snapshot_date = :prev_d
                  AND p.account_number = :account_number
                  AND c.symbol IS NULL
            """), {"prev_d": prev_date, "curr_d": snapshot_date, "account_number": account_number}).fetchall()

            for symbol, qty, gain_dollar, gain_pct, cost_basis in sold_symbols:
                s.execute(text("""
                    UPDATE hist_f
                    SET sold_date = :sold_d,
                        shares_sold = :qty,
                        realized_gain_dollar = COALESCE(:gain, total_gl_dollar),
                        realized_gain_pct = COALESCE(:gain_pct, total_gl_pct)
                    WHERE snapshot_date = :prev_d
                      AND account_number = :account_number
                      AND symbol = :symbol
                """), {
                    "sold_d": snapshot_date,
                    "qty": qty,
                    "gain": gain_dollar,
                    "gain_pct": gain_pct,
                    "prev_d": prev_date,
                    "account_number": account_number,
                    "symbol": symbol
                })
                total_marked += 1

        s.commit()
        return total_marked
