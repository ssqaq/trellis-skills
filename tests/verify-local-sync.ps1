$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$syncScript = Join-Path $repoRoot 'sync-local-skills.ps1'
$installScript = Join-Path $repoRoot 'install.ps1'
$sourceSkill = Join-Path $repoRoot 'skills\trellis-finish-work\SKILL.md'
$temporaryRoot = Join-Path ([System.IO.Path]::GetTempPath()) ('trellis-local-sync-' + [guid]::NewGuid().ToString('N'))
$temporaryProject = Join-Path $temporaryRoot 'project'
$temporarySkills = Join-Path $temporaryProject '.agents\skills\trellis-finish-work'
$temporaryRegistry = Join-Path $temporaryRoot 'projects.json'

New-Item -ItemType Directory -Force -Path $temporarySkills | Out-Null

try {
    Copy-Item -LiteralPath $sourceSkill -Destination $temporarySkills -Force

    $output = & pwsh -NoProfile -ExecutionPolicy Bypass -File $syncScript -ProjectRoot $temporaryProject -RegistryPath $temporaryRegistry
    if ($LASTEXITCODE -ne 0) {
        throw "Initial project registration failed: $($output -join ' ')"
    }
    $sourceHash = (Get-FileHash -Algorithm SHA256 $sourceSkill).Hash
    $targetFile = Join-Path $temporarySkills 'SKILL.md'
    $targetHash = (Get-FileHash -Algorithm SHA256 $targetFile).Hash
    if ($sourceHash -ne $targetHash) {
        throw 'Initial registration did not copy the current skill.'
    }

    Add-Content -LiteralPath $targetFile -Value "`nLOCAL TEST EDIT"
    $output = & pwsh -NoProfile -ExecutionPolicy Bypass -File $syncScript -FromRegistry -RegistryPath $temporaryRegistry
    if ($LASTEXITCODE -ne 0) {
        throw "Registry-only update failed: $($output -join ' ')"
    }
    $targetHash = (Get-FileHash -Algorithm SHA256 $targetFile).Hash
    if ($sourceHash -ne $targetHash) {
        throw 'Registry-only update did not restore the newest skill.'
    }

    $installText = Get-Content -LiteralPath $installScript -Raw
    if ($installText.IndexOf('sync-local-skills.ps1', [System.StringComparison]::Ordinal) -lt 0 -or
        $installText.IndexOf('-FromRegistry', [System.StringComparison]::Ordinal) -lt 0) {
        throw 'install.ps1 is not wired to update registered project-local skills.'
    }

    Write-Output 'PASS: project registration, registry-only update, and installer wiring'
}
finally {
    if (Test-Path -LiteralPath $temporaryRoot) {
        Remove-Item -LiteralPath $temporaryRoot -Recurse -Force
    }
}
