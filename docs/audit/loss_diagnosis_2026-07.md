# Loss diagnosis — where is the money going? (2026-07)

Diagnosis-only report for TASK_117. Read-only + additive ETL (`backfill_derives`,
`compute_firing_outcomes --truncate`); no rule, derive-logic, or schema changes.
Numbers below are from the DB as of the refresh run on 2026-07-12.

## A. Outcome dataset refresh

```
python -m etl.backfill_derives            -> "No missing dates to backfill — nothing to do."
python -m etl.compute_firing_outcomes --truncate
```

- `drv_rule_outcome`: **7,924,452 rows** after truncate+repopulate
  (composite: 1,164,078 / atomic: 6,760,374, across 98 atomic rules).
- Date range covered: **2026-02-02 → 2026-06-11** (the most recent ~20 anchor
  dates have no 20d forward label yet by design — correct, not a bug).
- Latest anchor date `D` (`MAX(export_date) FROM hist_td`): **2026-07-10**.

## B. Rule scorecard — are the signals wrong?

`v_rule_scorecard`, `fires >= 20`, direction-adjusted 20d edge (`edge_20d`):
positive = the stock moved in the direction the rule implied.

**Every SELL-direction rule with fires >= 20 has edge_20d < 0; every BUY-direction
rule with fires >= 20 has edge_20d >= 0.** Split:

| direction | rules (fires>=20) | edge_20d < 0 | confidence |
|---|---|---|---|
| BUY  | 34 | 0  | all "proven" |
| SELL | 30 | 30 | all "unproven" |

Worst SELL rules (price rose after the sell signal, over the next 20d):

| rule_id | fires | edge_20d | win_rate |
|---|---|---|---|
| 699-SW-Resistance | 1,239 | -2.708 | 0.353 |
| 783-SW-Vol-Spke-Price-Dn-Past | 993 | -2.267 | 0.419 |
| 897-SW-Vlm-Spike-Price-Dn | 484 | -1.946 | 0.397 |
| 697-STM-Earnings-Date | 14,710 | -1.646 | 0.443 |
| 893-SA-TRR-blw-TN | 16,828 | -1.463 | 0.436 |
| 898-SA-Streak-VeryBad | 18,431 | -1.416 | 0.430 |
| 899-SA-Trend-Breaks | 16,634 | -1.405 | 0.437 |
| 784-SS-Streak-GoingBad | 17,581 | -1.370 | 0.435 |
| 896-SA-TRbelowTN-Trade-Breaks | 16,227 | -1.272 | 0.437 |
| 785-SS-Trade-Breaks | 16,621 | -1.192 | 0.444 |

Best BUY rules (all "proven", edge_20d 1.0-1.9%, win_rate ~0.48):

| rule_id | fires | edge_20d | win_rate |
|---|---|---|---|
| 52-BS-BRR | 27,477 | 1.943 | 0.503 |
| 188-BR-TNabvTD-UP-MACD-DAY | 16,258 | 1.284 | 0.487 |
| 99-BS-Min | 19,165 | 1.243 | 0.484 |
| 269-BS-Bull | 15,383 | 1.121 | 0.481 |
| 298-BS-BB-HL-HiHi-TN-TD | 15,375 | 1.119 | 0.481 |

**Reading**: the high-fire-count SELL rules (streaks, trend breaks, oversold /
"resistance" conditions) systematically fire near local bottoms and the stock
recovers over the next 20 trading days — the opposite of what the SELL label
implies. BUY rules, in contrast, are consistently right-signed with positive
edge and a plausible >0.48 win rate. This is the single cleanest, most
consistent finding in this report: **SELL-side signal quality, not BUY-side, is
the problem.**

**Regime caveat**: the outcome dataset spans ~4.5 months (2026-02-02 to
2026-06-11), effectively **one market regime**. These edges have not been
tested across a drawdown-then-recovery *and* a sustained downtrend separately,
so the SELL-rule finding could partly reflect "sell rules fire in dips that
this particular period happened to V-shape out of" rather than a structural
flaw. Directionally still useful, but don't over-fit thresholds to it yet.

## C. Personal track record — is the user following signals?

- `user_action_log` (explicit action log, e.g. Cockpit ACTED/SKIP-style
  entries): **1 row**. Effectively empty — the explicit feedback loop is open;
  nothing is logged from direct user interaction, so the system cannot
  attribute outcomes to explicit user decisions.
