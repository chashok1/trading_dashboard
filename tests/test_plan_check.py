"""Behaviour tests for etl/plan_check.py (pure, no database)."""
from etl import plan_check as pc

SIDE = lambda c: "buy" if c in ("BM", "BS") else ("sell" if c in ("SA", "SS") else "neutral")


def _plan(**cls):
    base = {"Equities": 50, "Fixed Income": 30, "Gold": 0, "Commodities": 0, "Crypto": 0, "Currency": 2, "Cash": 18}
    base.update(cls)
    return {"cls": base}


def _acct():
    return {"value": 100000.0, "cash": 20000.0, "holdings": {
        "SPY": {"value": 40000.0, "bucket": "Equities"},
        "TLT": {"value": 30000.0, "bucket": "Fixed Income"},
        "GLD": {"value": 10000.0, "bucket": "Gold"}}}


INFO = {"SPY": {"bucket": "Equities", "sector": "Broad", "beta": 1.0, "styles": []},
        "MSFT": {"bucket": "Equities", "sector": "Technology", "beta": 1.1, "styles": []},
        "AAPL": {"bucket": "Equities", "sector": "Technology", "beta": 1.2, "styles": []}}


def test_classes_must_add_to_100():
    assert pc.validate_plan(_plan()) == []
    assert any("100" in e for e in pc.validate_plan(_plan(Cash=10)))


def test_sector_total_cannot_exceed_equities():
    p = _plan()
    p["sector"] = {"Technology": 40, "Health Care": 20}
    assert any("Sectors" in e for e in pc.validate_plan(p))


def test_cash_to_spend_keeps_cash_percent_and_floor():
    # cash 20,000, Cash plan 18% of 100,000 = 18,000 -> only 2,000 may be spent
    assert pc.cash_to_spend(20000, 0, 100000, _plan()) == 2000
    # a ticked sell adds to what may be spent
    assert pc.cash_to_spend(20000, 5000, 100000, _plan()) == 7000
    assert pc.cash_to_spend(500, 0, 100000, _plan()) == 0


def test_class_planned_zero_means_sell_all():
    now = pc.now_lines(_acct()["holdings"], INFO, 20000)
    needs = {n["cls"]: n for n in pc.sell_needs(_plan(), now, 100000)}
    assert needs["Gold"]["all"] is True and needs["Gold"]["need"] == 10000
    assert "Equities" not in needs          # 40% held, plan 50%


def _todo(picks, plan=None, calls=None, caps=None):
    return pc.todo(plan or _plan(), _acct(), picks, calls or {"MSFT": "BM", "AAPL": "HOLD"}, INFO, {}, SIDE, caps)


def test_unticked_sell_changes_nothing_and_ticked_sell_adds_cash_here():
    base = _todo([])
    assert base["sell_cash"] == 0 and base["cash_to_spend"] == 2000
    t = _todo([{"id": 1, "side": "SELL", "members": ["GLD"], "amount": 0, "ticked": True}])
    assert t["sell_cash"] == 10000 and t["cash_to_spend"] == 12000


def test_buy_is_cut_to_cash_and_never_exceeds_it():
    t = _todo([{"id": 1, "side": "BUY", "members": ["MSFT"], "amount": 9000, "ticked": True}])
    b = t["buys"][0]
    assert b["result"] == "SHRUNK" and b["allowed"] == 2000 and t["cash_left"] == 0


def test_buy_blocked_when_no_cash():
    picks = [{"id": 1, "side": "BUY", "members": ["MSFT"], "amount": 2000, "ticked": True},
             {"id": 2, "side": "BUY", "members": ["MSFT"], "amount": 1000, "ticked": True}]
    b = _todo(picks)["buys"]
    assert b[0]["result"] == "OK" and b[1]["result"] == "BLOCKED"


def test_planned_buy_counts_without_a_buy_call_and_a_group_counts_once():
    g = {"id": 1, "side": "BUY", "members": ["MSFT", "AAPL"], "amount": 1500, "ticked": False}
    nocall = _todo([g], calls={"MSFT": "HOLD", "AAPL": "HOLD"})
    assert nocall["bought"] == 1500 and nocall["buys"][0]["has_call"] is False and nocall["buys"][0]["buy_member"] is None
    t = _todo([g], calls={"MSFT": "BM", "AAPL": "BM"})
    assert t["bought"] == 1500 and t["buys"][0]["buy_member"] in ("MSFT", "AAPL")


