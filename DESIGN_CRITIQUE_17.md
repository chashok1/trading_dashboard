# Design Critique — DESIGN_SPEC_17 (Builder review)

Critique only. DESIGN_SPEC_17.md and the app code were not changed. All claims were checked by reading `web/builder.js`, `web/builder.html`, `web/builder_plan.js`, `etl/plan_check.py`, `etl/plan_store.py`, `etl/builder_data.py`, `api/routers/builder.py`, `web/actionable.js`, plus one read-only row count on the five Builder tables. Nothing was run in a browser.

## Overall verdict

**Mostly right, and the direction is right.** The facts hold up. The 3-step flow fits the user's wish. Three things need to change before a developer starts:

1. It plans to **delete `builder_plan.js`**, but that file is already most of the "Limits" card and the "Plan to buy / Buy one of these" buttons the spec asks for. Reuse it. Don't rebuild it.
2. It **missed two bugs that save work to the wrong place**: picks carry over when you switch account, and Buy $ amounts can be filled in for you.
3. It **ranks the "tell me" part too low.** The user's main ask is "notify me when I hit a limit". The Actionable notice (T6) should come second, not sixth.

---

## 1. Fact check

| # | Spec claim | Verdict | Evidence |
|---|---|---|---|
| F1 | `builder_plan.js` is loaded by no page | **CONFIRMED** | `builder.html` loads only `_common.js`, `portfolio_mix.js`, `builder.js`, `warning_badge.js`. Its markup (`plCls`, `plOpt`, `plMake`) is not in the HTML and never was in git. The file is untracked. |
| F2 | `GET /api/builder/plan` and `/plan/states` have no other caller | **CONFIRMED** | Only `builder_plan.js` calls them. |
| F3 | No button to accept and freeze a model portfolio | **CONFIRMED** | Nothing in `builder.js` calls `POST /api/builder/portfolios`, `/compare`, `/backtest` or the keep endpoints. Roll-over can only be reached from the detail view of an existing portfolio, and none exist. |
| F4 | Nothing is stored yet | **CONFIRMED** | `user_plan`, `user_plan_pick`, `user_builder_set`, `user_model_portfolio`, `user_my_stock` all have 0 rows. |
| F5 | Every Target box is pre-filled from holdings | **CONFIRMED** | `seedTargets` fills beta, low/high beta, Quad, every sector and every style from `exposure.held`. |
| F6 | Saved limits get replaced on reload, depending on which request returns first | **CONFIRMED** (by reading the code) | On an account change, `S.seeded` is cleared. If the saved plan arrives first, `planApply` starts a second preview, the first is thrown away, and `seedTargets` then overwrites `S.targets`. If the preview arrives first, the saved plan wins. Asset classes are safe because they live in `S.mix`. Only the optional limits are lost. |
| F7 | Two % bases | **CONFIRMED** | `builder_data.exposure` divides by invested money only (no cash). `plan_check._line_rows` multiplies by account value. The grid header even says "% of the invested money". |
| F8 | Hidden non-equity "sector" lines are saved | **CONFIRMED, and worse than stated** | `exposure` uses the asset class as the "sector" of a non-equity holding. The grid hides those rows, but `planFromState` sends every `sector:` key. **Also missed:** the key `Equities` (equities with no sector, shown as "No sector") and `Unmapped` are saved as sector limits too. |
| F9 | Activate is likely refused ("Sectors add to …, more than Equities") | **CONFIRMED by logic, UNVERIFIED on screen** | Seeded sector keys add to about 100% of invested money. They are compared with an Equities % of the account. This fails on any account that is not about 100% equities. |
| F10 | Save draft changes live buys | **CONFIRMED** | `save_draft` calls `sync_buy_picks`, but the message says "The active plan has not changed." |
| F11 | Amounts typed in To do are reverted by the next save | **CONFIRMED** | `PATCH /pick/{id}` updates only `user_plan_pick`. The next save runs `sync_buy_picks` from the grid's `amt`. |
| F12 | Activate saves a draft first, then asks | **CONFIRMED** | `planActivate` calls `planSave(true)` before the dry run. A refused or cancelled Activate has already changed the draft and the buys. |
| F13 | `openSet` switches account without loading its plan | **CONFIRMED** | It sets `S.acct` and `S.seeded` but never calls `planLoad`. |
| F14 | A buy is checked only if it has an amount, a Buy call and is ticked | **CONFIRMED, plus one more step** | New BUY rows are always inserted with `ticked = FALSE`, and the tick box is disabled while there is no Buy call. So the user can't even pre-tick. |
| F15 | Actionable warns only when a line is already full | **CONFIRMED** | `plan_check_page` flags a Buy call only when `left <= 0`. It does not use planned amounts (`used` is empty). |
| F16 | Holdings alone breaking a sector/style/beta limit gives no Actionable notice | **CONFIRMED** | Only asset class sells make rows. Other overages exist only as a note line at the bottom of To do. |
| F17 | Beta counts all classes in the grid, equities only in the check | **CONFIRMED, and style has the same problem (missed)** | `exposure` counts style tags across every class. `now_lines` counts styles for equities only. |
| F18 | Warnings card, `S.horizon`, `S.useDial` do nothing for the plan | **CONFIRMED** | `S.warn` only travels in the preview request, and `horizon` has no control. |
| F19 | Quad targets and Portfolio beta target are never saved | **CONFIRMED** | `planFromState` reads only `lowbeta`, `highbeta`, `sector:`, `style:`. |
| F20 | No leave-page warning | **CONFIRMED** | There is no `beforeunload`, and account or date changes don't ask. |
| F21 | Docs out of date (Plan/To do tabs, Actionable column "not built") | **CONFIRMED** | `docs/portfolio_builder_logic.md` lines 78 and 87. |
| F22 | F-A Technology 93% vs 47%; IRA sector sum; F-M 3.1% no sector | **UNVERIFIED** | Not re-run. Plausible given F7. |

