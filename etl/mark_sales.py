"""
Detect and mark position sales by comparing consecutive snapshots.
When a symbol is missing from a new snapshot but was in the previous one, mark it as sold.

Two provisional layers, both superseded by the real thing:
  - mark_cs_sales / mark_f_sales (legacy): full exits only, written directly
    into hist_cs/hist_f's own sold_date/realized_gain_dollar columns using
    the broker's own lifetime gain figure. NEVER reconciled — that number
    sits there permanently, even after the real CST/FT transaction loads.
    Kept as-is for its existing consumers (e.g. Risk Dial modal).
  - estimate_cs_partial_sale / estimate_f_partial_sale / estimate_cs_full_sale /
    estimate_f_full_sale (this module's actual provisional layer): BOTH
    partial and full exits, written into drv_realized_gain_estimate using
    one consistent formula (avg cost basis x that day's LOW price). This is
    the table other screens should read "pending realized gain" from — it's
    auto-purged by derive_realized_gain() (etl/derive_realized.py) the
    moment the real CST/FT-derived FIFO number covers the same
    account/symbol/date gap. See drv_realized_gain_estimate comment in
    db/baseline.sql.
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


def _low_price(s, tos_symbol, d):
    """Day's low for tos_symbol on date d — hist_td first (EOD), falling
    back to drv_quote (covers dates a slower/weekly symbol hasn't hit TD
    for yet). Returns None if neither has it."""
    low = s.execute(text("""
        SELECT low_price FROM hist_td
        WHERE tos_symbol = :sym AND export_date = :d
        ORDER BY sequence DESC LIMIT 1
    """), {"sym": tos_symbol, "d": d}).scalar()
    if low is None:
        low = s.execute(text("""
            SELECT low_price FROM drv_quote
            WHERE tos_symbol = :sym AND as_of_date = :d
        """), {"sym": tos_symbol, "d": d}).scalar()
    return float(low) if low is not None else None


def _upsert_estimate(s, source, account, tos_symbol, snapshot_date, prev_date,
                     shares_sold_est, cost_per_share_prev, low_price,
                     prev_mark_price=None):
    proceeds_est = shares_sold_est * low_price
    cost_basis_est = shares_sold_est * cost_per_share_prev
    realized_gain_est = proceeds_est - cost_basis_est
    realized_gain_pct_est = (
        realized_gain_est / cost_basis_est * 100.0 if cost_basis_est else None
    )
    # sold_move_est mirrors get_portfolio_summary's real cs_sold_move CTE
    # (api/routers/dash.py): the day's mark-to-market move on shares no
    # longer held, i.e. today's price vs. the PRIOR snapshot's own mark —
    # not vs. cost basis. Feeds the "Today's Gain" KPI / Cumulative P&L
    # fallback, a different number from realized_gain_est on purpose.
    sold_move_est = (
        shares_sold_est * (low_price - prev_mark_price)
        if prev_mark_price is not None else None
    )
    s.execute(text("""
        INSERT INTO drv_realized_gain_estimate
          (source, account, tos_symbol, snapshot_date, prev_snapshot_date,
           shares_sold_est, cost_per_share_prev, low_price,
           proceeds_est, cost_basis_est, realized_gain_est, realized_gain_pct_est,
           prev_mark_price, sold_move_est)
        VALUES
          (:source, :account, :tos_symbol, :snapshot_date, :prev_snapshot_date,
           :shares_sold_est, :cost_per_share_prev, :low_price,
           :proceeds_est, :cost_basis_est, :realized_gain_est, :realized_gain_pct_est,
           :prev_mark_price, :sold_move_est)
        ON CONFLICT (source, account, tos_symbol, snapshot_date) DO UPDATE SET
           prev_snapshot_date    = EXCLUDED.prev_snapshot_date,
           shares_sold_est       = EXCLUDED.shares_sold_est,
           cost_per_share_prev   = EXCLUDED.cost_per_share_prev,
           low_price             = EXCLUDED.low_price,
           proceeds_est          = EXCLUDED.proceeds_est,
           cost_basis_est        = EXCLUDED.cost_basis_est,
           realized_gain_est     = EXCLUDED.realized_gain_est,
           realized_gain_pct_est = EXCLUDED.realized_gain_pct_est,
           prev_mark_price       = EXCLUDED.prev_mark_price,
           sold_move_est         = EXCLUDED.sold_move_est,
           computed_at           = now()
    """), {
        "source": source, "account": account, "tos_symbol": tos_symbol,
        "snapshot_date": snapshot_date, "prev_snapshot_date": prev_date,
        "shares_sold_est": round(shares_sold_est, 6),
        "cost_per_share_prev": round(cost_per_share_prev, 6),
        "low_price": low_price,
        "proceeds_est": round(proceeds_est, 2),
        "cost_basis_est": round(cost_basis_est, 2),
        "realized_gain_est": round(realized_gain_est, 2),
        "realized_gain_pct_est": round(realized_gain_pct_est, 4) if realized_gain_pct_est is not None else None,
        "prev_mark_price": round(prev_mark_price, 6) if prev_mark_price is not None else None,
        "sold_move_est": round(sold_move_est, 2) if sold_move_est is not None else None,
    })


def estimate_cs_partial_sale(snapshot_date):
    """
    Provisional realized gain/loss for CS positions whose qty dropped
    between two consecutive snapshots but the symbol is still open (a full
    exit is mark_cs_sales' job, not this). Writes drv_realized_gain_estimate.
    """
    with session_scope() as s:
        prev_date = s.execute(text("""
            SELECT MAX(snapshot_date) FROM hist_cs WHERE snapshot_date < :d
        """), {"d": snapshot_date}).scalar()
        if not prev_date:
            return 0

        rows = s.execute(text("""
            SELECT p.account, COALESCE(p.tos_symbol, p.symbol) AS tos_symbol,
                   p.qty AS qty_prev, c.qty AS qty_curr, p.cost_basis AS cost_basis_prev,
                   p.price AS prev_mark_price
            FROM hist_cs p
            JOIN hist_cs c
                ON c.account = p.account AND c.symbol = p.symbol
               AND c.snapshot_date = :curr_d
            WHERE p.snapshot_date = :prev_d
              AND c.qty > 0 AND p.qty > c.qty
        """), {"prev_d": prev_date, "curr_d": snapshot_date}).fetchall()

        total = 0
        for account, tos_symbol, qty_prev, qty_curr, cost_basis_prev, prev_mark_price in rows:
            if not tos_symbol or not qty_prev or not cost_basis_prev:
                continue
            shares_sold_est = float(qty_prev) - float(qty_curr)
            if shares_sold_est <= 0:
                continue
            cost_per_share_prev = float(cost_basis_prev) / float(qty_prev)
            low = _low_price(s, tos_symbol, snapshot_date)
            if low is None:
                continue
            _upsert_estimate(s, "CS", account, tos_symbol, snapshot_date, prev_date,
                             shares_sold_est, cost_per_share_prev, low,
                             prev_mark_price=float(prev_mark_price) if prev_mark_price is not None else None)
            total += 1

        s.commit()
        return total


def estimate_f_partial_sale(snapshot_date):
    """
    Provisional realized gain/loss for F positions whose qty dropped
    between two consecutive snapshots but the symbol is still open (a full
    exit is mark_f_sales' job, not this). Writes drv_realized_gain_estimate.
    """
    with session_scope() as s:
        prev_date = s.execute(text("""
            SELECT MAX(snapshot_date) FROM hist_f WHERE snapshot_date < :d
        """), {"d": snapshot_date}).scalar()
        if not prev_date:
            return 0

        rows = s.execute(text("""
            SELECT p.account_number, COALESCE(p.tos_symbol, p.symbol) AS tos_symbol,
                   p.qty AS qty_prev, c.qty AS qty_curr, p.avg_cost_basis AS cost_per_share_prev,
                   p.last_price AS prev_mark_price
            FROM hist_f p
            JOIN hist_f c
                ON c.account_number = p.account_number AND c.symbol = p.symbol
               AND c.snapshot_date = :curr_d
            WHERE p.snapshot_date = :prev_d
              AND c.qty > 0 AND p.qty > c.qty
        """), {"prev_d": prev_date, "curr_d": snapshot_date}).fetchall()

        total = 0
        for account_number, tos_symbol, qty_prev, qty_curr, cost_per_share_prev, prev_mark_price in rows:
            if not tos_symbol or not qty_prev or not cost_per_share_prev:
                continue
            shares_sold_est = float(qty_prev) - float(qty_curr)
            if shares_sold_est <= 0:
                continue
            low = _low_price(s, tos_symbol, snapshot_date)
            if low is None:
                continue
            _upsert_estimate(s, "F", account_number, tos_symbol, snapshot_date, prev_date,
                             shares_sold_est, float(cost_per_share_prev), low,
                             prev_mark_price=float(prev_mark_price) if prev_mark_price is not None else None)
            total += 1

        s.commit()
        return total


def estimate_cs_full_sale(snapshot_date):
    """
    Provisional realized gain/loss for CS positions that vanished entirely
    between two consecutive snapshots (same detection as mark_cs_sales, which
    also runs and writes its own — unreconciled — number straight into
    hist_cs). This one uses the same avg-cost x day's-low formula as the
    partial-sale estimate above and lands in drv_realized_gain_estimate, so
    it gets purged automatically once the real CST-derived FIFO row exists.
    """
    with session_scope() as s:
        prev_date = s.execute(text("""
            SELECT MAX(snapshot_date) FROM hist_cs WHERE snapshot_date < :d
        """), {"d": snapshot_date}).scalar()
        if not prev_date:
            return 0

        rows = s.execute(text("""
            SELECT p.account, COALESCE(p.tos_symbol, p.symbol) AS tos_symbol,
                   p.qty AS qty_prev, p.cost_basis AS cost_basis_prev, p.price AS prev_mark_price
            FROM hist_cs p
            LEFT JOIN hist_cs c
                ON c.account = p.account AND c.symbol = p.symbol
               AND c.snapshot_date = :curr_d
            WHERE p.snapshot_date = :prev_d
              AND c.symbol IS NULL
        """), {"prev_d": prev_date, "curr_d": snapshot_date}).fetchall()

        total = 0
        for account, tos_symbol, qty_prev, cost_basis_prev, prev_mark_price in rows:
            if not tos_symbol or not qty_prev or not cost_basis_prev:
                continue
            shares_sold_est = float(qty_prev)
            cost_per_share_prev = float(cost_basis_prev) / shares_sold_est
            low = _low_price(s, tos_symbol, snapshot_date)
            if low is None:
                continue
            _upsert_estimate(s, "CS", account, tos_symbol, snapshot_date, prev_date,
                             shares_sold_est, cost_per_share_prev, low,
                             prev_mark_price=float(prev_mark_price) if prev_mark_price is not None else None)
            total += 1

        s.commit()
        return total


def estimate_f_full_sale(snapshot_date):
    """
    Provisional realized gain/loss for F positions that vanished entirely
    between two consecutive snapshots (same detection as mark_f_sales, which
    also runs and writes its own — unreconciled — number straight into
    hist_f). Same avg-cost x day's-low formula, lands in
    drv_realized_gain_estimate, purged once the real FT-derived FIFO row
    exists.
    """
    with session_scope() as s:
        prev_date = s.execute(text("""
            SELECT MAX(snapshot_date) FROM hist_f WHERE snapshot_date < :d
        """), {"d": snapshot_date}).scalar()
        if not prev_date:
            return 0

        rows = s.execute(text("""
            SELECT p.account_number, COALESCE(p.tos_symbol, p.symbol) AS tos_symbol,
                   p.qty AS qty_prev, p.avg_cost_basis AS cost_per_share_prev,
                   p.last_price AS prev_mark_price
            FROM hist_f p
            LEFT JOIN hist_f c
                ON c.account_number = p.account_number AND c.symbol = p.symbol
               AND c.snapshot_date = :curr_d
            WHERE p.snapshot_date = :prev_d
              AND c.symbol IS NULL
        """), {"prev_d": prev_date, "curr_d": snapshot_date}).fetchall()

        total = 0
        for account_number, tos_symbol, qty_prev, cost_per_share_prev, prev_mark_price in rows:
            if not tos_symbol or not qty_prev or not cost_per_share_prev:
                continue
            low = _low_price(s, tos_symbol, snapshot_date)
            if low is None:
                continue
            _upsert_estimate(s, "F", account_number, tos_symbol, snapshot_date, prev_date,
                             float(qty_prev), float(cost_per_share_prev), low,
                             prev_mark_price=float(prev_mark_price) if prev_mark_price is not None else None)
            total += 1

        s.commit()
        return total


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
