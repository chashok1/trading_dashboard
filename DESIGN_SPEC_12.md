# Design Spec — DESIGN_WORK_12

## Goal
Make the Final Call, the Tradability Score, Trade / Trade2 and every other Actionable column tell one story, count each
fact once, and keep only what earns its place. Used by: you, when picking today's buys and sells on the Actionable screen.

## Design

### 1. Plain-English summary (one page)

**What we found**

1. **The score mostly repeats the Final Call.** Seven things go into the 🎯 Tradability Score. Three of them say
   nothing new on a BUY row:
   - "Technical is a buy" (+2) is true for 97 of every 100 rows that reach Trade. The Final Call and the Trade test
     already require it.
   - "Agreement" counts Technical and Sources again. Both are always "yes" on a BUY, so Agreement really just means
     "MACRO also says buy". That is worth +3 or +6 points.
   - RSI and Volume give almost every stock the same +3.7 and +3.1. That happens because of a mistake in the
     "baseline" they are compared with (see Bugs). Together with the +2 above, they fill the 8-point cap for 4 of
     every 5 rows.
2. **So the score is really a two-question test.** Is price near the bottom of its range, and does MACRO say buy?
   In our data:
   - MACRO says buy → 74–90% of rows pass anywhere above LRR, even above the top of the range.
   - MACRO does not say buy → a row passes only if price is in the bottom quarter of the range.
   The only things that knock a row down are a weak-record source (TOP5, PS, MACROSHOW) or an IV spike.
3. **It argues with Technical.** The new Technical rules (since 23 Oct) buy on purpose after a bounce from the LRR
   zone, while price is 25–60% up the range. The score gives those buys zero range points. TXG is one of these: BUY
   MORE at 56% of its range, MACRO HOLD, TOP5 source, so its score is about 6–9. On 20 and 22 Oct, at 27% and 12%,
   the same BUY MORE was in Trade. It moved to Trade2 because the price rose 8%, not because anything got worse.
4. **It does not predict returns.** We checked about 7,700 BUY rows from 2 Feb to 29 Sep 2026, scoring each
   against the average stock 20 days later:
   - A higher score did no better. The link between score and outcome is zero (0.01).
   - Trade buys: 1.9% behind the average stock (median), 42% wins.
   - Trade2 buys: 1.4% behind (median), 50% wins.
   - Neither list beat the average stock. Trade did not beat Trade2.
   - The Final Call's own buy codes are flat too.
5. **Two parts point the wrong way.**
   - **IV:** stocks whose IV was below their own normal (+3 points) did worst: 1.8% behind the average, 28% wins
     (1,030 rows). Spiked IV (−3 points) did best, but that is only 35 rows.
   - **PVV BUY_DIP:** it is pushed to the top of the buy list, but across all stocks it did worse than average (36%
     wins against 46%, 520 rows, 265 stocks).
6. **The same fact shows up many times.** Where price sits in its range is used in six places:
   - Technical
   - the score (10× weight)
   - the "Caution: at TRR" warning
   - PVV
   - the LIVE chase/trim lines
   - the RR column
   Each uses its own cut-off. The winning source's track record shows four times. Some columns say opposite things
   about the same stock:
   - **Volume:** the popup lists a high-volume up day as a caution, but the Tradability box colours the same line green.
   - **IV:** the IV column's tag praises high IV, but the caution warns about it.
   - **RSI:** a neutral RSI counts as "helping" in the score, but the popup calls it "no read".
7. **BUY rows that are in no list.** On 28 Oct, 10 rows show a BUY badge but are in neither Trade nor Trade2. The
   reason is that MACRO says sell (examples: KO, PEP, UNH). Nothing on the badge says so.

**What we recommend (Option C+E)**

- **Retire the 🎯 number.** Show a plain **Entry** label instead, based on one thing only: where price sits in its
  range right now. This is the only part with a steady (small) signal in the data.
  - The bottom quarter did best.
  - Below LRR and above TRR did clearly worst.
  - The label uses the same "LRR zone" setting the Technical rules use, so the two can't disagree.
