# AGENT TASK 33 — verify Cockpit "Market context" band, commit

**You (VS Code agent), browser + Windows git.** Write results to
**`AGENT_RESULT_33.md`**. Builds on Tasks 31–32 (macro feed + throttle, already
applied & committed). This round is **front-end only** — static web files. No DB
change, no FRED key, no server restart needed (just hard-refresh the page).

Files changed (on disk — do NOT rewrite):
- `web/cockpit.html` — adds a "Market context" card above the actions table
  (container `#macroBand`, `#macroRefreshBtn`, `#macroAsOf`, `#macroLastFetch`) +
  scoped tile styles + `<script src="/static/macro_band.js">`.
- `web/macro_band.js` — NEW, self-contained band renderer.
- `docs/macro_feed_logic.md`, `CLAUDE.md` — docs.

## Step 1 — syntax
```
node --check web\macro_band.js   :: -> no output = OK
```
Paste result.

## Step 2 — browser check (app already running; if not: `uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir api`)
Open http://127.0.0.1:8000/cockpit and **hard-refresh** (Ctrl+F5; web/ is static).
Confirm and paste one line each:
1. A **"Market context"** card appears at the top, above the actions table, with
   grouped tiles — Indexes (S&P 500, Nasdaq, Dow), Rates & curve (10Y, 2Y, …),
   Inflation, Jobs, Risk (VIX, …), Dollar & commodities. Tiles show a value, a
   colored change (green up / red down), and a date.
2. The header shows `as of <date>` and an `updated <relative>` stamp.
3. Click **"Refresh data"**. Because Task 32 just fetched, it should be throttled:
   the stamp changes to **"Up to date (fetched Nm ago)"** and the button
   re-enables. (No error, no duplicate fetch.)
4. Browser console is **clean** (no JS errors, no failed requests).

> Optional — prove a real refresh path: in a terminal
> `UPDATE ref_settings SET setting_value='0' WHERE setting_name='macro_fetch_min_interval_min';`
> then click Refresh (tiles reload with fresh values), then set it back to `'360'`.
> Skip if not needed.

## Step 3 — commit
```
git add web/cockpit.html web/macro_band.js docs/macro_feed_logic.md CLAUDE.md AGENT_TASK.md
git status --porcelain   :: confirm only these (+ AGENT_RESULT_33.md)
git commit -m "Cockpit: Market context band (macro tiles + throttled Refresh) wired to /api/macro"
git log --oneline -2
```
(Delete `.git\index.lock`/`HEAD.lock` from Explorer first if present.)
Paste status + log.

## Verdict
(a) band renders with grouped tiles + as-of/updated stamps ✓
(b) Refresh button respects throttle ("Up to date") ✓
(c) console clean ✓
(d) committed ✓
If the band is blank or the console shows an error, STOP and paste: the console
error, and the output of `curl -s http://127.0.0.1:8000/api/macro | head -c 400`.

Write `DONE` at the bottom of `AGENT_RESULT_33.md`.
