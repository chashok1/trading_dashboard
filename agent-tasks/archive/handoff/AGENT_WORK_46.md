# AGENT_WORK — Developer master pointer

> **TASK_138 is COMPLETE** (`AGENT_WORK_45.md`, `DEV_HANDOFF.md` → `ALL_DONE`,
> verified by Cowork 2026-09-21). Do not reopen it.
> **This batch releases the remaining four: 139, 140, 141, 142.**
> They are NOT all startable now — read "Sequencing" before touching anything.

**Created:** 2026-09-21 by Cowork
**Origin:** whole-project logic review 2026-09-20; continuation of the batch
that began with TASK_138.

---

## Start here

**Two tasks are startable immediately, in either order or in parallel:**

- `agent-tasks/TASK_139_revalidate_second_regime.md` — measurement only, no
  code ships. Its prerequisite (TASK_138) is now met.
- `agent-tasks/TASK_142_analytics_freshness_contract.md` — purely additive,
  touches nothing 139/140/141 touch.

**Two tasks are gated behind TASK_139's findings:**

- `agent-tasks/TASK_140_source_order_from_edge.md`
- `agent-tasks/TASK_141_enforce_unproven_sell.md`

Suggested order if working serially: **139 → (gate) → 140 → 141 → 142**, or run
142 first if you want a quick additive win while 139's full rebuild runs.

---

## Sequencing

```
  TASK_138  ✅ COMPLETE — outcome ETL now refreshes nightly
     │       drv_rule_outcome current through 2026-08-20
     │
     ├──────────────► TASK_142  Freshness contracts + 7th health check
     │                          READY NOW. Independent of 139/140/141.
     ▼
  TASK_139  Re-validate on Feb→Sep data          READY NOW
     │       (measurement only; writes a report, ships no code)
     │
     ├── A4 verdict?
     │     HELD ──────────────► TASK_140  Re-rank SOURCE_ORDER
     │     FLIPPED / STILL THIN ──► STOP (see "The gate" below)
     │
     └── SELL-side verdict?
           still negative ─────► TASK_141  Enforce unproven-sell
           FLIPPED / STILL THIN ──► STOP (see "The gate" below)
```

---

## The gate — how to decide, mechanically

TASK_139 step 5 requires an explicit one-line verdict on five questions. Two of
them are the gate. Apply this literally; do not interpret:

| 139's verdict on... | Then |
|---|---|
| **A4** (source ranking still near-reverse of `SOURCE_ORDER`) = **HELD** | Start TASK_140 |
| A4 = **FLIPPED** or **STILL THIN** | **Do not start 140.** Write `STOPPED_AT_139_GATE: A4 <verdict>` in `DEV_HANDOFF.md`, state what the new numbers say, and stop. |
| **SELL side** (rules still uniformly negative-edge on the new half) = **HELD** | Start TASK_141 |
| SELL side = **FLIPPED** or **STILL THIN** | **Do not start 141.** Write `STOPPED_AT_139_GATE: SELL <verdict>`, state the new numbers, and stop. |

A gate stop is a **successful outcome**, not a failure — it means the data
changed its mind and the spec needs re-scoping by Cowork before code ships.
Report it plainly; do not work around it, and do not "partially" implement a
gated task.

**140 and 141 gate independently.** One can proceed while the other stops.

**If either gate stops, still finish TASK_142** — it is ungated.

---

## Why this batch exists

The system's own July measurement (`docs/audit/signal_validation_2026-07.md` §D)
found that **following its recommendations performed worse than contradicting
them** — FOLLOWED −3.57%, CONTRADICTED −2.95%, NO_SIGNAL −0.88% (fwd-20d).

The pipeline is sound; the defects are in the decision layer, and each was
already documented and then parked in a follow-up queue:

