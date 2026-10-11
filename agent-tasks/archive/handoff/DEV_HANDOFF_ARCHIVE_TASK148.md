# Dev Handoff — AGENT_WORK_48 (TASK_148)

## Step 0 — Cleanup
Moved (git mv for tracked, plain mv for untracked; nothing deleted):
- `agent-tasks/TASK_*.md` except 148: 61 -> `agent-tasks/archive/`
- Root `AGENT_WORK_<n>.md` 47, `TEST_REPORT_<n>.md` 24, `AGENT_RESULT_93.md` 1 -> `agent-tasks/archive/handoff/`
- `DEV_HANDOFF.md` -> `agent-tasks/archive/handoff/DEV_HANDOFF_ARCHIVE_TASK147.md`
- `DEV_HANDOFF_ARCHIVE_TASK132.md`, `COWORK_IMPL_LOG.md` -> `agent-tasks/archive/handoff/`
- Total in `archive/handoff/`: 74 files (47+24+1+3).
- `AGENT_TASK.md` reset; this fresh `DEV_HANDOFF.md` started; one line added to `docs/agent_handoff_workflow.md`.
- Current round's `AGENT_WORK.md` was then archived as root `AGENT_WORK_48.md` (N=48).

References fixed (paths now point into the archive): `CLAUDE.md` (TASK_74 lookup row),
`docs/actionable_dataflow_analysis.md` (TASK_92 x2), `docs/bull_rollout_runbook.md`
(TASK_65..69 + AGENT_WORK_7), `docs/source_standing_logic.md` (TASK_9).
Left alone: `.claude/`, `agent-setup/` (only generic `AGENT_WORK_<n>` templates), `docs/migrations.md`, `docs/audit/*`.

