# One-click uninstaller for Trellis Skills (Windows)
# Usage:  pwsh -File uninstall.ps1

$ErrorActionPreference = 'Stop'

$skillsDst = Join-Path $env:USERPROFILE '.agents\skills'

Write-Host '=== Trellis Skills Uninstaller ===' -ForegroundColor Cyan

if (-not (Test-Path $skillsDst)) {
    Write-Host "Nothing to uninstall: $skillsDst does not exist." -ForegroundColor Yellow
    exit 0
}

$trellisSkills = Get-ChildItem -LiteralPath $skillsDst -Directory -ErrorAction SilentlyContinue | Where-Object { $_.Name -like 'trellis-*' }

if ($trellisSkills.Count -eq 0) {
    Write-Host 'Nothing to uninstall: no trellis-* skill folders found.' -ForegroundColor Yellow
    exit 0
}

$removed = 0
foreach ($skill in $trellisSkills) {
    Remove-Item -LiteralPath $skill.FullName -Recurse -Force
    $removed++
    Write-Host "  removed: $($skill.Name)"
}

Write-Host ""
Write-Host "Done. $removed skills removed from: $skillsDst" -ForegroundColor Green
Write-Host 'Note: project-level .trellis cabinets were NOT touched.' -ForegroundColor Cyan
Write-Host '      If you also want to remove a project cabinet, delete that project'"'"'s .trellis folder manually.'