- **Rename the buttons.**
  - **Trade → "Buy now":** BUY calls whose price is in the LRR zone.
  - **Trade2 → "Pullback":** the same BUY calls with price higher up. Each row shows the price to wait for, and you
    can set a 🔔 alert for that price.
- **The Final Call does not change.** This changes labels, list membership and sort order only.
- **Each fact gets counted once.**
  - MACRO stays a veto but gets no bonus points. When it vetoes, the BUY badge says so ("MACRO says no").
  - The PVV AVOID veto and the BUY_DIP top-of-list boost go.
  - RSI, IV-spike and volume-climax stay as plain cautions in the popup. They are not scored.
- **Fewer columns by default.**
  - Hide MACD, MACDH and PVV. PVV's icon stays inside ACTION.
  - Make the IV cell show the "vs own average" number the caution uses.
  - Take CALC, P(↑20d) and Agree out of the menu until a model is switched on.

**Be clear about this.** None of the buy-side layers has beaten the average stock in this history:
- the Final Call
- the score
- Trade
The new split will not change that. What it does is make the screen honest and simple. See "Worth reconsidering".

### 2. Decisions for you (full list under Open questions)

1. Replace the score with the Entry label and re-cut Trade / Trade2 as "Buy now" / "Pullback"? **Recommend yes.**
2. "Buy now" width = the Technical's own LRR zone (bottom 25% of the range)? **Recommend yes.**
3. MACRO: veto only (no bonus points), with a "MACRO says no" pill on vetoed BUY badges? **Recommend yes.**
4. PVV: drop the AVOID veto and the BUY_DIP top-of-list boost; keep the PVV icon? **Recommend yes.**
5. Columns: hide MACD / MACDH / PVV by default, IV cell shows "vs own average", hide CALC / P(↑20d) / Agree from the
   menu? **Recommend yes.**
6. Keep your "BUY TO MIN only above the Trade line" rule in "Buy now"? **Recommend keep** (data is neutral).

### 3. Inventory: every input for one BUY row and where it is used

Key: **FC** = Final Call (`final_code`), **Score** = Tradability Score, **Gate** = Trade / Trade2 test,
**Sort** = default sort, **Show** = shown only. "×n" = counted that many times.

| Input | FC | Score | Gate | Sort | Shown elsewhere |
|---|---|---|---|---|---|
| Technical code (`rr_action`, Steps 1 / 3) | yes, required for a buy (RTA exempt) | +2, plus the Technical leg of Agreement | must be BS / BM / BMN (RTA exempt); Watchlist gate | through the score | Technical column, Why card, "Tech buy" tag |
| Range position (LRR–TRR %) | inside Technical Step 3 (25% / 60% / 90% bands) | 10× term (0–40% taper) | through the score | through the score | RR column + pills, "at TRR" caution, PVV `at_lrr`, LIVE chase tag / trim lines |
| Trade / Trend lines | Technical Step 1 | no | stop-breach veto; BMN must be above Trade | Tier 0 (stop) | AMT$ stop sub-line, ▼TD / ▼TN pill, Technical Td/Tn arrows |
| Sources call (`consolidated_action`) | yes, the main input | Sources leg of Agreement (always yes on a buy) | through FC | no | Sources column |
| Winning source | sets BMN vs BM / BS; RTA bypass | win-rate term (−3..+6) | RTA exempt from Technical | through the score | Source line in popup, hit-rate badge (Trade view), "source underperforms" caution |
| MACRO (`macro_action`) | **no** | MACRO leg of Agreement (+3 / +6) | veto if SA / STM | through the score | MACRO column, "Sector is Bear" caution (same table) |
| PVV decision | no | no | veto if AVOID | BUY_DIP +2000 (always); other PVV buys +1000 in Trade | PVV column, icon in ACTION |
| RSI | no | +3.7 neutral / +6 oversold / +0.3 overbought | through the score | through the score | RSI cell edge tag, caution / support line, "no read" line |
| RVOL + direction | no | +3.1 normal / +2.6 high-up / +6 high-down | through the score | through the score | Vlm cell, "buying climax" caution, PVV volume |
| IV vs own 63-day average (`iv_ratio`) | no | −3 / 0 / +3 | through the score | through the score | "IV spiked" caution; **not shown in the IV cell** |
| IV percentile | no | no | no | no | IV cell + edge tag |
| Stop breached | no (removed 26 Oct) | no | veto on buys; held breaches shown in Trade | Tier 0 | stop pill, LIVE blocks buys |
| Macro instrument (index / futures / FX) | no | no | excluded from Trade | no | — |
| Fixed income | no | no | Trade2 only | no | hidden in normal view |
| Fired rules + edges | rule groups feed Sources | no | no | buys: 0.01 tiebreak; HOLD / Watchlist / Bottom tiers: main key | Rules (edge) column, popup caution / support |
| `trig_action` | no | no | no | sell sub-rank 1a / 1b only | not shown (column retired) |
| Final Call code (BM / BS / BMN) | — | no | must be BM / BS / BMN | BM +500, BS +250 (beats the whole score range) | ACTION badge |
| Held / position $ | held vs not-held rules | no | held sells / stops | $ tiebreaks, sell tiers | POS$, AMT$ |

