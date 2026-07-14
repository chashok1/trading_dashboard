# Actionable Screen — Trading Playbook & Design Critique

**Date:** 2026-07-13 · **Purpose:** turn the Actionable screen into a decisive,
repeatable trading routine, and state honestly which parts of the system are
validated vs. faith-based. Grounded in `docs/actionable_logic.md`,
`docs/actionable_dataflow_analysis.md`, `docs/rule_tuning_and_outcomes.md`,
`docs/audit/bull_calc_analysis.md`, `docs/audit/actionable_screen_review.md`,
`docs/quad_design.md`, `docs/bull_rollout_runbook.md`.

> Not financial advice — this is an operating procedure for *your own* system.
> The system's edge numbers cover ~4 months of one market regime. Treat every
> "proven" label as directional evidence, not proof.

---

## 0. Diagnose FIRST — why trades aren't making money

There are only three possible failure modes. The system already has the
instruments to tell them apart. Do this once, before changing anything:

| Hypothesis | Where to check | Verdict signal |
|---|---|---|
| **H1 — Signals are wrong** (you follow them, they lose) | Performance screen → "Your actions" panel (`/rule-performance`): FOLLOWED rows' avg forward return | FOLLOWED trades have negative avg fwd return → system problem → §5 fixes |
| **H2 — You contradict/override** (signals fine, execution isn't) | Same panel: FOLLOWED vs CONTRADICTED headline + counts | Many CONTRADICTED rows, and CONTRADICTED underperforms FOLLOWED → discipline problem → §3 playbook is the fix |
| **H3 — Timing/staleness** (acting on stale or intraday-mixed data) | Ingest log (`/api/ingest-log`), amber date picker, stale banner history | Trades placed while anchor was behind or feeds missing → §2 pre-flight is the fix |

The "Your actions" panel is **inferred from your daily CS/F loads**
(`drv_inferred_action`, TASK_121) — since you load transactions almost daily,
this data is real. Refresh the outcome ETL first so the numbers are current:

```cmd
python -m etl.backfill_derives
python -m etl.compute_firing_outcomes --truncate
```

**Decision after diagnosis:** H1 → restrict yourself to the high-conviction
subset (§3.3) and queue the §5 validations. H2 → adopt the hard rules (§4)
verbatim. H3 → never trade without the pre-flight (§3.1). Usually it's a mix;
the playbook below handles all three.

---

## 1. What the screen actually gives you (mental model)

```
            SENTIMENT stack                TECHNICAL stack
   RR/CALL/ETF/II/SSS/PS (periodic)   price vs Trend/Trade/BB/RR (EOD+intraday)
                 │                               │
        consolidated_action                  rr_action (QS)
                 └────────── _compute_final_call ─────────┘
                                    │
                    ACTION column = Final Call + confidence
                                    │
        overlays that NEVER change the call, only frame it:
        MACRO (quad regime) · Rules(edge) · P(↑20d)/Agree · STOP · LOW CONF
                                    │
                        AMT$ (sizing) + stop_level (risk)
```

One row = one verdict (**ACTION**), one size (**AMT$**), one risk line
(**stop**). Everything else on the screen is *context for confidence*, not a
second opinion to re-litigate. The #1 cause of hesitation is treating the 20
columns as 20 votes. They are not — the server already voted.

### Column triage — read only what decides

| Tier | Columns | Role |
|---|---|---|
| **Decide** | ACTION (Final Call + confidence badge), AMT$, stop (STOP pill / red sub-text), POS$ | The trade itself |
| **Confirm** | MACRO (conflict check), Rules (edge) pills, LOW CONF sub-label, Sources freshness dates | Raise/lower conviction, size |
| **Diagnose only** | CALC, P(↑20d), Agree, Technical, RSI/MACD/MACDH, Vlm, IV | Model evaluation; hidden by default — keep them hidden while trading |

Use the gear menu to hide everything in the third tier during the trading
pass. Open it only in the weekly review.

---

## 2. When to decide vs when to execute (your actual day)

You can only trade during market hours, and the full decision data (Sources,
MACRO, ACTION) is only final after the EOD load — so split the day:

| When | Data state | What you do |
|---|---|---|
| **Evening / pre-market** | Yesterday's EOD (TOSD) fully derived — ACTION, Sources, MACRO final for anchor D | **PLAN**: run the triage (§3.2), pick trades, sizes (AMT$), limit levels (near LRR), stops |
| **During market hours** | Load TOSL periodically — correct and expected. %CHG, RR position, Technical action, stop checks go **live**; Sources/MACRO stay as-of last close (fine — they're plan inputs, they don't change intraday) | **EXECUTE** the plan: limit fills near LRR, stop checks. Don't form *new* theses intraday — only price moved, not the evidence |
| Amber date / stale banner | Derives behind loaded data | **No decisions.** Click Re-derive now, or load the missing file first. |

There is nothing wrong with intraday TOSL loads — TOSL is the execution feed.
Detail on exactly which cells move intraday: `docs/actionable_dataflow_analysis.md`.

---

## 3. The daily playbook

### 3.1 Pre-flight (2 minutes — skip nothing)

1. Date picker not amber; no orange stale banner (else Re-derive).
2. Ingest log: today's expected feeds landed (TOSD/TOSL/TOSW/Y; periodic feeds per their cadence).
3. Hedgeye panel `effective_date` current — intraday feeds (RTA/Top-5/ETF chg) surface here first.
4. **One-glance market check — the mini-tape SPX chip**: %CHG plus where the
   tick sits in its risk-range bar. Near TRR (top) = market extended, don't
   chase buys today; near LRR (bottom) = better day to fill your planned buys.
   VIX chip up sharply = halve sizes. (The quad band is the slow *regime*
   backdrop — check it weekly, not to gauge today.)

### 3.2 Triage (10 minutes, top-down)

Keep the **default sort** (dollar-weighted edge, TASK_120) — it already ranks
by "expected $ impact × historical edge". Work the top 10–15 rows only. Rows
below that are tomorrow's problem; scrolling the whole list is how decisiveness
dies.

For each row, run the 5-gate check **in order, stop at the first fail**:

```
GATE 1  ACTION badge
        HOLD / — ......................... next row (no trade, not a "maybe")
GATE 2  Confidence badge
        Gate or Mixed .................... Skip (log it) — stacks disagree or
                                           a stop gated the buy; not your trade
GATE 3  STOP
        STOP pill / price < stop_level ... no new buying, ever. If held:
                                           execute the exit review NOW
GATE 4  Direction-specific check
        SELL side: LOW CONF sub-label? ... demand one more confirmation
                                           (source REMOVE or Technical sell);
                                           none → Skip
        BUY side: MACRO bearish
        (SA/STM) on this row? ............ conflict matrix says trim/skip →
                                           half size or Skip
GATE 5  Edge
        Rules(edge) pills: at least one
        green (positive edge) pill, or a
        fresh winning source (recent
        snapshot date in Sources cell) ... full size
        only stale/red pills ............. half size or Skip
```

A row that passes all 5 gates is a trade. **Take it at AMT$ next session, no
re-analysis.** A row that fails any gate gets Skip/Snooze — clicked, not just
mentally noted (see 3.4).

**Hide the no-action rows before you start:** HOLD/"—" rows sort low by
design (sort = action severity, then $ size), but the cleaner move is to
click the action chips (SELL ALL · SELL SOME · BUY SOME · BUY→MIN) so only
tradeable rows render. If HOLD rows ever crowd the top-15 under the default
sort, that's a sort bug — file a dev task.

### 3.3 High-conviction subset — REQUIRED until re-validated
### (rewritten 2026-07-13 from measured evidence, TASK_123)

The validation round (`docs/audit/signal_validation_2026-07.md`) found that
**following the system's recommendations lost more than contradicting them**
(FOLLOWED −3.57% vs CONTRADICTED −2.95% fwd-20d). The broad signal set is
net-negative; only a narrow subset showed real, correctly-signed edge. Trade
ONLY that subset:

**Buys** — take only when ALL of:

- Final Call is **BM or BMN** (measured edge +3.2% / +2.1–3.2%, win 63–70%)
- The case rests on **RR or SSS** (buy-family edge +2.8% / +2.3%) — not on
  PS, ETF, or II (all measured *negative*: −2.1% / −3.4% / −1.4%)
- `rr_bull_bear` = **B** in the RR drilldown (B +2.59% vs !B +1.00%) — do
  NOT use the bull ladder (−3..+3) for anything; it measured *inverted*
- Standard gates still apply (no STOP, no MACRO conflict)

**Sells** — trust **SA/gate** (edge +5.1%, win 72%) and RR-driven sell-family
(−2.67% correctly signed). **Distrust SS/high** — it measured directionally
*wrong* (price rose +5.0% after the sell, win 37%) — demand a second
confirmation before acting on it, High badge or not.

Expect 0–3 trades/day. Fewer, better trades is the point — the sizing engine
(category MIN/MAX, AMT$) already prevents any single name from mattering too
much. All edges are one-regime numbers (A5): revisit after a drawdown/chop
period is in the data.

### 3.4 Close the loop — every row gets a click

Done / Skip / Snooze on every triaged row (bulk bar or Focus mode:
Enter=Done · S=Skip · Z=Snooze). This:

- keeps tomorrow's list short (acted rows hide until the next anchor),
- writes the forensic snapshot to `user_action_log`,
- makes FOLLOWED/CONTRADICTED stance in the "Your actions" panel meaningful.

Skipping this step is why triage feels endless: the same 40 rows greet you
every morning.

### 3.5 Execution rules (three rules, plain)

1. **Trade exactly the AMT$ dollars shown.** Never a different size — the
   MIN/MAX sizing is the risk system. (`SELL→MAX` badge = you're over the
   category ceiling; AMT$ is the trim amount.)
2. **Buys: limit order near the LRR line** (bottom of the risk-range bar /
   Graph 1). The system's buy signals assume buying the pullback — buying at
   market near the top of the range is a different, worse trade.
3. **The moment a buy fills, place the stop at `stop_level`** (shown under
   AMT$) with your broker. Don't wait for tomorrow's STOP pill.

---

## 4. Hard rules (the decisiveness contract)

1. No trade on a row whose confidence badge is Gate or Mixed.
2. No buy on a stop-breached row. No exception "because it's cheap now."
3. No size other than AMT$ (±rounding).
4. No decisions when the date is amber or the stale banner shows.
5. No intraday thesis changes — intraday is for executing the plan.
6. Every triaged row gets Done/Skip/Snooze.
7. Overrides are allowed but must be logged (OVERRIDDEN) — so the panel can
   later prove whether your overrides beat the system. If CONTRADICTED keeps
   underperforming FOLLOWED, stop overriding.
8. One weekly review (§6); no rule/threshold edits mid-week.

---

## 5. Design validation — what holds up, what doesn't

### Sound (keep relying on it)

- **Architecture & explainability**: two-stack design, server-side Final Call,
  per-cell "why" drilldowns, forensic action log, freshness honesty (stale
  banners, IDY tags). Independently reviewed 2026-07-03; P1 bugs fixed
  (TASK_103–110).
- **Position-aware sizing & suppression** (MIN/MAX, ALREADY ESTABLISHED,
  AT CEILING/FLOOR) — coherent risk framework.
- **Outcome instrumentation**: `v_rule_scorecard` (direction-adjusted
  edge_20d), firing-based outcomes, inferred-action performance from your
  CS/F loads. This is the only part of the system that asks "does it make
  money?" — use it weekly.
- **Safety rails added 2026-07**: stop_breached gating of buys (TASK_119),
  LOW CONF sell annotation from `v_unproven_sell_rules` (TASK_118).

### Assumptions — MEASURED 2026-07-13 (TASK_123)

Full evidence: `docs/audit/signal_validation_2026-07.md` (views
`v_bull_gate_scorecard`, `v_final_call_scorecard`, `v_source_edge_scorecard`
now standing in the DB — re-query any time).

| # | Assumption | Verdict | Measured reality |
|---|---|---|---|
| A1 | Bull ladder (−3..+3) switches the RR playbook correctly | **BROKEN — inverted** | −2 bucket +4.85% fwd-20d; +2/+3 buckets *negative*. But `rr_bull_bear` (B/!B) works: B +2.59% vs !B +1.00% |
| A2 | `_FC_SCALE` strengths reflect real conviction | Untestable this regime | BM/BMN show real positive edge (+2.1 to +3.2%, win 63–70%); no usable BS sample to rank against |
| A3 | Disagreement → HOLD ("mixed") is safe | **Weak/broken** | Mixed rows move 20–35% more than clean HOLDs (informative, wasted). SS/high is directionally *wrong* (−5.0% edge) while SS/mixed is right (+0.7%) |
| A4 | Source precedence PS>ETF>RR>SSS>II>CALL | **BROKEN — near-reversed** | Empirical: RR +2.84 > SSS +2.33 > CALL +0.52 > II −1.42 > PS −2.07 > ETF −3.40 |
| A5 | Edges generalize across regimes | Standing caveat | One regime (~5 months, a bounce); every number above may flip in a drawdown |
| A6 | Hit thresholds ±0.5% meaningful | **Weak** | Win rates ~45–50% at any threshold (near coin-flip), but relative rule ranking stable (top-10 overlap 7/10) |

**Headline (item D):** FOLLOWED trades −3.57% vs CONTRADICTED −2.95% vs
NO_SIGNAL −0.88% (fwd-20d) — **the system, not the operator, was the larger
loss source** over this window. Hence §3.3 is mandatory, not optional.

**Standing instructions:** stay on the **Baseline** param profile; do not
activate Sigmoid/ml profiles; never use the bull ladder; treat PS/ETF/II-driven
buys as noise until re-measured in a second regime.

### Follow-up design queue (not yet specced — decide deliberately)

1. **Re-rank `SOURCE_ORDER` from measured edge** (cheap, directly fixes A4).
2. **Stop gating the RR playbook on the bull ladder** — QP (`rr_bull_bear`)
   is the component that works (A1).
3. **Score disagreement instead of discarding it** — mixed = "about to move";
   investigate SS/high's wrong direction (A3).
4. **Re-run the whole validation after a second regime** exists in the data
   (A5) — before trusting any of the above as permanent.

---

## 6. Weekly maintenance loop (30 minutes, e.g. Saturday)

1. Refresh outcomes: `backfill_derives` + `compute_firing_outcomes --truncate`.
2. Performance screen: scorecard sorted by edge_20d ASC — rules with many
   fires and clearly negative edge → deactivate deliberately (`is_active=false`,
   then `rebuild_rules`; mind the DB-only-tweak gotcha).
3. "Your actions": did FOLLOWED beat CONTRADICTED this week? Adjust your own
   behavior, not the rules, if not.
4. Re-read A1–A6 status; nag the validation queue.
5. Only now consider threshold/profile changes — never mid-week.

---

## Summary (pin this)

- **Diagnose first**: the "Your actions" panel (built from your daily CS/F
  loads) tells you whether the system or the operator is losing money.
- **One verdict per row**: ACTION + AMT$ + stop. The other columns are
  context, not extra votes.
- **5-gate check, stop at first fail**: ACTION → confidence → STOP → LOW
  CONF/MACRO conflict → edge. Pass = trade at AMT$ same day. Fail = Skip,
  clicked.
- **Plan evening/pre-market (EOD data final); execute intraday with TOSL
  loads** — TOSL is the execution feed, not a problem.
- **Every row gets Done/Skip/Snooze** — it keeps the list short and the
  feedback loop honest.
- **Measured 2026-07 (TASK_123): the broad signal set loses money** —
  FOLLOWED underperformed CONTRADICTED. Trade only the §3.3 subset:
  BM/BMN buys backed by RR/SSS with `rr_bull_bear=B`; trust SA/gate sells;
  distrust SS/high sells, PS/ETF/II buys, and the bull ladder entirely.
- All edges are one-regime numbers — re-run the validation once a
  drawdown/chop period is in the data before treating any of this as
  permanent.
