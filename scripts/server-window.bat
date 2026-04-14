@echo off
REM Runs Flask in THIS window — leave it open while you use the site.
title Thumbnail Studio Server
pushd "%~dp0.."

set "APP_PORT=%~1"
if "%APP_PORT%"=="" set "APP_PORT=8080"
set "APP_HOST=127.0.0.1"

set "PY="
if exist ".venv\Scripts\python.exe" set "PY=%CD%\.venv\Scripts\python.exe"
if not defined PY (
    echo [ERROR] No .venv\Scripts\python.exe in:
    echo   %CD%
    echo Run run-local.bat from this folder first.
    pause
    exit /b 1
)

echo.
echo  ============================================================
echo    Thumbnail Studio — KEEP THIS WINDOW OPEN
echo    Home:    http://127.0.0.1:%APP_PORT%/
echo    Studio:  http://127.0.0.1:%APP_PORT%/studio
echo  ============================================================
echo.

"%PY%" app.py
set "EX=%ERRORLEVEL%"
echo.
if not "%EX%"=="0" echo Server exited with code %EX%
echo.
echo Server stopped. You can close this window.
pause
popd
