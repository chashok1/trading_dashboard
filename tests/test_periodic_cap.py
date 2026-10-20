"""api/_helpers.py::periodic_cap -- the 'newest Hedgeye list on the latest day, back to that day on an older date' rule (needs the DB)."""
from datetime import date, timedelta

import pytest
from sqlalchemy import text


def _session():
    try:
        from etl.db import session_scope
        return session_scope()
    except Exception as e:   # no database in this environment
        pytest.skip(f"no database: {e}")


def test_latest_day_is_uncapped_and_older_day_is_capped():
    from api._helpers import periodic_cap
    with _session() as s:
        anchor = s.execute(text("SELECT MAX(export_date) FROM hist_td")).scalar()
        if anchor is None:
            pytest.skip("hist_td is empty")
        assert periodic_cap(s, anchor) == date.max            # latest day -> newest file of every periodic list
        older = anchor - timedelta(days=3)
        assert periodic_cap(s, older) == older                # older picked date -> that day's data