- `v_user_action_performance` (per project convention, this is *inferred* from
  `hist_f`/`hist_cs` position deltas, not from `user_action_log`/Cockpit
  ACTED-SKIP buttons): **335 rows**, but only covering **2026-06-01 →
  2026-06-10** (10 calendar days — a short window; take as directional, not
  conclusive).

  | change_type | n | avg fwd_5d_pct | avg fwd_20d_pct |
  |---|---|---|---|
  | ADD    | 230 | -0.61 | **-2.33** |
  | REDUCE | 105 | -0.53 | **+1.58** |

  In this short window, positions that were **added to** subsequently lost
  ground (-2.33% over 20d) while positions that were **reduced**
  subsequently gained (+1.58% over 20d) — i.e. adds were, on average, poorly
  timed and reduces were early/right. This echoes the SELL-rule finding in
  section B but from the position-delta side and is a much smaller, shorter
  sample.
- Attribution split: 214 discretionary vs 121 rule-attributed rows.

## D. Position bleed — which held names are losing?

Latest `hist_cs` snapshot per account (all four accounts current as of
2026-07-12; `hist_f` is stale — max `export_date` 2026-07-02 across its
accounts — so `hist_cs` is used as the primary/authoritative source here).

Top 10 unrealized losers by `gain_dollar` ascending:

| tos_symbol | account | market_value | cost_basis | gain_dollar | gain_pct |
|---|---|---|---|---|---|
| XHB | Rollover_IRA ...892 | 19,549.80 | 20,690.72 | -1,140.92 | -5.51% |
| DHI | Rollover_IRA ...892 | 16,673.80 | 17,578.69 | -904.89 | -5.15% |
| BNDD | Rollover_IRA ...892 | 39,448.00 | 40,173.50 | -725.50 | -1.81% |
| TLT | Rollover_IRA ...892 | 29,564.50 | 30,180.61 | -616.11 | -2.04% |
| CELH | Designated_Bene_Individual ...254 | 550.80 | 1,031.36 | -480.56 | -46.59% |
| SOFI | Designated_Bene_Individual ...254 | 845.10 | 1,304.18 | -459.08 | -35.20% |
| RKT | Rollover_IRA ...892 | 7,195.00 | 7,624.14 | -429.14 | -5.63% |
| LQD | Rollover_IRA ...892 | 10,746.00 | 10,890.09 | -144.09 | -1.32% |
| RHP | Rollover_IRA ...892 | 15,713.75 | 15,856.97 | -143.22 | -0.90% |
| ZROZ | Rollover_IRA ...892 | 6,120.00 | 6,230.92 | -110.92 | -1.78% |

Portfolio totals (32 lots across 4 accounts): **market_value = $406,069.95**,
**unrealized gain_dollar = -$3,890.68** (~-0.95% of cost basis $325,077.01).

**This is a small unrealized drag, not a large one.** For context, realized
losses booked over the same broad window (`drv_cs_realized_gain`,
2026-02-02 → 2026-06-02, 433 sale lots) sum to **-$16,704.21** — over 4x the
current unrealized drag. **Most of the money lost has already been realized
by selling, not left sitting as an unrealized loser on the books today.** This
matters for the verdict: the pain isn't "big losers still held" so much as
"losses already crystallized," which points at either bad entry timing
(buying into things that then dropped and were sold) or selling at the wrong
time (per section B/C, selling right before recoveries).

## E. Unheeded sell signals & stop breaches — are losers being cut?

### E.1 Current stop breaches (anchor date D = 2026-07-10)

Held positions where `drv_ma.last_price < drv_actionable.stop_level`:

| tos_symbol | position $ | stop_level | last_price | consolidated_action |
|---|---|---|---|---|
| BNDD | 119,642.40 | 99.68 | 98.62 | HOLD |
| TLT | 80,870.50 | 85.97 | 84.47 | **INCREASE** |
| LQD | 32,474.00 | 108.59 | 107.46 | REMOVE |
| CLOX | 30,642.00 | 25.54 | 25.535 | HOLD |
| BUXX | 30,330.00 | 20.24 | 20.22 | HOLD |
| DHI | 16,673.80 | 154.00 | 151.58 | REMOVE |
| ZROZ | 6,120.00 | 63.86 | 61.20 | **INCREASE** |

