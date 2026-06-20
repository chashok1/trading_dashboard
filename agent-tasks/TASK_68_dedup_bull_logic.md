# TASK 68 — De-duplicate bull/bear logic (one source of truth each)

**You: VS Code developer agent, psql + code.** Log progress in `DEV_HANDOFF.md`; end with
`ALL_DONE`. **DO NOT COMMIT/PUSH.**

> **NOT blocked — can run in parallel with TASK 65/66/67.** This is behavior-preserving
> cleanup. Do each item as its own small, verifiable change.

## Why (one line)
The same bull/bear logic is implemented in several places and the copies have already
drifted, so a screen can show one thing while the engine does another. Collapse each to a
single source of truth without changing behavior. Background:
`docs/audit/bull_calc_analysis.md` §3 (D1–D7).

## The duplications to fix (priority order)

### D5 — action-code → buy/sell side  ★ highest risk, do first
Four hand-maintained lists that already disagree (`BC`,`BRW`,`SWW`,`SN` present in some,
absent in others):
- `db/baseline.sql::v_rule_scorecard` direction regex
- `web/_common.js::renderRRAnalysis` `isBull`/`isBear`
- `web/rule_flow.js::buysellColor` + `_compSide`
- `web/actionable.js::_RULE_EXTRA` (+ `actionDisplay`)

**Fix:** one canonical map. Preferred: a DB-driven map (extend the existing
`ref_param_lookup table_name='buysell'`, which already has the scores) exposed via a tiny
endpoint, plus **one** JS helper (e.g. in `web/actions.js`) that all screens import.
Delete the other three JS lists and the inline regex's hand-list (keep the regex only if
it's reconciled to the canonical set). Document the one true list.

### D4 — RR "decision path" recomputed in JS
`web/_common.js::renderRRAnalysis` re-implements the QF<0 / QK<0 / QO branch from raw
component scores. **Fix:** have the backend expose the already-computed QR/QS decision
(it's in `drv_tn_td_bb_rr` / `_derive_trend_trade_rules_impl`) and make the JS *display*
it instead of re-deriving. No recompute in the browser.

### D6 — finalCall reimplemented in JS
`web/actionable.js::finalCall` is a full reimplementation used as fallback. It already
prefers server `final_code`/`fc_side` when present. **Fix:** ensure the server always
populates those, then reduce the JS to display-only (or keep a thin, clearly-labeled
fallback). Don't maintain two decision engines.

### D3 — outlook → color, two palettes
`web/actions.js::outlookColor` (canonical) vs `web/market_bar.js::outlookBg` re-deriving
with different hex. **Fix:** `market_bar.js` uses `outlookColor()` only; delete its
fallback palette.

### D1 — change_str → token, written twice
`derive_source_standing._normalize_change_str` (Python) and
`derive_outlook_action._normalize_change_str_sql` (SQL). **Fix:** keep one. Prefer the
Python helper as source of truth; if SQL needs it inline, generate/centralize so both
can't drift (or drop the SQL copy if that path is dead).

### D2 — ETF/II bundle-cap state, written twice
Canonical `derive_source_standing._build_etf_ii` (live) vs legacy
`derive_outlook_action._state_etf_ii`/`_state_etf_ii_tos` (prev-period only). **Fix:**
make the prev-period path read from `drv_source_standing` snapshots and delete the
legacy duplicate implementation.

### D7 — brr sign threshold duplicated
`brr>0/<0` appears in both `_composite_outlook` and the `etf_outlook` COALESCE. **Fix:**
one small shared helper/constant.

## Non-negotiables
- **Behavior-preserving.** Output values and on-screen results must be identical before/
  after each item (except where a copy was *wrong* — call those out explicitly in
  `DEV_HANDOFF.md` with the corrected behavior).
- One item = one self-contained change you can verify independently. Don't bundle.
- Conventions hold (#7 SQL length, #15 tos_symbol).

## Files expected to change (indicative)
`db/baseline.sql`, `api/routers/{rules,trace,dash}.py`, `web/{actions,_common,
market_bar,actionable,rule_flow}.js`, `etl/{derive,derive_source_standing,
derive_outlook_action}.py`.

## How to verify (tester reference — only on request)
1. **D5:** the canonical buy/sell map lists exactly the codes in use; all four former
   lists now resolve through it; pick 5 codes incl. `BC`/`BRW`/`SWW`/`SN` and confirm
   every screen agrees on side/color.
2. **D4:** for several symbols, the screen's RR decision text == the backend QR/QS
   decision (no divergence).
3. **D6:** with server `final_code` present, JS path is display-only; final call matches
   server for a sample of symbols.
4. **D3:** same outlook renders the same hex on market bar and actionable screens.
5. **D1/D2/D7:** derive outputs unchanged for a sample of symbols/dates after removing
   the duplicate implementations (diff before/after).
6. No console errors; existing screens visually unchanged.
