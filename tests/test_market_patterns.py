"""
tests/test_market_patterns.py -- TASK_133 Phase 8.2.

Pure-Python, no DB. Covers etl/derive_market_event.py::_pattern_events (6 of
the 8 seeded ref_market_pattern conditions that are pure functions of
z-scores) and _vol_zone (the crossing-not-level classifier behind
vol_regime_break). oil_squeeze and vol_regime_break's live day-over-day
lookup themselves need drv_rr/drv_quote/ref_vol_threshold (DB) and are out
of scope for a no-DB test file -- _vol_zone alone (the pure classifier) is
still directly testable here.
"""
from datetime import date

from sqlalchemy import text

from etl.derive_market_event import _pattern_events, _vol_zone, _risk_range_events


def _z(**kwargs):
    """Build a z dict {symbol: (z, last_value, change)} from keyword z-values."""
    return {sym: (val, None, None) for sym, val in kwargs.items()}


def _keys(events):
    return {e[0] for e in events}


def test_yen_bid_fires_and_near_miss_does_not():
    fired = _pattern_events(_z(**{"/6J": 2.5, "TNX:CGI": -1.5}))
    assert "yen_bid" in _keys(fired)
    near_miss = _pattern_events(_z(**{"/6J": 1.9, "TNX:CGI": -1.5}))  # below 2.0
    assert "yen_bid" not in _keys(near_miss)


def test_dollar_wrecking_ball_fires_and_near_miss_does_not():
    fired = _pattern_events(_z(**{"$DXY": 2.0, "/CL": -1.5, "/GC": -1.5,
                                  "/HG": -1.0, "/NG": -0.8}))
    assert "dollar_wrecking_ball" in _keys(fired)
    near_miss = _pattern_events(_z(**{"$DXY": 1.0, "/CL": -1.5, "/GC": -1.5,
                                      "/HG": -1.0, "/NG": -0.8}))  # DXY below 1.5
    assert "dollar_wrecking_ball" not in _keys(near_miss)


def test_rates_shock_fires_both_directions_and_near_miss_does_not():
    assert "rates_shock" in _keys(_pattern_events(_z(**{"TNX:CGI": 2.1})))
    assert "rates_shock" in _keys(_pattern_events(_z(**{"TNX:CGI": -2.1})))
    assert "rates_shock" not in _keys(_pattern_events(_z(**{"TNX:CGI": 1.9})))


def test_credit_leads_equity_fires_and_near_miss_does_not():
    fired = _pattern_events(_z(**{"HYG": -2.5, "SPX": 0.2}))
    assert "credit_leads_equity" in _keys(fired)
    near_miss_hyg = _pattern_events(_z(**{"HYG": -1.5, "SPX": 0.2}))
    assert "credit_leads_equity" not in _keys(near_miss_hyg)
    near_miss_spx = _pattern_events(_z(**{"HYG": -2.5, "SPX": 1.2}))  # SPX moved too
    assert "credit_leads_equity" not in _keys(near_miss_spx)


def test_flight_to_quality_fires_and_near_miss_does_not():
    fired = _pattern_events(_z(**{"/GC": 2.5, "TNX:CGI": -1.5, "SPX": -1.5}))
    assert "flight_to_quality" in _keys(fired)
    near_miss = _pattern_events(_z(**{"/GC": 1.5, "TNX:CGI": -1.5, "SPX": -1.5}))
    assert "flight_to_quality" not in _keys(near_miss)


def test_korea_semis_fires_and_near_miss_does_not():
    assert "korea_semis" in _keys(_pattern_events(_z(**{"EWY": -2.5})))
    assert "korea_semis" not in _keys(_pattern_events(_z(**{"EWY": -1.9})))


def test_no_pattern_fires_on_empty_zscores():
    assert _pattern_events({}) == []


def test_vol_zone_crossing_not_level():
    """The core rule of the whole band: a gauge sustained above 'high' for
    many days is NOT re-emitted every day -- only the transition matters.
    _vol_zone itself is the pure classifier; the caller (_vol_regime_events,
    DB-backed) only emits an event when zone(prev) != zone(today)."""
    low, high = 15.0, 30.0
    assert _vol_zone(10.0, low, high) == "low"
    assert _vol_zone(20.0, low, high) == "chop"
    assert _vol_zone(35.0, low, high) == "high"
    # Sustained in the same zone across two days -> no crossing.
    assert _vol_zone(35.0, low, high) == _vol_zone(36.0, low, high)
    # A real crossing.
    assert _vol_zone(29.0, low, high) != _vol_zone(31.0, low, high)


# ---------------------------------------------------------------------------
# TASK_134 B.3 -- Band 2 must only report genuine Hedgeye risk-range symbols
# (drv_rr.source='RR'), never the 'BB' TOS-Bollinger-band fallback that
# covers the whole ~1,000-symbol universe. DB-backed (_risk_range_events
# queries drv_rr/drv_quote directly) -- skips gracefully without Postgres.
# ---------------------------------------------------------------------------

def test_risk_range_events_ignore_bb_fallback_source(db_session):
    d, prev = date(2099, 1, 2), date(2099, 1, 1)
    # Two symbols, identical lrr/trr and identical price move into the top
    # decile -- only the 'RR' one should ever emit an event.
    for sym, source in (("ZZTASK134RR", "RR"), ("ZZTASK134BB", "BB")):
        db_session.execute(text(
            "INSERT INTO drv_rr (as_of_date, tos_symbol, lrr, trr, source) "
            "VALUES (:d, :s, 100, 200, :src)"
        ), {"d": d, "s": sym, "src": source})
        for dt, px in ((prev, 150.0), (d, 195.0)):
            db_session.execute(text(
                "INSERT INTO drv_quote (as_of_date, tos_symbol, last_price) "
                "VALUES (:d, :s, :p)"
            ), {"d": dt, "s": sym, "p": px})

    events = _risk_range_events(db_session, d, prev)
    hits = [e for e in events if e[2] in ("ZZTASK134RR", "ZZTASK134BB")]
    assert len(hits) == 1
    assert hits[0][2] == "ZZTASK134RR"
