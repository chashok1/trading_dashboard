# TASK_153 — Phase 4: LIVE column + "Today's actions" panel (screen only)

**Design sources:** `DESIGN_SPEC_3.md` §6 (LIVE column); `DESIGN_SPEC_4.md` §7 and §7b (sell badges, notes, caution);
`DESIGN_SPEC_5.md` §6 (wording), §7 (placement) and rule A7. Needs TASK_152 (`GET /api/actionable/live`).
The user approved this on 2026-10-12. The same user decisions as TASK_152 apply (accounts independent, Hold = snooze,
Final Call sizing untouched, one combined list).

## What to build (`web/actionable.js`, `web/actionable.html`; bump `?v=`)
### A. LIVE column
New toggleable column `live` after PVV, built like PVV (`TOGGLEABLE_COLS`, visible by default). One badge per row
(TRIM, TRIM->MAX, DIP BUY, dip buy (Light, greyed), BUY BACK, WAIT, dash), tags `chase` and `!`, stale outline after
45 min, and a **bulleted** hover tooltip (`data-livepop`, same `_showDataPop` as `data-pvvpop`): one block per account
(shares, dollars, limit price), prior close / SD / trim line, room to top of range and range width (info only), the
"Don't sell the low" caution + bounce price, the gain / outlook-turned / sector notes (sector names are inconsistent,
normalise before use), PVV line on WAIT, "Why required" and "Est. value" lines, "too small to list" lines, price time.
Sort is tier first (MUST 0, CONSIDER 1, BUYIDEA 2, INFO 3, none 9), then spec 3's order; larger dollars first. Light
dips and other INFO badges show only when the panel's "Show all live signals" is on. No new pills in the SYMBOL cell,
no "Live now" strip, no Action popup section (the user dislikes duplicates). The OVER MAX pill stays as it is.

### B. "Today's actions" panel (one combined list)
`#todayPanel` between `#hedgeyePanel` and `.act-toolbar`, full width, no max-width. Open by default when MUST > 0,
otherwise one collapsed line (`Today's actions: none required - 6 to consider - 10:58 ET`). Three sections in order:
**Do today** (MUST), **Consider** (up to 8, "+N more"), **Buy ideas** (top 5). Each line reads like an order
(verb, shares, symbol, account, price, size, short reason, evidence word) -- spec 5 §6 table. "Since Tue (day 3)" tag
for carried items (warn colour from day 3). "Not listed today:" muted line with counts. Quiet-state and stale-price
and "Can't size" messages per spec 5 §6. Existing colour tokens only. Click a line = scroll to the grid row and open
its LIVE tooltip. Plain English, short labels.
- **Act (N) chip** next to "In headwind area (N)": N = MUST + CONSIDER + BUYIDEA stocks; it filters the grid to them.
  It replaces the "Live (N)" chip of spec 3.
- "Show all live signals" link in the panel reveals INFO badges in the LIVE column.

### C. Trade Mode folds into Buy ideas
The user chose one combined list, so the **Trade** switch is replaced by the Buy ideas section. Concretely:
- `state.filters.trade_mode` must no longer start ON (it currently "always starts ON" -- search that phrase).
- Remove the **Trade** button from the toolbar once the panel works. **Keep** `_isTradeModeQualifyingBuy` and the other
  helper functions (the back end ports the rule; Trade2 and WL still use the helpers).
- Do not remove or change Trade2 or WL without telling the user: if Trade2 only makes sense with Trade on, **leave
  Trade2 and WL working as they are and list the question in the handoff** (do not guess).
- Keep the saved-preferences key behaviour safe (old saved `trade_mode: true` must not turn it back on).

## Checks
- `node --check web/actionable.js`; TestClient load of `/actionable` and `GET /api/actionable/live` for 2026-10-09.
- Run the real render code against live data from the endpoint in the scratchpad (see the memory note on verifying
  visual fixes computationally) and confirm: the 10/9 panel shows MUST XLE, TXG, MSFT, AAPL; Buy ideas has at most 5;
  every tooltip is a bulleted list; the LIVE column sorts MUST first.
- Report what you could not verify in a browser.

## Rules
- Full-width layouts, no duplicate chips/pills, bulleted tooltips, plain-English wording, bump the `?v=` on the changed
  JS in `web/actionable.html`. Preserve line endings. No tests/pytest this round. No emails or network calls.
- Docs: `docs/live_advice_logic.md` (new: tiers, precedence, wording), one Lookup row in `CLAUDE.md`, dated line in
  `docs/migrations.md`.
