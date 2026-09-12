# One-click installer for Trellis Skills (Windows)
# Usage:  pwsh -File install.ps1    (or right-click > Run with PowerShell)

$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$skillsSrc = Join-Path $scriptDir 'skills'
$skillsDst = Join-Path $env:USERPROFILE '.agents\skills'
$versionPath = Join-Path $scriptDir 'VERSION'
$installedVersion = if (Test-Path -LiteralPath $versionPath) { (Get-Content -LiteralPath $versionPath -Raw).Trim() } else { 'unknown' }

Write-Host '=== Trellis Skills Installer ===' -ForegroundColor Cyan

# 1. Check source skills exist
if (-not (Test-Path $skillsSrc)) {
    Write-Host "ERROR: skills folder not found next to install.ps1: $skillsSrc" -ForegroundColor Red
    exit 1
}

$trellisSkills = Get-ChildItem -LiteralPath $skillsSrc -Directory | Where-Object { $_.Name -like 'trellis-*' }
if ($trellisSkills.Count -eq 0) {
    Write-Host 'ERROR: no trellis-* skill folders found in the skills folder.' -ForegroundColor Red
    exit 1
}

# 2. Copy to global skills directory
New-Item -ItemType Directory -Force -Path $skillsDst | Out-Null

$copied = 0
foreach ($skill in $trellisSkills) {
    Copy-Item -LiteralPath $skill.FullName -Destination $skillsDst -Recurse -Force
    $copied++
    Write-Host "  installed: $($skill.Name)"
}

Write-Host ""
Write-Host "Done. $copied skills installed to: $skillsDst" -ForegroundColor Green
Write-Host "Installed version: $installedVersion (see VERSION file for details)" -ForegroundColor Cyan

# 3. Update registered project-local Trellis skill copies
$syncScript = Join-Path $scriptDir 'sync-local-skills.ps1'
if (Test-Path -LiteralPath $syncScript) {
    & $syncScript -FromRegistry
}

# 4. Check Trellis CLI
$trellisCmd = Get-Command trellis -ErrorAction SilentlyContinue
if ($trellisCmd) {
    Write-Host 'Trellis CLI: installed.' -ForegroundColor Green
} else {
    Write-Host 'Trellis CLI: NOT installed.' -ForegroundColor Yellow
    Write-Host 'Install it with:  npm install -g @mindfoldhq/trellis' -ForegroundColor Yellow
}

# 5. Next-step reminder
Write-Host 'Register a project-local skill copy once (optional):' -ForegroundColor Cyan
Write-Host '  pwsh -File sync-local-skills.ps1 -ProjectRoot D:\your-project-folder'
Write-Host 'After registration, future runs of this installer update that project automatically.' -ForegroundColor Cyan
Write-Host ""
Write-Host 'Next step (once per project):' -ForegroundColor Cyan
Write-Host '  cd your-project-folder'
Write-Host '  trellis init'
Write-Host ""
Write-Host 'After that, just talk to Codex normally - the skills trigger automatically.'
