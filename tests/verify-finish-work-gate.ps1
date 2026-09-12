$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$finishSkill = Get-Content (Join-Path $repoRoot 'skills\trellis-finish-work\SKILL.md') -Raw

function Assert-Contains {
    param(
        [string]$Text,
        [string]$Needle,
        [string]$Message
    )

    if ($Text.IndexOf($Needle, [System.StringComparison]::Ordinal) -lt 0) {
        throw $Message
    }
}

Assert-Contains $finishSkill '## Mandatory first step: run the full quality check' 'finish-work is missing its mandatory quality gate.'
Assert-Contains $finishSkill 'dispatch or invoke `trellis-check` and wait for its complete result' 'finish-work does not require waiting for trellis-check.'
Assert-Contains $finishSkill 'Do not archive the task, record a completed session, publish, push, or claim success' 'finish-work does not block completion on a failed check.'
Assert-Contains $finishSkill 'Only after the check passes may you continue' 'finish-work does not place archive after the quality gate.'

$temporaryProject = Join-Path ([System.IO.Path]::GetTempPath()) ('trellis-finish-gate-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temporaryProject | Out-Null

try {
    function Invoke-SimulatedFinish {
        param(
            [string]$ProjectPath,
            [bool]$CheckPasses
        )

        $events = New-Object System.Collections.Generic.List[string]
        $events.Add('finish-work started')
        $events.Add('trellis-check started')

        if (-not $CheckPasses) {
            $events.Add('trellis-check failed')
            return $events
        }

        $events.Add('trellis-check passed')
        New-Item -ItemType File -Path (Join-Path $ProjectPath 'task-archived.marker') | Out-Null
        $events.Add('task archived')
        New-Item -ItemType File -Path (Join-Path $ProjectPath 'session-recorded.marker') | Out-Null
        $events.Add('session recorded')
        return $events
    }

    $passingProject = Join-Path $temporaryProject 'passing'
    New-Item -ItemType Directory -Path $passingProject | Out-Null
    $passingEvents = Invoke-SimulatedFinish -ProjectPath $passingProject -CheckPasses $true
    $expectedPassing = @('finish-work started', 'trellis-check started', 'trellis-check passed', 'task archived', 'session recorded')
    if (($passingEvents -join '|') -ne ($expectedPassing -join '|')) {
        throw 'A passing check did not archive and record in the required order.'
    }

    $failingProject = Join-Path $temporaryProject 'failing'
    New-Item -ItemType Directory -Path $failingProject | Out-Null
    $failingEvents = Invoke-SimulatedFinish -ProjectPath $failingProject -CheckPasses $false
    if (($failingEvents -join '|') -ne 'finish-work started|trellis-check started|trellis-check failed') {
        throw 'A failed check incorrectly continued into archive or journal steps.'
    }
    if (Test-Path (Join-Path $failingProject 'task-archived.marker')) {
        throw 'A failed check created an archive marker.'
    }
    if (Test-Path (Join-Path $failingProject 'session-recorded.marker')) {
        throw 'A failed check created a session marker.'
    }

    Write-Output 'PASS: finish-work quality gate contract and pass/fail simulations'
}
finally {
    if (Test-Path $temporaryProject) {
        Remove-Item -LiteralPath $temporaryProject -Recurse -Force
    }
}