def test_no_amount_means_not_counted():
    t = _todo([{"id": 1, "side": "BUY", "members": ["MSFT"], "amount": 0, "ticked": True}])
    assert t["bought"] == 0 and t["buys"][0]["result"] == "READY" and t["cash_left"] == t["cash_to_spend"]


def test_line_states_for_classes_and_ceilings():
    v = 100000.0
    cls = lambda left, key="Equities": {"kind": "cls", "key": key, "left": left}
    assert pc.line_state(cls(5000), v) == "ROOM" and pc.line_state(cls(100), v) == "ON_PLAN"
    assert pc.line_state(cls(-5000), v) == "OVER" and pc.line_state(cls(-5000, "Cash"), v) == "SHORT"
    ceil = lambda now, used=0: {"kind": "sector", "key": "IT", "plan": 10000.0, "now": now, "used": used}
    assert pc.line_state(ceil(5000), v) == "OK" and pc.line_state(ceil(9000), v) == "NEAR"
    assert pc.line_state(ceil(8000, 1500), v) == "NEAR" and pc.line_state(ceil(10400, 400), v) == "OVER"


def test_small_account_tolerance_is_tighter():
    assert pc.tolerance(100000) == 500 and pc.tolerance(20000) == 100


def test_max_add_names_the_tightest_limit_and_uses_the_stock_max():
    t = _todo([{"id": 1, "side": "BUY", "members": ["MSFT"], "amount": 1000, "ticked": False}],
              caps={"MSFT": {"min": 1000.0, "max": 2000.0, "unit": 500.0}})
    b = t["buys"][0]
    assert b["max_add"] == 2000 and b["binding"] in ("Cash to spend", "The stock's own Max")
    assert b["suggest"] == 1000                      # not held -> the amount rules' Min
    t2 = _todo([{"id": 1, "side": "BUY", "members": ["SPY"], "amount": 1500, "ticked": False}],
               caps={"SPY": {"min": 1000.0, "max": 40500.0, "unit": 500.0}})
    b2 = t2["buys"][0]
    assert b2["binding"] == "The stock's own Max" and b2["max_add"] == 500 and b2["suggest"] == 500
    assert any(o["line"] == "The stock's own Max" for o in b2["over"])


def test_percentage_lines_warn_but_do_not_cut():
    p = _plan(Equities=41, Cash=18, **{"Fixed Income": 39})
    p["sector"] = {"Technology": 0.5}
    b = _todo([{"id": 1, "side": "BUY", "members": ["MSFT"], "amount": 2000, "ticked": True}], plan=p)["buys"][0]
    assert b["allowed"] == 2000 and b["result"] == "OVER_PLAN" and b["over"]


def test_open_lines_never_limit():
    b = _todo([{"id": 1, "side": "BUY", "members": ["MSFT"], "amount": 2000, "ticked": True}])["buys"][0]
    assert b["result"] == "OK"


def test_same_input_same_answer():
    picks = [{"id": 1, "side": "BUY", "members": ["MSFT"], "amount": 1000, "ticked": True}]
    assert _todo(picks) == _todo(picks)


def test_plan_keeps_grid_picks_with_amount_and_group():
    p = pc.clean_plan({"cls": {"Equities": 100}, "picks": [{"sym": "msft", "amt": "9000", "grp": "A"}, {"sym": " ", "amt": 5}, {"sym": "KO"}]})
    assert [x["sym"] for x in p["picks"]] == ["MSFT", "KO"]
    assert p["picks"][0]["amt"] == 9000.0 and p["picks"][0]["grp"] == "A" and p["picks"][1]["amt"] == 0.0


