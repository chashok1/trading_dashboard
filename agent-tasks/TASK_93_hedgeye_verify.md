# TASK_93 — Verify the Hedgeye pipeline (tester)

**Type:** verification only (no code change unless a defect is found). **Owner:** Tester
agent (live DB + app). Run after `DEV_HANDOFF.md` ends `ALL_DONE`. Write evidence to
`AGENT_RESULT_93.md`, ending `DONE` or `FAILED: <items>`. Spec: `TASK_93_hedgeye_pipeline.md`,
`docs/hedgeye_feeds_design.md` (Decision log).

## Verify

1. **Schema present.** All NEW objects from `db/hedgeye_schema.sql` exist; `\d hist_rta`,
   `\d note_repo`, `\d hist_call_top5` match the design; `drv_rr_trend_change` is a view.

2. **Classification correct (dry-run).** `python -m etl.hedgeye_fetch --dry-run` over the
   last 3 days: every research email maps to the expected type; `hedgeye@hedgeye.com`
   marketing, `The Call … Access Here`, and `MOMO Tracker` are dropped; no UNKNOWN for a
   known type. Paste the type histogram.

3. **DATA tables populated for a known day** (e.g. 2026-06-26):
   - `hist_rr` has ~38 rows; `SELECT * FROM drv_rr_trend_change WHERE as_of_date='2026-06-26'`
     returns the expected flips (AAPL Bullish→Bearish, XLK Bullish→Neutral, etc.) and
     **matches** that day's printed TREND CHANGE block (QA cross-check).
   - `hist_rta` has the day's alerts; a correction email set `superseded=TRUE` on the
     prior same-ticker alert and created **no** phantom action row.
   - `hist_call` has LONGS/SHORTS/NEUTRAL; `hist_call_top5` has 5 ranked rows with `side`
     consistent with the POSITIONS lists.
   - `hist_hedgeye_stance` has the Macro Show Bullish/Bearish list (non-ticker names
     mapped or NULL+flagged).
   - `hist_etfchg`, `hist_iichg`, `hist_sss_change`, `hist_ps` (full rank table) populated.
   - `hist_macro` has `HE_CPI_NOWCAST` for the nowcast date with the right value.

4. **Notes + media.** `note_repo` has rows for Early Look / Macro Show / Market Situation /
   The Call summary with `tickers[]`, `quad`, and a `gmail_link`. Market Situation chart
   images were archived to `hedgeye_image_dir` and recorded in `hist_media`.

5. **Idempotency.** Re-run `--once` → no new/duplicate rows; `meta_hedgeye_msg` unchanged
   counts. Re-run a `--backfill` for one day → identical rows (ON CONFLICT DO NOTHING).

6. **Unknown handling.** Temporarily feed an unrecognized subject (or find one) → it lands
   in `note_repo` with `status` review + `meta_hedgeye_msg.status='review_unclassified'`,
   nothing lost.

7. **Tests.** `pytest tests/test_hedgeye_parsers.py tests/test_hedgeye_classify.py -q` → 29
   passed. `pytest tests/` → no regressions.

8. **Derive integration.** Confirm a Hedgeye DATA load for `D` triggered `derive_all(D)` and
   the actionable screen / `drv_actionable` reflects the new RTA/stance inputs (per design
   §7), without disturbing EOD-anchored fields.

Pre-req gate: `DEV_HANDOFF.md` must end `ALL_DONE` first.
