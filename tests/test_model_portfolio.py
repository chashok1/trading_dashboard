"""Portfolio Builder: pure-function behaviour (no database). DESIGN_SPEC_9/10/11."""
import math
from datetime import date, timedelta

import pytest

from etl import derive_model_portfolio as m
from etl import builder_engine as eng
from etl.builder_store import add_months


# ---------------------------------------------------------------- measures
def _walk(n, step=0.01, start=100.0):
    out = [start]
    for i in range(n):
        out.append(out[-1] * (1 + (step if i % 2 == 0 else -step)))
    return out


def test_swings_needs_55_returns_and_annualises():
    assert m.swings(_walk(40)) is None
    v = m.swings(_walk(70, 0.01))
    assert v is not None and 0.10 < v < 0.20           # ~1% daily moves -> ~16% a year
    assert m.swings(_walk(70, 0.02)) > v


def test_beta_is_two_for_a_double_move_fund():
    dates = [date(2026, 1, 1) + timedelta(days=i) for i in range(140)]
    spy, fund = {}, {}
    px, fx = 100.0, 100.0
    for i, d in enumerate(dates):
        r = 0.01 if i % 3 else -0.015
        px *= 1 + r
        fx *= 1 + 2 * r
        spy[d], fund[d] = px, fx
    b, w = m.beta_vs_spy(fund, spy, dates)
    assert w == 126 and b == pytest.approx(2.0, abs=0.05)


def test_beta_falls_back_to_63_and_needs_55():
    dates = [date(2026, 1, 1) + timedelta(days=i) for i in range(80)]
    spy = {d: 100 + (i % 5) for i, d in enumerate(dates)}
    fund = {d: 50 + (i % 5) / 2 for i, d in enumerate(dates)}
    b, w = m.beta_vs_spy(fund, spy, dates)
    assert w == 63 and b is not None
    assert m.beta_vs_spy(fund, spy, dates[:30]) == (None, 0)


def test_momentum_skips_last_month():
    closes = [100.0] * 127
    closes[-127] = 100.0     # t-126
    closes[-22] = 130.0      # t-21
    closes[-1] = 10.0        # last month's crash is ignored
    assert m.momentum(closes) == pytest.approx(0.30)
    assert m.momentum(closes[:100]) is None


# ---------------------------------------------------------------- recipes
def test_recipe_rules():
    base = {"vol63": 0.15, "beta": 0.9, "mom": 0.2, "above_trend": True, "hedgeye": {}}
    assert m.score_fund("low_vol", base) == (True, -0.15, None)
    assert m.score_fund("low_vol", dict(base, vol63=None))[0] is False
    assert m.score_fund("low_beta", dict(base, beta=0.1))[0] is False
    assert m.score_fund("low_beta", base)[1] == -0.9
    assert m.score_fund("momentum", dict(base, above_trend=False))[0] is False
    assert m.score_fund("momentum", dict(base, hedgeye={"call": "Bearish"}))[0] is False
    assert m.score_fund("momentum", base)[1] == pytest.approx(0.2)
    assert m.score_fund("momentum", dict(base, hedgeye={"rr": "Bullish"}))[1] == pytest.approx(0.25)


def test_rank_ties_break_on_lower_swings_then_symbol():
    rows = [{"sym": "B", "score": 1, "vol63": 0.2}, {"sym": "A", "score": 1, "vol63": 0.2},
            {"sym": "C", "score": 1, "vol63": 0.1}, {"sym": "D", "score": 2, "vol63": 0.9}]
    assert [r["sym"] for r in m.rank_scored(rows)] == ["D", "C", "A", "B"]


# ---------------------------------------------------------------- weights and caps
def test_inverse_swing_weights():
    w = m.inverse_swing_weights({"A": 0.1, "B": 0.2})
    assert sum(w.values()) == pytest.approx(1.0) and w["A"] == pytest.approx(2 / 3)
    assert m.inverse_swing_weights({"A": None, "B": 0.2}) == {"A": 0.5, "B": 0.5}