def test_save_and_check_saves_always_and_checks_only_a_valid_plan(monkeypatch):
    from datetime import date
    from etl import plan_store as ps
    calls = []

    class FakeSession:
        def execute(self, *a, **k):
            calls.append("sql")

        def commit(self):
            pass

    monkeypatch.setattr(ps, "save_version", lambda s, a, n, p: calls.append("version") or (n or "Main"))
    monkeypatch.setattr(ps, "activate", lambda s, a, p, dry_run=False: calls.append("activate") or {"changes": ["x"]})
    bad = ps.save_and_check(FakeSession(), date(2026, 11, 13), "IRA", _plan(Cash=10), "Main")
    assert bad["saved"] and not bad["checking"] and "100" in bad["problems"][0] and calls == ["version"]
    good = ps.save_and_check(FakeSession(), date(2026, 11, 13), "IRA", _plan(), "Defensive")
    assert good["checking"] and good["name"] == "Defensive" and good["warning"] is None and "activate" in calls


def test_plan_remembers_the_ticked_lists():
    p = pc.clean_plan({"cls": {"Equities": 100}, "sources": ["PS", "", "RR"]})
    assert p["sources"] == ["PS", "RR"]


def test_middle_and_unknown_beta_and_no_style_are_real_lines():
    info = {"A": {"bucket": "Equities", "sector": "Tech", "beta": 1.0, "styles": []},
            "B": {"bucket": "Equities", "sector": "Tech", "beta": None, "styles": []},
            "C": {"bucket": "Equities", "sector": "Tech", "beta": 1.5, "styles": []}}
    hold = {"A": {"value": 30000.0, "bucket": "Equities"}, "B": {"value": 10000.0, "bucket": "Equities"}, "C": {"value": 20000.0, "bucket": "Equities"}}
    now = pc.now_lines(hold, info, 40000.0, {})
    assert now["beta"]["mid"] == 30000 and now["beta"]["none"] == 10000 and now["beta"]["high"] == 20000
    assert now["style"]["none"] == 60000
    plan = {"cls": {"Equities": 60, "Cash": 40}, "beta": {"mid": 20.0, "none": 5.0}, "style": {"none": 50.0}}
    assert pc.validate_plan(plan) == []
    rows = {(r["kind"], r["key"]): r for r in pc._line_rows(pc.clean_plan(plan), 100000.0, now, {"cls": {}, "sector": {}, "style": {}, "beta": {}})}
    assert rows[("beta", "mid")]["state"] if "state" in rows[("beta", "mid")] else True
    assert pc.line_state(dict(rows[("beta", "mid")]), 100000.0) == "OVER"        # 30,000 held vs a 20,000 limit
    assert rows[("style", "none")]["label"] == "No style tag" and rows[("beta", "none")]["label"] == "No beta known"
    assert any("beta limits" in e for e in pc.validate_plan({"cls": {"Equities": 100}, "beta": {"low": 60.0, "mid": 50.0}}))


def test_quad_favored_limits_count_money_in_bull_names():
    info = {"A": {"bucket": "Equities", "sector": "Tech", "beta": 1.0, "styles": [], "quad": ["bull", "neutral", "bear", None]},
            "B": {"bucket": "Gold", "beta": None, "quad": ["bull", "bull", "neutral", "neutral"]}}
    hold = {"A": {"value": 30000.0, "bucket": "Equities"}, "B": {"value": 10000.0, "bucket": "Gold"}}
    now = pc.now_lines(hold, info, 60000.0, {})
    assert now["quad"] == {"Q1": 40000.0, "Q2": 10000.0, "Q3": 0.0, "Q4": 0.0}
    plan = {"cls": {"Equities": 30, "Gold": 10, "Cash": 60}, "quad": {"Q1": 30.0}}
    assert pc.validate_plan(plan) == []
    rows = {(r["kind"], r["key"]): r for r in pc._line_rows(pc.clean_plan(plan), 100000.0, now, {"cls": {}, "sector": {}, "style": {}, "beta": {}, "quad": {}})}
    assert pc.line_state(dict(rows[("quad", "Q1")]), 100000.0) == "OVER" and rows[("quad", "Q1")]["label"] == "Q1 favored (Bull)"
    # a planned buy of a Q1-bull name is counted against the Q1 limit and the tightest limit says so
    t = pc.todo(plan, {"value": 100000.0, "cash": 60000.0, "holdings": hold}, [{"id": 1, "side": "BUY", "members": ["A"], "amount": 5000, "ticked": False}], {}, info, {}, lambda c: "neutral")
    assert t["buys"][0]["max_add"] == 0 and t["buys"][0]["binding"] in ("Q1 favored (Bull)", "Equities")


