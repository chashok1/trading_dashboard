# AGENT_WORK — Developer master pointer

**Follow-up round: one missed section of TASK_120.**

The previous round (AGENT_WORK_27) implemented TASK_119/118/121 and most of
TASK_120, but the **"Buy-noise gate (unheld ADD/BMN flood)"** section of
`agent-tasks/TASK_120_default_sort_dollar_edge.md` was not implemented —
`web/actionable.js` has no `_ENTRY_RIPE_TECH` const and no Watchlist band
(the spec was updated mid-round; re-read it from disk now).

Implement ONLY that section, exactly as specced:

- UNHELD rows with effective action ADD or final code BMN rank in Tier 1
  only when Technical (`rr_action`, the QS code) is in
  `_ENTRY_RIPE_TECH = ['BS','BM']`; otherwise they go to a collapsed
  "Watchlist (n)" band that sits above the Bottom tier.
- Held rows never gated; first-day new arrivals bypass the gate once.
- Band: collapsed by default, one-click expand, ordered by dollar-weighted
  edge inside; chip filters and symbol search match banded rows and
  auto-expand on match. Nothing hidden permanently.
- Update the "?" legend. Display layer only — no derive/schema changes.
- Run spec verification item 4 (buy-noise gate) and report the observed
  Watchlist count vs the unheld-ADD count for the anchor date.

Append to `DEV_HANDOFF.md` (do not erase the AGENT_WORK_27 log); end with
`ALL_DONE`. Same ground rules: no commit, no tester, `node --check` before
finishing.