def test_apply_caps_fund_and_area():
    w = m.apply_caps({"A": 0.7, "B": 0.1, "C": 0.1, "D": 0.1}, fund_cap=0.4)
    assert w["A"] == pytest.approx(0.4) and sum(w.values()) == pytest.approx(1.0)
    w = m.apply_caps({"A": 0.4, "B": 0.4, "C": 0.1, "D": 0.1}, 1.0, {"A": "x", "B": "x", "C": "y", "D": "z"}, 0.4)
    assert w["A"] + w["B"] <= 0.4 + 1e-9 and sum(w.values()) == pytest.approx(1.0)
    # too few funds: cap rises to 1/n
    assert m.apply_caps({"A": 0.9, "B": 0.1}, 0.2) == {"A": pytest.approx(0.5), "B": pytest.approx(0.5)}
    # small weights dropped
    assert "D" not in m.apply_caps({"A": 0.5, "B": 0.3, "C": 0.19, "D": 0.01}, 1.0, min_weight=0.03)


# ---------------------------------------------------------------- Quad and areas
def test_area_stance_default_override_and_rule():
    t = ["Bullish", "Bullish", "Bearish", "Bearish"]
    assert m.area_stance(t, [0.29, 0.71, 0, 0]) == pytest.approx(1.0)
    assert m.area_stance(t, [0, 0, 0.5, 0.5]) == pytest.approx(-1.0)
    assert m.area_stance(t, None, [2]) == 1.0
    assert m.area_stance(t, None, [1, 2]) == 1.0          # Bullish in all picked
    assert m.area_stance(t, None, [2, 3]) == -1.0         # Bearish in any picked
    assert m.area_stance(["Bullish", "Neutral", "Bullish", "Bullish"], None, [1, 2]) == 0.0
    assert m.area_stance(None, [1, 0, 0, 0]) is None
    assert [m.chip_of(x) for x in (0.3, 0.1, -0.3, None)] == ["B", "H", "S", "-"]


def _areas(stances, kept=None):
    kept = kept or {}
    return [{"name": n, "stance": s, "eligible": True, "kept_dollars": kept.get(n, 0.0)} for n, s in stances.items()]


def test_fill_areas_zeroes_sell_areas_and_adds_to_one():
    st = {"Tech": 1.0, "Fin": 1.0, "Util": -1.0, "Health": 0.0, "Energy": 0.0}
    r = m.fill_areas(_areas(st), "Equities", 100000)
    by = {x["name"]: x for x in r["rows"]}
    assert by["Util"]["fill"] == 0.0
    assert sum(x["fill"] for x in r["rows"]) == pytest.approx(1.0, abs=1e-5)
    assert by["Tech"]["fill"] > by["Health"]["fill"]
    assert by["Tech"]["fill"] <= 0.40 + 1e-9


def test_fill_areas_keeps_minimum_three_areas():
    st = {"A": -1.0, "B": -1.0, "C": -1.0, "D": -1.0, "E": 0.1}
    r = m.fill_areas(_areas(st), "Equities", 50000)
    assert sum(1 for x in r["rows"] if x["fill"] > 0) >= 3


def test_fill_areas_locks_and_over_100():
    st = {"A": 1.0, "B": 0.0, "C": 0.0, "D": 0.0}
    r = m.fill_areas(_areas(st), "Equities", 100000, {"A": 10})
    by = {x["name"]: x for x in r["rows"]}
    assert by["A"]["fill"] == pytest.approx(0.10) and by["A"]["locked"]
    assert sum(x["fill"] for x in r["rows"]) == pytest.approx(1.0, abs=1e-5)
    bad = m.fill_areas(_areas(st), "Equities", 100000, {"A": 70, "B": 50})
    assert "Locked areas add to" in bad["message"]