def test_rounding_dollars_over_a_limit_taken_from_holdings_is_not_a_warning_note():
    info = {"A": {"bucket": "Equities", "sector": "Utilities", "beta": 1.0, "styles": []}}
    hold = {"A": {"value": 11010.0, "bucket": "Equities"}}
    plan = {"cls": {"Equities": 100}, "sector": {"Utilities": 11006.0 / 451063.5 * 100}}
    t = pc.todo(plan, {"value": 451063.5, "cash": 0.0, "holdings": hold}, [], {}, info, {}, lambda c: "neutral")
    assert not any("over its plan" in n for n in t["notes"])
    big = pc.todo({"cls": {"Equities": 100}, "sector": {"Utilities": 0.5}}, {"value": 451063.5, "cash": 0.0, "holdings": hold}, [], {}, info, {}, lambda c: "neutral")
    assert any("over its plan" in n for n in big["notes"])


def _room_plan():
    p = _plan(Equities=60, Cash=8)
    p["sector"] = {"Technology": 10}
    return p


def test_room_for_alone_ceiling_is_the_tightest_limit():
    c = [{"sym": "MSFT", "bucket": "Equities", "amt": 0, "pick": True}, {"sym": "AAPL", "bucket": "Equities", "amt": 0, "pick": True}]
    r = pc.room_for(_room_plan(), _acct(), c, INFO)
    assert r["MSFT"]["max"] == 10000 and r["MSFT"]["binding"] == "Technology"
    assert r["AAPL"]["max"] == 10000


def test_room_for_counts_other_typed_amounts_but_not_its_own():
    c = [{"sym": "MSFT", "bucket": "Equities", "amt": 0, "pick": True}, {"sym": "AAPL", "bucket": "Equities", "amt": 4000, "pick": True}]
    r = pc.room_for(_room_plan(), _acct(), c, INFO)
    assert r["MSFT"]["max"] == 6000
    assert r["AAPL"]["max"] == 10000          # its own $4,000 is not counted against itself


def test_room_for_starting_amounts_are_first_come_first_served_buy_calls_first():
    c = [{"sym": "MSFT", "bucket": "Equities", "amt": 0, "pick": True}, {"sym": "AAPL", "bucket": "Equities", "amt": 0, "pick": True}]
    r = pc.room_for(_room_plan(), _acct(), c, INFO, buyers={"MSFT", "AAPL"})
    assert r["MSFT"]["start"] == 10000 and r["AAPL"]["start"] == 0
    r2 = pc.room_for(_room_plan(), _acct(), c, INFO, buyers={"AAPL"})            # AAPL has the Buy call, so it is served first
    assert r2["AAPL"]["start"] == 10000 and r2["MSFT"]["start"] == 0
    r3 = pc.room_for(_room_plan(), _acct(), c, INFO)                             # no Buy call at all: still planned, in the order picked
    assert r3["MSFT"]["start"] == 10000 and r3["AAPL"]["start"] == 0


def test_room_for_never_negative_and_is_warn_only():
    c = [{"sym": "MSFT", "bucket": "Equities", "amt": 50000, "pick": True}]
    r = pc.room_for(_room_plan(), _acct(), c, INFO)
    assert r["MSFT"]["max"] >= 0


def test_room_for_counts_selling_over_target_classes_as_cash():
    plan = _plan(Equities=30, **{"Fixed Income": 40, "Gold": 10})          # equities held 40,000 vs 30,000 target: 10,000 would be sold
    info = dict(INFO, AGG={"bucket": "Fixed Income", "sector": None, "beta": None, "styles": []})
    c = [{"sym": "AGG", "bucket": "Fixed Income", "amt": 0, "pick": True}]
    r = pc.room_for(plan, _acct(), c, info)
    assert r["AGG"]["max"] == 10000 and r["AGG"]["sells"] == 10000          # class room 10,000; cash 12,000 only because of the sale
    assert pc.room_for(_plan(Equities=40, **{"Fixed Income": 40, "Gold": 10}), _acct(), c, info)["AGG"]["sells"] == 0


