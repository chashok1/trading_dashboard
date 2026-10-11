# AGENT_WORK — Developer master pointer

Work these in order:

1. **`agent-tasks/TASK_126_quad_lookahead_window.md`** — MACRO: replace the
   month now/next ramp + quarterly one-hot blend with a sliding 60-day
   look-ahead window over the monthly quad calendar → one effective quad
   distribution into the existing Stage 1–2 calc. Quarterly weight → 0.05,
   ramp params retired, `macro_thr_*` recalibrated by percentile, tooltip
   shows month mix + tracking tag.

2. **`agent-tasks/TASK_127_pvv_outlook_decision.md`** — PVV decision
   rewrite: `decide_pvv` becomes RR-outlook × sig_today (outlook decides
   WHAT, today's tape decides WHEN; knife guard on STRONG_BEAR). Bucket
   calculations untouched; re-derive + backfill drv_pvv.

(TASK_125 PVV is complete — see the AGENT_WORK_32 section of
`DEV_HANDOFF.md`, verified and awaiting user commit. TASK_127 modifies only
its decision layer.)

Work each spec top to bottom. Record all changes, decisions, and risks in
new `DEV_HANDOFF.md` sections (one per task); end the file with the literal
marker `ALL_DONE` only when both are finished. Do not invoke the tester.
Do not commit or push.