def test_fill_areas_kept_exceeds_area():
    st = {"Tech": 1.0, "Fin": 0.0, "Ind": 0.0, "Util": 0.0}
    r = m.fill_areas(_areas(st, {"Util": 60000}), "Equities", 100000)
    by = {x["name"]: x for x in r["rows"]}
    assert by["Util"]["fill"] == pytest.approx(0.6) and by["Util"]["buy_dollars"] == 0
    assert any("Kept holdings already exceed" in n for n in by["Util"]["notes"])
    assert sum(x["fill"] for x in r["rows"]) == pytest.approx(1.0, abs=1e-5)


def test_fill_areas_fixed_income_two_areas_no_fill():
    r = m.fill_areas(_areas({"Long": -1.0, "HY": 1.0}), "Fixed Income", 10000)
    assert [x["fill"] for x in r["rows"]] == [pytest.approx(0.5), pytest.approx(0.5)]


def test_horizon_quad_mix_blends_months_and_transition():
    d = date(2026, 10, 1)
    monthly = {(2026, 10): [0, 1, 0, 0], (2026, 11): [1, 0, 0, 0], (2026, 12): [1, 0, 0, 0]}
    r = m.horizon_quad_mix(d, 91, monthly, {}, "HOLDING", None)
    assert r["shares"][1] == pytest.approx(31 / 92, abs=0.02) and r["coverage_pct"] > 90
    t = m.horizon_quad_mix(d, 91, monthly, {}, "TRANSITION", 3)
    assert t["shares"][2] == pytest.approx(0.5, abs=1e-6)
    none = m.horizon_quad_mix(d, 91, {}, {}, None, None)
    assert none["shares"] is None
    # months with no monthly row fall back to the quarter's declared Quad
    q = m.horizon_quad_mix(d, 30, {}, {(2026, 4): 3}, "HOLDING", None)
    assert q["shares"][2] == pytest.approx(1.0)


# ---------------------------------------------------------------- mix
def test_quad_tilt_keeps_cash():
    out = m.quad_tilt_mix({"Equities": 60, "Fixed Income": 30, "Cash": 10}, {"Equities": 1.0, "Fixed Income": -1.0}, 0.25)
    assert out["Cash"] == 10 and sum(out.values()) == pytest.approx(100.0)
    assert out["Equities"] > 60 and out["Fixed Income"] < 30


def test_risk_dial_trim_and_floor():
    mix = {"Equities": 60, "Fixed Income": 30, "Cash": 10}
    out = m.risk_dial_trim(mix, 0.7)
    assert out["Equities"] == pytest.approx(42) and out["Cash"] == pytest.approx(28) and out["Fixed Income"] == 30
    kept = m.risk_dial_trim(mix, 0.7, {"Equities": 50})
    assert kept["Equities"] == pytest.approx(50)
    assert m.risk_dial_trim(mix, None) == mix
    fl = m.enforce_floors({"Equities": 20, "Fixed Income": 30, "Cash": 5}, {"Equities": 30})
    assert fl["Equities"] == 30 and fl["Cash"] == 0 and fl["Fixed Income"] == pytest.approx(25.0)


def test_normalise_mix_cash_is_the_rest():
    assert m.normalise_mix({"Equities": 60, "Fixed Income": 30})["Cash"] == pytest.approx(10)
    n = m.normalise_mix({"Equities": 90, "Fixed Income": 30})
    assert n["Cash"] == 0 and n["Equities"] + n["Fixed Income"] == pytest.approx(100)


def test_whole_shares_and_small_bucket_positions():
    assert m.whole_shares(1000, 333) == 3 and m.whole_shares(100, 333) == 0 and m.whole_shares(100, None) == 0
    assert m.positions_for_bucket("Equities", 8, 100000) == 8
    assert m.positions_for_bucket("Equities", 8, 20000) == 4


# ---------------------------------------------------------------- engine
def _fund(sym, bucket, area, price, vol, **kw):
    f = {"sym": sym, "bucket": bucket, "area": area, "outlook_cat": "Equity Sectors" if bucket == "Equities" else "Fixed Income",
         "outlook_sub": area, "eligible": True, "reason": None, "price": price, "vol63": vol, "beta": 1.0, "mom": 0.1,
         "above_trend": True, "hedgeye": {}, "styles": [], "final_code": None, "listed": True}
    f.update(kw)
    return f


