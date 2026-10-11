# AGENT_WORK — Developer pointer

## ✅ Cowork has coded ALL remaining Hedgeye enhancements. Developer: VERIFY + RUN.

Cowork implemented everything directly in code (no per-task handoff). Your job now is to
apply, run, and smoke-test it on the live DB + app, then hand to the tester.

### Run checklist (see `COWORK_IMPL_LOG.md` for the full file list)
1. `python -m db.init_db` — applies `db/baseline.sql` (feed_code columns on
   ref_load_files + ref_hedgeye_email_type; `v_feed_catalog` view).
2. `psql -d trading -f db/seeds_feed_code.sql`.
3. Restart app + scheduler (api/ and etl/ changed; use `--reload-dir api`).
4. Verify syntax on Windows (the sandbox flagged false truncations on in-session-edited
   files — confirm real files parse):
   `python -c "import ast; ast.parse(open(r'api/main.py').read())"` and
   `node --check web/hedgeye_panel.js`.
5. Smoke-test endpoints: `/api/actionable/hedgeye?date=2026-06-26`, `/api/notes`,
   `/api/notes/source-types`, `/api/rule-candidates` (GET + POST + PATCH),
   `/api/digest/preopen`, `/api/digest/weekly`, `/api/macro/hedgeye-quad`,
   `/api/symbol/AAPL/hedgeye`, `/api/notes/<message_id>/llm`.
6. Smoke-test pages: Hedgeye panel on `/actionable`; `/notes`, `/digest`,
   `/symbol-hedgeye?sym=AAPL`.
7. Record results in `DEV_HANDOFF.md`, end `ALL_DONE`. Then the tester runs.

### What was built (all coded by Cowork — see COWORK_IMPL_LOG.md)
- Feed catalog (`feed_code` + `v_feed_catalog`) · Actionable Hedgeye panel
  (`/api/actionable/hedgeye` + `web/hedgeye_panel.js`) · Notes browser + rule-candidate
  builder (`/notes`) · Pre-open & weekly digests (`/digest`) · Hedgeye Quad signal ·
  Per-symbol dossier (`/symbol-hedgeye`) · LLM read endpoint (display-only).

### Done earlier by the dev agent
- TASK_99/98/96/95/94/93 (all `ALL_DONE`).
