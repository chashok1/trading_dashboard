"""
QA regression coverage for TASK_103–TASK_110 (Actionable screen batch review).

These tests exercise the two most load-bearing, real-DB-write changes flagged
for extra scrutiny in the batch:

  - TASK_103 Item 1/3: SNOOZED semantics (dateless SNOOZED = hidden for the
    as_of_date; dated SNOOZED = hidden until that date) + un-snooze via
    DELETE /api/actionable/{symbol}/action (clears SKIPPED **and** SNOOZED).
  - TASK_106 Item 1: POST /api/actionable/bulk-action — one transaction for N
    symbols, plus the real pre-existing bug where user_action_log INSERTs
    referenced a dropped `symbol` column (silently 500ing every Done/Skip/
    Snooze click before TASK_106's fix).

All tests hit the real DB through the FastAPI TestClient (session_scope()
commits), so every test cleans up any row it inserts via the DELETE endpoint
(or a direct DELETE keyed on a unique `user_notes` marker) so the suite is
non-destructive to real data. Tests skip gracefully when Postgres is not
reachable, per repo convention (see tests/conftest.py::db_available).
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

pytestmark = pytest.mark.usefixtures("db_available")


def _client():
    from fastapi.testclient import TestClient
    from api.main import app
    return TestClient(app)


def _latest_date_with_visible_rows(client, min_rows=3):
    """Find a date where /api/actionable (default filters) returns at least
    `min_rows` symbols, so we have safe candidates to snooze/skip without
    fighting other suppression reasons. Returns (date_str, [symbols])."""
    dates = client.get("/api/actionable/dates").json()
    for d in dates[:10]:
        resp = client.get("/api/actionable", params={"date": d})
        if resp.status_code != 200:
            continue
        rows = resp.json()
        syms = [r["tos_symbol"] for r in rows if r.get("tos_symbol")]
        if len(syms) >= min_rows:
            return d, syms
    pytest.skip("No recent date with enough visible Actionable rows to test against")


def _cleanup(client, sym, d):
    """Best-effort: remove any SKIPPED/SNOOZED row we may have left behind."""
    try:
        client.delete(f"/api/actionable/{sym}/action", params={"date": d})
    except Exception:
        pass


# ---------------------------------------------------------------------------
# TASK_103 Item 1 — dateless SNOOZED hides for the as_of_date
# ---------------------------------------------------------------------------

class TestSnoozeDatelessSemantics:
    def test_dateless_snooze_hides_row_and_is_visible_with_show_acted(self, db_available):
        if not db_available:
            pytest.skip("Postgres not available")
        client = _client()
        d, syms = _latest_date_with_visible_rows(client)
        sym = syms[0]
        try:
            # Row must be visible before we touch it.
            before = client.get("/api/actionable", params={"date": d}).json()
            assert any(r["tos_symbol"] == sym for r in before), (
                f"{sym} should be visible on {d} before snoozing"
            )

            resp = client.post(
                f"/api/actionable/{sym}/action",
                json={"as_of_date": d, "user_action": "SNOOZED", "user_notes": "qa_snooze_dateless"},
            )
            assert resp.status_code == 200, resp.text
            assert resp.json().get("log_id") is not None

            # Default (show_acted=false) — row must now be hidden.
            after = client.get("/api/actionable", params={"date": d}).json()
            assert not any(r["tos_symbol"] == sym for r in after), (
                f"{sym} should be hidden on {d} after a dateless SNOOZED action (TASK_103 Item 1)"
            )

            # show_acted=true — row must reappear with snooze_until NULL.
            shown = client.get("/api/actionable", params={"date": d, "show_acted": True}).json()
            match = [r for r in shown if r["tos_symbol"] == sym]
            assert match, f"{sym} should still be queryable via show_acted=true"
            assert match[0].get("last_user_action") == "SNOOZED"
            assert match[0].get("snooze_until") is None, (
                "Dateless SNOOZED must persist snooze_until = NULL"
            )
        finally:
            _cleanup(client, sym, d)

    def test_future_dated_snooze_also_hides_row(self, db_available):
        if not db_available:
            pytest.skip("Postgres not available")
        client = _client()
        d, syms = _latest_date_with_visible_rows(client)
        sym = syms[0]
        future = (date.fromisoformat(d) + timedelta(days=30)).isoformat()
        try:
            resp = client.post(
                f"/api/actionable/{sym}/action",
                json={
                    "as_of_date": d, "user_action": "SNOOZED",
                    "snooze_until": future, "user_notes": "qa_snooze_dated",
                },
            )
            assert resp.status_code == 200, resp.text

            after = client.get("/api/actionable", params={"date": d}).json()
            assert not any(r["tos_symbol"] == sym for r in after), (
                f"{sym} should be hidden on {d} — snooze_until ({future}) is still in the future"
            )
        finally:
            _cleanup(client, sym, d)


# ---------------------------------------------------------------------------
# TASK_103 Item 3 — un-snooze via DELETE clears SNOOZED (not just SKIPPED)
# ---------------------------------------------------------------------------

class TestUnSnoozeDelete:
    def test_delete_clears_snoozed_row_and_row_reappears(self, db_available):
        if not db_available:
            pytest.skip("Postgres not available")
        client = _client()
        d, syms = _latest_date_with_visible_rows(client)
        sym = syms[0]
        try:
            resp = client.post(
                f"/api/actionable/{sym}/action",
                json={"as_of_date": d, "user_action": "SNOOZED", "user_notes": "qa_unsnooze"},
            )
            assert resp.status_code == 200, resp.text

            hidden = client.get("/api/actionable", params={"date": d}).json()
            assert not any(r["tos_symbol"] == sym for r in hidden)

            clear = client.delete(f"/api/actionable/{sym}/action", params={"date": d})
            assert clear.status_code == 200, clear.text
            assert clear.json().get("cleared", 0) >= 1

            restored = client.get("/api/actionable", params={"date": d}).json()
            assert any(r["tos_symbol"] == sym for r in restored), (
                f"{sym} should reappear on {d} after DELETE clears the SNOOZED row (TASK_103 Item 3)"
            )
        except AssertionError:
            _cleanup(client, sym, d)
            raise

    def test_delete_still_clears_skipped_row(self, db_available):
        """Regression guard: TASK_103's fix widened the DELETE to also clear
        SNOOZED — it must not have narrowed or dropped the original SKIPPED
        clearing behavior."""
        if not db_available:
            pytest.skip("Postgres not available")
        client = _client()
        d, syms = _latest_date_with_visible_rows(client)
        sym = syms[0]
        try:
            resp = client.post(
                f"/api/actionable/{sym}/action",
                json={"as_of_date": d, "user_action": "SKIPPED", "user_notes": "qa_skip_clear"},
            )
            assert resp.status_code == 200, resp.text

            clear = client.delete(f"/api/actionable/{sym}/action", params={"date": d})
            assert clear.status_code == 200, clear.text
            assert clear.json().get("cleared", 0) >= 1

            restored = client.get("/api/actionable", params={"date": d}).json()
            assert any(r["tos_symbol"] == sym for r in restored)
        except AssertionError:
            _cleanup(client, sym, d)
            raise


# ---------------------------------------------------------------------------
# TASK_106 Item 1 — bulk-action endpoint (+ the dropped-`symbol`-column bug)
# ---------------------------------------------------------------------------

class TestBulkActionEndpoint:
    def test_bulk_action_one_call_writes_all_symbols(self, db_available):
        if not db_available:
            pytest.skip("Postgres not available")
        client = _client()
        d, syms = _latest_date_with_visible_rows(client, min_rows=3)
        batch = syms[:3]
        try:
            resp = client.post(
                "/api/actionable/bulk-action",
                json={
                    "symbols": batch, "as_of_date": d,
                    "user_action": "SKIPPED", "user_notes": "qa_bulk_action",
                },
            )
            # This is the endpoint that TASK_106 introduced specifically to
            # replace N sequential POSTs; a 500 here would mean the dropped
            # `symbol` column regression (fixed by TASK_106) is back.
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body.get("ok") is True
            results = body.get("results") or []
            assert len(results) == len(batch)
            got_syms = {r["symbol"] for r in results}
            assert got_syms == set(s.upper() for s in batch)
            for r in results:
                assert r.get("error") is None, f"bulk-action reported an error for {r}"
                assert r.get("log_id") is not None

            # All 3 symbols must now be hidden (SKIPPED).
            after = client.get("/api/actionable", params={"date": d}).json()
            after_syms = {r["tos_symbol"] for r in after}
            for s in batch:
                assert s not in after_syms, f"{s} should be hidden after bulk SKIPPED"
        finally:
            for s in batch:
                _cleanup(client, s, d)

    def test_bulk_action_rejects_empty_symbol_list(self, db_available):
        if not db_available:
            pytest.skip("Postgres not available")
        client = _client()
        resp = client.post(
            "/api/actionable/bulk-action",
            json={"symbols": [], "as_of_date": "2026-01-01", "user_action": "SKIPPED"},
        )
        assert resp.status_code == 400

    def test_bulk_action_rejects_invalid_user_action(self, db_available):
        if not db_available:
            pytest.skip("Postgres not available")
        client = _client()
        d, syms = _latest_date_with_visible_rows(client)
        resp = client.post(
            "/api/actionable/bulk-action",
            json={"symbols": [syms[0]], "as_of_date": d, "user_action": "BOGUS"},
        )
        assert resp.status_code == 400

    def test_bulk_action_partial_failure_does_not_abort_whole_batch(self, db_available):
        """One bad symbol (no drv_actionable row) must not prevent the other,
        valid symbols in the same batch from being logged — the endpoint's
        docstring promises per-symbol try/except inside the shared loop."""
        if not db_available:
            pytest.skip("Postgres not available")
        client = _client()
        d, syms = _latest_date_with_visible_rows(client)
        good_sym = syms[0]
        bogus_sym = "ZZQATESTNOPE"
        try:
            resp = client.post(
                "/api/actionable/bulk-action",
                json={
                    "symbols": [bogus_sym, good_sym], "as_of_date": d,
                    "user_action": "SKIPPED", "user_notes": "qa_bulk_partial",
                },
            )
            assert resp.status_code == 200, resp.text
            results = {r["symbol"]: r for r in resp.json()["results"]}
            assert results[bogus_sym].get("error") is not None
            assert results[bogus_sym].get("log_id") is None
            assert results[good_sym].get("error") is None
            assert results[good_sym].get("log_id") is not None
        finally:
            _cleanup(client, good_sym, d)
            _cleanup(client, bogus_sym, d)
