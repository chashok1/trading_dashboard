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
2. You MUST invoke the `tester` subagent (Task tool, subagent_type tester) after
   the developer — for EVERY task that changed code, NO exceptions (even tiny
   UI/CSS tweaks). The tester writes its own TEST_REPORT_<N>.md. After it returns,
   VERIFY that TEST_REPORT_<N>.md exists (N = the archived AGENT_WORK_<N>.md); if it
   is missing, invoke the tester again. Never finish a code task without a
   TEST_REPORT_<N>.md on disk.
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
        # Stream live: print mode only streams with --output-format stream-json --verbose.
        # We parse each JSON event into a readable progress line (assistant text, tool calls, result).
        & claude -p $prompt --verbose --output-format stream-json --permission-mode acceptEdits --model $Model --allowedTools $allowed 2>&1 |
            ForEach-Object {
                $line = $_; $out = $null
                try {
                    $o = $line | ConvertFrom-Json -ErrorAction Stop
                    switch ($o.type) {
                        'assistant' {
                            foreach ($c in $o.message.content) {
                                if ($c.type -eq 'text' -and $c.text) { $out = $c.text.Trim() }
                                elseif ($c.type -eq 'tool_use') {
                                    $arg = if ($c.input.file_path) { $c.input.file_path }
                                           elseif ($c.input.command) { $c.input.command }
                                           elseif ($c.input.pattern) { $c.input.pattern }
                                           else { '' }
                                    $out = "  -> $($c.name) $arg".TrimEnd()
                                }
                            }
                        }
                        'result' { $out = "[done] " + $o.result }
                        default  { }
                    }
                } catch { $out = $line }   # non-JSON (stderr) -> pass through
                if ($out) { $out }
            } |
            Tee-Object -FilePath $logFile -Append
        Write-Log "Cycle finished."
    } catch {
        Write-Log "ERROR during cycle: $_"
    } finally {
        Pop-Location
    }
}

$queueDir = Join-Path $Project 'agent_queue'
New-Item -ItemType Directory -Force -Path $queueDir | Out-Null
Write-Log "Watcher started. Project=$Project poll=${PollSeconds}s. Bare task: AGENT_WORK.md | Queue: agent_queue\*.md (Ctrl+C to stop)."

while ($true) {
    try {
        if (Test-Path $taskFile) {
            # A task is staged as AGENT_WORK.md (manual drop OR pulled from the queue). Process it.
            Start-Sleep -Milliseconds $DebounceMs   # let the file finish writing
            Invoke-Cycle
            # Developer should rename AGENT_WORK.md -> AGENT_WORK_N.md. If it lingers
            # (failed run), retire it so we never reprocess the same task in a loop.
            if (Test-Path $taskFile) {
                $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
                Move-Item $taskFile (Join-Path $Project "AGENT_WORK.unhandled-$stamp.md") -Force
                Write-Log "WARN: AGENT_WORK.md not archived by the run; retired as AGENT_WORK.unhandled-$stamp.md"
            }
        } else {
            # No active task -> pull the NEXT queued task (alphabetical; name them 01-, 02-, ...).
            $next = Get-ChildItem -Path $queueDir -Filter '*.md' -File -ErrorAction SilentlyContinue |
                    Sort-Object Name | Select-Object -First 1
            if ($next) {
                Write-Log "Dequeue: $($next.Name) -> AGENT_WORK.md"
                Move-Item $next.FullName $taskFile -Force   # picked up on the next loop pass
            }
        }
    } catch {
        Write-Log "WATCH ERROR: $_"
    }
    Start-Sleep -Seconds $PollSeconds
}