### 4. Every grid column: what it shows and what it drives

Columns in screen order. "Decides" = changes the Final Call, the Trade lists or the default sort. "Display" = shown only.

| Column | Shows | Comes from | Role | Keep? |
|---|---|---|---|---|
| 🔭 LT | your long-term Hold / Avoid note | `ref_conviction_hold` → `drv_actionable.conviction_*` | Display. Rings the ACTION badge on a conflict. LIVE blocks live buys on Avoid | Keep |
| 🔔 Watch | your price / line alert | `ref_watch` (live join) | Display / alerts | Keep. Becomes the "tell me at the pullback price" tool |
| ☐ bulk | select | — | tool | Keep |
| H | why a row is hidden | client filter | Display | Keep (only when "show hidden") |
| POS$ | held $ (per account) | `hist_cs / hist_f` via `drv_actionable` | Decides (held vs not held) | Keep |
| AMT$ | suggested buy / sell $; stop sub-line | sizing; `stop_signal` | Decides (sort $; stop veto) | Keep |
| %CHG | candle, % move, price, day range | `drv_quote` | Small inputs (score "turning up", RVOL direction, Technical "up day") | Keep |
| Symbol | name (coloured by outlook), NEW pill, 🎯 badge, hit-rate badge (Trade view), action tag | outlook; score; source scorecard | 🎯 decides Trade / Trade2 and the buy sort | Keep. **🎯 → Entry pill** |
| ACTION | Final Call badge + pills: PVV icon, LT ring, Tech buy, stop, earnings, ⚠ / ▲ signals, OVER MAX, sizing, LOW CONF | `drv_actionable.final_*` + client | **The decision** | Keep. Add "MACRO says no" pill |
| MACRO | quad-regime stance by sector / asset / style | `drv_macro_score` | Decides (Trade veto + score points) | Keep (veto only) |
| PVV | Price / Volume / Volatility decision | `drv_pvv` | Decides (veto, sort boost) | **Hide by default.** The icon stays in ACTION |
| LIVE | today's price vs last night's plan lines | `hist_advice_plan / live` | Display + Act (N) chip + Today's panel. Never changes FC | Keep |
| RR | range bar, %, LRR / TRR pills | `drv_rr` + price | Decides (score 10×, Technical Step 3) | Keep. Becomes the Entry source |
| Vlm | RVOL dot, volume trend | `drv_technicals` | Score term + caution | Keep (display) |
| IV | IV percentile / HV / IV + percentile edge tag | `drv_technicals`, `drv_quote` | Display (score uses `iv_ratio`, not shown here) | Keep. **Add "×own avg"**, drop the percentile edge tag |
| MACD | MACD value + caret | TOS custom study | Display only. Used by nothing | **Hide by default** |
| MACDH | MACDH value + caret | TOS custom study | Display only. Measured edge is flat (49.5% vs 50.1%) | **Hide by default** |
| RSI | RSI + edge tag | `drv_technicals` | Score term + caution | Keep (display) |
| CALC (hidden) | calibrated call | `ref_bull_model` (no active model) | All dashes | **Remove from menu** until a model is on |
| Sources | consolidated call + per-source lines | `drv_outlook_action` → `drv_actionable` | **Decides FC** | Keep |
| Technical (TrTnBBRskRng) | Technical code, Td / Tn arrows, sub-lines | `drv_tn_td_bb_rr` | **Decides FC** + gate | Keep |
| Rules (edge) | fired composite rules + edges | `rules_engine_fires`, `v_rule_scorecard` | Decides the HOLD-tier sort; popup cautions | Keep |
| P(↑20d) (hidden) | model probability | inactive model | All dashes | **Remove from menu** |
| Agree (hidden) | model vs call agreement | inactive model (`v_agreement_scorecard` has 0 rows, confirmed) | All dashes | **Remove from menu** |
| Act (N) chip / Today's panel | LIVE tiers | `hist_advice_live` | Display / filter | Keep |
| Trig | — | `trig_action` | Not a column since TASK_109. Sell sub-rank only | No change |

