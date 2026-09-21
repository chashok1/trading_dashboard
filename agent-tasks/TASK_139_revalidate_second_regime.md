# TASK_139 — Re-run the signal validation on Feb→Sep data (second regime)

## Context

Every money-relevant finding this system currently operates on comes from one
report — `docs/audit/signal_validation_2026-07.md` (TASK_123) — computed over
**2026-02-02 → 2026-06-11**, which the report itself flags as a single market
regime (a bounce). Assumption **A5** ("edges generalize") was never tested.

Those one-regime findings are currently load-bearing:

- `docs/actionable_playbook.md` §3.3 restricts the user to a narrow trade subset
- the standing instruction "never use the bull ladder"
- "treat PS/ETF/II-driven buys as noise"
- TASK_140's whole premise (re-ranking `SOURCE_ORDER`)
- TASK_141's whole premise (unproven SELL rules)

There are now ~3 more months of data (through the current anchor). Before
changing decision logic off July's numbers, re-measure them. **If a finding
flips, TASK_140/141 must be re-scoped before they ship.**

**Prerequisite: TASK_138 must be complete and its nightly run must have fired
at least once** — otherwise this task measures the same stale table.

## Goal

A second-regime replication of TASK_123, reported side by side with July's
numbers, so each finding is marked *held* / *flipped* / *still thin*.

1. **Refresh the dataset first:**
   ```
   python -m etl.backfill_full
   python -m etl.compute_firing_outcomes --truncate
   ```
   (`--truncate` is correct here — this is the deliberate full rebuild.)
   Record the resulting row count and `as_of_date` range in the report.

2. **Re-query, unchanged, the four standing views** — no view edits, no
   threshold edits, no rule edits anywhere in this task:
   - `v_bull_gate_scorecard`   (A1 — bull ladder, and `rr_bull_bear` B/!B)
   - `v_final_call_scorecard`  (A2/A3 — BM/BMN/SA/SS by `fc_confidence`)
   - `v_source_edge_scorecard` (A4 — per-source buy-family / sell-family edge)
   - `v_rule_scorecard`        (the BUY-vs-SELL direction split, `fires >= 20`)
   plus the `drv_inferred_action` FOLLOWED / CONTRADICTED / NO_SIGNAL aggregate
   (§D — the headline).

3. **Split the window in two** and report each half separately as well as
   pooled: **2026-02-02 → 2026-06-11** (July's window, as a regression check
   that the numbers reproduce) and **2026-06-12 → latest scored date** (the new,
   independent period). Pooled-only would hide a flip.

4. **Write `docs/audit/signal_validation_2026-09.md`** — same section order as
   the 2026-07 report so they diff cleanly. Every table gets an `n` and, where
   the 2026-07 report gave one, a 95% CI. For each of A1–A6 state one of:
   - **HELD** — same sign, same rough magnitude, n grew
   - **FLIPPED** — sign reversed in the new half
   - **STILL THIN** — n too small in the new half to say

5. **Answer these five explicitly**, since they gate other work:
   - **A4/TASK_140:** is the empirical source ranking still near-reverse of the
     static `SOURCE_ORDER`? Give the new n-weighted buy-family edge per source.
   - **A1:** is the `bull` ladder still inverted? Does `rr_bull_bear` (B vs !B)
     still separate correctly?
   - **§B/TASK_141:** are SELL rules still uniformly negative-edge, or did the
     new period (if it contained any downtrend) rehabilitate them? Report the
     BUY/SELL split table for the new half on its own.
   - **A3:** is `SS`/`high` still directionally wrong vs `SS`/`mixed`?
   - **§D headline:** does FOLLOWED still underperform CONTRADICTED and
     NO_SIGNAL on the new half?

6. **Characterize the new period** in one short section — SPX drawdown/rally %,
   VIX range, `drv_market_stat` regime markers — so the reader can judge whether
   it is genuinely a second regime or more of the same bounce. If it is *not* a
   different regime, say so plainly; that is a valid and important result, and
   it means A5 is still unproven.

## Files expected to change

- `docs/audit/signal_validation_2026-09.md` (**new** — the deliverable)
- `docs/actionable_playbook.md` §5 verdict table + §3.3 subset, updated to the
  new numbers **only where a verdict changed**
- `docs/migrations.md` (one row noting the re-validation, no schema change)
- `DEV_HANDOFF.md`

**Explicitly out of scope:** no changes to `db/baseline.sql` views, `etl/`
derive logic, `ref_trig_*`, `ref_settings`, param sets, or any UI. This is a
measurement task. Findings feed TASK_140/141; they do not ship code here.

## How to verify

1. `docs/audit/signal_validation_2026-09.md` exists and covers A1–A6 with
   HELD/FLIPPED/STILL THIN on each.
2. `SELECT MIN(as_of_date), MAX(as_of_date), COUNT(*) FROM drv_rule_outcome;`
   matches the row count and range stated at the top of the report.
3. The report's 2026-02→06 half reproduces the 2026-07 report's figures within
   rounding. **If it does not, stop** — something changed in the derive or
   outcome path between July and now, and that discrepancy is the finding.
4. Every table carries an `n`; no verdict rests on n < 30.
5. The five questions in step 5 each have a one-line explicit answer.
