param(
    [switch]$SetupOnly,
    [switch]$WithoutAI,
    [switch]$EnableLLM,
    [switch]$DisableLLM,
    [switch]$SkipInstall,
    [switch]$SkipBuild
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repoRoot
$env:PYTHONUTF8 = '1'

# Locate Python environment (prefer local .venv, then SUPPORTIQ_PYTHON, then root repo venv in worktree)
$pythonPath = Join-Path $repoRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    if ($env:SUPPORTIQ_PYTHON -and (Test-Path -LiteralPath $env:SUPPORTIQ_PYTHON)) {
        $pythonPath = $env:SUPPORTIQ_PYTHON
    } else {
        $commonGitDir = & git rev-parse --git-common-dir 2>$null
        if ($commonGitDir) {
            $rootRepoCandidate = Join-Path (Split-Path $commonGitDir -Parent) '.venv/Scripts/python.exe'
            if (Test-Path -LiteralPath $rootRepoCandidate) {
                $pythonPath = $rootRepoCandidate
            }
        }
    }
}
if (-not (Test-Path -LiteralPath $pythonPath)) {
    $installedPython = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (-not $installedPython) { $installedPython = 'C:/Users/PC/AppData/Local/Programs/Python/Python314/python.exe' }
    & $installedPython -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python environment.' }
    $pythonPath = Join-Path $repoRoot '.venv/Scripts/python.exe'
}

if (-not $SkipInstall) {
    & $pythonPath -X utf8 -m pip install --disable-pip-version-check -r apps/backend/requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Backend dependency installation failed.' }
}

# Run runtime preflight and export discovery/driver variables
if (-not $env:PSYCOPG_IMPL) {
    $env:PSYCOPG_IMPL = 'python'
}
& $pythonPath -X utf8 scripts/native_runtime.py preflight
if ($LASTEXITCODE -ne 0) { throw 'Runtime preflight verification failed.' }

$discoveredPgBin = & $pythonPath -X utf8 -c "from scripts.native_runtime import discover_pg_bin; print(discover_pg_bin())"
if ($discoveredPgBin -and (Test-Path -LiteralPath $discoveredPgBin)) {
    $env:PATH = "$discoveredPgBin;$env:PATH"
}

& $pythonPath -X utf8 scripts/native_runtime.py prepare
if ($LASTEXITCODE -ne 0) { throw 'Native PostgreSQL setup failed.' }
& $pythonPath -X utf8 -m apps.backend.manage initialize
if ($LASTEXITCODE -ne 0) { throw 'Database initialization failed.' }
if ($SetupOnly) { return }

Push-Location -LiteralPath (Join-Path $repoRoot 'apps/frontend')
try {
    if (-not $SkipInstall) {
        & pnpm.cmd install --frozen-lockfile
        if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
    }
    if (-not $SkipBuild) {
        & pnpm.cmd build
        if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
    }
} finally { Pop-Location }

$processFile = Join-Path $repoRoot '.local/processes.json'
if (Test-Path -LiteralPath $processFile) {
    $recorded = Get-Content -LiteralPath $processFile -Raw | ConvertFrom-Json
    foreach ($record in $recorded) {
        $running = Get-Process -Id $record.Id -ErrorAction SilentlyContinue
        if ($running -and $running.StartTime.ToUniversalTime().Ticks -eq ([datetime]$record.StartedAt).ToUniversalTime().Ticks) {
            throw 'The application is already running. Use scripts/stop-app.ps1 before starting it again.'
        }
    }
}
function Test-ApplicationPort([int]$Port) {
    $probe = [System.Net.Sockets.TcpClient]::new()
    try { $probe.Connect('127.0.0.1', $Port); return $true } catch { return $false } finally { $probe.Dispose() }
}
if (Test-ApplicationPort 8080) { throw 'Port 8080 is in use. The existing process has been left running.' }
$processRecords = @()
if (-not $WithoutAI) {
    & $pythonPath -X utf8 -c "import torch, transformers, numpy"
    if ($LASTEXITCODE -ne 0) { throw 'AI dependencies are missing. Install pipeline/requirements-transformers.txt, or start with -WithoutAI.' }
    if (Test-ApplicationPort 8002) { throw 'Port 8002 is in use. Start with -WithoutAI or stop the existing service.' }
    $env:HF_HUB_OFFLINE = '1'
    $env:TRANSFORMERS_OFFLINE = '1'
    $env:SUPPORTIQ_ENABLE_LLM = if ($DisableLLM) { 'false' } else { 'true' }
    $aiProcess = Start-Process -FilePath $pythonPath -ArgumentList @('-X','utf8','-m','uvicorn','apps.ai_service.main:create_app','--factory','--host','127.0.0.1','--port','8002','--no-access-log') -WorkingDirectory $repoRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $repoRoot '.local/ai.stdout.log') -RedirectStandardError (Join-Path $repoRoot '.local/ai.stderr.log')
    $processRecords += @{ Id = $aiProcess.Id; StartedAt = $aiProcess.StartTime.ToUniversalTime().ToString('o'); Kind = 'ai-service' }
    $env:SUPPORTIQ_AI_SERVICE_BASE_URL = 'http://127.0.0.1:8002'
} else { Remove-Item Env:SUPPORTIQ_AI_SERVICE_BASE_URL -ErrorAction SilentlyContinue }
$backendProcess = Start-Process -FilePath $pythonPath -ArgumentList @('-X','utf8','-m','uvicorn','apps.backend.main:create_app','--factory','--host','127.0.0.1','--port','8080','--no-access-log') -WorkingDirectory $repoRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $repoRoot '.local/backend.stdout.log') -RedirectStandardError (Join-Path $repoRoot '.local/backend.stderr.log')
$processRecords += @{ Id = $backendProcess.Id; StartedAt = $backendProcess.StartTime.ToUniversalTime().ToString('o'); Kind = 'backend' }
ConvertTo-Json -InputObject @($processRecords) | Set-Content -LiteralPath $processFile -Encoding utf8

$isReady = $false
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    try { $null = Invoke-RestMethod -Uri 'http://127.0.0.1:8080/health/ready' -TimeoutSec 2; $isReady = $true; break } catch { Start-Sleep -Milliseconds 500 }
}
if (-not $isReady) { throw 'Backend did not become ready. See .local/backend.stderr.log. Use scripts/stop-app.ps1 to stop the recorded processes.' }
Write-Host 'SupportIQ is running at http://127.0.0.1:8080'
Write-Host 'Login names: customer-1, staff-1, manager-1, admin-1. Passwords are in .local/application.json.'
Write-Host 'AI uses the existing ML model, embeddings and configured Gemini LLM. Use -DisableLLM to disable external drafting.'
Write-Host 'Stop with: .\scripts\stop-app.ps1'
