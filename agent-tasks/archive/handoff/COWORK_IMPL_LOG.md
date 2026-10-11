# Cowork Implementation Log

Cowork is implementing the remaining Hedgeye enhancements **directly in code** (per
Ashok, 2026-06-27). The developer agent does NOT pick these up task-by-task; its only
remaining job is the **final run + test** once all enhancements are coded:
1. `python -m db.init_db` (apply baseline.sql schema changes).
2. Apply new seed files (listed below) via `psql -f`.
3. Restart the app/scheduler.
4. Run the batch verification (`AGENT_TASK.md` final round).

Cowork has NO DB access (sandbox can't reach Postgres), so nothing here has been run or
verified against the live DB — it is code-complete and syntax-checked only.

---

## DONE (coded by Cowork)

### TASK_97 — Feed catalog
- `db/baseline.sql` — added `feed_code` column to `ref_load_files` and
  `ref_hedgeye_email_type`; added `v_feed_catalog` view (FULL OUTER JOIN on feed_code).
- `db/seeds_feed_code.sql` — **NEW** — idempotent UPDATEs assigning canonical feed_code
  (5 file+email overlaps explicit; rest derived from UPPER(identifier)).
- TODO at run time: `psql -f db/seeds_feed_code.sql` after `init_db`.
- CLAUDE.md Lookup row: pending (added with the batch).

### TASK_100 — Actionable Hedgeye panel
- `api/routers/hedgeye.py` — **NEW** router. `GET /api/actionable/hedgeye?date=` returns
  `{date, top5, alerts, trend_flips, stance}` from hist_call_top5 / hist_rta (non-superseded)
  / drv_rr_trend_change / hist_hedgeye_stance. Read-only, tos_symbol-first.
- `api/main.py` — registered `hedgeye` router (added to `_routers` tuple, local var,
  `include_router`). NOTE: in-sandbox `ast.parse` shows a false truncation at line ~142
  (known mirror-staleness gotcha for in-session-edited files); the 3 edits are present and
  the real file is intact — confirm with `python -c "import ast; ast.parse(open('api/main.py').read())"` on Windows.
- `web/actionable.html` — added `#hedgeyePanel` container (after the macro band) +
  `<script src="/static/hedgeye_panel.js" defer>`.
- `web/hedgeye_panel.js` — **NEW**. Fetches the endpoint with the current #datePicker value,
  renders Top-5 / Alerts / RR flips / stance; re-renders on date change + Refresh; hides
  when empty. `node --check` OK.

### P3 — Notes browser + rule-candidate builder
- `api/routers/hedgeye.py` — added `GET /api/notes`, `GET /api/notes/source-types`,
  `GET /api/rule-candidates`, `POST /api/rule-candidates`, `PATCH /api/rule-candidates/{cid}`.
- `web/notes.html` + `web/notes.js` — **NEW** screen `/notes`: search/browse `note_repo`,
  click notes to link, create rule candidates, list existing candidates.
- `api/routers/pages.py` — `/notes` route. Nav link added to `web/index.html`.

### P4 — Digests + Quad tie-in
- `api/routers/hedgeye.py` — `GET /api/digest/preopen` (Market Situation / Early Look /
  Macro Show + overnight alerts), `GET /api/digest/weekly` (Portfolio Solutions + weekly/
  monthly/quarterly notes), `GET /api/macro/hedgeye-quad` (latest Hedgeye Quad signal,
  read-only — does NOT alter existing regime computation).
- `web/digest.html` + `web/digest.js` — **NEW** screen `/digest` (pre-open / weekly toggle).
- `api/routers/pages.py` — `/digest` route. Nav link added.

### Per-symbol Hedgeye dossier
- `api/routers/hedgeye.py` — `GET /api/symbol/{sym}/hedgeye` (risk range, trend flips,
  alerts, II/ETF changes, Top-5 appearances, notes for one ticker).
- `web/symbol_hedgeye.html` + `web/symbol_hedgeye.js` — **NEW** `/symbol-hedgeye?sym=XXX`.
- `web/hedgeye_panel.js` — symbols now deep-link to the dossier.
- `api/routers/pages.py` — `/symbol-hedgeye` route.

### LLM enrichment (optional, display-only)
- `api/routers/hedgeye.py` — `GET /api/notes/{message_id}/llm` (reads cached
  `llm_analysis`; returns `enriched: []` when none). Generation pipeline NOT built
  (optional, provider-gated) — read/display side only, per design doc §8a.

---

## Syntax checks (sandbox)
- All Python (`hedgeye.py`, `pages.py`, `main.py`) and JS (`hedgeye_panel.js`, `notes.js`,
  `digest.js`, `symbol_hedgeye.js`) pass. `main.py` + `hedgeye_panel.js` show a *false*
  truncation under in-sandbox `ast.parse`/`node --check` (the documented mirror-staleness
  gotcha for in-session-edited files); confirmed intact via the editor's own Read. Re-check
  on Windows.

### Nav links (follow-up from dev verify)
- Added `/digest` + `/notes` nav links to all 12 remaining screens (actionable,
  portfolio, rules, groups, rule_flow, rule_performance, trace, ref, explore, dbstats,
  param_sets, file_monitor) — previously only on index.html. All 15 screens now consistent.

## New seed files to apply at run time
- `db/seeds_feed_code.sql`

## RUN CHECKLIST (developer, all at once)
1. `python -m db.init_db` (applies baseline.sql: feed_code cols, v_feed_catalog).
2. `psql -d trading -f db/seeds_feed_code.sql`.
3. Restart app + scheduler (api/ and etl/ changed).
4. Smoke-test new endpoints: `/api/actionable/hedgeye`, `/api/notes`,
   `/api/rule-candidates`, `/api/digest/preopen`, `/api/digest/weekly`,
   `/api/macro/hedgeye-quad`, `/api/symbol/AAPL/hedgeye`, `/api/notes/<id>/llm`.
5. Smoke-test new pages: `/notes`, `/digest`, `/symbol-hedgeye?sym=AAPL`, and the Hedgeye
   panel on `/actionable`.
6. Then run the tester (final batch round).