def _ctx(**over):
    funds = {s["sym"]: s for s in [
        _fund("XLK", "Equities", "Technology", 200.0, 0.20), _fund("XLF", "Equities", "Financials", 40.0, 0.15),
        _fund("XLU", "Equities", "Utilities", 70.0, 0.12), _fund("XLE", "Equities", "Energy", 90.0, 0.25),
        _fund("XLV", "Equities", "Health", 140.0, 0.13), _fund("XLY", "Equities", "Discretionary", 180.0, 0.22),
        _fund("TLT", "Fixed Income", "Long Bond", 90.0, 0.14), _fund("LQD", "Fixed Income", "IG Credit", 105.0, 0.08),
        _fund("HYG", "Fixed Income", "HY Credit", 78.0, 0.07),
        _fund("GLD", "Gold", "Gold", 250.0, 0.15), _fund("SPY", "Equities", "Broad US", 500.0, 0.15)]}
    out_ = {("equity sectors", a.lower()): q for a, q in {
        "Technology": ["Bullish", "Bullish", "Bearish", "Bearish"], "Financials": ["Bullish", "Bullish", "Neutral", "Bearish"],
        "Utilities": ["Bearish", "Bearish", "Neutral", "Bullish"], "Energy": ["Neutral", "Neutral", "Bullish", "Neutral"],
        "Health": ["Neutral", "Neutral", "Neutral", "Neutral"], "Discretionary": ["Bearish", "Neutral", "Neutral", "Neutral"]}.items()}
    out_.update({("asset class", "equities"): ["Bullish"] * 4, ("asset class", "fixed income"): ["Bearish"] * 4})
    out_.update({("fixed income", "long bond"): ["Bearish"] * 4, ("fixed income", "ig credit"): ["Bullish"] * 4,
                 ("fixed income", "hy credit"): ["Neutral"] * 4})
    ctx = {"D": date(2026, 10, 23), "funds": funds, "outlook": out_, "quad": {"shares": [0.3, 0.7, 0, 0], "coverage_pct": 100.0, "weighted": []},
           "risk_mult": 0.7, "risk_label": "CAUTION", "kept": [],
           "presets": {"balanced": {"label": "Balanced 60/30/10", "mix": {"Equities": 60, "Fixed Income": 30, "Cash": 10}, "quad_tilt": None},
                       "quad_tilted": {"label": "Quad", "mix": {"Equities": 60, "Fixed Income": 30, "Cash": 10}, "quad_tilt": 0.25}},
           "account": {"value": 400000.0, "holdings": {}, "cash": 40000.0, "current_mix": {"Equities": 70.0, "Cash": 30.0}}}
    ctx.update(over)
    return ctx


REQ = {"preset": "balanced", "use_risk_dial": True, "skip_sells": True,
       "buckets": {"Equities": {"split": "area", "pick": "low_vol"}, "Fixed Income": {"split": "area", "pick": "core"}}}


def test_build_balanced_with_risk_dial():
    res = eng.build_positions(_ctx(), dict(REQ))
    assert res["mix_final"]["Equities"] == pytest.approx(42) and res["mix_final"]["Cash"] == pytest.approx(28)
    pos = {p["sym"]: p for p in res["positions"]}
    assert all(float(p["shares"]).is_integer() for p in pos.values())
    total = sum(p["value"] for p in res["positions"]) + res["cash"]["dollars"]
    assert total == pytest.approx(400000.0)
    assert "XLU" not in pos                                   # Utilities is a Sell area under this Quad mix
    assert "XLK" in pos and "LQD" in pos
    assert all(p["why"] for p in res["positions"])
    chips = {a["name"]: a["chip"] for a in res["buckets"]["Equities"]["areas"]}
    assert chips["Technology"] == "B" and chips["Utilities"] == "S"


