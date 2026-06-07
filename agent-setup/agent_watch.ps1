<#
  agent_watch.ps1 — continuous watcher for Cowork-delegated tasks.

  Watches the project root for AGENT_WORK.md. When one appears (Cowork drops it),
  it runs Claude Code HEADLESS to:
    1. invoke the `developer` subagent to do the task (it archives AGENT_WORK.md
       -> AGENT_WORK_N.md and writes DEV_HANDOFF.md), then
    2. invoke the `tester` subagent ONLY if the task needs tests (auto-decided
       from the task / handoff text).
  When the Developer renames the file, the trigger clears until the next task.

  Permissions: SCOPED. Runs with --permission-mode acceptEdits (auto-accepts file
  edits) plus an explicit --allowedTools allowlist (git/python/pytest/psql + safe
  file utils). It will NOT run arbitrary commands outside that list.

  Start it (leave it running in a terminal):
      powershell -ExecutionPolicy Bypass -File .\agent_watch.ps1
  Stop it with Ctrl+C.
#>

param(
    [string]$Project    = 'C:\Ashok\Invest\Projects\trading-dashboard',
    [int]   $PollSeconds = 3,
    [int]   $DebounceMs  = 1500,
    [string]$Model       = 'sonnet'
)

$ErrorActionPreference = 'Stop'
$taskFile = Join-Path $Project 'AGENT_WORK.md'
$logFile  = Join-Path $Project 'agent_watch.log'

function Write-Log([string]$msg) {
    $line = "{0}  {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $msg
    $line | Tee-Object -FilePath $logFile -Append
}

# Verify the CLI is available
if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
    Write-Log "ERROR: 'claude' CLI not found on PATH. Open the VS Code terminal where 'claude' works, or set the full path."
    exit 1
}

# The headless orchestration prompt (auto-decide dev -> test).
$prompt = @'
A task has been delegated in AGENT_WORK.md in the current project. Do it NOW by
actually invoking the subagents with the Task tool — do not merely describe steps.

1. Use the `developer` subagent to implement the task in AGENT_WORK.md. It will
   archive the file to AGENT_WORK_N.md and write DEV_HANDOFF.md ending in
   "Status: READY_FOR_TEST".
2. Read DEV_HANDOFF.md (and the archived AGENT_WORK_N.md). Decide if tests are
   needed: if the task or handoff says "no tests", "nothing to test",
   "diagnostic only", "read-only", or "commit/push only", then SKIP testing.
   Otherwise use the `tester` subagent to validate and save its report verbatim
   to TEST_REPORT_N.md (matching N).
3. Print a one-paragraph summary: what ran, the verdict (or "no test needed"),
   and the artifact filenames produced.
'@

# Scoped allowlist for unattended runs (NOT skip-all).
$allowed = @(
    'Bash(git:*)','Bash(python:*)','Bash(python3:*)','Bash(pytest:*)',
    'Bash(psql:*)','Bash(node:*)','Bash(mv:*)','Bash(mkdir:*)','Bash(ls:*)',
    'Bash(cat:*)','Bash(tail:*)','Bash(head:*)','Bash(grep:*)','Bash(sed:*)',
    'Edit','Write','Read','Grep','Glob'
)

function Invoke-Cycle {
    Write-Log "AGENT_WORK.md detected -> running agents headless (model=$Model)..."
    Push-Location $Project
    try {
        & claude -p $prompt --permission-mode acceptEdits --model $Model --allowedTools $allowed 2>&1 |
            Tee-Object -FilePath $logFile -Append
        Write-Log "Cycle finished."
    } catch {
        Write-Log "ERROR during cycle: $_"
    } finally {
        Pop-Location
    }
}

Write-Log "Watcher started. Project=$Project  poll=${PollSeconds}s. Watching for AGENT_WORK.md (Ctrl+C to stop)."

$seen = $false
# Process one immediately if a task is already waiting.
if (Test-Path $taskFile) { $seen = $false }

while ($true) {
    try {
        $exists = Test-Path $taskFile
        if ($exists -and -not $seen) {
            Start-Sleep -Milliseconds $DebounceMs   # let the file finish writing
            if (Test-Path $taskFile) { Invoke-Cycle }
            # after the cycle the Developer should have renamed it; re-check
            $seen = Test-Path $taskFile
        } elseif (-not $exists) {
            $seen = $false
        }
    } catch {
        Write-Log "WATCH ERROR: $_"
    }
    Start-Sleep -Seconds $PollSeconds
}
