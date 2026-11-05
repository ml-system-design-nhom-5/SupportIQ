<#
.SYNOPSIS
  Run the autoeval workflow (.github/workflows/autoeval.yml) locally on Windows.

.DESCRIPTION
  Mirrors the CI "offline" job: install dependencies, run the evaluator unit tests, then
  `python -m pipeline.evaluation.autoeval run --compare pipeline/configs/autoeval_baseline.json`.
  With -Live it also runs the CI "live" job (calls Gemini; needs GEMINI_API_KEY in .env).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\run_autoeval.ps1
  powershell -ExecutionPolicy Bypass -File scripts\run_autoeval.ps1 -Light        # no torch download; numpy backend
  powershell -ExecutionPolicy Bypass -File scripts\run_autoeval.ps1 -SkipInstall  # reuse installed packages
  powershell -ExecutionPolicy Bypass -File scripts\run_autoeval.ps1 -Live -MaxLlmCalls 30
#>
[CmdletBinding()]
param(
    [switch]$Light,
    [switch]$SkipInstall,
    [switch]$Live,
    [switch]$Judge,
    [int]$MaxLlmCalls = 0,
    [string]$Python = ""
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repoRoot
$env:PYTHONUTF8 = '1'
$logDir = Join-Path $repoRoot 'artifacts/evaluation/autoeval'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir 'local-run.log'
"autoeval local run $(Get-Date -Format o)" | Out-File -FilePath $log -Encoding utf8

function Step([string]$name) {
    Write-Host ""
    Write-Host "=== $name ===" -ForegroundColor Cyan
    "=== $name ===" | Out-File -FilePath $log -Append -Encoding utf8
}
function Run([string]$exe, [string[]]$argv) {
    # Native stderr (pip warnings, progress) must not abort the script under ErrorActionPreference=Stop.
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $exe @argv 2>&1 | ForEach-Object { "$_" } | Tee-Object -FilePath $log -Append | Out-Host
        $code = $LASTEXITCODE
    } finally { $ErrorActionPreference = $previous }
    return $code
}

# ---------------------------------------------------------------- Python environment
Step 'Python environment'
if (-not $Python) {
    $venvPython = Join-Path $repoRoot '.venv/Scripts/python.exe'
    if (-not (Test-Path -LiteralPath $venvPython)) {
        $base = (Get-Command python -ErrorAction SilentlyContinue).Source
        if (-not $base) { $base = (Get-Command py -ErrorAction SilentlyContinue).Source }
        if (-not $base) { throw 'Python not found. Install Python 3.10+ or pass -Python <path to python.exe>.' }
        Write-Host "Creating .venv with $base"
        & $base -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Could not create .venv' }
    }
    $Python = $venvPython
}
$null = Run $Python @('--version')

# ---------------------------------------------------------------- dependencies
if (-not $SkipInstall) {
    Step 'Install dependencies'
    $code = Run $Python @('-m', 'pip', 'install', '--disable-pip-version-check', '--upgrade', 'pip')
    if ($Light) {
        $code = Run $Python @('-m', 'pip', 'install', '--disable-pip-version-check',
            'numpy', 'scipy', 'pydantic', 'httpx', 'python-dotenv', 'pytest', 'pytest-asyncio')
    } else {
        # Same as CI: CPU torch first so pip does not pull a CUDA build, then project requirements.
        $code = Run $Python @('-m', 'pip', 'install', '--disable-pip-version-check', 'torch', '--index-url', 'https://download.pytorch.org/whl/cpu')
        if ($code -ne 0) { throw 'torch installation failed (retry with -Light to use the numpy backend)' }
        $code = Run $Python @('-m', 'pip', 'install', '--disable-pip-version-check',
            '-r', 'apps/demo/requirements.txt', '-r', 'pipeline/requirements.txt', '-r', 'pipeline/requirements-transformers.txt',
            'pytest', 'pytest-asyncio')
    }
    if ($code -ne 0) { throw 'Dependency installation failed (see artifacts/evaluation/autoeval/local-run.log)' }
}

# ---------------------------------------------------------------- unit tests
Step 'Unit tests for the evaluator'
$pytestArgs = @('-m', 'pytest', 'tests/unit/test_autoeval.py', '-q', '-p', 'no:cacheprovider')
if ($Light) { $pytestArgs += '--noconftest' }   # repo conftest patches transformers, absent in -Light
$testCode = Run $Python $pytestArgs
if ($testCode -ne 0) { Write-Host "Evaluator unit tests failed (exit $testCode)" -ForegroundColor Red }

# ---------------------------------------------------------------- offline job
Step 'autoeval: ML + LLM offline'
$backend = if ($Light) { 'numpy' } else { 'auto' }
$evalCode = Run $Python @('-m', 'pipeline.evaluation.autoeval', 'run', '--backend', $backend,
    '--compare', 'pipeline/configs/autoeval_baseline.json', '--tag', 'local')
$latest = (Get-Content -LiteralPath (Join-Path $logDir 'latest.txt') -ErrorAction SilentlyContinue | Select-Object -First 1)

# ---------------------------------------------------------------- live job (optional)
$liveCode = $null
if ($Live) {
    Step 'autoeval: LLM live (Gemini, costs API calls)'
    $liveArgs = @('-m', 'pipeline.evaluation.autoeval', 'run', '--suite', 'llm', '--llm-mode', 'live', '--tag', 'local-live')
    if ($Judge) { $liveArgs += '--judge' }
    if ($MaxLlmCalls -gt 0) { $liveArgs += @('--max-llm-calls', "$MaxLlmCalls") }
    $liveCode = Run $Python $liveArgs
}

# ---------------------------------------------------------------- summary
Step 'Summary'
$meaning = @{ 0 = 'all blocking gates passed'; 1 = 'blocking gate(s) failed'; 2 = 'evaluation could not run' }
Write-Host ("unit tests : exit {0}" -f $testCode)
Write-Host ("offline    : exit {0} ({1}) -> {2}/report.md" -f $evalCode, $meaning[[int]$evalCode], $latest)
if ($Live) {
    $liveLatest = (Get-Content -LiteralPath (Join-Path $logDir 'latest.txt') | Select-Object -First 1)
    Write-Host ("live       : exit {0} ({1}) -> {2}/report.md" -f $liveCode, $meaning[[int]$liveCode], $liveLatest)
}
Write-Host "log        : artifacts/evaluation/autoeval/local-run.log"
if ($testCode -ne 0 -or $evalCode -eq 2) { exit 2 }
exit $evalCode
