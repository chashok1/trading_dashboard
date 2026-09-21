# Signal validation scorecards — second-regime revalidation (TASK_139)

Read-only + additive report. Same four analyst views as `docs/audit/
signal_validation_2026-07.md` (TASK_123) — `v_bull_gate_scorecard`,
`v_final_call_scorecard`, `v_source_edge_scorecard`, `v_rule_scorecard` — plus
the `drv_inferred_action` aggregate, **queried unchanged**. No view, derive,
rule, threshold, or UI change was made in this task. Every table below is
reported **pooled** (2026-02-02 → latest scored date), **orig** (2026-02-02 →
2026-06-11, July's window, as a regression check), and **new** (2026-06-12 →
latest scored date, the independent replication window).

## Prep — dataset refresh

```
python -m etl.backfill_full
```

(`backfill_full` reported 0 missing derive dates — `drv_trig` already covered
every `hist_td` date through the 2026-09-18 anchor — then ran
`compute_firing_outcomes` over the full history, no `--truncate` needed since
the table already held every historical row; upsert is idempotent.)

`drv_rule_outcome` after the refresh: **12,406,349 rows** (composite:
1,299,918; atomic: 11,106,431), `as_of_date` range **2026-02-02 → 2026-08-20**.
The max date is ~4 weeks behind the 2026-09-18 anchor — expected, not stale:
a 20-trading-day forward return needs 20 future trading days of price (same
maturity-lag property TASK_142 now encodes in `ref_freshness_contract`).

