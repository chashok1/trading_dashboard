"""drv_vol_spike: the TOS spike study, stress flag and held-symbol Watch alerts. Behaviour only, pure Python (fake session, no DB)."""
from datetime import date, timedelta

from etl import vol_spike as vs


def _dates(n, start=date(2026, 1, 5)):
    return [start + timedelta(days=i) for i in range(n)]


# ── spike_series -----------------------------------------------------------------------------------------------------
def test_flat_series_never_spikes():
    s = vs.spike_series([1.0] * 120)
    assert not any(s["mk"]) and not any(s["was"]) and abs(s["ratio"][-1] - 1.0) < 1e-9


def test_spike_then_normalize_in_order():
    s = vs.spike_series([1.0] * 80 + [2.0] * 8 + [0.5] * 40)
    assert s["mk"].count("up") == 1 and s["mk"].count("down") == 1
    assert s["mk"].index("up") < s["mk"].index("down")
    assert s["was"][s["mk"].index("up")] is True and s["was"][-1] is False


def test_exclusion_keeps_the_average_from_chasing_the_spike():
    # while spiked the average switches to the full (normal) average, so the red line is above the pre-spike one
    s = vs.spike_series([1.0] * 80 + [2.0] * 8)
    i = s["mk"].index("up")
    assert s["red"][i] < s["red"][-1]


# ── stress ------------------------------------------------------------------------------------------------------------
def test_stress_needs_spike_and_falling_price():
    assert vs.is_stress(True, 3, -4.0) is True
    assert vs.is_stress(True, 3, -1.0) is False          # price not falling enough
    assert vs.is_stress(False, 30, -9.0) is False        # no spike
    assert vs.is_stress(False, 2, -4.0) is True          # a fresh arrow still counts as spiked
    assert vs.is_stress(True, 3, None) is False


def test_build_rows_flags_stress_when_price_drops_during_a_spike():
    n = 130
    iv = [1.0] * 80 + [2.0] * 50
    px = [100.0] * 100 + [100.0 - 2 * i for i in range(30)]
    rows = vs.build_rows(_dates(n), px, iv, [1.0] * n)
    assert any(r["stress"] for r in rows)
    assert not any(r["stress"] for r in rows[:80])
    assert all(r["px_chg_5d"] is None for r in rows[:5])


def test_build_rows_carries_gaps_forward():
    iv = [1.0] * 100
    iv[50] = None
    rows = vs.build_rows(_dates(100), [10.0] * 100, iv, [1.0] * 100)
    assert rows[50]["iv"] == 1.0


# ── alerts ------------------------------------------------------------------------------------------------------------
def _row(**kw):
    base = {"as_of_date": date(2026, 10, 28), "stress": False, "iv_event": None, "iv_ratio": 1.3, "px_chg_5d": -5.0}
    base.update(kw)
    return base


def test_alert_on_fresh_stress_only_once():
    assert vs._alert_for(_row(stress=True), prev_stress=False)[0].startswith("Auto: IV stress")
    assert vs._alert_for(_row(stress=True), prev_stress=True) is None


def test_alert_on_fresh_iv_spike_arrow():
    note, reason = vs._alert_for(_row(iv_event="up"), prev_stress=False)
    assert note.startswith("Auto: IV spike") and "1.30" in reason


def test_no_alert_when_nothing_new():
    assert vs._alert_for(_row(), prev_stress=False) is None
    assert vs._alert_for(_row(iv_event="down"), prev_stress=False) is None


class _Res:
    def __init__(self, hit): self._hit = hit
    def first(self): return (1,) if self._hit else None


class _Sess:
    def __init__(self, existing=False): self.inserts, self._existing = [], existing
    def execute(self, stmt, params=None):
        sql = str(stmt)
        if sql.lstrip().startswith("INSERT"):
            self.inserts.append(params)
            return _Res(False)
        return _Res(self._existing)


def test_watch_alert_created_only_for_held_symbols(monkeypatch):
    monkeypatch.setattr("etl.derive_outlook_action._load_holdings", lambda s, d: {"AAA"})
    today = {"AAA": _row(iv_event="up"), "BBB": _row(iv_event="up")}
    s = _Sess()
    n = vs._create_watch_alerts(s, date(2026, 10, 28), today, {}, {"AAA": 12.5})
    assert n == 1 and s.inserts[0]["s"] == "AAA" and s.inserts[0]["p"] == 12.5


def test_existing_watch_is_left_alone(monkeypatch):
    monkeypatch.setattr("etl.derive_outlook_action._load_holdings", lambda s, d: {"AAA"})
    s = _Sess(existing=True)
    assert vs._create_watch_alerts(s, date(2026, 10, 28), {"AAA": _row(iv_event="up")}, {}, {}) == 0
    assert s.inserts == []