### 5. Double counting and overlap (what, how bad, what to do)

| # | Same evidence | Kind | Size (data) | Fix |
|---|---|---|---|---|
| D1 | Technical buy: FC requirement + Trade gate + score +2 + Agreement leg | **True duplicate** (×4) | 96.6% of Trade candidates have it, so +2 is a constant | Drop from the score (the score is retired) |
| D2 | Sources buy: FC + Agreement leg | **True duplicate** | always yes on a buy | Same |
| D3 | Agreement = effectively the MACRO vote; MACRO also a veto | Counted twice inside Trade (veto + points); FC ignores MACRO | Among Trade candidates: MACRO buy beat MACRO HOLD by about 1.5 points (−0.56 vs −2.09). Across all stocks, MACRO BM / BS sit *below* baseline (41% / 45% wins vs 46%). **Mixed, unproven** | Veto only + visible pill |
| D4 | Range position in 6 places with different cut-offs (Technical 25 / 60 / 90%; score 0–40% taper; caution ≥80%; RR pill ≤15%; PVV `at_lrr`; LIVE chase ≥90%) | Correlated views that **disagree** | Technical 3x buys: half get 0 range points; 3h buys: all get 0 (28 Oct, n=394 / 36) | One Entry label from the Technical's own zone setting |
| D5 | Volume: score +2.6 (green) vs "buying climax" caution, same row | **Contradiction** | High-RVOL up day = 48.8% wins vs 46.2% "baseline" | Caution only, never scored |
| D6 | IV: cell shows percentile (tag praises high IV); score + caution use `iv_ratio` (spike = bad) | **Contradiction** + backwards term | Since 15 Aug, ratio < 1 (+3 pts) = −1.81 excess, 28% wins (n=1,030, 184 stocks); spike = +9.5 (n=35, 14 stocks, small) | Show the ratio in the cell; caution only |
| D7 | RSI neutral: +3.7 "helping" in the score vs "no read" in the popup | **Contradiction** (baseline bug) | Neutral = 49.9% wins vs 46.2% baseline | Caution / support only |
| D8 | PVV: ACTION icon + Trade veto + sort boost | Overlaps range (`at_lrr`) + RR outlook (a source) | The AVOID veto removed 6 rows ever, all already failing the score. BUY_DIP across all stocks: 36% wins vs 46% (n=520 / 265) | Drop the veto and the boost; keep the icon |
| D9 | Stop (price below Trade / Trend line): AMT$ line + pill + Trade veto + Tier 0 + LIVE block | Same facts as Technical Step 1 | You removed it from FC on 26 Oct for this reason | Keep the veto on *buys* (a buy on a broken stop reads wrong), keep Tier 0. No change |
| D10 | Final Call code inside the sort: BM +500 / BS +250, larger than the whole score range | Not a duplicate, but the score only orders rows *within* one code | — | New sort order (section 7) |
| D11 | Source track record: score term + hit-rate badge + popup Source line + "underperforms" caution | Shown ×4, scored ×1 | TOP5 buys: 28% wins (ADD n=253). PS 37%. SSS 47–53% | Show in the Sources line + badge only |
| D12 | MACRO vs Quad vs Area: MACRO column + "Sector Bear" caution (same `sector_stance`) + Area headwind caution | Correlated | — | Leave the cautions; they are labelled. No new work |
| D13 | Rules: rule groups → Sources (FC); composite rules → Rules column + popup cautions + HOLD-tier sort; `trig_action` → sell sub-rank | Correlated-but-different | — | No change |
| D14 | LIVE vs Final Call: LIVE dip-buy can fire on a HOLD row; LIVE "Chase" can tag a Trade buy | Intended add-on | Chase on Trade buys is now rare (new Technical buys stop at 60%) | No change. LIVE stays separate by your rule |

