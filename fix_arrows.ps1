$file = "C:\Ashok\Invest\Projects\trading-dashboard\web\explore.html"
$content = Get-Content $file -Raw -Encoding UTF8

# Fix corrupted arrow characters
$content = $content -replace '[â†]+\s*Prev', '← Prev'
$content = $content -replace 'Next\s*[â†]+', 'Next →'

# Also fix the pagination buttons at the bottom
$content = $content -replace '[â†]+\s*Previous', '← Previous'

# Write back as UTF8
$content | Set-Content $file -Encoding UTF8

Write-Host "[OK] Fixed arrow characters in explore.html"
