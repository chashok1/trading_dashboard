# AGENT_WORK — Developer master pointer

> **THE ONLY ACTIVE TASK IS: fix the issue in TEST_REPORT_42.md.**
> TASK_136 (`AGENT_WORK_42.md`) is otherwise correct and complete — do not redo it,
> do not touch anything outside the one bug below.

**Created:** round 2 of TASK_136, dev-cycle send-back
**Prior work:** `AGENT_WORK_42.md`, `DEV_HANDOFF.md` (`# Dev Handoff — TASK_136`),
`TEST_REPORT_42.md` (verdict: **FAIL**)

---

## The bug

`web/styles.css`, around line 1847, has a comment header for the cockpit CSS section
that contains the literal substring `--text-*/--border`. The `*/` inside that substring
prematurely closes the CSS comment. Everything between that point and the next real
`*/` becomes garbage "selector" text (it contains an unmatched `)`), and standards CSS
error-recovery drops the entire next rule — which is exactly
`.cockpit-bands { display: grid; ... }`.

Net effect: **the grid rule never applies in any browser.** `.cockpit-bands` computes
`display: block` at every viewport width (confirmed live via Playwright screenshots at
1900/1500/1100/900px — pixel-identical single-column stack at all four). This bug
predates TASK_136 (it's inside a comment written during TASK_134's token-replacement
pass) but was invisible until now: the old rule this silently defeated was
`display:flex; flex-direction:column`, and a `<div>` falling back to `display:block`
stacks children identically to a column flex — no visual symptom until TASK_136 swapped
the target to `display:grid`, which *is* visually distinct from block.

## Fix

1. Edit the comment near `web/styles.css:~1847` so it no longer contains a literal `*/`
   mid-comment — e.g. change `--text-*/--border` to `--text-*, --border` or spell it out
   as `--text-1/2/3`. Do not touch anything else in that comment or nearby rules.
2. **Verify live, in an actual rendered browser — not just by reading the CSS.** Start
   the app (the existing `uvicorn` on :8000 is fine, this is a static-file-only fix, no
   restart needed), load `/`, and confirm:
   - `.cockpit-bands` computes `display: grid` (check via devtools/computed style or an
     automated page-render tool if you have one available).
   - The 3-across row (Risk Dial / What changed / Shortlist) actually appears at a wide
     viewport (≥1500px), collapsing per the two breakpoints at 1500px and 1100px.
   - The single-scroll fix from TASK_136 still holds (it does not depend on this bug —
     do not touch it, just confirm it's undisturbed).
3. Paste evidence of the live check (not just "css now parses") into `DEV_HANDOFF.md`.

## Hard rules (unchanged from TASK_136 — still apply)

- No calculation, threshold, endpoint shape, or stored value may change. Nothing under
  `api/`, `etl/`, or `db/` may be touched.
- Do NOT touch `web/actionable.js` / `web/actionable.html` — unrelated uncommitted work.
- Do NOT reorder sections in `index.html`.
- No new tests — do not write or extend anything under `tests/`.
- No commits, no pushes.
- `node --check web/app.js` after any edit — file-integrity check, not a test, truncation
  is silent.

## Log

Append a `# Dev Handoff — TASK_136 round 2` section to `DEV_HANDOFF.md` below the
existing sections (do not overwrite them). Record the exact fix and the live-verification
evidence. End with `ALL_DONE`.

Archive this file to the next `AGENT_WORK_N.md` when done (check the project root for
the next free number — should be 43 unless a newer archive appeared).
