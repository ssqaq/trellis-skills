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

$minimalWorkflow = @'
# Local workflow
[workflow-state:in_progress]
Implement the active task.
[/workflow-state:in_progress]
#### 3.5 Wrap-up reminder
After the above, remind the user they can run `/finish-work` to wrap up (archive the task, record the session).
Keep this custom rule.
'@
$nestedProject = Join-Path $temporaryProject 'nested'
$globalOnlyProject = Join-Path $temporaryProject 'global-only'
$ignoredProject = Join-Path $temporaryProject 'node_modules\ignored-project'
foreach ($project in @($temporaryProject, $nestedProject, $globalOnlyProject, $ignoredProject)) {
    New-Item -ItemType Directory -Force -Path (Join-Path $project '.trellis') | Out-Null
    Set-Content -LiteralPath (Join-Path $project '.trellis\workflow.md') -Value $minimalWorkflow -Encoding UTF8
    Set-Content -LiteralPath (Join-Path $project 'AGENTS.md') -Value 'Keep user rules.' -Encoding UTF8
}
New-Item -ItemType Directory -Force -Path (Join-Path $nestedProject '.codex\skills\trellis-start') | Out-Null
Set-Content -LiteralPath (Join-Path $nestedProject '.codex\skills\trellis-start\SKILL.md') -Value 'old skill'

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

    foreach ($project in @($temporaryProject, $nestedProject, $globalOnlyProject)) {
        $workflow = Get-Content -LiteralPath (Join-Path $project '.trellis\workflow.md') -Raw
        $agents = Get-Content -LiteralPath (Join-Path $project 'AGENTS.md') -Raw
        if ($workflow -notmatch 'Automatic wrap-up' -or $workflow -notmatch 'Keep this custom rule' -or
            $agents -notmatch 'TRELLIS-SKILLS:AUTOFINISH:START' -or $agents -notmatch 'Keep user rules') {
            throw "Workflow or user-rule preservation failed: $project"
        }
    }
    if ((Get-Content -LiteralPath (Join-Path $ignoredProject 'AGENTS.md') -Raw) -match 'AUTOFINISH') {
        throw 'Dependency directories must not be migrated.'
    }
    $initialBackupCount = @(Get-ChildItem -LiteralPath (Join-Path $temporaryRoot 'backups') -Recurse -Filter '*.bak').Count
    if ($initialBackupCount -lt 7) { throw "Original instructions and replaced skill were not all backed up: $initialBackupCount" }

    Add-Content -LiteralPath $targetFile -Value "`nLOCAL TEST EDIT"
    $output = & pwsh -NoProfile -ExecutionPolicy Bypass -File $syncScript -FromRegistry -RegistryPath $temporaryRegistry
    if ($LASTEXITCODE -ne 0) {
        throw "Registry-only update failed: $($output -join ' ')"
    }
    $targetHash = (Get-FileHash -Algorithm SHA256 $targetFile).Hash
    if ($sourceHash -ne $targetHash) {
        throw 'Registry-only update did not restore the newest skill.'
    }
    $backupCount = @(Get-ChildItem -LiteralPath (Join-Path $temporaryRoot 'backups') -Recurse -Filter '*.bak').Count
    if ($backupCount -ne ($initialBackupCount + 1)) { throw 'The replaced local skill edit needs its own backup; unchanged rules must not be backed up again.' }
    $output = & pwsh -NoProfile -ExecutionPolicy Bypass -File $syncScript -FromRegistry -RegistryPath $temporaryRegistry
    if ($LASTEXITCODE -ne 0) { throw 'Unchanged repeat synchronization failed.' }
    $repeatBackupCount = @(Get-ChildItem -LiteralPath (Join-Path $temporaryRoot 'backups') -Recurse -Filter '*.bak').Count
    if ($repeatBackupCount -ne $backupCount) { throw 'An unchanged repeat installation must not add backups.' }

    Write-Output 'PASS: registration, stale-skill repair with recovery backup, nested/legacy/global-only projects, workflow preservation, dependency exclusion and idempotency'
}
finally {
    if (Test-Path -LiteralPath $temporaryRoot) {
        $resolvedTemporary = (Resolve-Path -LiteralPath $temporaryRoot).Path
        $allowedParent = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\') + '\'
        if (-not $resolvedTemporary.StartsWith($allowedParent, [StringComparison]::OrdinalIgnoreCase) -or
            (Split-Path -Leaf $resolvedTemporary) -notlike 'trellis-local-sync-*') { throw 'Unexpected cleanup path' }
        Remove-Item -LiteralPath $resolvedTemporary -Recurse -Force
    }
}