### 6. The three layers today: counts and outcomes

Data: `drv_actionable` buy-side Final Calls. Score and gates were rebuilt in Python with the same rules as
`web/actionable_pops.js` / `web/actionable.js`, using today's scorecards. Forward returns come from
`drv_factor_snapshot` (2 Feb – 29 Sep 2026). "Excess" = 20-trading-day return minus that day's average over all
stocks. Read-only queries were run on 28 Oct 2026.

**Rows per day**

| Period | Trade | Trade2 | BUY in no list | Watchlist |
|---|---|---|---|---|
| Feb–Sep (all) | 7.6 | 10.6 | 43.5* | 92 |
| 1–22 Oct | 11.4 | 7.1 | 3.5 | ~95 |
| 23–28 Oct (new Technical) | 14.0 | 16.2 | 6.8 | ~96 |

\*Before 12 Sep a buy did not need Technical, so older "no list" rows are mostly an older rule. October is the
fair picture. On 28 Oct all 10 "no list" rows were MACRO SA / STM vetoes.

October scores are approximate: RSI comes from the raw value and Volume is assumed "normal" (+3.1), because the
factor snapshot ends on 29 Sep.

**Outcomes, Feb–Sep** (rows with a 20-day result)

| Bucket | Rows | Stocks | Mean excess | Median excess | Win rate |
|---|---|---|---|---|---|
| Trade | 877 | 197 | −0.92% | −1.89% | 42% |
| Trade2 | 1,409 | 261 | −1.50% | −1.39% | 50% |
| BUY in no list | 5,426 | 370 | −0.77% | −1.22% | 49% |
| Watchlist | 13,197 | 420 | +1.48% | −1.31% | 48% |
| *First day per stock only:* Trade | 197 | 197 | −0.72% | −1.98% | 42% |
| *First day per stock only:* Trade2 | 261 | 261 | −1.07% | −1.32% | 49% |

Since 15 Aug (the score in its current shape): Trade −0.86% (n=576, win 36%), Trade2 +0.64% (n=275, win 30%).
That is too short and too overlapping to read anything into.

**Score bands** (Trade candidates, Feb–Sep): <0 −8.6% (n=10, too small); 0–6 −0.99% (n=50); 6–12 −1.66% (n=796);
12–16 −1.02% (n=1,080); 16+ −1.04% (n=350). The bands are flat. The rank link between score and excess is **0.011**
(n=7,720). By term: range +0.022, source +0.034, agreement +0.007, IV **−0.098** (backwards).

**Final Call itself** (`v_final_call_scorecard`, edge over 20 days): BM / high +0.17% (n=1,117), BMN / high −0.14%
(n=2,500), BS / high −0.10% (n=148).

**Technical buy steps** (`drv_signal_winrate`, 15 days, 2 Feb – 27 Oct): 3x 46.9% up (n=12,300), 3f 47.1% (5,005),
3h 44.8% (2,543). All are close to a coin flip.

**Answer to "does the score earn its weight?"** No. A high score did not beat a low one, and Trade did not beat
Trade2. The range term alone shows a small, steady pattern (below), and that is what we keep.

**Caveats.**
- These are 8 months in mostly a rising market.
- One stock appears on many days, so the real sample is much smaller than the row counts.
- History used the Technical rules of the time, not the 23 Oct rules.
- Scorecard weights are in-sample. That flatters the score, and it still shows nothing.

### 7. Recommendation: Option C+E, "Entry label, Buy now / Pullback"

**Options considered**

