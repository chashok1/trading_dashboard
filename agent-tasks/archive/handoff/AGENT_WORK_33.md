# AGENT_WORK — Developer master pointer

Current task: **`agent-tasks/TASK_126_quad_lookahead_window.md`**

MACRO: replace the month now/next ramp + quarterly one-hot blend with a
sliding 60-day look-ahead window over the monthly quad calendar → one
effective quad distribution into the existing Stage 1–2 calc. Quarterly
weight → 0.05, ramp params retired, `macro_thr_*` recalibrated by
percentile, tooltip shows month mix + tracking tag.

(TASK_125 PVV is complete — see the AGENT_WORK_32 section of
`DEV_HANDOFF.md`, verified and awaiting user commit. Do not rework it.)

Work the spec top to bottom. Record all changes, decisions, and risks in a
new `DEV_HANDOFF.md` section; end the file with the literal marker
`ALL_DONE` when finished. Do not invoke the tester. Do not commit or push.