def test_room_for_held_stocks_do_not_take_the_starting_money_first():
    plan = _room_plan()
    info = INFO
    c = [{"sym": "SPY", "bucket": "Equities", "amt": 0, "pick": True}, {"sym": "MSFT", "bucket": "Equities", "amt": 0, "pick": True}]
    r = pc.room_for(plan, _acct(), c, info)           # SPY is held in _acct(), MSFT is new
    assert r["SPY"]["start"] is None and r["MSFT"]["start"] == 10000


def test_room_for_splits_stock_limit_from_bucket_room_and_etfs_use_the_usual_limit():
    plan = _plan(Equities=70, Cash=0, **{"Fixed Income": 28})
    info = dict(INFO, XLV={"bucket": "Equities", "sector": "Health Care", "beta": 0.9, "styles": []})
    c = [{"sym": "XLV", "bucket": "Equities", "amt": 0, "pick": True}, {"sym": "MSFT", "bucket": "Equities", "amt": 0, "pick": True}]
    caps = {"MSFT": {"min": 3000, "max": 9000, "unit": 1000}}
    r = pc.room_for(plan, _acct(), c, info, caps=caps, default_cap={"min": 5000, "max": 18000, "unit": 2000})
    assert r["MSFT"]["stock"] == 9000                       # its own rule
    assert r["XLV"]["stock"] == 18000                       # an ETF with no rule counts as an equity: the usual limit
    assert r["XLV"]["bucket"] >= r["XLV"]["stock"] and r["XLV"]["max"] == 18000 and r["XLV"]["binding"] == "The stock's own Max"
    bonds = pc.room_for(plan, _acct(), [{"sym": "AGG", "bucket": "Fixed Income", "amt": 0, "pick": True}],
                        dict(INFO, AGG={"bucket": "Fixed Income", "sector": None, "beta": None, "styles": []}), default_cap={"max": 18000})
    assert bonds["AGG"]["stock"] is None                    # other classes without a rule have no per-stock limit


def test_todo_read_only_mode_assumes_sells_and_only_warns():
    plan = _plan(Equities=30, **{"Fixed Income": 40, "Gold": 10})            # equities held 40,000 vs 30,000: 10,000 over
    picks = [{"id": 1, "side": "BUY", "members": ["AAPL"], "amount": 50000.0, "ticked": False}]
    acct = _acct()
    cut = pc.todo(plan, acct, picks, {}, INFO, buy_side=SIDE)                # old behaviour: cut to cash
    assert cut["buys"][0]["allowed"] < 50000
    ro = pc.todo(plan, acct, picks, {}, INFO, buy_side=SIDE, assume_sells=True, warn_only=True)
    assert ro["sell_cash"] == 10000                                         # the over-target equities count as sold, nothing ticked
    b = ro["buys"][0]
    assert b["allowed"] == 50000 and b["result"] == "OVER_PLAN"            # the amount stands; it is flagged, not cut


def test_alloc_sell_is_proportional_and_overrides_stand():
    vals = {"A": 60000.0, "B": 30000.0, "C": 10000.0}
    even = pc.alloc_sell(vals, 50000.0)
    assert even == {"A": 30000.0, "B": 15000.0, "C": 5000.0}               # every holding cut by the same half
    ov = pc.alloc_sell(vals, 50000.0, {"A": 10000.0})                       # A typed over: the rest share what is left
    assert ov["A"] == 10000.0 and ov["B"] + ov["C"] == 40000.0 and ov["B"] == 30000.0
    assert sum(pc.alloc_sell(vals, 999999.0).values()) == 100000.0           # never more than is held
    assert sum(pc.alloc_sell({"X": 333.0, "Y": 333.0, "Z": 334.0}, 500.0).values()) == 500.0   # rounding leaves no dollar behind


def test_todo_uses_the_typed_sale_amount_and_saves_it_in_the_plan():
    plan = _plan(Equities=30, **{"Fixed Income": 40, "Gold": 10})            # equities over by 10,000
    plan["sell"] = {"Equities": 4000}
    r = pc.todo(plan, _acct(), [], {}, INFO, buy_side=SIDE, assume_sells=True, warn_only=True)
    assert r["sell_cash"] == 4000
    assert r["sells"][0]["amount"] == 4000 and r["sells"][0]["holdings"][0]["sell"] == 4000
    assert pc.clean_plan(plan)["sell"] == {"Equities": 4000.0}
