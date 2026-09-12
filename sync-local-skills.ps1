[CmdletBinding()]
param(
    [string[]]$ProjectRoot = @(),
    [switch]$FromRegistry,
    [string]$RegistryPath = '',
    [string]$BackupRoot = '',
    [switch]$IncludeActiveProjects
)
$ErrorActionPreference = 'Stop'
$helper = Join-Path $PSScriptRoot 'skills\trellis-setup\scripts\auto_update.py'
$arguments = @('-B', $helper, 'sync', '--source', $PSScriptRoot)
foreach ($project in $ProjectRoot) {
    $arguments += @('--project-root', $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($project))
}
if ($RegistryPath) { $arguments += @('--registry-path', $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($RegistryPath)) }
if ($BackupRoot) { $arguments += @('--backup-root', $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($BackupRoot)) }
if ($IncludeActiveProjects) { $arguments += '--include-active' }
if (-not $ProjectRoot.Count -and -not $FromRegistry) { throw 'Use -ProjectRoot <path> or -FromRegistry.' }
$output = & python @arguments
if ($LASTEXITCODE -ne 0) { throw "Trellis project synchronization failed: $($output -join ' ')" }
Write-Output $output
