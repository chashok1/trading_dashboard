"""Plain-English "Why this action" card (etl/why_card.py) + the Technical stage trail (etl/technical_why.py::technical_trail).

Pure Python, no DB. Asserts behaviour (which verdict / which step tone / which near-miss), not point-in-time database values.
"""
from etl.derive_actionable import _compute_final_call
from etl.technical_why import technical_trail
from etl.why_card import build_why_card

# A bullish-trend stock with NO range-position setup: the situation behind "sources say buy, Technical says nothing".
NO_SIGNAL = dict(td_tn_bb_rr_action=None, trend_trade_rule=4, bb_rng_strk_rule=4, bb_desc="Buy PuBks/Hld Lng", last=207.82, trade_line=168.05,
                 trend_line=80, high=223.7, lrr=193.97, trr=222.76, prev_trr=216.19, perf1d=-2, pct_change=-4.28, lrr_idx_eff=1, mrr_idx=0,
                 trr_idx=0, macd_dir=1, macdh_dir=1, trade_rule=3, pullback=0.10)


def _ctx(**kw):
    fc = _compute_final_call(kw.pop("consolidated", "INCREASE"), kw.pop("rr_action", None), kw.get("held_today", False), 0, 1000)
    base = dict(sources=[{"source": "SSS", "action": "INCREASE", "reason": "rising"}, {"source": "CALL", "action": "ADD", "reason": "weight +3"}],
                winning_source="SSS", rr_action=None, trail=technical_trail(NO_SIGNAL), held_today=False, held_dollar=0, fc=fc, groups=[])
    base.update(kw)
    return base


def test_trail_stages_for_a_bullish_stock_with_no_setup():
    t = technical_trail(NO_SIGNAL)
    assert t["signal"] is False
    assert [s["ok"] for s in t["stages"]] == [True, True, None]
    assert "No Step 3 rule matched" in t["stages"][2]["text"]


def test_trail_names_the_near_miss_and_what_it_lacks():
    flips = technical_trail(NO_SIGNAL)["flip"]
    assert flips and all(f["missing"] for f in flips)
    # the bounce-at-LRR rule (3x) missed only because the day's low never reached the LRR zone
    bounce = [f for f in flips if f["name"].startswith("bounce at LRR")]
    assert bounce and any("LRR zone" in m for m in bounce[0]["missing"])


def test_trail_below_both_lines_is_a_step1_sell_stage_and_still_reaches_step3():
    d = dict(NO_SIGNAL, trend_trade_rule=-2, step1_id="S1-b")
    st = technical_trail(d)["stages"]
    assert st[0]["ok"] is False and st[0]["step"] == "S1-b" and st[0]["action"] == "Sell All" and st[0]["dir"] == -1
    assert st[-1]["name"] == "Range position"   # Step 3 now runs for every stock


def test_card_unheld_buy_with_no_technical_signal_is_hold_and_explains_why():
    card = build_why_card(_ctx())
    assert card["verdict"] == "HOLD"
    assert [s["key"] for s in card["steps"]] == ["sources", "technical", "rules"]
    assert card["steps"][0]["tone"] == "buy" and card["steps"][1]["text"] == "No signal"
    assert "NEW position needs Technical to confirm" in card["result"]
    assert card["flip"]


def test_card_held_stock_wording_differs():
    card = build_why_card(_ctx(held_today=True, held_dollar=5000))
    assert "already have a position" in card["result"]


def test_card_sources_mixed_when_they_disagree():
    ctx = _ctx(sources=[{"source": "SSS", "action": "INCREASE"}, {"source": "II", "action": "REDUCE"}])
    assert build_why_card(ctx)["steps"][0]["tone"] == "warn"


def test_card_rules_step_flags_mixed_groups():
    ctx = _ctx(groups=[{"action": "BS"}, {"action": "SS"}], trig_action="SS", low_confidence=True)
    rules = [s for s in build_why_card(ctx)["steps"] if s["key"] == "rules"][0]
    assert rules["tone"] == "warn" and "mixed" in rules["text"]
    assert any("Low confidence" in l["text"] for l in rules["lines"])


def test_card_stop_breach_is_explained():
    fc = _compute_final_call("INCREASE", "BS", True, 5000, 1000, stop_breached=True)
    card = build_why_card(_ctx(fc=fc, held_today=True, held_dollar=5000, stop_breached=True, stop_signal="TD SA", rr_action="BS"))
    assert "below its stop" in card["result"] and card["steps"][2]["tone"] == "warn"


