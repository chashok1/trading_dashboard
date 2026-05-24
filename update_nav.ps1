# Update navigation menus in all HTML files to include File Monitor link

$files = @(
    'web\cockpit.html',
    'web\actionable.html',
    'web\portfolio.html',
    'web\rules.html',
    'web\groups.html',
    'web\rule_performance.html',
    'web\trace.html',
    'web\explore.html',
    'web\ref.html',
    'web\dbstats.html',
    'web\trig.html',
    'web\composite_edit.html'
)

foreach ($file in $files) {
    $path = Join-Path $PSScriptRoot $file
    if (Test-Path $path) {
        $content = Get-Content $path -Raw

        # Replace: <a href="/explore"...Explore</a>\n      <a href="/ref"
        # With: <a href="/explore"...Explore</a>\n      <a href="/file-monitor"...File Monitor</a>\n      <a href="/ref"

        $pattern = '(<a href="/explore" class="nav-item">Explore</a>)\s+(<a href="/ref")'
        $replacement = '$1`n      <a href="/file-monitor" class="nav-item">File Monitor</a>`n      $2'

        $newContent = $content -replace $pattern, $replacement

        if ($newContent -ne $content) {
            Set-Content -Path $path -Value $newContent -Encoding UTF8
            Write-Host "Updated: $file"
        }
    }
}

Write-Host "Done updating navigation menus"
