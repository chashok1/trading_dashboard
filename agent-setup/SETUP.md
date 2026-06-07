# Developer + Tester agent workflow (Claude Code / VS Code terminal)

A two-agent loop where **Cowork delegates a task in `AGENT_WORK.md`**, a **Developer**
agent implements it (and archives the task to `AGENT_WORK_N.md`), and a **Tester**
agent validates it and reports. Both pinned to **Sonnet**.

## The one constraint that shapes the design

In Claude Code a **subagent cannot invoke another subagent** — nesting is blocked
by design. So the Developer cannot literally "call" the Tester. The industry
standard fix is an **orchestrator**: a `/dev-cycle` slash command you run once in
the main terminal session that drives Developer -> Tester -> (loop on failure).
Same end result, reliable. (Hooks can only *print* a suggestion to run the next
step; they can't auto-spawn an agent.)

## What gets installed (user level: `~/.claude/`)

| File | Role |
|------|------|
| `~/.claude/agents/developer.md` | Developer agent (Sonnet; Read/Write/Edit/Bash/Grep/Glob) |
| `~/.claude/agents/tester.md`    | Tester agent (Sonnet; **read-only** Read/Bash/Grep/Glob — no Edit/Write) |
| `~/.claude/commands/dev-cycle.md` | `/dev-cycle` orchestrator command |

## Install

From this `agent-setup` folder, in PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\install_claude_agents.ps1
```

Then verify in any project: open the VS Code Claude terminal, run `claude`, then `/agents`.
You should see `developer` and `tester`.

## Daily use

1. **Delegate.** Cowork (or you) writes the task into `AGENT_WORK.md` in the project
   root. Use `AGENT_WORK.template.md` as the shape.
2. **Run the cycle.** In the project's Claude terminal:
   ```
   /dev-cycle
   ```
   (optionally `/dev-cycle 5` to allow up to 5 fix iterations).
3. The orchestrator:
   - runs **developer** -> implements, renames `AGENT_WORK.md` -> `AGENT_WORK_N.md`, writes `DEV_HANDOFF.md`
   - runs **tester** -> runs the checks, writes `TEST_REPORT_N.md`
   - if FAIL and iterations remain -> writes a new `AGENT_WORK.md` with the fixes and loops
   - stops on PASS or when iterations run out, then summarizes.

## Artifacts produced per task

```
AGENT_WORK.md          (input; consumed)
AGENT_WORK_1.md        (archived task)
DEV_HANDOFF.md         (developer -> tester contract)
TEST_REPORT_1.md       (tester verdict + evidence)
```

## Why this matches industry practice

- **Single-responsibility agents** with least-privilege tools (Tester is read-only,
  so it can never "fix" its way to a green result — a common multi-agent failure mode).
- **Explicit orchestrator** owns sequencing and the full context, instead of fragile
  agent-to-agent chaining.
- **File-based handoff** (`DEV_HANDOFF.md` / `TEST_REPORT_N.md`) gives a durable,
  auditable trail and survives context resets.
- **Verify-don't-trust** Tester checks the work against acceptance criteria, not just
  "does it run".

## Optional: hook signal (visibility only)

If you want a printed nudge when the Developer finishes, add to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "SubagentStop": [
      { "matcher": "developer", "hooks": [
        { "type": "command", "command": "echo Developer done -> running Tester next." } ] }
    ]
  }
}
```

This only prints; the `/dev-cycle` command still does the real orchestration.

## Tuning

- Want the Tester able to save its own report file? Add `Write` to its `tools` and
  tighten the prompt to "only ever write `TEST_REPORT_*.md`". The stricter default
  has the orchestrator persist the report instead.
- Want a different model per agent? Change `model:` in each agent file (`opus`,
  `sonnet`, `haiku`, or `inherit`).
