# TASK 10 — Streamline Actionable filters (front-end only)

## Goal
The Actionable filter bar has ~14 controls and is confusing. Reduce to one clean
bar and collapse the five "+Show" toggles into a single **Show Hidden** toggle.
Front-end only — NO DB / derive / API changes.

## Final filter bar (single row, no More panel)
`[action chips + counts] · Conviction (Any/Multi/Proven) · Positions · Source ·
Symbol search · Show Hidden · Clear` (plus existing Refresh / date / Focus /
Export icons).

## Remove
- **Buys/Sells** toggle (`buyToggle`, `sellToggle`, `.buysell-toggle`) — redundant
  with the action chips.
- **Sector** filter (`sectorFilter`) and its populate/handler/predicate.
- **Asset Class** filter (`assetClassFilter`) and its populate/handler/predicate.
- **$ Stake** control (`amtCtrl`) and its predicate.
- **More** button (`moreFiltersBtn`) and the whole **More panel** (`morePanel`);
  the active-filter badge tied to it (`filterActiveBadge`) can go too.
- The five individual show toggles: `showNoAction`, `showZeroAmt`,
  `showSuppressed`, `showActed`, `showNotHeldRemove`.

## Add
- One **Show Hidden** toggle on the main bar (e.g. `id="showHidden"`,
  `<label class="toggle">`), default **off**. When ON it reveals ALL
  normally-hidden rows — the union of the old five conditions (suppressed, $0
  AMT, no-action, acted/snoozed, unheld-remove). When OFF, the current clean
  default view.

## Keep unchanged
Action chips, **Conviction** (user may enable later), Positions, Source, Symbol
search, Clear, Refresh, date picker, Focus mode, Export CSV.

## Implementation notes (`web/actionable.html`, `web/actionable.js`)
- `state.filters`: delete the removed keys; add `showHidden` (default false).
  In the row predicate (`matchesBaseFilters`), replace the five separate
  show-flag checks with a single rule: if `!showHidden`, hide suppressed / $0 /
  no-action / acted / unheld-remove rows; if `showHidden`, include them all.
  Remove the sector / asset-class / stake / buys-sells predicate branches.
- Remove the corresponding event listeners; add one for `showHidden`.
- `save`/`load`/`sync`/`clear`: drop removed keys; `Clear` resets `showHidden` to
  off and all else to default. **Ignore stale persisted keys** (old localStorage
  filter state) gracefully — no JS error if an old key is present.
- Remove now-dead dropdown-population code for sector/asset-class and any fetch
  used solely for them. CSV export data columns may stay; just remove the filter
  coupling.
- Optional tidy: delete unused CSS (`.act-more-panel`, `.buysell-toggle`,
  `#amtCtrl`, related `.act-fzone-label`).

## How to verify (dev has browser; front-end, no DB needed)
1. Hard-refresh `/actionable`. Bar shows ONLY: chips, Conviction, Positions,
   Source, Symbol, Show Hidden, Clear. Confirm Buys/Sells, Sector, Asset Class,
   $ Stake, and the More button/panel are GONE.
2. Default (Show Hidden off): a not-held REMOVE (e.g. NORW), a $0-AMT row, a
   no-action `—` row, and an acted/snoozed row are all hidden. Toggle Show Hidden
   ON → all appear; OFF → hidden again.
3. `Clear` resets Show Hidden to off and returns the default row set.
4. Chips, Conviction, Positions, Source, Symbol still filter correctly.
5. `node --check web/actionable.js` clean; `grep -nE
   "buyToggle|sellToggle|sectorFilter|assetClassFilter|amtCtrl|moreFiltersBtn|morePanel|showNoAction|showZeroAmt|showSuppressed|showActed|showNotHeldRemove"
   web/actionable.html web/actionable.js` → no remaining references. Console clean
   on load; no error when a stale saved-filter key exists.

## Constraints
Follow `CLAUDE.md`. Front-end only — no DB/derive/API changes. No commits/pushes
(#17). When complete and the tester passes, **delete `AGENT_WORK.md`** so the
5-minute `/dev-cycle` loop does not re-run this task.
