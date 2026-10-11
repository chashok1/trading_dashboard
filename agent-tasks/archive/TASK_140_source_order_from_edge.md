# TASK_140 — Rank sources by measured edge, not by a hand-typed list

## Context

`etl/derive_actionable.py` picks `consolidated_action` from whichever source
sits highest in a static dict:

```python
SOURCE_ORDER = {"RTA": 1, "TOP5": 2, "SSSCHG": 3, "PS": 4, "ETF": 5, "RR": 6,
                "SSS": 7, "II": 8, "CALL": 9, "RTAINFO": 10, "MACROSHOW": 11}
```

Measured buy-family 20d edge (`v_source_edge_scorecard`, 2026-07) for the six
outlook sources this task touches:

| source | edge_20d | n | static rank |
|---|---|---|---|
| RR   | **+2.84** | 1,888 | 6 |
| SSS  | **+2.33** | 302 | 7 |
| CALL | +0.52 | 7,945 | 9 |
| II   | −1.42 | 170 | 8 |
| PS   | **−2.07** | 106 | **4** |
| ETF  | **−3.40** | 51 | **5** |

The two negative-edge sources outrank the two best. Assumption A4 is recorded
**BROKEN** in `docs/actionable_playbook.md` §5 and the fix has sat in that
doc's follow-up queue since 2026-07-13.

**Prerequisite: TASK_139 must confirm A4 still holds on the second regime.** If
TASK_139 marks A4 FLIPPED or STILL THIN, stop and re-scope — do not ship a
re-rank fitted to a single bounce.

## Goal

The winner contest orders the six outlook sources by their own measured edge,
with the Hedgeye same-day triggers untouched and a one-row revert.

1. **`ref_source_precedence`** (new, in `db/baseline.sql`):
   `source_code TEXT PK`, `static_rank INT NOT NULL`,
   `measured_rank INT`, `buy_edge_20d NUMERIC`, `n INT`,
   `updated_at TIMESTAMP`. Seed `static_rank` with today's `SOURCE_ORDER`
   values exactly — this row set is the rollback anchor.

2. **`ref_settings.source_order_mode`**, seeded `'static'`.
   `'static'` = today's behaviour, byte for byte. `'measured'` = the new path.
   **This is the only switch, and it defaults to off.** Flipping it is the
   user's decision, not this task's.

3. **`etl/derive_source_edge.py`** — extend the existing nightly recompute
   (it already reads `v_source_edge_scorecard` for the weak-buy list) to also
   write `measured_rank` / `buy_edge_20d` / `n` into `ref_source_precedence`:
   - rank the six outlook sources **only** — `RR, SSS, CALL, II, PS, ETF` —
     descending by n-weighted buy-family (`ADD`+`INCREASE`) `edge_20d`;
   - a source with `n < 30` (the existing `_MIN_N` floor) keeps its
     `static_rank` and gets `measured_rank = NULL` — never guess off a thin
     sample;
   - ranks are emitted in the numeric band the six sources occupy today (4–9)
     so nothing collides with the Hedgeye tiers.

4. **`etl/derive_actionable.py::_order()`** — when
   `source_order_mode = 'measured'`, resolve the six outlook sources through
   `COALESCE(measured_rank, static_rank)`. **Do not touch** `RTA`, `TOP5`,
   `SSSCHG`, `RTAINFO`, `MACROSHOW` — those ranks encode "same-day trigger
   beats standing weekly list", a timing rule, not an edge claim, and they
   keep their current values under both modes.

5. **Also fix the not-held path.** Today unheld symbols sort by
   `(-latest_update, source_order)` — "most recent update wins" — which
   structurally favours `CALL`, the highest-volume / lowest-edge feed. Under
   `'measured'`, make it `(source_rank, -latest_update)`: rank first, recency
   as tie-break. Under `'static'`, leave it exactly as it is.

6. **Persist what won and why.** Add `drv_actionable.winning_source_rank INT`
   and `winning_source_edge NUMERIC`, filled from the row that won. Without
   this there is no way to measure afterwards whether the re-rank helped.

7. **UI:** on the Actionable row drilldown, next to the winning source, show
   its measured edge and n when mode is `'measured'`. Read-only.

8. **Docs:** `docs/migrations.md`; `docs/actionable_logic.md` (the winner-
   selection section); `docs/actionable_playbook.md` §5 A4 row → resolved,
   pointing here.

## Files expected to change

- `db/baseline.sql` (+ a `db/seeds_source_precedence.sql`)
- `etl/derive_source_edge.py`, `etl/derive_actionable.py`
- `api/routers/dash.py`, `web/actionable.js`
- `docs/migrations.md`, `docs/actionable_logic.md`,
  `docs/actionable_playbook.md`
- `DEV_HANDOFF.md`

## How to verify

1. `python -m db.init_db` idempotent; `ref_source_precedence` seeded with all
   eleven `static_rank` values matching the current dict.
2. **Mode `'static'` (default): re-derive the anchor and diff
   `consolidated_action` per symbol against the pre-change run — must be
   byte-identical, zero rows changed.** This is the most important check in
   the task.
3. Run the nightly job; `measured_rank` populated for sources with n ≥ 30,
   NULL for the rest, and RR/SSS rank ahead of PS/ETF.
4. Set `source_order_mode = 'measured'`, re-derive, and report: how many
   symbols changed action, and the before/after winning source for each. Hand
   that list to the user — **do not leave the mode on**; revert to `'static'`
   before writing `ALL_DONE`.
5. Confirm `RTA`/`TOP5`/`SSSCHG` winners are identical under both modes.
6. Confirm an unheld symbol whose only actions are a fresh `CALL` ADD and an
   older `RR` ADD resolves to `CALL` under `'static'` and `RR` under
   `'measured'`.
7. `winning_source_rank` / `winning_source_edge` populated on rows that had a
   winner, NULL where none.
