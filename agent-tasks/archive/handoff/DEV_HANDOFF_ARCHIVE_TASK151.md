# Dev Handoff — AGENT_WORK_50 (TASK_150 + TASK_151)

## Step 0
- `AGENT_WORK_49.md` moved to `agent-tasks/archive/handoff/`.
- Old `DEV_HANDOFF.md` (TASK_149, ALL_DONE) moved to `agent-tasks/archive/handoff/DEV_HANDOFF_ARCHIVE_TASK149.md`.
- `agent-tasks/TASK_149_area_driver_rules.md` moved to `agent-tasks/archive/`.
- This round's pointer archived as `AGENT_WORK_50.md`. Nothing else touched (cockpit.py, DESIGN_* untouched).

## TASK_150
Files:
- `etl/hedgeye/parsers.py` — "Book-SOME" subject now gives `signal_kind='Sell-SOME'` (raw subject kept).
- `etl/derive_outlook_action.py` — RTA query maps NULL kind + subject matching `book-some` to Sell-SOME (no raw rows rewritten). Both fixes done.
- `db/seeds_area_driver.sql` — symbol rows CRAK -> oil, BLOK and HOOD -> bitcoin (`ref_gauge_transmission`, idempotent).
- `etl/derive_actionable.py` + new `db/seeds_lowconf_sell_sources.sql` — setting `lowconf_sell_sources` (default `SSS,RR,ETF`). `low_confidence` is also TRUE when the only sell evidence is a REMOVE/REDUCE from those sources (or an unproven composite). A sell from any other source, or a proven sell rule, means no flag. Annotation only: `consolidated_action`, `final_code`, sizing and `trig_action` untouched.
- `web/actionable.js` — only the three LOW CONF tooltip texts changed to mention weak sources. Existing LOW CONF rendering reused, no new pills. `web/actionable.html` cache-buster bumped to `?v=20261011b`.
- `docs/migrations.md` — dated entry.

Checks (re-derived 10/8 and 10/9 by calling the derive functions directly in a separate process, so the server restart is not needed for these results):
- NET 10/8: `source_actions` includes `RTA: REDUCE` (Sell-SOME, -0.5), and the older Buy no longer wins.
- Other kind-less RTA rows: not separately listed. The derive-time mapping only matches a subject containing "book-some", so no other row is affected.
- CRAK shows under Oil, BLOK and HOOD under Bitcoin (`drv_driver_exposure` 10/9).
- LOW CONF: ILMN 10/8 is flagged (SSS REDUCE only). A row with a PS/II/etc. sell is never flagged (0 such rows). **Spec vs live data:** TWLO on 10/8 is SSS INCREASE with CALL ADD, so it has no sell evidence and is not flagged. On 10/9 both ILMN and TWLO are INCREASE. The spec's "TWLO REDUCE" does not match live data.
- Flagged rows: 405 of 1,089 (10/8) and 379 of 1,087 (10/9). Many are not-held names with a list-drop REMOVE. The UI only shows the badge when the Final Call side is sell, so held-name noise is limited.

## TASK_151
Files:
- `db/baseline.sql` — `ref_accounts.size_mult` (NUMERIC, default 0, CHECK 0-5), `ref_asset_allocation.units_pct`, table `drv_account_size` (PK as_of_date, tos_symbol, account_short; raw and rounded min/max/unit, account value, multiplier, value_date, held $, over_max).
- `db/seeds_account_size.sql` — size_mult IRA 1 / F-A 2 / F-M 1 (only seeded while no account has a multiplier, so /ref edits survive), `units_pct = units/400000`, freshness-contract row `drv_account_size` (refreshed by `derive_all`).
- `etl/derive_account_size.py` (new) + `etl/derive.py` — runs in `derive_all` right after `drv_actionable`. Category = `drv_actionable.position_category`, the one Final Call sizing already resolved. Account value = latest file per account <= position ceiling, no rows if older than 5 trading days. Active accounts only (85911 excluded), rows sharing a short name (two HSA) are one account. Rounding to nearest $1,000, .5 up, >0 floored at $1,000. Over max = held > rounded max.
- `api/routers/dash.py` — each `/api/actionable` row gets `account_sizes` (name, mult, min, max, unit, held, over).
- `web/actionable.js` / `.html` — OVER MAX pill is per account (`IRA over max ($30.9k / $17k)`; several accounts show names only). Pill tooltip and Action popup list each account (min/max/unit/held) as bullets plus an all-accounts sum. Household check kept as fallback for rows without account data.
- Docs: `docs/migrations.md`, `docs/actionable_logic.md`.

Table check (10/9, matches spec exactly): Call IRA 4k/17k/2k, F-A 4k/14k/2k, F-M 4k/18k/2k; Equities IRA 8k/25k/4k, F-A 7k/21k/4k, F-M 9k/27k/4k. Account values IRA 419,861, F-A 178,196, F-M 445,626.
- 10/8 over-max, 7 stocks: AAPL (F-M), BUXX (IRA), CLOX (IRA), ILMN (IRA), MSFT (F-M), TXG (IRA and F-A), XLE (F-M). TXG IRA is $30.9k vs $17k, as in the spec.
- 10/9 over-max, 8 stocks: AAPL (F-M), BUXX (IRA), CLOX (IRA), IBIT (F-M, IRA), MSFT (F-M), TWLO (F-M), TXG (IRA), XLE (F-M).
- No amount above $0 rounds to $0 (0 rows). No Neutral/Other symbols exist in the 10/9 data, so that $0 case holds by the 0% setting but was not seen in a row.
- NOT run: changing F-A `size_mult` on /ref and re-deriving (no DB edits by me). The multiplier is read fresh each derive. Confirm `/ref` shows `size_mult` as editable (it is not the key column, so it should be).
- TestClient `GET /api/actionable?date=2026-10-09` returns 200 with `account_sizes` on TXG.

Household sizing note for the user (NOT changed): Final Call still uses the one household number. If it were switched to the sum of the account amounts, a Call stock's household min would go from $4k to $12k (4k+4k+4k) and max from $16k to $49k (17k+14k+18k). Equities min from $8k to $24k, max from $24k to $73k.

## How to test
Sanity only (no tests this round). STOP the server, relaunch `start.bat` (loads the new `etl/` code), THEN re-derive (the scheduler or `derive_all`). Then open Actionable and check the OVER MAX pill on TXG.

## Risks & notes
- `etl/`, `db/` and `web/` changed. Files are mixed line endings in the repo (dash.py, actionable.js, derive_outlook_action.py are CRLF; most others LF). I kept each file's existing style; `db/baseline.sql` was already mixed.
- `init_db` was run once to apply the schema and seeds. 10/8 and 10/9 were re-derived outside the running server.
- Held-by-account dollars use each account's own latest file, so they can differ slightly from the household `current_position_dollar`.
- The tooltip uses a plain-text bulleted list in a `title` attribute (no rich HTML tooltip).
- `lowconf` now flags about 35% of rows; consider whether non-held REMOVE rows need it later.

## Status
ALL_DONE
