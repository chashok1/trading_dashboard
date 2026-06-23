# Bull-Calc Rollout & Activation Runbook

**Read this when:** you've come back after a break and forgotten what the bull-calc
changes (TASK 65–69) were, or you want to turn them on/off. Plain-English, no need to
remember anything.

**Source of the plan:** `docs/audit/bull_calc_analysis.md` (the full analysis).
**Task specs:** `agent-tasks/TASK_65..69_*.md`. **Build order:** see `AGENT_WORK_7.md`.

---

## The one promise: you cannot lose your current setup
Every change is either **additive** (new column/panel beside the old ones — nothing
replaced) or **revertible by one config line**. Your existing screens, rules, gates, and
the Excel thresholds keep working exactly as before until *you* choose to act on the new
stuff. Defaults are set so doing nothing = today's behavior.

---

## What each piece is, and what YOU must do to use it

| Task | What it adds | Where you see it | What you must do to "enable" | How to revert |
|---|---|---|---|---|
| **65** Per-rule scorecard | Each individual rule graded by real forward returns | Performance screen, new panel | Nothing — it's just a report. **Read it** to see which rules have edge. | n/a (read-only) |
| **66** Bull probability | One number per stock: P(up in 20 days), + agreement | Actionable screen, new sortable column + filter | Nothing to switch. To *use* it: sort by it, filter to high prob, trade those. | Ignore the column. It changes no existing signal. |
| **67** Data-fit thresholds | Calculated cutoffs that replace the Excel guesses | Rules/Param screen (original vs calculated + comparison) | **The only real switch.** After checking the comparison, set `active_source = 'calculated'` for the rules you trust. | Set `active_source = 'original'`. One line, instant, nothing recomputed. |
| **68** De-dup cleanup | Same bull/bear answer everywhere (kills drift bugs) | Invisible | Nothing. Always on. | n/a (behavior-preserving) |
| **69** Agreement signal | "Both agree / split" flag + whether splits pay | Actionable column (badge) + Performance report | Nothing to switch. To *use* it: combine with prob in the filter. | Ignore the badge. |

---

## The activation sequence (do this, in order, when you're ready)

1. **Let the agent build the whole queue** (`AGENT_WORK_7.md`). Safe — see the promise
   above. Nothing you trade changes yet.
2. **Look at the Performance screen (TASK 65).** Which rules actually have edge
   (`proven` / `promising`)? Which are `unproven` noise? Just look — no action.
3. **Watch the new Actionable columns (TASK 66 + 69)** for ~2 weeks against what you'd
   have done anyway. Build confidence that the probability and agreement make sense.
4. **Only then, the one switch (TASK 67):** open the Rules/Param screen, read the
   "original vs calculated — would it have made more?" comparison, and for the rules where
   the answer is clearly yes, set `active_source = 'calculated'`. Leave the rest on
   `original`.
5. **If anything feels off, flip back:** `active_source = 'original'`. Done.

**Net:** the only irreversible-feeling decision (changing thresholds) is actually a
one-line, instantly-reversible config change — and it defaults to your originals until
you opt in.

---

## Quick "is it safe?" checklist
- Did I change any existing column/rule? **No** (66/69 add columns; 68 preserves behavior).
- Are my Excel thresholds still there? **Yes**, stored as `original_value`, never
  overwritten; active unless I switch.
- Can I undo the threshold switch? **Yes**, set `active_source='original'`.
- Do I have to remember anything? **No** — re-read this file.
