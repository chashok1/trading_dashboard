# TASK_93 — Wire up & run the Hedgeye email pipeline

**Type:** implementation + live run. **Author:** Cowork. **Owner:** Developer agent
(has Postgres + app + can set secrets). **Design:** `docs/hedgeye_feeds_design.md`
(Decision log + §8a + §9). **Diagram:** `docs/diagrams/hedgeye_pipeline.svg`.

Cowork already authored the deterministic, no-LLM core and unit tests; it could not
touch Postgres/Gmail (sandbox). Your job is the DB + credentials + live wiring.

## What Cowork already wrote (review, don't rewrite)

- `etl/hedgeye/parsers.py` — pure parsers for all 12 structured types (tested).
- `etl/hedgeye/classify.py` — subject/asset/meta router; DROP + UNKNOWN handling.
- `etl/hedgeye/source.py` — IMAP reader (+ Gmail-API stub) → `Email`.
- `etl/hedgeye/dispatch.py` — writes tables/note_repo/media + ledger + correction reverse.
- `etl/hedgeye/config.py` — ref_settings/.env loader.
- `etl/hedgeye_fetch.py` — CLI poller (`--dry-run/--once/--loop/--backfill`).
- `db/hedgeye_schema.sql`, `db/seeds_hedgeye.sql` — NEW objects + router/seed rows.
- `tests/test_hedgeye_parsers.py`, `tests/test_hedgeye_classify.py` — 29 tests
  (28 green in the Cowork sandbox; the 1 `test_early_look` failure was a stale-mirror
  cached compile — the fix is in source at `parsers.py:589`; a clean `pytest` run will
  be green — confirm in step 6).

## Steps

1. **Schema.** Fold `db/hedgeye_schema.sql` into `db/baseline.sql` (Rule 5) and the seed
   into a `db/seeds_hedgeye.sql` reference; then `python -m db.init_db`. Confirm all NEW
   objects exist: `meta_hedgeye_msg, hist_rta, hist_call_top5, hist_hedgeye_stance,
   hist_sss_change, note_repo, llm_analysis, hist_media, rule_candidate,
   ref_hedgeye_email_type` + view `drv_rr_trend_change`.

2. **Reconcile existing-table column mappings** (Cowork could not see live schemas).
   The parsers emit normalized dicts for these EXISTING tables — confirm column names and
   add a thin adapter in `dispatch.py` if they differ:
   - `hist_rr`  ← risk_range rows (`symbol, tos_symbol, outlook, buy_trade, sell_trade,
     last_price, market_close, snapshot_date`).
   - `hist_iichg` ← investing_ideas (`action, side, symbol, snapshot_date`).
   - `hist_etfchg` ← etf_changes (`action, side, symbol, snapshot_date`).
   - `hist_call` ← the_call POSITIONS (`symbol, outlook, snapshot_date`) — note the
     existing tab loader also writes `hist_call`; confirm the email source is additive,
     not conflicting (dedupe on `(snapshot_date, symbol)`).
   - `hist_ps`  ← portfolio_solutions (`rank, ticker, snapshot_date`; enrich remaining
     columns — entry date, asset class, position sizing — from the same HTML table).
   - `hist_macro` ← inflation_nowcast (`series_id='HE_CPI_NOWCAST', obs_date, value`);
     confirm `ref_macro_series` accepts the seeded series.

3. **Credentials + settings.** In `.env`: `HEDGEYE_IMAP_PASSWORD` (Gmail app-password for
   `chilukua14@gmail.com`, IMAP enabled). In `ref_settings` (seeded): set
   `hedgeye_enabled=true` only after a clean dry-run. Confirm `hedgeye_image_dir` points
   at a real writable folder.

4. **Dry-run classification** (no writes):
   `python -m etl.hedgeye_fetch --dry-run` → spot-check that ~last 2 days of emails map to
   the right types, marketing/Access-Here/MOMO are dropped, nothing is mis-bucketed.

5. **Live one-pass + backfill.** `--once`, inspect rows; then
   `python -m etl.hedgeye_fetch --backfill 2026-06-24` and verify counts (see TASK_93 verify).
   Re-run `--once` → confirm `meta_hedgeye_msg` makes it idempotent (no dupes).

6. **Tests.** `pytest tests/test_hedgeye_parsers.py tests/test_hedgeye_classify.py -q`
   → expect 29 passed. Then full `pytest tests/` → no regressions.

7. **Schedule.** Add the poller to the app's scheduled tasks (or Windows Task Scheduler),
   interval = `hedgeye_poll_interval_sec`. Do NOT fold the IMAP poll into `scheduler.py`'s
   file-watch loop unless it stays off the `--reload-dir` path.

8. **Derive trigger.** After a DATA load advances data for date `D`, ensure `derive_all(D)`
   runs (reuse the existing trigger) so `drv_*` + `drv_actionable` pick up the new rows.

## Out of scope (separate follow-up task)

UI panels (`/api/symbol/{sym}/hedgeye` dossier, actionable-screen Top-5 panel, macro-book
panel, notes/rule-builder pages) and the optional LLM enrichment lane. Backend + data
correctness first.

## Done criteria

DDL applied; dry-run classification correct; `--once` + backfill populate the tables;
idempotent on re-run; correction auto-reverse works; `drv_rr_trend_change` returns flips;
`pytest tests/` green. Log progress to `DEV_HANDOFF.md`, ending `ALL_DONE`. No commits —
Ashok commits from Windows.
