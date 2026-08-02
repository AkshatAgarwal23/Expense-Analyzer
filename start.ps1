# Start Postgres + Ollama (if needed) + FastAPI on port 8001.
# Usage (from repo root):  .\start.ps1

$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot

$pgCtl = "C:\Program Files\PostgreSQL\16\bin\pg_ctl.exe"
$pgData = "C:\Program Files\PostgreSQL\16\data"
$pgReady = "C:\Program Files\PostgreSQL\16\bin\pg_isready.exe"
$ollama = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
$uvicorn = Join-Path $PSScriptRoot ".venv\Scripts\uvicorn.exe"

Write-Host "==> PostgreSQL" -ForegroundColor Cyan
& $pgReady -h localhost -p 5432 2>$null | Out-Null
if ($LASTEXITCODE -eq 0) {
    Write-Host "    already running"
} else {
    & $pgCtl start -D $pgData -w
    if ($LASTEXITCODE -ne 0) {
        Write-Host "    failed to start Postgres" -ForegroundColor Red
        exit 1
    }
    Write-Host "    started"
}

Write-Host "==> Ollama" -ForegroundColor Cyan
$ollamaUp = $false
try {
    $null = Invoke-RestMethod "http://127.0.0.1:11434/api/tags" -TimeoutSec 2
    $ollamaUp = $true
} catch {
    $ollamaUp = $false
}

if ($ollamaUp) {
    Write-Host "    already running"
} elseif (Test-Path $ollama) {
    Start-Process $ollama -ArgumentList "serve" -WindowStyle Hidden
    Start-Sleep -Seconds 2
    try {
        $null = Invoke-RestMethod "http://127.0.0.1:11434/api/tags" -TimeoutSec 5
        Write-Host "    started"
    } catch {
        Write-Host "    started process (API not ready yet - Extract may need a few seconds)" -ForegroundColor Yellow
    }
} else {
    Write-Host "    not installed - voice Extract will fail until you install Ollama" -ForegroundColor Yellow
}

if (-not (Test-Path $uvicorn)) {
    Write-Host "==> Missing venv. Run: python -m venv .venv; .\.venv\Scripts\pip install -e `".[dev,voice]`"" -ForegroundColor Red
    exit 1
}

Write-Host "==> API  http://127.0.0.1:8001  (Ctrl+C to stop API only)" -ForegroundColor Cyan
Write-Host "    App UI:   http://127.0.0.1:8001/"
Write-Host "    Voice UI: http://127.0.0.1:8001/static/kharcha-voice-record.html"
& $uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
