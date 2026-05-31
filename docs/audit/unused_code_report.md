# Unused / Unnecessary Code Files — Audit

**Date:** 2026-05-31 · **Method:** import/reference reachability from the real entrypoints
(`api/main.py` + routers, `etl/scheduler.py`, `etl/tickers_initial_load.py`, `etl/etl_load.py`,
`etl/refresh_ref.py`, `etl/cleanup.py`, `etl/rebuild_rules.py`, `etl/daily_health_check.py`,
`db/init_db.py`, `tests/`, the `.bat` launchers, and `<script src>` tags in `web/`). A file is
**LIVE** if something on that path imports it; otherwise it is cruft, a one-off, or dead.
**No files were deleted** — this is a recommendation list.

---

## Headline

The `api/ db/ etl/ web/ config/ tests/` core is clean. The problem is the **repository root**:
**~178 tracked loose files** that violate the "top-level layout is settled" convention, plus
two large tracked junk directories.

| Bucket | Tracked count | Recommendation |
|---|---|---|
| Root one-off `*.py` (`check_/debug_/fix_/verify_/reload_/...`) | 158 | archive or delete |
| Root loose `*.bat` (non-launcher) | several of 9 | keep 4 launchers, prune rest |
| Root `*.log` / `*.txt` dumps / `*.html` response dumps / `*.png` screenshot | ~11 | delete (logs already gitignored going forward) |
| `_trash_2026-05-12/` (tracked) | 107 files | delete from git |
| `docs_backup_2026-05-20/` (tracked) | 56 files | delete from git |
| `etl/` orphan modules | 1–2 | review |
| `web/` orphan page | 1 | review |

---

## 1. Root-level throwaway scripts (158 tracked `.py`) — top cleanup target

These are ad-hoc diagnostics written during development. They are **not imported by anything**
and duplicate functionality now living in `etl/`, `tests/`, and the API. Counts by prefix:

```
check_*   53      fix_*     19      verify_*   6      diagnose_* 2
test_*    23      debug_*   17      reload_*   4      migrate_*  2   (+ ~30 misc one-offs)
```

Notable subgroups:

- **`test_*.py` at root (23):** NOT real tests — the maintained suite is in `tests/`
  (`conftest.py`, `test_action_classifier.py`, `test_comprehensive.py`, etc., run by pytest).
  Root `test_api.py`, `test_portfolio_*.py`, `test_explore_*.py`, `test_port8001*.py`, … are
  manual probes. **They are not collected by pytest's configured paths and add noise.**
- **`check_*` / `debug_*` (70):** one-shot DB/data inspections (`check_cs_*`, `debug_892_*`,
  `debug_cs_*`, `check_etf_*`). Superseded by the File Monitor / Trace screens and
  `etl/check_null_columns_v2.py`.
- **`fix_*` (19):** historical HTML/encoding repair scripts (`fix_titles*`, `fix_arrows`,
  `fix_double_dash*`) — the fixes are long since applied to `web/`.
- **`migrate_*` / `apply_*` / `create_hist_pk.py` / `populate_sales_retroactively.py`:**
  already-applied one-time migrations. Keep only if you want the migration history; otherwise
  move to an `archive/` dir outside the build path. (CLAUDE.md's documented pattern keeps
  reusable migrators like `migrate_ref_load_files_pk.py` as a *template* — that one is worth
  keeping as reference.)

**Recommendation:** create `archive/2026-05-dev-scripts/` (gitignored) and move all 158, or
delete outright. None are on a runtime path.

---

## 2. Tracked junk directories — delete from git

| Path | Tracked files | What it is |
|---|---|---|
| `_trash_2026-05-12/` | 107 | explicitly-named trash: old `api/main.py.bak.trace`, pre-consolidation `migrations_consolidated_into_baseline/`, etc. |
| `docs_backup_2026-05-20/` | 56 | snapshot backup of `docs/` — superseded by current `docs/` + git history |

Both are redundant with git history. `.gitignore` already covers `_backups/` and `*.bak` but
**not** these two specific dirs — they are committed. Recommend `git rm -r` both.

---

## 3. Loose root artifacts (logs, dumps, screenshots)

`output.txt`, `initial_load.log`, `scheduler*.log` (5 files), `server.log`, `init_db.log`,
`check_response.html`, `portfolio_response.html`, `actionable_RECOVERED.txt`,
`actionable_screenshot.png`, `sync_test_marker.txt`. `.gitignore` ignores `*.log` going
forward but the already-committed ones remain tracked — `git rm` them. The `.html`/`.txt`/`.png`
dumps are debugging residue.

Data files at root (`Accounts_History.csv`, `Rollover_IRA_*.csv`, `Tickers 2026-04-30.xlsx`,
`drv_formulas_reference.xlsx`) are inputs/reference — keep, but consider a `data/` or
`reference/` folder so they don't clutter root.

---

## 4. `etl/` orphan & one-off modules

| File | Verdict | Evidence |
|---|---|---|
| `etl/position_rules.py` | **DEAD** — no importer in `api/ etl/ db/ tests/`; appears only as a string in a test docstring | safe to delete |
| `etl/notify.py` | **Test-only** — imported solely by `tests/test_comprehensive.py`, never by runtime code | keep if email-notify is a planned feature; otherwise dead |
| `etl/check_null_columns.py` | **superseded** by `check_null_columns_v2.py` | delete v1 |
| `etl/execute_build.py` + `generate_cat_ddl.py`, `generate_drv2_views.py`, `build_drv_cat_layers.py`, `seed_ref_ma_columns.py`, `enrich_ref_ma_columns.py`, `auto_enrich_registry.py`, `gen_data_flow_doc.py` | **LIVE but build-time only** — run manually to regenerate DDL/registry, not in the runtime cascade | keep; now grouped under "BUILD/CODEGEN one-offs" in CLAUDE.md |

`ma_codegen.py` is genuinely live (imported by both `derive.py` and the build scripts).
`derive_v2.py` is **not** superseded by anything — `derive.py` imports its overrides; keep both.

---

## 5. `web/` orphan

| File | Verdict | Evidence |
|---|---|---|
| `web/portfolio-detail.html` | **orphan** — not routed by `api/routers/pages.py`, loads no project JS (CDN Chart.js only) | confirm it isn't a planned screen, then delete |

All 17 `web/*.js` files are referenced by at least one served HTML; 16 HTML files are routed by
`pages.py`. No JS orphans.

---

## Suggested cleanup order (lowest risk first)

1. `git rm -r _trash_2026-05-12/ docs_backup_2026-05-20/` (pure backups, recoverable via history).
2. `git rm` the tracked `*.log`, `*.txt` dumps, `*.html` response dumps, `actionable_screenshot.png`.
3. Move the 158 root one-off `.py` to a gitignored `archive/` (or delete).
4. Delete `etl/position_rules.py` and `etl/check_null_columns.py`; decide on `etl/notify.py`.
5. Resolve `web/portfolio-detail.html`.

> All recommendations are non-destructive to the running app: nothing listed for removal is on
> an import path or served route. Verify with `pytest tests/` and a smoke run of `start.bat`
> after any deletion.
