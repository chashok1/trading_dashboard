# TASK_120 — Actionable default sort: stop breaches first, then dollar-weighted edge

Depends on: TASK_118 (`low_confidence` flag), TASK_119 (`stop_breached` flag).
Display-layer only — `web/actionable.js` `_computePriority()` and friends. No
derive or schema changes.

## Context

Current default sort ranks by signal severity ("agreement" tiers + Final Call
seq). Diagnosis showed severity ≠ money: it ignores whether the underlying
rules are historically right, mostly ignores dollars, and `_agreementDir` is
"no dissent," not agreement (1 signal + 2 silents lands in the top tier).

## New default order (descending tiers)

```
Tier 0     stop_breached held rows             → by position $ desc
Tier 1     everything else                     → by dollar-weighted edge desc
Watchlist  unheld standing buys, entry not ripe → collapsed band (see below)
Bottom     low_confidence-only sells, infeasible, suppressed
```

## Buy-noise gate (unheld ADD/BMN flood)

Diagnosis E.3: ~4,635 ADD recs over 40 anchors (~116/day), 93% unheld —
standing-list sources re-emit ADD daily and BMN is the default bull outcome.
This buries the few rows that matter.

1. **Entry-timing gate — Technical column (QS code).** An UNHELD row whose
   effective action is ADD or final code BMN ranks in Tier 1 only when its
   Technical value (`rr_action`, the QS code from
   `drv_cat_atomic_input.td_tn_bb_action_desc`) is **BS or BM** — the strong
   buy codes that Tables 2–3 emit only near LRR with momentum/pullback
   confirmation (mirrors the proven 52-BS-BRR entry). BMN, N, watch codes,
   sell codes, or missing Technical → not ripe. The ripe-code set is a JS
   const (`_ENTRY_RIPE_TECH = ['BS','BM']`), documented in the legend. Do NOT
   use raw LRR proximity — QS already contains it plus Trend/Trade, BB-streak,
   and MACDH context (a falling knife near LRR shows SA/STM and stays gated).
   A watchlisted row's own Technical cell thus shows the reason it's parked.
2. **Watchlist band.** Gated-out rows collapse into a "Watchlist (n)" band at
   the bottom of the grid (above the Bottom tier), collapsed by default with
   a one-click expand — same interaction spirit as the old "Show all N" bar.
   Within the band, order by dollar-weighted edge. Nothing is hidden
   permanently; chip filters and symbol search still match rows inside the
   band (auto-expand on match).
3. **Held rows are never gated** — this applies only to initiating new
   positions. New arrivals (source_snapshot_date = current anchor, first
   appearance) also bypass the gate for their first day so genuinely new
   recommendations surface once.

**Dollar-weighted edge** per row:

```
netEdge = Σ edge_20d of the row's fired composites (from state.scorecard,
          already loaded for the Rules(edge) column), sign-aligned so a
          SELL row's negative-edge rules SUBTRACT confidence
score   = netEdge * log10(1 + dollarsAtStake)
dollarsAtStake = |_amt| for actionable rows, position $ for HOLD rows
```

Rows with no fired rules fall back to the current seq*1e6+amt ordering,
scaled to sit between scored rows of similar magnitude (developer's judgment;
document the chosen scaling in code comments).

## Also in scope

1. Fix `_agreementDir` semantics: require >= 2 of 3 columns in the same
   direction with none opposing before the Agree column / legend claims
   agreement; rename internals accordingly. (Agree stays a display column —
   it no longer drives the default sort.)
2. `low_confidence` sell rows (TASK_118) sink below all scored rows regardless
   of dollars.
3. Column-header sorting, chip filters, preserveState auto-refresh behavior,
   and CSV export must keep working; default re-applies on date change /
   manual refresh exactly as today (`state.sort = {_priority, -1}` reset path).
4. Update the "?" legend text describing the default sort.

## Files expected to change

- `web/actionable.js` (+ legend text), `DEV_HANDOFF.md`

## How to verify

1. Load /actionable on latest anchor: breached-stop rows (TASK_119) are pinned
   top, ordered by position $.
2. Among tier-1 rows: a large-$ row backed by `52-BS-BRR` (edge +1.9) ranks
   above a small-$ row backed by weaker rules; a sell row backed only by
   negative-edge rules is near the bottom.
3. Clicking a column header still sorts that column; clicking date/Refresh
   restores the new default; 30s auto-poll preserves a user-chosen sort.
4. Buy-noise gate: an unheld ADD/BMN row with Technical = BMN/N/blank sits in
   the collapsed "Watchlist (n)" band; an unheld ADD with Technical = BS or
   BM stays in Tier 1; a HELD row is never in the band; searching a
   watchlisted symbol auto-expands the band; the band count roughly matches
   `SELECT count(*) ... consolidated_action='ADD' AND NOT held_today` minus
   Technical-in-(BS,BM)/new-arrival rows for the date.
5. `node --check web/actionable.js` passes; no console errors on load.
