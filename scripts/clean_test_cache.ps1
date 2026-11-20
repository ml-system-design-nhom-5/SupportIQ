[CmdletBinding()]
param([switch]$Apply)

$ErrorActionPreference = "Stop"
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..")).TrimEnd('\', '/')
$prefix = $repoRoot + [IO.Path]::DirectorySeparatorChar
$sourceRoots = @('apps', 'services', 'pipeline', 'tests', 'scripts')
$excluded = @('.git', '.venv', 'venv', 'node_modules')

function Test-PlainPath([string]$Path) {
    $current = [IO.Path]::GetFullPath($Path)
    while ($current) {
        if ((Get-Item -LiteralPath $current -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
            return $false
        }
        $current = [IO.Path]::GetDirectoryName($current)
    }
    return $true
}

function Test-Allowlisted([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    if (-not $full.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) { return $false }
    $relative = $full.Substring($prefix.Length).Replace('\', '/')
    return ($relative -match '^\.pytest-[^/]+$' -or $relative -eq '.pytest_cache' -or
        $relative -match '^\.review-system-probe-[^/]+$' -or
        $relative -match '^tmp/pytest/[^/]+$' -or
        ($relative -match '^(apps|services|pipeline|tests|scripts)/(.*/)?__pycache__$' -and
         -not ($relative.Split('/') | Where-Object { $_ -in $excluded })))
}

function Test-SafeTree([string]$Path) {
    if (-not (Test-Allowlisted $Path) -or -not (Test-PlainPath $Path)) { return $false }
    $pending = [Collections.Generic.Stack[string]]::new()
    $pending.Push($Path)
    while ($pending.Count) {
        foreach ($entry in Get-ChildItem -LiteralPath $pending.Pop() -Force) {
            if ($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) { return $false }
            if ($entry.PSIsContainer) { $pending.Push($entry.FullName) }
        }
    }
    $relative = $Path.Substring($prefix.Length).Replace('\', '/')
    $tracked = @(git -C $repoRoot ls-files -- $relative)
    if ($LASTEXITCODE -ne 0) { throw 'Cannot verify tracked files; refusing cleanup.' }
    return $tracked.Count -eq 0
}

if (-not (Test-PlainPath $repoRoot)) { throw 'Repository path contains a link; refusing cleanup.' }
$gitStatus = git -C $repoRoot rev-parse --is-inside-work-tree 2>$null
if ($LASTEXITCODE -ne 0 -or $gitStatus -ne 'true' -or -not (Test-Path -LiteralPath (Join-Path $repoRoot '.git'))) {
    throw 'Cleaner must be inside the repository root; refusing cleanup.'
}
$lockPath = Join-Path $repoRoot '.pytest-cleanup.lock'
if ((Test-Path -LiteralPath $lockPath) -and -not (Test-PlainPath $lockPath)) {
    throw 'Cleanup lock is a link; refusing cleanup.'
}
$lock = $null
try {
    # Pytest sessions hold this file open; exclusive access also prevents a new session during cleanup.
    try {
        $lock = [IO.File]::Open($lockPath, [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    } catch { throw 'An active pytest session or cleaner holds the cleanup lock; refusing cleanup.' }

    Write-Host "Repository root: $repoRoot"
    if ($Apply) { Write-Host 'Mode: APPLY' } else { Write-Host 'Mode: DRY RUN (pass -Apply to remove)' }
    $candidates = [Collections.Generic.List[string]]::new()
    foreach ($entry in Get-ChildItem -LiteralPath $repoRoot -Directory -Force) {
        if (Test-Allowlisted $entry.FullName) { $candidates.Add($entry.FullName) }
    }
    $tmpPytest = Join-Path $repoRoot 'tmp/pytest'
    if ((Test-Path -LiteralPath $tmpPytest -PathType Container) -and (Test-PlainPath $tmpPytest)) {
        foreach ($entry in Get-ChildItem -LiteralPath $tmpPytest -Directory -Force) {
            $candidates.Add($entry.FullName)
        }
    }
    # Walk only source roots, pruning environments and links before descending.
    $pending = [Collections.Generic.Stack[string]]::new()
    foreach ($name in $sourceRoots) {
        $path = Join-Path $repoRoot $name
        if ((Test-Path -LiteralPath $path -PathType Container) -and (Test-PlainPath $path)) { $pending.Push($path) }
    }
    while ($pending.Count) {
        foreach ($entry in Get-ChildItem -LiteralPath $pending.Pop() -Directory -Force) {
            if (($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) -or $entry.Name -in $excluded) { continue }
            if ($entry.Name -eq '__pycache__') { $candidates.Add($entry.FullName) }
            else { $pending.Push($entry.FullName) }
        }
    }
    $removed = 0
    foreach ($path in $candidates) {
        if (-not (Test-SafeTree $path)) {
            Write-Warning "Skipping linked, tracked, or unsafe candidate: $path"
            continue
        }
        Write-Host "Cache candidate: $path"
        if ($Apply) {
            # Revalidate the resolved absolute target immediately before recursive removal.
            if (-not (Test-SafeTree $path)) { throw "Candidate changed during cleanup: $path" }
            Remove-Item -LiteralPath $path -Recurse -Force
            $removed++
        }
    }
    if ($Apply) { Write-Host "Removed $removed cache directories." }
} finally {
    if ($lock) { $lock.Dispose() }
}