| # | Defect | Evidence |
|---|---|---|
| 138 ✅ | Outcome ETL never scheduled — every edge number, including the default sort, ran on 2026-07-12 data | fixed; nightly since 2026-09-20 |
| 139 | Every finding above comes from **one regime** (a bounce, Feb–Jun). A5 never tested | `signal_validation_2026-07.md` standing caveat |
| 140 | `SOURCE_ORDER` hand-typed and near-reverse of measured edge — PS (−2.07) and ETF (−3.40) outrank RR (+2.84) and SSS (+2.33) | A4 = **BROKEN**, `actionable_playbook.md` §5 |
| 141 | 30/30 SELL rules negative-edge; TASK_118 **annotated** instead of enforcing; `SS`/high is an anti-signal (−5.03%, 37% win) | `loss_diagnosis_2026-07.md` §B, `v_final_call_scorecard` |
| 142 | 138 was the **third** silent-staleness incident. Nothing watches whether a computed analytics table is current — a stale number renders identically to a fresh one | scheduler.py comments 2026-08-15 & 2026-09-13 |

---

## Standing constraints for every task in this batch

1. **Every behaviour change ships behind a `ref_settings` switch defaulting to
   OFF.** 140 → `source_order_mode='static'`. 141 →
   `unproven_sell_mode='annotate'`. The first verification step in each is a
   byte-identical re-derive in default mode. (139 and 142 change no behaviour
   and need no switch — 138 correctly had none either.)
2. **Leave every switch OFF before writing `ALL_DONE`.** Report the switch-on
   diff — symbol counts, before → after actions — in `DEV_HANDOFF.md` so the
   user can decide. Do not leave the new path live.
3. **Buy-side rules, thresholds and `ref_trig_*` are out of scope** in all four.
   The measured BUY set is the part that works (BM/BMN +2.1 to +3.2%, win
   63–70%) — do not touch it.
4. **Persist what the new logic did** (`winning_source_rank`/`_edge` in 140,
   `unproven_sell_suppressed` in 141). A change that can't be scored afterwards
   is another faith-based threshold — the problem, not the fix.
5. Stay on the **Baseline** param profile. Do not activate Sigmoid/ml profiles
   (standing instruction, `actionable_playbook.md` §5).
6. **No commits or pushes** — the user commits from Windows.
7. Log each task separately in `DEV_HANDOFF.md` under its own heading, and write
   `ALL_DONE` only when the whole released set is finished or gate-stopped.
   If you stop mid-batch, write `PARTIAL: <tasks done>` instead — do **not**
   write `ALL_DONE`.

---

## Still out of scope (parked — do not start)

Reviewed 2026-09-20, deferred until this batch reports:

- **Hysteresis / minimum-hold before an action can flip.** No churn control
  exists anywhere (grepped: no hysteresis, cooldown, min_hold). Realized losses
  −$16.7k vs unrealized drag −$3.9k — 4× more lost selling than holding.
  Likely the highest-value item after this batch.
- **Letting measured edge / `bull_prob` break ties in the winner sort.**
  `drv_bull_prob` and `drv_final_call_cal` run *after* `drv_actionable` in
  `derive_all()` — evaluation-only, structurally unable to influence a call.
- **Conviction- and volatility-scaled sizing.** `AMT$` is a flat
  `ref_asset_allocation` MIN/MAX lookup; the Risk Dial's
  `suggested_size_multiplier` is computed and never used.
- **Scoring disagreement instead of collapsing it to HOLD** — "mixed" rows move
  20–35% more than clean-signal HOLDs (A3).
- **Staleness decay on carried-forward periodic sources** —
  `source_snapshot_date` exists, nothing acts on its age.
- **Swapping the RR playbook gate from the `bull` ladder (measured inverted) to
  `rr_bull_bear`** (measured correct, +2.59 vs +1.00) — A1.

---

## Reporting

Log every change in `DEV_HANDOFF.md`, one heading per task. End with `ALL_DONE`
only when every released task has passed its "How to verify" block **in default
(switch-off) mode**, or has been gate-stopped with its reason recorded.

**No test round is pending** (`AGENT_TASK.md` → NO TEST ROUND). Do not invoke
the tester for any task in this batch. The user will ask if and when they want
one; until then each task's "How to verify" block is yours to run as part of
implementation, not a handoff.
