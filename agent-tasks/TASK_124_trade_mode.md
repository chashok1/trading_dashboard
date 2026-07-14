# TASK_124 — Trade Mode: show only rows that need action

## Context

`docs/actionable_playbook.md` §3.3 (rewritten from the TASK_123 measurements
in `docs/audit/signal_validation_2026-07.md`) defines the narrow subset with
measured positive edge. The user wants the screen to *show only that subset*
on demand instead of ranking 1,100+ rows. User decision (2026-07-13): buys
from **all sources** qualify — but rows backed by a source that measured
negative buy-edge get a visible "WEAK SRC" tag rather than being hidden.

Display layer + one small API addition. **No derive/rule/threshold changes.**

## Behavior

A **"Trade Mode"** toggle in the Actionable toolbar (persisted in
localStorage, default OFF, styled like the existing icon toggles but with a
1-word label — see U7 precedent). When ON, the grid shows ONLY:

1. **Qualifying buys** — ALL of:
   - `final_code` ∈ {BM, BMN} and `fc_feasible`
   - `rr_bull_bear = 'B'` (new payload field, see API below)
   - not `stop_breached`
   - MACRO not bearish: `macro_value` NOT IN (SA, STM)
   - any winning source qualifies; if the winning source is in the
     weak-source list (see below), render a small **WEAK SRC** pill next to
     the symbol (amber tint; reuse `.stop-pill`/`.new-pill` shape)
2. **Sells** — held rows with `final_code = 'SA'`
3. **Stop breaches** — held rows with `stop_breached = TRUE` (whatever the
   action)

Everything else hidden — including the Watchlist band and HOLD/no-action
rows. Toggle OFF restores the full grid exactly as it is today.

Details:

- Apply Trade Mode at the base-filter level (`baseRows` vs `rows` split) so
  summary/filter chips recount against the visible set, consistent with the
  existing filter architecture.
- Empty state when ON and nothing qualifies: "No trades today — nothing
  passed the playbook checks." (positive framing, distinct message).
- Focus mode and bulk bar operate on the filtered set (existing behavior —
  verify, don't rework).
- "?" legend: add a short Trade Mode block quoting the criteria above and
  what WEAK SRC means ("source measured negative buy-edge in the last
  validation — size down or skip; see docs/audit/signal_validation_2026-07.md").

## Weak-source list — tunable, not hardcoded

New `ref_settings` row: `trade_mode_weak_buy_sources` = `'PS,ETF,II'`
(seed in `db/baseline.sql` following the existing `stop_pct`/`macro_thr_*`
pattern; INSERT ... ON CONFLICT DO NOTHING). Serve it through the existing
`GET /api/actionable/settings` (TASK_106). Client reads it there — no
hardcoded source list in JS. When a future validation run changes the
verdict, the user updates one settings row.

## API — expose `rr_bull_bear`

`GET /api/actionable` (api/routers/dash.py::get_actionable) already joins
`drv_tn_td_bb_rr`; add `rr_bull_bear` to the selected columns and row dict.
Confirm the column name via `information_schema.columns` first (TASK_123
verified it exists and is populated). No other API changes.

## Files expected to change

- `web/actionable.js` — toggle, base filter, WEAK SRC pill, empty state,
  legend text
- `web/actionable.html` — toggle button, pill CSS
- `api/routers/dash.py` — `rr_bull_bear` in payload; settings passthrough if
  `/api/actionable/settings` doesn't already return arbitrary ref_settings
- `db/baseline.sql` — one seeded `ref_settings` row (additive)
- `DEV_HANDOFF.md` (append; end `ALL_DONE`)

## Constraints

- No derive/rule changes; no new derive columns.
- Additive SQL only; SQL commands ≤ 965 bytes.
- Toggle OFF must be pixel-identical to current behavior (this feature must
  be invisible until opted into).

## How to verify

1. Toggle OFF: grid identical to pre-task (row counts, tiers, band) on the
   live anchor.
2. Toggle ON at the live anchor: every visible row satisfies exactly one of
   the three categories; report the counts (buys / SA sells / stop rows) and
   spot-check 3 buys (BM/BMN + B + no stop + MACRO not SA/STM).
3. A qualifying buy whose winning source is PS, ETF, or II shows the WEAK
   SRC pill; an RR/SSS-backed one does not.
4. `UPDATE ref_settings SET setting_value='PS' WHERE
   setting_name='trade_mode_weak_buy_sources';` + reload → only PS rows
   tagged (then restore to 'PS,ETF,II').
5. Chips recount under Trade Mode; Focus mode iterates only visible rows;
   empty state shows the new message when nothing qualifies.
6. Toggle state survives a page reload (localStorage).
7. `node --check web/actionable.js` passes; `python -m db.init_db` applies
   cleanly.
