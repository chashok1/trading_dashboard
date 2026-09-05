"""
Dividend income derivation across CS + F transactions.

Why a separate module (mirrors etl/derive_realized.py's own reasoning):
  - hist_cs and hist_f are SNAPSHOTS (not historic) and carry no dividend
    information at all -- a snapshot only shows current qty/cost basis.
  - The transaction tables (hist_cst, hist_ft) carry the real dividend
    activity, so this reads the same two source tables derive_realized.py
    does.

"Gross" dividend income = cash-received dividends PLUS dividend-
reinvestment (DRIP) amounts. Both brokers record a DRIP leg's actual BUY
EXECUTION as a BUY-tagged row (never tagged as a dividend) -- F's
"REINVESTMENT" action text is classified action_kind='BUY' everywhere else
in this codebase (etl/derive_realized.py), and CS's 'Reinvest Shares' is
the same idea (see _fetch_rows's own comment) -- so a plain "sum
dividend-tagged rows" silently undercounts income for any symbol with DRIP
on. Each leg is kept as its own row (is_reinvested flag) so the
cash-vs-reinvested split stays auditable; summing both gives the gross
figure a 1099-DIV would report. User: "track it" (dividends), confirmed
"gross income" over "cash-received only" -- 2026-09-05.

2026-09-05 follow-up: the CS action-text matching originally covered only
'DIVIDEND' -- wrong, and caught live, by the user asking specifically about
4 symbols (BUXX/CLOX/CLOZ/HYG) that showed zero income despite real
payments. Schwab's actual export never uses the bare word "Dividend"; see
_fetch_rows's CS branch for the real string list this now matches.

Not FIFO -- no lot matching needed. This is a straight filter+classify of
the transaction tables, unlike derive_realized_gain's stateful buy-lot walk.

Edge cases we DON'T handle yet (same caveats as derive_realized.py):
  - Cross-account transfers of a dividend-paying position mid-quarter are
    just whatever each account's own transaction file shows -- no
    reconciliation across accounts.
  - Return-of-capital vs. qualified/ordinary dividend classification (tax
    character) isn't tracked -- this is a cash-flow figure, not a tax one.
"""
from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

log = logging.getLogger("etl.derive_dividend_income")


# Same (source_code, table_name, account_column) convention as
# derive_realized.py -- F groups by account_number, not account, for the
# same reason (hist_ft.account is inconsistently populated across load
# batches for the same physical account).
_SOURCES = [
    ("CS", "hist_cst", "account"),
    ("F",  "hist_ft",  "account_number"),
]


def _fetch_rows(session: Session, source: str, table: str, account_col: str) -> list[dict]:
    """Pull dividend-related rows (cash-received + DRIP legs) for one source."""
    if source == "CS":
        # Schwab action text is short and un-normalized (no action_kind
        # column, unlike hist_ft). 2026-09-05: this originally matched only
        # 'DIVIDEND' -- WRONG, and confirmed missing real income against
        # live data (BUXX/CLOX/CLOZ/HYG all showed zero dividend income
        # despite dozens of real payments) -- Schwab's actual export never
        # uses the bare word "Dividend"; the real action strings are
        # 'Cash Dividend', 'Qualified Dividend', 'Non-Qualified Div', and
        # 'Pr Yr Cash Div' (a prior-year true-up entry), plus capital-gain
        # distributions ('Long Term Cap Gain' / 'Short Term Cap Gain',
        # mirroring Fidelity's action_kind='DIV' which already folds those
        # in). The DRIP leg is 'Qual Div Reinvest' (positive amount, the
        # income record) -- its counterpart 'Reinvest Shares' (negative
        # amount, the same-day same-symbol BUY execution that spent that
        # exact cash) is deliberately NOT matched here: it's the spend side
        # of the pair, not an income record, same role a plain BUY row
        # plays elsewhere. 'Reinvest Dividend' also kept (distinct action
        # text, same role as 'Qual Div Reinvest').
        sql = f"""
            SELECT trade_date AS pay_date, {account_col} AS account, symbol,
                   COALESCE(amount, 0) AS amount, action AS raw_action,
                   (UPPER(action) IN ('REINVEST DIVIDEND', 'QUAL DIV REINVEST')) AS is_reinvested
            FROM {table}
            WHERE symbol IS NOT NULL AND symbol <> ''
              AND UPPER(action) IN (
                  'CASH DIVIDEND', 'QUALIFIED DIVIDEND', 'NON-QUALIFIED DIV',
                  'PR YR CASH DIV', 'LONG TERM CAP GAIN', 'SHORT TERM CAP GAIN',
                  'REINVEST DIVIDEND', 'QUAL DIV REINVEST'
              )
              AND {account_col} NOT IN (SELECT account_number FROM ref_accounts WHERE is_active = FALSE)
        """
    else:
        # Fidelity: action_kind='DIV' already covers cash dividends AND
        # cap-gain distributions (_f_action_kind's "DIVIDEND RECEIVED" /
        # "LONG-TERM CAP GAIN" / "SHORT-TERM CAP GAIN" patterns, see
        # etl/load_raw.py's _F_ACTION_PATTERNS). The DRIP leg is classified
        # action_kind='BUY' (the loader matches "REINVESTMENT" before any
        # DIV check), so it's matched here on the raw action text instead.
        sql = f"""
            SELECT trade_date AS pay_date, {account_col} AS account, symbol,
                   COALESCE(amount, 0) AS amount, action AS raw_action,
                   (action_kind = 'BUY') AS is_reinvested
            FROM {table}
            WHERE symbol IS NOT NULL AND symbol <> ''
              AND (action_kind = 'DIV' OR action ILIKE '%REINVESTMENT%')
              AND {account_col} NOT IN (SELECT account_number FROM ref_accounts WHERE is_active = FALSE)
        """
    return [dict(r) for r in session.execute(text(sql)).mappings().all()]


