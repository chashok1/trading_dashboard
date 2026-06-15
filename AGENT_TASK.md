# AGENT TASK — Task 46 verification (market-bar tile restyle)

**Tester agent (VS Code), psql + browser. You HAVE database access.**
Pre-req: `DEV_HANDOFF.md` ends `ALL_DONE`. If not, STOP and report. Write results
to **`AGENT_RESULT_46.md`** (exact filename), ending `DONE` or `FAILED: <checks>`.
**DO NOT COMMIT.** Paste real query/console output as evidence for every check — a
check with no pasted output counts as `FAILED`.

Anchor: `:D = SELECT MAX(export_date) FROM hist_td`.

## Check 1 — drv_rr.outlook column added + populated
- `\d drv_rr` shows an `outlook TEXT` column.
- ```sql
  SELECT count(*) FILTER (WHERE outlook IS NOT NULL) AS with_ol,
         count(*) FILTER (WHERE source='RR') AS rr_rows, count(*) AS total
  FROM drv_rr WHERE as_of_date=(SELECT MAX(as_of_date) FROM drv_rr);
  ```
  `with_ol` > 0 and equals `rr_rows`. Paste 5 sample RR rows (tos_symbol, lrr, trr,
  outlook, source). Paste one BB-fallback row showing `outlook IS NULL`.

## Check 2 — API emits OHLC + drv_rr range/outlook
- `curl -s localhost:8000/api/marketbar | python -m json.tool` — paste one item
  with non-null `open/high/low/close`, `rr_buy`, `rr_sell`, `rr_outlook`.
- `curl -s localhost:8000/api/rr-bar | python -m json.tool` — paste one item with
  `open/high/low/close`, `buy`, `sell`, `outlook`, `bar_price`.

## Check 3 — Frontend renders + layout preserved
- `node --check web/market_bar.js` — passes.
- `/actionable` hard-refresh, console clean. Confirm (one line each): both bars are
  still single-row horizontal scrollers; each tile has a colored symbol button, a
  colored %, a range bar with a current-price tick, and a candle (wicks + flat
  body) on the right.
- Direction/inversion: paste a one-line confirmation that a rising **VIX** shows a
  **red** % (INVERTED preserved) and its candle matches that direction; a Bullish
  symbol shows a green symbol button, a Bearish one red.

## Check 4 — Idempotency
- Re-run the derive for :D twice; paste matching `drv_rr` row counts and identical
  `outlook` values (a diff or matching aggregate).

## Check 5 — Regression
- `pytest tests/ -q --tb=no` — DB tests must EXECUTE (not skip). Report new failures
  vs the pre-existing ~89 baseline. Confirm `tests/test_agent_work_46.py` passes.

## Verdict
Per check: PASS/FAIL + pasted evidence. Final line of `AGENT_RESULT_46.md`:
`DONE` or `FAILED: <checks>`.
