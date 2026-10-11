# Test Report — AGENT_WORK_42

## Verdict
FAIL

## What I ran
- Read `DEV_HANDOFF.md` (TASK_136 section), `AGENT_WORK.md`, `agent-tasks/TASK_136_cockpit_grid_layout.md`, `web/styles.css`, `web/app.js`, `web/index.html` — direct inspection.
- `git status`, `git log --oneline -5`, `git diff --stat -- api/ etl/ db/`, `git diff --stat -- web/actionable.js web/actionable.html`, `git diff -- web/actionable.js` — scope/commit verification.
- `powershell Get-ChildItem ... LastWriteTime` on all `web/*.js|*.html|*.css` and the touched `api/etl/db` files — mtime cross-check (no test framework involved, direct filesystem inspection).
- `node --check web/app.js` — passed.
- Brace-balance check on `web/styles.css` (Python script, comment/string-aware) — 607 open / 607 close, globally balanced.
- Started nothing myself — an existing `uvicorn` instance was already live on `127.0.0.1:8000` (verified `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/` → `200`). Used it directly (no server restart needed since this round only touched static `web/` files).
- **Live rendering via Playwright (Chromium)** at 1900px, 1500px, 1100px, 900px viewports against the running server: screenshots + `getComputedStyle`/`getBoundingClientRect` probes of `.cockpit-bands`, `.cockpit-band`, each band's `#id`, and a CSSOM walk of `document.styleSheets` (including nested `@media` rules) to find exactly which parsed CSS rules apply to `.cockpit-bands`.
- Isolated CSS reproduction (`playwright` + minimal `<style>` snippets) to bisect which part of `web/styles.css` causes the anomaly found live.
- Manual `curl http://127.0.0.1:8000/static/styles.css` to confirm the server is serving the exact file on disk (ruled out caching).

## Evidence

### Check 1/2 — Grid conversion + Pitfall 1 (`minmax(0,1fr)` / `min-width:0`) — **BROKEN AT RUNTIME**
The CSS *source* at `web/styles.css:1857-1896` is exactly as specified: `grid-template-columns: repeat(12, minmax(0, 1fr))`, correct `grid-template-areas` for all 4 rows, `#regimeBand/#riskDialBand/#eventsBand/#shortlistBand/#factorScorecardBand/#housekeepingBand { grid-area: ... }`, the two breakpoints at 1500px/1100px, and `.cockpit-band { min-width: 0; ... }`.

**But in the live, rendered browser this rule never applies.** `getComputedStyle(document.querySelector('.cockpit-bands')).display` returns `"block"` (not `"grid"`) at every viewport width tested (1900/1500/1100/900px), and `gridTemplateColumns`/`gridTemplateAreas` both compute to `"none"`. A CSSOM walk (including nested `@media` rules) confirms the base `.cockpit-bands { display: grid; ... }` rule (the one at line 1857, *not* inside any media query) is **entirely absent from the parsed stylesheet** — every rule before and after it (`.qf-arrow-neutral`, `#regimeBand`, `#riskDialBand`, ..., the two `@media` blocks, `.cockpit-band`, `.cockpit-band h2`, etc.) parses and applies correctly; only this one rule is missing.

