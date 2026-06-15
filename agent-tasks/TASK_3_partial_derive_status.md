# TASK 3 — derive_all status: SUCCESS / PARTIAL / FAILED + UI surfacing

## Goal
`derive_all()` wraps ~40 steps in a per-step `_safe()` catch; a mid-cascade
failure lets later derives run on incomplete upstream state and nothing tells
the user the cascade was partial. Track an overall status and surface it.

## Scope
- `etl/derive.py::derive_all` / `_safe` — collect per-step failures; write one
  summary row (meta_derived_run or a new meta column — pick the smallest schema
  change in db/baseline.sql) with status SUCCESS/PARTIAL/FAILED + failed step
  names.
- `etl/daily_health_check.py` — new `_check_derive_health()`: any
  meta_derived_run status='error' in last 24h on critical tables
  (drv_cat_atomic_input, drv_stks, drv_actionable, drv_technicals) → warning.
- `api/routers/health.py` + `web/warning_badge.js` — if latest derive for the
  viewed date is PARTIAL/FAILED, show "derivation incomplete for D" banner on
  Actionable + Dashboard.
- Out of scope: changing transaction semantics / rollback tiers — do NOT attempt
  an atomic-cascade refactor.

## Acceptance criteria
- Forcing one derive step to raise (monkeypatch in test) yields a PARTIAL
  summary + banner; normal run yields SUCCESS and no banner.
- Health check reports recent derive errors.

## How to verify (combined test round)
- pytest with a monkeypatched failing step; check meta rows; load screens;
  `python -m etl.daily_health_check` output.

## Constraints
- Follow CLAUDE.md. Keep the schema tweak minimal and idempotent in baseline.sql.
