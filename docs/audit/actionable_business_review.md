# Actionable Screen — Business Review

Date: 2026-06-13. Author: Claude (code-only analysis; live-DB checks listed at the
end for you to run). **No code was changed.** This is a findings report only.

Scope: the path that turns 6 sources (RR, CALL, ETF, II, SSS, PS) + the rules
engine into one recommended action per symbol, with sizing and stops.
Files of record: `etl/derive_outlook_action.py`, `etl/derive_actionable.py`,
`api/routers/dash.py`, `web/actionable.js`, `db/baseline.sql` (scorecard views).

---

## TL;DR

1. **Two of your "not working" symptoms are real and explainable.** The PS-removal
   case is partly *by design* (a PS drop on a name you don't hold is intentionally
   silent) **and** partly a genuine bug: PS is keyed on the raw analyst `ticker`
   while everything else keys on `tos_symbol`, so held-detection can misfire and
   suppress a legitimate REMOVE. The SSS case is mostly *by design*: SSS
   INCREASE/REDUCE are deliberately excluded from ever becoming the headline action
   — only SSS ADD/REMOVE move the recommendation.
2. **The biggest improvement isn't a bug fix — it's a design gap.** The final
   recommendation is chosen by "most aggressive source wins," and your already-built
   edge / forward-return / conviction data never touches that decision. It's
   display-only decoration.
3. **To make money:** wire the measurement layer you already built (rule edge,
   forward returns, ML threshold tuner) back into the recommendation and the sizing.
   Four changes, no new data collection required.

---

# Part 1 — Is the existing functionality working as expected?

## 1A. "A symbol removed from PS doesn't show a REMOVE"

**Verdict: partly by design, partly a real bug.** Three distinct causes, ranked by
likelihood.

### Cause 1 (by design) — a PS drop on a name you DON'T hold is silent
`etl/derive_outlook_action.py:546-547`:

```python
if curr is None and prev is not None:
    return "REMOVE" if held else None, "dropped from list"
```

If PS drops a symbol you don't own, the classifier returns `None` → no action. This
is intentional ("don't tell me to sell what I don't have"). If your expectation is
"PS dropped XYZ, show me that regardless of holding," that's a deliberate behavior
change, not a fix.

### Cause 2 (REAL BUG) — `ticker` vs `tos_symbol` key mismatch breaks held-detection
PS rows are keyed on the raw analyst **`ticker`** (`derive_outlook_action.py:728`):

```python
key_col = "ticker" if table in ("hist_ps",) else "symbol"
```

but holdings are keyed on **`tos_symbol`** (`_load_holdings`, ~lines 82-102), and the
held test is `held = sym in holdings` where `sym` is the PS `ticker`. For any symbol
whose analyst ticker differs from its `tos_symbol` (share classes, normalization —
the entire reason `tos_symbol` exists, see `docs/tos_symbol_normalization.md`),
**held registers False even though you own it**, so the REMOVE is suppressed at the
source. The same `ticker`-as-`tos_symbol` value is then written into the
`tos_symbol` column of `drv_outlook_action`, so the downstream JOIN in
`derive_actionable` (on `tos_symbol`) can also miss. This is the most likely "I own
it, PS dropped it, and I see nothing" case. **Violates convention #15** (tos_symbol
in all drv_*).

### Cause 3 (working as designed, but hidden) — REMOVE produced then filtered out
Even when a REMOVE is correctly emitted for a not-held symbol, it is suppressed and
hidden by default:

- `derive_actionable.py:479-484` sets `suppressed_reason = "NOT HELD — nothing to remove"`.
- `api/routers/dash.py:344-351` filters suppressed rows out of the API response unless
  "Show acted/snoozed / suppressed" is on.
- `web/actionable.js:354-355` additionally hides rows with no action or `_amt = 0`
  (a not-held REMOVE has `_amt = 0`).

So a not-held REMOVE exists in the DB but never reaches the screen at default
settings.

**Note:** the daily-universe gate (`drv_symbols`) is *not* the cause here — PS reads
`hist_ps` directly and never joins the TOSD universe. Held-status is the lever.

### A related conflict-resolution risk (worth verifying)
Because REMOVE has the highest `ACTION_RANK` (4) and wins the sort *before*
suppression runs, a name you don't hold where one source says ADD and another says
REMOVE can resolve to REMOVE → then get suppressed to a do-nothing → and the ADD
**silently disappears**. See Part 2, item A6.

