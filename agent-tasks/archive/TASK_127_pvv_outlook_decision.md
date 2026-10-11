# TASK_127 — PVV decision: RR outlook × today's tape (replace bucket matrix)

## Goal

Replace `drv_pvv`'s consolidated-decision logic (TASK_125 §4 — the
5d/3w/3m alignment matrix) with a simpler, forward-looking rule: **the
stock's RR outlook decides WHAT, today's PVV signal decides WHEN.**

Everything else from TASK_125 stays exactly as-is:

- All 4 bucket signals (`sig_today/sig_5d/sig_3w/sig_3m`) still computed,
  stored, and shown in the tooltip — **no change to any bucket calculation**.
- Table shape, column, badge, sort rank, popover mechanism unchanged.
- Only `decide_pvv()` (and its callers/tests/docs) changes.

## 1. Outlook input

`drv_rr.outlook` for `(as_of_date=D, tos_symbol)` — values
'Bullish'/'Bearish'/'Neutral' (case-insensitive match, trim). NULL (BB
fallback rows, `source='BB'`) or missing row → no outlook.

## 2. New decision matrix (outlook × sig_today)

| sig_today ↓ \ outlook → | **Bullish** | **Bearish** | Neutral / NULL |
|---|---|---|---|
| STRONG_BULL | BUY | TRIM | WATCH |
| WEAK_BULL | BUY | TRIM | WATCH |
| OVEREXT_BULL | TRIM | TRIM | WATCH |
| BEAR_DIV | WATCH | TRIM | WATCH |
| NEUTRAL / NA | WATCH | AVOID | WATCH |
| DRIFT | **BUY_DIP** | AVOID | WATCH |
| MILD_BEAR | **BUY_DIP** | REDUCE | WATCH |
| BEAR_LEAN | **BUY_DIP** | REDUCE | WATCH |
| STRONG_BEAR | WATCH *(knife guard)* | SELL | WATCH |

Notes:
- **Knife guard**: bullish outlook + STRONG_BEAR (heavy-volume selloff, vol
  spiking) deliberately does NOT fire BUY_DIP — it waits at WATCH.
- **Sell the rip**: bearish outlook + any up-tape day → TRIM.
- Neutral outlook and no-outlook (BB fallback) are both WATCH across the
  board; distinguish them in detail (`"outlook": null` vs `"Neutral"`).
- 5d/3w/3m signals no longer influence the decision — display-only context.
- Decision vocab unchanged (BUY, BUY_DIP, TRIM, WATCH, AVOID, REDUCE,
  SELL) so `_pvvRank`/badge colors need no edits.

## 3. Code changes

- `etl/derive_pvv.py`:
  - `decide_pvv(sig_today, outlook)` — new signature, pure function, the
    matrix above verbatim. Delete the old rule-1..8 logic.
  - `_derive_pvv_impl`: fetch `drv_rr.outlook` for D (one query, LEFT JOIN
    into the symbol loop), pass to `decide_pvv`.
  - `detail` JSONB: add `"outlook": {"value": "Bullish"|"Bearish"|"Neutral"|null,
    "source": "RR"|"BB"|null}`.
- `web/actionable.js` (`_buildPvvPopHtml`): add one line at the top of the
  tooltip — `Outlook: Bullish (RR)` (or "no outlook — BB fallback") — and
  a short "decision = outlook × today" formula line. Bucket rows unchanged.
- `docs/pvv_logic.md`: replace the decision-matrix section; note explicitly
  that 5d/3w/3m are informational context only as of this task.

## 4. Tests

- Rewrite the decision-rule tests in `tests/test_pvv_classify.py`: full
  9×3 matrix + NULL outlook + case-insensitivity. Bucket-classification
  tests (classify_pvv / classify_pvv_3m) untouched.
- Acceptance: after re-derive, `SELECT decision, COUNT(*) FROM drv_pvv
  WHERE as_of_date=<anchor> GROUP BY 1` returns a sane mix; spot-check one
  BUY_DIP symbol has outlook='Bullish' and sig_today in
  (DRIFT, MILD_BEAR, BEAR_LEAN).

## 5. Re-derive + backfill

Re-run `derive_pvv` for the current anchor and re-backfill the same
historical date range as TASK_125 (drv_pvv-only loop, idempotent) so the
stored decisions all reflect the new matrix.

## How to verify (tester reference — run only on explicit request)

1. `pytest tests/test_pvv_classify.py` → pass (new matrix cases included).
2. `psql`: pick 3 symbols with outlook='Bullish' and sig_today='DRIFT' →
   all decision='BUY_DIP'; 1 with outlook='Bullish' + sig_today='STRONG_BEAR'
   → 'WATCH'; 1 with outlook='Bearish' + a bull sig_today → 'TRIM'.
3. `psql`: symbols with `drv_rr.source='BB'` (NULL outlook) → all 'WATCH',
   detail.outlook.value is null.
4. UI: PVV tooltip shows the Outlook line above the bucket table.

## Files expected to change

`etl/derive_pvv.py`, `web/actionable.js`, `docs/pvv_logic.md`,
`tests/test_pvv_classify.py`, `tests/acceptance/...`. No schema change.

No commits — user commits from Windows.
