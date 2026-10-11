# TASK_98 — Ingest Log dashboard screen

**Type:** implementation (web UI). **Author:** Cowork. **Owner:** Developer agent.
**Depends on:** TASK_96 (`v_ingest_log` + `GET /api/ingest-log` already exist).

## Why

TASK_96 built the unified ingest ledger and its API but left the UI as a follow-up.
This adds a screen so Ashok can *see* — in one place — every file load and every email
processed, with filters, instead of running SQL.

## What to build (mirror the File Monitor screen)

Use `web/file_monitor.html` + `web/file_monitor.js` as the template (same header,
`/static/styles.css`, fetch-and-render-table pattern, optional auto-refresh).

1. **`web/ingest_log.html`** — standard page shell + nav header (copy from
   `file_monitor.html`), a filter bar, and a single results table.
   - Filter bar: a `channel` select (All / file_load / email), a `feed` text box
     (ILIKE), a `date` picker (YYYY-MM-DD), and a Refresh button.
   - Table columns: When (`processed_at`), Channel, Source (`source_kind` —
     file vs email), Feed, Target table, Data date, Status, Reference
     (`source_ref` — filename or message_id; truncate/long-titles ok).

2. **`web/ingest_log.js`** — on load and on filter change, `fetch('/api/ingest-log'
   + querystring)`, render rows newest-first. Build the querystring from the active
   filters (`date`, `channel`, `feed`, `limit`). Show a small count ("N rows"). Keep
   it dependency-free (vanilla JS like the other screens).
   - Visually distinguish `source_kind='email'` rows (e.g. a small badge) so the
     email-rendered file loads stand out from real files.

3. **Page route** — in `api/routers/pages.py` add:
   ```python
   @router.get("/ingest-log")
   def page_ingest_log():
       return FileResponse(WEB_DIR / "ingest_log.html", media_type="text/html; charset=utf-8")
   ```

4. **Nav link** — in `web/index.html` nav-menu, add
   `<a href="/ingest-log" class="nav-item">Ingest Log</a>` next to the File Monitor
   link. Add the same nav item to the shared header used by other screens if they
   carry their own copy (match how File Monitor appears across pages).

## How to verify

- Visit `http://localhost:8000/ingest-log` → table loads with recent ingests,
  newest first.
- Channel filter: "email" shows only Hedgeye messages; "file_load" shows only file
  loads. Feed filter (e.g. `RR`) narrows correctly. Date picker scopes to that day.
- A tab-backed feed (e.g. RR for a day) shows in both channels (email + file_load);
  `source_kind='email'` rows are visually flagged.
- Nav link appears and routes correctly; no console errors; existing screens
  unaffected.
- `pytest tests/` → no new failures (known pre-existing: test_task_86_regime_band_factors,
  test_task_90_histy_corr, test_agent_work_31, test_cat_parity).

## Done criteria

`/ingest-log` screen lists the unified ledger with working channel/feed/date filters,
email-origin rows flagged, nav link added; no regressions. Log to `DEV_HANDOFF.md`,
end `ALL_DONE`. No commits — Ashok commits from Windows.

## Out of scope

Live SSE auto-streaming (a periodic Refresh is enough); editing/acting on rows
(read-only screen).
