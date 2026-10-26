# TASK 155 — Technical rules redesign (Step 1 / Step 2 / Step 3), with win %, popup and mini graphs

Author: Cowork/VS Code session, 2026-10-25. Status: **spec only, nothing built**. The user approved the rule set below one rule at a time against 163 trading days of history (2 Feb to 22 Oct 2026, ~1,100 stocks). No commit/push by the agent.

## 1. Goal (plain English)
Replace most of the "Technical" step rules with a smaller set that the history supports, split every Step 3 action by whether the stock is **above or below its Trade/Trend lines**, add a new "falls below Trade" sell and a "below the lowest of the last 5 Trade lines" Sell All, and make the app show how each rule has performed (win %) and how it was derived (small graph).

Three companion changes are **required**, not optional (user: "when these change, make sure jobs are updated, the Action popup shows the %, and add a small graph, the size of a big icon, depicting how each technical rule came about"):
1. The nightly win-% job (`etl/derive_signal_winrate.py`, table `drv_signal_winrate`, TASK_154, committed as 1d8b62e) is updated for the new rule ids and definitions.
2. The Action popup shows the 3-day win % next to every fired technical step.
3. Each technical rule in the popup gets a small graph (about the size of a large icon) that illustrates the rule.

## 2. Visual spec
`scratchpad/technical_flow_map.html` (generator `scratchpad/flow2.py` + `flow_tail.py`) is the picture of the final flow; published privately at https://claude.ai/artifact/Q7aMKmptAkquGDtyq1DdHs. Read the HTML for layout, chart shapes and the exact rule wording. Scratchpad = `C:\Users\chash\AppData\Local\Temp\claude\C--Ashok-Invest-Projects-trading-dashboard\1345be8b-a1af-471a-b4a4-57f09439c64f\scratchpad\` (read-only reference; do not write there, do not import from it).

## 3. Definitions used by every rule
- **pos%** = (price − LRR) / (TRR − LRR) × 100, using the current/closing price. Requires TRR > LRR.
- **LRR zone** is measured on the day's **low** (existing `lrr_idx`): −1 = low broke more than 0.25 SD below LRR; 0 = low inside the zone, from LRR up to `range_lrr_zone_pct` (0.25) of the range above it; +1 = low clear of the zone. "Low reached LRR zone" = `lrr_idx` ∈ {0, −1}.
- **Midpoint zone** (`mrr_idx`): −1 below 40% of range, 0 = 40% to 60% (±`range_mid_zone_pct` 0.10 around 50%), +1 above 60%. **TRR zone** = top `range_trr_zone_pct` (0.10) of the range.
- **Bands** (`bb_rng_strk_rule`): ≥ 2 rising, 0 or 1 flat, < 0 falling (existing Step 2 meaning; in the old code "rising" = QJ ≥ 2).
- **Above flag** = `trend_trade_rule` ∈ {3, 4} (price above Trade AND above Trend). **Below flag** = anything else (below Trade, or below Trend, or the Trade line is below the Trend line).
- **Up day / down day** = price higher / lower than the previous close (existing `perf1d_sd_rule` > 0 / < 0).
- **TRR up 2% over 5 days** = TRR today ≥ 1.02 × TRR five trading days earlier.
- **Last 5 Trade lines** = the Trade line value (`a_trade_value`) of the previous five trading days (shifted by one, not including today). Check what `min_trade5` in `etl/derive.py` does today and reuse it only if it matches; prototype used previous-5-days minimum.
- All price/volume history uses **real trading days only**: drop dates where > 90% of stocks have a price identical to the prior day, and blank stock-days whose price equals their previous kept day (the STALE FIX in `derive_signal_winrate.apply_stale_fix`).

## 4. Final rules

