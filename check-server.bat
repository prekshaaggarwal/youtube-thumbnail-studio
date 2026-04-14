@echo off
title Check Thumbnail Studio server
cd /d "%~dp0"
echo.
echo === Who is LISTENING on 8080 / 8765? (empty = nothing running) ===
netstat -ano | findstr ":8080 "  | findstr "LISTENING"
netstat -ano | findstr ":8765 "  | findstr "LISTENING"
echo.

set "PY="
if exist ".venv\Scripts\python.exe" set "PY=%~dp0.venv\Scripts\python.exe"
if not defined PY where python >nul 2>&1 && set "PY=python"

if not defined PY (
  echo No Python found — install Python or run run-local.bat first.
  goto :end
)

echo === HTTP /health probe (Connection refused = server not started) ===
"%PY%" "%~dp0scripts\probe_health.py"
echo.
echo If both failed: double-click run-local.bat — wait until it says the server is up.
echo A SECOND window titled "Thumbnail Studio Server" must stay open (that is the site).
echo Then use: http://127.0.0.1:8080/studio  (port 8765 if run-local chose it)
echo.
:end
pause