| Option | On screen | Code | Risk | You give up |
|---|---|---|---|---|
| A. Keep, document | none | docs only | Contradictions stay. TXG-type rows keep confusing | nothing |
| B. Strip duplicates from the score (keep range, RSI, IV, volume, source) | same 🎯 | score function | The rest has no proven edge; IV is backwards | little |
| **C+E. Entry label + Buy now / Pullback** (recommended) | 🎯 → Entry pill; buttons renamed; popup Entry box | gates, sort, popup, Universe, export | Low. Advisory only; FC untouched | a number to sort by (replaced by range %) |
| D. Fold into the Final Call, retire the score | FC changes (e.g. BUY MORE → HOLD when high in range) | `derive_actionable.py` | **Changes `final_code`, needs approval**; repeats Technical's own range rule | the separation "what" vs "when" |
| E alone. Rename only | buttons renamed | labels | the score still decides | — |

**Why C+E:**
- It answers the one question the Final Call doesn't: "now, or wait?"
- It uses the same range setting as Technical, so Technical and Entry can't disagree.
- It turns Trade2 into something you can act on: a price to wait for, plus a 🔔 alert.
- In the data, "Buy now" rows did a little better than "Pullback" rows:

| Zone (Trade candidates, no index, no fixed income) | Rows | Stocks | Mean excess | Median | Win |
|---|---|---|---|---|---|
| Buy now (0–25%) | 440 | 181 | −0.38% | −1.65% | 46% |
| Pullback (25–60%) | 1,083 | 242 | −1.59% | −1.95% | 46% |
| Stretched (60–80%) | 286 | 133 | −1.05% | −0.36% | 51% |
| At / above TRR (>80%) | 128 | 86 | −2.32% | −2.59% | 41% |
| Below LRR | 39 | 30 | −3.64% | −4.28% | 33% |

The first-day-per-stock results show the same order: Buy now −0.82% vs Pullback −1.20%. The two ends are clearly
worst. On 23–28 Oct there were 4–8 "Buy now" rows a day and 16–34 "Pullback" rows a day.

**On screen**

Symbol cell (replaces 🎯 or the number):
```
 TXG            ABNB
 [Pullback]     [Buy now]
```
Pill colours:
- "Buy now": green (`--act-buy` fill)
- "Pullback": amber outline
- "Stretched": grey outline
- "Below LRR": red outline
- "No range": grey dash

ACTION cell when MACRO vetoes a buy (new pill, same row as the other pills):
```
 [ BUY MORE ]
  MACRO no
```

Toolbar buttons:
```
 [Buy now 14]  [Pullback 16]  [WL 96]
```
Hover text, as bullets:
- Buy now:
  - BUY calls with price in the bottom quarter of its range (the LRR zone)
  - Also: sells on held positions and broken stops
- Pullback:
  - The same BUY calls, but price is higher up the range
  - Each row shows the price to wait for
  - Set a 🔔 alert to hear when it gets there

Action popup: the **Entry** box replaces the Tradability box.
```
 Entry: Pullback
 • Price 84.41 is 56% up its range (LRR 67.51 – TRR 97.74)
 • Buy-now zone ends at 75.07 (LRR + 25% of range)
 • Today: up 8.2%
 • Cautions (not scored):
     – IV 1.17x its own 63-day average (above 1.15x)
 [ 🔔 Alert me at 75.07 ]
```
Popup wording by label (first bullet):
- Buy now: "Price is in the LRR zone, the Technical buy zone."
- Pullback: "Price is above the LRR zone. Waiting for a dip to {price} gives a better entry."
- Stretched: "Price is near the top of its range (TRR zone). Buying here has done worst."
- Below LRR: "Price is under LRR. Wait for a close back above {LRR}."

The Tradability "+pp vs baseline" lines are removed. The source's record stays on the popup's Source line.

Legend / header tooltip for the Entry pill (bullets):
- Where price sits in its LRR–TRR range right now
- Buy now = bottom 25% (the same zone the Technical rules use)
- Pullback = above that, below the TRR zone
- Stretched = in the TRR zone (top 20%)
- Below LRR = under the range
- Never changes the Final Call

**Default sort, buys (Tier 2):**
1. Entry group: Buy now → Pullback → Stretched → Below LRR → No range.
2. Final Call code: BM → BS → BMN.
3. Range % (lower first).
4. $ at stake.

