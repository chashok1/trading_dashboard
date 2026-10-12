# TASK_150 — Phase 0: three quick fixes (Book-SOME alerts, area links, LOW CONF sells)

**Source of truth for the design:** `DESIGN_SPEC_2.md` (R3, area links), `DESIGN_SPEC_4.md` (L2), consolidated
build plan at the end of `DESIGN_SPEC_4.md`. Read only the sections named here. The user approved this build
on 2026-10-11. You choose the implementation; the spec fixes behaviour. Where spec and live code/data
disagree, trust live and say so in `DEV_HANDOFF.md`.

## Fix 1 — "Book-SOME" Hedgeye real-time alerts are dropped (R3)
**Problem (verified):** NET's 10/8 alert, subject `**Real-Time Alert: Book-SOME (Investing Summit!): NET -KM`,
is stored in `hist_rta` with `signal_kind = NULL`, `action = SELL`, `side = long`, because the subject regex in
`etl/hedgeye/parsers.py` (~line 387) only recognises `<Kind> Signal` and "Book-SOME" has no word "Signal".
`etl/derive_outlook_action.py` (RTA block ~line 1322; `_action_rta`, `_RTA_WEIGHT`) then returns no action for
a NULL kind. Because the newest alert per symbol wins (`ROW_NUMBER() ... ORDER BY alert_ts DESC`), the dropped
alert also **hides the older Buy alert** on the same stock.
**Wanted:** a "Book-SOME" alert (take some profit) behaves exactly like a **Sell-SOME** alert: for a held stock
the RTA source says REDUCE, with the same weight and priority as Sell-SOME.
- Fix the parser so new rows get `signal_kind = 'Sell-SOME'` (keep the raw subject).
- **Do not rewrite or delete raw `hist_*` rows** (convention #1). For the existing rows (2 known with NULL kind
  and a "Book" subject), map them at derive time: treat `signal_kind IS NULL` with a subject matching
  `book-some` (case-insensitive) as Sell-SOME. If a derive-time mapping is cleaner than a parser-only fix, do
  both.
- Check there are no other kind-less RTA rows that this would wrongly affect (list them in the handoff).
**Check:** after re-deriving 2026-10-08, NET's `source_actions` includes `RTA: REDUCE` (not hidden), and the
older 10/7 Buy alert no longer wins over it.

## Fix 2 — Area links
Link **CRAK → Oil** area and **BLOK, HOOD → Bitcoin** area so the area Tailwind/Headwind tiles and verdicts cover
them. Data only: `db/seeds_area_driver.sql` (see `docs/area_driver_rules_logic.md`; tables `drv_area_verdict`,
`drv_driver_exposure`). Keep the seed idempotent. Find the existing membership/exposure structure and add rows
the same way the other members are added. Re-derive the area verdicts for the anchor date.
**Check:** CRAK shows under the Oil tile; BLOK and HOOD under the Bitcoin tile on the dashboard.

## Fix 3 — LOW CONF for weak sell sources (L2, DECIDED: annotate, never suppress)
**Why:** history shows SSS (Signal Strength) sells, RR-list sells and ETF-list sells have **no edge** (n = 683–1,613).
**Wanted:** extend `drv_actionable.low_confidence` (set in `etl/derive_actionable.py`) so it is **TRUE when the
only sell evidence is a REMOVE/REDUCE from SSS, RR or ETF, or an unproven composite.** Edge case: if a kept
source (PS, II, CALL, RTA, SSSCHG, Technical) also says sell, there is **no** demotion.
- **No change to `consolidated_action`, `final_code`, sizing or `trig_action`.** Annotate only
  (`unproven_sell_mode` stays `annotate`).
- Make the source list a setting: `ref_settings.lowconf_sell_sources` (default `SSS,RR,ETF`), seeded in
  `db/seeds_*.sql` and read in the derive (follow how `trade_mode_weak_buy_sources` is read).
- Check how `low_confidence` is already shown on the Actionable screen (`web/actionable.js`) and make sure the
  newly flagged rows render the existing LOW CONF treatment. Do not add new pills or chips (the user dislikes
  duplicates). If the UI needs no change, say so.
**Check (10/8 data):** TWLO and ILMN (SSS REDUCE) show LOW CONF; a stock with a PS or II sell does not.

## Rules for this task
- Plan-first rule (#9) is satisfied by the user's approval of the design; do not re-ask.
- Schema/seeds only in `db/baseline.sql` / `db/seeds_*.sql`; add a dated line to `docs/migrations.md`.
- Bump the `?v=` cache-buster on any web JS you edit. Preserve LF line endings.
- `etl/` changes need the server restarted before re-deriving (it does not hot-reload etl).
- No emails, no network calls, no files outside the project folder.
- No tests this round; sanity checks only (`ast.parse`, `node --check`, a TestClient load, the "Check" lines above).