`v_bull_gate_scorecard` / `v_final_call_scorecard` / `v_source_edge_scorecard`
build their own `LEAD(last_price, 5/20)` window directly over `drv_ma` (not a
join to `drv_rule_outcome`), so their own max scored date tracks `drv_ma`
directly rather than `drv_rule_outcome`'s maturity lag; verified via
`MAX(as_of_date)` over `drv_cat_atomic_input` joined to `drv_ma` = **2026-09-18**
(today's anchor) — the LEAD window itself returns NULL for dates too close to
the end of each symbol's own price history, which the `WHERE fwd20 IS NOT
NULL` filter already excludes, so no extra date cap was needed for A1/A2/A4.

## Window split

| window | start | end |
|---|---|---|
| pooled | 2026-02-02 | latest scored |
| orig (July's window) | 2026-02-02 | 2026-06-11 |
| new (independent) | 2026-06-12 | latest scored |

---

## A. Bull-gate scorecard (assumption A1)

**`bull_ladder` (MQ ladder, -3..+3), avg_fwd_20d by bucket:**

| bucket | orig n | orig avg20 | new n | new avg20 | pooled n | pooled avg20 |
|---|---|---|---|---|---|---|
| -3 | 8 | -4.662 | 0 | — | 8 | -4.662 |
| -2 | 2,252 | +4.413 | 696 | **+10.462** | 2,948 | +5.841 |
| 0  | 58,023 | +1.627 | 31,758 | +1.826 | 89,781 | +1.697 |
| 2  | 3,574 | -1.381 | 2,497 | -0.648 | 6,071 | -1.080 |
| 3  | 8,768 | -0.415 | 7,186 | -0.366 | 15,954 | -0.393 |

**Still inverted in both windows**: -2 (most bearish label) outperforms +2/+3
(most bullish label) in orig, new, and pooled — the gap even widened in the
new half (-2 at +10.46% vs +3 at -0.37%). **Verdict: HELD (still broken).**
-3 has n=0 in the new half — that rung simply didn't fire; ignore as before.

**`rr_bull_bear` (QP, 'B'/'!B') — does B separate outcomes correctly?**

| window | !B n | !B avg20 | B n | B avg20 | B beats !B? |
|---|---|---|---|---|---|
| orig | 58,778 | +1.043 | 7,357 | **+3.044** | yes (correct) |
| new  | 33,159 | **+1.952** | 8,629 | -0.296 | **no — reversed** |
| pooled | 91,937 | +1.371 | 15,986 | +1.241 | no (roughly flat) |

**Verdict: FLIPPED.** July found `rr_bull_bear` = B correctly separating
better forward returns (+2.594% vs +1.003%, both large-n). In the new,
independent half that separation **reverses**: !B now averages +1.952% vs
B's -0.296%, both on large samples (n=33,159 / 8,629). Pooled washes out to
roughly flat because the two halves point opposite directions. This directly
affects the "still out of scope" idea in `AGENT_WORK.md` of swapping the RR
playbook gate from `bull` to `rr_bull_bear` — that idea is **no longer
supported**: `rr_bull_bear`'s July-era edge did not survive a second regime
any better than the `bull` ladder did.

---

## B. Final Call scorecard (assumptions A2, A3)

**A2 — BM vs BS (buy-side conviction ladder):**

| final_code/conf | orig n | orig edge20 | new n | new edge20 | pooled n | pooled edge20 |
|---|---|---|---|---|---|---|
| BM/high  | 208 | +1.412 | 623 | -0.125 | 831 | +0.260 |
| BMN/gate | 1,970 | +1.050 | 1,579 | +0.463 | 3,549 | +0.789 |
| BMN/high | 555 | +1.016 | 1,378 | -0.234 | 1,933 | +0.125 |
| BS/high  | 29 | -9.330 | 71 | **+4.238** | 100 | +0.304 |

**Regression-check note (step 3):** July's report found BS/high at **n=2**
(too thin to use) for the same 2026-02→06-11 window; this rebuild finds
**n=29** for that identical window. This is a real discrepancy, not rounding,
and per this task's own instructions it is itself a finding: `final_code`/
`fc_confidence` are read live off `drv_actionable` for each historical date,
not a frozen snapshot — decision-layer logic (rule thresholds, param sets,
`_compute_final_call`) has changed multiple times since 2026-07-13, and any
date that was re-derived since then (stale-heal, manual backfill) picks up
today's classification logic, not July's. `drv_rule_outcome` (frozen at
firing time) does not have this issue; `v_final_call_scorecard` and
`v_bull_gate_scorecard`/`v_source_edge_scorecard` (all three read live
`drv_actionable`/`drv_cat_atomic_input`/`drv_tn_td_bb_rr`/`drv_outlook_action`)
do. Treat A1/A2/A3/A4 numbers in this report as "current decision logic
applied retroactively to historical prices", not "what the screen actually
showed on that date" — the same caveat applied, unstated, in the July report.

**Verdict: STILL THIN / untestable**, same as July — BS/high's n grew from 2
to 29-100 but is still below the n≥30 "promising" floor in the orig window
and only modestly past it pooled; the new-half result (+4.238%, n=71) is
provocative but the orig-window result (-9.330%, n=29) points the opposite
way on similar order-of-magnitude n. Needs more history before BM vs BS can
be ranked with confidence — unchanged from July's conclusion.

**A3 — is `SS`/`high` still directionally wrong vs `SS`/`mixed`?**

| window | SS/high n | SS/high edge20 | SS/mixed n | SS/mixed edge20 |
|---|---|---|---|---|
| July (TASK_123) | 59 | -5.032 (wrong dir) | 58 | +0.730 (correct) |
| orig (regression check) | 100 | -3.611 (wrong dir) | 297 | +2.443 (correct) |
| new (independent) | 114 | **+1.591 (correct)** | 248 | **-0.680 (wrong dir)** |
| pooled | 214 | -0.840 (wrong dir) | 545 | +1.022 (correct) |

**Verdict: FLIPPED in the new half.** The orig window reproduces July's
finding directionally (SS/high wrong-signed, SS/mixed correctly-signed,
n's in the same range). In the new, independent half the pattern **inverts**:
SS/high becomes correctly signed (+1.591%) and SS/mixed becomes wrong-signed
(-0.680%), both on n well past the n≥30 floor (114/248). Pooled reverts to
July's direction only because the orig window dominates by n. **This is a
genuine, surprising flip** — the "distrust SS/high, prefer SS/mixed" guidance
in `docs/actionable_playbook.md` §3.3 no longer holds uniformly; it held for
one regime and reversed in the next. Not one of TASK_140/141's two gate
questions, so it does not block this batch, but `actionable_playbook.md` §5's
A3 row is updated to reflect FLIPPED rather than "weak/broken".

---

## C. Per-source edge scorecard (assumption A4) — **TASK_140 gate**

Buy-family (ADD+INCREASE) edge_20d, six outlook sources only, by window:

| source | orig n | orig edge | new n | new edge | pooled n | pooled edge | static rank (PS>ETF>RR>SSS>II>CALL) |
|---|---|---|---|---|---|---|---|
| RR   | 917 | **+10.196** | 1,640 | **+10.847** | 2,557 | **+10.613** | 3 (mid) |
| SSS  | 303 | +2.379 | 463 | +0.116 | 766 | +1.011 | 4 |
| CALL | 8,009 | +0.479 | 5,625 | +0.751 | 13,634 | +0.591 | 6 (last) |
| ETF  | 52 | -1.239 | 70 | +1.054 | 122 | +0.077 | 2 (near-first) |
| II   | 171 | -1.076 | 77 | -0.327 | 248 | -0.843 | 5 |
| PS   | 106 | -1.841 | 116 | -0.123 | 222 | -0.944 | **1 (first)** |

**Empirical ranking, both halves:** RR is the clear best in orig, new, and
pooled — by a wide margin, on a large and growing sample (n=917 → 1,640).
PS (today's #1 static precedence) is negative or flat-negative in every
window. SSS holds a solid positive edge in both halves (weaker in the new
half but still positive, n well past 30). II stays negative in both halves.
ETF is the one source whose sign is not stable: strongly negative in July
(-3.396, n=51) and in this orig-window regression check (-1.239, n=52), but
flips to modestly positive in the new half (+1.054, n=70) — n=70 clears the
30-floor but is still the thinnest of the six, so treat ETF's new-half sign
as provisional, not proven.

**Answering step 5's A4 question directly: is the empirical ranking still
near-reverse of the static `SOURCE_ORDER`?** Yes — RR (static rank 3 of 6)
is empirically #1 by a wide margin in both halves; PS (static rank 1, today's
*highest* precedence) is empirically among the *worst* in both halves. The
core claim survives on the two sources that drive it (RR, PS — both large-n,
both stable-signed across both halves). ETF's flip is real but thin and
affects only the #2 static slot, not the #1 (PS) or the RR/SSS advantage.

**Verdict: HELD.** → Per `AGENT_WORK.md`'s gate table, **TASK_140 may
proceed.**

---

## D. Inferred-action aggregate — who loses the money? (§D headline)

| stance | orig n | orig avg20 | orig $-wt | new n | new avg20 | new $-wt | pooled n | pooled avg20 | pooled $-wt |
|---|---|---|---|---|---|---|---|---|---|
| FOLLOWED | 484 | -3.352 | -2.396 | 321 | +0.934 | +0.156 | 805 | -1.643 | -1.120 |
| CONTRADICTED | 374 | -2.868 | -2.461 | 301 | +1.108 | +2.011 | 675 | -1.095 | -0.411 |
| NO_SIGNAL | 525 | -0.838 | -0.729 | 99 | -1.436 | -1.287 | 624 | -0.933 | -0.843 |

**Regression check:** orig-window n's (484/374/525) closely match July's
(474/364/525) — the small deltas are expected (a handful of additional
rows matured/were reprocessed since; same caveat as §B above) and the sign/
ranking reproduces (FOLLOWED worst, CONTRADICTED next, NO_SIGNAL least bad),
so no "stop" condition here.

**Does FOLLOWED still underperform CONTRADICTED?** Yes, in all three windows
— **HELD**. This is the core, money-relevant finding from July and it
survives the new regime: acting on the system's own recommendation
underperforms doing the opposite, consistently.

**Does FOLLOWED still underperform NO_SIGNAL?** No, in the new half — **FLIPPED**,
but on a thin NO_SIGNAL sample (n=99, well under the size of the other two
cells in that window). The market was rising broadly in the new period
(+2.9% SPX, see §Regime below), so NO_SIGNAL rows (mostly non-trending,
lower-beta names by construction of what doesn't generate a signal) lagged
a broad rally — plausible, but n=99 is thin enough that this specific
sub-finding should be re-checked once more data accumulates, not acted on.

**Combined verdict: HELD** on the primary, actionable claim (don't blindly
follow the system's own calls — fading it beats following it); the secondary
NO_SIGNAL comparison is FLIPPED/thin and not load-bearing for either gate.

---

## E. Rule scorecard — BUY/SELL direction split (§B/TASK_141 gate)

Composite rules, `fires >= 20`, direction-adjusted `edge_20d` (SELL sign
flipped so >0 = correctly signed):

| window | BUY rules | BUY positive-edge | SELL rules | SELL positive-edge | SELL n-wt edge (n≥100 subset) |
|---|---|---|---|---|---|
| orig (regression check) | 34 | 34/34 (100%) | 30 | 0/30 (0%) | -1.307 (unweighted mean, all 30) |
| new (independent) | 28 | 13/28 (46%) | 21 | 5/21 (24%) | -1.61 (n-weighted, 18 rules with n≥100) |
| pooled | 34 | 34/34 (100%) | 30 | 0/30 (0%) | -1.225 (unweighted mean, all 30) |

**Regression check:** orig window reproduces July's headline exactly — 30/30
SELL rules negative-edge, 34/34 BUY rules positive-edge (July: same 30-of-30 /
34-of-34 split). No discrepancy here (unlike §B/§D above) — `drv_rule_outcome`
is frozen-at-firing-time, so it doesn't drift the way `drv_actionable`-derived
views do.

**New-half detail:** 9 of the original 30 SELL rules didn't clear `fires>=20`
in the shorter new window (dropped to 21). Of those 21, **5 flipped to
positive edge** (`789-SS-!Bull-OverBought` +4.32, `897-SW-Vlm-Spike-Price-Dn`
+2.94, `793-STM-!TD!Bull-TRR-Rev` +2.57, `783-SW-Vol-Spke-Price-Dn-Past`
+1.82, `698-SS-Bull-HighAbvTRR` +0.89), all on n≥65. **The remaining 16/21
(76%) are still negative**, several sharply so (`899-SA-Trend-Breaks` -5.30,
`894-SA-!Bull-TN-TRR` -8.28). Re-checked at a stricter `n≥100` floor (18 of
21 rules qualify): 14/18 (78%) still negative, n-weighted mean edge **-1.61%**
— slightly worse than the orig window's -1.31% unweighted mean, not better.

**Does the new period rehabilitate SELL rules, or hold?** Mostly **held**:
the SELL rule class is no longer *literally* 30-for-30 (it wasn't tested on
all 30 — 9 didn't reach the fire-count floor in the shorter window), but
among rules with enough fires to measure, ~76-78% are still negative-edge and
the n-weighted average edge is unchanged-to-slightly-worse (-1.31% → -1.61%).
The handful that flipped positive did so on more modest samples (65-1,249
fires) than the rules that stayed negative (up to 22,288 fires in the orig
window) — the negative-edge finding is backed by more data, not less.

**Verdict: HELD** (SELL rules remain net negative-edge as a class; not a
uniform 100% anymore, but the money-relevant conclusion — SELL rules lose
more than they win, on average and n-weighted — is unchanged). → Per
`AGENT_WORK.md`'s gate table, **TASK_141 may proceed.**

---

## F. Hit-threshold sensitivity (assumption A6) — brief re-check

Aggregate win rate across composite rules with `fires >= 100`, at the current
±0.5% hit threshold vs a stricter ±2%:

| window | n rules (fires≥100) | avg win rate ±0.5% | avg win rate ±2% |
|---|---|---|---|
| orig | 64 | 0.458 | 0.377 |
| new  | 43 | 0.440 | 0.353 |
| pooled | 64 | 0.459 | 0.377 |

Same pattern as July in both windows: win rates sit in the mid-40s at the
current threshold (barely better than a coin flip) and drop ~8-9 points at
the stricter ±2% bar, in both windows. **Verdict: HELD** ("weak, not fully
broken" — thresholds don't mean much in an absolute sense, but nothing here
suggests recalibrating would change which rules look good vs bad).

---

## Regime characterization

| metric | orig window (2026-02-02→06-11) | new window (2026-06-12→09-18) |
|---|---|---|
| SPX | 6,976.44 → 7,394.30 (**+6.0%**) | 7,431.46 → 7,650.50 (**+3.0%**) |
| VIX range | 15.32 – 31.05 (avg 20.09) | 14.23 – 20.66 (avg 16.46) |
| `drv_market_stat.risk_label` | (not queried — orig window predates some risk-label history) | CLEAR 64 days, CAUTION 14 days, 0 ALERT |
| `pct_above_sma200` (new window) | — | 48.9% – 67.2% |

**Is the new window a genuinely different regime, or more of the same
bounce?** **More of the same bounce, calmer.** SPX rose in both windows
(+6.0% then +3.0% — no drawdown or sustained chop), and VIX fell further
(avg 20.09 → 16.46, max 31.05 → 20.66) — the new period is a **continuation
of the up-trend at lower volatility**, not a different regime. **A5 (do
edges generalize beyond the original dataset) remains formally untested** —
this report is a same-regime replication with a calmer second half, not the
drawdown/chop period needed to prove or disprove generalization. Read every
HELD verdict above as "held across a bull-market extension", not "held
across regimes" — the FLIPPED findings (A1's `rr_bull_bear`, A3's SS
confidence badge) are the more interesting result precisely because they
flipped *without* a regime change, which argues these are noisier/more
fragile signals than their July numbers suggested, not that they need a
crash to fail.

---

## G. Verdicts (A1–A6 + gates)

| # | Assumption | Verdict | Evidence |
|---|---|---|---|
| A1 (ladder) | `bull` -3..+3 ladder correctly switches the playbook | **HELD (broken)** | Still inverted in both halves; gap widened in the new half (§A) |
| A1 (rr_bull_bear) | QP `rr_bull_bear` B/!B separates outcomes | **FLIPPED** | July: B beats !B (+2.59 vs +1.00). New half: !B beats B (+1.95 vs -0.30), both large-n (§A) |
| A2 | BM/BS conviction ladder ranks BM > BS | **STILL THIN / untestable** | BS/high n grew (2→29-100) but flips sign between windows (-9.33 orig, +4.24 new); regression-check n discrepancy explained (drv_actionable is live, not frozen) (§B) |
| A3 | SS/high beats SS/mixed (confidence ⇒ reliability) | **FLIPPED (new half)** | Orig reproduces July (SS/high wrong-signed); new half inverts, both n well past 30 (§B) |
| A4 (**TASK_140 gate**) | Fixed `SOURCE_ORDER` reflects real edge | **HELD (broken)** | RR best / PS worst in both halves, large stable-signed n; only ETF's sign is unstable, and it's the thinnest of the six (§C) → **TASK_140 may proceed** |
| SELL-side (**TASK_141 gate**) | SELL rules uniformly negative-edge | **HELD** | 76-78% of rules with enough new-half fires stay negative; n-weighted edge -1.31%→-1.61% (slightly worse, not better) (§E) → **TASK_141 may proceed** |
| §D headline | FOLLOWED underperforms CONTRADICTED and NO_SIGNAL | **HELD vs CONTRADICTED; FLIPPED vs NO_SIGNAL (thin, n=99)** | Core "don't follow your own signal" claim holds; NO_SIGNAL's relative ranking is noisy/thin (§D) |
| A6 | Hit thresholds ±0.5%/±2% are meaningful cutoffs | **HELD (weak)** | Win rates mid-40s / high-30s in both halves, same as July (§F) |
| A5 | Scorecard edges generalize beyond the original dataset | **NOT PROVEN — same regime, calmer** | New period is a continuation of the same up-trend at lower VIX, not a drawdown/chop (§Regime) |

**Gate outcome for this batch:** A4 = HELD → **TASK_140 released.** SELL-side
= HELD → **TASK_141 released.** Neither gate stopped.
