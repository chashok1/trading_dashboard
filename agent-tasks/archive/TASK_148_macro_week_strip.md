# TASK_148 — Macro Week Strip + "Your book vs your signals" checklist on `/`

**Author:** Cowork, 2026-10-10. **Owner:** Developer agent.
**Acceptance reference:** `docs/mockups/macro_week_strip_mockup_v2.html`
(layout + rules only — **every number in it is illustrative**; Cowork had no DB access).
**Ignore** `docs/mockups/macro_week_strip_mockup.html` (v1) — it was built from a
Hedgeye PDF and is superseded.

You have more context than Cowork (live DB, running app, recent UI changes).
**The outcome below is fixed; the implementation approach is yours.** Where the
spec and the live code/data disagree, trust the live code and note it in
`DEV_HANDOFF.md`.

---

## Why

The user reads Hedgeye's weekly "Macro Week Summary Notes" PDF and wants the
same *first-glance* read on the dashboard — but computed **only from data
already in this database**, using as little screen space as possible.
Hedgeye's written commentary and weekly position calls are **out of scope**
(they exist only in the PDF; the email stores just a link — see TASK_94). The
user accepts that.

## What to build

### 1. The strip — one line, always visible
Folded into the existing Regime band on `/` (`#crossAssetPanel`, under
`#regimeLineBody` in `web/index.html`) — **no new band**. Target: +1 line
(~24px) at 1200px width.

| Chip | Source (as Cowork found it — verify) |
|---|---|
| Quad M · Q · G | `ref_quad_periods`, `period_type` monthly / quarterly / global — current period, argmax of `quad1_pct..quad4_pct`. Reuse the existing helper in `api/routers/cockpit.py` (~line 1505) / `dash.py` rather than re-deriving. User maintains these by hand in /ref. |
| DXY | `drv_quote` last for `$DXY` + position in `drv_rr` LRR→TRR (%), `drv_rr.outlook`, ▲/▼ = 5-day change |
| 10Y | `drv_quote` `TNX:CGI` (**stored ×10** — see TASK_133 note in `db/seeds_cockpit.sql`), red above the existing 5% gauge level |
| VIX | `drv_quote` `VIX`; bucket from the existing vix gauges in `ref_risk_gauge` / their thresholds |
| MOVE | `drv_quote` `MOVE:GIF`; existing `move_chop` (100) / `move_elevated` (120) bands |
| ⚑ Next event | Next flagged release within 7 days from `ref_econ_indicator` (has `expected`, `show_on_dashboard`) — decide vs `ref_calendar_event` which is the right source; show "CPI Wed · exp 0.3%". **No time-of-day exists in either table — show day only.** |
| Your book: N aligned · M against | Counts from §2; clicking opens §2 |

Each chip has a hover tooltip (what it means + its source). Reuse existing
endpoints (`/api/cockpit/risk-dial`, `/api/macro-areas`, `/api/marketbar`,
`/api/rr-bar`) wherever they already return these values — don't duplicate.

### 2. The checklist — hidden until clicked (0px when closed)
One row per **current holding** (`drv_portfolio`, held qty fid + cs > 0;
exclude cash per `is_cash()`), `$ held = qty × drv_quote.last_price`.

| Column | Source |
|---|---|
| Quad fit | `drv_macro_score.macronet` — tailwind if > 0, headwind if < 0 (**confirm sign convention**) |
| HE outlooks | `drv_outlooks.rr_outlook / call_outlook / etf_outlook / ii_outlook` — 4 glyphs ▲▼– + "3/3 bull". Blanks skipped. **Confirm value vocabulary.** |
| Where in range | `drv_rr.lrr/trr` + last price → %; flag ⚠ at ≥ 85% (same cut-off as existing `is_hot`) |
| Verdict | see rules |

**Verdict rules**
- **Aligned** = Quad tailwind AND HE majority bullish
- **Against** = Quad headwind AND HE majority bearish
- **Mixed** = they disagree, OR range ≥ 85% (⚠ top of range)
- No HE coverage (all four blank) → Quad fit alone decides
- Sort: against → mixed → aligned, then $ held desc. Show top 7, "show all" for the rest.

Right side: "Next 7 days" list from the same event source as the ⚑ chip,
with `expected` values.

## Constraints
1. **Display only** (cockpit design rule C4). Do not touch `derive_actionable.py`,
   `ref_trig_*`, `SOURCE_ORDER`, `ref_settings` decision switches, or
   `ref_risk_gauge.is_active`.
2. Prefer a **live query / API join** over a new computed table. If you do add a
   table, it ships with its `ref_freshness_contract` row and a scheduler hook in
   this task (TASK_142 rule).
3. Colours: the app's CVD-safe `--mr-bull` / `--mr-bear` pair, and every state also
   carries a glyph (▲ ▼ ◆ ⚠) — never colour alone.
4. Follow existing UI conventions on `/` (collapse toggles, `msr-*` / `cockpit-band`
   classes, 4px spacing).
5. Tests per policy #18: acceptance tests in `tests/acceptance/` only; nothing kept
   in `tests/` asserts point-in-time DB values or palette hexes.
6. No commits or pushes.

## Things Cowork could NOT verify (please confirm, note results in handoff)
- `macronet` sign meaning; `drv_outlooks` outlook vocabulary.
- `ref_econ_indicator` holds future dates and which flag means "show on dashboard";
  whether it or `ref_calendar_event` is the better event source.
- `ref_quad_periods` has a current `global` row (user says quad data is stored there).
- `$DXY`, `TNX:CGI`, `VIX`, `MOVE:GIF` are present and fresh in `drv_quote` daily.

## Files expected to change (your call)
`web/index.html`, `web/cockpit.js` (or a new `web/macro_week.js`), `web/styles.css`,
`api/routers/cockpit.py`, `docs/dashboard_cockpit_design.md` (short addendum),
`CLAUDE.md` (one Lookup row), `docs/migrations.md` if schema changes, `DEV_HANDOFF.md`.

## How to verify
1. `/` at 1200px: strip renders on **one line** inside the Regime band; page
   height grows by ≤ ~30px with the checklist closed.
2. Every chip value matches a direct SQL query against its source table for the
   anchor date (record the queries + values in the handoff).
3. Checklist lists every non-cash holding; spot-check 3 verdicts by hand against
   `drv_macro_score` / `drv_outlooks` / `drv_rr`.
4. A holding with no HE outlooks shows "––––" and is judged on Quad fit only.
5. Event chip shows day + expected value, no time; nothing shows when no flagged
   event is within 7 days (silence is the default, cockpit rule C1).
6. `git diff --stat` shows no change to the constraint-1 files.
7. `node --check` on changed JS; `python -c "import ast..."` on changed Python;
   `pytest tests/ -q` green.
