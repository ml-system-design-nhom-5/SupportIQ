param([switch]$StopDatabase)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$processFile = Join-Path $repoRoot '.local/processes.json'
if (Test-Path -LiteralPath $processFile) {
    $records = Get-Content -LiteralPath $processFile -Raw | ConvertFrom-Json
    foreach ($record in $records) {
        $running = Get-Process -Id $record.Id -ErrorAction SilentlyContinue
        if ($running -and $running.StartTime.ToUniversalTime().Ticks -eq ([datetime]$record.StartedAt).ToUniversalTime().Ticks) {
            $command = (Get-CimInstance Win32_Process -Filter "ProcessId=$($record.Id)").CommandLine
            if ($command -match 'uvicorn apps\.(backend|ai_service)\.main:create_app') {
                # Windows venv launchers run the actual interpreter as a child process.
                $children = Get-CimInstance Win32_Process -Filter "ParentProcessId=$($record.Id)"
                foreach ($child in $children) {
                    if ($child.CommandLine -match 'uvicorn apps\.(backend|ai_service)\.main:create_app') {
                        Stop-Process -Id $child.ProcessId -ErrorAction SilentlyContinue
                    }
                }
                Stop-Process -Id $record.Id -ErrorAction SilentlyContinue
            }
        }
    }
    Remove-Item -LiteralPath $processFile
}
if ($StopDatabase) {
    Push-Location -LiteralPath $repoRoot
    try { & (Join-Path $repoRoot '.venv/Scripts/python.exe') -X utf8 scripts/native_runtime.py stop } finally { Pop-Location }
}
Write-Host 'Recorded SupportIQ application processes have been stopped.'
