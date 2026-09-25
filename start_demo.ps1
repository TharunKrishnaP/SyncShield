# start_demo.ps1 - boot backend + frontend, wait for health, open dashboard.
# Run from the repo root:  powershell -ExecutionPolicy Bypass -File .\start_demo.ps1
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

# --- bail if already bound ---
if (Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue) {
    Write-Host "port 8000 busy - backend already running? aborting."
    return
}
if (Get-NetTCPConnection -State Listen -LocalPort 5173 -ErrorAction SilentlyContinue) {
    Write-Host "port 5173 busy - frontend already running? aborting."
    return
}

Write-Host "[1/3] starting backend (FastAPI :8000, DEBUG=false so uvicorn does NOT spawn a reloader child that survives kills) ..."
$env:DEBUG = 'false'
$backend = Start-Process python -ArgumentList 'backend/main.py' -WorkingDirectory $root `
    -RedirectStandardOutput "$root\backend_demo.log" -RedirectStandardError "$root\backend_demo.err.log" -PassThru -WindowStyle Hidden

Write-Host "[2/3] starting frontend (Vite :5173) ..."
$frontend = Start-Process npm.cmd -ArgumentList 'run dev' -WorkingDirectory "$root\frontend" `
    -RedirectStandardOutput "$root\frontend_demo.log" -RedirectStandardError "$root\frontend_demo.err.log" -PassThru -WindowStyle Hidden

# --- wait for backend health ---
$ready = $false
foreach ($i in 1..24) {
    Start-Sleep -Seconds 2
    try {
        $h = Invoke-RestMethod -Uri 'http://localhost:8000/api/health' -TimeoutSec 5
        if ($h.status -eq 'healthy') { $ready = $true; break }
    } catch {}
}
if (-not $ready) {
    Write-Host "backend did not become healthy. tail of backend_demo.err.log:"
    Get-Content "$root\backend_demo.err.log" -Tail 15 -ErrorAction SilentlyContinue
    exit 1
}
Write-Host "  backend healthy: $($h.status) | zones=$($h.zones) | live=$($h.live_sources)"

# --- wait for frontend ---
$fready = $false
foreach ($i in 1..18) {
    Start-Sleep -Seconds 2
    try {
        $code = (Invoke-WebRequest -Uri 'http://localhost:5173' -TimeoutSec 5 -UseBasicParsing).StatusCode
        if ($code -eq 200) { $fready = $true; break }
    } catch {}
}
if (-not $fready) {
    Write-Host "frontend did not come up. tail of frontend_demo.err.log:"
    Get-Content "$root\frontend_demo.err.log" -Tail 15 -ErrorAction SilentlyContinue
    exit 1
}
Write-Host "[3/3] dashboard ready - opening http://localhost:5173"
Start-Process 'http://localhost:5173'
Write-Host "backend  PID $($backend.Id)   frontend PID $($frontend.Id)"
Write-Host "logs: backend_demo.log / frontend_demo.log  (repo root)"