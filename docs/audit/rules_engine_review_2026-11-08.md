# Rules engine review - 2026-11-08

Read-only review. DB queries ran fine (SELECT only). Scripts are in the session scratchpad (`q1.py` to `q11.py`, helper `h.py`).
All edges below are UNCORRECTED (they use the old scorecard baseline, see DESIGN_SPEC_13 section 6).

## 1. Plain-English summary

- The rules engine runs every day and fires a lot. About 1,500 to 2,100 composite-rule fires per day, 43 to 50 different rules, across about 1,057 symbols.
- But it does not move the Final Call. Not once. In all 244,814 rows of `drv_actionable` (Jan 2025 to 2026-11-06), a rule group never won the action. No row has a `RULES:` winner or a `RULES:` entry in `source_actions`.
- Why: the groups speak "SA / SS / STM / SW / BW / BS / BR". The Final Call only accepts "REMOVE / REDUCE / INCREASE / ADD / HOLD" from sources. So the groups only fill the `trig_action` column. Nothing in the Final Call reads `trig_action`.
- The Final Call today = Sources (consolidated_action) + Technical (the redesigned Technical rules). The rules engine is a side display.
- The rules engine still has three small effects: the "Trig" column, a line in the "Why this action" card, and a low-confidence flag on sells (which only changes the display while `unproven_sell_mode` stays on `annotate`, as it is now).
- Quality is weak. Every BUY rule shows a positive edge and every SELL rule a negative one. That is just the market going up, not skill. The average stock gained +1.33% over 20 days in the same window. The typical BUY rule shows +1.1%, which is at or below that.
- All 30 SELL rules with at least 100 fires have negative edge. The price usually went UP after they fired. Examples: `899-SA-Trend-Breaks` -1.75 (n=17,824), `893-SA-TRR-blw-TN` -1.68 (n=18,727).
- Fix-or-retire advice: stop investing in groups, thresholds and tuning. Keep the data, the Rule Flow trace and the scorecard as a read-only "evidence" tool, and consider dropping the rest.

## 2. Findings table

| # | Finding | Number | Source |
|---|---|---|---|
| 1 | Atomic rules | 115 total, 0 deprecated; 69 used by composites, 46 used by none | `ref_trig_atomic_rule`, mapping |
| 2 | Composites | 69 (487 member rows, all atomic members), 0 deprecated, 0 inactive | `ref_trig_composite_mapping` |
| 3 | Rule groups | 9 (all type `action`, 0 deprecated); 2 are test groups (`TEST-SA-GROUP`, `INTEG-TEST-GROUP`); 61 group members, all composites | `ref_trig_rule_group` |
| 4 | Composites in no group | 11 of 69 | member table |
| 5 | Active param set | `Baseline 2026-06-05` (id 1). Two others inactive: `Sigmoid v1` (id 2), `ml-sweep-20d` (id 3, 96 rules tuned). None validated, no holdout edge recorded | `ref_trig_param_set` |
| 6 | Daily fires (last 60 calendar days = 41 derive days, 2026-09-08 to 2026-11-06) | 1,462 to 2,134 fires/day; 43 to 50 composites firing/day; about 1,057 symbols scored/day. 52,445 non-BASE fires in the window | `drv_trig` |
| 7 | Composites never fired | 9 of 69 in last 60 days; 6 of 69 in last 180 days (`187-BR-NoTN-NoTD-UP-MACD-DAY`, `278-BS-BB-HL-HiHi`, `298-BS-BB-HL-HiHi-TN-TD`, `798-STM-!Bull-TRR-Rev`, `859-SS-Bull-BBTh-Crossover-RSI-IVHV`, `888-STM-!Bull-BBTh-Crossover-RSI-IVHV`) | `drv_trig` |
| 8 | Barely fire (60d) | `96-BW-RSI-IVHV-Min` 9, `97-BW-TD-RSI-IV` 8, `857-...-RSIOnly` 6, `787-SS-Bull-TRR-Rev` 3, `792-STM-...` 2, `889-STM-OverBought` 1, `197-BS-TN-LRR-UP-DAY` 1 | `drv_trig` |
| 9 | Rows per day with a fired group | avg 498 of 1,089 rows (46%); with trig_action 498 | `drv_actionable`, 41 days |
| 10 | Groups that won the Final Call | 0 of 244,814 rows. `RULES:` never in winning_source or source_actions | `drv_actionable` |
| 11 | Rows with no source action but a trig_action | avg 329 per day (these show a Trig label but the Final Call is HOLD) | `drv_actionable` |
| 12 | trig_action vs final_code on 2026-11-06 | e.g. trig BS: 215 of 238 end as HOLD; trig SA: 97 of 98 HOLD; trig SW: 85 of 90 HOLD | `drv_actionable` |
| 13 | trig_action vs Technical action (2026-11-06) | Poor agreement: trig BS rows have Technical -10 (sell all) on 74 of 239; trig SW has Technical +10 on 12 of 90 | join to `drv_tn_td_bb_rr` |
| 14 | Group fire counts since 2026-09-08 | GROUP-BS 16,441; STM 5,889; SS 4,382; SA 3,287; BW 2,978; SW 2,063; BR 580; INTEG-TEST-GROUP 556 (a test group is still firing in live data) | `drv_actionable` |
| 15 | Outcomes freshness | `drv_rule_outcome` ends 2026-10-07 (about a month stale); covers 178 dates, 1,009 symbols, 98 atomic + 69 composite rules; 12.8M atomic rows, 1.35M composite rows | `drv_rule_outcome` |
| 16 | Scorecard | 64 rules (34 BUY, 30 SELL), all with n >= 100. All 34 BUY positive, all 30 SELL negative | `v_rule_scorecard` |
| 17 | Edge vs the real market | Average 20d move of all fired rows 0.97%; all stocks 1.33% (median 0.0%). BUY edges sit around +1.1, so about the market. This is the "uncorrected" label | `drv_factor_snapshot` |
| 18 | Unproven sells | 30 SELL composites flagged by `v_unproven_sell_rules`; 322 of 1,092 rows on 2026-11-06 carry `low_confidence`; mode = `annotate` (display only) | view, `ref_settings` |

