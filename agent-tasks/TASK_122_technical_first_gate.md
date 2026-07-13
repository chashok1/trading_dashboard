# TASK_122 — Technical-first buy gate: remove the new-arrival bypass

Display layer only — `web/actionable.js`. No derive/schema changes.

## Context

TASK_120's buy-noise gate has a leak, confirmed by a real case (FAB): the
"new arrival" bypass fires whenever the winning source's snapshot_date equals
the anchor — which for daily-refreshing sources (RR, CALL) is *every day*, so
their rows skip the Watchlist band permanently even with blank Technical.

User decision: invert priority. **Technical decides WHEN (entry timing);
Sources decide WHAT (conviction).** A source listing alone never promotes an
unheld buy.

## Changes

1. **Delete the new-arrival bypass** (`_isNewArrival` and its use in
   `_buyNoiseGated`). The gate becomes purely:
   unheld AND effective ADD / final BMN AND `rr_action` not in
   `_ENTRY_RIPE_TECH (['BS','BM'])` → Watchlist band. Blank/missing Technical
   stays not-ripe. Held rows still never gated.
2. **NEW pill inside the band**: rows whose winning source snapshot_date ==
   anchor date render a small "NEW" pill next to the symbol *inside the
   expanded Watchlist band* (reuse an existing pill/badge style). Discoverable,
   never auto-promoted.
3. Band internal order: keep dollar-weighted edge, but NEW rows first within
   equal-score groups (stable tiebreak) so fresh arrivals are on top when the
   band is expanded.
4. Update the "?" legend: describe the technical-first rule in one sentence
   ("Unheld buys surface only when Technical shows BS/BM; new list arrivals
   wait in the Watchlist with a NEW tag").

## Files expected to change

- `web/actionable.js` (+ minimal CSS in `web/actionable.html` if the NEW pill
  needs it), `DEV_HANDOFF.md` (append; end `ALL_DONE`)

## How to verify

1. FAB-type case: an unheld row, winning source RR refreshed today, blank
   Technical → sits INSIDE the Watchlist band with a NEW pill; NOT in Tier 1.
2. An unheld ADD with Technical BS or BM → Tier 1 (unchanged).
3. A held row → never in the band (unchanged).
4. Expand the band: NEW-pilled rows are visible near the top of their score
   group; searching a banded symbol still auto-expands.
5. `node --check web/actionable.js` passes; report the new Watchlist count vs
   the previous round's (expected to grow, since bypassed rows now land in
   the band).
