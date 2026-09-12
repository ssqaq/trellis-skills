[CmdletBinding()]
param(
    [string[]]$ProjectRoot = @(),
    [switch]$FromRegistry,
    [string]$RegistryPath = ''
)

$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$skillsSrc = Join-Path $scriptDir 'skills'
if ([string]::IsNullOrWhiteSpace($RegistryPath)) {
    $RegistryPath = Join-Path $env:USERPROFILE '.trellis-skills\projects.json'
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

function Get-ExistingSkillRoots {
    param([string[]]$Roots)

    $found = New-Object System.Collections.Generic.List[string]
    foreach ($root in ($Roots | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })) {
        $resolvedRoot = Resolve-FullPath $root
        if ($null -eq $resolvedRoot) {
            Write-Warning "Project root not found, skipped: $root"
            continue
        }

        $candidates = New-Object System.Collections.Generic.List[string]
        foreach ($kind in @('.agents', '.codex')) {
            $direct = Join-Path $resolvedRoot "$kind\skills"
            if (Test-Path -LiteralPath $direct) {
                $candidates.Add((Get-Item -LiteralPath $direct).FullName)
            }
        }

        $nestedMetaDirs = Get-ChildItem -LiteralPath $resolvedRoot -Directory -Recurse -Force -ErrorAction SilentlyContinue |
            Where-Object {
                $_.Name -in @('.agents', '.codex') -and
                $_.FullName -notmatch '\\node_modules\\' -and
                $_.FullName -notmatch '\\.git(\\|$)'
            }
        foreach ($metaDir in $nestedMetaDirs) {
            $nestedSkills = Join-Path $metaDir.FullName 'skills'
            if (Test-Path -LiteralPath $nestedSkills) {
                $candidates.Add((Get-Item -LiteralPath $nestedSkills).FullName)
            }
        }

        foreach ($candidate in ($candidates | Sort-Object -Unique)) {
            $hasTrellis = @(Get-ChildItem -LiteralPath $candidate -Directory -ErrorAction SilentlyContinue |
                Where-Object { $_.Name -like 'trellis-*' }).Count -gt 0
            if ($hasTrellis -and ($found -notcontains $candidate)) {
                $found.Add($candidate)
            }
        }
    }
    return @($found)
}

$registered = @(Read-RegisteredRoots)
$allRoots = @($registered + $ProjectRoot) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | ForEach-Object {
    Resolve-FullPath $_
} | Where-Object { $null -ne $_ } | Sort-Object -Unique

if ($ProjectRoot.Count -gt 0) {
    $registryDir = Split-Path -Parent $RegistryPath
    New-Item -ItemType Directory -Force -Path $registryDir | Out-Null
    $registryData = @{ version = 1; projects = @($allRoots) }
    $registryData | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath $RegistryPath -Encoding UTF8
}

if ($allRoots.Count -eq 0) {
    if ($FromRegistry) {
        Write-Output "No registered project roots found. Register one with -ProjectRoot <path>."
        exit 0
    }
    throw 'No project root supplied. Use -ProjectRoot <path> to register and sync a project.'
}

$targets = @(Get-ExistingSkillRoots $allRoots)
foreach ($target in $targets) {
    foreach ($skill in $trellisSkills) {
        Copy-Item -LiteralPath $skill.FullName -Destination $target -Recurse -Force
    }
    Write-Output "Updated $($trellisSkills.Count) Trellis skills: $target"
}

if ($targets.Count -eq 0) {
    Write-Output 'No existing Trellis skill installation was found under the registered project roots.'
}
else {
    Write-Output "Updated $($targets.Count) existing Trellis skill installation(s)."
}