`git status --short` before: 14 lines, all untracked (Claude outputs/, screenshot, TOSDownloads/*.png|csv|xlsx,
agent-tasks/TASK_148, docs/mockups/*, temp_compare/) — no modified tracked files.
After (excluding the rename/untracked entries under agent-tasks/archive): the same 14 untracked items plus
modified `AGENT_TASK.md`, `CLAUDE.md`, 4 docs, `api/routers/cockpit.py`, `web/index.html`, `web/styles.css`,
`docs/dashboard_cockpit_design.md`, new `web/macro_week.js`, renamed `AGENT_WORK_48.md`, new `DEV_HANDOFF.md`.

## TASK_148 — Macro Week Strip
### Files changed
- `api/routers/cockpit.py` — new `GET /api/cockpit/macro-week` (+ helpers `_mw_quad_chips`, `_mw_he_state`). Live queries only, no new table, no schema change.
- `web/macro_week.js` (new) — renders strip + checklist.
- `web/index.html` — `#macroWeekStrip` / `#macroWeekList` siblings under `#regimeLineBody`; script tag; styles.css cache-bust bumped.
- `web/styles.css` — `.mw-*` rules (CVD-safe `--mr-*` colours, every state also has a glyph).
- `docs/dashboard_cockpit_design.md` (addendum), `CLAUDE.md` (one Lookup row), `docs/agent_handoff_workflow.md` (Step 0 line).
- Not touched: derive_actionable.py, ref_trig_*, SOURCE_ORDER, ref_settings, ref_risk_gauge (git diff confirms; no etl/ or db/ change, so no server restart needed — api reloads).

### Answers to "could not verify" (live DB, anchor 2026-10-09)
- macronet sign: positive = tailwind (>= 1.25 is BM, <= -0.6 is SA). 547 symbols > 0, 168 < 0.
- drv_outlooks vocab is mixed-case: BULLISH / Bullish / BEARISH / NEUTRAL; ii_outlook also Long / Short (and BULLISH). Normalised case-insensitively (Long = bull, Short = bear, NEUTRAL = covered but neither).
- ref_econ_indicator is STALE (max date 2026-08-22, 9 rows flagged `show_on_dashboard='Y'`) and `expected` holds BULLISH/BEARISH, never a numeric forecast. `ref_calendar_event` is current (future dates through Nov) and is already the primary source for the Econ panel -> used it. Consequence: **no "exp 0.3%" anywhere** (no source has it). Spec/live disagree; live wins.
- ref_quad_periods: monthly 2026-10 = Q2 (argmax 44%), quarterly 2026 Q4 = Quad 2. There is **no global row for Q4 2026** (latest is Q3 2026 = Quad 3). Chip falls back to the latest global row at/before the current quarter and marks it `G3*` with a tooltip explaining.
- drv_quote fresh on 2026-10-09: `$DXY` 102.231, `TNX:CGI` 52.44 (x10), `VIX` 14.84, `MOVE:GIF` 98.4735. drv_rr has `$DXY` (101.4-102.58, BULLISH) and `TNX:CGI`; MOVE and VIX have no RR range used by the chips.

### Decisions
- Quad M/Q/G reuses `_mr_current_quad_label` (monthly argmax) in cockpit.py; quarterly/global read `quad` directly.
- 10Y: `<15` is treated as plain percent and x10-normalised (same rule as derive_risk_dial `_normalize_tnx`); "red" = at/above the highest active `ref_level_watch` TNX level (50 = 5.00%). Live: 5.24% -> shown with warning glyph.
- VIX/MOVE bucket from `ref_vol_threshold` (VIX 19/30, MOVE 100/120): calm / chop / high. Live: both calm.
- DXY/10Y/VIX/MOVE arrow = 5-session change (6th most recent drv_quote row). Arrows are neutral-coloured (direction is not good/bad).
- Next-event chip: "major" names (CPI, PPI, NFP, Fed/FOMC, GDP, PCE, retail sales, ISM, JOLTS, Jackson) within 7 days, day-of-week only (no time exists). No major in 7 days -> chip absent. The popover's "Next 7 days" lists everything from `ref_calendar_event` (major ones flagged).
- Verdict: Aligned = tailwind + HE majority bull; Against = headwind + HE majority bear; everything else Mixed; range >= `macro_area_hot_pct` (0.85) forces Mixed (literal spec reading, also overrides Against); no HE coverage -> Quad fit alone (macronet 0/NULL -> Mixed). "Majority" = more than half of non-blank HE sources.
- **Layout deviates from spec:** the Regime band lives in the right rail, only ~206px wide at 1200px (300px at 1600, 376px at 1920). One 846px line cannot fit. The strip therefore wraps (measured 70px = 4 short lines at 1200px, vs the spec's +24px target). To keep the checklist at 0px when closed and readable when open, it is a fixed-position popover (760px max, anchored to the strip's right edge, closes on Escape/outside click) rather than an inline expansion. If you want the one-line target, the strip would have to move out of the rail (e.g. full-width above the three columns) — a layout decision for the user.
- Quad chip duplicates information already shown in the Regime line above it (60d / Qtr); kept because the spec lists it.

### SQL used to check chips (anchor 2026-10-09)
- `select tos_symbol,last_price,net_chng from drv_quote where as_of_date='2026-10-09' and tos_symbol in ('$DXY','TNX:CGI','VIX','MOVE:GIF')` -> 102.231 / 52.44 / 14.84 / 98.4735 (match chip values 102.2, 5.24%, 14.8, 98).
- `select lrr,trr,outlook from drv_rr where tos_symbol='$DXY'` -> 101.4 / 102.58 / BULLISH; (102.231-101.4)/(102.58-101.4) = 70% (match).
- `select * from ref_vol_threshold`, `ref_level_watch where tos_symbol='TNX:CGI'` -> thresholds above.
- `select category,event_date from ref_calendar_event where event_date between '2026-10-09' and '2026-10-16'` -> JOLTS Mon 10/12, CPI x3 Wed 10/14 (chip shows "JOLTS Mon").
- Holdings: `drv_portfolio` held_qty_fid+held_qty_cs > 0 on 2026-10-09 = 41 rows, all listed (21 aligned / 20 mixed / 0 against). Spot checks: AAPL tailwind (1.85), HE rr up/call down = 1/2 -> Mixed; META headwind (-0.82) with 2/2 bull -> Mixed; CLOX tailwind, etf bull, range 27% -> Aligned; CELH tailwind, no HE ("----"), price above TRR (hot) -> Mixed.

### How to test
- App is running with reload; just open `/` (hard refresh). `curl http://127.0.0.1:8000/api/cockpit/macro-week` returns the JSON.
- `node --check web/macro_week.js`; `python -c "import ast;ast.parse(open('api/routers/cockpit.py',encoding='utf8').read())"` — both pass.
- `pytest tests/test_dashboard_middle_column.py -q` -> 64 passed. I did NOT run the whole `pytest tests/` suite (project memory: a full run once sent real emails via an unmocked notify()); orchestrator/tester decides.
- Playwright check at 1200px: strip visible inside `#crossAssetPanel`; checklist `hidden` (0px) until the Book chip is clicked; popover lists all 41 holdings (top 7 + "show all 41"), Next 7 days column on the right.

### Risks & notes
- 20 of 41 holdings are "Mixed" mainly because the top-of-range rule fires on 20 (many are above TRR, rr_pos clamps to 100%). That is the spec rule applied literally; "against" is empty today partly because of it (BUXX/WST/META/XLV/TXG are headwind but hot or HE-bull).
- BUXX (ultra-short bond ETF, $93k) is the top row — it is not cash per `is_cash()` but its range is 6 cents wide, so it is always "hot". Cosmetic data quirk, not changed.
- `is_cash(p.tos_symbol, NULL, NULL)` is a symbol-only guard; drv_portfolio contains no cash rows today anyway.
- Global quad Q4 2026 is missing in /ref — add it to remove the `*`.
- No tests written (policy #18 / role). Unrelated: root has no stray files left from me.

## Status
ALL_DONE
