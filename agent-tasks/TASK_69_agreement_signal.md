# TASK 69 — Agreement signal (sentiment vs technical) + edge validation

**You: VS Code developer agent, psql + code.** Log progress in `DEV_HANDOFF.md`; end with
`ALL_DONE`. **DO NOT COMMIT/PUSH.**

> **QUEUED — blocked by TASK 65 and TASK 66.** Needs TASK 65's per-signal outcomes (to
> score buckets) and reuses TASK 66's agreement measure. Do not start until both are
> `ALL_DONE`. This is effectively the reporting/validation half of TASK 66.

## Why (one line)
The high-information setups are where the two engines **disagree** (technical-bull +
sentiment-bear, or vice versa). Surface that split as its own signal and **let forward
returns decide whether splits are traps or opportunities.** Background:
`docs/audit/bull_calc_analysis.md` §5 (P5).

## Scope

### 1. Agreement classification (per symbol, per date)
From the two stacks' directional verdicts (Stack-A sentiment label / Stack-B technical
gate — or TASK 66's contributing signals if it's done), classify each symbol into:
- `agree_bull` — both bullish
- `agree_bear` — both bearish
- `split_tech_bull` — technical bull, sentiment bear
- `split_tech_bear` — technical bear, sentiment bull
- `neutral` — neither side committed

If TASK 66 already emits `signal_agreement`, derive these buckets from the same inputs —
don't invent a second agreement calc. Write to a new column (e.g.
`drv_actionable.agreement_class`), additive, idempotent.

### 2. Edge validation per bucket (the point of the task)
A read-only view/report: for each `agreement_class`, the realized forward 5d/20d return,
win rate, and n — using the same forward-return source as TASK 65. This answers, with
data: **do split-tech-bull setups make money or bleed?** Same for each bucket.
Mirror `v_rule_scorecard` shape; tier by confidence.

### 3. Surface it
- Add an **agreement column** to the Actionable screen (label + the bucket's historical
  edge as a badge, reusing the canonical color/side helper from TASK 68 if done).
- No new color palette; read existing styles.

**Screen placement (intent):** the agreement badge sits **right next to TASK 66's
`bull_prob` column** on the Actionable screen — together they're the trade decision
(prob = how bullish, agreement = whether to trust it). Wire agreement into the same
top-of-screen filter as `bull_prob` so the user can require "high prob AND favorable
agreement" in one go. The bucket **edge-validation report** (v_agreement_scorecard) goes
on the **Performance screen** next to the scorecards — that's the trust/research view,
separate from the daily Actionable decision.

## How this feeds sizing (document, don't automate yet)
In `DEV_HANDOFF.md`, note the read for the user: which buckets show positive edge (lean
in / size up) vs negative (avoid), with sample sizes. Do not auto-size positions.

## Non-negotiables
- Additive only — no existing column/behavior changes.
- One agreement definition shared with TASK 66 (no duplicate calc — that would re-create
  the very problem TASK 68 fixes).
- No look-ahead; date-based outcomes. Conventions #7/#15 hold.

## Files expected to change (indicative)
- `etl/derive_actionable.py` (or TASK 66's `derive_bull_prob.py`) — `agreement_class`
- `db/baseline.sql` — `v_agreement_scorecard` view (+ column); `python -m db.init_db`
- `api/routers/{actionable,rules}.py` + `web/actionable.*` — column + badge

## How to verify (tester reference — only on request)
1. `agreement_class` populated for all anchor-date symbols; buckets sum to the universe.
2. `SELECT * FROM v_agreement_scorecard` returns one row per bucket with sane
   edge/win-rate/n; numbers reconcile to a manual AVG(fwd_20d_pct) for one bucket.
3. The agreement definition matches TASK 66's `signal_agreement` inputs (no second calc).
4. Actionable screen shows the agreement column + edge badge; existing columns unchanged;
   no console errors.
5. Derive idempotent; existing outputs unchanged (additive).