### Step 1 — Trade and Trend lines (checked top to bottom, first match wins)
| # | Condition | Action |
|---|---|---|
| S1-a | Price below the lowest of the last 5 Trade lines | **Sell All** (new) |
| S1-b | Below both lines, or Trade line below Trend line and price less than 1 ATR above the Trade line (`trend_trade_rule` −2 / −1; −1 = Trade below Trend and price less than 1 ATR (14-day) above Trade. CHANGE: the code today uses 1 SD (`trade_sd < 1` in `etl/derive.py` Pass 1, the `WHEN c.trade_trend_sd < 0 AND c.trade_sd < 1 THEN -1` line); switch it to `(price − Trade) / ATR14 < 1`, using the same ATR14 and SD-fallback as the LRR break) | **Sell All** (existing, unchanged) |
| S1-c | Price fell below Trade within the last 3 trading days (was at/above Trade on a prior day in that window), is still below Trade today, and is above Trend (`trend_trade_rule` = 1) | **Sell Some** (new; replaces today's Sell to Min for code 1) |
| S1-d | None of the above | no Step 1 sell → go to Step 3 with the Above/Below flag |

The existing rising-dip rule (code 0, Buy Some), the neutral dip (code 5) and the bounce exception (Pass 1b) are **unchanged**. Stocks in "above Trade, below Trend" (code 2, no signal) now continue to Step 3 with the **Below** flag.

**Structural change:** Step 3 must now run for every stock (today it only runs when price is above both lines or in the bounce exception), because the Below column needs it.

### Step 2 — band gate
Rising bands → 3A. Flat bands → 3B. Falling bands → 3C. Keep the existing "falling band = warning" wording in the why card.

### Step 3A — rising bands (checked top to bottom, first match wins)
| Rule | Condition | Above flag | Below flag |
|---|---|---|---|
| 3a | Support broken (existing detection, `lrr_idx_eff` = −1) | Sell to Min | Sell All |
| **3x** | Low reached LRR zone (0 or −1) **today or in the previous 3 days**, and pos% 25 to 60 | **Buy More** | **Buy To Min** |
| **3f** | Low reached LRR zone (0 or −1) **today**, price above LRR, pos% < 25 | **Buy Min** | Do nothing |
| **3h** | Up day, pos% 25 to 60 (widened from 40-60 on 2026-10-25; 3x still wins where both fire), TRR up 2% or more over 5 days | **Buy Min** | Do nothing |
| else | | Hold | Hold |

3x wins over 3h where both match. **Removed:** 3b, 3c, 3d, 3e, 3g, 3h(old definition), 3i (3i becomes Hold). Remove the old `bull_rr_action` codes that produced them.

### Step 3B — flat bands
| Rule | Condition | Above flag | Below flag |
|---|---|---|---|
| 3x | same as 3A | Buy More | Buy To Min |
| 3f | same as 3A | Buy Min | Do nothing |
| 3h | Up day, pos% 25 to 60 (no TRR condition; added by user 2026-10-25 against back-test: ~1,878 above-both signals, 48% up 3d, below the 51% baseline). Checked after 3x and 3f. | Buy Min | Do nothing |
| 3k | Price pos% > 90 OR the day's high pos% > 90 (high reached the top 10%), and Above flag | Sell Some | n/a |

**Removed:** 3j, 3l, 3m, 3n.

### Step 3C — falling bands
| Rule | Condition | Above flag | Below flag |
|---|---|---|---|
| 3x | same as 3A | **Buy Some** | **Do nothing** |
| 3p | Price pos% > 90 OR the day's high pos% > 90, and Above flag (same as 3k; back-test: ~2,350 above-both falling-band signals, 49% down 3d) | Sell Some | n/a |
| (below) | any stock below Trade or below Trend | n/a | **Sell All** |

**Removed:** 3o, 3q, 3r, 3s.

### Precedence
- A Step 3 **buy** result (3x, 3f, 3h, and the falling-band 3x) wins over the Step 1 sells (S1-a, S1-b, S1-c). The user said "3x wins" explicitly.
- Decision still open (see section 9): whether a Step 3 "Do nothing" also blocks Step 1 sells.

## 5. Where to change things (investigate; do not trust blindly)
- `etl/derive.py::_derive_trend_trade_rules_impl` Pass 1 / 1b / 2 / 2b: Step 1 (`trend_trade_rule`), bands (`bb_rng_strk_rule`), `bull_rr_action` / `not_bull_rr_action`, `lrr_idx_eff`, `bounce_exempt`. Note `etl/derive.py` and `etl/technical_why.py` have **uncommitted edits from another task** (rising dip codes 0/5, bounce note). Build on top of them; do not revert them.
- `etl/derive_actionable.py::_compute_final_call` and `docs/actionable_logic.md` for how step results become `consolidated_action`/`trig_action` and the Final Call. Add Above/Below handling and the new action vocabulary values (Buy Some / Buy Min / Buy More / Buy To Min / Do nothing / Sell Some / Sell All / Sell to Min) without breaking existing vocab (SA/STM/SS/BM...). **Buy To Min** may be a new value: map it to the existing "buy up to the minimum" code if there is one, else add it.
- `etl/technical_why.py` (`step_ids`, `technical_trail`, `_bounce_note`) and `etl/why_card.py`: new step ids and plain-English "why" lines for every rule above (e.g. "Fell below Trade 2 days ago, still above Trend: Sell Some").
- `db/baseline.sql`: any new columns on `drv_tn_td_bb_rr` (e.g. previous-5-day Trade minimum, fell-below flag). Idempotent; also add a `migrate_*.py` if DO blocks are needed.
- `web/actionable_pops.js::_actpopWhyCardHtml` and `web/actionable.js` for the popup; bump the `?v=` cache-buster on every edited web JS.

## 6. Win % job (update `etl/derive_signal_winrate.py`)
- New step ids: S1-a, S1-b, S1-c, 3a, 3x, 3f, 3h, 3k, 3p (and the unchanged Step 1 ids 1a..1g that still exist). Keep splits already stored: horizons 1, 2, 3, 4 (main) and 10, 15 (reference); outlook split (Bullish/Bearish/Neutral from `drv_rr.outlook`); Trade/Trend split; Above/Below flag split for each Step 3 rule.
- **Do not use stored codes for history.** Stored `bull_rr_action`/`not_bull_rr_action` before 2026-10-05 follow older definitions (e.g. old 3e/3b were assigned without the MACD condition; old 3d had no midpoint limit). Rebuild every rule's history from raw definitions in section 3/4 (prices from `drv_quote`, LRR/TRR from `drv_rr`, Trade/Trend values from `hist_td`, bands from `drv_tn_td_bb_rr`).
- **Win % shown = 3 days:** for Buy/Hold-type steps the share that went **up**; for Sell steps the share that went **down**. Do-nothing rows show nothing. Keep `few` (< 30 signals) and `thin` (< 30 stocks) flags; show a % only when not `few`.
- Runs inside the existing nightly outcomes run (as TASK_154 did) with the same dashboard warning on failure (`meta_warning`, screen `dashboard`, codes `signal_winrate_*`). Failure of the job must keep the last good table.

## 7. Action popup
- Next to every fired technical step show: the step id, the action for the stock's Above/Below flag, and `<3-day win %> (n signals)`. If `few`: "too few past signals". Tooltip is a **bulleted list** (1/2/4/10/15-day numbers, outlook split, Above/Below split, history range, "counts signals, not stocks"). Use existing CSS vars; no new hex colours.
- **Mini graph per rule** (about the size of a large icon, e.g. 56 to 72 px square, inline SVG, theme aware via CSS variables, `role="img"` with an `aria-label`): a static illustration of the rule, not stock data. Step 1 rules: price path against the Trade line (dashed), Trend line and the dotted lowest-of-5 Trade line, with the trigger point marked. Step 3 rules: the LRR to TRR ladder with the zone shaded, the bracket for the rule's pos% range, and the low touching the LRR zone where relevant. Reuse the shapes drawn in `scratchpad/technical_flow_map.html` (functions `ladder`, `bracket`, and the Step 1 chart in `flow2.py`). Put the SVG builders in one small shared JS module so grid and popup share them.
- **Rule help text (added 2026-10-25):** on every Technical step line in the "Why this action" card show a small ⓘ. Hover or click shows a **bulleted list**: the rule's plain-English "When" sentence (same wording as the flow diagram, e.g. "Price or day's high reached 90% of the range"), then the action for Above Trade and Trend, then the action for Below Trade or below Trend. Keep the sentences in ONE place (a dict next to the step ids in `etl/technical_why.py`, sent to the popup in `tech_trail`) so the popup, the tooltip and any docs never drift apart. Use the final wording of every rule from section 4 in plain English; do not show code values.
- **Whole rules map (added 2026-10-25):** the user wants the whole flow diagram reachable from the popup. A reference copy of the final diagram is at `agent-tasks/TASK_155_assets/technical_flow_map.html` (self-contained HTML + inline SVG, theme aware). Publish it as a static app page `web/technical_rules_map.html` (served like the other web pages; 100% width, no max-width) and add a link "How these rules work" in the header of the card's Technical section that opens it in a new tab. Because rules are described in the SVG as text, regenerate or hand-edit the page whenever a rule changes, and add one line to `docs/actionable_logic.md` saying so. The ⓘ on a step may deep-link to that step with an `#step-id` anchor (add an `id` to each rule row/box in the SVG), highlighting it on arrival if easy.
- Show the graph in the "Why this action" card next to the Technical stages, and also usable at larger size on hover if easy.

## 8. Acceptance (compare with the prototype; history grows daily so allow small drift)
Re-derive the full history with the new rules and compare 3-day shares (up for buys, down for sells):
- 3x rising bands: ~1,515 signals, 54% up (4 days 56%). 3f rising: ~713, 55% up (4 days 60%). 3h rising: ~518, 58% up (4 days 54%).
- S1-a (below lowest of last 5 Trade lines, above Trend): ~12,300, 52% down. S1-c (fell below Trade within 3 days, above Trend): ~8,150, 50% down.
- Flat bands 3x or 3f (above-both population): ~12,350, 51% up. Falling bands 3x (above-both population): ~1,090, 48% up.
- 3k flat (price or day high > 90%, above both lines): ~17,880, 49% down 3d (price-only part ~9,190, 50% down; the added day-high-only part ~5,840, 48% down). Below the 51% baseline, so weak; user chose to keep it. Falling-band below-Trade-or-Trend Sell All: informational only (history shows ~48% down; user chose to keep it).
- Idempotent: the job twice gives the same rows. Cross-check: `drv_actionable` actions change only where rules changed; list how many symbols change action on the latest date before/after.
- Task-acceptance tests only in `tests/acceptance/` marked `@pytest.mark.acceptance`; keep in `tests/` only behaviour tests for the new rule functions (pure Python, no DB). Do not run the whole suite for UI-only parts.

## 9. Open items — ask the user, do not guess
1. Does a Step 3 "Do nothing" (3f below, falling 3x below) also block the Step 1 sells, or only Buy results win? Default until answered: only buys win.
2. 3a in flat and falling bands: same Sell to Min / Sell All split as rising bands? Default: yes, unchanged detection.
3. Falling-band 3p: RESOLVED 2026-10-25 -- same as 3k: price or day's high over 90% of the range, Above flag only.
4. Falling bands, below Trade or below Trend → Sell All: user chose it despite history (48% down, stocks tended to bounce). Implement as asked.
5. Whether the "Buy To Min" action needs a new vocabulary value.

## 10. Constraints
- **No git commit or push.** LF line endings (`newline='\n'`; check `git diff --stat`). Verify Python with `ast.parse`, JS with `node --check`.
- No external side effects: no real emails, no network calls, no files outside the project folder.
- Restart the app (stop the server, `start.bat`) before re-deriving, because `etl/` changes.
- SQL statements ≤ 965 bytes; use `tos_symbol` everywhere; DB via SQLAlchemy + psycopg v3 only.
- Update `docs/actionable_logic.md` with a dated section describing the new rules, and add one Lookup row to `CLAUDE.md` only if a new doc is created.
- Write `DEV_HANDOFF.md` (plain English first, ends with `ALL_DONE`).