**Section verdict: accurate.** No claim was found wrong.

---

## 2. What the spec missed

Ranked by harm.

| # | Problem | Effect | Where |
|---|---|---|---|
| M1 | **Picks carry over when you switch account.** `acctSel.onchange` resets targets, mix and amount, but not `S.picks`. | If the new account has no saved plan, the old account's picks stay on screen. Save draft then writes them as **the new account's planned buys**. It also stops the "tick held names" step for the new account. | `builder.js` `init` (acctSel handler) |
| M2 | **Buy $ can be filled in for you.** Auto-tick, then "Match my holdings", then `fillBuyGaps` sets each pick's Buy $ to its gap from the model. With a saved plan (preset = custom), these gaps are real money. | Planned buys the user never typed. They go live on the next Save draft. Whether it happens depends on request order. | `builder.js` `loadSourceNames`, `matchHoldings`, `fillBuyGaps` |
| M3 | **Changing the date or pressing Refresh reloads the saved plan over unsaved edits.** `reloadAll` calls `planInit`, then `planLoad`, then `planApply`. | Silent loss (S2 says "dropped", but it is actually replaced). | `builder.js` `reloadAll` |
| M4 | **Two meanings of "high beta".** The Offensive style group includes the *tag* "High Beta". The beta line uses *measured* beta over 1.2. | "High beta 10%" can mean two different things, and Offensive overlaps with High beta. | `FLAVOURS`, `plan_check.now_lines` |
| M5 | **Sell ticks never expire.** A ticked SELL row stays forever. When its class is no longer over plan, it is ignored. If the class goes over again months later, the old tick comes back as "expected cash". | Ghost cash. | `plan_store.add_pick`, `plan_check.todo` |
| M6 | **Buys are matched by their set of names.** Changing a group (adding MSFT to AAPL) deletes the row and makes a new unticked one. Any BUY row made another way is deleted on the next save. | Lost ticks. A trap for T7 if buys are created directly. | `plan_store.sync_buy_picks` |
| M7 | **Blank asset class box means 0, not "no number".** `setAssetTarget` turns `''` into 0. | Fine for a required line, but the spec should say a blank class box is an error, not a silent 0. | `builder.js` `setAssetTarget` |

---

## 3. The proposed flow and tasks

### What is right
- Account first, then limits, then stocks. One basis (% of the whole account). Blank means no limit. These all match the wish.
- Removing the paper-portfolio left-overs, saved sets and the Amount box is safe, because nothing is stored.
- Counting a planned buy as soon as it has an amount is the fix that makes "all limits validated" true.

### What I would do differently

**D1. Reuse `builder_plan.js`. Don't delete it (changes T2, T4, T7).** It already has:
- the asset class boxes with a Cash box and a "100% ✓ / must be 100" total;
- optional beta, sector and style boxes that start blank ("Open"), with "Held" shown as % of the account (from `plan_page`, so it uses the one correct basis);
- "Start from: what this account holds / copy another account's plan";
- "Add as pick / Make a buy-one-of group" buttons that write buy rows directly.

Its holes are known: there is no HTML, it has the draft/activate split, and it lacks the names filters. Moving its Plan pieces into the new column 1 and its pick buttons into column 2 is a smaller job than writing them again. The spec's T4 and T7 drop from Medium to Small.

**D2. Split T1 into a bug-fix task that ships first.**
- T0: stop the reload overwrite (F6), reset picks on account change (M1), stop auto-filled Buy $ (M2), and stop date/Refresh overwriting edits (M3).
- These are a few lines each and protect saved work today, before any redesign.
- The basis change and pre-fill removal stay in T1.

**D3. Move the "tell me" work up.** The user said "when I start buying… I must be notified". Real buys show up as a new positions file, not as typing in the Builder. So the key notice is "**your holdings now break a limit**" (F16), seen away from the Builder. Rank T6 second, after T0/T1.

Also use the existing status-bar warning badge (`warning_badge.js`, already on every page including the Builder) for "IRA: Info Tech over its 10% limit". The amber "My plan" chip only helps if you are on Actionable with that chip in view. This is the one place where adding something beats the spec's "no new table, no email" stance. It is still no email.

