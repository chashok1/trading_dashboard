# AGENT_WORK — Developer master pointer

> **ACTIVE: TASK_138 ONLY.** Do not start 139, 140 or 141 yet — they are gated,
> see "Sequencing" below. TASK_137 and earlier are closed; do not reopen them.

**Active task:** `agent-tasks/TASK_138_nightly_outcome_refresh.md`
**Created:** 2026-09-20 by Cowork
**Origin:** whole-project logic review, 2026-09-20 (see "Why" below)

---

## Why this batch exists

A review of the decision path found that the system's own July measurement
(`docs/audit/signal_validation_2026-07.md` §D) shows **following the system's
recommendation performed worse than contradicting it** — FOLLOWED −3.57%,
CONTRADICTED −2.95%, NO_SIGNAL −0.88% (fwd-20d, $-weighted the same way).

The pipeline is sound. The defects are all in the **decision layer**, and all
four were already documented and then left in a follow-up queue:

| # | Defect | Evidence |
|---|---|---|
| 138 | The outcome ETL is **not scheduled** — every edge number on screen, including the default sort, runs on data last refreshed 2026-07-12 | `etl/scheduler.py`, `register_startup_tasks.bat` — no caller |
| 139 | Every finding above is from **one regime** (a bounce, Feb–Jun). A5 never tested | `signal_validation_2026-07.md` standing caveat |
| 140 | `SOURCE_ORDER` is hand-typed and near-reverse of measured edge — PS (−2.07) and ETF (−3.40) outrank RR (+2.84) and SSS (+2.33) | A4 = **BROKEN**, `actionable_playbook.md` §5 |
| 141 | 30/30 SELL rules have negative edge; TASK_118 **annotated** this instead of enforcing it, and `SS`/high is an anti-signal (−5.03%, 37% win) | `loss_diagnosis_2026-07.md` §B, `v_final_call_scorecard` |
| 142 | Defect 138 is the **third** silent-staleness incident. Nothing watches whether a computed analytics table is still current — a stale number renders identically to a fresh one | scheduler.py comments 2026-08-15 & 2026-09-13; the six existing health checks all watch inputs |

---

## Sequencing — read this before starting anything

```
  TASK_138  Schedule the outcome ETL nightly          ← START HERE
     │       (infrastructure; nothing on the decision path moves)
     ├──────────────► TASK_142  Freshness contracts + 7th health check
     │                          (independent once 138 is in; purely
     ▼                           additive — makes staleness visible)
  TASK_139  Re-validate on Feb→Sep data               ← needs 138's nightly
     │       (measurement only; no code ships)          run to have fired once
     │
     ├── A4 still BROKEN? ──────► TASK_140  Re-rank SOURCE_ORDER
     │   else STOP, re-scope
     │
     └── SELL side still negative? ──► TASK_141  Enforce unproven-sell
         else STOP, re-scope
```

**TASK_142 is the prevention task** — 138 fixes one stale table, 142 stops the
next one going unnoticed. It only needs 138 done (so its first run isn't just
re-reporting what 138 fixed); it does not wait on 139. It can run in parallel
with 139/140/141 and touches nothing they touch.

**140 and 141 are independent of each other** and can run in either order (or
in parallel) once 139 clears them. Both are gated on 139 because both would
otherwise be fitted to a single bounce.

**Do not skip 139 to get to 140/141 faster.** Changing decision logic off
one-regime numbers is exactly the failure mode this batch exists to correct.

---

## Standing constraints for all four tasks

1. **Every behaviour change ships behind a `ref_settings` switch that defaults
   to OFF.** 140 → `source_order_mode='static'`. 141 →
   `unproven_sell_mode='annotate'`. The first verification step in both is a
   byte-identical re-derive in default mode. Turning a switch on is the user's
   decision, made after seeing the diff — not part of the task.
2. **Leave the switch OFF before writing `ALL_DONE`.** Report the diff; do not
   leave the new path live.
3. **Buy-side rules, thresholds and `ref_trig_*` are out of scope** in all four.
   The measured BUY set is the part that works (BM/BMN +2.1 to +3.2%, win
   63–70%) — do not touch it.
4. **Persist what the new logic did** (`winning_source_rank`/`_edge` in 140,
   `unproven_sell_suppressed` in 141). A change that can't be scored afterwards
   is another faith-based threshold, which is the problem, not the fix.
5. Stay on the **Baseline** param profile throughout. Do not activate
   Sigmoid/ml profiles (standing instruction, `actionable_playbook.md` §5).
6. No commits or pushes — the user commits from Windows.

---

## Out of scope for this batch (deliberately deferred)

Reviewed and parked until 139 reports. Do not start these:

- **Hysteresis / minimum-hold before an action can flip.** No churn control
  exists anywhere in the codebase (grepped: no hysteresis, cooldown, min_hold).
  Realized losses −$16.7k vs unrealized drag −$3.9k — 4× more money lost
  selling than holding. Likely the highest-value item after this batch.
- **Letting measured edge / `bull_prob` break ties in the winner sort.**
  `drv_bull_prob` and `drv_final_call_cal` run *after* `drv_actionable` in
  `derive_all()` — evaluation-only, structurally unable to influence a
  recommendation.
- **Conviction- and volatility-scaled sizing.** `AMT$` is a flat
  `ref_asset_allocation` MIN/MAX lookup; the Risk Dial's
  `suggested_size_multiplier` is computed and never used.
- **Scoring disagreement instead of collapsing it to HOLD.** "Mixed" rows move
  20–35% more than clean-signal HOLDs (A3).
- **Staleness decay on carried-forward periodic sources** (A5 in the business
  review) — `source_snapshot_date` exists, nothing acts on its age.
- **Swapping the RR playbook gate from the `bull` ladder (measured inverted)
  to `rr_bull_bear`** (measured correct, +2.59 vs +1.00) — A1.

---

## Reporting

Log every change in `DEV_HANDOFF.md` as usual; end with `ALL_DONE` only when
the active task's "How to verify" block passes in **default (switch-off) mode**.
For 140 and 141, include the switch-on diff as a report in `DEV_HANDOFF.md` —
symbol counts and before → after actions — so the user can decide whether to
enable it.

Testing is **on request only**. Do not hand off to the tester.
