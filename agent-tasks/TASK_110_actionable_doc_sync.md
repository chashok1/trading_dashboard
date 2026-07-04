# TASK_110 — Actionable: documentation sync (final)

Source: `docs/audit/actionable_screen_review.md` — §4 doc drift. Deliberately
LAST in the queue (104 → … → 109 → **110**) so the docs describe the grid as
it exists after all the preceding tasks, not a moving target.

Goal: `docs/actionable_logic.md` and the `CLAUDE.md` Lookup index match the
shipped screen.

Files expected to change: `docs/actionable_logic.md`, `CLAUDE.md` (lookup
rows only), `docs/audit/actionable_screen_review.md` (mark items done).

## Items

1. **Rewrite the Display section** of `docs/actionable_logic.md` from the
   code as it now stands (post TASK_103–109). Must cover:
   - actual grid column list + which are default-hidden / user-toggleable
     (column manager, TASK_105) and the top-15 collapse behavior;
   - ACTION = Final Call (server-computed, D6) + confidence badges; chips
     derive from `finalCall()`; SELL→MAX overlay unchanged;
   - snooze semantics (TASK_103): dateless SNOOZED = hidden for that
     as_of_date; dated SNOOZED = hidden until date; DELETE clears
     SKIPPED+SNOOZED; Show Hidden reveals with reasons;
   - auto-refresh behavior (TASK_104): background reload preserves
     sort/selection;
   - lazy macro-detail fetch (TASK_106) and the bulk-action endpoint;
   - focus-mode keys (TASK_107);
   - DELETE the stale text: Metric column, Snapshot column, Other Sources
     column, per-source "Way 1 / Way 2" sort, "first grid column is a
     per-row Snooze button".
2. **CLAUDE.md Lookup index** (keep every row one line, per convention #10):
   - Fix "Actionable Market-context band" row — `macro_band.js` +
     `cockpit.html` were deleted in TASK_109; point at the Econ panel
     (`web/market_bar.js`, `#econPanel`, `/api/macro`) instead.
   - Add a row for the bulk-action + macro-detail endpoints if not already
     covered by an existing row.
3. **Mark the review doc**: in `docs/audit/actionable_screen_review.md`, add
   a short "Status (post TASK_103–110)" note at top listing which findings
   were fixed in which task, so the audit doesn't read as open issues later.

## Guardrails

- Docs only — no code changes. If the Display rewrite reveals a code/doc
  mismatch that is actually a bug, do NOT fix it here; note it in
  `DEV_HANDOFF.md` for triage.
- Convention #10: CLAUDE.md stays an index — one-line rows, detail in docs/.
- Log in `DEV_HANDOFF.md`, end `ALL_DONE`. No commit; no tester.

## How to verify

1. Read `docs/actionable_logic.md` Display section side-by-side with the
   live screen: every column, chip, badge, and behavior mentioned exists;
   nothing on screen is undocumented; no deleted feature is still described.
2. `grep -n "macro_band\|Metric column\|Way 1\|Way 2" docs/actionable_logic.md CLAUDE.md`
   → no stale hits.
3. CLAUDE.md diff touches only Lookup index rows.
