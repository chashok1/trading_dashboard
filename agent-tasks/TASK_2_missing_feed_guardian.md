# TASK 2 — Missing-feed guardian: block actionable on absent EOD price data

## Goal
If TOSL (or another daily-EOD price source) never arrived for anchor date D,
`drv_actionable` still fires with NULL/absent prices and the user can act on it.
Make this impossible to miss.

## Scope
- `api/_helpers.py` / `api/routers/dash.py` — new lightweight check (or extend
  `/api/anchor-status`): for date D, count drv_technicals rows with NULL
  last_price and detect hist_tl missing export_date=D entirely.
- `web/actionable.js` + `web/warning_badge.js` — when the check trips: prominent
  red blocking banner on Actionable ("EOD price feed missing for D —
  recommendations unreliable") above the grid; rows get a warning style.
  (Cockpit is being retired in Task 7 — banner only needs Actionable + Dashboard.)
- `etl/derive.py::warn_missing_eod_sources` — confirm it covers all 4 daily-EOD
  sources (TOSL/TOSD/TOSW/Y); extend if not.
- Out of scope: schema constraints on drv_actionable; carry-forward age expiry.

## Acceptance criteria
- With hist_tl rows for D absent (simulated), Actionable shows the blocking
  banner; with normal data it does not.

## How to verify (combined test round)
- Simulate missing TOSL for a date (transactional test or temp delete+rollback),
  hit the check endpoint, load /actionable — banner shows; restore — banner gone.
- Console clean; pytest passes.

## Constraints
- Follow CLAUDE.md. Read docs/derive_date_logic.md first. SQL ≤965 bytes.