## 1B. "Loading a new SSS file isn't reflected in my rules"

**Verdict: the load and re-derive DO run; the lack of visible change is mostly by
design.** Ranked causes:

### Cause 1 (by design, most likely) — SSS INCREASE/REDUCE can never be the headline
`derive_actionable.py:423-428`:

```python
outlook_candidates = [
    a for a in src_actions
    if a["action"] in ACTION_RANK
    and not (a["source_code"] == "SSS"
             and a["action"] in ("INCREASE", "REDUCE"))
]
```

A fresh SSS file that nudges `pct_delta` up or down produces INCREASE/REDUCE, which
is excluded from the winner contest and only appears under "Other Sources." Only SSS
**ADD** (new on list) or **REMOVE** (dropped, or pct_delta < 0) can change the
headline action. This matches "loaded SSS, nothing changed" exactly.

### Cause 2 — a new SSS file does not advance the anchor date `D`
`D = MAX(export_date) FROM hist_td` and `ANCHOR_LOCKED_SOURCES` is only
`(hist_tl, hist_td, hist_tw, hist_y)` (`etl/derive.py`). Loading SSS re-derives the
*current* `D`; it never moves `D` forward. If the SSS file is dated **after** the
current TOSD anchor (e.g. next week's SSS but no fresh TOSD), the new snapshot is
`> D`, and both the outlook-action lookback (`<= D`) and the consolidation
carry-forward (`as_of_date <= D`) **exclude it until a TOSD load advances `D`.**

### Cause 3 — atomic rules reading `SSS_signal_sign` see NULL unless snapshot == D
`drv_sss` is only built for `snapshot_date = D` (`etl/derive_v2.py`
`_derive_sss_v2_impl`), and `drv_ma` LEFT-JOINs it on `(snapshot_date, tos_symbol)`.
Since SSS is weekly (Mon) and `D` is the daily TOSD date, the carried-forward SSS
snapshot usually ≠ `D`, so `SSS_signal` / `SSS_signal_sign` / `SSS_rank_hl` come back
**NULL**. Any atomic/composite rule keyed on those columns is silently disabled even
though `hist_sss` loaded fine. (The outlook-action path reads `hist_sss` directly and
is unaffected — but the *rules engine* path is.)

### Cause 4 — re-loading the same snapshot inserts 0 rows
`hist_sss` PK is `(snapshot_date, symbol)` with `ON CONFLICT DO NOTHING`. Re-loading a
file that reuses an existing `snapshot_date` inserts nothing; the forward re-derive
block is gated on `rows_inserted > 0`. Confirm via `meta_etl_run.rows_inserted`.

## 1C. Pipeline behaving as expected? — summary

The mechanical pipeline (watch → load → `ON CONFLICT DO NOTHING` → derive on anchor
`D` → consolidate → API → JS) is sound and idempotent. The "not working" feeling
comes from **business-logic gates that are invisible to the user**: not-held
silencing, SSS demotion, the anchor-date rule for periodic feeds, and the
`tos_symbol` keying bug for PS. None of these throw errors; they just quietly produce
"no change."

---

# Part 2 — What can be improved in the existing logic

Ranked by impact.

**A1 (HIGH) — the winner ignores edge.** `derive_actionable.py:442` sorts candidates
by `(-ACTION_RANK, priority)` — most aggressive source wins, tie-broken by a static
priority. One source flipping to REMOVE overrides five saying ADD/HOLD. No agreement
count, no historical edge, no conviction enters the stored recommendation. All the
edge data (`edge_20d`, agreement counts) exists but is **display-only** in
`web/actionable.js`. This is the single biggest driver of churn and whipsaw.

**A2 (HIGH) — not-held INCREASE is sized larger than ADD, and can size to $0.**
`derive_actionable.py:493-499` sizes a not-held INCREASE to `MIN + Units` (bigger than
an explicit ADD, which targets exactly MIN) — backwards, since INCREASE-while-unowned
is weaker evidence. If the category is unmapped, `target_min`/`units` can be `None`
and you get a $0 "BUY SOME."

**A3 (MED-HIGH) — stop formula is volatility-blind and can sit above price.**
`_compute_stop` uses `max(trade_line, price*(1-0.08))`. Fixed 8% is too tight for
high-vol names and too loose for low-vol ones, and if `a_trade_value` is near
`last_price` the "stop" can land at or above the current price (instant stop-out).
You already compute `std_dev`/`median_sd` per symbol — an SD-scaled stop with a
`stop < price*(1-buffer)` guard is available and unused.

**A4 (MED) — SSS demotion discards the only conviction gradient SSS has.** Excluding
INCREASE/REDUCE throws away "analyst conviction rising on a name I own," which is
tradeable. Should be a down-weight, not a hard exclude.

**A5 (MED) — carried-forward periodic feeds have no staleness decay.** A 5-week-old
PS rank wins the consolidated slot at the same weight as a fresh one. Age in days is
trivially derivable from `source_snapshot_date` vs `as_of_date` but nothing acts on
it.

**A6 (MED) — REMOVE-then-suppress can erase a competing ADD.** On a not-held name,
REMOVE outranks ADD, wins, then suppresses itself to a do-nothing — the ADD vanishes.
A SELL signal on an unowned name is really an "avoid/don't-buy," and should be
modeled as competing against ADDs rather than silently winning-then-dying. Verify
this interaction.

**A7 (MED) — disagreement is never surfaced.** The UI counts *agreeing* sources but
never *dissenting* ones. When 3 say BUY and 2 say SELL, the screen shows one
confident action. Disagreement is exactly where the edge (or the trap) lives.

**A8 (MED) — no persisted conviction/confidence score.** Everything conviction-related
is recomputed in JS, so it can't be sorted server-side or used by automation. One
`conviction_score` column would centralize A1/A7/A8.

**A9 (LOW) — CALL demotion is brittle.** `other_sources_present` is computed over raw
`src_actions` (line 421) before SSS informational rows are filtered, so a symbol whose
only other "action" is a demoted SSS INCREASE still demotes CALL — leaving the symbol
with *no winner* when CALL had a good ADD.

**A10 (LOW, hygiene) — f-string SQL in `derive_outlook_action.py`.** Dates/table names
are interpolated rather than bound. Near-zero exploitability in a single-user local
app, but inconsistent with the rest of the codebase. Only worth touching if editing
those functions anyway.

---

# Part 3 — What can we do to make money

Theme: **you already built the measurement layer; the decision layer ignores it.**
The highest-ROI work is wiring measurement back into the recommendation, not building
anything new. Ranked by leverage.

**B1 (HIGHEST) — edge-weight the winner instead of pure aggressiveness.** Add
historical direction-adjusted edge as a sort/override key at
`derive_actionable.py:442`, and don't let an unproven/negative-edge rule group flip a
multi-source BUY into a SELL. Data already exists: `v_rule_scorecard.edge_20d` /
`confidence` (`db/baseline.sql`), forward returns in `compute_firing_outcomes.py`,
scorecard already fetched in the UI. Persist `winning_edge` on the row. *Effort:
~1 day incl. re-derive + backtest.*

**B2 (HIGH) — suppress / down-rank unproven rule-group candidates.** Rule groups with
`confidence='unproven'` or `edge_20d <= 0` are noise but still inject synthetic
actions. The UI already renders them muted — enforce that on the server in the
`group_candidates` block so they can't win. *Effort: ~half a day.*

**B3 (HIGH) — size by conviction, not flat category MIN/MAX.** Scale
`suggested_target_dollar` within `[MIN, MAX]` by conviction = f(agreeing-source
count, mean positive edge): 1 weak source → MIN; 4 sources + proven edge → MAX.
Replaces the binary "MIN for ADD, +1 unit for INCREASE." Needs the persisted
conviction score (A8). *Effort: ~1–2 days; backtest before activating.*

**B4 (MED, cheap) — make "edge-positive" the default view + a sortable column.** The
`_hasPositiveEdge` filter already exists but is opt-in and never a sort dimension.
Compute a per-row expected forward return server-side (mean of contributing rules'
`raw_avg_fwd20`) so you can sort by expectancy and spend attention there first.
*Effort: ~half a day.*

**B5 (MED) — actually use the ML tuner, and score the final recommendation.** You
built `etl/ml_tune_thresholds.py` with a chronological train/hold-out split that
writes an inactive param set for review — and it appears unused. (a) Run it, review
hold-out edges, activate the best set, `rebuild_rules`. (b) Build a
`compute_firing_outcomes`-style join keyed on `drv_actionable.consolidated_action`
to measure whether **the final recommendation the user acts on** has positive
expectancy — today only individual rules are scored, never the consolidated action.
This closes the loop on A1/B1. *Effort: ~1–2 days.*

**B6 (MED, data-gated) — feed your personal track record back in.**
`v_user_action_performance` already joins your DONE actions to 5d/20d forward returns.
If certain sources/sectors reliably under/out-perform for *you*, weight future
recs accordingly. Caveat: empty until you log actions, and `user_action_log` may be
column-drifted — verify it's populating first. *Effort: low to surface, med to feed
back.*

**B7 (MED) — volatility-scaled stops (also fixes A3).** Add `stop_mode='sd_scaled'`:
`stop = price - k*AC` with a `stop < price*(1-buffer)` guard, using the `std_dev`/
`median_sd` already computed. `ref_settings.stop_mode` already supports pluggable
modes. *Effort: ~1 day; pick `k` from backtest.*

**Recommended order:** B1 → B2 → B3 → B5. Those four convert an existing measurement
layer into real decision edge with no new data collection.

---

# Appendix — Live-DB checks to confirm (run these next)

Replace `:D` with the anchor date (`SELECT MAX(export_date) FROM hist_td;`) and
`XYZ`/`ticker` with the symbol you expected to see.

### PS REMOVE — confirm by-design vs bug

```sql
-- Was a PS action even emitted, and with what held flag?
SELECT as_of_date, tos_symbol, source_code, base_weight, prev_weight,
       held_today, action, action_reason
FROM drv_outlook_action
WHERE source_code='PS' AND tos_symbol='XYZ'
ORDER BY as_of_date DESC;
-- no row / action NULL  -> Cause 1 (not held -> silent, by design)
-- held_today=FALSE but you own it -> Cause 2 (ticker/tos mismatch BUG)

-- Confirm the ticker vs tos_symbol mismatch directly:
SELECT ticker, tos_symbol, snapshot_date, rank
FROM hist_ps WHERE ticker='XYZ' OR tos_symbol='XYZ'
ORDER BY snapshot_date DESC LIMIT 5;
SELECT tos_symbol, SUM(qty) FROM hist_f
WHERE snapshot_date=(SELECT MAX(snapshot_date) FROM hist_f WHERE snapshot_date<=:D)
GROUP BY tos_symbol HAVING SUM(qty)>0;
-- if hist_ps.ticker <> tos_symbol AND the holding is under tos_symbol -> Cause 2

-- Did a REMOVE reach drv_actionable but get suppressed/hidden?
SELECT tos_symbol, consolidated_action, winning_source, held_today,
       current_position_dollar, suppressed_reason
FROM drv_actionable WHERE as_of_date=:D AND tos_symbol='XYZ';
-- consolidated_action='REMOVE' + suppressed_reason set -> Cause 3 (toggle "Show suppressed")
```

### SSS load — confirm which cause

```sql
-- Cause 2: is the anchor behind the SSS file's date?
SELECT MAX(export_date) AS anchor_D FROM hist_td;
SELECT MAX(snapshot_date) AS latest_sss FROM hist_sss;   -- latest_sss > anchor_D -> Cause 2

-- Cause 4: did the new file actually insert rows?
SELECT * FROM meta_etl_run WHERE target_tab='hist_sss'
ORDER BY started_at DESC LIMIT 5;                         -- rows_inserted=0 -> ON CONFLICT skip
SELECT snapshot_date, COUNT(*) FROM hist_sss GROUP BY 1 ORDER BY 1 DESC LIMIT 6;

-- Cause 1: are SSS actions dominated by INCREASE/REDUCE (which never win the headline)?
SELECT as_of_date, action, COUNT(*) FROM drv_outlook_action
WHERE source_code='SSS' GROUP BY 1,2 ORDER BY 1 DESC;

-- Cause 3: are SSS columns NULL in drv_ma because snapshot != D?
SELECT COUNT(*) FROM drv_sss WHERE snapshot_date=:D;     -- 0 -> drv_sss empty for D
SELECT COUNT(*) FILTER (WHERE "SSS_signal_sign" IS NOT NULL) AS nonnull, COUNT(*)
FROM drv_ma WHERE as_of_date=:D;
```

### Force a clean reload to rule out skip/staleness

```cmd
python -m etl.etl_load "PATH\TO\SSS YYYY-MM-DD.xlsx" --force
:: then confirm the scheduler/derive log shows the anchor it derived for
```