## 3. Quality detail (uncorrected edges, 20-day, 2026-02-02 to 2026-10-07)

Edge here = average 20-day forward return, sign-flipped for SELL rules. It is not net of the market. A true edge should be measured against about +1.33%.

Best by edge (all BUY):

| Rule | n | Edge |
|---|---|---|
| `52-BS-BRR` | 39,114 | +1.98 (about +0.65 over the market, the only clear standout) |
| `188-BR-TNabvTD-UP-MACD-DAY` | 16,953 | +1.26 |
| `189-BR-BB-LoHi` | 15,577 | +1.12 |
| `187-BR-NoTN-NoTD-UP-MACD-DAY` | 15,377 | +1.12 (stopped firing 2026-05-30) |
| `278-BS-BB-HL-HiHi` | 15,378 | +1.12 (stopped firing 2026-05-30) |
| `99-BS-Min` | 22,810 | +1.10 |

Worst by edge (all SELL, price kept rising):

| Rule | n | Edge |
|---|---|---|
| `899-SA-Trend-Breaks` | 17,824 | -1.75 |
| `893-SA-TRR-blw-TN` | 18,727 | -1.68 |
| `697-STM-Earnings-Date` | 17,430 | -1.59 |
| `898-SA-Streak-VeryBad` | 20,994 | -1.53 |
| `784-SS-Streak-GoingBad` | 20,024 | -1.41 |
| `896-SA-TRbelowTN-Trade-Breaks` | 16,959 | -1.35 |
| `785-SS-Trade-Breaks` | 18,026 | -1.30 |
| `699-SW-Resistance` | 8,083 | -1.27 |

Consistently negative with n >= 100: 30 of 64 rules, every one a SELL (0 BUY). Their win rates are 42.6% to 46%.

Cautions: many rules show nearly the same n (about 15,376 to 15,410) and the same edge (about 1.12). They are close to the same fired rows counted under different names. One fire is one symbol-day, so neighbouring days overlap heavily and the real sample is far smaller than n. The window is one rising market (Feb to Oct 2026). These numbers cannot separate skill from drift.

## 4. Redundancy with the redesigned Technical rules (code reading, `etl/technical_rules.py`)

- The Technical rules (Step 1 Trade/Trend lines, Step 3 LRR-TRR range) produce the same action codes as the rule groups: SA -10, STM -9, SS -8, BMN 8, BS 9, BM 10. That is the same vocabulary as `trig_action`.
- Technical feeds the Final Call (`rr_action` in `_compute_final_call`). The rules engine does not.
- By rule name, about 48 of 64 non-BASE composites are about Trade/Trend, Bollinger bands, LRR/TRR or streaks (rough name match, not exact). About 27,000 of 52,000 fires in 60 days are in that family. They are the ones Technical now covers.
- Strongly overlapped: all 5 SA composites in `GROUP-SA` (Trend-Breaks, Trade-Breaks, TRR-blw-TN, Streak-VeryBad, TN-TRR), the SS/STM Trade-Breaks and TRR family, and BS/BR/B-TN-TD-LRR family (`394` to `449`).
- Not covered by Technical: Earnings-Date (`697`), Resistance (`699`), Volume-spike (`783`, `897`), RSI/IV combos (`92`, `96`, `97`, `98`), 3-month high (`268`, `782`).
- The BASE-* sub-composites (`BASE-Bull-Context` 11,313 fires, `BASE-Bull-Trend`, `BASE-RR-Position`) are building blocks, not decisions.
- Other consumers that still use rule data: the factor-edge tags, the Rules (edge) grid column, the signal-winrate tool (`etl/derive_signal_winrate.py`) and `low_confidence` (annotate only).
- Safe to delete now: `TEST-SA-GROUP`, `INTEG-TEST-GROUP` (still firing, 556 hits), the 6 never-fired composites, and the 46 atomic rules no composite uses (check each first for outcome history use).

