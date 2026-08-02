# TASK_137 — Exclude SO (Sell Overage) from the Shortlist

## Goal

The Shortlist is showing `SO` rows. `SO` ("Sell Overage" — trim back to category max) is
a **position-sizing action**, not a market signal: it fires because a holding drifted
above its `ref_asset_allocation` ceiling, regardless of what the market is doing. It was
never part of the validated high-conviction subset in `docs/actionable_playbook.md` §3.3,
so it cannot earn one of the three slots.

**Remove it from the Shortlist. Change nothing else.**

---

## The change

`api/routers/cockpit.py`, `_SHORTLIST_SQL` (~line 245).

`SO` currently qualifies through the third OR branch —
`(a.final_side = 'sell' AND a.fc_confidence = 'gate')` — which was written to admit
conviction sells and catches sizing actions as a side effect.

Add one top-level condition so it applies regardless of which branch matched:

```sql
    WHERE a.as_of_date = :d
      AND COALESCE(a.fc_confidence, '') <> 'mixed'
      AND COALESCE(a.final_code, '') <> 'SO'          -- ← add this line
      AND (
        ...unchanged...
      )
```

Note `etl/derive_actionable.py` maps **both** `OVER_MAX` and `SO` to `final_code = 'SO'`
(`_FC_MAP` lines 50–51), so this single condition covers both. Confirm that mapping still
holds before relying on it; if `OVER_MAX` can reach `final_code` unmapped, exclude it too.

Update the comment block above `_SHORTLIST_SQL` to record why `SO` is excluded — a future
reader will otherwise see "gate-confidence sells are trusted" and re-admit it.

---

## Explicitly NOT in scope

Per the user: **do not touch anything else.**

- No footer line, no "N positions over category max" count, no link.
- No change to the buy branch, the `SA` branch, or the gate-sell branch.
- No change to the 3-row cap, the sort, or `web/app.js`.
- No change to any other action code (`SS`, `STM`, `REDUCE` stay as they are).
- Nothing under `etl/`, `db/`, `web/`, or `tests/`.

## Done when

`/api/cockpit/shortlist` returns no row with `final_code = 'SO'`, and the rows it does
return are otherwise unchanged for the same date.

## Files expected to change

`api/routers/cockpit.py` — one line plus a comment. Nothing else.

## Standing rules

- **No questions.** The change is fully specified.
- **No tests.** Do not write, extend or run anything under `tests/`. Do not hand off to
  the tester agent.
- **No commits, no pushes.** The user commits from Windows.
- Append a short `# Dev Handoff — TASK_137` section; end `ALL_DONE`.
