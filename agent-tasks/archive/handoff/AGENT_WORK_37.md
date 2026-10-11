# AGENT_WORK — current developer assignment

Implement, in order:

1. `agent-tasks/TASK_130_tos_bb_vix_coupling_bottom_refine.md` — refine the
   TASK_129 TOS band fit with inverse VIX coupling (VIX range top → equity
   bottom, VIX range bottom → equity top), a vol-level width law, downside
   semi-deviation, and directional volume; primary goal is the BOTTOM band
   (≤0.75% median APE, ≥78% within 2%) without regressing TOP. Strict
   2-fold walk-forward CV guardrails per the spec.

Log progress in `DEV_HANDOFF.md`; end with `ALL_DONE` when finished.
Do not invoke the tester. No commits — the user commits from Windows.