def test_final_call_sell_is_information_only_when_building():
    ctx = _ctx()
    ctx["funds"]["XLV"]["final_code"] = "SS"
    req = dict(REQ, buckets={"Equities": {"split": "recipe", "recipe": "low_vol", "n": 4}, "Fixed Income": {"split": "core", "n": 3}})
    for r in (req, dict(req, skip_sells=True)):
        res = eng.build_positions(ctx, r)
        assert "XLV" in {p["sym"] for p in res["positions"]}
        assert not [s for s in res["skipped"] if s.get("final_code") == "SS"]
        assert any(p.get("conflict") for p in res["positions"] if p["sym"] == "XLV")   # shown as info only


def test_kept_holding_is_never_traded_or_bought_twice():
    ctx = _ctx(kept=["XLK"])
    ctx["account"]["holdings"] = {"XLK": {"qty": 100, "value": 20000.0, "price": 200.0, "bucket": "Equities", "area": "Technology", "cost": 15000.0}}
    res = eng.build_positions(ctx, dict(REQ))
    xlk = [p for p in res["positions"] if p["sym"] == "XLK"]
    assert len(xlk) == 1 and xlk[0]["is_kept"] and xlk[0]["shares"] == 100


def test_standard_fund_bucket_and_unavailable_goes_to_cash():
    ctx = _ctx()
    req = dict(REQ, preset="custom", mix={"Equities": 40, "Fixed Income": 30, "Gold": 10}, use_risk_dial=False)
    res = eng.build_positions(ctx, req)
    assert any(p["sym"] == "GLD" for p in res["positions"])
    ctx["funds"]["GLD"]["eligible"] = False
    res2 = eng.build_positions(ctx, req)
    assert not any(p["sym"] == "GLD" for p in res2["positions"]) and res2["cash"]["pct"] > 20


def test_zero_amount_and_missing_risk_dial():
    ctx = _ctx(risk_mult=None)
    ctx["account"]["value"] = 0
    assert eng.build_positions(ctx, dict(REQ))["positions"] == []
    ctx["account"]["value"] = 100000.0
    res = eng.build_positions(ctx, dict(REQ))
    assert any("Risk Dial unavailable" in n for n in res["notes"]) and res["mix_final"]["Equities"] == pytest.approx(60)


def test_quad_tilted_preset_changes_equities_share():
    res = eng.build_positions(_ctx(risk_mult=None), dict(REQ, preset="quad_tilted"))
    assert res["mix_target"]["Cash"] == pytest.approx(10) and res["mix_target"]["Equities"] != 60


# ---------------------------------------------------------------- vs account, drift
def test_vs_account_never_suggests_selling_what_the_model_skips():
    model = [{"sym": "XLK", "value": 8000.0, "price": 200.0, "area": "Tech", "bucket": "Equities"}]
    hold = {"XLK": {"value": 12000.0, "cost": 9000.0}, "NVDA": {"value": 9800.0, "cost": 4000.0}}
    r = eng.vs_account(model, hold, set(), "TAXABLE")
    rows = {x["sym"]: x for x in r["rows"]}
    assert rows["NVDA"]["trade"] == "Held, not in model" and rows["NVDA"]["gap"] is None
    assert rows["XLK"]["trade"].startswith("Sell 20 sh")
    assert r["tax"]["gain"] > 0
    kept_rows = {x["sym"]: x for x in eng.vs_account(model, hold, {"XLK"}, "IRA")["rows"]}
    assert kept_rows["XLK"]["trade"] == "Kept"
    assert eng.vs_account(model, hold, set(), "401K")["paper_only"] is True
    assert eng.vs_account(model, hold, set(), "IRA")["tax"] is None


def test_drift_table_flags_five_points():
    rows = eng.drift_table({"Equities": 42, "Cash": 28}, {"Equities": 43, "Cash": 28}, {"Equities": 71, "Cash": 10})
    by = {r["bucket"]: r for r in rows}
    assert by["Equities"]["amber"] and by["Cash"]["amber"] and by["Equities"]["gap"] == 29


