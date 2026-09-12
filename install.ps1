# One-time installation also enables task-triggered automatic release updates.
[CmdletBinding()]
param([switch]$IncludeActiveProjects)
$ErrorActionPreference = 'Stop'
$helper = Join-Path $PSScriptRoot 'skills\trellis-setup\scripts\auto_update.py'
$arguments = @('-B', $helper, 'install', '--source', $PSScriptRoot)
if ($IncludeActiveProjects) { $arguments += '--include-active' }
$output = & python @arguments
if ($LASTEXITCODE -ne 0) { throw "Trellis installation failed: $($output -join ' ')" }
$result = $output | ConvertFrom-Json
Write-Output "Installed version: $($result.version)"
Write-Output "Updated global skills and $($result.projects_updated.Count) project(s)."
foreach ($pending in $result.pending_projects) {
    Write-Output "Pending project ($($pending.reason)): $($pending.project)"
}
Write-Output 'Automatic updates: check at task start/resume; install after closeout.'
Write-Output 'Busy projects keep their current rules until their own closeout.'
Write-Output 'Register another project with: pwsh -File sync-local-skills.ps1 -ProjectRoot <path>'
if (-not (Get-Command trellis -ErrorAction SilentlyContinue)) {
    Write-Output 'Trellis CLI is not installed. Install it with: npm install -g @mindfoldhq/trellis'
}
Write-Output 'Done. Open a new Codex task to load the updated entry rules.'
