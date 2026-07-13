# TASK_119 — Stop consistency: below-stop held rows can't say HOLD/INCREASE

## Context

Diagnosis E.1: 7 held positions trade below `drv_actionable.stop_level`, yet
5 show HOLD and two (TLT, ZROZ) show **INCREASE**. The stop and the ACTION
column don't talk to each other — contradictory advice on the same row.

## Goal

A held position below stop is always visibly flagged, and the surface never
recommends adding to it.

1. `db/baseline.sql`: add `drv_actionable.stop_breached BOOLEAN NOT NULL
   DEFAULT FALSE`.
2. `etl/derive_actionable.py`: after consolidation, for held rows where the
   latest price (`drv_quote`, same lookup `_compute_stop` uses) `< stop_level`:
   - set `stop_breached = TRUE`;
   - if `consolidated_action` in (ADD, INCREASE): keep the original in
     `source_actions`/reason but downgrade the effective action to HOLD with
     `suppressed_reason = 'STOP BREACHED'` (mirrors existing suppression
     pattern — the user still sees what the system would have said);
   - REMOVE/REDUCE/HOLD rows keep their action, just flagged.
   Derive stays idempotent. Do NOT force REMOVE — breach ≠ auto-sell
   (bond ETFs sit pennies below tight stops); the flag + no-add rule is the fix.
3. `web/actionable.js` + `api/routers/dash.py`:
   - payload includes `stop_breached`;
   - breached rows get a red "STOP" pill next to the ACTION badge and the row's
     left edge tinted red;
   - a summary chip "STOP n" filters to breached rows (same pattern as the
     SELL→MAX synthetic chip).
4. Legend ("?" panel): add the STOP pill explanation.

## Files expected to change

- `db/baseline.sql`, `etl/derive_actionable.py`, `api/routers/dash.py`,
  `web/actionable.js` (+ `web/styles.css` if needed), `DEV_HANDOFF.md`

## How to verify

1. `python -m db.init_db` idempotent; re-derive latest anchor.
2. `SELECT tos_symbol, consolidated_action, suppressed_reason FROM
   drv_actionable WHERE as_of_date = D AND stop_breached;` — TLT/ZROZ-class
   rows no longer show ADD/INCREASE as effective action; reason = STOP BREACHED.
3. /actionable: STOP chip count matches the query; pill renders; filter works.
4. A non-held symbol below its would-be stop is NOT flagged.