# ---------------------------------------------------------------- paper marks, alerts, promise
def test_series_stats_and_worst_drop():
    vals = [101, 103, 99, 100, 104, 106]
    spy = [100, 101, 102, 101, 103, 104]
    s = m.series_stats(vals, spy, 100.0)
    assert s["ret"] == pytest.approx(0.06) and s["spy_ret"] == pytest.approx(0.04)
    assert s["worst_drop"] == pytest.approx(99 / 103 - 1)
    assert s["swings"] is not None


def test_alerts_fire_once_and_data_alerts_always_on():
    state = {"value": 85.0, "amount": 100.0, "quad_label": "TRANSITION", "risk_label": "NOT INVESTABLE",
             "positions": [{"sym": "A", "stale_days": 3, "move": 0.5, "final_side": "sell", "is_kept": False}]}
    none = m.evaluate_alerts({}, state)
    assert {a["code"] for a in none} == {"stale:A", "split:A"}
    allon = m.evaluate_alerts({"drop": True, "quad_turn": True, "no_new_risk": True, "final_call_sell": True}, state)
    assert {"drop", "quad_turn", "no_new_risk", "final_call_sell"} <= {a["code"] for a in allon}
    w = m.fire_once({}, allon, date(2026, 10, 23))
    n = len(w["fired"])
    assert len(m.fire_once(w, allon, date(2026, 10, 24))["fired"]) == n


def test_promise_check():
    stats = {"ret": 0.03, "spy_ret": 0.01, "swings": 0.09, "spy_swings": 0.13, "beta": 0.6}
    r = m.promise_check(["low_vol", "low_beta", "momentum"], True, stats, {"A": 0.05, "B": -0.01}, {"A": "B", "B": "H"}, ["HOLDING", "WATCH"])
    res = {i["label"]: i["result"] for i in r["items"]}
    assert all(v == "pass" for v in res.values()) and r["hit_rate"] == {"beat": 1, "of": 2}
    early = m.promise_check(["low_vol"], False, {"ret": 0.0, "spy_ret": 0.0, "swings": None, "spy_swings": None}, {}, {}, [])
    assert early["items"][0]["result"] == "pending"


# ---------------------------------------------------------------- back-test
def _bt_inputs(n):
    cal = [date(2025, 1, 1) + timedelta(days=i) for i in range(n)]
    closes = {}
    for k, sym in enumerate(["SPY", "XLK", "XLF", "XLU", "XLE", "XLV", "TLT", "LQD", "HYG"]):
        px, ser = 100.0 + k, {}
        for i, d in enumerate(cal):
            px *= 1 + (0.004 if (i + k) % 3 else -0.003) * (1 + k * 0.05)
            ser[d] = px
        closes[sym] = ser
    funds = {s: _fund(s, "Equities" if s.startswith("XL") or s == "SPY" else "Fixed Income", s, 100.0, None) for s in closes}
    return closes, funds


def test_backtest_counts_periods_honestly():
    closes, funds = _bt_inputs(400)
    ctx = {"outlook": {}, "presets": {"balanced": {"mix": {"Equities": 60, "Fixed Income": 30, "Cash": 10}}},
           "quad_inputs": {"monthly": {}, "quarterly": {}}}
    req = {"preset": "balanced", "buckets": {"Equities": {"split": "recipe", "recipe": "low_vol", "n": 4},
                                              "Fixed Income": {"split": "core", "n": 3}}}
    r = eng.backtest(closes, {}, funds, ctx, req, "1M")
    s = r["summary"]
    assert s["periods"] >= 6 and s["message"] is None
    assert s["periods_total"] >= s["periods"]
    long_ = eng.backtest(closes, {}, funds, ctx, req, "12M")
    assert long_["summary"]["periods"] < 3 and long_["summary"]["message"]
    short = _bt_inputs(60)
    none = eng.backtest(short[0], {}, short[1], ctx, req, "3M")
    assert none["summary"]["periods"] == 0 and none["summary"]["message"] == "Not enough history yet"


