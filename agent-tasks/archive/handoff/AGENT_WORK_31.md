# AGENT_WORK — Developer master pointer

Current task: **`agent-tasks/TASK_124_trade_mode.md`**

Trade Mode toggle on `/actionable`: when ON, show only (1) qualifying buys —
`final_code` BM/BMN + feasible + `rr_bull_bear='B'` + not stop_breached +
MACRO not SA/STM, any source, with a WEAK SRC pill when the winning source
is in the tunable `ref_settings.trade_mode_weak_buy_sources` list (seed
'PS,ETF,II'); (2) held SA sells; (3) held stop_breached rows. Everything
else hidden. Toggle OFF = pixel-identical to today. Small API addition:
`rr_bull_bear` in the `/api/actionable` payload. Additive `ref_settings`
seed only — no derive/rule changes.

Append progress to `DEV_HANDOFF.md`; end with `ALL_DONE`. No commit, no
tester handoff.
