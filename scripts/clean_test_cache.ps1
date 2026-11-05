[CmdletBinding()]
param(
    [switch]$Apply
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

# Protected folders that must NEVER be touched
$protectedNames = @(
    ".git",
    ".venv",
    "venv",
    "data",
    "artifacts",
    "apps",
    "services",
    "pipeline",
    "tests",
    "docs",
    "scripts"
)

Write-Host "=== SupportIQ Test Cache Cleaner ===" -ForegroundColor Cyan
Write-Host "Repository root: $repoRoot"
if ($Apply) {
    Write-Host "Mode: APPLY (destructive removal of cache items)" -ForegroundColor Yellow
} else {
    Write-Host "Mode: DRY RUN (no files will be deleted; pass -Apply to execute)" -ForegroundColor Green
}
Write-Host ""

$candidates = [System.Collections.Generic.List[PSCustomObject]]::new()

# 1. Root level .pytest-* and .review-system-probe-* directories
$rootPatterns = @(".pytest-*", ".pytest_cache", ".review-system-probe-*")
foreach ($pattern in $rootPatterns) {
    Get-ChildItem -Path $repoRoot -Filter $pattern -Directory -ErrorAction SilentlyContinue | ForEach-Object {
        $candidates.Add([PSCustomObject]@{
            Path = $_.FullName
            Type = "Directory"
            Reason = "Test temporary/cache directory ($pattern)"
        })
    }
}

# 2. tmp/pytest directory contents
$tmpPytest = Join-Path $repoRoot "tmp\pytest"
if (Test-Path $tmpPytest) {
    Get-ChildItem -Path $tmpPytest -Directory -ErrorAction SilentlyContinue | ForEach-Object {
        $candidates.Add([PSCustomObject]@{
            Path = $_.FullName
            Type = "Directory"
            Reason = "Temporary pytest basetemp folder"
        })
    }
}

# 3. __pycache__ directories outside protected roots (excluding .venv)
Get-ChildItem -Path $repoRoot -Filter "__pycache__" -Directory -Recurse -ErrorAction SilentlyContinue | ForEach-Object {
    $fullPath = $_.FullName
    if ($fullPath -notlike "*\.venv\*" -and $fullPath -notlike "*\venv\*") {
        $candidates.Add([PSCustomObject]@{
            Path = $fullPath
            Type = "Directory"
            Reason = "Python bytecode cache (__pycache__)"
        })
    }
}

if ($candidates.Count -eq 0) {
    Write-Host "No cache or temporary test directories found. Clean!" -ForegroundColor Green
    exit 0
}

Write-Host ("Found {0} cache candidate item(s):" -f $candidates.Count) -ForegroundColor Cyan
Write-Host ""

$totalBytes = 0

foreach ($item in $candidates) {
    $itemPath = $item.Path
    # Safety verification: ensure inside $repoRoot
    if (-not $itemPath.StartsWith($repoRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        Write-Warning "Skipping unsafe candidate outside repo root: $itemPath"
        continue
    }

    # Safety check: ensure not a protected top-level folder itself
    $rel = $itemPath.Substring($repoRoot.Length).TrimStart('\', '/')
    $firstSegment = ($rel -split '[\\/]', 2)[0]
    if ($protectedNames -contains $rel) {
        Write-Warning "Skipping protected root folder: $itemPath"
        continue
    }

    # Measure size
    $size = 0
    try {
        $measure = Get-ChildItem -LiteralPath $itemPath -Recurse -File -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum
        if ($measure -and $measure.Sum) {
            $size = $measure.Sum
        }
    } catch {}
    $totalBytes += $size

    $sizeMb = [Math]::Round($size / 1MB, 2)
    Write-Host ("[{0}] {1} ({2} MB) - {3}" -f $item.Type, $rel, $sizeMb, $item.Reason)

    if ($Apply) {
        try {
            Remove-Item -LiteralPath $itemPath -Recurse -Force -ErrorAction Stop
            Write-Host "  -> REMOVED" -ForegroundColor Green
        } catch {
            Write-Warning "  -> FAILED to remove: $($_.Exception.Message)"
        }
    }
}

Write-Host ""
$totalMb = [Math]::Round($totalBytes / 1MB, 2)
if ($Apply) {
    Write-Host ("Cleaned {0} items (~{1} MB reclaimed)." -f $candidates.Count, $totalMb) -ForegroundColor Green
} else {
    Write-Host ("Total candidate size: ~{0} MB in {1} items." -f $totalMb, $candidates.Count) -ForegroundColor Yellow
    Write-Host "Run with -Apply to permanently delete these cache directories." -ForegroundColor Yellow
}