**Root cause, isolated and reproduced in a minimal repro:** the comment block immediately preceding the rule (`web/styles.css:1843-1849`, the "===== Dashboard cockpit (TASK_133/134) =====" comment) contains the literal substring `--text-*/--border` inside its prose (part of `--bull/--bear/--warn/--ok/--accent/--text-*/--border/--act-*`). `*/ ` there is a **premature CSS comment terminator** — the browser's CSS tokenizer closes the comment right there, then treats everything from that point through the end of that same intended comment (`-border/--act-*) so the cockpit shares the app's palette instead of reading as a different product bolted on. See docs/dashboard_cockpit_design.md. */`) as live CSS. That fragment contains an unmatched `)`, which invalidates the "selector" being accumulated for the next rule — and per standard CSS error recovery, the browser drops the entire next qualified rule (selector *and* declaration block), which is exactly `.cockpit-bands { display: grid; ...}`. Parsing correctly resynchronizes afterward (the very next comment, `/* TASK_136 A.2/A.3 ... */`, has no such collision and closes normally), which is why every subsequent rule parses fine and only this one is silently eaten.

Confirmed via a minimal isolated repro (`<style>` containing only the exact comment text + the rule): reproduces `display: block`. Removing that one comment (or just the `.cockpit-bands`-adjacent one) while keeping the rule reproduces `display: grid` correctly.

**This bug pre-dates this round** — the comment text (and the `--text-*/--border` landmine) matches TASK_134's own `DEV_HANDOFF.md` prose describing that round's token-replacement work, not anything TASK_136 wrote. It was invisible before TASK_136 because the *old* rule at that position was `display: flex; flex-direction: column` — and a `<div>` with `display:block` (the accidental fallback once that rule is silently dropped) visually stacks its `<section>` children identically to `display:flex; flex-direction:column`, so the bug produced no visible symptom until TASK_136 changed the target `display` value to `grid`, which is visually distinct from `block`. TASK_136 did not introduce the landmine, but TASK_136 is the round whose entire deliverable is silently defeated by it, and the developer's own "How to test" section explicitly defers the live-render check to the tester rather than claiming to have done it — so this is a real gap this round needed to catch and did not.

**Live visual proof:** screenshots at 1900px and 1100px are pixel-layout-identical (both single-column, one band per row, in DOM order) — there is no 3-across row, no 2-column mid state, and no visual change at all across any of the four tested widths. `.cockpit-band` itself does correctly compute `min-width: 0` and the new `padding: 8px 12px` (that rule is unaffected, since it sits after the resync point), so Pitfall 1's *second* half is live; the first half (`minmax(0,1fr)` on the grid track) never executes because the grid never exists.

### Check 3 — Pitfall 2 (double scrollbar) — verified independently of the grid bug, PASSES
- `web/styles.css` — confirmed: `body.dash-page` was removed from the shared "lock main" selector list (~line 814, now lists only `fill-page/rules-page/trig-page/ref-page/perf-page/portfolio-page`), and the standalone `body.dash-page .cockpit-bands { flex:1; ... overflow-y:auto }` rule is gone (only `body.dash-page .side-stack { overflow-y: auto; ... }` remains, an unrelated element).
- Live: `getComputedStyle(document.querySelector('.cockpit-bands')).overflowY` = `"visible"` at every width (it never scrolls independently); `main`'s `scrollHeight` (1578–1810px depending on width) exceeds its `clientHeight` (1008px), confirming `main` is the one element that actually needs to and does scroll. This part of the fix is real and correct, and is unaffected by the CSS-parsing bug above (that bug is scoped to a completely different, unrelated rule ~1000 lines earlier in the file).
- Note: the app hides the native scrollbar affordance everywhere (`main::-webkit-scrollbar { display: none }`, pre-existing, not part of this task) so "one scrollbar" is a functional claim (one scrolling container) rather than something visibly countable — consistent with the rest of the app.

### Check 4 — Content additions — PASS
- Screenshot + live DOM: Factor scorecard shows `WT% | FLOWS | VERDICT | VS MKT 1W | VS MKT 3W | VS MKT 1M | VS MKT 2M | VS MKT 3M` — all five delta columns render with sign-colored values (e.g. Health Care: -0.7%/-0.2%/-1.1%/-12.2%/-22.4%, all red/negative; Industrials: +1.4%/+6.1%/+7.0%/+1.5%/+4.3%, green/positive).
- Row `title` attribute confirmed present and correct: `"1w: you 0.0% / mkt 0.7%\n3w: you 0.0% / mkt 0.2%\n..."` — raw values reachable on hover as specified.
- Shortlist: each row shows the pre-multiplied `$` figure as the primary number with `AMT$ <raw> × <mult>` beneath in the smaller sub-line, e.g. `ACHC ... $41,910` / `AMT$ 53,050 × 0.79`. Matches spec's C.2 example format exactly.
- Both additions work correctly *despite* the layout bug above — they are `app.js`/DOM content, not dependent on the broken grid rule.

### Check 5 — No reordering — PASS
DOM order in `web/index.html` (lines 120/125/130/135/145/150): `riskDialBand`, `eventsBand`, `regimeBand`, `factorScorecardBand`, `shortlistBand`, `housekeepingBand` — matches DEV_HANDOFF's claimed "dial, events, regime, score, short, house" order, and matches what's visibly rendered top-to-bottom in the (currently non-grid) fallback layout. `index.html` mtime (17:37:40) predates this round's `app.js`/`styles.css` edits (20:11/20:13), consistent with the developer's claim of only reading it, not editing it.

### Check 6 — No scope violations — PASS
- All files under `api/`, `etl/`, `db/` touched by prior rounds (TASK_133/134) show mtimes ≤ 17:33:26 — strictly before this round's `web/app.js` (20:11:43) and `web/styles.css` (20:13:01) edits. None of these files were modified after this round began.
- `web/actionable.js`/`web/actionable.html` mtimes (16:39:07 / 16:39:24) also predate this round's edits. `git diff -- web/actionable.js` shows exactly the sector/style-filter-chip diff (`renderSectorSummary`, `renderStyleSummary`, `state.filters.sector/style`) that TASK_133/134's own handoff already disclosed as pre-existing, unrelated, uncommitted user work — no cockpit/grid content in that diff.

### Check 7 — Integrity — PASS (with the caveat above)
- `node --check web/app.js` → passes, no output (clean).
- `web/index.html` has no inline `<script>` blocks to check (only external `<script src=...>` tags) — nothing to run `node --check` against there.
- Brace balance in `web/styles.css`: 607 `{` / 607 `}` — globally balanced. (This check does **not** catch the bug found above, because that bug is a comment-termination error, not a brace mismatch — the dropped rule's own braces are still counted as balanced, they're just attached to a corrupted/invalid preceding "selector".)

### Check 8 — No commits — PASS
`git log --oneline -5` top commit is still `8fb4a91` (same as the session's starting `gitStatus`) — unchanged.

## Failures & gaps
- **Critical:** `web/styles.css` — the `.cockpit-bands { display: grid; ... }` rule (line 1857) is silently dropped by every standards-conformant browser due to a premature comment terminator in the immediately preceding comment (line ~1847, the substring `--text-*/--border`). Net effect: **the entire grid conversion — the core deliverable of TASK_136 — does not render.** The page displays as a plain single-column block stack (indistinguishable from the pre-TASK_136 layout) at every width tested (1900/1500/1100/900px); there is no 3-across row, no 2-column intermediate state, and the two `@media` breakpoint rules are inert (they only ever modify `grid-template-areas`/`grid-template-columns`, which have no effect without `display: grid`).
- This landmine pre-dates TASK_136 (traced to TASK_134's own token-replacement comment) and was invisible before because the old `display: flex; flex-direction: column` value it silently defeated produces the same visual result as the accidental `display: block` fallback. TASK_136 is the first round where this landmine has a real, breaking effect, and it went uncaught because the developer's own testing section defers all live-rendering verification to the tester (per the task's "no tests" constraint) rather than performing/reporting one themselves.
- Minimal fix (not applied — QA does not edit source): break up the comment so no `*/ ` sequence appears inside it, e.g. change `--text-*/--border` to `--text-*, --border` or `--text-1/2/3` (matching how the same token list is phrased in `DEV_HANDOFF.md`'s own prose, which uses `--text-1/2/3` without the collision).

## Acceptance criteria check
- `/` renders as the A.2 layout at ≥1500px, two columns at ≤1500px, one column at ≤1100px — **NO.** Verified live: identical single-column block-stack layout at 1900/1500/1100/900px; the grid never activates (see Failures above).
- No horizontal scrollbar at any width; exactly one vertical scrollbar — **PARTIAL.** Vertical: yes, exactly one scrolling container (`main`), confirmed both in CSS and live. Horizontal: a horizontal-scroll condition *does* exist below ~1564px viewport width, but it is caused by the pre-existing header nav (`.nav-menu`, which does not shrink/wrap below ~1320px) and reproduces identically on `/actionable` (unrelated page, not touched by this task) — this is a real, pre-existing, out-of-scope issue, not something TASK_136 introduced in `.cockpit-bands` itself (which does correctly track viewport width with no overflow of its own).
- On 1920×1080, regime + the three-card row + the scorecard visible without scrolling — **NO** (there is no three-card row; everything is a single stacked column, so this can't be evaluated as intended — trivially "more" than 3 bands are below the fold at 1920×1080 because bands never share rows).
- Scorecard shows five delta columns; shortlist shows pre-multiplied size — **YES**, both render correctly and match spec.
- `node --check web/app.js` passes — **YES.**

## Recommendation
SEND BACK TO DEVELOPER — specific fixes needed:
1. Fix the premature CSS comment terminator in `web/styles.css` around line 1843-1849 (the `--text-*/--border` substring inside the "Dashboard cockpit (TASK_133/134)" comment prematurely closes the comment with `*/`, which silently drops the very next rule — the entire `.cockpit-bands` grid declaration). This is the single blocking issue; once fixed, re-verify live in a browser (not just by reading the CSS source) that `.cockpit-bands` computes `display: grid` and that the 3-across / 2-col / 1-col responsive behavior actually appears at 1900/1500/1100px, per the task's own explicit instruction to render and look at the page.
2. Re-confirm, after the fix, that the "Done when" checklist items (3-across at ≥1500px, all bands visible without scrolling at 1920×1080) actually hold — they could not be evaluated as intended this round because the grid never activated.
3. (Informational, out of scope for TASK_136, no action required from this task) The header nav bar (`.nav-menu`) causes horizontal scroll below ~1320px viewport width on every page, not just `/` — flagged for awareness, not a regression from this round.