**D4. "Near" should apply to ceilings only.** The spec's line states give every line OK / Near / Over at 90% used. But asset classes are two-sided targets. Equities at 46% of a 50% target is "on track", not a warning. Rule:
- optional limits are OK / Near / Over;
- asset classes are Room / On plan / Over, as today, using the existing $500.

**D5. Say what cash counting means.** If every planned buy counts as soon as it has an amount, buys with no Buy call today also use up "cash you can spend". Later buys then show "Cut" or "Blocked" for money that is not being spent today. Keep counting them against the % limits. For cash, show it as "if you buy everything planned" and don't use the word "Blocked" unless the buy has a Buy call today.

**D6. Drop "Pause checks" for now.** The user did not ask for it. With one Save, "no plan" plus the existing Turn off endpoint covers it. Keep the button only if it costs nothing. Don't design new states (pill text, chip rules) around it.

**D7. Name the beta meaning on screen.** "High beta = measured beta over 1.2 (not the 'High Beta' style tag)". Put it in the row tooltip, and use the same rule in Now and the check (fixes M4).

### What is over-built
- Three "Now / After buys / Room / state" columns, plus a bar, plus a sentence per buy. It's fine, but build the table first and add the bar later.
- "Copy other account's plan" is free if D1 is taken. Don't build it fresh.
- A "Show lines with no limit" link and the "Add sector" picker. One list of every sector the account holds, with blank boxes, is enough.

### What is risky
- **T5 replaces three cards at once.** Ship it behind the old To do block for one round, or at least keep `/api/builder/todo` working, since Actionable's logic shares the same `plan_check` code.
- **The what-if endpoint** (`plan_check.todo` on the typed, unsaved plan) is new API surface. It's fine, but it must not write anything. That is easy to break if it reuses `save_draft`.
- **Changing `user_plan` from draft/active to "saved + checks on"** while `plan_check_page` reads `active`. Simplest path: Save writes both `draft` and `active` (as Activate does now) and the UI stops showing draft. No schema change is needed.

**Section verdict: good flow, wrong build route.** Reuse what exists, fix the save bugs first, and move notifications up.

---

## 4. Open questions

| Spec question | Verdict | Why |
|---|---|---|
| One "Save plan"? | **Decide it, don't ask** | It follows directly from the user's "natural flow" wish and three overlapping saves. Recommend yes. |
| Hide paper model portfolios? | **Keep as a question** | It removes a whole feature the user paid for over rounds 9–11. That is the user's call. |
| Count planned buys without a Buy call? | **Keep, but reword** | Add the cash consequence (D5) so the user knows what "yes" means. |
| Optional limits as ceilings only? | **Decide it, don't ask** | The user's words ("reach 10%", "above 50%", "above 10%") are all ceilings. |

That leaves two real questions. If a third is wanted: **"Should a broken limit also show on the status-bar warning badge on every screen?"** (recommend yes, see D3).

---

## 5. Does it meet the user's wish?

| Wish | Met? | Note |
|---|---|---|
| Everything by account | **Yes** | Removing "Whole book" makes it strict. M1 must be fixed or picks leak between accounts. |
| Only asset class % required | **Yes** | Optional boxes start blank. A blank class box should be an error (M7). |
| Optional sector / style / beta, e.g. IT 10%, high beta 10% | **Yes**, after the one basis fix and D7 | |
| Pick one stock, a group, or none | **Yes** | Use the `builder_plan.js` buttons (D1). |
| Natural order: account, limits, stocks | **Yes** | The 3-column layout does this. |
| ALL limits checked when buying, and I am notified | **Partly** | The Builder side is complete. Away from the Builder it relies on an Actionable chip only, and it ranks this sixth. With D3 (holdings-based check, warning badge, ranked second) it is fully met. |

**Section verdict: meets the wish once notifications are moved up and made visible on every screen.**

---

## 6. Ranked list of changes to the spec

1. **Add T0, the save-safety fixes:** reload overwrite (F6), picks carry over between accounts (M1), auto-filled Buy $ (M2), date/Refresh overwrite (M3). Smallest change, protects data.
2. **Reuse `builder_plan.js`** for the Limits card, Start from, and the pick buttons. Replace "delete it" in T2 and shrink T4 and T7.
3. **Move T6 to second place** and widen it: a holdings-only overage on any line goes to the status-bar warning badge plus the "My plan" chip.
4. **Line states:** Near/Over for ceilings only. Asset classes keep Room / On plan / Over (D4).
5. **Add the missed basis gaps to T1:** style counted on equities only in both places (F17), and drop the `Equities`/`Unmapped` sector keys (F8).
6. **State the cash rule** for planned buys with no Buy call (D5).
7. **Say which "high beta"** on screen (D7 / M4).
8. **Add sell-tick expiry** next to the "Done?" button for bought stocks (M5). Clear a sell tick when its holding is gone or its class is back on plan.
9. **Cut "Pause checks" and the extra "Show lines with no limit" / "Add sector" parts** unless they are free.
10. **Cut open questions to two** (hide model portfolios; count buys without a Buy call). Decide the other two.
