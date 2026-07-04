# TASK_107 — Actionable: keyboard support + focus mode v2

Source: `docs/audit/actionable_screen_review.md` — U8.
Prereq: TASK_106 done. Queue: 104 → 105 → 106 → **107** → 108 → 109 → 110.

Goal: make focus mode a genuine rapid-triage tool and fix modal keyboard gaps.

Files expected to change: `web/actionable.js`, `web/actionable.html` (focus
card hint text).

## Items

1. **Escape closes the drilldown modal** (currently only focus mode reacts to
   Esc). Reuse the existing `_closeModal()`; guard so Esc closes the topmost
   layer only (atomic popover → modal → nothing).
2. **Focus-mode keys** — active only while `#focusBackdrop` has `.open`, and
   ignored when the event target is an input/select/textarea:
   - Enter or D → Done (logs Final Call code, same as the button)
   - S → Skip
   - Z → Snooze
   - → or N → next
   - ← or P → previous
   - Esc → close (existing)
3. **Prev button** beside "Next ›" (`state.focusIdx` decrement, floor 0).
4. **Key hints** in small text at the card bottom (replace the current
   "Esc or ← Back to grid" line with e.g.
   "Enter Done · S Skip · Z Snooze · ←/→ Prev/Next · Esc Close").

## Guardrails

- Verify on Windows: `node --check web/actionable.js`, `tail -10`.
- Don't leak key handlers: single delegated `keydown` listener with the
  backdrop-open guard, not per-open listeners.
- Log in `DEV_HANDOFF.md`, end `ALL_DONE`. No commit; no tester.

## How to verify

1. Triage 3 rows start-to-finish using only the keyboard (Done, Skip,
   Snooze, arrows); progress counter and card content advance correctly;
   actions land in `user_action_log`.
2. ← at the first card stays on card 1; → at the last stays on the last.
3. Open drilldown → Esc closes it. Open drilldown → open atomic popover →
   Esc closes the popover first, second Esc closes the modal.
4. With focus mode closed, D/S/Z typed into the symbol search box filter text
   normally (no accidental actions).
5. `node --check` passes on Windows; console clean.
