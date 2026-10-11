# TASK_95 — Unify tab-backed Hedgeye feeds on the existing file loader

**Type:** implementation (refactor of the shipped Hedgeye path). **Author:** Cowork.
**Owner:** Developer agent (Postgres + can run `etl.hedgeye_fetch` and the scheduler).
**Depends on:** TASK_93 (shipped Hedgeye pipeline). **Design:** `docs/hedgeye_feeds_design.md` §5.

> Supersedes the earlier "direct-insert + emit a skipped file" draft of TASK_95.
> That approach is dropped: it kept two parsers for the same target tables. This
> task removes that duplication instead of papering over it.

## Why

Ashok runs the legacy Excel `Tickers` workbook **and** the DB app in parallel.
Today the Hedgeye email path parses + inserts rows directly into `hist_*` — a second
copy of the column/parse logic the file loader already owns. Instead, the email path
should render each tab-backed feed into the **workbook-format file the existing loader
already understands**, drop it in the watched source dir, and let the normal
scheduler → loader → derive flow ingest it. One parser per target, and the same file
feeds the Excel workbook for free.

## Scope — the 5 tab-backed feeds (email_type → file/loader → table)

| email_type | file feed / loader | table | change-format carries action? |
|---|---|---|---|
| `risk_range` | `RR …xlsx` | `hist_rr` | n/a (outlook feed) |
| `investing_ideas` | `IIchg` tab → `load_iichg` | `hist_iichg` | yes — reads `Change`/`Action` (load_raw.py:815) |
| `etf_changes` | `ETFChange …xlsx` → `load_etfchg` | `hist_etfchg` | yes — reads `Action` (load_raw.py:1610) |
| `portfolio_solutions` | `PS …xlsx` | `hist_ps` | n/a |
| `the_call` | `call …csv` | `hist_call` | n/a |

The Hedgeye emails map to the **change** feeds (`investing_ideas → hist_iichg`,
`etf_changes → hist_etfchg`), whose file formats already have an Action column — so
**no information is lost and no tab format needs extending.**

**Out of scope — stay on direct-insert** (no workbook tab to render into):
`hist_rta`, `hist_call_top5`, `hist_hedgeye_stance`, `note_repo`, macro nowcast
(`hist_macro`). These keep the current `dispatch` + `_trigger_derive` path unchanged.

## Steps

1. **Resolve conventions from the source of truth.** For each in-scope feed, read its
   `source_dir` + filename/tab convention from `ref_load_files` (and/or
   `LoadFiles.xlsx`) — same resolver pattern as
   `etl/yahoo_fetch.py::_get_yfiles_dir()`. Then open the **latest live sample** of
   each feed and mirror sheet name, header row (incl. leading spaces like ` Outlook`,
   ` Ticker`, ` RANK`), and value/date formatting byte-for-byte.
   - **`IIchg` needs explicit confirmation:** there are NO `IIchg`/`IIChange` files in
     `etl/working/` (only II snapshots). Get its real filename + tab name from
     `ref_load_files` (file_type for `load_iichg`). `ETFChange …xlsx` is the analog;
     `load_iichg` reads an `IIchg` tab with a single-sheet fallback, columns
     Date / Ticker / Outlook / Description / Change(or Action).
   - Verified samples for the others: `RR …xlsx` sheet `Table_Section`
     (Index, Description, Outlook, BUY TRADE, SELL TRADE, Prev Close, RR Date);
     `ETFChange …xlsx` sheet `Data Sheet` (Date, ` Description`, ` Ticker`, ` Outlook`, ` Action`);
     `PS …xlsx` sheet `Data Sheet` (Date, ` RANK`, TICKER, 1-WEEKCHANGE, 1-MONTHCHANGE, ENTRYDATE, ASSET CLASS, POSITIONSIZING);
     `call …csv` (Date `MM/DD/YYYY`, Symbol, Outlook, Outlook Modifier).

2. **New module `etl/hedgeye/emit.py`** — one renderer per in-scope feed: parsed email
   rows → a file in the loader's exact format, written into that feed's `source_dir`.
   Pure and unit-testable (renderer takes rows + path, no network).

3. **Precedence — a real file wins (no collisions).** Before rendering, check whether a
   real file for that feed+date already exists (present in `source_dir`, or recorded in
   `meta_file_processed` with `source_kind='file'`). If yes, **skip** rendering — the
   real file already serves both Excel and the DB. Only render when absent. This makes
   each feed/day come from exactly one source.

4. **`source_kind` tagging.** Add `source_kind TEXT` (`file`|`email`, default `file`) to
   `meta_file_processed` (in `baseline.sql`). When `emit.py` writes a file, register its
   intended origin (`email`) so the loader stamps `meta_file_processed.source_kind='email'`
   on ingest; ordinary files stay `file`. Suggested mechanism: `emit.py` inserts a small
   origin hint (new `meta_file_origin(file_path, source_kind)` or a pending
   `meta_file_processed` row) keyed on the final path; `etl/etl_load.py` reads it and sets
   `source_kind` in `mark_processed()`. Do NOT encode origin in the filename (it must stay
   workbook-importable).

5. **Rewire `dispatch.py`.** For the 5 in-scope feeds: remove the direct
   `insert_skip_duplicates()` calls and call `emit.write(...)` instead (subject to the
   precedence check). Still record the email in `meta_hedgeye_msg` (status + which file it
   produced/skipped). Keep direct-insert untouched for the out-of-scope email-only feeds.

6. **Derive trigger.** Tab-backed feeds now derive via the loader's existing
   post-load `derive_all` (etl_load.py step 6) — remove the redundant `_trigger_derive`
   for those. Email-only feeds keep `_trigger_derive` after their direct inserts.

## How to verify

- Enable + run `python -m etl.hedgeye_fetch --backfill 2026-06-26` with the scheduler
  running. Each in-scope feed produces a file in its source dir (when no real file
  exists), the loader ingests it, and rows land in the right `hist_*` table.
- Diff a generated `RR 2026-06-26.xlsx` / `ETFChange …` / `PS …` / `call …csv` against a
  real sample — sheet names + headers identical; importing into the Excel tab is clean.
- **`hist_iichg` keeps add/remove:** an investing_ideas add and the MDB-style remove both
  land with the Action populated (re-check the TASK_93 remove case).
- **Precedence:** with a real file already present for a feed/date, the email renders
  nothing and does not double-load (row counts unchanged).
- **`source_kind`:** `meta_file_processed.source_kind` = `email` for email-rendered files,
  `file` for real ones.
- **Out-of-scope feeds unchanged:** `hist_rta`/`hist_call_top5`/`hist_hedgeye_stance`/
  `note_repo`/nowcast still populate via direct insert; idempotent on re-run.
- `pytest tests/test_hedgeye_emit.py` (new) green; full `pytest tests/` no regressions.

## Done criteria

5 tab-backed feeds ingest via the existing loader from email-rendered workbook files;
direct-insert removed for them; email-only feeds unchanged; precedence prevents
double-loads; `source_kind` stamped; files import into the Excel workbook; tests green.
Log to `DEV_HANDOFF.md`, end `ALL_DONE`. No commits — Ashok commits from Windows.

## Queued follow-ups (do NOT start — separate specs to come)

- **TASK_96** — `v_ingest_log` view: UNION `meta_file_processed` (+`source_kind`) and
  `meta_hedgeye_msg` into one "what was ingested" list (file + email).
- **TASK_97** — feed catalog: additive canonical `feed_code` linking `ref_load_files` ↔
  `ref_hedgeye_email_type` + `v_feed_catalog` view (one feed, both recognizers).
