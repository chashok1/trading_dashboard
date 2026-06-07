<#
  install_claude_agents.ps1
  Installs the Developer + Tester subagents and the /dev-cycle orchestrator
  command at USER level so they're available in every project.

  Run from the agent-setup folder:
      powershell -ExecutionPolicy Bypass -File .\install_claude_agents.ps1

  Targets:
      $HOME\.claude\agents\developer.md
      $HOME\.claude\agents\tester.md
      $HOME\.claude\commands\dev-cycle.md
#>

$ErrorActionPreference = 'Stop'
$src        = $PSScriptRoot
$claudeRoot = Join-Path $HOME '.claude'
$agentsDst  = Join-Path $claudeRoot 'agents'
$cmdsDst    = Join-Path $claudeRoot 'commands'

New-Item -ItemType Directory -Force -Path $agentsDst | Out-Null
New-Item -ItemType Directory -Force -Path $cmdsDst   | Out-Null

$files = @(
    @{ From = (Join-Path $src 'agents\developer.md');   To = (Join-Path $agentsDst 'developer.md') }
    @{ From = (Join-Path $src 'agents\tester.md');      To = (Join-Path $agentsDst 'tester.md') }
    @{ From = (Join-Path $src 'commands\dev-cycle.md'); To = (Join-Path $cmdsDst   'dev-cycle.md') }
)

foreach ($f in $files) {
    if (-not (Test-Path $f.From)) { throw "Source file missing: $($f.From)" }
    Copy-Item -Path $f.From -Destination $f.To -Force
    Write-Host "  installed -> $($f.To)" -ForegroundColor Green
}

Write-Host "`nDone. User-level agents installed under $claudeRoot" -ForegroundColor Cyan
Write-Host "In any project, open the VS Code Claude terminal and run:  /dev-cycle" -ForegroundColor Cyan
Write-Host "Verify with:  claude   then   /agents" -ForegroundColor DarkGray
