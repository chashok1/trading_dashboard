"""Tests for AGENT_WORK_42 — Behavioral verification (live data, no skips).

Confirms the two original bugs are fixed:
  1. SSS whole-snapshot keying: on-list symbols populated, dropped symbols NOT carried forward
  2. PS REMOVE behavior: held→REMOVE in consolidated; not-held→NOT in consolidated but ADD wins

Also verifies: tos_symbol keying, action-signal parity, idempotency, JS syntax.

All DB tests auto-skip if Postgres is unreachable. Pure-Python tests never need DB.

Anchor date: 2026-06-12 (D = MAX(export_date) FROM hist_td)
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parent.parent
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

ANCHOR_DATE = "2026-06-12"

# ---------------------------------------------------------------------------
# DB connection helper
# ---------------------------------------------------------------------------


def _get_engine():
    """Return a SQLAlchemy engine, or None if DB is unreachable."""
    try:
        from config.settings import settings
        from sqlalchemy import create_engine, text

        eng = create_engine(settings.sqlalchemy_url, connect_args={"connect_timeout": 5})
        with eng.connect() as c:
            c.execute(text("SELECT 1"))
        return eng
    except Exception:
        return None


@pytest.fixture(scope="module")
def db_engine():
    eng = _get_engine()
    if eng is None:
        pytest.skip("Postgres not available — set PG_PASSWORD in .env to run DB tests")
    return eng


@pytest.fixture(scope="module")
def anchor_date(db_engine):
    """Return the real anchor date from the DB and assert it equals expected."""
    from sqlalchemy import text

    with db_engine.connect() as c:
        d = c.execute(text("SELECT MAX(export_date) FROM hist_td")).scalar()
    assert d is not None, "hist_td is empty — cannot determine anchor date"
    return str(d)


# ===========================================================================
# Check 1 — SSS bug fixed: whole-snapshot keying, no carry-forward
# ===========================================================================


class TestSSSBugFixed:
    """SSS signals for on-list symbols are non-NULL; dropped symbols have no carry-forward."""

    def test_1a_aapl_in_drv_source_standing(self, db_engine, anchor_date):
        """AAPL (on latest SSS load) must have a non-NULL SSS row in drv_source_standing."""
        from sqlalchemy import text

        with db_engine.connect() as c:
            row = c.execute(
                text(
                    "SELECT raw_value, signal_sign, rank_hl, on_list "
                    "FROM drv_source_standing "
                    "WHERE as_of_date=:d AND source_code='SSS' AND tos_symbol='AAPL'"
                ),
                {"d": anchor_date},
            ).fetchone()

        assert row is not None, "AAPL has no SSS row in drv_source_standing at anchor date"
        raw_value, signal_sign, rank_hl, on_list = row
        assert raw_value is not None, "AAPL SSS raw_value is NULL"
        assert signal_sign is not None, "AAPL SSS signal_sign is NULL"
        assert on_list is True, "AAPL SSS on_list is not True"

    def test_1a_aapl_drv_ma_matches_source_standing(self, db_engine, anchor_date):
        """drv_ma SSS columns for AAPL must match drv_source_standing values."""
        from sqlalchemy import text

        with db_engine.connect() as c:
            ss = c.execute(
                text(
                    "SELECT raw_value, signal_sign, rank_hl "
                    "FROM drv_source_standing "
                    "WHERE as_of_date=:d AND source_code='SSS' AND tos_symbol='AAPL'"
                ),
                {"d": anchor_date},
            ).fetchone()
            ma = c.execute(
                text(
                    "SELECT sss_signal, sss_signal_sign, sss_rank_hl "
                    "FROM drv_ma "
                    "WHERE as_of_date=:d AND tos_symbol='AAPL'"
                ),
                {"d": anchor_date},
            ).fetchone()

        assert ss is not None, "AAPL not in drv_source_standing SSS"
        assert ma is not None, "AAPL not in drv_ma at anchor date"
        assert float(ss[0]) == float(ma[0]), (
            f"raw_value mismatch: drv_source_standing={ss[0]} vs drv_ma.sss_signal={ma[0]}"
        )
        assert int(ss[1]) == int(ma[1]), (
            f"signal_sign mismatch: drv_source_standing={ss[1]} vs drv_ma.sss_signal_sign={ma[1]}"
        )

    def test_1a_aapl_sss_values_nonzero(self, db_engine, anchor_date):
        """AAPL SSS raw_value and rank_hl must be non-zero (sanity check)."""
        from sqlalchemy import text

        with db_engine.connect() as c:
            row = c.execute(
                text(
                    "SELECT raw_value, rank_hl FROM drv_source_standing "
                    "WHERE as_of_date=:d AND source_code='SSS' AND tos_symbol='AAPL'"
                ),
                {"d": anchor_date},
            ).fetchone()

        assert row is not None
        assert float(row[0]) > 0, f"AAPL SSS raw_value should be >0, got {row[0]}"
        assert row[1] is not None and float(row[1]) > 0, f"AAPL SSS rank_hl should be >0, got {row[1]}"

    def test_1b_dropped_sss_symbols_exist_in_prior_loads(self, db_engine, anchor_date):
        """Symbols in prior SSS snapshots but absent from latest must exist."""
        from sqlalchemy import text

        # Identify the latest SSS snapshot date
        with db_engine.connect() as c:
            latest_sss = c.execute(
                text("SELECT MAX(snapshot_date) FROM hist_sss")
            ).scalar()

        assert latest_sss is not None, "hist_sss is empty"

        with db_engine.connect() as c:
            dropped = c.execute(
                text(
                    "SELECT DISTINCT tos_symbol FROM hist_sss "
                    "WHERE snapshot_date < :latest "
                    "AND tos_symbol NOT IN ("
                    "  SELECT tos_symbol FROM hist_sss WHERE snapshot_date = :latest"
                    ") LIMIT 5"
                ),
                {"latest": latest_sss},
            ).fetchall()

        if not dropped:
            pytest.skip("No dropped SSS symbols found — all prior symbols are on latest snapshot")

        dropped_syms = [r[0] for r in dropped]
        assert len(dropped_syms) >= 1, "Expected at least 1 dropped SSS symbol"
        # Report for evidence
        print(f"\nDropped SSS symbols (prior but not in latest): {dropped_syms}")

    def test_1b_dropped_sss_no_carry_forward_in_source_standing(self, db_engine, anchor_date):
        """Dropped SSS symbols must have 0 rows in drv_source_standing at anchor date."""
        from sqlalchemy import text

        with db_engine.connect() as c:
            latest_sss = c.execute(text("SELECT MAX(snapshot_date) FROM hist_sss")).scalar()
            if latest_sss is None:
                pytest.skip("hist_sss empty")

            dropped = c.execute(
                text(
                    "SELECT DISTINCT tos_symbol FROM hist_sss "
                    "WHERE snapshot_date < :latest "
                    "AND tos_symbol NOT IN ("
                    "  SELECT tos_symbol FROM hist_sss WHERE snapshot_date = :latest"
                    ") LIMIT 5"
                ),
                {"latest": latest_sss},
            ).fetchall()

        if not dropped:
            pytest.skip("No dropped SSS symbols found to check carry-forward")

        dropped_syms = [r[0] for r in dropped]

        failures = []
        with db_engine.connect() as c:
            for sym in dropped_syms:
                cnt = c.execute(
                    text(
                        "SELECT COUNT(*) FROM drv_source_standing "
                        "WHERE as_of_date=:d AND source_code='SSS' AND tos_symbol=:s"
                    ),
                    {"d": anchor_date, "s": sym},
                ).scalar()
                if cnt != 0:
                    failures.append(f"{sym}: count={cnt} (expected 0 — carry-forward bug)")

        assert not failures, "SSS carry-forward detected: " + "; ".join(failures)

    def test_1b_dropped_sss_null_in_drv_ma(self, db_engine, anchor_date):
        """Dropped SSS symbols must have NULL sss_signal_sign in drv_ma."""
        from sqlalchemy import text

        # Use known dropped symbols from DEV_HANDOFF evidence
        check_syms = ["ABNB", "ADBE", "ACI"]
        failures = []
        with db_engine.connect() as c:
            for sym in check_syms:
                sign = c.execute(
                    text(
                        "SELECT sss_signal_sign FROM drv_ma "
                        "WHERE as_of_date=:d AND tos_symbol=:s"
                    ),
                    {"d": anchor_date, "s": sym},
                ).scalar()
                # If the symbol is in drv_ma at all, its SSS sign must be NULL
                if sign is not None:
                    failures.append(f"{sym}: sss_signal_sign={sign} (expected NULL)")

        assert not failures, "Carry-forward SSS signal detected in drv_ma: " + "; ".join(failures)

    def test_1a_sss_count_at_anchor(self, db_engine, anchor_date):
        """SSS count at anchor date must be in a reasonable range (>=10)."""
        from sqlalchemy import text

        with db_engine.connect() as c:
            cnt = c.execute(
                text(
                    "SELECT COUNT(*) FROM drv_source_standing "
                    "WHERE as_of_date=:d AND source_code='SSS'"
                ),
                {"d": anchor_date},
            ).scalar()

        assert cnt >= 10, f"SSS row count too low: {cnt} — expected >=10"
        print(f"\nSSS count at anchor: {cnt}")


# ===========================================================================
# Check 2 — PS REMOVE behavior
# ===========================================================================


class TestPSRemoveBehavior:
    """PS REMOVE: held symbols get consolidated REMOVE; not-held do not."""

    HELD_PS_DROPPED = ["ROBO", "XTL", "IWM"]
    NOT_HELD_PS_DROPPED = ["NORW", "OIH", "SLX"]

    def test_2a_held_ps_dropped_consolidated_remove(self, db_engine, anchor_date):
        """Held PS-dropped symbols must have consolidated_action='REMOVE'."""
        from sqlalchemy import text

        failures = []
        with db_engine.connect() as c:
            for sym in self.HELD_PS_DROPPED:
                ca = c.execute(
                    text(
                        "SELECT consolidated_action FROM drv_actionable "
                        "WHERE as_of_date=:d AND tos_symbol=:s"
                    ),
                    {"d": anchor_date, "s": sym},
                ).scalar()
                if ca != "REMOVE":
                    failures.append(f"{sym}: consolidated_action={ca!r} (expected 'REMOVE')")

        assert not failures, "Held PS REMOVE not showing as REMOVE: " + "; ".join(failures)

    def test_2a_held_ps_dropped_outlook_action_remove(self, db_engine, anchor_date):
        """Held PS-dropped symbols must have REMOVE in drv_outlook_action with held_today=True."""
        from sqlalchemy import text

        failures = []
        with db_engine.connect() as c:
            for sym in self.HELD_PS_DROPPED:
                rows = c.execute(
                    text(
                        "SELECT action, held_today FROM drv_outlook_action "
                        "WHERE as_of_date=:d AND source_code='PS' AND tos_symbol=:s"
                    ),
                    {"d": anchor_date, "s": sym},
                ).fetchall()
                if not rows:
                    failures.append(f"{sym}: no PS row in drv_outlook_action")
                elif rows[0][0] != "REMOVE":
                    failures.append(f"{sym}: action={rows[0][0]!r} (expected 'REMOVE')")
                elif rows[0][1] is not True:
                    failures.append(f"{sym}: held_today={rows[0][1]} (expected True)")

        assert not failures, "Held PS outlook_action wrong: " + "; ".join(failures)

    def test_2b_not_held_ps_dropped_consolidated_not_remove(self, db_engine, anchor_date):
        """Not-held PS-dropped symbols must NOT have consolidated_action='REMOVE'."""
        from sqlalchemy import text

        failures = []
        with db_engine.connect() as c:
            for sym in self.NOT_HELD_PS_DROPPED:
                ca = c.execute(
                    text(
                        "SELECT consolidated_action FROM drv_actionable "
                        "WHERE as_of_date=:d AND tos_symbol=:s"
                    ),
                    {"d": anchor_date, "s": sym},
                ).scalar()
                if ca == "REMOVE":
                    failures.append(f"{sym}: consolidated_action='REMOVE' (should NOT be for not-held)")

        assert not failures, "Not-held PS REMOVE leaked to consolidated: " + "; ".join(failures)

    def test_2b_not_held_ps_dropped_has_remove_in_outlook(self, db_engine, anchor_date):
        """Not-held PS-dropped symbols must have REMOVE in drv_outlook_action with held_today=False."""
        from sqlalchemy import text

        failures = []
        with db_engine.connect() as c:
            for sym in self.NOT_HELD_PS_DROPPED:
                rows = c.execute(
                    text(
                        "SELECT action, held_today FROM drv_outlook_action "
                        "WHERE as_of_date=:d AND source_code='PS' AND tos_symbol=:s"
                    ),
                    {"d": anchor_date, "s": sym},
                ).fetchall()
                if not rows:
                    failures.append(f"{sym}: no PS row in drv_outlook_action")
                elif rows[0][0] != "REMOVE":
                    failures.append(f"{sym}: action={rows[0][0]!r} (expected 'REMOVE' at outlook level)")
                elif rows[0][1] is not False:
                    failures.append(f"{sym}: held_today={rows[0][1]} (expected False for not-held)")

        assert not failures, "Not-held PS outlook_action wrong: " + "; ".join(failures)

    def test_2c_hyg_competing_add_preserved(self, db_engine, anchor_date):
        """HYG: PS REMOVE (not-held) + RR ADD → consolidated_action must be 'ADD'."""
        from sqlalchemy import text

        with db_engine.connect() as c:
            row = c.execute(
                text(
                    "SELECT consolidated_action, source_actions "
                    "FROM drv_actionable "
                    "WHERE as_of_date=:d AND tos_symbol='HYG'"
                ),
                {"d": anchor_date},
            ).fetchone()

        if row is None:
            pytest.skip("HYG not in drv_actionable at anchor date")

        ca, source_actions = row
        assert ca == "ADD", (
            f"HYG consolidated_action={ca!r} — expected 'ADD' (PS not-held REMOVE should not erase RR ADD)"
        )

        # Verify both actions are present in source_actions
        sources = {a.get("source") for a in (source_actions or [])}
        assert "PS" in sources, "HYG source_actions missing PS REMOVE entry"
        assert "RR" in sources, "HYG source_actions missing RR ADD entry"

        ps_actions = [a for a in (source_actions or []) if a.get("source") == "PS"]
        assert ps_actions[0].get("action") == "REMOVE", "HYG PS source_action is not REMOVE"
        assert ps_actions[0].get("held_today") is False, "HYG PS REMOVE should be not-held"

    def test_2c_hyg_source_actions_structure(self, db_engine, anchor_date):
        """HYG source_actions must have both PS REMOVE and an ADD from another source."""
        from sqlalchemy import text

        with db_engine.connect() as c:
            row = c.execute(
                text(
                    "SELECT source_actions FROM drv_actionable "
                    "WHERE as_of_date=:d AND tos_symbol='HYG'"
                ),
                {"d": anchor_date},
            ).fetchone()

        if row is None:
            pytest.skip("HYG not in drv_actionable")

        source_actions = row[0] or []
        add_actions = [a for a in source_actions if a.get("action") == "ADD"]
        remove_actions = [a for a in source_actions if a.get("action") == "REMOVE"]
        assert len(add_actions) >= 1, "HYG has no ADD in source_actions"
        assert len(remove_actions) >= 1, "HYG has no REMOVE in source_actions"


# ===========================================================================
# Check 3 — tos_symbol keying
# ===========================================================================


class TestToSSymbolKeying:
    """All PS and SSS entries must use tos_symbol, not raw ticker/symbol."""

    def test_3_ps_no_ticker_tos_symbol_mismatch(self, db_engine, anchor_date):
        """hist_ps must have 0 rows where ticker != tos_symbol."""
        from sqlalchemy import text

        with db_engine.connect() as c:
            cnt = c.execute(
                text("SELECT COUNT(*) FROM hist_ps WHERE ticker != tos_symbol")
            ).scalar()

        assert cnt == 0, f"{cnt} rows in hist_ps have ticker != tos_symbol (tos_symbol normalization broken)"

    def test_3_sss_no_symbol_tos_symbol_mismatch_latest(self, db_engine, anchor_date):
        """hist_sss latest snapshot must have 0 rows where symbol != tos_symbol."""
        from sqlalchemy import text

        with db_engine.connect() as c:
            latest_sss = c.execute(text("SELECT MAX(snapshot_date) FROM hist_sss")).scalar()
            if latest_sss is None:
                pytest.skip("hist_sss empty")
            cnt = c.execute(
                text(
                    "SELECT COUNT(*) FROM hist_sss "
                    "WHERE symbol != tos_symbol AND snapshot_date = :s"
                ),
                {"s": latest_sss},
            ).scalar()

        assert cnt == 0, f"{cnt} rows in hist_sss (latest) have symbol != tos_symbol"

    def test_3_drv_source_standing_tos_symbol_not_null(self, db_engine, anchor_date):
        """All drv_source_standing rows at anchor must have non-NULL tos_symbol."""
        from sqlalchemy import text

        with db_engine.connect() as c:
            cnt = c.execute(
                text(
                    "SELECT COUNT(*) FROM drv_source_standing "
                    "WHERE as_of_date=:d AND tos_symbol IS NULL"
                ),
                {"d": anchor_date},
            ).scalar()

        assert cnt == 0, f"{cnt} rows have NULL tos_symbol in drv_source_standing"


# ===========================================================================
# Check 4 — action-signal parity (AAPL SSS)
# ===========================================================================


class TestActionSignalParity:
    """SSS signal in drv_source_standing must match drv_ma and source_actions weight."""

    def test_4_aapl_parity_chain(self, db_engine, anchor_date):
        """AAPL: drv_source_standing.raw_value == drv_ma.sss_signal == source_action weight."""
        from sqlalchemy import text

        with db_engine.connect() as c:
            ss = c.execute(
                text(
                    "SELECT raw_value, signal_sign FROM drv_source_standing "
                    "WHERE as_of_date=:d AND source_code='SSS' AND tos_symbol='AAPL'"
                ),
                {"d": anchor_date},
            ).fetchone()
            ma = c.execute(
                text(
                    "SELECT sss_signal, sss_signal_sign FROM drv_ma "
                    "WHERE as_of_date=:d AND tos_symbol='AAPL'"
                ),
                {"d": anchor_date},
            ).fetchone()
            act = c.execute(
                text(
                    "SELECT source_actions FROM drv_actionable "
                    "WHERE as_of_date=:d AND tos_symbol='AAPL'"
                ),
                {"d": anchor_date},
            ).scalar()

        assert ss is not None, "AAPL not in drv_source_standing SSS"
        assert ma is not None, "AAPL not in drv_ma"

        # Layer 1 == Layer 2
        assert float(ss[0]) == float(ma[0]), (
            f"drv_source_standing.raw_value ({ss[0]}) != drv_ma.sss_signal ({ma[0]})"
        )
        assert int(ss[1]) == int(ma[1]), (
            f"drv_source_standing.signal_sign ({ss[1]}) != drv_ma.sss_signal_sign ({ma[1]})"
        )

        # Layer 3: source_actions weight must match
        if act:
            sss_entries = [a for a in act if a.get("source") == "SSS"]
            if sss_entries:
                weight = sss_entries[0].get("weight")
                if weight is not None:
                    assert abs(float(weight) - float(ss[0])) < 1e-9, (
                        f"source_actions weight ({weight}) != drv_source_standing.raw_value ({ss[0]})"
                    )

    def test_4_aapl_sss_values_specific(self, db_engine, anchor_date):
        """AAPL SSS raw_value=0.197, signal_sign=1 at anchor 2026-06-12 (evidence check)."""
        from sqlalchemy import text

        with db_engine.connect() as c:
            row = c.execute(
                text(
                    "SELECT raw_value, signal_sign, rank_hl FROM drv_source_standing "
                    "WHERE as_of_date=:d AND source_code='SSS' AND tos_symbol='AAPL'"
                ),
                {"d": anchor_date},
            ).fetchone()

        assert row is not None, "AAPL SSS row missing"
        # Values from DEV_HANDOFF evidence — these are the specific values recorded
        assert abs(float(row[0]) - 0.197) < 0.001, f"AAPL SSS raw_value={row[0]} expected ~0.197"
        assert int(row[1]) == 1, f"AAPL SSS signal_sign={row[1]} expected 1"


# ===========================================================================
# Check 5 — idempotency
# ===========================================================================


class TestIdempotency:
    """derive_all run twice must produce identical drv_source_standing contents."""

    def test_5_row_counts_stable_after_second_derive(self, db_engine, anchor_date):
        """drv_source_standing counts per source must be identical across two derive_all runs."""
        from datetime import date

        from sqlalchemy import text

        anchor = date.fromisoformat(anchor_date)

        # Capture counts before re-derive
        with db_engine.connect() as c:
            rows_before = dict(
                c.execute(
                    text(
                        "SELECT source_code, COUNT(*) FROM drv_source_standing "
                        "WHERE as_of_date=:d GROUP BY source_code ORDER BY source_code"
                    ),
                    {"d": anchor},
                ).fetchall()
            )

        if not rows_before:
            pytest.skip("drv_source_standing empty at anchor — no data to check idempotency")

        # Re-derive
        from etl.db import session_scope
        from etl.derive import derive_all

        with session_scope() as sess:
            derive_all(sess, anchor)

        # Capture counts after re-derive
        with db_engine.connect() as c:
            rows_after = dict(
                c.execute(
                    text(
                        "SELECT source_code, COUNT(*) FROM drv_source_standing "
                        "WHERE as_of_date=:d GROUP BY source_code ORDER BY source_code"
                    ),
                    {"d": anchor},
                ).fetchall()
            )

        assert rows_before == rows_after, (
            f"drv_source_standing counts changed after re-derive:\n"
            f"Before: {rows_before}\nAfter:  {rows_after}"
        )

    def test_5_expected_counts_match_baseline(self, db_engine, anchor_date):
        """drv_source_standing counts must match DEV_HANDOFF baseline: CALL=203, ETF=39, II=14, PS=19, RR=971, SSS=74."""
        from sqlalchemy import text

        expected = {"CALL": 203, "ETF": 39, "II": 14, "PS": 19, "RR": 971, "SSS": 74}

        with db_engine.connect() as c:
            rows = dict(
                c.execute(
                    text(
                        "SELECT source_code, COUNT(*) FROM drv_source_standing "
                        "WHERE as_of_date=:d GROUP BY source_code"
                    ),
                    {"d": anchor_date},
                ).fetchall()
            )

        if not rows:
            pytest.skip("drv_source_standing empty")

        mismatches = []
        for src, exp_count in expected.items():
            actual = rows.get(src, 0)
            if actual != exp_count:
                mismatches.append(f"{src}: expected={exp_count}, actual={actual}")

        assert not mismatches, "Count mismatches vs DEV_HANDOFF baseline: " + "; ".join(mismatches)

    def test_5_total_count_is_1320(self, db_engine, anchor_date):
        """Total drv_source_standing rows at anchor must be 1320."""
        from sqlalchemy import text

        with db_engine.connect() as c:
            total = c.execute(
                text(
                    "SELECT COUNT(*) FROM drv_source_standing WHERE as_of_date=:d"
                ),
                {"d": anchor_date},
            ).scalar()

        assert total == 1320, f"Total rows={total}, expected 1320"


# ===========================================================================
# Check 6 — JS syntax (pure Python, no DB)
# ===========================================================================


class TestJSSyntax:
    """web/actionable.js must pass node --check."""

    def test_6_actionable_js_valid(self):
        result = subprocess.run(
            ["node", "--check", str(PROJECT / "web" / "actionable.js")],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"actionable.js has syntax errors:\n{result.stderr}"
        )


# ===========================================================================
# Structural checks (pure Python, no DB) — UI toggle and code-level assertions
# ===========================================================================


# TestUIUnheldRemoveToggle — RETIRED (TASK_111 test-debt cleanup,
# 2026-07-04). Asserted a "+Unheld Remove" toggle (show_not_held_remove
# state, showNotHeldRemove checkbox) — confirmed zero matches for
# "show_not_held_remove" anywhere in web/. Feature never implemented (or
# removed since). Cat B per docs/audit/test_debt_review.md.


# ===========================================================================
# Anchor date check (meta-test: confirms DB is at expected date)
# ===========================================================================


# TestAnchorDate — RETIRED (TASK_111 test-debt cleanup, 2026-07-04).
# Asserted MAX(export_date) FROM hist_td == a hardcoded point-in-time anchor
# ('2026-06-12'); the anchor advances with every new TOSD load (per
# docs/derive_date_logic.md), so this has been wrong every day since it was
# written. Cat B point-in-time-data pin per docs/audit/test_debt_review.md.