7 held positions are currently trading below their stop_level. Only 2 of 7
(LQD, DHI) actually carry a REMOVE recommendation; the rest are HOLD, and two
(TLT, ZROZ — both bond/duration ETFs) are flagged **INCREASE** despite being
below stop. Total dollars sitting below stop: **~$316.75k** (dominated by
BNDD/TLT, both fixed-income). This is a smaller finding numerically (bond ETFs
below a tight stop band aren't necessarily "losers" in the equity sense) but
it does show `stop_level` breaches aren't consistently reflected in
`consolidated_action`.

### E.2 Forward outcome of REDUCE/REMOVE signals while held (last 40 anchor dates, 2026-05-20 → 2026-07-10)

428 (symbol, date) rows had `consolidated_action` in (REDUCE, REMOVE) while
`held_today = true`. Classifying each by whether the symbol was still held in
`drv_portfolio` 5 sessions later (using the anchor-date sequence, not calendar
days):

| group | n | avg fwd_5d | avg fwd_20d |
|---|---|---|---|
| **Followed** (no longer held 5 sessions later) | 157 | — | -1.40% (n=81 with a 20d label) |
| **Ignored** (still held 5 sessions later) | 211 | +1.57% (n=194) | +2.01% (n=129) |
| (near end of window, no +5d label available) | 60 | — | — |

**Reading**: when the sell-side signal was ignored (position kept), the stock
went *up* on average over the following 5 and 20 sessions (+1.57% / +2.01%).
When it was followed (position cut), the stock kept falling (-1.40% over 20d)
— i.e. cutting, when it happened, was on average the right call, and *not*
cutting was, on average, also not costly (the position recovered). **This
does not show a large "cost of not acting" — if anything it mirrors section B:
the SELL-direction signal itself is what's mistimed, not primarily the user's
follow-through on it.** Caveat: same one-regime caveat as section B; 129-194
row samples per group are decent but not huge, and this measures the whole
book (all held REDUCE/REMOVE), not just the biggest-dollar names.

### E.3 Buy-bias check (same 40-date window)

`consolidated_action` counts, split by whether the symbol was already held:

| action | held_today=False | held_today=True | total |
|---|---|---|---|
| ADD | 4,291 | 344 | 4,635 |
| INCREASE | 1,081 | 300 | 1,381 |
| REDUCE | 385 | 276 | 661 |
| REMOVE | 1,885 | 152 | 2,037 |
| **ADD+INCREASE** | 5,372 | **644** | 6,016 |
| **REDUCE+REMOVE** | 2,270 | **428** | 2,698 |

Across the whole surface, ADD/INCREASE outnumbers REDUCE/REMOVE about **2.2:1**
(6,016 vs 2,698). Restricted to symbols *already held* — where a buy-bias would
most directly translate into "keep deploying capital into a falling position"
— it's **644 vs 428, still ~1.5:1 in favor of adding**. This is a real, though
more moderate, buy-side skew: the surface is more likely to tell you to add to
a held position than to trim it, even before accounting for signal accuracy.

## F. Where the money is going — verdict

Ranking the three candidate causes by the evidence gathered:

1. **Signals are wrong — SELL-side specifically. (Strongest evidence.)**
   Every SELL-direction rule with a meaningful fire count (fires>=20, 30/30
   rules) has *negative* direction-adjusted 20d edge — i.e. after a SELL
   signal fires, price tends to recover, not fall further. Every BUY rule
   (34/34) has positive edge and is "proven." Section C's short-window
   position-delta data (adds -2.33% fwd20, reduces +1.58% fwd20) and
   section E.2 (ignoring REDUCE/REMOVE outperformed following it, +2.01% vs
   -1.40% fwd20) both point the same direction. The realized-vs-unrealized
   loss split in section D (-$16.7k realized vs -$3.9k unrealized) is
   consistent with losses being crystallized by selling at bad moments rather
   than sitting as unrealized drag.

2. **Over-allocation / buy bias. (Moderate evidence.)**
   ADD/INCREASE recommendations outnumber REDUCE/REMOVE ~2.2:1 overall and
   ~1.5:1 even among already-held positions (section E.3). Combined with #1
   (SELL signals are unreliable, so REDUCE/REMOVE gets suppressed/ignored
   correctly in practice), the net effect is a surface that leans toward
   adding capital, which is riskier if BUY-side entries aren't well-timed
   relative to the broader tape.

3. **Losers aren't cut. (Weakest evidence — largely not supported.)**
   Only 7 held positions currently breach stop_level, worth ~$317k (mostly
   fixed-income ETFs, arguably not "losers" in the traditional sense), and
   only $3.9k of unrealized loss sits on the books today. The forward-return
   data in E.2 shows that *not* cutting REDUCE/REMOVE-flagged positions was,
   on average, the better outcome over this window — the opposite of what
   "losers aren't cut" would predict. This cause is not well supported by the
   data collected here (though the one-regime caveat applies).

**Highest-leverage fixes implied (design/implementation deferred):**

1. **Re-validate and likely deprioritize/retune the SELL-side rule set**
   (streak/trend-break/oversold/resistance rules) — they are the most
   consistent negative-edge finding in the dataset. At minimum, downweight
   their contribution to `consolidated_action` until re-tested across a
   different regime.
2. **Tie `stop_level` breaches directly into `consolidated_action`/priority**
   so a below-stop held position can't silently show HOLD or INCREASE
   (section E.1) — a cheap consistency fix independent of signal quality.
3. **Close the explicit feedback loop** (`user_action_log` is effectively
   empty) so future diagnosis can separate "the system recommended X and the
   user did X" from "the user did something unrelated" — right now all
   personal-performance evidence is inferred from position deltas over a
   10-day window, too thin to be conclusive on its own.
