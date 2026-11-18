"""Builder: a held pick with a blank % stays as held; a NEW blank pick takes an equal share of what is still unfilled in the class target (2026-11-18)."""
import pytest

from etl import builder_engine as eng
from tests.test_model_portfolio import _ctx


def _req(picks):
    return {"manual": True, "preset": "custom", "mix": {"Equities": 10, "Cash": 90}, "use_risk_dial": False, "amount": 400000.0, "picks": picks}


def _values(picks, held):
    ctx = _ctx(risk_mult=None)
    ctx["account"]["holdings"] = {s: {"value": v, "bucket": "Equities", "area": "x"} for s, v in held.items()}
    res = eng.build_positions(ctx, _req(picks))
    return {p["sym"]: p["value"] for p in res["positions"]}


def test_held_blank_pick_stays_as_held_even_when_the_class_target_is_bigger():
    v = _values([{"sym": "XLK", "bucket": "Equities", "pct": None, "amt": 0}], {"XLK": 20000.0})
    assert v["XLK"] == pytest.approx(20000.0)           # the screen's "Unallocated" line shows the other $20K; you decide


def test_typed_pct_still_takes_its_share_of_the_class():
    typed = _values([{"sym": "XLK", "bucket": "Equities", "pct": 100.0, "amt": 0}], {"XLK": 20000.0})
    assert typed["XLK"] == pytest.approx(40000.0)


def test_new_blank_pick_takes_the_unfilled_room():
    v = _values([{"sym": "XLK", "bucket": "Equities", "pct": None, "amt": 0}, {"sym": "XLF", "bucket": "Equities", "pct": None, "amt": 0}],
                {"XLK": 20000.0})
    assert v["XLK"] == pytest.approx(20000.0) and v["XLF"] == pytest.approx(20000.0)      # $40K target, $20K held: the new stock gets the rest


def test_target_equal_to_holdings_leaves_every_pick_matched():
    v = _values([{"sym": "XLK", "bucket": "Equities", "pct": None, "amt": 0}, {"sym": "XLF", "bucket": "Equities", "pct": None, "amt": 0}],
                {"XLK": 30000.0, "XLF": 10000.0})
    assert v["XLK"] == pytest.approx(30000.0) and v["XLF"] == pytest.approx(10000.0)


def test_buy_one_of_group_still_uses_held_plus_group_money():
    v = _values([{"sym": "XLK", "bucket": "Equities", "pct": None, "amt": 5000.0, "grp": "A"}], {"XLK": 20000.0})
    assert v["XLK"] == pytest.approx(25000.0)
