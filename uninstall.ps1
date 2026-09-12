# Remove this package's global Trellis skills and its own global instruction block.
$ErrorActionPreference = 'Stop'
$profileRoot = [IO.Path]::GetFullPath($env:USERPROFILE).TrimEnd('\')
$roots = @((Join-Path $profileRoot '.agents\skills'), (Join-Path $profileRoot '.codex\skills'))
$sourceRoot = Join-Path $PSScriptRoot 'skills'
$names = @(Get-ChildItem -LiteralPath $sourceRoot -Directory | Where-Object { $_.Name -like 'trellis-*' } | ForEach-Object { $_.Name })
$targets = New-Object System.Collections.Generic.List[string]

Write-Host '=== Trellis Skills Uninstaller ===' -ForegroundColor Cyan

# Validate all roots, ancestors, and descendants before deleting anything.
foreach ($root in $roots) {
    $ancestor = $root
    while ($ancestor) {
        if ((Test-Path -LiteralPath $ancestor) -and ((Get-Item -LiteralPath $ancestor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw "Refusing to uninstall through a linked parent: $ancestor"
        }
        if ($ancestor -eq $profileRoot) { break }
        $ancestor = Split-Path -Parent $ancestor
    }
    if (-not (Test-Path -LiteralPath $root)) { continue }
    foreach ($name in $names) {
        $target = Join-Path $root $name
        if (-not (Test-Path -LiteralPath $target)) { continue }
        $resolvedTarget = [IO.Path]::GetFullPath($target)
        $allowedRoot = [IO.Path]::GetFullPath($root).TrimEnd('\') + '\'
        if (-not $resolvedTarget.StartsWith($allowedRoot, [StringComparison]::OrdinalIgnoreCase)) { throw "Unexpected uninstall target: $target" }
        $linked = @(Get-Item -LiteralPath $target -Force; Get-ChildItem -LiteralPath $target -Recurse -Force) |
            Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }
        if ($linked) { throw "Refusing to uninstall a linked skill path: $target" }
        $targets.Add($resolvedTarget)
    }
}

$upgradeScript = Join-Path $sourceRoot 'trellis-setup\scripts\upgrade_project.py'
& python $upgradeScript --remove-global-rules
if ($LASTEXITCODE -ne 0) { throw 'Failed to remove the Trellis global entry rule; skill files were kept.' }
foreach ($target in $targets) {
    Remove-Item -LiteralPath $target -Recurse -Force
    Write-Host "  removed: $target"
}
Write-Host "Done. Removed $($targets.Count) packaged Trellis skill directories from both global locations." -ForegroundColor Green
Write-Host 'Project skills, task cabinets and unrelated user skills were kept.' -ForegroundColor Cyan