def test_every_final_call_branch_has_a_reason_code():
    cases = [("", None, False), ("REMOVE", None, False), ("REMOVE", None, True), ("REDUCE", None, False), ("INCREASE", "SS", True),
             ("REDUCE", "SS", True), ("INCREASE", "SS", False), ("REDUCE", "BS", True), ("ADD", "BS", False), ("INCREASE", "BS", True),
             ("REDUCE", None, True), ("INCREASE", None, False)]
    for ca, rr, held in cases:
        assert _compute_final_call(ca, rr, held, 0, 1000)["fc_reason"], (ca, rr, held)


def test_sss_weight_drop_is_a_warning_not_a_vote():
    srcs = [{"source": "CALL", "action": "ADD", "reason": "x"},
            {"source": "SSS", "action": "REDUCE", "reason": "pct_delta falling", "warning_only": True}]
    step = build_why_card(_ctx(sources=srcs, winning_source="CALL"))["steps"][0]
    assert step["tone"] == "buy"
    assert any("Warning only" in l["text"] for l in step["lines"])


def test_bearish_bollinger_is_a_warning_not_a_sell_stage():
    t = technical_trail(dict(NO_SIGNAL, bb_rng_strk_rule=-3, bb_desc="Cnfm Bear Trnd Less"))
    bb = t["stages"][1]
    assert bb["ok"] is None and bb["warn"] is True and "warning" in bb["text"] and "not a sell" in bb["text"]
    card = build_why_card(_ctx(trail=t))
    assert any(l.get("warn") for l in card["steps"][1]["lines"])


def test_falling_top_or_bottom_band_is_a_warning_only():
    for top, bot in ((-5.0, 1.0), (1.0, -5.0)):
        t = technical_trail(dict(NO_SIGNAL, bb_rng_strk_rule=2, bb_top_slope=top, bb_bot_slope=bot))
        bb = [s for s in t["stages"] if s["name"] == "Bollinger bands"]
        assert len(bb) == 1 and bb[0].get("warn") is True and "warning only" in bb[0]["text"]
    t = technical_trail(dict(NO_SIGNAL, bb_rng_strk_rule=2, bb_top_slope=1.0, bb_bot_slope=0.5))
    assert not any(s.get("warn") for s in t["stages"])


def test_bounce_exception_adds_a_below_trade_warning_and_carries_on_to_the_range_stage():
    d = dict(NO_SIGNAL, trend_trade_rule=1, step1_id="1d", bounce_exempt=True, last=75.08, trade_line=86.75, trend_line=45.0,
             bb_rng_strk_rule=-1, td_tn_bb_rr_action=10, macdh_dir=1)
    t = technical_trail(d)
    first = t["stages"][0]
    assert first["warn"] is True and "below Trade" in first["text"] and "sell was skipped" in first["text"]
    assert [s["name"] for s in t["stages"]][:2] == ["Trend & Trade", "Bollinger bands"] and len(t["stages"]) == 3


def test_falling_band_no_longer_ends_the_trail_before_range_position():
    t = technical_trail(dict(NO_SIGNAL, bb_rng_strk_rule=-3, bb_desc="Cnfm Bear Trnd Less"))
    assert t["stages"][-1]["name"] == "Range position"


def test_reclaim_buy_names_the_line_and_is_low_confidence():
    d = dict(NO_SIGNAL, td_tn_bb_rr_action=9, reclaim_buy=True, reclaim_line=200.59, last=209.73, trend_line=129.02)
    t = technical_trail(d)
    assert t["signal"] is True
    last = t["stages"][-1]
    assert last["name"] == "Range position" and "200.59" in last["text"] and "209.73" in last["text"]


def test_sources_step_is_one_summary_line_naming_who_drove_it():
    srcs = [{"source": "TOP5", "action": "INCREASE", "reason": "r", "snapshot_date": "2026-10-13"},
            {"source": "CALL", "action": "ADD", "reason": "r", "snapshot_date": "2026-10-20"}]
    ctx = _ctx(sources=srcs, winning_source="TOP5", consolidated="INCREASE")
    ctx["fc"] = {"final_side": "buy", "fc_reason": "tech_buy"}
    step = build_why_card(ctx)["steps"][0]
    assert step["lines"] == [] and "TOP5 drove it" in step["text"] and "2 sources agree" in step["text"]


def test_position_step_only_shows_when_it_adds_something():
    plain = build_why_card(_ctx(held_today=True, held_dollar=5000))
    assert "position" not in [s["key"] for s in plain["steps"]]
    flagged = build_why_card(_ctx(held_today=True, held_dollar=5000, suppressed="ALREADY ESTABLISHED"))
    assert "position" in [s["key"] for s in flagged["steps"]]
