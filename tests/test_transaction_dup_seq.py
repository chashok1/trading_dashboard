"""Identical fills in one file keep distinct occurrence numbers (etl/load_raw.py)."""
from datetime import date

from etl.load_raw import _number_identical_rows

KEY = ("account_number", "trade_date", "action", "symbol", "quantity", "price")


def row(sym="DT", qty=-100, price=58.62, d=date(2026, 10, 1)):
    return {"account_number": "A1", "trade_date": d, "action": "SOLD", "symbol": sym,
            "quantity": qty, "price": price}


def test_identical_fills_get_increasing_numbers():
    recs = [row(), row(), row()]
    _number_identical_rows(recs, KEY)
    assert [r["dup_seq"] for r in recs] == [1, 2, 3]


def test_different_fills_all_start_at_one():
    recs = [row(price=58.62), row(price=58.63), row(sym="GTLB")]
    _number_identical_rows(recs, KEY)
    assert [r["dup_seq"] for r in recs] == [1, 1, 1]


def test_numbering_is_stable_between_overlapping_files():
    older = [row(), row(), row(sym="GTLB")]
    newer = [row(), row()]
    _number_identical_rows(older, KEY)
    _number_identical_rows(newer, KEY)
    assert {(r["symbol"], r["dup_seq"]) for r in newer} <= {(r["symbol"], r["dup_seq"]) for r in older}


def test_null_quantity_and_price_rows_number_too():
    recs = [row(qty=None, price=None), row(qty=None, price=None)]
    _number_identical_rows(recs, KEY)
    assert [r["dup_seq"] for r in recs] == [1, 2]
