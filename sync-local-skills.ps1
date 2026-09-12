[CmdletBinding()]
param(
    [string[]]$ProjectRoot = @(),
    [switch]$FromRegistry,
    [string]$RegistryPath = '',
    [string]$BackupRoot = ''
)

$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$skillsSrc = Join-Path $scriptDir 'skills'
if ([string]::IsNullOrWhiteSpace($RegistryPath)) {
    $RegistryPath = Join-Path $env:USERPROFILE '.trellis-skills\projects.json'
}
$RegistryPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($RegistryPath)
if (-not [string]::IsNullOrWhiteSpace($BackupRoot)) {
    $BackupRoot = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($BackupRoot)
}

if (-not (Test-Path -LiteralPath $skillsSrc)) {
    throw "skills folder not found: $skillsSrc"
}

$trellisSkills = @(Get-ChildItem -LiteralPath $skillsSrc -Directory | Where-Object { $_.Name -like 'trellis-*' })
if ($trellisSkills.Count -eq 0) {
    throw "No trellis-* skill folders found in: $skillsSrc"
}

function Resolve-FullPath {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        return $null
    }
    return (Get-Item -LiteralPath $Path).FullName.TrimEnd('\')
}

function Read-RegisteredRoots {
    if (-not (Test-Path -LiteralPath $RegistryPath)) {
        return @()
    }

    $raw = Get-Content -LiteralPath $RegistryPath -Raw
    if ([string]::IsNullOrWhiteSpace($raw)) {
        return @()
    }

    $data = $raw | ConvertFrom-Json
    if ($null -ne $data.projects) {
        return @($data.projects)
    }
    return @($data)
}

function Get-ProjectInstallations {
    param([string[]]$Roots)

    $helper = Join-Path $skillsSrc 'trellis-setup\scripts\upgrade_project.py'
    Write-Output "Scanning registered projects for Trellis installations..." | Out-Host
    $json = & python $helper --discover-projects @Roots
    if ($LASTEXITCODE -ne 0) { throw 'Unable to scan all registered projects.' }
    $result = $json | ConvertFrom-Json
    foreach ($missing in $result.Missing) { Write-Warning "Project root not found, skipped: $missing" }
    Write-Output "Scanned $($result.Directories) directories; found $($result.Projects.Count) initialized projects." | Out-Host
    return $result
}

$registered = @(Read-RegisteredRoots)
$allRoots = @(@($registered + $ProjectRoot) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | ForEach-Object {
    $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($_)
} | Sort-Object -Unique)

if ($ProjectRoot.Count -gt 0) {
    $registryDir = Split-Path -Parent $RegistryPath
    New-Item -ItemType Directory -Force -Path $registryDir | Out-Null
    $registryData = @{ version = 1; projects = @($allRoots) }
    $registryData | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath $RegistryPath -Encoding UTF8
}

if ($allRoots.Count -eq 0) {
    if ($FromRegistry) {
        Write-Output "No registered project roots found. Register one with -ProjectRoot <path>."
        return
    }
    throw 'No project root supplied. Use -ProjectRoot <path> to register and sync a project.'
}

$installations = Get-ProjectInstallations $allRoots
$targets = @($installations.Skills)
foreach ($target in $targets) {
    foreach ($skill in $trellisSkills) {
        $destination = Join-Path $target $skill.Name
        if (Test-Path -LiteralPath $destination) {
            $linked = @(Get-Item -LiteralPath $destination -Force; Get-ChildItem -LiteralPath $destination -Recurse -Force) |
                Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }
            if ($linked) { throw "Refusing to overwrite a linked skill path: $destination" }
        }
        Copy-Item -LiteralPath $skill.FullName -Destination $target -Recurse -Force -Exclude '__pycache__', '*.pyc'
    }
    Write-Output "Updated $($trellisSkills.Count) Trellis skills: $target"
}

if ($targets.Count -eq 0) {
    Write-Output 'No existing Trellis skill installation was found under the registered project roots.'
}
else {
    Write-Output "Updated $($targets.Count) existing Trellis skill installation(s)."
}

# Initialized projects may use global skills without any project skill directory.
$upgradeScript = Join-Path $skillsSrc 'trellis-setup\scripts\upgrade_project.py'
if ([string]::IsNullOrWhiteSpace($BackupRoot)) {
    $BackupRoot = Join-Path (Split-Path -Parent $RegistryPath) 'backups'
}
foreach ($project in $installations.Projects) {
    $result = & python $upgradeScript --project-root $project --backup-root $BackupRoot
    if ($LASTEXITCODE -ne 0) { throw "Workflow upgrade failed for $project`: $($result -join ' ')" }
    Write-Output $result
}
Write-Output "Checked automatic closeout for $($installations.Projects.Count) initialized project(s)."