The PVV boosts are removed (Q4). Other tiers are unchanged.

## Rules & numbers

**Entry label** (per row; `pos` = (last − LRR) / (TRR − LRR) × 100, not clamped)
- **No range:** LRR or TRR is missing, or TRR ≤ LRR. The row shows a grey dash. It is never "Buy now".
- **Below LRR:** pos < 0.
- **Buy now:** 0 ≤ pos ≤ 100 × `range_lrr_zone_pct`. That setting is 0.25 today, the same one Technical Step 3 uses.
- **Pullback:** above "Buy now" and below 100 × (1 − `range_trr_zone_pct`). That setting is 0.20 today, the same one
  the "at TRR" caution uses.
- **Stretched:** pos ≥ 100 × (1 − `range_trr_zone_pct`).
- **Pullback price** = LRR + `range_lrr_zone_pct` × (TRR − LRR), rounded to the cent.
- **Stale price:** use the same `last_price` the RR column uses, so the label always matches the bar.
- **Ties:** a value exactly on a boundary goes to the lower (better) group.

**Buy now list** (replaces `_isTradeModeQualifyingBuy`). The row must meet all of these:
- Final Call is BM, BS or BMN, and feasible.
- Technical is BS, BM or BMN, or the winning source is RTA.
- Stop not breached.
- MACRO is not SA or STM.
- Not an index, futures contract or FX pair.
- Not fixed income.
- A BMN row must be above its Trade line (your rule, kept; data is neutral: above −0.96% vs below −1.36% excess, win
  33% vs 57%).
- Entry = Buy now.

Held sells and held stop breaches are included as today.

**Pullback list** (replaces `_isTradeModeDiffBuy`): the same tests, but Entry is Pullback, Stretched, Below LRR or
No range. Fixed-income rows stay here as today.

**Removed:**
- the score threshold (12)
- the PVV AVOID veto (never the only reason in history: 6 rows)
- the duplicate RTA Technical pass. The loose and strict checks are now identical, so the second one is dead code.

**MACRO veto pill:** show "MACRO no" when the Final Call side is buy and MACRO is SA or STM. Hover bullets:
- MACRO says {SA / STM} for this stock's sector / asset / style
- The buy is kept off the Buy now and Pullback lists
- The Final Call itself is unchanged

**Cautions** (shown, never scored; existing thresholds kept):
- RSI ≥ `rsi_overbought`
- `iv_ratio` > 1.15
- RVOL ≥ `vlm_rvol_avoid_threshold` on an up day
- price in the TRR zone
- the existing source / sector "underperforms" lines

**GUESS / judgement calls:**
- Using the TRR-zone setting (20%) as the "Stretched" line is a judgement call. It reuses an existing setting rather
  than a measured cut.
- The green / amber / grey pill colours are a design choice.

**Data notes:** all figures are from read-only queries on 28 Oct 2026. Scratch scripts are not in the project.

### Worth reconsidering
No buy-side layer (Final Call, score, Trade) has beaten the average stock in eight months, and adding more filters
has not changed that. Before tuning anything else on the buy side:
- Let the 23 Oct Technical rules build 4–6 weeks of history.
- Then measure win rate by winning source and Entry zone (one short query on `drv_actionable` + `drv_factor_snapshot`).
- Prune weak buy sources (TOP5 28% wins, PS 37%) at the source level, where it changes the Final Call. That needs
  your approval.

## Files likely touched
- `web/actionable_pops.js`:
  - Replace `_buyTradabilityScore`, `_lrrProximityScore`, `_sourceTrackRecordScore`, `_buyAgreementSubTier` (score
    use), `_tradabilityBreakdown`, `_actpopTradabilityHtml` and `_TRADABILITY_BADGE_MIN` with `_entryZone(row)`,
    `_entryPillHtml`, `_actpopEntryHtml`.
  - Retire `_ivRatioScore` and `_tradabilityDeltaColor` (the IV / RVOL / RSI cautions stay in `_signalReasons`).
  - Add the MACRO-veto pill helper.
