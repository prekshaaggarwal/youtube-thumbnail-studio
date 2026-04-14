param(
    [int]$Port = 8080
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

Write-Host "Checking Python..." -ForegroundColor Cyan
$pythonPath = (& where.exe python 2>$null | Select-Object -First 1)
if ([string]::IsNullOrWhiteSpace($pythonPath)) {
    Write-Host ""
    Write-Host "Python is not installed or not in PATH." -ForegroundColor Red
    Write-Host "Install Python 3.11+ from: https://www.python.org/downloads/windows/" -ForegroundColor Yellow
    Write-Host "During install, check: Add python.exe to PATH" -ForegroundColor Yellow
    exit 1
}

python --version | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "Python command exists but is not runnable from PATH." -ForegroundColor Red
    Write-Host "Reinstall Python and enable: Add python.exe to PATH." -ForegroundColor Yellow
    exit 1
}

Write-Host "Creating virtual environment (if missing)..." -ForegroundColor Cyan
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    python -m venv .venv
}

Write-Host "Installing dependencies..." -ForegroundColor Cyan
& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { Write-Host "pip upgrade failed." -ForegroundColor Red; exit 1 }
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { Write-Host "pip install failed." -ForegroundColor Red; exit 1 }

if ($Port -eq 8080) {
    Write-Host "Checking port 8080 (clears stale servers that cause /studio 404)..." -ForegroundColor Cyan
    & ".\.venv\Scripts\python.exe" ".\scripts\port_8080.py"
    if ($LASTEXITCODE -eq 4) {
        Write-Host "This app is already running on http://127.0.0.1:8080/" -ForegroundColor Green
        if ($env:TSG_BROWSER_OPEN -ne "0") { Start-Process "http://127.0.0.1:8080/studio" }
        exit 0
    }
    if ($LASTEXITCODE -eq 2) {
        $Port = 8765
        Write-Host "Using port 8765 instead." -ForegroundColor Yellow
    }
}

Write-Host "Starting server in a new window (leave 'Thumbnail Studio Server' open)..." -ForegroundColor Green
$serverBat = Join-Path $PSScriptRoot "scripts\server-window.bat"
Start-Process -FilePath $serverBat -ArgumentList "$Port" -WorkingDirectory $PSScriptRoot
Write-Host "Waiting for /health on port $Port ..." -ForegroundColor DarkGray
& ".\.venv\Scripts\python.exe" ".\scripts\wait_for_health.py" "$Port"
if ($LASTEXITCODE -ne 0) {
    Write-Host "`nServer did not respond. Check the 'Thumbnail Studio Server' window for errors." -ForegroundColor Red
    Read-Host "Press Enter to close"
    exit 1
}
if ($env:TSG_BROWSER_OPEN -ne "0") {
    Start-Process "http://127.0.0.1:$Port/studio"
}
Write-Host "`nServer is running in the other CMD window. Close THAT window to stop the site." -ForegroundColor Cyan
Write-Host "This PowerShell window is safe to close." -ForegroundColor DarkGray
Read-Host "Press Enter to exit launcher"