## 5. Keep / fix / retire

| Item | Verdict | Why |
|---|---|---|
| Rule Flow (`/rule-flow`) | KEEP | Linked from the Rules cell on Actionable; shows the data-flow trace. Useful as an explainer. |
| Rule Performance (`/rule-performance`) | KEEP, fix first | Also holds "Your actions" and the factor scorecard. Fix the baseline bug (DESIGN_SPEC_13) and refresh the outcomes job (stale since 2026-10-07). |
| Trace (`/trace`) | KEEP (optional) | Debugging only; low cost. |
| Trig (`/trig`) | RETIRE or fold into Rule Flow | Raw `drv_trig` view; nothing decides on it. |
| Rules (`/rules`) | RETIRE from daily use | Editing thresholds changes a display that does not drive the Final Call. Keep read-only. |
| Rule Groups (`/groups`) | RETIRE | Groups never win. Only 9, 2 are test groups. |
| Composite edit (`/composite-edit`) | RETIRE | Same reason as Rules. |
| Param sets (`/param-sets`) | RETIRE | One active set (June baseline), the ML sets unvalidated, no holdout. Tuning the rules engine cannot change the Final Call. |
| Rules health (`/rules-health`) | RETIRE (or merge into Rule Performance) | Health of a non-decision layer. |
| Daily derive of `drv_trig`/`drv_stks` groups | KEEP for now | Cheap and feeds Rule Flow, edge badges, low-confidence flag. Stop adding rules. |
| Test groups and 6 never-fired composites | RETIRE | Dead weight, zero effect. |
| Unproven-sell flag | KEEP as annotation | Honest warning that sell rules lost. Do not flip to `suppress` until the baseline is fixed. |

## 6. Questions for you (max 5)

1. Do you want the rules engine to ever drive the Final Call? Recommendation: no. Technical + Sources already do, and the rules show no edge over the market. Treat the engine as an evidence display only.
2. Retire the editing screens (Rules, Rule Groups, Composite edit, Param sets, Health) and keep Rule Flow, Rule Performance and Trace? Recommendation: yes, hide them from the menu first, delete code later.
3. Delete the 2 test groups, 6 never-fired composites and the 46 unused atomic rules? Recommendation: yes for the test groups and never-fired composites now; leave atomics until we confirm outcomes history does not depend on them.
4. Fix the scorecard baseline (market-relative, trading-day forward counts) before judging any rule further? Recommendation: yes, one fix covers `v_rule_scorecard` and `v_factor_scorecard`. Also restart the outcomes job (stale since 2026-10-07).
5. Keep `trig_action` in the grid and the Why card? Recommendation: hide the Trig column (it disagrees with Technical on many rows and 90+% end as HOLD) but keep the Rule Flow link.

## 7. Supporting numbers and how to reproduce

- Windows: "60 days" = 2026-09-08 to 2026-11-06 (41 derive days); "180 days" = 2026-05-10 to 2026-11-06 using calendar days from max `drv_trig` date.
- `drv_trig` and `drv_stks`: 199 dates, 2025-01-01 to 2026-11-06. `drv_actionable`: 210 dates, same range.
- Scorecard edge definition (from the view): average of `fwd_20d_pct`, negated for rules not starting with a BUY prefix; excludes BASE-*; CI from sd/sqrt(n). No market subtraction. This is the baseline problem.
- Market reference: `drv_factor_snapshot`, 149,482 rows 2026-02-02 to 2026-10-07: mean 20d return +1.334%, median 0.0%, 13,845 rows (9.3%) exactly zero (frozen prices). Even this reference is bent by the same zero-return bug.
- Not measured: individual atomic-rule fire counts (not stored per atomic per day, only as ids in `drv_stks.triggered_atomic_ids`: 639 of 1,057 rows on 2026-11-06 had at least one). Rule-by-rule win-rate after market correction (needs the fixed baseline).
- Scripts: `C:\Users\chash\AppData\Local\Temp\claude\d5a64e5c3aad2de4\7ea80ca9-80e2-4f3f-8b2d-bf45442f4115\scratchpad\q2.py` (usage), `q4.py` (group vs Final Call), `q6.py` (scorecard), `q9.py` (trig vs Technical), `q10.py` (inventory).
