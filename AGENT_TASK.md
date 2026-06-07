# AGENT TASK 28 — verify rule-edge badges on Actionable + Rule Flow, commit

**You (VS Code agent), Windows git.** Write to **`AGENT_RESULT_28.md`**.

Frontend-only change (no DB, no rules). The Actionable detail and Rule Flow now
show each fired rule's historical edge (from the live `/api/rules/scorecard`)
as a small colored badge next to the rule code. Files changed:
`web/actionable.js`, `web/rule_flow.js`.

## Step 1 — confirm the endpoint is live
```
curl -s "http://127.0.0.1:8000/api/rules/scorecard?min_fires=0&limit=3"
```
Should return JSON rows with edge_20d. (Already shipped earlier; just confirming.)

## Step 2 — check the screens (hard-refresh; web/ is static)
1. Open `/actionable`, click a symbol row to open its detail. In the "Rules fires"
   area, each fired-rule pill should now show a small edge like `+1.9% · 50%`
   (green if positive, red if negative). Open the browser devtools Console and
   confirm NO JS errors on the page.
2. Open `/rule-flow`, load a symbol (e.g. AAPL). Each composite code should show
   the same edge badge. Confirm no console errors.

Paste: one line each on whether badges render on Actionable and Rule Flow, and
whether the console is clean. If a screen errors, paste the console error.

## Step 3 — commit
```
git add web/actionable.js web/rule_flow.js
git status --porcelain   # confirm only these two (+ nothing unexpected)
git commit -m "UI: inline rule-edge badges on Actionable detail + Rule Flow (v_rule_scorecard via /api/rules/scorecard) — show each fired rule's historical 20d edge at the point of decision"
git log --oneline -2
```
Paste status + log.

## Verdict
(a) badges show on Actionable? (b) badges show on Rule Flow? (c) console clean?
(d) committed? If any screen has a JS error, STOP and paste it so I can fix.

Write `DONE` at the bottom of `AGENT_RESULT_28.md`.
