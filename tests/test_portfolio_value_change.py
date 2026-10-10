"""Portfolio Today's change = account value change (+ breakdown). Behaviour only."""
import pytest

try:
    from etl.db import session_scope
    from sqlalchemy import text
    with session_scope() as _s:
        _s.execute(text("SELECT 1"))
    _DB = True
except Exception:
    _DB = False

pytestmark = pytest.mark.skipif(not _DB, reason="Postgres not available")


def _summary():
    from api.routers.dash import get_portfolio_summary
    import inspect
    kwargs = {}
    for name, p in inspect.signature(get_portfolio_summary).parameters.items():
        kwargs[name] = p.default.default if hasattr(p.default, "default") else p.default
    kwargs = {k: (None if v is inspect.Parameter.empty else v) for k, v in kwargs.items()}
    return get_portfolio_summary(**kwargs)


def test_flow_diff_is_value_change_minus_explained_gain():
    d = _summary()
    for a in d["by_account"]:
        if a["value_change_dollar"] is None:
            continue
        assert a["flow_diff_dollar"] == pytest.approx(a["value_change_dollar"] - a["today_gain_dollar"], abs=0.01)


def test_totals_are_sum_of_accounts():
    d = _summary()
    parts = [a for a in d["by_account"] if a["value_change_dollar"] is not None]
    if parts:
        assert d["value_change_dollar"] == pytest.approx(sum(a["value_change_dollar"] for a in parts), abs=0.01)
        assert d["flow_diff_dollar"] == pytest.approx(sum(a["flow_diff_dollar"] for a in parts), abs=0.01)


def test_txn_loaded_flag_present():
    d = _summary()
    assert isinstance(d["txn_loaded"], bool)
    assert all(isinstance(a["txn_loaded"], bool) for a in d["by_account"])
