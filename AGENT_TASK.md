# AGENT_TASK — tester pointer

## ✅ FINAL BATCH TEST — run after the developer's `DEV_HANDOFF.md` ends `ALL_DONE`.

Ashok deferred all testing to one end-of-project round. Now is that round: verify the
full Hedgeye enhancement set against the live DB + running app. Write evidence to
`AGENT_RESULT_final.md`, ending `DONE` or `FAILED: <blocks>`.

Pre-req gate: `DEV_HANDOFF.md` (developer's run/verify pass) must end `ALL_DONE` first.

### Scope — run every checklist together

1. **TASK_95** — `agent-tasks/TASK_95_verify.md` (unify-on-loader, source_kind,
   precedence, IIChange = ETFChange format).
2. **Earlier specs' "How to verify"** — TASK_96 (`v_ingest_log` + `/api/ingest-log`),
   TASK_98 (Ingest Log screen), TASK_99 (IIChange render).
3. **Cowork-built work** (see `COWORK_IMPL_LOG.md`):
   - Feed catalog: `SELECT feed_code,file_type,email_type FROM v_feed_catalog ORDER BY 1;`
     — 5 overlaps show both recognizers; no NULL feed_code for data-bearing feeds.
   - Actionable panel: `/api/actionable/hedgeye` returns top5/alerts/trend_flips/stance;
     panel renders on `/actionable`, date-linked; superseded RTAs excluded.
   - Notes + rule candidates: `/notes` browses note_repo; create + list rule_candidate works.
   - Digests: `/digest` pre-open and weekly load with real content.
   - Quad signal: `/api/macro/hedgeye-quad` returns the latest quad note.
   - Dossier: `/symbol-hedgeye?sym=AAPL` shows per-symbol Hedgeye data; panel symbols link to it.
   - LLM read endpoint: `/api/notes/<id>/llm` returns `enriched: []` (or rows if present).
4. Full `pytest tests/` — no NEW failures vs the known baseline
   (test_task_86*, test_task_90*, test_agent_work_31*, test_cat_parity*).

Quote offending rows on any failure.