- `web/actionable.js`:
  - `_isTradeModeQualifyingBuy` (Entry replaces the score; drop the PVV and duplicate RTA passes)
  - `_isTradeModeDiffBuy` / `_matchesTradeModeDiff`
  - `_computePriority` (Entry rank replaces score × 10; drop the PVV boosts)
  - `_tradabilityBadge` → Entry pill; `_buildTradabilityPopHtml`
  - the Final-Call side-panel checklist row (about line 4465)
  - `_finalCallHtml` (MACRO pill)
  - IV cell (add ×own avg, drop the percentile edge tag)
  - `DEFAULT_HIDDEN_COLS` (+ macd, macdh, pvv); column menu (drop calc / bullprob / agree)
- `web/actionable.html`: button labels and `data-tip` bullets, header tooltip for Symbol / IV, legend text, CSS for
  the Entry pills, cache-bust `?v=` bumps.
- `web/universe.js`: its own copy of the score and badge (about lines 3739–4330). Same swap to the Entry pill.
- `etl/export_trade_mode.py`: mirrors the score, gates and BUY_DIP sort. Change it to the Entry rules so the export
  matches the screen.
- `docs/actionable_logic.md`: a new dated section (Entry label, Buy now / Pullback, what was retired and why, the
  figures above). `docs/actionable_playbook.md`: one-line pointer.
- `CLAUDE.md`: one Lookup row, "Entry label / Buy now / Pullback → docs/actionable_logic.md". It stays an index.
- Optional, separate fix: `v_factor_scorecard` baseline in `db/baseline.sql` / `etl/compute_factor_outcomes.py` (see
  Bugs). It only affects the RSI / IV edge tags once the score is gone.

## Open questions
1. **Replace the 🎯 score with the Entry label, and rename Trade / Trade2 to "Buy now" / "Pullback"?**
   - Recommend yes. The score did not predict returns (link 0.011). Trade did not beat Trade2.
   - Alternative: Option B, keep the score with only the range, RSI, IV, volume and source terms.
2. **"Buy now" = bottom 25% of the range (the Technical's own LRR-zone setting)?**
   - Recommend yes, so Technical and Entry use one number.
   - Alternative: the old 15% "near LRR" line. That gives fewer rows and has no better data.
3. **MACRO: veto only, no bonus points, plus a "MACRO no" pill on vetoed BUY badges?**
   - Recommend yes.
   - Alternative: make MACRO part of the Final Call. That changes `final_code` and needs your approval. Not
     recommended: MACRO's all-stock record is mixed.
4. **PVV: drop the AVOID veto (never the only reason) and the BUY_DIP top-of-list boost (BUY_DIP: 36% wins vs 46%
   average)?**
   - Recommend drop both and keep the PVV icon in ACTION.
   - Both were your own asks (27 Aug, 3 Oct), so this is your call.
5. **Columns: hide MACD / MACDH / PVV by default, show "×own avg" in the IV cell, remove CALC / P(↑20d) / Agree from
   the menu while no model is active?**
   - Recommend yes. All stay reachable or come back when a model is switched on.
6. **Keep "BUY TO MIN only above the Trade line" inside Buy now?**
   - Recommend keep. It is your rule, and the data is neutral.

Bugs noted (no decision needed; fix with this work or separately):
- **Baseline mismatch** in `v_factor_scorecard`. 'Baseline | All stocks' (46.2% wins, n=144,858) includes rows that
  have no RSI or RVOL bucket. The RSI buckets add up to only 128,652 rows and the RVOL buckets to 115,804. So almost
  every bucket looks 3–4 points "better than baseline". This is why neutral RSI gets +3.7 and the grid's edge tags
  lean green. The code comments still quote a 49.4% baseline.
- **Dead check** in `web/actionable.js::_isTradeModeQualifyingBuy`. The "3rd Strict pass" (the RTA Technical check)
  is now identical to the loose check. It never removes a row.
- **Stale comment** in `_signalReasons`: it says the Tradability box's IV item was removed, but
  `_tradabilityBreakdown` still has it.
- **Technical sell steps look weak** in `drv_signal_winrate`. S1-b (Sell All) is followed by a rise 56.5% of the
  time over 15 days (n=36,895). That is outside this brief. Worth a separate look.

## Status
READY_FOR_DEV