def test_backtest_area_mode_without_quad_history_says_so():
    closes, funds = _bt_inputs(300)
    ctx = {"outlook": {}, "presets": {"balanced": {"mix": {"Equities": 60, "Fixed Income": 30, "Cash": 10}}},
           "quad_inputs": {"monthly": {}, "quarterly": {}}}
    req = {"preset": "balanced", "buckets": {"Equities": {"split": "area", "pick": "low_vol"}, "Fixed Income": {"split": "area"}}}
    r = eng.backtest(closes, {}, funds, ctx, req, "1M")
    assert r["summary"]["periods"] == 0 and r["summary"]["message"] == "Not enough Quad history"


# ---------------------------------------------------------------- misc
def test_add_months_clamps_end_of_month():
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2026, 10, 23), 3) == date(2027, 1, 23)
    assert add_months(date(2026, 10, 23), 12) == date(2027, 10, 23)


def test_final_call_sides():
    assert m.final_call_side("SS") == "sell" and m.final_call_side("BM") == "buy" and m.final_call_side("HOLD") == "neutral"
    assert m.final_call_side(None) == "neutral"


# ---------------------------------------------------------------- source pool + validation checks
POOL_REQ = {"preset": "balanced", "use_risk_dial": False, "skip_sells": True, "sources": ["PS", "II"],
            "buckets": {"Equities": {"split": "recipe", "recipe": "low_vol", "n": 4}}}


def test_source_bullish_rules_per_source():
    from etl import builder_data as bd
    assert bd.source_bullish("PS", None, None, None) and bd.source_bullish("GOANY", None, None, None)
    assert bd.source_bullish("II", "Long", None, None) and not bd.source_bullish("II", "Bearish", None, None)
    assert bd.source_bullish("RR", "Bullish", None, None) and not bd.source_bullish("RR", "DROPPED", None, None)
    assert bd.source_bullish("CALL", None, 2, None) and not bd.source_bullish("CALL", "Bearish", -1, None)
    assert bd.source_bullish("SSS", None, None, 2) and not bd.source_bullish("SSS", None, None, -1)


def test_pool_trim_mix_moves_empty_bucket_share_keeps_cash():
    mix, dropped = eng.pool_trim_mix({"Equities": 60.0, "Fixed Income": 30.0, "Cash": 10.0}, {"Equities"})
    assert dropped == ["Fixed Income"] and mix == {"Equities": pytest.approx(90.0), "Cash": 10.0}
    mix, dropped = eng.pool_trim_mix({"Equities": 60.0, "Cash": 40.0}, set())
    assert mix == {"Cash": 100.0}


def test_low_beta_check_removes_high_beta_names_and_says_why():
    ctx = _ctx()
    ctx["funds"]["XLK"]["beta"] = 1.4
    ctx["funds"]["XLU"]["beta"] = 0.4
    base = eng.build_positions(ctx, dict(POOL_REQ))
    chk = eng.build_positions(ctx, dict(POOL_REQ, checks=["low_beta"]))
    assert "XLK" not in {x["sym"] for x in chk["positions"]}
    skipped = {s["sym"]: s for s in chk["skipped"] if s.get("kind") == "check"}
    assert "XLK" in skipped and "beta 1.40" in skipped["XLK"]["reason"]
    assert chk["checks"] == ["low_beta"] and base["checks"] == []


def test_quad_check_drops_sell_areas_only():
    ctx = _ctx()     # shares Q2 70%: Utilities Bearish in Q1/Q2 -> Sell area; Health neutral -> kept
    res = eng.build_positions(ctx, dict(POOL_REQ, checks=["quad"]))
    removed = {s["sym"] for s in res["skipped"] if s.get("kind") == "check"}
    assert "XLU" in removed and "XLV" not in removed


def test_pool_mode_uses_recipe_for_every_bucket_and_never_picks_benchmark():
    ctx = _ctx()
    ctx["funds"]["SPY"].update(eligible=False, reason="Benchmark only")
    res = eng.build_positions(ctx, dict(POOL_REQ))
    assert "SPY" not in {x["sym"] for x in res["positions"]}
    assert all(u["sym"] != "SPY" for u in res["unavailable"])
    assert res["pool_mode"] is True