def derive_dividend_income(session: Session) -> int:
    """Rebuild drv_dividend_income across all known transaction sources.

    Idempotent: TRUNCATEs then re-inserts. Cheap full rebuild every time --
    no stateful matching needed (unlike derive_realized_gain's FIFO walk),
    so there's no reason to try a partial/incremental rebuild.

    Returns the number of dividend-leg rows written.
    """
    all_rows: list[dict] = []
    for source, table, account_col in _SOURCES:
        try:
            rows = _fetch_rows(session, source, table, account_col)
        except Exception as e:
            log.warning("source %s: read failed (%s); skipping", source, e)
            continue
        log.info("source %s: %d dividend-related rows", source, len(rows))

        # Dedup the money-market/cash-sweep pattern: a sweep fund (e.g.
        # SPAXX) records ONE dividend event as TWO rows -- a cash-received
        # leg AND a same-day, same-amount reinvestment leg (the cash gets
        # auto-swept right back into the fund) -- confirmed via the real
        # data this was built against: every SPAXX pay_date had a matching
        # DIV + REINVESTMENT pair at the identical amount. Summing both
        # would double the actual income. A genuine stock/fund DRIP (e.g.
        # SWPPX) instead produces ONLY the reinvestment-tagged row, no
        # separate cash leg -- that case must still be counted (it's the
        # only record of that income). Rule: group by (account, symbol,
        # pay_date, amount); if the group has a cash-received (not
        # reinvested) row, drop any reinvested row(s) in that same group as
        # the sweep-pattern duplicate; otherwise keep the reinvested row(s)
        # -- they're the only evidence of that dividend.
        groups: dict[tuple, list[dict]] = {}
        for r in rows:
            amount = abs(float(r["amount"] or 0))
            if amount <= 0:
                continue
            key = (r["account"], r["symbol"], r["pay_date"], f"{amount:.2f}")
            groups.setdefault(key, []).append({**r, "amount": round(amount, 2)})
        for key, group_rows in groups.items():
            cash_rows = [r for r in group_rows if not r["is_reinvested"]]
            keep = cash_rows if cash_rows else group_rows
            for r in keep:
                all_rows.append({
                    "source":        source,
                    "account":       r["account"],
                    "symbol":        r["symbol"],
                    "pay_date":      r["pay_date"],
                    "amount":        r["amount"],
                    "is_reinvested": bool(r["is_reinvested"]),
                    "raw_action":    r["raw_action"],
                })

    session.execute(text("TRUNCATE TABLE drv_dividend_income"))
    if not all_rows:
        session.commit()
        return 0
    session.execute(text("""
        INSERT INTO drv_dividend_income
          (source, account, tos_symbol, pay_date, amount, is_reinvested, raw_action)
        VALUES
          (:source, :account, :symbol, :pay_date, :amount, :is_reinvested, :raw_action)
        ON CONFLICT (source, account, tos_symbol, pay_date, amount, is_reinvested) DO UPDATE SET
           raw_action  = EXCLUDED.raw_action,
           computed_at = now()
    """), all_rows)
    session.commit()
    return len(all_rows)


if __name__ == "__main__":
    from etl.db import session_scope
    from etl._logging import setup_logging
    setup_logging()
    with session_scope() as s:
        n = derive_dividend_income(s)
        print(f"drv_dividend_income rebuilt: {n} dividend-leg rows")
